"""
Tests for Chapter 12: Cross-language interoperability.

Verifies that a Python MCP Server can be accessed by a Node.js client
via stdio transport (JSON-RPC line protocol). Also verifies that the
Python MCPClient can access the Python MCPServer.

This validates the core value proposition of MCP: language-agnostic
protocol interoperability.
"""

import json
import pytest
import asyncio
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path


def _has_node() -> bool:
    """Check if Node.js is available on the system."""
    return shutil.which("node") is not None

sys.path.insert(0, str(Path(__file__).parent))

from mcp_client import MCPClient


# ---------------------------------------------------------------------------
# Helper: Minimal MCP server script for interop testing
# ---------------------------------------------------------------------------

INTEROP_SERVER_SCRIPT = """
import sys, json, asyncio
sys.path.insert(0, r'{ch12_dir}')

from mcp_server import MCPServer, ToolDefinition, ResourceDefinition

async def main():
    srv = MCPServer("interop-server", "2.0.0")
    srv.register_tool(ToolDefinition(
        name="echo",
        description="Echo back the message",
        inputSchema={"type": "object", "properties": {"message": {"type": "string"}}, "required": ["message"]},
        handler=lambda a: a["message"]
    ))
    srv.register_tool(ToolDefinition(
        name="add",
        description="Add two integers",
        inputSchema={"type": "object", "properties": {"a": {"type": "integer"}, "b": {"type": "integer"}}, "required": ["a", "b"]},
        handler=lambda a: str(a["a"] + a["b"])
    ))
    srv.register_tool(ToolDefinition(
        name="get_server_info",
        description="Return server information",
        inputSchema={"type": "object", "properties": {}},
        handler=lambda a: json.dumps({"language": "python", "version": "2.0.0"})
    ))
    srv.register_resource(ResourceDefinition(
        uri="interop://status",
        name="Server Status",
        description="Current server status information",
        mimeType="application/json"
    ), reader=lambda uri: json.dumps({"status": "ok", "uptime": 0}))
    srv.register_resource(ResourceDefinition(
        uri="interop://greeting",
        name="Greeting",
        mimeType="text/plain"
    ), reader=lambda uri: "Hello from Python MCP Server!")
    await srv.run_stdio()

asyncio.run(main())
"""

# Node.js interop client that tests the Python MCP Server via stdio
NODE_INTEROP_SCRIPT = """
// Node.js MCP Interop Client
// Connects to a Python MCP server via stdio and validates JSON-RPC interactions.

const { spawn } = require('child_process');

async function sendRequest(proc, method, params, id) {
    const request = JSON.stringify({ jsonrpc: '2.0', id, method, params });
    proc.stdin.write(request + '\\n');
}

function readResponse(proc, timeout = 5000) {
    return new Promise((resolve, reject) => {
        const timer = setTimeout(() => reject(new Error('Timeout')), timeout);
        const onData = (data) => {
            const lines = data.toString().trim().split('\\n');
            for (const line of lines) {
                if (!line) continue;
                try {
                    const msg = JSON.parse(line);
                    if (msg.id !== undefined) {
                        clearTimeout(timer);
                        proc.stdout.removeListener('data', onData);
                        resolve(msg);
                        return;
                    }
                } catch (e) { /* skip */ }
            }
        };
        proc.stdout.on('data', onData);
    });
}

async function runTests() {
    const errors = [];
    const pythonCmd = process.argv[2] || 'python3';
    const scriptPath = process.argv[3];
    if (!scriptPath) {
        console.error('No server script provided');
        process.exit(1);
    }

    const proc = spawn(pythonCmd, [scriptPath], {
        stdio: ['pipe', 'pipe', 'pipe'],
        env: { ...process.env, PYTHONUNBUFFERED: '1' }
    });

    let requestId = 0;

    try {
        // 1. Initialize
        await sendRequest(proc, 'initialize', {
            protocolVersion: '2025-11-25',
            capabilities: { roots: { listChanged: true }, sampling: {} },
            clientInfo: { name: 'node-interop-client', version: '1.0.0' }
        }, ++requestId);

        const initResp = await readResponse(proc);
        if (!initResp.result) {
            errors.push('Initialize failed: ' + JSON.stringify(initResp));
        } else {
            if (initResp.result.serverInfo.name !== 'interop-server') {
                errors.push('Server name mismatch');
            }
            if (!initResp.result.capabilities.tools) {
                errors.push('Tools capability missing');
            }
            if (!initResp.result.capabilities.resources) {
                errors.push('Resources capability missing');
            }
        }

        // Send initialized notification
        const notif = JSON.stringify({ jsonrpc: '2.0', method: 'notifications/initialized', params: {} });
        proc.stdin.write(notif + '\\n');

        // 2. List tools
        await sendRequest(proc, 'tools/list', {}, ++requestId);
        const toolsResp = await readResponse(proc);
        const tools = toolsResp.result?.tools || [];
        const toolNames = tools.map(t => t.name);
        if (!toolNames.includes('echo')) errors.push('echo tool not found');
        if (!toolNames.includes('add')) errors.push('add tool not found');
        if (!toolNames.includes('get_server_info')) errors.push('get_server_info tool not found');
        if (tools.length !== 3) errors.push('Expected 3 tools, got ' + tools.length);

        // 3. Call echo
        await sendRequest(proc, 'tools/call', {
            name: 'echo',
            arguments: { message: 'hello from node' }
        }, ++requestId);
        const echoResp = await readResponse(proc);
        const echoText = echoResp.result?.content?.[0]?.text;
        if (echoText !== 'hello from node') {
            errors.push('echo failed: got "' + echoText + '"');
        }

        // 4. Call add
        await sendRequest(proc, 'tools/call', {
            name: 'add',
            arguments: { a: 40, b: 2 }
        }, ++requestId);
        const addResp = await readResponse(proc);
        const addText = addResp.result?.content?.[0]?.text;
        if (addText !== '42') {
            errors.push('add failed: got "' + addText + '"');
        }

        // 5. Call get_server_info
        await sendRequest(proc, 'tools/call', {
            name: 'get_server_info',
            arguments: {}
        }, ++requestId);
        const infoResp = await readResponse(proc);
        const info = JSON.parse(infoResp.result.content[0].text);
        if (info.language !== 'python') {
            errors.push('language should be python, got ' + info.language);
        }
        if (info.version !== '2.0.0') {
            errors.push('version mismatch');
        }

        // 6. List resources
        await sendRequest(proc, 'resources/list', {}, ++requestId);
        const resResp = await readResponse(proc);
        const resources = resResp.result?.resources || [];
        const uris = resources.map(r => r.uri);
        if (!uris.includes('interop://status')) errors.push('status resource not found');
        if (!uris.includes('interop://greeting')) errors.push('greeting resource not found');

        // 7. Read resource
        await sendRequest(proc, 'resources/read', { uri: 'interop://greeting' }, ++requestId);
        const readResp = await readResponse(proc);
        const greeting = readResp.result?.contents?.[0]?.text;
        if (!greeting || !greeting.includes('Python MCP Server')) {
            errors.push('resource read failed: ' + greeting);
        }

        // 8. Ping
        await sendRequest(proc, 'ping', {}, ++requestId);
        const pingResp = await readResponse(proc);
        if (!pingResp.result) {
            errors.push('ping failed');
        }

    } catch (e) {
        errors.push('Exception: ' + e.message);
    } finally {
        proc.kill();
    }

    if (errors.length > 0) {
        console.error('FAILED:', JSON.stringify(errors));
        process.exit(1);
    }
    console.log('PASSED: All interop tests passed');
    process.exit(0);
}

runTests();
"""


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def server_script() -> str:
    """Write interop server script to temp file."""
    ch12_dir = str(Path(__file__).parent)
    script = INTEROP_SERVER_SCRIPT.replace("{ch12_dir}", ch12_dir)

    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".py", delete=False
    ) as f:
        f.write(script)
        path = f.name

    yield path
    os.unlink(path)


