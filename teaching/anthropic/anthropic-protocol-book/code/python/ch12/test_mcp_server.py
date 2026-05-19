"""
Tests for Chapter 12: MCP Server.

Tests the MCPServer JSON-RPC handling, tool/resource/prompt registration,
capability negotiation, and task lifecycle.
"""

import json
import pytest
import asyncio

from mcp_server import (
    MCPServer,
    ToolDefinition,
    ResourceDefinition,
    PromptDefinition,
    ContentBlock,
    MCPTask,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _send(server: MCPServer, method: str, params: dict, msg_id: int = 100) -> dict:
    """Helper: send a JSON-RPC request and parse the response."""
    raw = await server.handle_message(
        json.dumps(
            {
                "jsonrpc": "2.0",
                "id": msg_id,
                "method": method,
                "params": params,
            }
        )
    )
    assert raw is not None, f"No response for {method}"
    return json.loads(raw)


async def _initialize(srv: MCPServer) -> None:
    """Initialize a server for testing."""
    await srv.handle_message(
        json.dumps(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2025-11-25",
                    "capabilities": {},
                    "clientInfo": {"name": "test-client", "version": "1.0.0"},
                },
            }
        )
    )
    await srv.handle_message(
        json.dumps(
            {
                "jsonrpc": "2.0",
                "method": "notifications/initialized",
                "params": {},
            }
        )
    )


def _make_server() -> MCPServer:
    """Create a fully configured test server."""
    srv = MCPServer("test-server", "1.0.0")

    srv.register_tool(
        ToolDefinition(
            name="echo",
            description="Echo back the input",
            inputSchema={
                "type": "object",
                "properties": {"message": {"type": "string"}},
                "required": ["message"],
            },
            handler=lambda args: args["message"],
        )
    )
    srv.register_tool(
        ToolDefinition(
            name="add",
            description="Add two numbers",
            inputSchema={
                "type": "object",
                "properties": {
                    "a": {"type": "integer"},
                    "b": {"type": "integer"},
                },
                "required": ["a", "b"],
            },
            handler=lambda args: str(args["a"] + args["b"]),
        )
    )
    srv.register_tool(
        ToolDefinition(
            name="failing_tool",
            description="Always fails",
            inputSchema={"type": "object", "properties": {}},
            handler=lambda args: (_ for _ in ()).throw(
                ValueError("intentional failure")
            ),
        )
    )
    srv.register_tool(
        ToolDefinition(
            name="long_task",
            description="A long-running task",
            inputSchema={
                "type": "object",
                "properties": {"duration": {"type": "number"}},
            },
            handler=lambda args: f"Done after {args.get('duration', 0)}s",
            execution_taskSupport="optional",
        )
    )

    srv.register_resource(
        ResourceDefinition(
            uri="test://config/server-info",
            name="Server Info",
            description="Server configuration information",
            mimeType="application/json",
        ),
        reader=lambda uri: '{"name": "test-server", "version": "1.0.0"}',
    )
    srv.register_resource(
        ResourceDefinition(
            uri="test://data/empty",
            name="Empty Resource",
            description="Resource with no reader callback",
            mimeType="text/plain",
        )
    )

    srv.register_prompt(
        PromptDefinition(
            name="greeting",
            description="Generate a greeting",
            arguments=[
                {
                    "name": "name",
                    "description": "Name to greet",
                    "required": True,
                }
            ],
        ),
        handler=lambda args: f"Write a warm greeting for {args['name']}.",
    )

    return srv


# ---------------------------------------------------------------------------
# Initialization tests
# ---------------------------------------------------------------------------


