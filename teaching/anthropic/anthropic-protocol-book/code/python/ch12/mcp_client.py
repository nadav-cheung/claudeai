"""
Chapter 12: MCP Client.

Protocol-level implementation of an MCP-compliant client supporting
connection management, capability negotiation, tool discovery and
invocation, resource listing/reading, and automatic reconnection
with exponential backoff. Supports stdio and HTTP transports.

MCP Specification: modelcontextprotocol.io/specification/2025-11-25
"""

from __future__ import annotations

import asyncio
import json
import os
import subprocess
import sys
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple


# ──────────────────────────────────────────────────────────────────────
# Data types
# ──────────────────────────────────────────────────────────────────────


@dataclass
class ClientCapabilities:
    """Capabilities the client advertises during initialization."""

    roots: Optional[dict] = None
    sampling: Optional[dict] = None
    elicitation: Optional[dict] = None


@dataclass
class ServerInfo:
    """Information about the connected MCP server."""

    name: str = ""
    version: str = ""
    protocol_version: str = ""
    capabilities: Dict[str, Any] = field(default_factory=dict)
    instructions: Optional[str] = None


# ──────────────────────────────────────────────────────────────────────
# MCPClient
# ──────────────────────────────────────────────────────────────────────


class MCPClient:
    """MCP-compliant client for connecting to and interacting with MCP servers.

    Supports:
    - stdio transport (launch server as child process)
    - HTTP transport (connect to remote server)
    - Capability negotiation during initialization
    - Automatic reconnection with exponential backoff
    - Tool listing, calling, resource reading, prompt discovery
    """

    PROTOCOL_VERSION = "2025-11-25"

    def __init__(self) -> None:
        self._process: Optional[subprocess.Popen[bytes]] = None
        self._reader: Optional[asyncio.StreamReader] = None
        self._writer: Optional[asyncio.StreamWriter] = None
        self._http_url: Optional[str] = None
        self._request_id: int = 0
        self._pending: Dict[int, asyncio.Future[dict]] = {}
        self._server_info = ServerInfo()
        self._initialized = False
        self._reader_task: Optional[asyncio.Task[None]] = None
        self._connected = False

    # ── Connection ────────────────────────────────────────────────

    async def connect_stdio(
        self, command: str, args: List[str], env: Optional[Dict[str, str]] = None
    ) -> ServerInfo:
        """Connect to an MCP server via stdio (launch as child process)."""
        merged_env = {**dict(os.environ), **(env or {})}

        self._process = subprocess.Popen(
            [command] + args,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=merged_env,
        )

        loop = asyncio.get_event_loop()

        # Set up stdout reader
        self._reader = asyncio.StreamReader()
        protocol = asyncio.StreamReaderProtocol(self._reader)
        await loop.connect_read_pipe(lambda: protocol, self._process.stdout)

        # Set up stdin writer
        transport, _ = await loop.connect_write_pipe(
            asyncio.streams.FlowControlMixin, self._process.stdin
        )

        class WriterWrapper:
            def __init__(self, t):
                self._t = t

            def write(self, data: bytes) -> None:
                self._t.write(data)

            async def drain(self) -> None:
                pass

            def close(self) -> None:
                self._t.close()

            @property
            def is_closing(self) -> bool:
                return self._t.is_closing()

        self._writer = WriterWrapper(transport)  # type: ignore[assignment]
        self._connected = True

        # Start background reader
        self._reader_task = asyncio.ensure_future(self._read_loop())

        # Perform initialization
        self._server_info = await self._initialize()
        self._initialized = True

        # Send initialized notification
        await self._send_notification("notifications/initialized", {})

        return self._server_info

    async def connect_http(self, url: str) -> ServerInfo:
        """Connect to a remote MCP server via HTTP."""
        import urllib.request

        self._http_url = url.rstrip("/")
        self._connected = True
        self._server_info = await self._initialize()
        self._initialized = True
        await self._send_notification("notifications/initialized", {})
        return self._server_info

    async def disconnect(self) -> None:
        """Close the connection to the MCP server."""
        self._connected = False
        if self._reader_task:
            self._reader_task.cancel()
            self._reader_task = None
        if self._writer:
            self._writer.close()
            self._writer = None
        if self._process:
            self._process.terminate()
            try:
                self._process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self._process.kill()
                self._process.wait()
            self._process = None
        self._http_url = None
        self._initialized = False
        self._server_info = ServerInfo()

    # ── Reconnection ──────────────────────────────────────────────

    async def reconnect_with_backoff(
        self,
        command: Optional[str] = None,
        args: Optional[List[str]] = None,
        max_retries: int = 5,
        base_delay: float = 1.0,
        max_delay: float = 30.0,
    ) -> ServerInfo:
        """Attempt reconnection with exponential backoff.

        Args:
            command: Server command (required for stdio).
            args: Server args (required for stdio).
            max_retries: Maximum number of reconnection attempts.
            base_delay: Initial delay in seconds.
            max_delay: Maximum delay cap in seconds.
        """
        if self._connected:
            await self.disconnect()

        for attempt in range(1, max_retries + 1):
            try:
                if self._http_url:
                    return await self.connect_http(self._http_url)
                elif command:
                    return await self.connect_stdio(command, args or [])
                else:
                    raise RuntimeError("No connection configuration available")
            except Exception as exc:
                if attempt == max_retries:
                    raise RuntimeError(
                        f"Failed to reconnect after {max_retries} attempts"
                    ) from exc
                delay = min(base_delay * (2 ** (attempt - 1)), max_delay)
                await asyncio.sleep(delay)

        raise RuntimeError("Reconnection failed")

    # ── Capability negotiation ────────────────────────────────────

    async def _initialize(self) -> ServerInfo:
        """Perform MCP initialization handshake."""
        result = await self._send_request(
            "initialize",
            {
                "protocolVersion": self.PROTOCOL_VERSION,
                "capabilities": {
                    "roots": {"listChanged": True},
                    "sampling": {},
                },
                "clientInfo": {
                    "name": "mcp-client-book",
                    "version": "1.0.0",
                },
            },
        )

        return ServerInfo(
            name=result.get("serverInfo", {}).get("name", ""),
            version=result.get("serverInfo", {}).get("version", ""),
            protocol_version=result.get("protocolVersion", ""),
            capabilities=result.get("capabilities", {}),
            instructions=result.get("instructions"),
        )

    # ── Tools ─────────────────────────────────────────────────────

    async def list_tools(self) -> List[dict]:
        """List all tools exposed by the server."""
        if not self._server_info.capabilities.get("tools"):
            return []
        result = await self._send_request("tools/list", {})
        return result.get("tools", [])

    async def call_tool(
        self, name: str, arguments: Dict[str, Any]
    ) -> dict:
        """Call a tool on the server and return the result."""
        return await self._send_request(
            "tools/call", {"name": name, "arguments": arguments}
        )

    async def call_tool_as_task(
        self,
        name: str,
        arguments: Dict[str, Any],
        ttl: Optional[int] = None,
    ) -> dict:
        """Call a tool as an MCP Task (SEP-1686).

        Returns a CreateTaskResult containing task metadata.
        """
        params: Dict[str, Any] = {
            "name": name,
            "arguments": arguments,
            "task": {},
        }
        if ttl is not None:
            params["task"]["ttl"] = ttl
        return await self._send_request("tools/call", params)

    # ── Resources ─────────────────────────────────────────────────

    async def list_resources(self) -> List[dict]:
        """List all resources exposed by the server."""
        if not self._server_info.capabilities.get("resources"):
            return []
        result = await self._send_request("resources/list", {})
        return result.get("resources", [])

    async def read_resource(self, uri: str) -> dict:
        """Read a resource from the server by URI."""
        return await self._send_request("resources/read", {"uri": uri})

    # ── Prompts ───────────────────────────────────────────────────

    async def list_prompts(self) -> List[dict]:
        """List all prompts exposed by the server."""
        if not self._server_info.capabilities.get("prompts"):
            return []
        result = await self._send_request("prompts/list", {})
        return result.get("prompts", [])

    async def get_prompt(
        self, name: str, arguments: Optional[Dict[str, Any]] = None
    ) -> dict:
        """Get a prompt from the server."""
        params: Dict[str, Any] = {"name": name}
        if arguments:
            params["arguments"] = arguments
        return await self._send_request("prompts/get", params)

    # ── Server Info ───────────────────────────────────────────────

    def get_server_info(self) -> ServerInfo:
        """Get the server information obtained during initialization."""
        return self._server_info

    async def ping(self) -> bool:
        """Ping the server to check connection health."""
        try:
            await self._send_request("ping", {})
            return True
        except Exception:
            return False

    # ── Messaging ─────────────────────────────────────────────────

    def _next_id(self) -> int:
        self._request_id += 1
        return self._request_id

    async def send_request(self, method: str, params: dict) -> dict:
        """Public: send a JSON-RPC request and wait for the response.

        This is the primary low-level API used by MCPTask and other
        components that need access to methods beyond tools/resources/prompts.
        """
        return await self._send_request(method, params)

    async def _send_request(self, method: str, params: dict) -> dict:
        """Send a JSON-RPC request and wait for the response."""
        req_id = self._next_id()
        future: asyncio.Future[dict] = asyncio.get_event_loop().create_future()
        self._pending[req_id] = future

        request = json.dumps(
            {"jsonrpc": "2.0", "id": req_id, "method": method, "params": params}
        )

        await self._write_line(request)

        try:
            result = await asyncio.wait_for(future, timeout=30.0)
        except asyncio.TimeoutError:
            self._pending.pop(req_id, None)
            raise TimeoutError(f"Request {method} timed out")
        return result

    async def _send_notification(self, method: str, params: dict) -> None:
        """Send a JSON-RPC notification (no response expected)."""
        notification = json.dumps(
            {"jsonrpc": "2.0", "method": method, "params": params}
        )
        await self._write_line(notification)

    async def _write_line(self, data: str) -> None:
        """Write a line to the underlying transport."""
        if self._http_url:
            await self._http_send(data)
        elif self._writer:
            self._writer.write((data + "\n").encode())
            await self._writer.drain()

    async def _http_send(self, data: str) -> None:
        """Send a JSON-RPC request to an HTTP endpoint."""
        import urllib.request

        req = urllib.request.Request(
            self._http_url + "/mcp" if self._http_url else "",
            data=data.encode(),
            headers={
                "Content-Type": "application/json",
                "MCP-Protocol-Version": self.PROTOCOL_VERSION,
            },
        )
        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(
            None, urllib.request.urlopen, req
        )
        body = response.read().decode()
        msg = json.loads(body)

        # Route the response to the pending future
        if "id" in msg:
            msg_id = msg["id"]
            future = self._pending.pop(msg_id, None)
            if future and not future.done():
                if "error" in msg:
                    future.set_exception(
                        Exception(msg["error"].get("message", "Unknown error"))
                    )
                else:
                    future.set_result(msg.get("result", {}))

    async def _read_loop(self) -> None:
        """Background task that reads lines from stdout and dispatches responses."""
        while self._connected and self._reader:
            try:
                line = await self._reader.readline()
                if not line:
                    # EOF: server process exited
                    self._connected = False
                    break

                raw = line.decode().strip()
                if not raw:
                    continue

                msg = json.loads(raw)

                # Route to pending future if it's a response
                if "id" in msg:
                    msg_id = msg["id"]
                    future = self._pending.pop(msg_id, None)
                    if future and not future.done():
                        if "error" in msg:
                            future.set_exception(
                                Exception(
                                    msg["error"].get("message", "Unknown error")
                                )
                            )
                        else:
                            future.set_result(msg.get("result", {}))
                # Notifications could be handled here (e.g. tasks/status)

            except asyncio.CancelledError:
                break
            except Exception:
                if not self._connected:
                    break
                continue