@pytest.fixture
def node_client_script() -> str:
    """Write Node.js interop client script to temp file."""
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".js", delete=False, prefix="interop_client_"
    ) as f:
        f.write(NODE_INTEROP_SCRIPT)
        path = f.name

    yield path
    os.unlink(path)


# ---------------------------------------------------------------------------
# Python Client -> Python Server (baseline)
# ---------------------------------------------------------------------------


class TestPythonClientPythonServer:
    @pytest.mark.asyncio
    async def test_python_client_connects(self, server_script: str) -> None:
        """Python MCPClient should connect to Python MCPServer via stdio."""
        client = MCPClient()
        try:
            info = await client.connect_stdio("python", [server_script])
            assert info.name == "interop-server"
            assert info.version == "2.0.0"
            assert info.protocol_version == "2025-11-25"
        finally:
            await client.disconnect()

    @pytest.mark.asyncio
    async def test_python_client_tool_echo(self, server_script: str) -> None:
        client = MCPClient()
        try:
            await client.connect_stdio("python", [server_script])
            result = await client.call_tool("echo", {"message": "interop test"})
            assert result["content"][0]["text"] == "interop test"
        finally:
            await client.disconnect()

    @pytest.mark.asyncio
    async def test_python_client_tool_add(self, server_script: str) -> None:
        client = MCPClient()
        try:
            await client.connect_stdio("python", [server_script])
            result = await client.call_tool("add", {"a": 40, "b": 2})
            assert result["content"][0]["text"] == "42"
        finally:
            await client.disconnect()

    @pytest.mark.asyncio
    async def test_python_client_get_server_info(self, server_script: str) -> None:
        client = MCPClient()
        try:
            await client.connect_stdio("python", [server_script])
            result = await client.call_tool("get_server_info", {})
            data = json.loads(result["content"][0]["text"])
            assert data["language"] == "python"
            assert data["version"] == "2.0.0"
        finally:
            await client.disconnect()

    @pytest.mark.asyncio
    async def test_python_client_read_resource(self, server_script: str) -> None:
        client = MCPClient()
        try:
            await client.connect_stdio("python", [server_script])
            result = await client.read_resource("interop://greeting")
            assert "Python MCP Server" in result["contents"][0]["text"]
        finally:
            await client.disconnect()


# ---------------------------------------------------------------------------
# Node.js Client -> Python Server (cross-language interop)
# ---------------------------------------------------------------------------


class TestNodeClientPythonServer:
    @pytest.mark.skipif(
        not _has_node(),
        reason="Node.js is not available on this system",
    )
    def test_node_client_interop(
        self, server_script: str, node_client_script: str
    ) -> None:
        """Node.js MCP client should work with Python MCP server via stdio.

        This is the key cross-language interop test. A Node.js client
        sends JSON-RPC messages to a Python MCP server over stdio and
        validates all responses.

        Tests: initialize, tools/list, tools/call (echo, add, get_info),
        resources/list, resources/read, ping.
        """
        proc = subprocess.run(
            ["node", node_client_script, "python", server_script],
            capture_output=True,
            text=True,
            timeout=15,
        )
        assert proc.returncode == 0, (
            f"Node.js interop client failed (exit={proc.returncode})\n"
            f"STDERR: {proc.stderr}\nSTDOUT: {proc.stdout}"
        )
        assert "PASSED" in proc.stdout, (
            f"Expected PASSED in output, got: {proc.stdout}\nSTDERR: {proc.stderr}"
        )