class TestInitialization:
    @pytest.mark.asyncio
    async def test_initialize_response(self) -> None:
        """initialize should return server capabilities and info."""
        srv = _make_server()
        raw = await srv.handle_message(
            json.dumps(
                {
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "initialize",
                    "params": {
                        "protocolVersion": "2025-11-25",
                        "capabilities": {},
                        "clientInfo": {"name": "c", "version": "1.0"},
                    },
                }
            )
        )
        resp = json.loads(raw)
        assert resp["id"] == 1
        assert resp["result"]["protocolVersion"] == "2025-11-25"
        assert resp["result"]["serverInfo"]["name"] == "test-server"
        assert resp["result"]["serverInfo"]["version"] == "1.0.0"
        assert "tools" in resp["result"]["capabilities"]

    @pytest.mark.asyncio
    async def test_uninitialized_server_rejects_requests(self) -> None:
        """Before initialized notification, non-initialize requests are rejected."""
        srv = MCPServer("test", "1.0")
        raw = await srv.handle_message(
            json.dumps(
                {
                    "jsonrpc": "2.0",
                    "id": 2,
                    "method": "tools/list",
                    "params": {},
                }
            )
        )
        resp = json.loads(raw)
        assert "error" in resp
        assert resp["error"]["code"] == -32000

    @pytest.mark.asyncio
    async def test_initialized_notification(self) -> None:
        """Server should accept requests after initialized notification."""
        srv = MCPServer("test", "1.0")
        await srv.handle_message(
            json.dumps(
                {
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "initialize",
                    "params": {
                        "protocolVersion": "2025-11-25",
                        "capabilities": {},
                        "clientInfo": {"name": "c", "version": "1.0"},
                    },
                }
            )
        )
        await srv.handle_message(
            json.dumps(
                {
                    "jsonrpc": "2.0",
                    "method": "notifications/initialized",
                    "params": {},
                }
            )
        )
        raw = await srv.handle_message(
            json.dumps(
                {
                    "jsonrpc": "2.0",
                    "id": 2,
                    "method": "tools/list",
                    "params": {},
                }
            )
        )
        resp = json.loads(raw)
        assert "result" in resp


# ---------------------------------------------------------------------------
# Tools tests
# ---------------------------------------------------------------------------


class TestTools:
    @pytest.mark.asyncio
    async def test_list_tools(self) -> None:
        srv = _make_server()
        await _initialize(srv)
        resp = await _send(srv, "tools/list", {}, 10)
        tools = resp["result"]["tools"]
        names = {t["name"] for t in tools}
        assert "echo" in names
        assert "add" in names
        assert "failing_tool" in names
        assert "long_task" in names

    @pytest.mark.asyncio
    async def test_call_echo(self) -> None:
        srv = _make_server()
        await _initialize(srv)
        resp = await _send(
            srv, "tools/call", {"name": "echo", "arguments": {"message": "hello"}}, 11
        )
        assert resp["result"]["isError"] == False
        assert resp["result"]["content"][0]["text"] == "hello"

    @pytest.mark.asyncio
    async def test_call_add(self) -> None:
        srv = _make_server()
        await _initialize(srv)
        resp = await _send(
            srv, "tools/call", {"name": "add", "arguments": {"a": 10, "b": 32}}, 12
        )
        assert resp["result"]["isError"] == False
        assert resp["result"]["content"][0]["text"] == "42"

    @pytest.mark.asyncio
    async def test_call_unknown_tool(self) -> None:
        srv = _make_server()
        await _initialize(srv)
        resp = await _send(
            srv, "tools/call", {"name": "nonexistent", "arguments": {}}, 13
        )
        assert "error" in resp
        assert resp["error"]["code"] == -32602

    @pytest.mark.asyncio
    async def test_call_failing_tool_returns_isError(self) -> None:
        srv = _make_server()
        await _initialize(srv)
        resp = await _send(
            srv, "tools/call", {"name": "failing_tool", "arguments": {}}, 14
        )
        assert resp["result"]["isError"] == True
        assert "intentional failure" in resp["result"]["content"][0]["text"]


# ---------------------------------------------------------------------------
# Resources tests
# ---------------------------------------------------------------------------


