"""
Tests for Chapter 14: Agent Loop, Reflexion Agent, Sub-Agent Orchestrator,
and Supervisor-Worker patterns.

Uses a mock Anthropic client that simulates model responses. No real
API calls are made.
"""

from __future__ import annotations

from typing import Any, Dict, List
from unittest.mock import MagicMock, patch

import pytest

from agent_loop import AgentLoop, AgentLoopResult, ToolResult
from reflexion_agent import (
    ReflexionAgent,
    ReflexionAgentResult,
    ReflectionResult,
)
from subagent_orchestrator import (
    SubAgentOrchestrator,
    OrchestratorResult,
    SubTaskResult,
    SubTask,
)
from supervisor_worker import (
    SupervisorWorker,
    SupervisorResult,
    WorkItem,
)


# ============================================================================
# Mock Client
# ============================================================================


class MockMessages:
    """Mock for ``client.messages``."""

    def __init__(self, responses: List[Dict[str, Any]]):
        self._responses = responses
        self._call_count = 0
        self.create = self._create

    def _create(self, **kwargs: Any) -> Dict[str, Any]:
        if self._call_count < len(self._responses):
            resp = self._responses[self._call_count]
        else:
            # Default end_turn fallback
            resp = {
                "stop_reason": "end_turn",
                "content": [{"type": "text", "text": "Default response"}],
                "usage": {"input_tokens": 10, "output_tokens": 10},
            }
        self._call_count += 1
        return resp

    @property
    def call_count(self) -> int:
        return self._call_count


class MockClient:
    """Mock Anthropic client with pre-programmed responses."""

    def __init__(self, responses: List[Dict[str, Any]]):
        self.messages = MockMessages(responses)


# ============================================================================
# Tool Executor
# ============================================================================


def make_tool_executor(tools_map: Dict[str, Any]):
    """Create a tool executor from a dict of name -> function."""

    def executor(name: str, input_data: Dict[str, Any]) -> ToolResult:
        handler = tools_map.get(name)
        if handler is None:
            return ToolResult(
                tool_use_id="unknown",
                success=False,
                content=f"Unknown tool: {name}",
                error=f"Tool '{name}' not found",
            )
        try:
            result = handler(**input_data)
            return ToolResult(
                tool_use_id="tool_001",
                success=True,
                content=str(result),
            )
        except Exception as e:
            return ToolResult(
                tool_use_id="tool_001",
                success=False,
                content=str(e),
                error=str(e),
            )

    return executor


# ============================================================================
# AgentLoop Tests
# ============================================================================


