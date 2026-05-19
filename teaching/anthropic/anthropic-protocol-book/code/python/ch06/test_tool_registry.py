"""
Tests for Chapter 6: Tool Registry.
"""

import pytest

from tool_registry import ToolDefinition, ToolRegistry


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def empty_registry() -> ToolRegistry:
    return ToolRegistry()


@pytest.fixture
def populated_registry() -> ToolRegistry:
    """Registry with 5 tools covering various configurations."""
    r = ToolRegistry()

    r.register(
        name="get_weather",
        description="Get current weather for a location",
        input_schema={
            "type": "object",
            "properties": {
                "location": {"type": "string", "description": "City name"}
            },
            "required": ["location"],
        },
        handler=lambda location: f"Weather for {location}: 72F",
        defer_loading=False,
    )

    r.register(
        name="get_time",
        description="Get current time for a timezone",
        input_schema={
            "type": "object",
            "properties": {
                "timezone": {"type": "string"}
            },
            "required": ["timezone"],
        },
        handler=lambda timezone: f"Time in {timezone}: 14:30",
        strict=True,
    )

    r.register(
        name="search_news",
        description="Search recent news articles by query",
        input_schema={
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "max_results": {"type": "integer", "default": 10},
            },
            "required": ["query"],
        },
        handler=lambda query, max_results=10: [f"News for {query}"] * min(max_results, 3),
        defer_loading=True,
    )

    r.register(
        name="query_database",
        description="Execute SQL query against internal database. Returns list of rows as JSON objects.",
        input_schema={
            "type": "object",
            "properties": {
                "sql": {"type": "string", "description": "SQL query to execute"}
            },
            "required": ["sql"],
        },
        handler=lambda sql: [{"id": 1, "name": "test"}],
        allowed_callers=["code_execution_20260120"],
    )

    r.register(
        name="send_slack",
        description="Send a message to a Slack channel",
        input_schema={
            "type": "object",
            "properties": {
                "channel": {"type": "string"},
                "text": {"type": "string"},
            },
            "required": ["channel", "text"],
        },
        handler=lambda channel, text: {"ok": True, "channel": channel},
        defer_loading=True,
        allowed_callers=["direct"],
    )

    return r


# ---------------------------------------------------------------------------
# Registration tests
# ---------------------------------------------------------------------------


class TestRegistration:
    def test_register_simple_tool(self, empty_registry: ToolRegistry) -> None:
        empty_registry.register(
            name="my_tool",
            description="A test tool",
            input_schema={"type": "object", "properties": {}, "required": []},
            handler=lambda: "done",
        )
        assert empty_registry.count() == 1
        assert empty_registry.get("my_tool") is not None

    def test_register_duplicate_raises(self, empty_registry: ToolRegistry) -> None:
        empty_registry.register(
            name="my_tool",
            description="First",
            input_schema={"type": "object", "properties": {}, "required": []},
            handler=lambda: 1,
        )
        with pytest.raises(ValueError, match="already registered"):
            empty_registry.register(
                name="my_tool",
                description="Second",
                input_schema={"type": "object", "properties": {}, "required": []},
                handler=lambda: 2,
            )

    def test_register_non_callable_raises(self, empty_registry: ToolRegistry) -> None:
        with pytest.raises(ValueError, match="must be callable"):
            empty_registry.register(
                name="bad",
                description="Not a function",
                input_schema={"type": "object", "properties": {}, "required": []},
                handler="not_callable",  # type: ignore[arg-type]
            )

    def test_register_bad_schema_raises(self, empty_registry: ToolRegistry) -> None:
        with pytest.raises(ValueError, match="type='object'"):
            empty_registry.register(
                name="bad",
                description="Invalid schema",
                input_schema={"type": "string"},  # must be object
                handler=lambda: None,
            )

    def test_unregister(self, empty_registry: ToolRegistry) -> None:
        empty_registry.register(
            name="t1",
            description="d",
            input_schema={"type": "object", "properties": {}, "required": []},
            handler=lambda: None,
        )
        assert empty_registry.count() == 1
        empty_registry.unregister("t1")
        assert empty_registry.count() == 0
        # unregister non-existent should not raise
        empty_registry.unregister("nonexistent")

    def test_register_with_all_options(self, empty_registry: ToolRegistry) -> None:
        empty_registry.register(
            name="full_tool",
            description="Tool with all options",
            input_schema={
                "type": "object",
                "properties": {"x": {"type": "integer"}},
                "required": [],
            },
            handler=lambda x=0: x * 2,
            defer_loading=True,
            allowed_callers=["code_execution_20260120"],
            input_examples=[{"x": 5}, {"x": 10}],
            strict=True,
        )
        tool = empty_registry.get("full_tool")
        assert tool is not None
        assert tool.defer_loading is True
        assert tool.allowed_callers == ["code_execution_20260120"]
        assert tool.strict is True
        assert len(tool.input_examples) == 2


