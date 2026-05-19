"""
Chapter 16: LangGraph Agent with Anthropic Claude.

Demonstrates:
  - StateGraph construction: nodes, edges, conditional edges
  - Checkpointing with InMemorySaver and SqliteSaver
  - Human-in-the-Loop via interrupt_before
  - Complete ReAct agent loop with tool calling
"""

from __future__ import annotations

import sqlite3
import uuid
from typing import Annotated, Any, Literal

from langchain_anthropic import ChatAnthropic
from langchain_core.messages import (
    AIMessage,
    BaseMessage,
    HumanMessage,
    ToolMessage,
)
from langchain_core.tools import StructuredTool
from langgraph.checkpoint.memory import InMemorySaver

try:
    from langgraph.checkpoint.sqlite import SqliteSaver
    _HAS_SQLITE_CHECKPOINT = True
except ImportError:
    _HAS_SQLITE_CHECKPOINT = False
    SqliteSaver = None  # type: ignore
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from langgraph.types import Command, interrupt
from typing_extensions import TypedDict


# ---------------------------------------------------------------------------
# State definition
# ---------------------------------------------------------------------------

class AgentState(TypedDict):
    """The state shared across all nodes in the LangGraph agent.

    ``messages`` uses ``add_messages`` as its reducer, which means new messages
    are appended rather than replacing the list.  Messages with the same ID
    replace earlier versions (useful for edits).
    """

    messages: Annotated[list[BaseMessage], add_messages]


# ---------------------------------------------------------------------------
# Tool definitions
# ---------------------------------------------------------------------------

def _get_weather(location: str) -> str:
    """Return simulated weather data for a location."""
    weather = {
        "san francisco": "Sunny, 72°F, wind 5mph NW",
        "new york": "Cloudy, 58°F, wind 10mph NE",
        "london": "Rainy, 12°C, wind 8m/s SW",
        "beijing": "Partly cloudy, 25°C, wind 3m/s SE",
    }
    return weather.get(location.lower(), f"No weather data for {location}")


def _calculator(expression: str) -> str:
    """Safely evaluate a numeric expression."""
    allowed = set("0123456789+-*/().% ")
    if not all(c in allowed for c in expression):
        return "Error: disallowed characters in expression"
    try:
        result = eval(expression, {"__builtins__": {}})
        return str(result)
    except Exception as e:
        return f"Error: {e}"


def _search(query: str) -> str:
    """Simulated search tool."""
    knowledge = {
        "capital of france": "Paris is the capital of France.",
        "largest planet": "Jupiter is the largest planet in our solar system.",
        "water boiling point": "Water boils at 100°C (212°F) at sea level.",
        "python creator": "Python was created by Guido van Rossum in 1991.",
    }
    query_lower = query.lower()
    for key, value in knowledge.items():
        if key in query_lower or query_lower in key:
            return value
    return f"No relevant results for: {query}"


def default_tools() -> list[StructuredTool]:
    """Return the standard tool set for the agent."""
    return [
        StructuredTool.from_function(
            func=_get_weather,
            name="get_weather",
            description="Get current weather for a location. Input: city name.",
        ),
        StructuredTool.from_function(
            func=_calculator,
            name="calculator",
            description="Evaluate a math expression. Supports +, -, *, /, (), %.",
        ),
        StructuredTool.from_function(
            func=_search,
            name="search",
            description="Search for factual information on a topic.",
        ),
    ]


# ---------------------------------------------------------------------------
# LangGraph node functions
# ---------------------------------------------------------------------------

def _create_llm_node(llm: ChatAnthropic):
    """Factory: create the 'call_model' node function."""

    def call_model(state: AgentState) -> dict[str, list[BaseMessage]]:
        """Invoke the LLM and return its response."""
        response = llm.invoke(state["messages"])
        return {"messages": [response]}

    return call_model


def _create_tool_node(tools: list[StructuredTool]):
    """Factory: create the 'tools' node function."""
    tools_by_name = {tool.name: tool for tool in tools}

    def execute_tools(state: AgentState) -> dict[str, list[BaseMessage]]:
        """Execute any pending tool calls in the most recent AI message."""
        last_message = state["messages"][-1]
        if not isinstance(last_message, AIMessage) or not last_message.tool_calls:
            return {"messages": []}

        results: list[ToolMessage] = []
        for tc in last_message.tool_calls:
            name = tc.get("name", "")
            args = tc.get("args", {})
            tc_id = tc.get("id", "")
            if name in tools_by_name:
                observation = str(tools_by_name[name].invoke(args))
            else:
                observation = f"Error: unknown tool '{name}'"
            results.append(ToolMessage(content=observation, tool_call_id=tc_id))

        return {"messages": results}

    return execute_tools


# ---------------------------------------------------------------------------
# Routing function
# ---------------------------------------------------------------------------

def _should_continue(state: AgentState) -> Literal["tools", "__end__"]:
    """Decide whether to call tools or end the conversation."""
    last_message = state["messages"][-1]
    if isinstance(last_message, AIMessage) and last_message.tool_calls:
        return "tools"
    return "__end__"


# ---------------------------------------------------------------------------
# Builder: create a standard ReAct agent
# ---------------------------------------------------------------------------