class TestAgentLoop:
    """Tests for the core AgentLoop (ReAct pattern)."""

    def test_simple_end_turn_no_tools(self) -> None:
        """Task completes in one turn without tools."""
        client = MockClient([
            {
                "stop_reason": "end_turn",
                "content": [{"type": "text", "text": "The answer is 42."}],
                "usage": {"input_tokens": 50, "output_tokens": 10},
            },
        ])
        executor = make_tool_executor({})
        loop = AgentLoop(client, executor)
        result = loop.run("What is the answer?")

        assert result.success is True
        assert "42" in result.answer
        assert result.iterations == 1
        assert result.tool_calls_made == 0
        assert len(result.trajectory) == 1
        assert result.trajectory[0]["type"] == "complete"

    def test_tool_use_then_end_turn(self) -> None:
        """Agent calls a tool, receives result, then completes."""
        client = MockClient([
            {
                "stop_reason": "tool_use",
                "content": [
                    {
                        "type": "tool_use",
                        "id": "toolu_001",
                        "name": "get_weather",
                        "input": {"location": "Beijing"},
                    },
                ],
                "usage": {"input_tokens": 50, "output_tokens": 20},
            },
            {
                "stop_reason": "end_turn",
                "content": [{"type": "text", "text": "Beijing is sunny, 24C."}],
                "usage": {"input_tokens": 80, "output_tokens": 10},
            },
        ])
        tools_map = {
            "get_weather": lambda location: f"Weather in {location}: sunny, 24C",
        }
        executor = make_tool_executor(tools_map)
        loop = AgentLoop(client, executor)
        result = loop.run("What is the weather in Beijing?")

        assert result.success is True
        assert "sunny" in result.answer
        assert result.iterations == 2
        assert result.tool_calls_made == 1
        assert result.trajectory[0]["type"] == "tool_call"
        assert result.trajectory[1]["type"] == "complete"

    def test_max_iterations_limit(self) -> None:
        """Agent stops when max_iterations is reached."""
        # Create a loop that always requests a tool
        responses = []
        for _ in range(5):
            responses.append({
                "stop_reason": "tool_use",
                "content": [
                    {
                        "type": "tool_use",
                        "id": f"toolu_{_}",
                        "name": "ping",
                        "input": {},
                    },
                ],
                "usage": {"input_tokens": 50, "output_tokens": 10},
            })

        client = MockClient(responses)
        tools_map = {"ping": lambda: "pong"}
        executor = make_tool_executor(tools_map)
        loop = AgentLoop(client, executor, max_iterations=3)
        result = loop.run("Ping forever")

        assert result.iterations == 3
        assert "maximum iterations" in result.answer.lower()
        assert result.tool_calls_made == 3

    def test_multiple_tool_calls_in_one_turn(self) -> None:
        """Model requests multiple tools in a single response."""
        client = MockClient([
            {
                "stop_reason": "tool_use",
                "content": [
                    {
                        "type": "tool_use",
                        "id": "toolu_001",
                        "name": "get_weather",
                        "input": {"location": "Tokyo"},
                    },
                    {
                        "type": "tool_use",
                        "id": "toolu_002",
                        "name": "get_time",
                        "input": {"timezone": "Asia/Tokyo"},
                    },
                ],
                "usage": {"input_tokens": 60, "output_tokens": 30},
            },
            {
                "stop_reason": "end_turn",
                "content": [{"type": "text", "text": "Tokyo: sunny, 14:30 JST."}],
                "usage": {"input_tokens": 100, "output_tokens": 10},
            },
        ])
        tools_map = {
            "get_weather": lambda location: f"Weather in {location}: sunny",
            "get_time": lambda timezone: f"Time in {timezone}: 14:30",
        }
        executor = make_tool_executor(tools_map)
        loop = AgentLoop(client, executor)
        result = loop.run("Tokyo weather and time?")

        assert result.success is True
        assert result.tool_calls_made == 2
        assert result.iterations == 2

    def test_tool_execution_error(self) -> None:
        """Agent handles a tool that throws an error gracefully."""
        client = MockClient([
            {
                "stop_reason": "tool_use",
                "content": [
                    {
                        "type": "tool_use",
                        "id": "toolu_001",
                        "name": "failing_tool",
                        "input": {},
                    },
                ],
                "usage": {"input_tokens": 50, "output_tokens": 10},
            },
            {
                "stop_reason": "end_turn",
                "content": [
                    {"type": "text", "text": "The tool failed, but I can still help."}
                ],
                "usage": {"input_tokens": 80, "output_tokens": 10},
            },
        ])
        tools_map = {"failing_tool": lambda: (_ for _ in ()).throw(RuntimeError("Boom"))}
        executor = make_tool_executor(tools_map)
        loop = AgentLoop(client, executor)
        result = loop.run("Try the failing tool")

        assert result.tool_calls_made == 1
        assert not result.trajectory[0]["success"]

    def test_stalled_no_tool_calls(self) -> None:
        """Agent returns tool_use stop reason but no valid tool blocks."""
        client = MockClient([
            {
                "stop_reason": "tool_use",
                "content": [{"type": "text", "text": "I think I should use a tool..."}],
                "usage": {"input_tokens": 30, "output_tokens": 10},
            },
        ])
        executor = make_tool_executor({})
        loop = AgentLoop(client, executor)
        result = loop.run("Do something")

        assert result.iterations == 1
        assert result.trajectory[0]["type"] == "stalled"

    def test_trajectory_records_complete_history(self) -> None:
        """Trajectory captures all steps accurately."""
        client = MockClient([
            {
                "stop_reason": "tool_use",
                "content": [
                    {
                        "type": "tool_use",
                        "id": "t1",
                        "name": "step1",
                        "input": {"a": 1},
                    },
                ],
                "usage": {"input_tokens": 30, "output_tokens": 10},
            },
            {
                "stop_reason": "end_turn",
                "content": [{"type": "text", "text": "Done."}],
                "usage": {"input_tokens": 50, "output_tokens": 5},
            },
        ])
        tools_map = {"step1": lambda a: f"Result: {a}"}
        executor = make_tool_executor(tools_map)
        loop = AgentLoop(client, executor)
        result = loop.run("Task")

        assert len(result.trajectory) == 2
        assert result.trajectory[0]["tool"] == "step1"
        assert result.trajectory[0]["input"] == {"a": 1}
        assert result.trajectory[1]["type"] == "complete"


