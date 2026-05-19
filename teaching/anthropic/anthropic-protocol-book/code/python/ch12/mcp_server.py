"""
Chapter 12: MCP Server.

Protocol-level implementation of an MCP-compliant server supporting
tool registration, resource exposure, prompt templates, and both
stdio and HTTP transports. Implements JSON-RPC 2.0 message handling,
capability negotiation during initialization, and task lifecycle.

MCP Specification: modelcontextprotocol.io/specification/2025-11-25
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional, Set, Tuple


# ──────────────────────────────────────────────────────────────────────
# Data types
# ──────────────────────────────────────────────────────────────────────

@dataclass
class ContentBlock:
    """A content block returned by tool calls or resource reads."""

    type: str  # "text", "image", "resource"
    text: Optional[str] = None
    data: Optional[str] = None
    mimeType: Optional[str] = None
    uri: Optional[str] = None

    def to_dict(self) -> dict:
        d: Dict[str, Any] = {"type": self.type}
        if self.text is not None:
            d["text"] = self.text
        if self.data is not None:
            d["data"] = self.data
        if self.mimeType is not None:
            d["mimeType"] = self.mimeType
        if self.uri is not None:
            d["uri"] = self.uri
        return d


@dataclass
class ToolDefinition:
    """Definition of a registered MCP tool."""

    name: str
    description: str
    inputSchema: Dict[str, Any]
    handler: Callable[..., Any]
    execution_taskSupport: Optional[str] = None  # "required", "optional", or "forbidden"

    def to_dict(self) -> dict:
        d = {
            "name": self.name,
            "description": self.description,
            "inputSchema": self.inputSchema,
        }
        if self.execution_taskSupport is not None:
            d["execution"] = {"taskSupport": self.execution_taskSupport}
        return d


@dataclass
class ResourceDefinition:
    """Definition of an exposed MCP resource."""

    uri: str
    name: str
    description: str = ""
    mimeType: str = "text/plain"

    def to_dict(self) -> dict:
        return {
            "uri": self.uri,
            "name": self.name,
            "description": self.description,
            "mimeType": self.mimeType,
        }


@dataclass
class PromptDefinition:
    """Definition of a registered MCP prompt template."""

    name: str
    description: str = ""
    arguments: Optional[List[Dict[str, Any]]] = None

    def to_dict(self) -> dict:
        d = {
            "name": self.name,
            "description": self.description,
        }
        if self.arguments:
            d["arguments"] = self.arguments
        return d


@dataclass
class MCPTask:
    """Represents an MCP Task (SEP-1686)."""

    taskId: str
    status: str  # working, input_required, completed, failed, cancelled
    statusMessage: str = ""
    createdAt: str = ""
    lastUpdatedAt: str = ""
    ttl: Optional[int] = None
    pollInterval: int = 5000
    result: Optional[Any] = None
    error: Optional[dict] = None

    def to_dict(self) -> dict:
        d = {
            "taskId": self.taskId,
            "status": self.status,
            "createdAt": self.createdAt,
            "lastUpdatedAt": self.lastUpdatedAt,
            "ttl": self.ttl,
            "pollInterval": self.pollInterval,
        }
        if self.statusMessage:
            d["statusMessage"] = self.statusMessage
        return d

    def is_terminal(self) -> bool:
        return self.status in ("completed", "failed", "cancelled")


# ──────────────────────────────────────────────────────────────────────
# MCPServer
# ──────────────────────────────────────────────────────────────────────


class MCPServer:
    """MCP-compliant server that registers tools, resources, and prompts.

    Supports JSON-RPC 2.0 message handling, capability negotiation,
    and both stdio and HTTP transports.
    """

    PROTOCOL_VERSION = "2025-11-25"

    def __init__(self, name: str, version: str) -> None:
        self.name = name
        self.version = version
        self._tools: Dict[str, ToolDefinition] = {}
        self._resources: Dict[str, ResourceDefinition] = {}
        self._resource_readers: Dict[str, Callable[..., Any]] = {}
        self._prompts: Dict[str, PromptDefinition] = {}
        self._prompt_handlers: Dict[str, Callable[..., Any]] = {}
        self._tasks: Dict[str, MCPTask] = {}
        self._task_callbacks: Dict[str, Dict[str, Any]] = {}
        self._initialized = False
        self._server_info: Dict[str, Any] = {}
        self._pending_tasks: Dict[str, asyncio.Task[Any]] = {}

    # ── Registration ──────────────────────────────────────────────

    def register_tool(self, tool_def: ToolDefinition) -> None:
        """Register a tool with the server."""
        self._tools[tool_def.name] = tool_def

    def register_resource(
        self, resource_def: ResourceDefinition, reader: Optional[Callable[..., Any]] = None
    ) -> None:
        """Register a resource, optionally with a reader callback."""
        self._resources[resource_def.uri] = resource_def
        if reader:
            self._resource_readers[resource_def.uri] = reader

    def register_prompt(
        self, prompt_def: PromptDefinition, handler: Optional[Callable[..., Any]] = None
    ) -> None:
        """Register a prompt template, optionally with a handler."""
        self._prompts[prompt_def.name] = prompt_def
        if handler:
            self._prompt_handlers[prompt_def.name] = handler

    # ── Capabilities ──────────────────────────────────────────────

    def _build_capabilities(self) -> dict:
        caps: Dict[str, Any] = {}
        if self._tools:
            caps["tools"] = {"listChanged": False}
        if self._resources:
            caps["resources"] = {"subscribe": False, "listChanged": False}
        if self._prompts:
            caps["prompts"] = {"listChanged": False}
        # Tasks capability
        caps["tasks"] = {
            "list": {},
            "cancel": {},
            "requests": {"tools": {"call": {}}},
        }
        return caps

    # ── JSON-RPC handling ─────────────────────────────────────────

    def _make_response(self, request_id: Any, result: Any) -> dict:
        return {"jsonrpc": "2.0", "id": request_id, "result": result}

    def _make_error(
        self, request_id: Any, code: int, message: str, data: Optional[Any] = None
    ) -> dict:
        err = {"code": code, "message": message}
        if data is not None:
            err["data"] = data
        return {"jsonrpc": "2.0", "id": request_id, "error": err}

    def _make_notification(self, method: str, params: dict) -> dict:
        return {"jsonrpc": "2.0", "method": method, "params": params}

    async def handle_message(self, raw: str) -> Optional[str]:
        """Process a single JSON-RPC message and return a response string (or None for notifications)."""
        try:
            msg = json.loads(raw)
        except json.JSONDecodeError:
            return json.dumps(self._make_error(None, -32700, "Parse error"))

        method = msg.get("method", "")
        msg_id = msg.get("id")
        params = msg.get("params", {})

        # Handle initialize and initialized notification (must work before initialized flag)
        if method == "initialize":
            return await self._handle_initialize(msg_id, params)
        if method == "notifications/initialized":
            return await self._handle_initialized_notification(params, msg_id)

        # Block other requests until initialized
        if not self._initialized and method:
            if msg_id is not None:
                return json.dumps(
                    self._make_error(msg_id, -32000, "Server not initialized")
                )
            return None

        # Dispatch by method
        handler_map = {
            "notifications/initialized": self._handle_initialized_notification,
            "tools/list": self._handle_tools_list,
            "tools/call": self._handle_tools_call,
            "resources/list": self._handle_resources_list,
            "resources/read": self._handle_resources_read,
            "resources/templates/list": self._handle_resource_templates_list,
            "prompts/list": self._handle_prompts_list,
            "prompts/get": self._handle_prompts_get,
            "tasks/get": self._handle_tasks_get,
            "tasks/result": self._handle_tasks_result,
            "tasks/list": self._handle_tasks_list,
            "tasks/cancel": self._handle_tasks_cancel,
            "ping": self._handle_ping,
        }

        handler = handler_map.get(method)
        if handler is None:
            if msg_id is not None:
                return json.dumps(
                    self._make_error(msg_id, -32601, f"Method not found: {method}")
                )
            return None

        result = await handler(params, msg_id)
        if result is None:
            return None
        if isinstance(result, str):
            return result
        return json.dumps(self._make_response(msg_id, result))

    # ── Lifecycle handlers ────────────────────────────────────────

    async def _handle_initialize(self, msg_id: Any, params: dict) -> str:
        client_info = params.get("clientInfo", {})
        self._server_info = {
            "name": client_info.get("name", "unknown"),
            "version": client_info.get("version", "0.0.0"),
        }
        result = {
            "protocolVersion": self.PROTOCOL_VERSION,
            "capabilities": self._build_capabilities(),
            "serverInfo": {
                "name": self.name,
                "version": self.version,
            },
        }
        return json.dumps(self._make_response(msg_id, result))

    async def _handle_initialized_notification(
        self, params: dict, msg_id: Any
    ) -> None:
        self._initialized = True
        return None

    async def _handle_ping(self, params: dict, msg_id: Any) -> dict:
        return {}

    # ── Tools handlers ────────────────────────────────────────────

    async def _handle_tools_list(self, params: dict, msg_id: Any) -> dict:
        return {"tools": [t.to_dict() for t in self._tools.values()]}

    async def _handle_tools_call(self, params: dict, msg_id: Any) -> Optional[str]:
        tool_name = params["name"]
        arguments = params.get("arguments", {})
        task_params = params.get("task")

        tool = self._tools.get(tool_name)
        if not tool:
            return json.dumps(
                self._make_error(
                    msg_id, -32602, f"Unknown tool: {tool_name}"
                )
            )

        # Task augmentation: if task params present, create a task
        if task_params is not None:
            return await self._create_task(msg_id, tool, arguments, task_params)

        # Synchronous tool call
        try:
            result = tool.handler(arguments)
            if asyncio.iscoroutine(result):
                result = await result

            if isinstance(result, dict) and "content" in result:
                return json.dumps(self._make_response(msg_id, result))

            text = str(result) if not isinstance(result, str) else result
            return json.dumps(
                self._make_response(
                    msg_id,
                    {
                        "content": [{"type": "text", "text": text}],
                        "isError": False,
                    },
                )
            )
        except Exception as exc:
            return json.dumps(
                self._make_response(
                    msg_id,
                    {
                        "content": [{"type": "text", "text": str(exc)}],
                        "isError": True,
                    },
                )
            )

    async def _create_task(
        self, msg_id: Any, tool: ToolDefinition, arguments: dict, task_params: dict
    ) -> str:
        task_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        ttl = task_params.get("ttl", 60000)

        task = MCPTask(
            taskId=task_id,
            status="working",
            statusMessage="Task accepted.",
            createdAt=now,
            lastUpdatedAt=now,
            ttl=ttl,
            pollInterval=3000,
        )
        self._tasks[task_id] = task
        self._task_callbacks[task_id] = {
            "tool": tool,
            "arguments": arguments,
        }

        # Start background execution
        bg_task = asyncio.ensure_future(self._execute_task_background(task_id))
        self._pending_tasks[task_id] = bg_task

        return json.dumps(
            self._make_response(msg_id, {"task": task.to_dict()})
        )

    async def _execute_task_background(self, task_id: str) -> None:
        """Execute a task in background, updating status and result."""
        task = self._tasks.get(task_id)
        if not task:
            return

        cb = self._task_callbacks.get(task_id, {})
        tool: ToolDefinition = cb["tool"]
        arguments: dict = cb["arguments"]

        try:
            result = tool.handler(arguments)
            if asyncio.iscoroutine(result):
                result = await result

            task.status = "completed"
            task.statusMessage = "Task completed successfully."
            task.lastUpdatedAt = datetime.now(timezone.utc).strftime(
                "%Y-%m-%dT%H:%M:%SZ"
            )

            if isinstance(result, dict) and "content" in result:
                task.result = result
            else:
                text = str(result) if not isinstance(result, str) else result
                task.result = {
                    "content": [{"type": "text", "text": text}],
                    "isError": False,
                }
        except Exception as exc:
            task.status = "failed"
            task.statusMessage = str(exc)
            task.lastUpdatedAt = datetime.now(timezone.utc).strftime(
                "%Y-%m-%dT%H:%M:%SZ"
            )
            task.result = {
                "content": [{"type": "text", "text": str(exc)}],
                "isError": True,
            }

        # Send status notification
        self._emit_task_notification(task_id)

    def _emit_task_notification(self, task_id: str) -> None:
        """Server-side hook for task status notifications.

        In a real server, this would push the notification to the client.
        For our implementation, we store it so the client can poll.
        """
        pass

    # ── Resources handlers ────────────────────────────────────────

    async def _handle_resources_list(self, params: dict, msg_id: Any) -> dict:
        return {"resources": [r.to_dict() for r in self._resources.values()]}

    async def _handle_resources_read(self, params: dict, msg_id: Any) -> str:
        uri = params["uri"]
        resource = self._resources.get(uri)
        if not resource:
            return json.dumps(
                self._make_error(msg_id, -32002, f"Unknown resource: {uri}")
            )

        reader = self._resource_readers.get(uri)
        if reader:
            try:
                text = reader(uri)
                if asyncio.iscoroutine(text):
                    text = await text
                return json.dumps(
                    self._make_response(
                        msg_id,
                        {
                            "contents": [
                                {
                                    "uri": uri,
                                    "mimeType": resource.mimeType,
                                    "text": str(text),
                                }
                            ]
                        },
                    )
                )
            except Exception as exc:
                return json.dumps(
                    self._make_error(msg_id, -32603, str(exc))
                )

        return json.dumps(
            self._make_response(
                msg_id,
                {
                    "contents": [
                        {
                            "uri": uri,
                            "mimeType": resource.mimeType,
                            "text": f"Resource at {uri}",
                        }
                    ]
                },
            )
        )

    async def _handle_resource_templates_list(
        self, params: dict, msg_id: Any
    ) -> dict:
        return {"resourceTemplates": []}

    # ── Prompts handlers ──────────────────────────────────────────

    async def _handle_prompts_list(self, params: dict, msg_id: Any) -> dict:
        return {"prompts": [p.to_dict() for p in self._prompts.values()]}

    async def _handle_prompts_get(self, params: dict, msg_id: Any) -> str:
        prompt_name = params["name"]
        arguments = params.get("arguments", {})
        prompt = self._prompts.get(prompt_name)

        if not prompt:
            return json.dumps(
                self._make_error(msg_id, -32602, f"Unknown prompt: {prompt_name}")
            )

        handler = self._prompt_handlers.get(prompt_name)
        if handler:
            try:
                result = handler(arguments)
                if asyncio.iscoroutine(result):
                    result = await result
                if isinstance(result, dict):
                    return json.dumps(self._make_response(msg_id, result))
                return json.dumps(
                    self._make_response(
                        msg_id,
                        {
                            "description": prompt.description,
                            "messages": [
                                {
                                    "role": "user",
                                    "content": {"type": "text", "text": str(result)},
                                }
                            ],
                        },
                    )
                )
            except Exception as exc:
                return json.dumps(
                    self._make_error(msg_id, -32603, str(exc))
                )

        return json.dumps(
            self._make_response(
                msg_id,
                {
                    "description": prompt.description,
                    "messages": [
                        {
                            "role": "user",
                            "content": {
                                "type": "text",
                                "text": f"Prompt: {prompt_name}",
                            },
                        }
                    ],
                },
            )
        )

    # ── Tasks handlers ────────────────────────────────────────────

    async def _handle_tasks_get(self, params: dict, msg_id: Any) -> Optional[str]:
        task_id = params.get("taskId")
        task = self._tasks.get(task_id)
        if not task:
            return json.dumps(
                self._make_error(msg_id, -32602, f"Task not found: {task_id}")
            )
        return json.dumps(self._make_response(msg_id, task.to_dict()))

    async def _handle_tasks_result(self, params: dict, msg_id: Any) -> Optional[str]:
        task_id = params.get("taskId")
        task = self._tasks.get(task_id)
        if not task:
            return json.dumps(
                self._make_error(msg_id, -32602, f"Task not found: {task_id}")
            )

        # Block until task reaches terminal status
        while not task.is_terminal():
            await asyncio.sleep(0.1)

        if task.result is not None:
            result = dict(task.result)
            result["_meta"] = {
                "io.modelcontextprotocol/related-task": {"taskId": task_id}
            }
            return json.dumps(self._make_response(msg_id, result))
        return json.dumps(
            self._make_error(msg_id, -32603, "Task has no result")
        )

    async def _handle_tasks_list(self, params: dict, msg_id: Any) -> dict:
        cursor = params.get("cursor")
        all_tasks = [t.to_dict() for t in self._tasks.values()]
        return {"tasks": all_tasks, "nextCursor": None}

    async def _handle_tasks_cancel(
        self, params: dict, msg_id: Any
    ) -> Optional[str]:
        task_id = params.get("taskId")
        task = self._tasks.get(task_id)
        if not task:
            return json.dumps(
                self._make_error(msg_id, -32602, f"Task not found: {task_id}")
            )
        if task.is_terminal():
            return json.dumps(
                self._make_error(
                    msg_id,
                    -32602,
                    f"Cannot cancel task: already in terminal status '{task.status}'",
                )
            )
        task.status = "cancelled"
        task.statusMessage = "The task was cancelled by request."
        task.lastUpdatedAt = datetime.now(timezone.utc).strftime(
            "%Y-%m-%dT%H:%M:%SZ"
        )
        return json.dumps(self._make_response(msg_id, task.to_dict()))

    # ── Transport layer ───────────────────────────────────────────

    async def run_stdio(self) -> None:
        """Run MCP server over standard input/output.

        Each line on stdin is a complete JSON-RPC message.
        Responses are written to stdout as single lines.
        """
        reader = asyncio.StreamReader()
        protocol = asyncio.StreamReaderProtocol(reader)
        loop = asyncio.get_event_loop()

        await loop.connect_read_pipe(lambda: protocol, sys.stdin)
        w_transport, _ = await loop.connect_write_pipe(
            asyncio.streams.FlowControlMixin, sys.stdout
        )

        async def write_line(data: str) -> None:
            w_transport.write((data + "\n").encode())

        while True:
            try:
                line = await reader.readline()
                if not line:
                    break

                raw = line.decode().strip()
                if not raw:
                    continue

                response = await self.handle_message(raw)
                if response is not None:
                    await write_line(response)

            except Exception:
                continue

    async def run_http(self, host: str = "127.0.0.1", port: int = 8000) -> None:
        """Run MCP server over HTTP (streamable HTTP transport).

        Accepts POST requests at /mcp with JSON-RPC body and returns
        JSON-RPC responses.
        """
        from http.server import HTTPServer, BaseHTTPRequestHandler
        import threading

        server_instance = self

        class MCPHandler(BaseHTTPRequestHandler):
            def do_POST(self):
                content_length = int(self.headers.get("Content-Length", 0))
                body = self.rfile.read(content_length).decode()
                raw = body.strip()

                # Run async handler in sync context
                loop = asyncio.new_event_loop()
                try:
                    response = loop.run_until_complete(
                        server_instance.handle_message(raw)
                    )
                finally:
                    loop.close()

                if response is not None:
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json")
                    self.end_headers()
                    self.wfile.write(response.encode())
                else:
                    self.send_response(202)
                    self.end_headers()

            def log_message(self, format, *args):
                pass  # Suppress HTTP server logs

        server = HTTPServer((host, port), MCPHandler)
        print(f"MCP Server running on http://{host}:{port}/mcp", file=sys.stderr)

        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()

        try:
            while True:
                await asyncio.sleep(1)
        except KeyboardInterrupt:
            server.shutdown()
