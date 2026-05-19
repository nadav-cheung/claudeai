"""
Tests for Chapter 6: Programmatic Tool Caller.
"""

import json

import pytest

from programmatic_tool_caller import (
    CodeExecutionResult,
    ProgrammaticToolCall,
    ProgrammaticToolCaller,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def caller() -> ProgrammaticToolCaller:
    return ProgrammaticToolCaller()


# ---------------------------------------------------------------------------
# Code execution tests
# ---------------------------------------------------------------------------


class TestCodeExecution:
    def test_execute_empty_code(self, caller: ProgrammaticToolCaller) -> None:
        result = caller.execute_code("")
        assert isinstance(result, CodeExecutionResult)
        assert result.return_code == 0
        assert result.stderr == "No tool calls found in code"

    def test_execute_code_with_await_calls(self, caller: ProgrammaticToolCaller) -> None:
        code = """
team = await get_team_members("engineering")
expenses = await get_expenses("emp_123", "Q3")
budget = await get_budget_by_level("senior")
"""
        result = caller.execute_code(code)
        assert result.return_code == 0
        assert len(caller.pending_calls) == 3
        assert caller.has_pending_calls

        names = [c.tool_name for c in caller.pending_calls]
        assert names == ["get_team_members", "get_expenses", "get_budget_by_level"]

    def test_execute_code_with_mixed_calls(self, caller: ProgrammaticToolCaller) -> None:
        code = """
data = query_database(sql="SELECT * FROM orders")
result = await process_data(data["items"])
"""
        result = caller.execute_code(code)
        names = [c.tool_name for c in caller.pending_calls]
        assert len(names) == 2
        assert "query_database" in names
        assert "process_data" in names

    def test_execute_code_with_no_tool_calls(self, caller: ProgrammaticToolCaller) -> None:
        code = """
x = 1 + 2
y = x * 3
"""
        result = caller.execute_code(code)
        assert result.stderr == "No tool calls found in code"
        assert not caller.has_pending_calls

    def test_execute_code_resets_previous_pending(self, caller: ProgrammaticToolCaller) -> None:
        caller.execute_code("result = tool_a()")
        assert len(caller.pending_calls) == 1
        # Second execution clears previous
        caller.execute_code("result = tool_b()")
        assert len(caller.pending_calls) == 1
        assert caller.pending_calls[0].tool_name == "tool_b"


# ---------------------------------------------------------------------------
# Tool call extraction tests
# ---------------------------------------------------------------------------


class TestExtractToolCalls:
    def test_extract_with_await(self, caller: ProgrammaticToolCaller) -> None:
        calls = caller.extract_tool_calls(
            "result = await get_data(param='value')"
        )
        assert len(calls) == 1
        assert calls[0].tool_name == "get_data"

    def test_extract_multiple_same_line(self, caller: ProgrammaticToolCaller) -> None:
        code = "a = foo()\nb = bar()\nc = baz()"
        calls = caller.extract_tool_calls(code)
        assert len(calls) == 3

    def test_extract_with_kwargs(self, caller: ProgrammaticToolCaller) -> None:
        calls = caller.extract_tool_calls(
            'result = query_database(sql="SELECT * FROM orders")'
        )
        assert len(calls) == 1
        assert calls[0].tool_name == "query_database"

    def test_extract_unique_ids(self, caller: ProgrammaticToolCaller) -> None:
        calls = caller.extract_tool_calls("a()\nb()\nc()")
        ids = [c.tool_use_id for c in calls]
        # All IDs should be unique
        assert len(set(ids)) == 3

    def test_extract_empty_code(self, caller: ProgrammaticToolCaller) -> None:
        calls = caller.extract_tool_calls("")
        assert calls == []


# ---------------------------------------------------------------------------
# Result processing tests
# ---------------------------------------------------------------------------


class TestResultProcessing:
    def test_process_single_result(self, caller: ProgrammaticToolCaller) -> None:
        output = caller.process_tool_results([
            {"tool_name": "get_weather", "result": "Sunny, 72F"}
        ])
        parsed = json.loads(output)
        assert parsed["tool_name"] == "get_weather"
        assert parsed["result"] == "Sunny, 72F"

    def test_process_multiple_results(self, caller: ProgrammaticToolCaller) -> None:
        output = caller.process_tool_results([
            {"tool_name": "a", "result": 1},
            {"tool_name": "b", "result": 2},
        ])
        lines = output.split("\n")
        assert len(lines) == 2
        assert json.loads(lines[0])["tool_name"] == "a"
        assert json.loads(lines[1])["tool_name"] == "b"

    def test_process_empty_results(self, caller: ProgrammaticToolCaller) -> None:
        output = caller.process_tool_results([])
        assert output == ""

    def test_format_tool_result_for_api(self, caller: ProgrammaticToolCaller) -> None:
        formatted = caller.format_tool_result_for_api(
            tool_use_id="toolu_abc123",
            result_content="Success",
        )
        assert formatted["type"] == "tool_result"
        assert formatted["tool_use_id"] == "toolu_abc123"
        assert formatted["content"] == "Success"


# ---------------------------------------------------------------------------
# Container management tests
# ---------------------------------------------------------------------------


class TestContainerManagement:
    def test_initial_container_none(self, caller: ProgrammaticToolCaller) -> None:
        assert caller.container_id is None

    def test_set_and_get_container(self, caller: ProgrammaticToolCaller) -> None:
        caller.set_container("container_xyz789")
        assert caller.container_id == "container_xyz789"

    def test_reset_container(self, caller: ProgrammaticToolCaller) -> None:
        caller.set_container("container_123")
        caller.execute_code("result = tool_a()")
        assert caller.container_id == "container_123"
        assert caller.has_pending_calls

        caller.reset_container()
        assert caller.container_id is None
        assert not caller.has_pending_calls

    def test_has_pending_calls_initially_false(self, caller: ProgrammaticToolCaller) -> None:
        assert not caller.has_pending_calls


# ---------------------------------------------------------------------------
# End-to-end PTC workflow
# ---------------------------------------------------------------------------


class TestEndToEndWorkflow:
    def test_budget_compliance_workflow(self, caller: ProgrammaticToolCaller) -> None:
        """Simulate the budget compliance workflow from the Anthropic blog."""
        orchestration_code = """
team = await get_team_members("engineering")
levels = list(set(m["level"] for m in team))
budget_results = await get_budget_by_level(level)
expenses = await get_expenses(m["id"], "Q3")

exceeded = []
for member, exp in zip(team, expenses):
    total = sum(e["amount"] for e in exp)
    if total > budget["travel_limit"]:
        exceeded.append({"name": member["name"], "spent": total})

print(json.dumps(exceeded))
"""
        result = caller.execute_code(orchestration_code)
        assert result.return_code == 0

        # Should have extracted 3 tool calls
        names = [c.tool_name for c in caller.pending_calls]
        assert "get_team_members" in names
        assert "get_budget_by_level" in names
        assert "get_expenses" in names

    def test_conditional_tool_selection(self, caller: ProgrammaticToolCaller) -> None:
        code = """
file_info = await get_file_info(path)
if file_info["size"] < 10000:
    content = await read_full_file(path)
else:
    content = await read_file_summary(path)
print(content)
"""
        result = caller.execute_code(code)
        names = [c.tool_name for c in caller.pending_calls]
        assert "get_file_info" in names
        assert "read_full_file" in names
        assert "read_file_summary" in names

    def test_batch_processing(self, caller: ProgrammaticToolCaller) -> None:
        code = """
data_west = await query_database("SELECT * FROM sales WHERE region='West'")
data_east = await query_database("SELECT * FROM sales WHERE region='East'")
data_central = await query_database("SELECT * FROM sales WHERE region='Central'")
data_north = await query_database("SELECT * FROM sales WHERE region='North'")
data_south = await query_database("SELECT * FROM sales WHERE region='South'")
"""
        result = caller.execute_code(code)
        # All 5 regions call the same tool
        names = [c.tool_name for c in caller.pending_calls]
        assert len(names) == 5
        assert all(n == "query_database" for n in names)
