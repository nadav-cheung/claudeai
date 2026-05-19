"""
Chapter 14: Sub-Agent Orchestrator.

Implements dynamic sub-agent delegation where the main agent decides
at runtime which specialized sub-agent to call for which subtask.

Pattern:  Main Agent -> detect subtask -> dispatch to sub-agent
         -> collect result -> synthesize -> continue or complete
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

from agent_loop import AgentLoop, AgentLoopResult, ToolResult


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------


@dataclass
class SubAgentDefinition:
    """Defines a sub-agent that the orchestrator can dispatch to."""

    name: str
    description: str
    system_prompt: str
    tools: List[Dict[str, Any]] = field(default_factory=list)
    model: str = "claude-sonnet-4-20250514"
    max_iterations: int = 10


@dataclass
class SubTask:
    """A task decomposed by the orchestrator for dispatch."""

    agent_name: str
    task_description: str
    context: str = ""
    priority: int = 0  # Lower = higher priority


@dataclass
class SubTaskResult:
    """Result of executing a single subtask."""

    agent_name: str
    task_description: str
    success: bool
    result: AgentLoopResult


@dataclass
class OrchestratorResult:
    """Final synthesized result from an orchestrator run."""

    success: bool
    answer: str
    total_iterations: int
    total_tool_calls: int
    total_tokens: int
    subtask_results: List[SubTaskResult] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Sub-Agent Orchestrator
# ---------------------------------------------------------------------------


class SubAgentOrchestrator:
    """Orchestrates a main agent that dynamically delegates to sub-agents.

    The orchestrator flow:
    1. Main agent receives the user task.
    2. Main agent determines if subtask delegation is needed.
    3. If yes, decompose the task into subtasks with assigned sub-agents.
    4. Dispatch each subtask to the designated sub-agent.
    5. Collect and synthesize results.
    6. Continue the main loop or return final answer.

    Usage::

        orchestrator = SubAgentOrchestrator(client, tool_executor)
        orchestrator.register_sub_agent(
            name="code-reviewer",
            description="Reviews code for bugs and style issues",
            system_prompt="You are a senior code reviewer...",
        )
        result = orchestrator.run("Review the auth module and fix issues")
    """

    def __init__(
        self,
        client: Any,
        tool_executor: Callable[[str, Dict[str, Any]], ToolResult],
        *,
        tools: Optional[List[Dict[str, Any]]] = None,
        system_prompt: str = "",
        model: str = "claude-sonnet-4-20250514",
        max_iterations: int = 15,
        max_tokens_per_response: int = 4096,
    ) -> None:
        self._client = client
        self._tool_executor = tool_executor
        self._tools = tools or []
        self._system_prompt = system_prompt
        self._model = model
        self._max_iterations = max_iterations
        self._max_tokens_per_response = max_tokens_per_response
        self._sub_agents: Dict[str, SubAgentDefinition] = {}

    # ------------------------------------------------------------------
    # Sub-agent registration
    # ------------------------------------------------------------------

    def register_sub_agent(
        self,
        name: str,
        description: str,
        system_prompt: str,
        *,
        tools: Optional[List[Dict[str, Any]]] = None,
        model: str = "claude-sonnet-4-20250514",
        max_iterations: int = 10,
    ) -> None:
        """Register a sub-agent with the orchestrator.

        Args:
            name: Unique sub-agent identifier.
            description: What this agent does (used by the main agent to decide delegation).
            system_prompt: The sub-agent's system prompt.
            tools: Tools available to this sub-agent.
            model: Model for this sub-agent.
            max_iterations: Max iterations for this sub-agent's loop.

        Raises:
            ValueError: If sub-agent name is already registered.
        """
        if name in self._sub_agents:
            raise ValueError(f"Sub-agent '{name}' is already registered")
        self._sub_agents[name] = SubAgentDefinition(
            name=name,
            description=description,
            system_prompt=system_prompt,
            tools=tools or [],
            model=model,
            max_iterations=max_iterations,
        )

    def unregister_sub_agent(self, name: str) -> None:
        """Remove a sub-agent (no-op if not found)."""
        self._sub_agents.pop(name, None)

    def list_sub_agents(self) -> List[Dict[str, str]]:
        """Return registered sub-agent names and descriptions."""
        return [
            {"name": sa.name, "description": sa.description}
            for sa in self._sub_agents.values()
        ]

    # ------------------------------------------------------------------
    # Task decomposition
    # ------------------------------------------------------------------

    def decompose(self, task: str) -> List[SubTask]:
        """Use the main model to decompose a task into subtasks.

        Returns a list of ``SubTask`` objects, each assigned to a
        specific sub-agent. If no sub-agents are registered or the
        task is simple, returns a single subtask for the main agent.
        """
        if not self._sub_agents:
            return [SubTask(agent_name="main", task_description=task)]

        agent_descriptions = "\n".join(
            f"- {sa.name}: {sa.description}"
            for sa in self._sub_agents.values()
        )

        decompose_prompt = (
            "You are a task decomposition specialist. Given a complex task "
            "and a set of available specialized agents, decompose the task "
            "into subtasks that can be assigned to specific agents.\n\n"
            "Available Agents:\n"
            f"{agent_descriptions}\n\n"
            "Main Agent: General-purpose, handles coordination and tasks "
            "not suited for other agents.\n\n"
            f"Task: {task}\n\n"
            "Respond in JSON format with a 'subtasks' array. Each subtask "
            "has: 'agent_name' (must match an available agent or 'main'), "
            "'task_description' (clear, specific), 'priority' (integer, "
            "lower = higher priority).\n\n"
            "Only decompose if the task truly benefits from specialization. "
            "For simple tasks, return a single subtask for 'main'."
        )

        response = self._client.messages.create(
            model=self._model,
            max_tokens=1024,
            messages=[{"role": "user", "content": decompose_prompt}],
        )

        text = self._extract_text(response.get("content", []))
        subtasks = self._parse_subtasks(text)

        # Validate agent names
        valid = []
        for st in subtasks:
            if st.agent_name in self._sub_agents or st.agent_name == "main":
                valid.append(st)
        return valid or [SubTask(agent_name="main", task_description=task)]

    # ------------------------------------------------------------------
    # Dispatch
    # ------------------------------------------------------------------

    def dispatch(self, subtask: SubTask) -> SubTaskResult:
        """Dispatch a subtask to the appropriate sub-agent and run it.

        If the agent_name is 'main', runs the task inline via the
        main agent loop.
        """
        if subtask.agent_name == "main":
            loop = AgentLoop(
                client=self._client,
                tool_executor=self._tool_executor,
                tools=self._tools,
                system_prompt=self._system_prompt,
                model=self._model,
                max_iterations=self._max_iterations,
                max_tokens_per_response=self._max_tokens_per_response,
            )
            result = loop.run(subtask.task_description)
            return SubTaskResult(
                agent_name="main",
                task_description=subtask.task_description,
                success=result.success,
                result=result,
            )

        sa = self._sub_agents.get(subtask.agent_name)
        if sa is None:
            # Unknown sub-agent -- run as main
            return self.dispatch(SubTask(
                agent_name="main",
                task_description=subtask.task_description,
            ))

        loop = AgentLoop(
            client=self._client,
            tool_executor=self._tool_executor,
            tools=sa.tools,
            system_prompt=sa.system_prompt,
            model=sa.model,
            max_iterations=sa.max_iterations,
            max_tokens_per_response=self._max_tokens_per_response,
        )
        result = loop.run(subtask.task_description)
        return SubTaskResult(
            agent_name=subtask.agent_name,
            task_description=subtask.task_description,
            success=result.success,
            result=result,
        )

    # ------------------------------------------------------------------
    # Synthesize
    # ------------------------------------------------------------------

    def synthesize(self, task: str, results: List[SubTaskResult]) -> AgentLoopResult:
        """Synthesize multiple sub-agent results into a final answer.

        Uses the main model to read all subtask outputs and produce a
        coherent, consolidated response.
        """
        results_text = ""
        for i, r in enumerate(results):
            results_text += (
                f"\n### Subtask {i + 1} [{r.agent_name}]\n"
                f"Task: {r.task_description}\n"
                f"Success: {r.success}\n"
                f"Result:\n{r.result.answer}\n"
            )

        synthesize_prompt = (
            f"Original Task: {task}\n\n"
            f"Subtasks and Results:\n{results_text}\n\n"
            "Synthesize these results into a single comprehensive answer. "
            "Address the original task fully. If any subtask failed, "
            "note the gap and provide your best answer based on available "
            "information."
        )

        response = self._client.messages.create(
            model=self._model,
            max_tokens=self._max_tokens_per_response,
            messages=[{"role": "user", "content": synthesize_prompt}],
        )

        text = self._extract_text(response.get("content", []))
        return AgentLoopResult(
            success=all(r.success for r in results),
            answer=text,
            iterations=1,
            tool_calls_made=0,
            total_tokens=0,
        )

    # ------------------------------------------------------------------
    # Full orchestration run
    # ------------------------------------------------------------------

    def run(self, task: str) -> OrchestratorResult:
        """Execute full sub-agent orchestration for a task.

        Decompose -> Dispatch (parallel or sequential) -> Synthesize.
        """
        # Step 1: Decompose
        subtasks = self.decompose(task)

        # Step 2: Dispatch (sequential in this implementation;
        # could be parallelized with asyncio for production)
        subtask_results: List[SubTaskResult] = []
        total_iterations = 0
        total_tool_calls = 0
        total_tokens = 0

        for subtask in subtasks:
            result = self.dispatch(subtask)
            subtask_results.append(result)
            total_iterations += result.result.iterations
            total_tool_calls += result.result.tool_calls_made
            total_tokens += result.result.total_tokens

        # Step 3: Synthesize
        final = self.synthesize(task, subtask_results)

        return OrchestratorResult(
            success=final.success,
            answer=final.answer,
            total_iterations=total_iterations,
            total_tool_calls=total_tool_calls,
            total_tokens=total_tokens,
            subtask_results=subtask_results,
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
    def _parse_subtasks(text: str) -> List[SubTask]:
        """Parse subtask JSON from model response."""
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
            items = data.get("subtasks", [data])
        except (json.JSONDecodeError, ValueError):
            return []

        subtasks = []
        for item in items:
            if isinstance(item, dict):
                subtasks.append(SubTask(
                    agent_name=item.get("agent_name", "main"),
                    task_description=item.get("task_description", ""),
                    priority=item.get("priority", 0),
                ))
        return subtasks