# ---------------------------------------------------------------------------
# Query tests
# ---------------------------------------------------------------------------


class TestQueries:
    def test_get_existing(self, populated_registry: ToolRegistry) -> None:
        tool = populated_registry.get("get_weather")
        assert tool is not None
        assert tool.name == "get_weather"
        assert tool.defer_loading is False

    def test_get_missing(self, populated_registry: ToolRegistry) -> None:
        assert populated_registry.get("nonexistent") is None

    def test_list_names(self, populated_registry: ToolRegistry) -> None:
        names = populated_registry.list_names()
        assert len(names) == 5
        assert "get_weather" in names
        assert "search_news" in names

    def test_count(self, populated_registry: ToolRegistry) -> None:
        assert populated_registry.count() == 5

    def test_get_deferred_tools(self, populated_registry: ToolRegistry) -> None:
        deferred = populated_registry.get_deferred_tools()
        deferred_names = [t.name for t in deferred]
        assert "search_news" in deferred_names
        assert "send_slack" in deferred_names
        assert "get_weather" not in deferred_names
        assert len(deferred) == 2

    def test_get_immediate_tools(self, populated_registry: ToolRegistry) -> None:
        immediate = populated_registry.get_immediate_tools()
        immediate_names = [t.name for t in immediate]
        assert "get_weather" in immediate_names
        assert "get_time" in immediate_names
        assert "query_database" in immediate_names
        assert "search_news" not in immediate_names
        assert len(immediate) == 3

    def test_get_programmatic_tools(self, populated_registry: ToolRegistry) -> None:
        pt = populated_registry.get_programmatic_tools()
        pt_names = [t.name for t in pt]
        assert "query_database" in pt_names
        assert "send_slack" not in pt_names  # has allowed_callers but not code_execution
        assert len(pt) == 1

    def test_get_strict_tools(self, populated_registry: ToolRegistry) -> None:
        strict = populated_registry.get_strict_tools()
        strict_names = [t.name for t in strict]
        assert "get_time" in strict_names
        assert "get_weather" not in strict_names
        assert len(strict) == 1


# ---------------------------------------------------------------------------
# API format tests
# ---------------------------------------------------------------------------


class TestApiFormat:
    def test_to_api_format(self, populated_registry: ToolRegistry) -> None:
        tools = populated_registry.to_api_format()
        assert len(tools) == 5
        # Each must have required fields
        for t in tools:
            assert "name" in t
            assert "description" in t
            assert "input_schema" in t

    def test_api_format_deferred_flags(self, populated_registry: ToolRegistry) -> None:
        tools = populated_registry.to_api_format()
        deferred = [t for t in tools if t.get("defer_loading")]
        assert len(deferred) == 2

    def test_api_format_allowed_callers(self, populated_registry: ToolRegistry) -> None:
        tools = populated_registry.to_api_format()
        db_tool = next(t for t in tools if t["name"] == "query_database")
        assert db_tool["allowed_callers"] == ["code_execution_20260120"]

    def test_api_format_strict(self, populated_registry: ToolRegistry) -> None:
        tools = populated_registry.to_api_format()
        time_tool = next(t for t in tools if t["name"] == "get_time")
        assert time_tool["strict"] is True

    def test_to_search_index_format(self, populated_registry: ToolRegistry) -> None:
        index = populated_registry.to_search_index_format()
        assert len(index) == 2  # only deferred tools
        names = [e["name"] for e in index]
        assert "search_news" in names
        assert "send_slack" in names
        assert "get_weather" not in names


