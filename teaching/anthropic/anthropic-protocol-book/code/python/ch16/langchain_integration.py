"""
Chapter 16: LangChain Integration with Anthropic Claude.

Demonstrates:
  - ChatAnthropic instantiation and configuration
  - Tool binding with bind_tools() and StructuredTool
  - ChatPromptTemplate with MessagesPlaceholder
  - Memory integration (ConversationBufferMemory, ConversationSummaryMemory)
"""

from __future__ import annotations

from typing import Any, Literal

from langchain_anthropic import ChatAnthropic
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.tools import StructuredTool


# ---------------------------------------------------------------------------
# 1. ChatAnthropic instantiation
# ---------------------------------------------------------------------------

def create_model(
    model: str = "claude-sonnet-4-20250514",
    temperature: float = 0.3,
    max_tokens: int = 1024,
    timeout: float | None = 60.0,
    max_retries: int = 2,
) -> ChatAnthropic:
    """Create a configured ChatAnthropic instance.

    Args:
        model: Anthropic model name. Defaults to Claude Sonnet 4.
        temperature: Sampling temperature (0-1). Claude recommends 0.3-0.7.
        max_tokens: Maximum tokens in the response.
        timeout: Request timeout in seconds. None means no timeout.
        max_retries: Number of retries on failure.
    """
    return ChatAnthropic(
        model=model,
        temperature=temperature,
        max_tokens=max_tokens,
        timeout=timeout,
        max_retries=max_retries,
    )


# ---------------------------------------------------------------------------
# 2. Basic invocation
# ---------------------------------------------------------------------------

def basic_invoke(model: ChatAnthropic, user_input: str) -> str:
    """Send a simple message and return the text response."""
    response = model.invoke([HumanMessage(content=user_input)])
    assert isinstance(response, AIMessage)
    assert isinstance(response.content, str)
    return response.content


def streaming_invoke(model: ChatAnthropic, user_input: str) -> list[str]:
    """Stream the response tokens from Claude."""
    chunks: list[str] = []
    for chunk in model.stream([HumanMessage(content=user_input)]):
        if isinstance(chunk, AIMessage) and chunk.content:
            text = chunk.content if isinstance(chunk.content, str) else str(chunk.content)
            chunks.append(text)
    return chunks


async def async_invoke(model: ChatAnthropic, user_input: str) -> str:
    """Async invocation of the model."""
    response = await model.ainvoke([HumanMessage(content=user_input)])
    assert isinstance(response, AIMessage)
    assert isinstance(response.content, str)
    return response.content


# ---------------------------------------------------------------------------
# 3. Tool binding
# ---------------------------------------------------------------------------

def _get_weather(location: str) -> str:
    """Get the current weather in a given location."""
    weather_data = {
        "san francisco": "Sunny, 72°F, wind 5mph NW",
        "new york": "Cloudy, 58°F, wind 10mph NE",
        "beijing": "Partly cloudy, 25°C, wind 3m/s SE",
        "london": "Rainy, 12°C, wind 8m/s SW",
        "tokyo": "Clear, 20°C, wind 2m/s N",
        "sydney": "Sunny, 28°C, wind 4m/s E",
    }
    return weather_data.get(location.lower(), f"Weather data unavailable for {location}")


def _calculator(expression: str) -> str:
    """Evaluate a mathematical expression safely."""
    allowed = set("0123456789+-*/().% ")
    if not all(c in allowed for c in expression):
        return "Error: expression contains disallowed characters"
    try:
        result = eval(expression, {"__builtins__": {}})
        return str(result)
    except Exception as e:
        return f"Error evaluating expression: {e}"


def create_weather_tool() -> StructuredTool:
    """Create a weather query tool."""
    return StructuredTool.from_function(
        func=_get_weather,
        name="get_weather",
        description="Get the current weather in a given location. Input is city and state/country.",
    )


def create_calculator_tool() -> StructuredTool:
    """Create a calculator tool."""
    return StructuredTool.from_function(
        func=_calculator,
        name="calculator",
        description="Evaluate a mathematical expression. Supports +, -, *, /, (), %.",
    )


def bind_tools_to_model(
    model: ChatAnthropic,
    tools: list[StructuredTool],
) -> ChatAnthropic:
    """Bind tools to a ChatAnthropic model so it can call them."""
    return model.bind_tools(tools)  # type: ignore[return-value]


def execute_tool_calls(response: AIMessage, tools: list[StructuredTool]) -> list[ToolMessage]:
    """Execute tool calls from a model response.

    Returns a list of ToolMessage objects suitable for feeding back to the model.
    """
    tools_by_name = {tool.name: tool for tool in tools}
    results: list[ToolMessage] = []

    for tool_call in response.tool_calls:
        tool_name = tool_call.get("name", "")
        tool_args = tool_call.get("args", {})
        tool_id = tool_call.get("id", "")

        if tool_name in tools_by_name:
            tool = tools_by_name[tool_name]
            observation = str(tool.invoke(tool_args))
        else:
            observation = f"Error: unknown tool '{tool_name}'"

        results.append(ToolMessage(content=observation, tool_call_id=tool_id))

    return results


# ---------------------------------------------------------------------------
# 4. Prompt templates
# ---------------------------------------------------------------------------

