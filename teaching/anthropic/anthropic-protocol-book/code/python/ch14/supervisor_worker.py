"""
Chapter 14: Supervisor-Worker Pattern.

Implements a centralized coordinator (Supervisor) that pre-plans
task decomposition, dispatches subtasks to Worker agents, and
synthesizes results. Unlike Sub-Agent Orchestration, task allocation
happens upfront rather than dynamically during execution.

Pattern:  Supervisor plans -> Workers execute -> Supervisor synthesizes
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

from agent_loop import AgentLoop, AgentLoopResult, ToolResult


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------


@dataclass
class WorkerDefinition:
    """Definition of a worker agent."""

    name: str
    description: str
    system_prompt: str
    tools: List[Dict[str, Any]] = field(default_factory=list)
    model: str = "claude-sonnet-4-20250514"
    max_iterations: int = 10


@dataclass
class WorkItem:
    """A unit of work assigned to a worker."""

    worker_name: str
    description: str
    expected_output: str
    constraints: List[str] = field(default_factory=list)


@dataclass
class WorkResult:
    """Result from a single worker."""

    worker_name: str
    description: str
    success: bool
    output: str
    iterations: int
    tool_calls: int


@dataclass
class SupervisorResult:
    """Final result from a supervisor-worker run."""

    success: bool
    answer: str
    plan: List[WorkItem] = field(default_factory=list)
    work_results: List[WorkResult] = field(default_factory=list)
    total_iterations: int = 0
    total_tool_calls: int = 0
    total_tokens: int = 0


# ---------------------------------------------------------------------------
# Supervisor-Worker
# ---------------------------------------------------------------------------


class SupervisorWorker:
    """Supervisor-Worker pattern implementation.

    The Supervisor:
    1. Receives the user task.
    2. Plans all subtasks upfront (which workers, what to do).
    3. Dispatches to workers (potentially in parallel).
    4. Collects results and synthesizes a final answer.

    Usage::

        sw = SupervisorWorker(client, tool_executor)
        sw.register_worker(
            name="code-reviewer",
            description="Code quality and security reviewer",
            system_prompt="You are a senior code reviewer...",
        )
        result = sw.run("Review the project for bugs")
    """

    def __init__(
        self,
        client: Any,
        tool_executor: Callable[[str, Dict[str, Any]], ToolResult],
        *,
        model: str = "claude-sonnet-4-20250514",
        max_tokens_per_response: int = 4096,
    ) -> None:
        self._client = client
        self._tool_executor = tool_executor
        self._model = model
        self._max_tokens_per_response = max_tokens_per_response
        self._workers: Dict[str, WorkerDefinition] = {}

    # ------------------------------------------------------------------
    # Worker registration
    # ------------------------------------------------------------------

    def register_worker(
        self,
        name: str,
        description: str,
        system_prompt: str,
        *,
        tools: Optional[List[Dict[str, Any]]] = None,
        model: str = "claude-sonnet-4-20250514",
        max_iterations: int = 10,
    ) -> None:
        """Register a worker agent.

        Raises:
            ValueError: If worker name is already registered.
        """
        if name in self._workers:
            raise ValueError(f"Worker '{name}' is already registered")
        self._workers[name] = WorkerDefinition(
            name=name,
            description=description,
            system_prompt=system_prompt,
            tools=tools or [],
            model=model,
            max_iterations=max_iterations,
        )

    def unregister_worker(self, name: str) -> None:
        """Remove a worker (no-op if not found)."""
        self._workers.pop(name, None)

    def list_workers(self) -> List[Dict[str, str]]:
        """Return registered worker names and descriptions."""
        return [
            {"name": w.name, "description": w.description}
            for w in self._workers.values()
        ]

    # ------------------------------------------------------------------
    # Plan phase
    # ------------------------------------------------------------------

    def _plan(self, task: str) -> List[WorkItem]:
        """Supervisor plans the full work breakdown.

        Uses the model to analyze the task and available workers,
        then produce a structured plan.
        """
        if not self._workers:
            return [WorkItem(
                worker_name="__main__",
                description=task,
                expected_output="Complete the task",
            )]

        worker_descriptions = "\n".join(
            f"- {w.name}: {w.description}"
            for w in self._workers.values()
        )

        plan_prompt = (
            "You are a work supervisor planning task execution.\n\n"
            "Available Workers:\n"
            f"{worker_descriptions}\n\n"
            f"User Task: {task}\n\n"
            "Create a work plan by decomposing the task into work items. "
            "Each work item should be assigned to the most appropriate worker.\n\n"
            "Respond in JSON with a 'plan' array. Each item has:\n"
            "- 'worker_name': name of the assigned worker\n"
            "- 'description': clear, specific task description for the worker\n"
            "- 'expected_output': what the worker should produce\n"
            "- 'constraints': any limits or rules the worker must follow\n\n"
            "Distribute work evenly. If a task doesn't fit any worker, "
            "assign it to '__main__' for the supervisor to handle."
        )

        response = self._client.messages.create(
            model=self._model,
            max_tokens=1024,
            messages=[{"role": "user", "content": plan_prompt}],
        )

        text = self._extract_text(response.get("content", []))
        plan = self._parse_plan(text)

        # Validate worker names
        valid = [
            item for item in plan
            if item.worker_name in self._workers or item.worker_name == "__main__"
        ]
        return valid or [WorkItem(
            worker_name="__main__",
            description=task,
            expected_output="Complete the task",
        )]

    # ------------------------------------------------------------------
    # Execute phase
    # ------------------------------------------------------------------

    def _execute_work(self, item: WorkItem) -> WorkResult:
        """Execute a single work item by dispatching to the assigned worker."""
        if item.worker_name == "__main__":
            loop = AgentLoop(
                client=self._client,
                tool_executor=self._tool_executor,
                tools=[],
                system_prompt=(
                    "You are a supervisor handling a task directly. "
                    "Complete the task thoroughly."
                ),
                model=self._model,
                max_iterations=10,
                max_tokens_per_response=self._max_tokens_per_response,
            )
            result = loop.run(item.description)
            return WorkResult(
                worker_name="__main__",
                description=item.description,
                success=result.success,
                output=result.answer,
                iterations=result.iterations,
                tool_calls=result.tool_calls_made,
            )

        worker = self._workers.get(item.worker_name)
        if worker is None:
            # Fallback: run as __main__
            return self._execute_work(WorkItem(
                worker_name="__main__",
                description=item.description,
                expected_output=item.expected_output,
            ))

        # Build worker task with constraints
        task_parts = [item.description]
        if item.expected_output:
            task_parts.append(f"\nExpected Output: {item.expected_output}")
        if item.constraints:
            task_parts.append(f"\nConstraints: {'; '.join(item.constraints)}")
        worker_task = "\n".join(task_parts)

        loop = AgentLoop(
            client=self._client,
            tool_executor=self._tool_executor,
            tools=worker.tools,
            system_prompt=worker.system_prompt,
            model=worker.model,
            max_iterations=worker.max_iterations,
            max_tokens_per_response=self._max_tokens_per_response,
        )
        result = loop.run(worker_task)
        return WorkResult(
            worker_name=item.worker_name,
            description=item.description,
            success=result.success,
            output=result.answer,
            iterations=result.iterations,
            tool_calls=result.tool_calls_made,
        )

    # ------------------------------------------------------------------
    # Synthesize phase
    # ------------------------------------------------------------------

    def _synthesize(self, task: str, plan: List[WorkItem],
                    results: List[WorkResult]) -> str:
        """Synthesize worker results into a final answer."""
        results_text = ""
        for i, (item, result) in enumerate(zip(plan, results)):
            results_text += (
                f"\n### Work Item {i + 1} [{result.worker_name}]\n"
                f"Task: {item.description}\n"
                f"Expected: {item.expected_output}\n"
                f"Success: {result.success}\n"
                f"Output:\n{result.output}\n"
            )

        syn_prompt = (
            f"Original Task: {task}\n\n"
            f"Plan and Results:\n{results_text}\n\n"
            "Synthesize these results into a single comprehensive answer "
            "that addresses the original task. If any work item failed, "
            "note the limitation in your response."
        )

        response = self._client.messages.create(
            model=self._model,
            max_tokens=self._max_tokens_per_response,
            messages=[{"role": "user", "content": syn_prompt}],
        )

        return self._extract_text(response.get("content", []))

    # ------------------------------------------------------------------
    # Full run
    # ------------------------------------------------------------------

    def run(self, task: str) -> SupervisorResult:
        """Execute the full Supervisor-Worker workflow.

        1. Plan: Supervisor decomposes the task.
        2. Execute: Workers process their assignments.
        3. Synthesize: Supervisor combines results.
        """
        # Phase 1: Plan
        plan = self._plan(task)

        # Phase 2: Execute (sequential; production should parallelize)
        results: List[WorkResult] = []
        total_iterations = 0
        total_tool_calls = 0
        total_tokens = 0

        for item in plan:
            result = self._execute_work(item)
            results.append(result)
            total_iterations += result.iterations
            total_tool_calls += result.tool_calls

        # Phase 3: Synthesize
        final_answer = self._synthesize(task, plan, results)

        return SupervisorResult(
            success=all(r.success for r in results),
            answer=final_answer,
            plan=plan,
            work_results=results,
            total_iterations=total_iterations,
            total_tool_calls=total_tool_calls,
            total_tokens=total_tokens,
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _extract_text(blocks: List[Dict[str, Any]]) -> str:
        parts: List[str] = []
        for block in blocks:
            if isinstance(block, dict) and block.get("type") == "text":
                parts.append(block.get("text", ""))
        return "\n".join(parts)

    @staticmethod
    def _parse_plan(text: str) -> List[WorkItem]:
        """Parse plan JSON from model response."""
        import json

        try:
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
            items = data.get("plan", [data])
        except (json.JSONDecodeError, ValueError):
            return []

        result = []
        for item in items:
            if isinstance(item, dict):
                result.append(WorkItem(
                    worker_name=item.get("worker_name", "__main__"),
                    description=item.get("description", ""),
                    expected_output=item.get("expected_output", ""),
                    constraints=item.get("constraints", []),
                ))
        return result
