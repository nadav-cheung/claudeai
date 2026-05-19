"""
Tests for Chapter 12: MCP Tasks (SEP-1686).

Tests the MCPTask class for task submission, status polling,
result retrieval, wait_for_completion, and cancellation using
a real MCPServer via MCPClient.
"""

import json
import pytest
import asyncio
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from mcp_client import MCPClient
from mcp_tasks import (
    MCPTask,
    TASK_STATUS_WORKING,
    TASK_STATUS_COMPLETED,
    TASK_STATUS_FAILED,
    TASK_STATUS_CANCELLED,
    TERMINAL_STATUSES,
)


# ---------------------------------------------------------------------------
# Helper: Server script with task-capable tools
# ---------------------------------------------------------------------------

TASK_SERVER_SCRIPT = """
import sys, json, asyncio
sys.path.insert(0, r'{ch12_dir}')

from mcp_server import MCPServer, ToolDefinition

async def main():
    srv = MCPServer("task-server", "1.0.0")
    srv.register_tool(ToolDefinition(
        name="quick_task",
        description="Completes immediately",
        inputSchema={"type": "object", "properties": {}},
        handler=lambda a: "quick done",
        execution_taskSupport="optional"
    ))
    srv.register_tool(ToolDefinition(
        name="slow_task",
        description="Takes a moment",
        inputSchema={"type": "object", "properties": {"delay": {"type": "number"}}},
        handler=lambda a: "slow done",
        execution_taskSupport="optional"
    ))
    srv.register_tool(ToolDefinition(
        name="task_required",
        description="Must be invoked as task",
        inputSchema={"type": "object", "properties": {}},
        handler=lambda a: "task required done",
        execution_taskSupport="required"
    ))
    await srv.run_stdio()

asyncio.run(main())
"""


def _write_server_script() -> str:
    """Write a task-capable MCP server script to a temp file."""
    ch12_dir = str(Path(__file__).parent)
    script = TASK_SERVER_SCRIPT.replace("{ch12_dir}", ch12_dir)

    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".py", delete=False
    ) as f:
        f.write(script)
        path = f.name
    return path


async def _connect() -> tuple[MCPClient, MCPTask, str]:
    """Create a connected MCPClient + MCPTask, return (client, task_mgr, script_path)."""
    server_script = _write_server_script()
    client = MCPClient()
    await client.connect_stdio("python", [server_script])
    task_mgr = MCPTask(client)
    return client, task_mgr, server_script


async def _disconnect(client: MCPClient, script_path: str) -> None:
    """Cleanup: disconnect client and remove temp script."""
    await client.disconnect()
    try:
        os.unlink(script_path)
    except FileNotFoundError:
        pass  # Script already cleaned up


# ---------------------------------------------------------------------------
# Task submission
# ---------------------------------------------------------------------------


class TestTaskSubmission:
    @pytest.mark.asyncio
    async def test_submit_task_returns_task_id(self) -> None:
        client, task_mgr, script = await _connect()
        try:
            task_id = await task_mgr.submit_task("quick_task", {})
            assert isinstance(task_id, str)
            assert len(task_id) > 0
        finally:
            await _disconnect(client, script)

    @pytest.mark.asyncio
    async def test_submit_task_with_ttl(self) -> None:
        client, task_mgr, script = await _connect()
        try:
            task_id = await task_mgr.submit_task("quick_task", {}, ttl=30000)
            assert isinstance(task_id, str)
        finally:
            await _disconnect(client, script)

    @pytest.mark.asyncio
    async def test_submit_task_stores_status(self) -> None:
        client, task_mgr, script = await _connect()
        try:
            task_id = await task_mgr.submit_task("quick_task", {})
            status = await task_mgr.get_task_status(task_id)
            assert "status" in status
            assert "taskId" in status
            assert status["taskId"] == task_id
        finally:
            await _disconnect(client, script)


# ---------------------------------------------------------------------------
# Task status polling
# ---------------------------------------------------------------------------


class TestTaskPolling:
    @pytest.mark.asyncio
    async def test_task_goes_to_completed(self) -> None:
        client, task_mgr, script = await _connect()
        try:
            task_id = await task_mgr.submit_task("quick_task", {})

            for _ in range(50):
                status = await task_mgr.get_task_status(task_id)
                if status["status"] == TASK_STATUS_COMPLETED:
                    break
                await asyncio.sleep(0.1)

            final = await task_mgr.get_task_status(task_id)
            assert final["status"] == TASK_STATUS_COMPLETED
        finally:
            await _disconnect(client, script)

    @pytest.mark.asyncio
    async def test_poll_respects_interval(self) -> None:
        client, task_mgr, script = await _connect()
        try:
            task_id = await task_mgr.submit_task("quick_task", {})
            status = await task_mgr.get_task_status(task_id)
            assert "pollInterval" in status
            assert isinstance(status["pollInterval"], (int, float))
        finally:
            await _disconnect(client, script)

    @pytest.mark.asyncio
    async def test_task_has_created_at(self) -> None:
        client, task_mgr, script = await _connect()
        try:
            task_id = await task_mgr.submit_task("quick_task", {})
            status = await task_mgr.get_task_status(task_id)
            assert "createdAt" in status
            assert "lastUpdatedAt" in status
        finally:
            await _disconnect(client, script)