# ============================================================================
# ReflexionAgent Tests
# ============================================================================


class TestReflexionAgent:
    """Tests for ReflexionAgent (self-evaluating agent)."""

    def test_success_on_first_attempt(self) -> None:
        """Reflexion agent completes successfully on first try."""
        client = MockClient([
            # First attempt: agent loop succeeds
            {
                "stop_reason": "end_turn",
                "content": [{"type": "text", "text": "Task completed successfully."}],
                "usage": {"input_tokens": 50, "output_tokens": 10},
            },
            # Reflection: evaluator says success
            {
                "stop_reason": "end_turn",
                "content": [
                    {
                        "type": "text",
                        "text": (
                            '{"task_completed": true, '
                            '"strategy_adjustment": "", '
                            '"lessons_learned": ["Good approach"], '
                            '"should_retry": false, '
                            '"confidence": 0.95}'
                        ),
                    },
                ],
                "usage": {"input_tokens": 50, "output_tokens": 20},
            },
        ])
        executor = make_tool_executor({})
        agent = ReflexionAgent(client, executor, max_reflection_cycles=3)
        result = agent.run("Simple task")

        assert result.success is True
        assert result.reflection_cycles == 1
        assert len(result.reflections) == 1
        assert result.reflections[0].success is True

    def test_retry_after_failure(self) -> None:
        """Reflexion agent retries after first attempt fails."""
        client = MockClient([
            # First attempt: max iterations (failed)
            {
                "stop_reason": "tool_use",
                "content": [
                    {
                        "type": "tool_use",
                        "id": "t1",
                        "name": "bad_tool",
                        "input": {},
                    },
                ],
                "usage": {"input_tokens": 30, "output_tokens": 10},
            },
            # First reflection: not successful, try again
            {
                "stop_reason": "end_turn",
                "content": [
                    {
                        "type": "text",
                        "text": (
                            '{"task_completed": false, '
                            '"strategy_adjustment": "Try a different approach", '
                            '"lessons_learned": ["Bad tool did not help"], '
                            '"should_retry": true, '
                            '"confidence": 0.4}'
                        ),
                    },
                ],
                "usage": {"input_tokens": 50, "output_tokens": 20},
            },
            # Second attempt: success
            {
                "stop_reason": "end_turn",
                "content": [{"type": "text", "text": "Task done with new approach."}],
                "usage": {"input_tokens": 50, "output_tokens": 10},
            },
            # Second reflection: success
            {
                "stop_reason": "end_turn",
                "content": [
                    {
                        "type": "text",
                        "text": (
                            '{"task_completed": true, '
                            '"strategy_adjustment": "", '
                            '"lessons_learned": ["New approach worked"], '
                            '"should_retry": false, '
                            '"confidence": 0.9}'
                        ),
                    },
                ],
                "usage": {"input_tokens": 50, "output_tokens": 20},
            },
        ])
        executor = make_tool_executor({"bad_tool": lambda: "some data"})
        agent = ReflexionAgent(
            client, executor,
            max_iterations_per_attempt=1,
            max_reflection_cycles=3,
        )
        result = agent.run("Complex task")

        assert result.success is True
        assert result.reflection_cycles == 2
        assert len(result.reflections) == 2
        assert result.reflections[0].success is False
        assert result.reflections[1].success is True

    def test_reflection_parse_fallback(self) -> None:
        """When reflection JSON is malformed, uses safe defaults."""
        client = MockClient([
            # First attempt
            {
                "stop_reason": "end_turn",
                "content": [{"type": "text", "text": "Done."}],
                "usage": {"input_tokens": 30, "output_tokens": 10},
            },
            # Malformed reflection -> triggers retry (fallback should_retry=True)
            {
                "stop_reason": "end_turn",
                "content": [
                    {"type": "text", "text": "This is not valid JSON at all."}
                ],
                "usage": {"input_tokens": 30, "output_tokens": 10},
            },
            # Second attempt (retry)
            {
                "stop_reason": "end_turn",
                "content": [{"type": "text", "text": "Done again."}],
                "usage": {"input_tokens": 30, "output_tokens": 10},
            },
            # Second reflection (also malformed, or cycle limit hit)
            {
                "stop_reason": "end_turn",
                "content": [
                    {"type": "text", "text": "Not JSON either."}
                ],
                "usage": {"input_tokens": 30, "output_tokens": 10},
            },
        ])
        executor = make_tool_executor({})
        agent = ReflexionAgent(client, executor, max_reflection_cycles=2)
        result = agent.run("Task")

        # Fallback defaults: not successful, should_retry triggers a second cycle
        assert len(result.reflections) == 2
        assert result.reflections[0].success is False
        assert result.reflections[0].should_retry is True
        assert result.reflections[1].success is False  # Also fallback

    def test_max_reflection_cycles(self) -> None:
        """Stops after reaching max reflection cycles."""
        # Create enough responses for 3 reflection cycles
        responses = []
        for _ in range(3):
            responses.append({
                "stop_reason": "end_turn",
                "content": [{"type": "text", "text": "Done."}],
                "usage": {"input_tokens": 30, "output_tokens": 10},
            })
            responses.append({
                "stop_reason": "end_turn",
                "content": [
                    {
                        "type": "text",
                        "text": (
                            '{"task_completed": false, '
                            '"strategy_adjustment": "Keep trying", '
                            '"lessons_learned": ["Not yet"], '
                            '"should_retry": true, '
                            '"confidence": 0.3}'
                        ),
                    },
                ],
                "usage": {"input_tokens": 30, "output_tokens": 20},
            })

        client = MockClient(responses)
        executor = make_tool_executor({})
        agent = ReflexionAgent(client, executor, max_reflection_cycles=2)
        result = agent.run("Task")

        assert result.reflection_cycles == 2
        assert "Max reflection cycles" in result.answer