def create_chat_prompt(
    system_prompt: str | None = None,
    include_history: bool = True,
    include_scratchpad: bool = True,
) -> ChatPromptTemplate:
    """Create a ChatPromptTemplate for Claude interactions.

    Args:
        system_prompt: Optional system instruction.
        include_history: Include a MessagesPlaceholder for conversation history.
        include_scratchpad: Include a MessagesPlaceholder for agent scratchpad
            (intermediate tool call results).

    Returns a ChatPromptTemplate with the configured components.
    """
    messages: list[Any] = []

    if system_prompt:
        messages.append(("system", system_prompt))

    if include_history:
        messages.append(MessagesPlaceholder(variable_name="history"))

    messages.append(("human", "{input}"))

    if include_scratchpad:
        messages.append(MessagesPlaceholder(variable_name="agent_scratchpad"))

    return ChatPromptTemplate.from_messages(messages)


def format_prompt(
    template: ChatPromptTemplate,
    user_input: str,
    history: list | None = None,
    agent_scratchpad: list | None = None,
) -> list:
    """Format a ChatPromptTemplate into message objects."""
    kwargs: dict[str, Any] = {"input": user_input}
    if history is not None:
        kwargs["history"] = history
    if agent_scratchpad is not None:
        kwargs["agent_scratchpad"] = agent_scratchpad
    return template.format_messages(**kwargs)


# ---------------------------------------------------------------------------
# 5. Memory integration
# ---------------------------------------------------------------------------

class ConversationBufferMemory:
    """A simple buffer-based conversation memory.

    Stores all messages and can inject them into prompts via the 'history' variable.
    """

    def __init__(self) -> None:
        self._messages: list[HumanMessage | AIMessage] = []

    @property
    def messages(self) -> list[HumanMessage | AIMessage]:
        return list(self._messages)

    def add_user_message(self, content: str) -> None:
        self._messages.append(HumanMessage(content=content))

    def add_ai_message(self, content: str) -> None:
        self._messages.append(AIMessage(content=content))

    def clear(self) -> None:
        self._messages.clear()

    def get_messages(self) -> list[HumanMessage | AIMessage]:
        return self.messages


class ConversationSummaryMemory:
    """Memory that summarizes old messages to keep the context window manageable.

    Uses a summary model (typically a fast model like Haiku) to periodically
    compress conversation history.
    """

    def __init__(
        self,
        summary_model: ChatAnthropic,
        max_summary_tokens: int = 256,
        summary_prompt: str = "Summarize the following conversation concisely, preserving key facts and decisions:",
    ) -> None:
        self._summary_model = summary_model
        self._max_summary_tokens = max_summary_tokens
        self._summary_prompt = summary_prompt
        self._summary: str = ""
        self._recent_messages: list[HumanMessage | AIMessage] = []

    @property
    def summary(self) -> str:
        return self._summary

    def add_user_message(self, content: str) -> None:
        self._recent_messages.append(HumanMessage(content=content))

    def add_ai_message(self, content: str) -> None:
        self._recent_messages.append(AIMessage(content=content))

    def summarize(self) -> str:
        """Generate a summary of recent messages and update internal state."""
        if not self._recent_messages:
            return self._summary

        summary_input: list = []
        if self._summary:
            summary_input.append(SystemMessage(
                content=f"Previous summary: {self._summary}"
            ))
        summary_input.append(HumanMessage(
            content=f"{self._summary_prompt}\n\n"
            + "\n".join(
                f"{'User' if isinstance(m, HumanMessage) else 'AI'}: {m.content}"
                for m in self._recent_messages
            )
        ))

        response = self._summary_model.invoke(summary_input)
        new_summary = response.content if isinstance(response.content, str) else str(response.content)

        # Update summary and merge recent into it
        if self._summary:
            self._summary = f"{self._summary}\n{new_summary}"
        else:
            self._summary = new_summary

        self._recent_messages.clear()
        return self._summary

    def get_context_messages(self) -> list:
        """Get the current context as messages ready for a prompt."""
        result: list = []
        if self._summary:
            result.append(SystemMessage(
                content=f"Conversation summary: {self._summary}"
            ))
        result.extend(self._recent_messages)
        return result


# ---------------------------------------------------------------------------
# 6. Full agent loop (tool-use with memory)
# ---------------------------------------------------------------------------

def run_agent_loop(
    model: ChatAnthropic,
    tools: list[StructuredTool],
    user_input: str,
    memory: ConversationBufferMemory | None = None,
    max_iterations: int = 5,
) -> str:
    """Run a complete agent loop: model -> tool calls -> execute -> repeat.

    Args:
        model: ChatAnthropic instance with tools bound.
        tools: Available tools.
        user_input: User's initial message.
        memory: Optional conversation memory.
        max_iterations: Maximum tool-call iterations.

    Returns:
        The final text response from the model.
    """
    if memory is None:
        memory = ConversationBufferMemory()

    memory.add_user_message(user_input)
    messages = memory.get_messages()

    for _ in range(max_iterations):
        response = model.invoke(messages)
        assert isinstance(response, AIMessage)

        # Check for tool calls
        if not response.tool_calls:
            memory.add_ai_message(
                response.content if isinstance(response.content, str) else ""
            )
            return response.content if isinstance(response.content, str) else str(response.content)

        # Execute tool calls
        tool_results = execute_tool_calls(response, tools)
        messages.append(response)
        messages.extend(tool_results)

    # Fallback: force model to respond without tools
    fallback = model.invoke(messages)
    return fallback.content if isinstance(fallback.content, str) else str(fallback.content)