class TestResources:
    @pytest.mark.asyncio
    async def test_list_resources(self) -> None:
        srv = _make_server()
        await _initialize(srv)
        resp = await _send(srv, "resources/list", {}, 20)
        resources = resp["result"]["resources"]
        uris = {r["uri"] for r in resources}
        assert "test://config/server-info" in uris
        assert "test://data/empty" in uris

    @pytest.mark.asyncio
    async def test_read_resource_with_reader(self) -> None:
        srv = _make_server()
        await _initialize(srv)
        resp = await _send(
            srv, "resources/read", {"uri": "test://config/server-info"}, 21
        )
        contents = resp["result"]["contents"]
        assert len(contents) == 1
        assert "test-server" in contents[0]["text"]

    @pytest.mark.asyncio
    async def test_read_resource_without_reader(self) -> None:
        srv = _make_server()
        await _initialize(srv)
        resp = await _send(srv, "resources/read", {"uri": "test://data/empty"}, 22)
        contents = resp["result"]["contents"]
        assert len(contents) == 1
        assert contents[0]["uri"] == "test://data/empty"

    @pytest.mark.asyncio
    async def test_read_unknown_resource(self) -> None:
        srv = _make_server()
        await _initialize(srv)
        resp = await _send(srv, "resources/read", {"uri": "nonexistent://uri"}, 23)
        assert "error" in resp
        assert resp["error"]["code"] == -32602


# ---------------------------------------------------------------------------
# Prompts tests
# ---------------------------------------------------------------------------


class TestPrompts:
    @pytest.mark.asyncio
    async def test_list_prompts(self) -> None:
        srv = _make_server()
        await _initialize(srv)
        resp = await _send(srv, "prompts/list", {}, 30)
        prompts = resp["result"]["prompts"]
        names = {p["name"] for p in prompts}
        assert "greeting" in names

    @pytest.mark.asyncio
    async def test_get_prompt(self) -> None:
        srv = _make_server()
        await _initialize(srv)
        resp = await _send(
            srv,
            "prompts/get",
            {"name": "greeting", "arguments": {"name": "Alice"}},
            31,
        )
        messages = resp["result"]["messages"]
        assert len(messages) == 1
        assert "Alice" in messages[0]["content"]["text"]

    @pytest.mark.asyncio
    async def test_get_unknown_prompt(self) -> None:
        srv = _make_server()
        await _initialize(srv)
        resp = await _send(srv, "prompts/get", {"name": "nonexistent"}, 32)
        assert "error" in resp
        assert resp["error"]["code"] == -32602


# ---------------------------------------------------------------------------
# Tasks tests
# ---------------------------------------------------------------------------