# ---------------------------------------------------------------------------
# Execution tests
# ---------------------------------------------------------------------------


class TestExecution:
    def test_execute_success(self, populated_registry: ToolRegistry) -> None:
        result = populated_registry.execute("get_weather", {"location": "Tokyo"})
        assert result["success"] is True
        assert "Tokyo" in result["result"]

    def test_execute_tool_not_found(self, populated_registry: ToolRegistry) -> None:
        with pytest.raises(KeyError, match="not found"):
            populated_registry.execute("nonexistent", {})

    def test_execute_handler_error(self, empty_registry: ToolRegistry) -> None:
        empty_registry.register(
            name="failing",
            description="Always fails",
            input_schema={"type": "object", "properties": {}, "required": []},
            handler=lambda: (_ for _ in ()).throw(ValueError("boom")),
        )
        result = empty_registry.execute("failing", {})
        assert result["success"] is False
        assert "boom" in result["error"]

    def test_execute_many(self, populated_registry: ToolRegistry) -> None:
        calls = [
            {"tool_name": "get_weather", "input": {"location": "SF"}},
            {"tool_name": "get_time", "input": {"timezone": "UTC"}},
        ]
        results = populated_registry.execute_many(calls)
        assert len(results) == 2
        assert results[0]["success"] is True
        assert results[1]["success"] is True

    def test_execute_many_mixed(self, empty_registry: ToolRegistry) -> None:
        empty_registry.register(
            name="ok",
            description="ok",
            input_schema={"type": "object", "properties": {}, "required": []},
            handler=lambda: "good",
        )
        empty_registry.register(
            name="fail",
            description="fail",
            input_schema={"type": "object", "properties": {}, "required": []},
            handler=lambda: (_ for _ in ()).throw(RuntimeError("bad")),
        )
        results = empty_registry.execute_many([
            {"tool_name": "ok", "input": {}},
            {"tool_name": "fail", "input": {}},
        ])
        assert results[0]["success"] is True
        assert results[1]["success"] is False


# ---------------------------------------------------------------------------
# Feature toggle tests
# ---------------------------------------------------------------------------


class TestFeatureToggles:
    def test_enable_search(self, empty_registry: ToolRegistry) -> None:
        assert empty_registry.is_search_enabled is False
        empty_registry.enable_tool_search()
        assert empty_registry.is_search_enabled is True

    def test_enable_code_execution(self, empty_registry: ToolRegistry) -> None:
        assert empty_registry.is_code_execution_enabled is False
        empty_registry.enable_code_execution()
        assert empty_registry.is_code_execution_enabled is True


# ---------------------------------------------------------------------------
# ToolDefinition tests
# ---------------------------------------------------------------------------


class TestToolDefinition:
    def test_minimal_to_api_format(self) -> None:
        td = ToolDefinition(
            name="test",
            description="desc",
            input_schema={"type": "object", "properties": {}, "required": []},
            handler=lambda: None,
        )
        api = td.to_api_format()
        assert api == {
            "name": "test",
            "description": "desc",
            "input_schema": {"type": "object", "properties": {}, "required": []},
        }
        # No extra keys for defaults
        assert "defer_loading" not in api
        assert "strict" not in api

    def test_full_to_api_format(self) -> None:
        td = ToolDefinition(
            name="full",
            description="A full tool",
            input_schema={"type": "object", "properties": {"a": {"type": "int"}}, "required": ["a"]},
            handler=lambda a: a,
            defer_loading=True,
            allowed_callers=["code_execution_20260120"],
            input_examples=[{"a": 1}],
            strict=True,
        )
        api = td.to_api_format()
        assert api["defer_loading"] is True
        assert api["allowed_callers"] == ["code_execution_20260120"]
        assert api["strict"] is True
        assert api["input_examples"] == [{"a": 1}]