# ============================================================================
# SubAgentOrchestrator Tests
# ============================================================================


class TestSubAgentOrchestrator:
    """Tests for sub-agent orchestration."""

    def test_register_and_list_sub_agents(self) -> None:
        """Sub-agents can be registered and listed."""
        client = MockClient([])
        executor = make_tool_executor({})
        orch = SubAgentOrchestrator(client, executor)
        orch.register_sub_agent(
            name="reviewer",
            description="Code reviewer",
            system_prompt="You review code",
        )
        orch.register_sub_agent(
            name="tester",
            description="Test writer",
            system_prompt="You write tests",
        )

        agents = orch.list_sub_agents()
        assert len(agents) == 2
        assert agents[0]["name"] == "reviewer"
        assert agents[1]["name"] == "tester"

    def test_register_duplicate_raises(self) -> None:
        """Duplicate sub-agent registration raises ValueError."""
        client = MockClient([])
        executor = make_tool_executor({})
        orch = SubAgentOrchestrator(client, executor)
        orch.register_sub_agent("r", "desc", "prompt")
        with pytest.raises(ValueError, match="already registered"):
            orch.register_sub_agent("r", "desc2", "prompt2")

    def test_unregister(self) -> None:
        """Sub-agent can be unregistered."""
        client = MockClient([])
        executor = make_tool_executor({})
        orch = SubAgentOrchestrator(client, executor)
        orch.register_sub_agent("r", "desc", "prompt")
        assert len(orch.list_sub_agents()) == 1
        orch.unregister_sub_agent("r")
        assert len(orch.list_sub_agents()) == 0

    def test_decompose_simple_task(self) -> None:
        """Simple task is not decomposed into sub-agent tasks."""
        client = MockClient([
            {
                "stop_reason": "end_turn",
                "content": [
                    {
                        "type": "text",
                        "text": '{"subtasks": [{"agent_name": "main", "task_description": "Do it", "priority": 0}]}',
                    },
                ],
                "usage": {"input_tokens": 30, "output_tokens": 10},
            },
        ])
        executor = make_tool_executor({})
        orch = SubAgentOrchestrator(client, executor)
        subtasks = orch.decompose("Simple task")

        assert len(subtasks) == 1
        assert subtasks[0].agent_name == "main"

    def test_decompose_with_sub_agents(self) -> None:
        """Task is decomposed and assigned to registered sub-agents."""
        client = MockClient([
            {
                "stop_reason": "end_turn",
                "content": [
                    {
                        "type": "text",
                        "text": (
                            '{"subtasks": ['
                            '{"agent_name": "reviewer", "task_description": "Review code", "priority": 0},'
                            '{"agent_name": "tester", "task_description": "Write tests", "priority": 1}'
                            ']}'
                        ),
                    },
                ],
                "usage": {"input_tokens": 30, "output_tokens": 10},
            },
        ])
        executor = make_tool_executor({})
        orch = SubAgentOrchestrator(client, executor)
        orch.register_sub_agent("reviewer", "Reviews code", "Review prompt")
        orch.register_sub_agent("tester", "Writes tests", "Test prompt")

        subtasks = orch.decompose("Review and test the code")

        assert len(subtasks) == 2
        assert subtasks[0].agent_name == "reviewer"
        assert subtasks[1].agent_name == "tester"

    def test_dispatch_to_sub_agent(self) -> None:
        """Subtask is dispatched and executed by the correct sub-agent."""
        client = MockClient([
            {
                "stop_reason": "end_turn",
                "content": [{"type": "text", "text": "Code reviewed: no issues found."}],
                "usage": {"input_tokens": 30, "output_tokens": 10},
            },
        ])
        executor = make_tool_executor({})
        orch = SubAgentOrchestrator(client, executor)
        orch.register_sub_agent(
            name="reviewer",
            description="Reviews code",
            system_prompt="You review code thoroughly",
        )

        subtask = SubTask(agent_name="reviewer", task_description="Review auth.py")
        result = orch.dispatch(subtask)

        assert result.success is True
        assert result.agent_name == "reviewer"
        assert "reviewed" in result.result.answer.lower()

    def test_dispatch_unknown_agent_falls_back_to_main(self) -> None:
        """Dispatching to an unknown agent falls back to main agent."""
        client = MockClient([
            {
                "stop_reason": "end_turn",
                "content": [{"type": "text", "text": "Done by main."}],
                "usage": {"input_tokens": 30, "output_tokens": 10},
            },
        ])
        executor = make_tool_executor({})
        orch = SubAgentOrchestrator(client, executor)

        subtask = SubTask(agent_name="nonexistent", task_description="Do something")
        result = orch.dispatch(subtask)

        assert result.agent_name == "main"
        assert "Done by main" in result.result.answer

    def test_synthesize_results(self) -> None:
        """Orchestrator synthesizes multiple sub-agent results."""
        client = MockClient([
            {
                "stop_reason": "end_turn",
                "content": [
                    {
                        "type": "text",
                        "text": "Synthesized: Code is clean and tests pass.",
                    },
                ],
                "usage": {"input_tokens": 30, "output_tokens": 10},
            },
        ])
        executor = make_tool_executor({})
        orch = SubAgentOrchestrator(client, executor)

        results = [
            SubTaskResult(
                agent_name="reviewer",
                task_description="Review",
                success=True,
                result=AgentLoopResult(
                    success=True, answer="Code is clean",
                    iterations=1, tool_calls_made=0, total_tokens=20,
                ),
            ),
            SubTaskResult(
                agent_name="tester",
                task_description="Test",
                success=True,
                result=AgentLoopResult(
                    success=True, answer="All tests pass",
                    iterations=1, tool_calls_made=0, total_tokens=20,
                ),
            ),
        ]

        final = orch.synthesize("Review and test", results)
        assert final.success is True
        assert "clean" in final.answer.lower()