class TestTasks:
    @pytest.mark.asyncio
    async def test_create_task_via_tools_call(self) -> None:
        """Submitting tools/call with task param should return CreateTaskResult."""
        srv = _make_server()
        await _initialize(srv)
        resp = await _send(
            srv,
            "tools/call",
            {
                "name": "long_task",
                "arguments": {"duration": 1},
                "task": {"ttl": 60000},
            },
            40,
        )
        assert "result" in resp
        task = resp["result"].get("task")
        assert task is not None
        assert task["status"] == "working"
        assert "taskId" in task

    @pytest.mark.asyncio
    async def test_tasks_get(self) -> None:
        """tasks/get should return the current task status."""
        srv = _make_server()
        await _initialize(srv)
        resp = await _send(
            srv,
            "tools/call",
            {
                "name": "long_task",
                "arguments": {"duration": 0},
                "task": {"ttl": 60000},
            },
            41,
        )
        task_id = resp["result"]["task"]["taskId"]

        # Poll until completed
        deadline = asyncio.get_event_loop().time() + 5
        while asyncio.get_event_loop().time() < deadline:
            status_resp = await _send(srv, "tasks/get", {"taskId": task_id}, 42)
            st = status_resp["result"]["status"]
            if st in ("completed", "failed", "cancelled"):
                break
            await asyncio.sleep(0.05)

        final = await _send(srv, "tasks/get", {"taskId": task_id}, 43)
        assert final["result"]["status"] == "completed"

    @pytest.mark.asyncio
    async def test_tasks_cancel(self) -> None:
        """tasks/cancel should cancel a running task."""
        srv = _make_server()
        await _initialize(srv)
        resp = await _send(
            srv,
            "tools/call",
            {
                "name": "long_task",
                "arguments": {"duration": 5},
                "task": {"ttl": 60000},
            },
            44,
        )
        task_id = resp["result"]["task"]["taskId"]

        cancel = await _send(srv, "tasks/cancel", {"taskId": task_id}, 45)
        assert cancel["result"]["status"] == "cancelled"

    @pytest.mark.asyncio
    async def test_cancel_terminal_task_fails(self) -> None:
        """Cancelling a completed task should return an error."""
        srv = _make_server()
        await _initialize(srv)
        resp = await _send(
            srv,
            "tools/call",
            {
                "name": "long_task",
                "arguments": {"duration": 0},
                "task": {"ttl": 60000},
            },
            46,
        )
        task_id = resp["result"]["task"]["taskId"]

        # Wait for completion
        deadline = asyncio.get_event_loop().time() + 5
        while asyncio.get_event_loop().time() < deadline:
            status_resp = await _send(srv, "tasks/get", {"taskId": task_id}, 47)
            if status_resp["result"]["status"] in (
                "completed",
                "failed",
                "cancelled",
            ):
                break
            await asyncio.sleep(0.05)

        cancel = await _send(srv, "tasks/cancel", {"taskId": task_id}, 48)
        assert "error" in cancel

    @pytest.mark.asyncio
    async def test_tasks_result(self) -> None:
        """tasks/result should return the final result of a completed task."""
        srv = _make_server()
        await _initialize(srv)
        resp = await _send(
            srv,
            "tools/call",
            {
                "name": "long_task",
                "arguments": {"duration": 0},
                "task": {"ttl": 60000},
            },
            49,
        )
        task_id = resp["result"]["task"]["taskId"]

        result = await _send(srv, "tasks/result", {"taskId": task_id}, 50)
        assert "result" in result
        assert "content" in result["result"]
        assert "_meta" in result["result"]
        assert (
            result["result"]["_meta"]["io.modelcontextprotocol/related-task"][
                "taskId"
            ]
            == task_id
        )


# ---------------------------------------------------------------------------
# Capabilities tests
# ---------------------------------------------------------------------------


class TestCapabilities:
    def test_capabilities_include_tools(self) -> None:
        srv = _make_server()
        caps = srv._build_capabilities()
        assert "tools" in caps
        assert "resources" in caps
        assert "prompts" in caps
        assert "tasks" in caps

    def test_capabilities_tasks_structure(self) -> None:
        srv = _make_server()
        caps = srv._build_capabilities()
        tasks_caps = caps["tasks"]
        assert tasks_caps["list"] == {}
        assert tasks_caps["cancel"] == {}
        assert "tools" in tasks_caps["requests"]
        assert "call" in tasks_caps["requests"]["tools"]


# ---------------------------------------------------------------------------
# Error handling tests
# ---------------------------------------------------------------------------


class TestErrorHandling:
    @pytest.mark.asyncio
    async def test_parse_error(self) -> None:
        srv = _make_server()
        await _initialize(srv)
        raw = await srv.handle_message("not valid json{{{")
        resp = json.loads(raw)
        assert "error" in resp
        assert resp["error"]["code"] == -32700

    @pytest.mark.asyncio
    async def test_method_not_found(self) -> None:
        srv = _make_server()
        await _initialize(srv)
        resp = await _send(srv, "nonexistent/method", {}, 60)
        assert "error" in resp
        assert resp["error"]["code"] == -32601

    @pytest.mark.asyncio
    async def test_ping(self) -> None:
        srv = _make_server()
        await _initialize(srv)
        resp = await _send(srv, "ping", {}, 61)
        assert resp["result"] == {}