def build_react_agent(
    model: ChatAnthropic,
    tools: list[StructuredTool] | None = None,
) -> StateGraph:
    """Build a ReAct-style agent as a StateGraph.

    The graph structure::

        START → call_model ──(tool_calls?)──→ tools → call_model
                         └──(no calls)──→ END

    Args:
        model: A ChatAnthropic instance (tools should be pre-bound if needed).
        tools: Optional tool list. If provided, tools are injected via the
               ``tools`` node rather than model's native tool binding.

    Returns:
        An un-compiled StateGraph builder.
    """
    if tools is None:
        tools = default_tools()

    # Bind tools to the model so it can request them
    model_with_tools = model.bind_tools(tools)  # type: ignore[return-value]

    builder = StateGraph(AgentState)

    # Add nodes
    builder.add_node("call_model", _create_llm_node(model_with_tools))
    builder.add_node("tools", _create_tool_node(tools))

    # Add edges
    builder.add_edge(START, "call_model")
    builder.add_conditional_edges(
        "call_model",
        _should_continue,
        {"tools": "tools", "__end__": END},
    )
    builder.add_edge("tools", "call_model")

    return builder


# ---------------------------------------------------------------------------
# Agent variants
# ---------------------------------------------------------------------------

def build_agent_with_memory(
    model: ChatAnthropic,
    tools: list[StructuredTool] | None = None,
) -> Any:
    """Build a ReAct agent with in-memory checkpointing for multi-turn support."""
    builder = build_react_agent(model, tools)
    checkpointer = InMemorySaver()
    return builder.compile(checkpointer=checkpointer)


def build_agent_with_sqlite(
    model: ChatAnthropic,
    tools: list[StructuredTool] | None = None,
    db_path: str = ":memory:",
) -> Any:
    """Build a ReAct agent with SQLite-backed checkpointing.

    Requires ``langgraph-checkpoint-sqlite`` to be installed.  Falls back to
    an in-memory checkpointer when the package is unavailable.
    """
    builder = build_react_agent(model, tools)
    if _HAS_SQLITE_CHECKPOINT and SqliteSaver is not None:
        conn = sqlite3.connect(db_path, check_same_thread=False)
        checkpointer = SqliteSaver(conn)
    else:
        checkpointer = InMemorySaver()
    return builder.compile(checkpointer=checkpointer)


def build_agent_with_hitl(
    model: ChatAnthropic,
    tools: list[StructuredTool] | None = None,
) -> Any:
    """Build a ReAct agent that pauses before every tool invocation (HITL).

    Human-in-the-Loop: the agent stops before executing tools so a human
    reviewer can approve or reject each tool call.
    """
    builder = build_react_agent(model, tools)
    checkpointer = InMemorySaver()
    return builder.compile(
        checkpointer=checkpointer,
        interrupt_before=["tools"],
    )


# ---------------------------------------------------------------------------
# HITL agent with dynamic interrupt
# ---------------------------------------------------------------------------

def build_agent_with_dynamic_interrupt(
    model: ChatAnthropic,
    tools: list[StructuredTool] | None = None,
) -> Any:
    """Build an agent where a node can dynamically request human input.

    This uses the ``interrupt()`` function inside a node to pause execution
    and wait for human approval before proceeding.
    """
    if tools is None:
        tools = default_tools()

    model_with_tools = model.bind_tools(tools)  # type: ignore[return-value]

    def call_model_with_review(state: AgentState) -> dict[str, list[BaseMessage]]:
        """Invoke the LLM, then request human review of any tool calls."""
        response = model_with_tools.invoke(state["messages"])

        # If tool calls are present, ask for human approval
        if isinstance(response, AIMessage) and response.tool_calls:
            approval = interrupt({
                "message": "Tool calls requested. Approve?",
                "tool_calls": [
                    {"name": tc.get("name"), "args": tc.get("args")}
                    for tc in response.tool_calls
                ],
            })
            if not approval:
                # Human rejected: send a message telling the model to stop
                rejection = AIMessage(content="The tool calls were rejected by the reviewer. Please respond without using tools.")
                return {"messages": [rejection]}

        return {"messages": [response]}

    builder = StateGraph(AgentState)
    builder.add_node("call_model", call_model_with_review)
    builder.add_node("tools", _create_tool_node(tools))
    builder.add_edge(START, "call_model")
    builder.add_conditional_edges(
        "call_model",
        _should_continue,
        {"tools": "tools", "__end__": END},
    )
    builder.add_edge("tools", "call_model")

    checkpointer = InMemorySaver()
    return builder.compile(checkpointer=checkpointer)


# ---------------------------------------------------------------------------
# Helper: invoke agent and collect messages
# ---------------------------------------------------------------------------

def run_agent(
    compiled_agent: Any,
    user_input: str,
    thread_id: str | None = None,
    config_extra: dict | None = None,
) -> dict:
    """Run a compiled agent with a user message.

    Args:
        compiled_agent: A compiled StateGraph.
        user_input: The user's message text.
        thread_id: Checkpointer thread ID. Auto-generated if not provided.
        config_extra: Additional config keys.

    Returns:
        The final state dict after agent execution.
    """
    if thread_id is None:
        thread_id = str(uuid.uuid4())

    config: dict[str, Any] = {
        "configurable": {"thread_id": thread_id},
    }
    if config_extra:
        config["configurable"].update(config_extra)

    return compiled_agent.invoke(
        {"messages": [HumanMessage(content=user_input)]},
        config,
    )


def stream_agent(
    compiled_agent: Any,
    user_input: str,
    thread_id: str | None = None,
) -> list[dict]:
    """Stream agent execution, collecting all chunks."""
    if thread_id is None:
        thread_id = str(uuid.uuid4())

    config: dict[str, Any] = {
        "configurable": {"thread_id": thread_id},
    }

    chunks: list[dict] = []
    for chunk in compiled_agent.stream(
        {"messages": [HumanMessage(content=user_input)]},
        config,
    ):
        chunks.append(chunk)
    return chunks