# ============================================================================
# SupervisorWorker Tests
# ============================================================================


class TestSupervisorWorker:
    """Tests for the Supervisor-Worker pattern."""

    def test_simple_task_with_no_workers(self) -> None:
        """Simple task runs directly through supervisor."""
        client = MockClient([
            # Plan phase
            {
                "stop_reason": "end_turn",
                "content": [
                    {
                        "type": "text",
                        "text": '{"plan": [{"worker_name": "__main__", "description": "Answer the question", "expected_output": "An answer", "constraints": []}]}',
                    },
                ],
                "usage": {"input_tokens": 30, "output_tokens": 10},
            },
            # Execute phase
            {
                "stop_reason": "end_turn",
                "content": [{"type": "text", "text": "The answer is 42."}],
                "usage": {"input_tokens": 30, "output_tokens": 10},
            },
            # Synthesize phase
            {
                "stop_reason": "end_turn",
                "content": [{"type": "text", "text": "Final: The answer is 42."}],
                "usage": {"input_tokens": 30, "output_tokens": 10},
            },
        ])
        executor = make_tool_executor({})
        sw = SupervisorWorker(client, executor)
        result = sw.run("What is the answer?")

        assert result.success is True
        assert "42" in result.answer
        assert len(result.plan) == 1
        assert result.plan[0].worker_name == "__main__"

    def test_register_worker(self) -> None:
        """Workers can be registered and listed."""
        client = MockClient([])
        executor = make_tool_executor({})
        sw = SupervisorWorker(client, executor)
        sw.register_worker(
            name="analyzer",
            description="Data analyzer",
            system_prompt="Analyze data",
        )

        workers = sw.list_workers()
        assert len(workers) == 1
        assert workers[0]["name"] == "analyzer"

    def test_duplicate_worker_raises(self) -> None:
        """Duplicate worker registration raises ValueError."""
        client = MockClient([])
        executor = make_tool_executor({})
        sw = SupervisorWorker(client, executor)
        sw.register_worker("w", "desc", "prompt")
        with pytest.raises(ValueError, match="already registered"):
            sw.register_worker("w", "desc2", "prompt2")

    def test_plan_delegates_to_workers(self) -> None:
        """Supervisor plans work across worker agents."""
        client = MockClient([
            {
                "stop_reason": "end_turn",
                "content": [
                    {
                        "type": "text",
                        "text": (
                            '{"plan": ['
                            '{"worker_name": "analyzer", "description": "Analyze data", "expected_output": "Analysis report", "constraints": []}'
                            ']}'
                        ),
                    },
                ],
                "usage": {"input_tokens": 30, "output_tokens": 10},
            },
        ])
        executor = make_tool_executor({})
        sw = SupervisorWorker(client, executor)
        sw.register_worker("analyzer", "Analyzes data", "Analyze prompt")

        plan = sw._plan("Analyze the dataset")
        assert len(plan) == 1
        assert plan[0].worker_name == "analyzer"

    def test_worker_execution_with_tools(self) -> None:
        """Worker executes task using its assigned tools."""
        client = MockClient([
            # Plan
            {
                "stop_reason": "end_turn",
                "content": [
                    {
                        "type": "text",
                        "text": '{"plan": [{"worker_name": "searcher", "description": "Search for info", "expected_output": "Search results", "constraints": []}]}',
                    },
                ],
                "usage": {"input_tokens": 30, "output_tokens": 10},
            },
            # Worker execution: tool call then complete
            {
                "stop_reason": "tool_use",
                "content": [
                    {
                        "type": "tool_use",
                        "id": "t1",
                        "name": "search",
                        "input": {"query": "latest docs"},
                    },
                ],
                "usage": {"input_tokens": 30, "output_tokens": 10},
            },
            {
                "stop_reason": "end_turn",
                "content": [{"type": "text", "text": "Found 5 relevant results."}],
                "usage": {"input_tokens": 30, "output_tokens": 10},
            },
            # Synthesize
            {
                "stop_reason": "end_turn",
                "content": [
                    {"type": "text", "text": "Synthesized: 5 results found."}
                ],
                "usage": {"input_tokens": 30, "output_tokens": 10},
            },
        ])
        search_tools = [
            {
                "name": "search",
                "description": "Search the web",
                "input_schema": {
                    "type": "object",
                    "properties": {"query": {"type": "string"}},
                    "required": ["query"],
                },
            },
        ]
        executor = make_tool_executor({"search": lambda query: f"Results for {query}"})
        sw = SupervisorWorker(client, executor)
        sw.register_worker(
            name="searcher",
            description="Web searcher",
            system_prompt="You search the web",
            tools=search_tools,
        )

        result = sw.run("Search for latest docs")
        assert result.success is True
        assert result.total_tool_calls >= 1


