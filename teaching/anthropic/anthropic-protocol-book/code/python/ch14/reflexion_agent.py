"""
Chapter 14: Reflexion Agent.

Extends ReAct Agent Loop with post-execution self-evaluation and
strategy adjustment. After each full trajectory, the agent reflects
on what worked, what failed, and how to improve before retrying.

Pattern:  ReAct Loop -> Evaluate -> Reflect -> Adjust -> Retry
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

from agent_loop import AgentLoop, AgentLoopResult, ToolResult


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------


@dataclass
class ReflectionResult:
    """Output of a single reflection cycle."""

    success: bool
    strategy_adjustment: str
    lessons_learned: List[str]
    should_retry: bool
    confidence: float  # 0.0 - 1.0


@dataclass
class ReflexionAgentResult:
    """Final result after potentially multiple reflection cycles."""

    success: bool
    answer: str
    total_iterations: int
    total_tool_calls: int
    total_tokens: int
    reflection_cycles: int
    all_trajectories: List[List[Dict[str, Any]]] = field(default_factory=list)
    reflections: List[ReflectionResult] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Reflexion Agent
# ---------------------------------------------------------------------------


class ReflexionAgent:
    """Agent that uses reflection to improve over multiple attempts.

    Extends the base ``AgentLoop`` with a meta-cognitive layer. After
    each trajectory, it calls the model as an evaluator to analyze what
    worked and what didn't, then injects improvement suggestions into
    the next attempt.

    Usage::

        agent = ReflexionAgent(client, tool_executor)
        result = agent.run("Debug the failing test suite")
    """

    def __init__(
        self,
        client: Any,
        tool_executor: Callable[[str, Dict[str, Any]], ToolResult],
        *,
        tools: Optional[List[Dict[str, Any]]] = None,
        system_prompt: str = "",
        model: str = "claude-sonnet-4-20250514",
        max_iterations_per_attempt: int = 10,
        max_reflection_cycles: int = 3,
        max_tokens_per_response: int = 4096,
    ) -> None:
        self._client = client
        self._tool_executor = tool_executor
        self._tools = tools or []
        self._system_prompt = system_prompt
        self._model = model
        self._max_iterations_per_attempt = max_iterations_per_attempt
        self._max_reflection_cycles = max_reflection_cycles
        self._max_tokens_per_response = max_tokens_per_response

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def run(self, task: str) -> ReflexionAgentResult:
        """Run the reflexion agent for a task.

        1. Execute the base AgentLoop (ReAct).
        2. Reflect on the trajectory.
        3. If reflection suggests a retry, adjust strategy and re-execute.
        4. Repeat until success or max reflection cycles reached.
        """
        all_trajectories: List[List[Dict[str, Any]]] = []
        reflections: List[ReflectionResult] = []
        total_iterations = 0
        total_tool_calls = 0
        total_tokens = 0
        final_answer = ""
        success = False
        cycles = 0

        current_task = task
        accumulated_lessons: List[str] = []

        for cycle in range(self._max_reflection_cycles):
            cycles += 1

            # Build enhanced system prompt with accumulated lessons
            enhanced_prompt = self._system_prompt
            if accumulated_lessons:
                lessons_text = "\n".join(
                    f"- {lesson}" for lesson in accumulated_lessons
                )
                enhanced_prompt = (
                    f"{self._system_prompt}\n\n"
                    f"## Previous Attempts & Lessons Learned\n\n"
                    f"{lessons_text}\n\n"
                    f"Please apply these lessons in your approach."
                )

            # --- Execute ---
            loop = AgentLoop(
                client=self._client,
                tool_executor=self._tool_executor,
                tools=self._tools,
                system_prompt=enhanced_prompt,
                model=self._model,
                max_iterations=self._max_iterations_per_attempt,
                max_tokens_per_response=self._max_tokens_per_response,
            )
            loop_result = loop.run(current_task)

            all_trajectories.append(loop_result.trajectory)
            total_iterations += loop_result.iterations
            total_tool_calls += loop_result.tool_calls_made
            total_tokens += loop_result.total_tokens

            # --- Reflect ---
            reflection = self.reflect(loop_result.trajectory)
            reflections.append(reflection)

            if reflection.success:
                final_answer = loop_result.answer
                success = True
                break

            if not reflection.should_retry:
                final_answer = (
                    f"{loop_result.answer}\n\n"
                    f"[Reflection determined no further improvement is likely. "
                    f"Confidence: {reflection.confidence:.0%}]"
                )
                break

            # --- Adjust ---
            accumulated_lessons.extend(reflection.lessons_learned)
            # Update task with reflection feedback
            current_task = (
                f"{task}\n\n"
                f"[Strategy Adjustment from Previous Attempt]:\n"
                f"{reflection.strategy_adjustment}"
            )

        else:
            final_answer = (
                f"{final_answer}\n\n"
                f"[Max reflection cycles ({self._max_reflection_cycles}) reached. "
                f"Best effort result returned.]"
            )

        return ReflexionAgentResult(
            success=success,
            answer=final_answer,
            total_iterations=total_iterations,
            total_tool_calls=total_tool_calls,
            total_tokens=total_tokens,
            reflection_cycles=cycles,
            all_trajectories=all_trajectories,
            reflections=reflections,
        )

    # ------------------------------------------------------------------
    # Reflection engine
    # ------------------------------------------------------------------

    def reflect(self, trajectory: List[Dict[str, Any]]) -> ReflectionResult:
        """Analyze a trajectory and produce a reflection.

        Uses the LLM as an evaluator to assess whether the task was
        completed successfully, what lessons were learned, and how
        the strategy should change for a retry.

        Args:
            trajectory: The full execution trace from an AgentLoop run.

        Returns:
            A ``ReflectionResult`` with evaluation outcome and strategy changes.
        """
        trajectory_text = self._format_trajectory(trajectory)

        reflection_prompt = (
            "You are an agent strategy evaluator. Analyze the following "
            "agent execution trajectory and determine:\n\n"
            "1. Did the agent successfully complete the task? (yes/no)\n"
            "2. What went well? (list specific effective actions)\n"
            "3. What went wrong or was suboptimal? (list specific issues)\n"
            "4. Should the agent retry with a different strategy? (yes/no)\n"
            "5. If retrying, what specific adjustments should be made?\n"
            "6. Your confidence in this assessment (0.0 to 1.0)\n\n"
            "Respond in JSON format.\n\n"
            "Trajectory:\n"
            f"{trajectory_text}"
        )

        response = self._client.messages.create(
            model=self._model,
            max_tokens=1024,
            messages=[{"role": "user", "content": reflection_prompt}],
        )

        # Extract text from response
        text = self._extract_text(response.get("content", []))
        result = self._parse_reflection(text)

        return result

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _format_trajectory(trajectory: List[Dict[str, Any]]) -> str:
        """Format a trajectory list into readable text for the evaluator."""
        lines: List[str] = []
        for step in trajectory:
            iteration = step.get("iteration", "?")
            step_type = step.get("type", "?")
            if step_type == "tool_call":
                tool = step.get("tool", "?")
                success = step.get("success", False)
                lines.append(
                    f"[Iter {iteration}] Tool: {tool} (success={success})"
                )
            elif step_type == "complete":
                text = step.get("text", "")
                lines.append(f"[Iter {iteration}] COMPLETE: {text[:200]}")
            elif step_type == "max_iterations":
                lines.append(f"[Iter {iteration}] MAX_ITERATIONS reached")
            elif step_type == "stalled":
                lines.append(f"[Iter {iteration}] STALLED (no tool calls)")
            else:
                lines.append(f"[Iter {iteration}] {step_type}")
        return "\n".join(lines)

    @staticmethod
    def _extract_text(blocks: List[Dict[str, Any]]) -> str:
        """Extract text from content blocks."""
        parts: List[str] = []
        for block in blocks:
            if isinstance(block, dict) and block.get("type") == "text":
                parts.append(block.get("text", ""))
        return "\n".join(parts)

    @staticmethod
    def _parse_reflection(text: str) -> ReflectionResult:
        """Parse reflection JSON from model response.

        Falls back to conservative defaults if parsing fails.
        """
        import json

        try:
            # Try to extract JSON from the text
            # Look for JSON in code blocks or raw
            if "```json" in text:
                start = text.index("```json") + 7
                end = text.index("```", start)
                json_str = text[start:end].strip()
            elif "```" in text:
                start = text.index("```") + 3
                end = text.index("```", start)
                json_str = text[start:end].strip()
            elif "{" in text and "}" in text:
                start = text.index("{")
                end = text.rindex("}") + 1
                json_str = text[start:end]
            else:
                json_str = text

            data = json.loads(json_str)
        except (json.JSONDecodeError, ValueError):
            # Fallback: treat as unsuccessful and suggest retry
            return ReflectionResult(
                success=False,
                strategy_adjustment="Re-evaluate the approach and try a different strategy.",
                lessons_learned=["Previous approach did not yield clear results."],
                should_retry=True,
                confidence=0.3,
            )

        return ReflectionResult(
            success=data.get("task_completed", data.get("success", False)),
            strategy_adjustment=data.get(
                "strategy_adjustment",
                data.get("adjustments", "Retry with improved approach."),
            ),
            lessons_learned=data.get("lessons_learned", data.get("lessons", [])),
            should_retry=data.get("should_retry", True),
            confidence=data.get("confidence", 0.5),
        )
