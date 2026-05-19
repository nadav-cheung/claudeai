"""
Chapter 14: Agent Loop -- ReAct (Reasoning + Acting) implementation.

Implements the foundational agent execution loop:
    Perceive -> Reason -> Act -> Observe

Uses the Anthropic Messages API + Tool Use to build an autonomous
agent that iteratively reasons about its task, calls tools, observes
results, and decides when the task is complete.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------


@dataclass
class ToolCall:
    """Represents a tool call extracted from an assistant response."""

    tool_id: str
    name: str
    input: Dict[str, Any]


@dataclass
class ToolResult:
    """Result of executing a single tool."""

    tool_use_id: str
    success: bool
    content: str
    error: Optional[str] = None


@dataclass
class AgentLoopResult:
    """Final result returned by an AgentLoop run."""

    success: bool
    answer: str
    iterations: int
    tool_calls_made: int
    total_tokens: int
    trajectory: List[Dict[str, Any]] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Agent Loop
# ---------------------------------------------------------------------------


class AgentLoop:
    """Core ReAct-style agent loop.

    Executes::

        while not done and remaining_iterations > 0:
            response = model(messages, tools)
            if stop_reason == "end_turn":
                done
            elif stop_reason == "tool_use":
                execute requested tools
                append results to messages
                continue

    The ``client`` is expected to have a ``messages.create()`` method
    compatible with the Anthropic Python SDK.

    The ``tool_executor`` is a callable that receives ``(tool_name, tool_input)``
    and returns a ``ToolResult``.

    Usage::

        loop = AgentLoop(client, tool_executor)
        result = loop.run("Find all Python files and count lines")
    """

    def __init__(
        self,
        client: Any,
        tool_executor: Callable[[str, Dict[str, Any]], ToolResult],
        *,
        tools: Optional[List[Dict[str, Any]]] = None,
        system_prompt: str = "",
        model: str = "claude-sonnet-4-20250514",
        max_iterations: int = 10,
        max_tokens_per_response: int = 4096,
    ) -> None:
        self._client = client
        self._tool_executor = tool_executor
        self._tools = tools or []
        self._system_prompt = system_prompt
        self._model = model
        self._max_iterations = max_iterations
        self._max_tokens_per_response = max_tokens_per_response

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def run(self, task: str) -> AgentLoopResult:
        """Execute the agent loop for a given task.

        Returns an ``AgentLoopResult`` with the final answer, iteration
        count, token usage, and full execution trajectory.
        """
        messages: List[Dict[str, Any]] = [
            {"role": "user", "content": task}
        ]
        iterations = 0
        tool_calls_made = 0
        total_tokens = 0
        trajectory: List[Dict[str, Any]] = []
        final_answer = ""

        while iterations < self._max_iterations:
            iterations += 1

            # --- PERCEIVE & REASON ---
            response = self._call_model(messages)
            total_tokens += self._extract_tokens(response)

            stop_reason = response.get("stop_reason", "")
            content_blocks = self._extract_content(response)

            if stop_reason == "end_turn":
                # Task complete -- extract text answer
                final_answer = self._extract_text(content_blocks)
                trajectory.append({
                    "iteration": iterations,
                    "type": "complete",
                    "text": final_answer,
                })
                break

            if stop_reason == "tool_use":
                # --- ACT & OBSERVE ---
                tool_calls = self._parse_tool_calls(content_blocks)
                if not tool_calls:
                    # Model stopped with tool_use but no valid tool blocks
                    # Treat as completion to avoid infinite loop
                    final_answer = "[Agent stopped with no actionable tool calls]"
                    trajectory.append({
                        "iteration": iterations,
                        "type": "stalled",
                    })
                    break

                # Append assistant message (with tool_use blocks)
                messages.append({
                    "role": "assistant",
                    "content": content_blocks,
                })

                # Execute tools and collect results
                tool_results: List[Dict[str, Any]] = []
                for tc in tool_calls:
                    tool_calls_made += 1
                    result = self._tool_executor(tc.name, tc.input)
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": tc.tool_id,
                        "content": result.content,
                        "is_error": not result.success,
                    })
                    trajectory.append({
                        "iteration": iterations,
                        "type": "tool_call",
                        "tool": tc.name,
                        "input": tc.input,
                        "success": result.success,
                    })

                # Append tool results as a user message
                messages.append({
                    "role": "user",
                    "content": tool_results,
                })
                continue

            # Unknown stop_reason -- treat as completion
            final_answer = self._extract_text(content_blocks)
            trajectory.append({
                "iteration": iterations,
                "type": "unknown_stop",
                "stop_reason": stop_reason,
            })
            break

        else:
            # max_iterations reached
            final_answer = (
                f"[Reached maximum iterations ({self._max_iterations}). "
                "Task may be incomplete.]"
            )
            trajectory.append({
                "iteration": iterations,
                "type": "max_iterations",
            })

        return AgentLoopResult(
            success=iterations <= self._max_iterations,
            answer=final_answer,
            iterations=iterations,
            tool_calls_made=tool_calls_made,
            total_tokens=total_tokens,
            trajectory=trajectory,
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _call_model(self, messages: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Send messages to the model and return the raw response."""
        kwargs: Dict[str, Any] = {
            "model": self._model,
            "max_tokens": self._max_tokens_per_response,
            "messages": messages,
        }
        if self._system_prompt:
            kwargs["system"] = self._system_prompt
        if self._tools:
            kwargs["tools"] = self._tools
        return self._client.messages.create(**kwargs)

    @staticmethod
    def _extract_content(response: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Extract content blocks from response."""
        content = response.get("content", [])
        if isinstance(content, list):
            return content
        if isinstance(content, str):
            return [{"type": "text", "text": content}]
        return []

    @staticmethod
    def _extract_text(blocks: List[Dict[str, Any]]) -> str:
        """Extract concatenated text from content blocks."""
        parts: List[str] = []
        for block in blocks:
            if block.get("type") == "text":
                parts.append(block.get("text", ""))
        return "\n".join(parts)

    @staticmethod
    def _parse_tool_calls(blocks: List[Dict[str, Any]]) -> List[ToolCall]:
        """Extract tool_use blocks from content."""
        calls: List[ToolCall] = []
        for block in blocks:
            if block.get("type") == "tool_use":
                try:
                    tool_input = block.get("input", {})
                    if isinstance(tool_input, str):
                        tool_input = json.loads(tool_input)
                    calls.append(ToolCall(
                        tool_id=block.get("id", ""),
                        name=block.get("name", ""),
                        input=tool_input,
                    ))
                except (json.JSONDecodeError, TypeError):
                    logger.warning("Failed to parse tool input: %s", block)
        return calls

    @staticmethod
    def _extract_tokens(response: Dict[str, Any]) -> int:
        """Extract total token usage from response."""
        usage = response.get("usage", {})
        return usage.get("input_tokens", 0) + usage.get("output_tokens", 0)
