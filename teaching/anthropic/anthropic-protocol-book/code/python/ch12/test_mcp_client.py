"""
Tests for Chapter 12: MCP Client.

Tests the MCPClient connection management, capability negotiation,
tool discovery/invocation, resource reading, and reconnection.
Uses a real MCPServer subprocess for integration testing.
"""

import json
import pytest
import asyncio
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from mcp_client import MCPClient, ServerInfo


# ---------------------------------------------------------------------------
# Helper: Server script
# ---------------------------------------------------------------------------

SERVER_SCRIPT = """
import sys, json, asyncio
sys.path.insert(0, r'{ch12_dir}')

from mcp_server import MCPServer, ToolDefinition, ResourceDefinition

async def main():
    srv = MCPServer("test-server", "1.0.0")
    srv.register_tool(ToolDefinition(
        name="echo", description="Echo",
        inputSchema={"type": "object", "properties": {"msg": {"type": "string"}}, "required": ["msg"]},
        handler=lambda a: a["msg"]
    ))
    srv.register_tool(ToolDefinition(
        name="add", description="Add two numbers",
        inputSchema={"type": "object", "properties": {"a": {"type": "integer"}, "b": {"type": "integer"}}, "required": ["a", "b"]},
        handler=lambda a: str(a["a"] + a["b"])
    ))
    srv.register_tool(ToolDefinition(
        name="get_info", description="Server info",
        inputSchema={"type": "object", "properties": {}},
        handler=lambda a: json.dumps({"language": "python", "version": "1.0.0"})
    ))
    srv.register_resource(ResourceDefinition(
        uri="test://hello", name="Hello", mimeType="text/plain"
    ), reader=lambda uri: "Hello from resource")
    srv.register_resource(ResourceDefinition(
        uri="test://greeting", name="Greeting", mimeType="text/plain"
    ), reader=lambda uri: "Hi from Python MCP Server!")
    await srv.run_stdio()

asyncio.run(main())
"""


def _write_server_script() -> str:
    ch12_dir = str(Path(__file__).parent)
    script = SERVER_SCRIPT.replace("{ch12_dir}", ch12_dir)

    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".py", delete=False
    ) as f:
        f.write(script)
        path = f.name
    return path


async def _connect() -> tuple[MCPClient, str]:
    """Create a connected MCPClient."""
    server_script = _write_server_script()
    client = MCPClient()
    await client.connect_stdio("python", [server_script])
    return client, server_script


async def _disconnect(client: MCPClient, script_path: str) -> None:
    await client.disconnect()
    try:
        os.unlink(script_path)
    except FileNotFoundError:
        pass


# ---------------------------------------------------------------------------
# Client connection tests
# ---------------------------------------------------------------------------


class TestClientConnection:
    @pytest.mark.asyncio
    async def test_connect_stdio(self) -> None:
        client, script = await _connect()
        try:
            info = client.get_server_info()
            assert info.name == "test-server"
            assert info.version == "1.0.0"
            assert info.protocol_version == "2025-11-25"
        finally:
            await _disconnect(client, script)

    @pytest.mark.asyncio
    async def test_connect_and_list_tools(self) -> None:
        client, script = await _connect()
        try:
            tools = await client.list_tools()
            assert len(tools) == 3
            names = {t["name"] for t in tools}
            assert "echo" in names
            assert "add" in names
            assert "get_info" in names
        finally:
            await _disconnect(client, script)

    @pytest.mark.asyncio
    async def test_call_tool_echo(self) -> None:
        client, script = await _connect()
        try:
            result = await client.call_tool("echo", {"msg": "hello from client"})
            assert result["isError"] == False
            assert result["content"][0]["text"] == "hello from client"
        finally:
            await _disconnect(client, script)

    @pytest.mark.asyncio
    async def test_call_tool_add(self) -> None:
        client, script = await _connect()
        try:
            result = await client.call_tool("add", {"a": 40, "b": 2})
            assert result["content"][0]["text"] == "42"
        finally:
            await _disconnect(client, script)

    @pytest.mark.asyncio
    async def test_call_tool_get_info(self) -> None:
        client, script = await _connect()
        try:
            result = await client.call_tool("get_info", {})
            data = json.loads(result["content"][0]["text"])
            assert data["language"] == "python"
            assert data["version"] == "1.0.0"
        finally:
            await _disconnect(client, script)

    @pytest.mark.asyncio
    async def test_list_resources(self) -> None:
        client, script = await _connect()
        try:
            resources = await client.list_resources()
            assert len(resources) == 2
            uris = {r["uri"] for r in resources}
            assert "test://hello" in uris
            assert "test://greeting" in uris
        finally:
            await _disconnect(client, script)

    @pytest.mark.asyncio
    async def test_read_resource(self) -> None:
        client, script = await _connect()
        try:
            result = await client.read_resource("test://hello")
            assert "Hello from resource" in result["contents"][0]["text"]
        finally:
            await _disconnect(client, script)

    @pytest.mark.asyncio
    async def test_get_server_info(self) -> None:
        client, script = await _connect()
        try:
            info = client.get_server_info()
            assert info.name == "test-server"
            assert "tools" in info.capabilities
        finally:
            await _disconnect(client, script)


class TestClientCapabilities:
    @pytest.mark.asyncio
    async def test_capability_negotiation(self) -> None:
        client, script = await _connect()
        try:
            info = client.get_server_info()
            caps = info.capabilities
            assert "tools" in caps
            assert "resources" in caps
            assert isinstance(caps["tools"], dict)
        finally:
            await _disconnect(client, script)


class TestReconnection:
    @pytest.mark.asyncio
    async def test_reconnect_with_backoff(self) -> None:
        client, script = await _connect()
        try:
            # Verify connected
            tools = await client.list_tools()
            assert len(tools) > 0

            # Disconnect
            await client.disconnect()

            # Reconnect
            info = await client.reconnect_with_backoff(
                command="python", args=[script], max_retries=3
            )
            assert info.name == "test-server"

            # Verify tools work after reconnection
            tools = await client.list_tools()
            assert len(tools) > 0
        finally:
            os.unlink(script)
            try:
                await client.disconnect()
            except Exception:
                pass

    @pytest.mark.asyncio
    async def test_ping(self) -> None:
        client, script = await _connect()
        try:
            assert await client.ping() is True
        finally:
            await _disconnect(client, script)
