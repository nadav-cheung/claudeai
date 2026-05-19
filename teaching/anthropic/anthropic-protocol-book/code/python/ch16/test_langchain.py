"""
Tests for Chapter 16: LangChain & LangGraph integration.

These tests mock the underlying Anthropic SDK calls to avoid real network access.
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from langchain_integration import (
    ConversationBufferMemory,
    ConversationSummaryMemory,
    bind_tools_to_model,
    create_calculator_tool,
    create_chat_prompt,
    create_model,
    create_weather_tool,
    execute_tool_calls,
    format_prompt,
    run_agent_loop,
)
from langgraph_agent import (
    AgentState,
    build_agent_with_hitl,
    build_agent_with_memory,
    build_agent_with_sqlite,
    build_react_agent,
    default_tools,
    run_agent,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_fake_ai_message(content: str, tool_calls: list | None = None) -> MagicMock:
    """Build a mock AIMessage that behaves like a langchain_core AIMessage."""
    from langchain_core.messages import AIMessage

    msg = MagicMock(spec=AIMessage)
    msg.content = content
    msg.tool_calls = tool_calls or []
    # Make isinstance checks pass
    msg.__class__ = AIMessage
    return msg


def mock_model_response(content: str = "Hello! How can I help?", tool_calls: list | None = None):
    """Create a mock for ChatAnthropic.invoke that returns a canned response."""
    msg = MagicMock()
    msg.content = content
    msg.tool_calls = tool_calls or []
    msg.__class__ = __import__("langchain_core.messages", fromlist=["AIMessage"]).AIMessage
    return msg


# ---------------------------------------------------------------------------
# Test: ChatAnthropic instantiation
# ---------------------------------------------------------------------------

class TestChatAnthropic:
    def test_create_model_with_defaults(self):
        model = create_model()
        assert model.model == "claude-sonnet-4-20250514"

    def test_create_model_custom_params(self):
        model = create_model(
            model="claude-haiku-4-5-20251001",
            temperature=0.7,
            max_tokens=512,
            timeout=30.0,
            max_retries=3,
        )
        assert model.model == "claude-haiku-4-5-20251001"
        assert model.temperature == 0.7
        assert model.max_tokens == 512
        assert model.default_request_timeout == 30.0
        assert model.max_retries == 3

    @patch("langchain_anthropic.ChatAnthropic.invoke")
    def test_basic_invoke(self, mock_invoke):
        from langchain_integration import basic_invoke

        mock_invoke.return_value = mock_model_response("Hi there!")

        model = create_model()
        result = basic_invoke(model, "Hello")
        assert result == "Hi there!"

    @patch("langchain_anthropic.ChatAnthropic.stream")
    def test_streaming_invoke(self, mock_stream):
        from langchain_integration import streaming_invoke

        mock_stream.return_value = [
            mock_model_response("Hello"),
            mock_model_response(" world"),
            mock_model_response("!"),
        ]

        model = create_model()
        chunks = streaming_invoke(model, "Say hello")
        assert len(chunks) == 3
        assert chunks == ["Hello", " world", "!"]


# ---------------------------------------------------------------------------
# Test: Tool binding
# ---------------------------------------------------------------------------

class TestToolBinding:
    def test_create_weather_tool(self):
        tool = create_weather_tool()
        assert tool.name == "get_weather"
        result = tool.invoke({"location": "San Francisco"})
        assert "72°F" in result

    def test_create_calculator_tool(self):
        tool = create_calculator_tool()
        assert tool.name == "calculator"
        result = tool.invoke({"expression": "2 + 3 * 4"})
        assert "14" in result

    def test_bind_tools_to_model(self):
        model = create_model()
        tools = [create_weather_tool(), create_calculator_tool()]
        bound = bind_tools_to_model(model, tools)
        # A bound model should still support invoke
        assert bound is not None
        assert hasattr(bound, "invoke")

    def test_execute_tool_calls(self):
        tools = [create_weather_tool(), create_calculator_tool()]
        msg = make_fake_ai_message("", tool_calls=[
            {"name": "get_weather", "args": {"location": "London"}, "id": "tc-1"},
            {"name": "calculator", "args": {"expression": "10/2"}, "id": "tc-2"},
        ])
        results = execute_tool_calls(msg, tools)
        assert len(results) == 2
        assert "Rainy" in results[0].content
        assert "5.0" in results[1].content
        assert results[0].tool_call_id == "tc-1"
        assert results[1].tool_call_id == "tc-2"

    def test_execute_tool_calls_unknown_tool(self):
        tools = [create_weather_tool()]
        msg = make_fake_ai_message("", tool_calls=[
            {"name": "nonexistent_tool", "args": {}, "id": "tc-1"},
        ])
        results = execute_tool_calls(msg, tools)
        assert len(results) == 1
        assert "unknown tool" in results[0].content.lower()

    @patch("langchain_anthropic.ChatAnthropic.invoke")
    def test_run_agent_loop_with_tools(self, mock_invoke):
        """Agent loop: first call has tool_calls, second is final answer."""
        tools = [create_calculator_tool()]

        call1 = make_fake_ai_message("", tool_calls=[
            {"name": "calculator", "args": {"expression": "3 + 5"}, "id": "tc-1"},
        ])
        call2 = make_fake_ai_message("The result is 8.", tool_calls=[])

        mock_invoke.side_effect = [call1, call2]

        model = create_model()
        bound = bind_tools_to_model(model, tools)

        result = run_agent_loop(bound, tools, "What is 3 + 5?")
        assert "8" in result
        assert mock_invoke.call_count == 2

    @patch("langchain_anthropic.ChatAnthropic.invoke")
    def test_run_agent_loop_no_tools(self, mock_invoke):
        """Agent loop: model answers directly without tool calls."""
        mock_invoke.return_value = make_fake_ai_message("I am Claude, nice to meet you!", tool_calls=[])
        model = create_model()
        result = run_agent_loop(model, [], "Hello!")
        assert "Claude" in result
        assert mock_invoke.call_count == 1


# ---------------------------------------------------------------------------
# Test: Prompt templates
# ---------------------------------------------------------------------------

class TestPromptTemplates:
    def test_create_chat_prompt_basic(self):
        prompt = create_chat_prompt(system_prompt="You are helpful.")
        assert prompt is not None
        messages = prompt.format_messages(input="Hi", history=[], agent_scratchpad=[])
        # system + history resolved to empty + human + scratchpad resolved to empty
        # MessagesPlaceholder with empty list resolves to zero messages
        assert len(messages) == 2  # system, human (placeholders resolve to nothing)

    def test_create_chat_prompt_no_scratchpad(self):
        prompt = create_chat_prompt(include_scratchpad=False)
        messages = prompt.format_messages(input="Hi", history=[])
        # history placeholder (empty) + human message
        assert len(messages) == 1  # human only (empty history placeholder resolves to nothing)

    def test_format_prompt_with_all_fields(self):
        from langchain_core.messages import HumanMessage

        prompt = create_chat_prompt(system_prompt="You are helpful.")
        messages = format_prompt(
            prompt,
            user_input="Hello",
            history=[HumanMessage(content="Previous message")],
            agent_scratchpad=[],
        )
        assert len(messages) == 3  # system, history (1 msg), human (empty scratchpad resolves to nothing)


# ---------------------------------------------------------------------------
# Test: Memory
# ---------------------------------------------------------------------------

class TestConversationBufferMemory:
    def test_initial_empty(self):
        memory = ConversationBufferMemory()
        assert len(memory.messages) == 0

    def test_add_and_retrieve(self):
        memory = ConversationBufferMemory()
        memory.add_user_message("Hello")
        memory.add_ai_message("Hi there!")
        assert len(memory.messages) == 2
        assert memory.messages[0].content == "Hello"
        assert memory.messages[1].content == "Hi there!"

    def test_clear(self):
        memory = ConversationBufferMemory()
        memory.add_user_message("Hello")
        memory.clear()
        assert len(memory.messages) == 0

    def test_messages_are_copied(self):
        memory = ConversationBufferMemory()
        memory.add_user_message("Hello")
        msgs = memory.messages
        msgs.append("bad")  # Should not affect internal state
        assert len(memory.messages) == 1


class TestConversationSummaryMemory:
    def test_initial_empty(self):
        model = create_model()
        memory = ConversationSummaryMemory(summary_model=model)
        assert memory.summary == ""

    @patch("langchain_anthropic.ChatAnthropic.invoke")
    def test_summarize_generates_summary(self, mock_invoke):
        mock_invoke.return_value = mock_model_response(
            "User greeted, AI responded helpfully."
        )
        model = create_model()
        memory = ConversationSummaryMemory(summary_model=model)
        memory.add_user_message("Hello")
        memory.add_ai_message("Hi there!")
        result = memory.summarize()
        assert "greeted" in result.lower()
        assert len(memory._recent_messages) == 0  # cleared after summary


# ---------------------------------------------------------------------------
# Test: LangGraph agent
# ---------------------------------------------------------------------------

class TestLangGraphAgent:
    def test_build_react_agent_builder(self):
        model = create_model()
        builder = build_react_agent(model)
        assert builder is not None
        # Builder should have nodes registered
        # We verify by compiling it
        agent = builder.compile()
        assert agent is not None

    def test_build_agent_with_memory(self):
        model = create_model()
        agent = build_agent_with_memory(model)
        assert agent is not None

    def test_build_agent_with_sqlite(self):
        model = create_model()
        agent = build_agent_with_sqlite(model, db_path=":memory:")
        assert agent is not None

    def test_build_agent_with_hitl(self):
        model = create_model()
        agent = build_agent_with_hitl(model)
        assert agent is not None

    def test_default_tools(self):
        tools = default_tools()
        assert len(tools) == 3
        tool_names = {t.name for t in tools}
        assert tool_names == {"get_weather", "calculator", "search"}

    @patch("langchain_anthropic.ChatAnthropic.invoke")
    def test_run_agent_no_tools(self, mock_invoke):
        """Agent responds without tool calls."""
        from langchain_core.messages import AIMessage as RealAIMessage

        mock_invoke.return_value = RealAIMessage(
            content="Hello! How can I assist you today?"
        )

        model = create_model()
        agent = build_agent_with_memory(model, tools=[])

        result = run_agent(agent, "Hello!")
        msgs = result.get("messages", [])
        assert len(msgs) >= 1
        last_msg = msgs[-1]
        assert "Hello" in str(last_msg.content)

    @patch("langchain_anthropic.ChatAnthropic.invoke")
    def test_run_agent_with_tool_calls(self, mock_invoke):
        """Agent calls a tool and then responds."""
        # First call: tool call for weather
        call1 = __import__("langchain_core.messages", fromlist=["AIMessage"]).AIMessage(
            content="",
            tool_calls=[{
                "name": "get_weather",
                "args": {"location": "San Francisco"},
                "id": "tc-1",
            }],
        )
        # Second call: final answer
        call2 = __import__("langchain_core.messages", fromlist=["AIMessage"]).AIMessage(
            content="The weather in San Francisco is Sunny, 72°F."
        )

        mock_invoke.side_effect = [call1, call2]

        model = create_model()
        agent = build_agent_with_memory(model)

        result = run_agent(agent, "What is the weather in San Francisco?")
        msgs = result.get("messages", [])
        # Should have: HumanMessage, AIMessage(tool_calls), ToolMessage, AIMessage(final)
        assert len(msgs) >= 3
        # Verify tool was executed
        tool_messages = [m for m in msgs if m.type == "tool"]
        assert len(tool_messages) >= 1
        assert "72" in str(tool_messages[0].content)

    def test_run_agent_with_thread_id(self):
        """Thread ID enables multi-turn conversation persistence."""
        model = create_model()

        with patch("langchain_anthropic.ChatAnthropic.invoke") as mock_invoke:
            mock_invoke.side_effect = [
                __import__("langchain_core.messages", fromlist=["AIMessage"]).AIMessage(
                    content="I remember: your name is Alice."
                ),
                __import__("langchain_core.messages", fromlist=["AIMessage"]).AIMessage(
                    content="Your name is Alice, as you told me earlier."
                ),
            ]

            agent = build_agent_with_memory(model, tools=[])
            thread_id = "test-conversation-1"

            # Turn 1
            result1 = run_agent(agent, "My name is Alice.", thread_id=thread_id)
            # Turn 2: should use same thread
            result2 = run_agent(agent, "What is my name?", thread_id=thread_id)

            msgs2 = result2.get("messages", [])
            # With checkpointing, the conversation history is maintained
            assert len(msgs2) >= 2


# ---------------------------------------------------------------------------
# Test: HITL agent
# ---------------------------------------------------------------------------

class TestHumanInTheLoop:
    def test_hitl_agent_interrupts_before_tools(self):
        model = create_model()
        agent = build_agent_with_hitl(model)

        config = {"configurable": {"thread_id": "hitl-test-1"}}

        with patch("langchain_anthropic.ChatAnthropic.invoke") as mock_invoke:
            mock_invoke.return_value = __import__(
                "langchain_core.messages", fromlist=["AIMessage"]
            ).AIMessage(
                content="",
                tool_calls=[{
                    "name": "get_weather",
                    "args": {"location": "London"},
                    "id": "tc-h-1",
                }],
            )

            # With interrupt_before="tools", the graph pauses BEFORE executing tools.
            # The invoke call itself completes, but the state shows an interrupt.
            result = agent.invoke(
                {"messages": [__import__("langchain_core.messages", fromlist=["HumanMessage"]).HumanMessage(
                    content="Weather in London?"
                )]},
                config,
            )

            # After interrupt_before pause, the state should exist
            state = agent.get_state(config)
            assert state is not None

            # The result should contain messages up to the LLM response
            msgs = result.get("messages", [])
            assert len(msgs) >= 1  # At minimum the AIMessage with tool_calls
            # The tool should NOT have been executed yet (interrupted before tools)
            tool_msgs = [m for m in msgs if m.type == "tool"]
            assert len(tool_msgs) == 0

    def test_hitl_agent_no_tool_call_passes_through(self):
        """When no tool calls are made, HITL agent should complete without interrupt."""
        model = create_model()
        agent = build_agent_with_hitl(model)

        config = {"configurable": {"thread_id": "hitl-no-tool"}}

        with patch("langchain_anthropic.ChatAnthropic.invoke") as mock_invoke:
            mock_invoke.return_value = __import__(
                "langchain_core.messages", fromlist=["AIMessage"]
            ).AIMessage(content="Hello! I am Claude. No tools needed.")

            result = agent.invoke(
                {"messages": [__import__("langchain_core.messages", fromlist=["HumanMessage"]).HumanMessage(
                    content="Say hello"
                )]},
                config,
            )

            msgs = result.get("messages", [])
            assert any("Claude" in (m.content or "") for m in msgs)


# ---------------------------------------------------------------------------
# Test: LangGraph with search tool
# ---------------------------------------------------------------------------

class TestAgentSearch:
    @patch("langchain_anthropic.ChatAnthropic.invoke")
    def test_search_tool_routing(self, mock_invoke):
        """Verify the agent can route to search tool."""
        call1 = __import__("langchain_core.messages", fromlist=["AIMessage"]).AIMessage(
            content="",
            tool_calls=[{
                "name": "search",
                "args": {"query": "capital of France"},
                "id": "tc-search-1",
            }],
        )
        call2 = __import__("langchain_core.messages", fromlist=["AIMessage"]).AIMessage(
            content="The capital of France is Paris."
        )

        mock_invoke.side_effect = [call1, call2]

        model = create_model()
        agent = build_agent_with_memory(model)

        result = run_agent(agent, "What is the capital of France?")
        msgs = result.get("messages", [])
        tool_msgs = [m for m in msgs if m.type == "tool"]
        assert len(tool_msgs) >= 1
        assert "Paris" in str(tool_msgs[0].content)