# ============================================================================
# Integration-style test
# ============================================================================


class TestIntegration:
    """End-to-end tests combining multiple components."""

    def test_agent_loop_handles_complex_task(self) -> None:
        """Agent loop handles a multi-step, multi-tool task."""
        responses = [
            # Step 1: get weather
            {
                "stop_reason": "tool_use",
                "content": [
                    {
                        "type": "tool_use",
                        "id": "t1",
                        "name": "get_weather",
                        "input": {"location": "Shanghai"},
                    },
                ],
                "usage": {"input_tokens": 50, "output_tokens": 20},
            },
            # Step 2: based on weather, check if outdoor activities are good
            {
                "stop_reason": "tool_use",
                "content": [
                    {
                        "type": "tool_use",
                        "id": "t2",
                        "name": "check_outdoor",
                        "input": {"weather": "sunny, 25C, light breeze"},
                    },
                ],
                "usage": {"input_tokens": 80, "output_tokens": 20},
            },
            # Step 3: final answer
            {
                "stop_reason": "end_turn",
                "content": [
                    {
                        "type": "text",
                        "text": "Shanghai is sunny and 25C with light breeze. Perfect for outdoor activities!",
                    },
                ],
                "usage": {"input_tokens": 100, "output_tokens": 20},
            },
        ]
        tools_map = {
            "get_weather": lambda location: f"Weather in {location}: sunny, 25C, light breeze",
            "check_outdoor": lambda weather: f"Based on '{weather}': excellent conditions",
        }
        client = MockClient(responses)
        executor = make_tool_executor(tools_map)
        loop = AgentLoop(client, executor)
        result = loop.run("Is today good for outdoor activities in Shanghai?")

        assert result.success is True
        assert result.iterations == 3
        assert result.tool_calls_made == 2
        assert "Shanghai" in result.answer
        assert "outdoor" in result.answer.lower()
