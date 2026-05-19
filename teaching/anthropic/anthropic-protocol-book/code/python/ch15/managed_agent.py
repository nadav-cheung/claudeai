"""
Chapter 15: Managed Agent Client.

A dependency-free HTTP client for Anthropic's Managed Agents API.
Does NOT depend on the official `anthropic` SDK -- uses httpx directly
so readers can understand every protocol detail.

Supports:
- Agent CRUD (create, retrieve, update, list, archive)
- Environment CRUD
- Session lifecycle (create, retrieve, list, delete, archive)
- Event sending, listing, and streaming (SSE)
- Session status polling and cancellation
- Memory Store attachment
- Outcome definition
- Dream creation and monitoring
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Iterator

import httpx


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

DEFAULT_BASE_URL = "https://api.anthropic.com"
DEFAULT_API_VERSION = "2023-06-01"
MANAGED_AGENTS_BETA = "managed-agents-2026-04-01"
DREAMING_BETA = "dreaming-2026-04-21"
DEFAULT_TIMEOUT = 120.0  # Managed Agents operations can take longer
DEFAULT_POLL_INTERVAL = 2.0  # seconds between status polls


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------

class ManagedAgentError(Exception):
    """Structured error for Managed Agents API failures."""

    def __init__(
        self,
        message: str,
        *,
        status_code: int = 0,
        error_type: str | None = None,
        request_id: str | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.error_type = error_type
        self.request_id = request_id

    @classmethod
    def from_response(cls, response: httpx.Response) -> ManagedAgentError:
        status_code = response.status_code
        error_type: str | None = None
        message = f"HTTP {status_code}"

        try:
            body = response.json()
        except (json.JSONDecodeError, ValueError):
            return cls(message, status_code=status_code)

        if isinstance(body, dict) and "error" in body:
            err = body["error"]
            if isinstance(err, dict):
                error_type = err.get("type")
                message = err.get("message", message)

        request_id = response.headers.get("request-id")
        return cls(
            message, status_code=status_code, error_type=error_type, request_id=request_id
        )


class SessionTimeoutError(ManagedAgentError):
    """Raised when polling exceeds max_wait_seconds."""


class SessionFailedError(ManagedAgentError):
    """Raised when a session terminates with an error state."""


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

@dataclass
class ManagedAgentConfig:
    """Client configuration for Managed Agents API."""

    api_key: str = field(
        default_factory=lambda: os.environ.get("ANTHROPIC_API_KEY", "")
    )
    base_url: str = field(
        default_factory=lambda: os.environ.get("ANTHROPIC_BASE_URL", DEFAULT_BASE_URL)
    )
    api_version: str = DEFAULT_API_VERSION
    timeout: float = DEFAULT_TIMEOUT
    poll_interval: float = DEFAULT_POLL_INTERVAL

    def __post_init__(self) -> None:
        if not self.api_key:
            raise ValueError(
                "api_key must be provided or set via ANTHROPIC_API_KEY environment variable"
            )


# ---------------------------------------------------------------------------
# Session Status
# ---------------------------------------------------------------------------

class SessionStatus(Enum):
    """Session lifecycle states."""

    CREATED = "created"
    RUNNING = "running"
    IDLE = "idle"
    ARCHIVED = "archived"
    DELETED = "deleted"


# ---------------------------------------------------------------------------
# Client
# ---------------------------------------------------------------------------

class ManagedAgentClient:
    """Synchronous HTTP client for Anthropic Managed Agents API.

    Does NOT use the official `anthropic` SDK. All requests are built by hand
    so readers can see every header, body field, and endpoint path.

    Usage::

        client = ManagedAgentClient()
        agent_id = client.create_agent({
            "name": "My Agent",
            "model": "claude-sonnet-4-6",
            "system": "You are a helpful assistant.",
        })
        session_id = client.start_session(agent_id, "Analyze this data.")
        status = client.get_session_status(session_id)
        result = client.get_session_result(session_id)
    """

    def __init__(self, config: ManagedAgentConfig | None = None) -> None:
        self._config = config or ManagedAgentConfig()
        self._client = httpx.Client(
            base_url=self._config.base_url,
            timeout=self._config.timeout,
            headers={"Content-Type": "application/json"},
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _headers(self, extra_betas: list[str] | None = None) -> dict[str, str]:
        """Build request headers including required beta headers."""
        betas = [MANAGED_AGENTS_BETA]
        if extra_betas:
            betas.extend(extra_betas)
        return {
            "x-api-key": self._config.api_key,
            "anthropic-version": self._config.api_version,
            "anthropic-beta": ",".join(betas),
        }

    def _get(self, path: str, extra_betas: list[str] | None = None) -> dict[str, Any]:
        resp = self._client.get(path, headers=self._headers(extra_betas))
        if resp.is_success:
            return resp.json()  # type: ignore[no-any-return]
        raise ManagedAgentError.from_response(resp)

    def _post(
        self,
        path: str,
        body: dict[str, Any],
        extra_betas: list[str] | None = None,
    ) -> dict[str, Any]:
        resp = self._client.post(path, headers=self._headers(extra_betas), json=body)
        if resp.is_success:
            return resp.json()  # type: ignore[no-any-return]
        raise ManagedAgentError.from_response(resp)

    def _delete(self, path: str) -> None:
        resp = self._client.delete(path, headers=self._headers())
        if not resp.is_success:
            raise ManagedAgentError.from_response(resp)

    # ------------------------------------------------------------------
    # Agent operations
    # ------------------------------------------------------------------

    def create_agent(self, config: dict[str, Any]) -> str:
        """Create a new agent configuration.

        Args:
            config: Must include 'name' and 'model' at minimum.
                    Optional: system, tools, mcp_servers, skills, description, metadata.

        Returns:
            The agent ID string (e.g. 'agent_01HqR2k7vXbZ9mNpL3wYcT8f').
        """
        required = ["name", "model"]
        for key in required:
            if key not in config:
                raise ValueError(f"Missing required field: {key}")

        # Normalize model to object form if passed as string
        body = dict(config)
        if isinstance(body.get("model"), str):
            body["model"] = {"id": body["model"], "speed": "standard"}

        resp = self._post("/v1/agents", body)
        return str(resp["id"])

    def retrieve_agent(self, agent_id: str) -> dict[str, Any]:
        """Get agent details by ID."""
        return self._get(f"/v1/agents/{agent_id}")

    def update_agent(self, agent_id: str, updates: dict[str, Any]) -> dict[str, Any]:
        """Update an agent. Generates a new version if config changes."""
        # Pass current version for optimistic concurrency
        if "version" not in updates:
            current = self.retrieve_agent(agent_id)
            updates["version"] = current["version"]
        return self._post(f"/v1/agents/{agent_id}", updates)

    def list_agents(self, limit: int = 20) -> list[dict[str, Any]]:
        """List agent configurations."""
        resp = self._get(f"/v1/agents?limit={limit}")
        return list(resp.get("data", []))

    def archive_agent(self, agent_id: str) -> dict[str, Any]:
        """Archive an agent (permanent, irreversible)."""
        return self._post(f"/v1/agents/{agent_id}/archive", {})

    # ------------------------------------------------------------------
    # Environment operations
    # ------------------------------------------------------------------

    def create_environment(self, config: dict[str, Any]) -> str:
        """Create an execution environment.

        Args:
            config: Must include 'name' and 'config' fields.

        Returns:
            The environment ID string.
        """
        if "name" not in config:
            raise ValueError("Missing required field: name")
        resp = self._post("/v1/environments", config)
        return str(resp["id"])

    def retrieve_environment(self, environment_id: str) -> dict[str, Any]:
        """Get environment details."""
        return self._get(f"/v1/environments/{environment_id}")

    def list_environments(self, limit: int = 20) -> list[dict[str, Any]]:
        """List environments."""
        resp = self._get(f"/v1/environments?limit={limit}")
        return list(resp.get("data", []))

    def delete_environment(self, environment_id: str) -> None:
        """Delete an environment."""
        self._delete(f"/v1/environments/{environment_id}")

    # ------------------------------------------------------------------
    # Session operations
    # ------------------------------------------------------------------

    def start_session(
        self,
        agent_id: str,
        task: str,
        *,
        environment_id: str | None = None,
        title: str | None = None,
        resources: list[dict[str, Any]] | None = None,
        vault_ids: list[str] | None = None,
    ) -> str:
        """Start a new session and send the initial task message.

        If no environment_id is provided, the client will try to find
        an available environment via list_environments().

        Args:
            agent_id: The agent to use for this session.
            task: The initial user message for the session.
            environment_id: Optional environment to run in.

        Returns:
            The session ID string.
        """
        if environment_id is None:
            envs = self.list_environments()
            if not envs:
                raise ValueError(
                    "No environment_id provided and no environments found. "
                    "Create one with create_environment() first."
                )
            # Use the most recently created environment
            envs.sort(
                key=lambda e: e.get("created_at", ""), reverse=True
            )
            environment_id = str(envs[0]["id"])

        body: dict[str, Any] = {
            "agent": agent_id,
            "environment_id": environment_id,
        }
        if title:
            body["title"] = title
        if resources:
            body["resources"] = resources
        if vault_ids:
            body["vault_ids"] = vault_ids

        resp = self._post("/v1/sessions", body)
        session_id = str(resp["id"])

        # Send the initial task message
        self._send_event(
            session_id,
            {
                "type": "user.message",
                "content": [{"type": "text", "text": task}],
            },
        )

        return session_id

    def _send_event(self, session_id: str, event: dict[str, Any]) -> dict[str, Any]:
        """Send a single event to a session."""
        return self._post(
            f"/v1/sessions/{session_id}/events",
            {"events": [event]},
        )

    def send_message(self, session_id: str, text: str) -> dict[str, Any]:
        """Send a follow-up message to a running session."""
        return self._send_event(
            session_id,
            {
                "type": "user.message",
                "content": [{"type": "text", "text": text}],
            },
        )

    def send_tool_result(
        self,
        session_id: str,
        tool_use_id: str,
        content: str,
        *,
        is_error: bool = False,
    ) -> dict[str, Any]:
        """Send a custom tool result back to the agent."""
        return self._send_event(
            session_id,
            {
                "type": "user.custom_tool_result",
                "custom_tool_use_id": tool_use_id,
                "content": [{"type": "text", "text": content}],
                "is_error": is_error,
            },
        )

    def define_outcome(
        self,
        session_id: str,
        description: str,
        rubric: str,
        *,
        max_iterations: int = 3,
    ) -> dict[str, Any]:
        """Define an outcome (with rubric) for the session.

        The agent will iterate until the rubric criteria are satisfied
        or max_iterations is reached.
        """
        return self._send_event(
            session_id,
            {
                "type": "user.define_outcome",
                "description": description,
                "rubric": {"type": "text", "content": rubric},
                "max_iterations": max_iterations,
            },
        )

    # ------------------------------------------------------------------
    # Session status & polling
    # ------------------------------------------------------------------

    def get_session_status(self, session_id: str) -> dict[str, Any]:
        """Get the current status of a session.

        Returns a dict with keys: id, status, agent, environment_id,
        created_at, updated_at, etc.

        Common status values: 'running', 'idle', 'archived', 'deleted'.
        """
        return self._get(f"/v1/sessions/{session_id}")

    def get_session_result(self, session_id: str) -> dict[str, Any]:
        """Get the complete session result including event history.

        This retrieves the session details (status, outcome_evaluations)
        and the full event list.
        """
        session = self.get_session_status(session_id)
        events = self.list_events(session_id)
        result: dict[str, Any] = {
            "session": session,
            "events": events,
        }
        return result

    def list_events(self, session_id: str, limit: int = 100) -> list[dict[str, Any]]:
        """List events for a session (paginated)."""
        resp = self._get(f"/v1/sessions/{session_id}/events?limit={limit}")
        return list(resp.get("data", []))

    def stream_events(self, session_id: str) -> Iterator[dict[str, Any]]:
        """Stream events via SSE from a session.

        Yields parsed JSON event objects as they arrive.

        Note: This is a blocking generator. For async usage, consider
        using httpx.AsyncClient with streaming.
        """
        url = f"{self._config.base_url}/v1/sessions/{session_id}/events/stream"
        with self._client.stream(
            "GET", url, headers=self._headers()
        ) as response:
            if not response.is_success:
                raise ManagedAgentError.from_response(response)
            for line in response.iter_lines():
                if not line:
                    continue
                # SSE format: "data: {...}" or "event: ..."
                if line.startswith("data: "):
                    data_str = line[6:]
                    if data_str == "[DONE]":
                        return
                    try:
                        yield json.loads(data_str)
                    except json.JSONDecodeError:
                        continue

    def wait_for_completion(
        self,
        session_id: str,
        max_wait_seconds: float = 600.0,
    ) -> dict[str, Any]:
        """Poll session status until idle/archived or timeout.

        Args:
            session_id: The session to wait on.
            max_wait_seconds: Maximum time to wait before raising timeout.

        Returns:
            The final session status dict.

        Raises:
            SessionTimeoutError: If session doesn't reach terminal state in time.
            SessionFailedError: If session encounters an error.
        """
        started = time.monotonic()
        interval = self._config.poll_interval

        while True:
            status = self.get_session_status(session_id)
            state = status.get("status", "unknown")

            if state in (SessionStatus.IDLE.value, SessionStatus.ARCHIVED.value):
                # Check for outcome evaluations
                return status

            if state == "failed":
                raise SessionFailedError(
                    f"Session {session_id} failed",
                    status_code=0,
                    error_type="session_failed",
                )

            elapsed = time.monotonic() - started
            if elapsed >= max_wait_seconds:
                raise SessionTimeoutError(
                    f"Session {session_id} did not complete within {max_wait_seconds}s",
                    status_code=0,
                    error_type="session_timeout",
                )

            # Exponential backoff: 2s, 4s, 8s, ..., capped at 30s
            time.sleep(min(interval, 30.0))
            interval *= 2

    # ------------------------------------------------------------------
    # Session lifecycle
    # ------------------------------------------------------------------

    def cancel_session(self, session_id: str) -> None:
        """Cancel a running session. Sends an interrupt event."""
        self._send_event(
            session_id,
            {"type": "user.interrupt"},
        )

    def archive_session(self, session_id: str) -> dict[str, Any]:
        """Archive a session (makes it read-only)."""
        return self._post(f"/v1/sessions/{session_id}/archive", {})

    def delete_session(self, session_id: str) -> None:
        """Delete a session permanently."""
        self._delete(f"/v1/sessions/{session_id}")

    def update_session(self, session_id: str, updates: dict[str, Any]) -> dict[str, Any]:
        """Update session metadata (e.g., title)."""
        return self._post(f"/v1/sessions/{session_id}", updates)

    def list_sessions(
        self,
        agent_id: str | None = None,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        """List sessions, optionally filtered by agent."""
        params = [f"limit={limit}"]
        if agent_id:
            params.append(f"agent_id={agent_id}")
        qs = "&".join(params)
        resp = self._get(f"/v1/sessions?{qs}")
        return list(resp.get("data", []))

    # ------------------------------------------------------------------
    # Memory Store operations
    # ------------------------------------------------------------------

    def create_memory_store(self, name: str, description: str = "") -> str:
        """Create a new memory store."""
        resp = self._post(
            "/v1/memory_stores",
            {"name": name, "description": description},
        )
        return str(resp["id"])

    def add_memory(self, store_id: str, path: str, content: str) -> dict[str, Any]:
        """Add a memory entry to a store."""
        return self._post(
            f"/v1/memory_stores/{store_id}/memories",
            {"path": path, "content": content},
        )

    def list_memory_stores(self, limit: int = 20) -> list[dict[str, Any]]:
        """List memory stores."""
        resp = self._get(f"/v1/memory_stores?limit={limit}")
        return list(resp.get("data", []))

    # ------------------------------------------------------------------
    # Dream operations
    # ------------------------------------------------------------------

    def create_dream(
        self,
        store_id: str,
        session_ids: list[str],
        *,
        model: str = "claude-sonnet-4-6",
        instructions: str = "",
    ) -> str:
        """Start a dreaming job.

        Args:
            store_id: Input memory store to reorganize.
            session_ids: Past session transcripts to mine (1-100).
            model: Model for the dreaming pipeline.
            instructions: Optional guidance for the dreaming run.

        Returns:
            The dream ID string.
        """
        if not session_ids:
            raise ValueError("At least one session_id is required")
        if len(session_ids) > 100:
            raise ValueError("Maximum 100 sessions per dream")

        resp = self._post(
            "/v1/dreams",
            {
                "inputs": [
                    {"type": "memory_store", "memory_store_id": store_id},
                    {"type": "sessions", "session_ids": session_ids},
                ],
                "model": model,
                "instructions": instructions,
            },
            extra_betas=[DREAMING_BETA],
        )
        return str(resp["id"])

    def get_dream_status(self, dream_id: str) -> dict[str, Any]:
        """Get the current status of a dream."""
        return self._get(f"/v1/dreams/{dream_id}", extra_betas=[DREAMING_BETA])

    def wait_for_dream(
        self,
        dream_id: str,
        max_wait_seconds: float = 600.0,
    ) -> dict[str, Any]:
        """Poll until a dream completes, fails, or is canceled."""
        started = time.monotonic()
        interval = self._config.poll_interval

        while True:
            dream = self.get_dream_status(dream_id)
            status = dream.get("status")

            if status in ("completed", "failed", "canceled"):
                return dream

            elapsed = time.monotonic() - started
            if elapsed >= max_wait_seconds:
                raise SessionTimeoutError(
                    f"Dream {dream_id} did not complete within {max_wait_seconds}s",
                    error_type="dream_timeout",
                )

            time.sleep(min(interval, 30.0))
            interval *= 2

    def cancel_dream(self, dream_id: str) -> dict[str, Any]:
        """Cancel a pending or running dream."""
        return self._post(
            f"/v1/dreams/{dream_id}/cancel",
            {},
            extra_betas=[DREAMING_BETA],
        )

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def close(self) -> None:
        """Release the underlying HTTP connection pool."""
        self._client.close()

    def __enter__(self) -> ManagedAgentClient:
        return self

    def __exit__(self, *args: Any) -> None:
        self.close()
