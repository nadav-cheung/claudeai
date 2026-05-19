"""
Chapter 12: MCP Tasks (SEP-1686).

Implements the MCP Tasks specification for asynchronous task execution.
Provides task submission, status polling, result retrieval, listing,
and cancellation. Designed to work with any MCPClient.

MCP Tasks Spec: modelcontextprotocol.io/specification/2025-11-25/basic/utilities/tasks
SEP-1686: modelcontextprotocol.io/seps/1686-tasks
SEP-2663: modelcontextprotocol.io/seps/2663-tasks-extension
"""

from __future__ import annotations

import asyncio
import time
from typing import Any, Dict, List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from mcp_client import MCPClient


# ──────────────────────────────────────────────────────────────────────
# Task status constants
# ──────────────────────────────────────────────────────────────────────

TASK_STATUS_WORKING = "working"
TASK_STATUS_INPUT_REQUIRED = "input_required"
TASK_STATUS_COMPLETED = "completed"
TASK_STATUS_FAILED = "failed"
TASK_STATUS_CANCELLED = "cancelled"

TERMINAL_STATUSES = {TASK_STATUS_COMPLETED, TASK_STATUS_FAILED, TASK_STATUS_CANCELLED}


# ──────────────────────────────────────────────────────────────────────
# MCPTask
# ──────────────────────────────────────────────────────────────────────


class MCPTask:
    """Manages the lifecycle of an MCP Task.

    Wraps the SEP-1686 task operations: submission, status polling,
    result retrieval, listing, and cancellation.

    Usage:
        client = MCPClient()
        await client.connect_stdio("python", ["mcp_server.py"])
        task_mgr = MCPTask(client)
        task_result = await task_mgr.submit("analyze_data", {"dataset": "q4"})
        print(task_result["task"]["taskId"])
        result = await task_mgr.wait_for_completion("task-id-here")
    """

    def __init__(self, client: "MCPClient"):
        self._client = client
        self._tasks: Dict[str, dict] = {}

    # ── Task submission ──────────────────────────────────────────

    async def submit_task(
        self, tool_name: str, arguments: Dict[str, Any], ttl: Optional[int] = None
    ) -> str:
        """Submit a task-augmented tool call and return the task ID.

        Args:
            tool_name: Name of the tool to invoke.
            arguments: Tool arguments.
            ttl: Task time-to-live in milliseconds.

        Returns:
            The task ID assigned by the server.

        Raises:
            RuntimeError: If the server does not support task-augmented requests.
        """
        params: Dict[str, Any] = {
            "name": tool_name,
            "arguments": arguments,
            "task": {},
        }
        if ttl is not None:
            params["task"]["ttl"] = ttl

        response = await self._client.send_request("tools/call", params)

        task_data = response.get("task")
        if not task_data:
            raise RuntimeError(
                "Server did not return task data. "
                "Does the server support task-augmented tools/call?"
            )

        task_id = task_data["taskId"]
        self._tasks[task_id] = task_data
        return task_id

    # ── Status polling ───────────────────────────────────────────

    async def get_task_status(self, task_id: str) -> dict:
        """Get the current status of a task.

        Returns the full Task object as defined by the spec:
        {taskId, status, statusMessage, createdAt, lastUpdatedAt, ttl, pollInterval}
        """
        result = await self._client.send_request("tasks/get", {"taskId": task_id})
        self._tasks[task_id] = result
        return result

    async def wait_for_completion(
        self, task_id: str, timeout: float = 60.0, poll_interval: Optional[float] = None
    ) -> dict:
        """Poll for task completion and return the result.

        Args:
            task_id: The task ID to wait for.
            timeout: Maximum time to wait in seconds.
            poll_interval: Optional override for polling interval.
                          If None, uses the server's suggested pollInterval.

        Returns:
            The task result on success. On timeout, raises TimeoutError.
            On failure, returns {"success": False, "error": "..."}.

        Raises:
            TimeoutError: If task doesn't complete within timeout.
        """
        start = time.monotonic()
        default_interval = 1.0

        while True:
            elapsed = time.monotonic() - start
            if elapsed >= timeout:
                raise TimeoutError(
                    f"Task {task_id} did not complete within {timeout}s"
                )

            status = await self.get_task_status(task_id)
            current_status = status.get("status", "")

            if current_status in TERMINAL_STATUSES:
                if current_status == TASK_STATUS_COMPLETED:
                    result = await self.get_task_result(task_id)
                    return {"success": True, "result": result}
                elif current_status == TASK_STATUS_FAILED:
                    return {
                        "success": False,
                        "error": status.get("statusMessage", "Task failed"),
                    }
                elif current_status == TASK_STATUS_CANCELLED:
                    return {
                        "success": False,
                        "error": "Task was cancelled",
                    }

            interval = poll_interval or status.get("pollInterval", default_interval)
            # Convert ms to seconds
            if interval > 1:
                interval = interval / 1000.0
            interval = min(interval, timeout - elapsed)

            await asyncio.sleep(interval)

    # ── Result retrieval ─────────────────────────────────────────

    async def get_task_result(self, task_id: str) -> dict:
        """Retrieve the result of a completed task.

        Blocks until the task reaches a terminal status.
        Returns the actual operation result (e.g., CallToolResult).
        """
        result = await self._client.send_request("tasks/result", {"taskId": task_id})
        return result

    # ── Task listing ─────────────────────────────────────────────

    async def list_tasks(self, cursor: Optional[str] = None) -> dict:
        """List all tasks managed by the server.

        Returns: {tasks: [...], nextCursor: str|None}
        """
        params: Dict[str, Any] = {}
        if cursor:
            params["cursor"] = cursor
        return await self._client.send_request("tasks/list", params)

    # ── Task cancellation ────────────────────────────────────────

    async def cancel_task(self, task_id: str) -> dict:
        """Cancel a running task.

        Returns the task object with status "cancelled".

        Raises:
            RuntimeError: If the task is already in a terminal status.
        """
        return await self._client.send_request("tasks/cancel", {"taskId": task_id})

    # ── High-level helpers ───────────────────────────────────────

    async def submit_and_wait(
        self,
        tool_name: str,
        arguments: Dict[str, Any],
        ttl: Optional[int] = None,
        timeout: float = 60.0,
    ) -> dict:
        """Convenience: submit a task and wait for completion.

        Returns: {"success": True, "result": ...} or {"success": False, "error": ...}
        """
        task_id = await self.submit_task(tool_name, arguments, ttl=ttl)
        return await self.wait_for_completion(task_id, timeout=timeout)

    async def poll_until(
        self,
        task_id: str,
        predicate: callable,
        timeout: float = 60.0,
        poll_interval: float = 1.0,
    ) -> dict:
        """Poll until a custom predicate is satisfied.

        Args:
            task_id: Task ID to poll.
            predicate: Callable(status_dict) -> bool. Return True to stop.
            timeout: Maximum time in seconds.
            poll_interval: Seconds between polls.

        Returns:
            The final status dict when predicate returns True.
        """
        start = time.monotonic()
        while True:
            elapsed = time.monotonic() - start
            if elapsed >= timeout:
                raise TimeoutError(f"Polling timeout after {timeout}s")

            status = await self.get_task_status(task_id)
            if predicate(status):
                return status

            await asyncio.sleep(poll_interval)