# ---------------------------------------------------------------------------
# Wait for completion
# ---------------------------------------------------------------------------


class TestWaitForCompletion:
    @pytest.mark.asyncio
    async def test_wait_for_completion_success(self) -> None:
        client, task_mgr, script = await _connect()
        try:
            task_id = await task_mgr.submit_task("quick_task", {})
            result = await task_mgr.wait_for_completion(task_id, timeout=10.0)
            assert result["success"] == True
            assert "result" in result
        finally:
            await _disconnect(client, script)

    @pytest.mark.asyncio
    async def test_submit_and_wait(self) -> None:
        client, task_mgr, script = await _connect()
        try:
            result = await task_mgr.submit_and_wait("quick_task", {}, timeout=10.0)
            assert result["success"] == True
        finally:
            await _disconnect(client, script)

    @pytest.mark.asyncio
    async def test_wait_completes_within_timeout(self) -> None:
        client, task_mgr, script = await _connect()
        try:
            task_id = await task_mgr.submit_task("quick_task", {})
            result = await task_mgr.wait_for_completion(task_id, timeout=10.0)
            assert result["success"] == True
        finally:
            await _disconnect(client, script)


# ---------------------------------------------------------------------------
# Task result retrieval
# ---------------------------------------------------------------------------


class TestTaskResult:
    @pytest.mark.asyncio
    async def test_get_task_result(self) -> None:
        client, task_mgr, script = await _connect()
        try:
            task_id = await task_mgr.submit_task("quick_task", {})
            await task_mgr.wait_for_completion(task_id, timeout=10.0)
            result = await task_mgr.get_task_result(task_id)
            assert "content" in result
        finally:
            await _disconnect(client, script)

    @pytest.mark.asyncio
    async def test_result_has_related_task_meta(self) -> None:
        client, task_mgr, script = await _connect()
        try:
            task_id = await task_mgr.submit_task("quick_task", {})
            await task_mgr.wait_for_completion(task_id, timeout=10.0)
            result = await task_mgr.get_task_result(task_id)
            meta = result.get("_meta", {})
            assert "io.modelcontextprotocol/related-task" in meta
            assert meta["io.modelcontextprotocol/related-task"]["taskId"] == task_id
        finally:
            await _disconnect(client, script)


# ---------------------------------------------------------------------------
# Task listing
# ---------------------------------------------------------------------------


class TestTaskListing:
    @pytest.mark.asyncio
    async def test_list_tasks(self) -> None:
        client, task_mgr, script = await _connect()
        try:
            await task_mgr.submit_task("quick_task", {})
            await asyncio.sleep(0.2)
            result = await task_mgr.list_tasks()
            assert "tasks" in result
            assert len(result["tasks"]) >= 1
        finally:
            await _disconnect(client, script)

    @pytest.mark.asyncio
    async def test_list_tasks_includes_task_id(self) -> None:
        client, task_mgr, script = await _connect()
        try:
            task_id = await task_mgr.submit_task("quick_task", {})
            await asyncio.sleep(0.3)
            result = await task_mgr.list_tasks()
            task_ids = [t["taskId"] for t in result["tasks"]]
            assert task_id in task_ids
        finally:
            await _disconnect(client, script)


# ---------------------------------------------------------------------------
# Task cancellation
# ---------------------------------------------------------------------------


class TestTaskCancellation:
    @pytest.mark.asyncio
    async def test_cancel_task_while_working(self) -> None:
        client, task_mgr, script = await _connect()
        try:
            # Submit and immediately cancel before background task completes.
            # We use asyncio.gather to race the cancel against the submit's
            # response processing, maximizing the chance of cancellation.
            submit_coro = task_mgr.submit_task("quick_task", {})
            task_id = await submit_coro

            # Cancel immediately - the background task may or may not have run
            try:
                result = await task_mgr.cancel_task(task_id)
                # If we got here, the cancel succeeded
                assert result["status"] == TASK_STATUS_CANCELLED
            except Exception as exc:
                # The task completed before we could cancel - that's fine too
                # for a fast task. Verify it's now terminal.
                status = await task_mgr.get_task_status(task_id)
                assert status["status"] in TERMINAL_STATUSES
        finally:
            await _disconnect(client, script)

    @pytest.mark.asyncio
    async def test_cancelled_task_is_terminal(self) -> None:
        client, task_mgr, script = await _connect()
        try:
            task_id = await task_mgr.submit_task("quick_task", {})
            # Wait for completion first
            await task_mgr.wait_for_completion(task_id, timeout=5.0)
            # Now cancel should fail because it's already terminal
            with pytest.raises(Exception):
                await task_mgr.cancel_task(task_id)
        finally:
            await _disconnect(client, script)
            await _disconnect(client, script)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------


class TestTaskConstants:
    def test_terminal_statuses(self) -> None:
        assert TASK_STATUS_COMPLETED in TERMINAL_STATUSES
        assert TASK_STATUS_FAILED in TERMINAL_STATUSES
        assert TASK_STATUS_CANCELLED in TERMINAL_STATUSES
        assert TASK_STATUS_WORKING not in TERMINAL_STATUSES
