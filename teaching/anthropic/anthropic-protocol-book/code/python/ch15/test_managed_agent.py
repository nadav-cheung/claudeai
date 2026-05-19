"""
Tests for the Chapter 15 Managed Agent client.

These tests mock the httpx transport layer to avoid real network calls.
Uses direct client._client replacement for simplicity and reliability.
"""

from __future__ import annotations

import json
import time

import httpx
import pytest

from managed_agent import (
    ManagedAgentClient,
    ManagedAgentConfig,
    ManagedAgentError,
    SessionFailedError,
    SessionTimeoutError,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def mock_client_with_handler(
    client: ManagedAgentClient,
    handler,
) -> ManagedAgentClient:
    """Replace client._client with a MockTransport-based client."""
    client._client = httpx.Client(
        base_url=client._config.base_url,
        transport=httpx.MockTransport(handler),
    )
    return client


def ok_json(body: dict) -> httpx.Response:
    """Return a 200 response with JSON body."""
    return httpx.Response(200, json=body)


def error_json(
    status_code: int,
    error_type: str,
    message: str,
    request_id: str | None = None,
) -> httpx.Response:
    headers = {}
    if request_id:
        headers["request-id"] = request_id
    return httpx.Response(
        status_code,
        json={
            "type": "error",
            "error": {"type": error_type, "message": message},
        },
        headers=headers,
    )


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def config() -> ManagedAgentConfig:
    return ManagedAgentConfig(api_key="test-key-001")


@pytest.fixture
def client(config: ManagedAgentConfig) -> ManagedAgentClient:
    return ManagedAgentClient(config=config)


@pytest.fixture
def agent_create_response():
    return {
        "id": "agent_01HqR2k7vXbZ9mNpL3wYcT8f",
        "type": "agent",
        "name": "Test Agent",
        "model": {"id": "claude-sonnet-4-6", "speed": "standard"},
        "system": "You are a test agent.",
        "version": 1,
        "created_at": "2026-04-03T18:24:10.412Z",
        "archived_at": None,
    }


@pytest.fixture
def env_create_response():
    return {
        "id": "env_01XyZAbCdEfGhIjKlMnOpQrSt",
        "type": "environment",
        "name": "Test Env",
        "created_at": "2026-04-03T18:00:00.000Z",
    }


# ---------------------------------------------------------------------------
# Agent operations
# ---------------------------------------------------------------------------

class TestAgentOperations:
    def test_create_agent_missing_required_fields(self, client):
        with pytest.raises(ValueError, match="Missing required field"):
            client.create_agent({"name": "NoModel"})

        with pytest.raises(ValueError, match="Missing required field"):
            client.create_agent({"model": "claude-sonnet-4-6"})

    def test_create_agent(self, client, agent_create_response):
        mock_client_with_handler(client, lambda req: ok_json(agent_create_response))
        agent_id = client.create_agent({
            "name": "Test Agent",
            "model": "claude-sonnet-4-6",
            "system": "You are a test agent.",
        })
        assert agent_id == "agent_01HqR2k7vXbZ9mNpL3wYcT8f"

    def test_retrieve_agent(self, client, agent_create_response):
        mock_client_with_handler(client, lambda req: ok_json(agent_create_response))
        agent = client.retrieve_agent("agent_01HqR2k7vXbZ9mNpL3wYcT8f")
        assert agent["name"] == "Test Agent"
        assert agent["version"] == 1

    def test_archive_agent(self, client, agent_create_response):
        resp = dict(agent_create_response)
        resp["archived_at"] = "2026-04-03T19:00:00.000Z"
        mock_client_with_handler(client, lambda req: ok_json(resp))
        result = client.archive_agent("agent_01HqR2k7vXbZ9mNpL3wYcT8f")
        assert result["archived_at"] is not None

    def test_list_agents(self, client, agent_create_response):
        mock_client_with_handler(
            client,
            lambda req: ok_json({"data": [agent_create_response]}),
        )
        agents = client.list_agents()
        assert len(agents) == 1
        assert agents[0]["name"] == "Test Agent"


# ---------------------------------------------------------------------------
# Environment operations
# ---------------------------------------------------------------------------

class TestEnvironmentOperations:
    def test_create_environment_missing_name(self, client):
        with pytest.raises(ValueError, match="Missing required field"):
            client.create_environment({"config": {"type": "cloud"}})

    def test_create_environment(self, client, env_create_response):
        mock_client_with_handler(client, lambda req: ok_json(env_create_response))
        env_id = client.create_environment({
            "name": "Test Env",
            "config": {"type": "cloud", "networking": {"type": "unrestricted"}},
        })
        assert env_id.startswith("env_")

    def test_list_environments(self, client, env_create_response):
        mock_client_with_handler(
            client,
            lambda req: ok_json({"data": [env_create_response]}),
        )
        envs = client.list_environments()
        assert len(envs) == 1

    def test_delete_environment(self, client):
        mock_client_with_handler(client, lambda req: httpx.Response(204))
        client.delete_environment("env_test")  # should not raise


# ---------------------------------------------------------------------------
# Session operations
# ---------------------------------------------------------------------------

class TestSessionOperations:
    def test_start_session_no_environment(self, client):
        """When no env_id provided, should list envs and use latest."""
        calls = []

        def handler(req):
            calls.append(str(req.url))
            url_str = str(req.url)
            if "/v1/environments" in url_str:
                return ok_json({
                    "data": [
                        {"id": "env_new", "name": "New", "created_at": "2026-04-03T19:00:00Z"},
                        {"id": "env_old", "name": "Old", "created_at": "2026-04-03T18:00:00Z"},
                    ]
                })
            elif url_str.endswith("/v1/sessions"):
                return ok_json({"id": "sesn_test", "status": "created"})
            elif "/events" in url_str and url_str.endswith("/events"):
                return ok_json({"id": "evt_ok"})
            return httpx.Response(404, json={"error": {"message": "?"}})

        mock_client_with_handler(client, handler)
        session_id = client.start_session("agent_123", "Do something")
        assert session_id == "sesn_test"

    def test_get_session_status(self, client):
        status_body = {
            "id": "sesn_test",
            "status": "running",
            "agent_id": "agent_123",
        }
        mock_client_with_handler(client, lambda req: ok_json(status_body))
        status = client.get_session_status("sesn_test")
        assert status["status"] == "running"

    def test_get_session_result(self, client):
        call_count = [0]

        def handler(req):
            call_count[0] += 1
            if "events" in req.url.path:
                return ok_json({
                    "data": [{"type": "user.message", "content": [{"type": "text", "text": "Hello"}]}]
                })
            return ok_json({"id": "sesn_test", "status": "idle", "outcome_evaluations": []})

        mock_client_with_handler(client, handler)
        result = client.get_session_result("sesn_test")
        assert "session" in result
        assert "events" in result
        assert result["session"]["status"] == "idle"
        assert len(result["events"]) == 1

    def test_send_message(self, client):
        mock_client_with_handler(
            client,
            lambda req: ok_json({
                "id": "evt_002", "type": "user.message",
                "content": [{"type": "text", "text": "Follow-up"}],
            }),
        )
        resp = client.send_message("sesn_test", "Follow-up")
        assert resp["type"] == "user.message"

    def test_send_tool_result(self, client):
        mock_client_with_handler(
            client,
            lambda req: ok_json({"id": "evt_003", "type": "user.custom_tool_result"}),
        )
        resp = client.send_tool_result("sesn_test", "sevt_abc", "Result data")
        assert resp["type"] == "user.custom_tool_result"

    def test_define_outcome(self, client):
        mock_client_with_handler(
            client,
            lambda req: ok_json({"id": "evt_outcome", "type": "user.define_outcome"}),
        )
        rubric = "# Test\n- Criterion 1\n- Criterion 2"
        resp = client.define_outcome("sesn_test", "Test task", rubric, max_iterations=3)
        assert resp["type"] == "user.define_outcome"

    def test_list_sessions_filtered(self, client):
        mock_client_with_handler(
            client,
            lambda req: ok_json({
                "data": [
                    {"id": "sesn_1", "agent_id": "agent_123", "status": "idle"},
                    {"id": "sesn_2", "agent_id": "agent_123", "status": "archived"},
                ]
            }),
        )
        sessions = client.list_sessions(agent_id="agent_123")
        assert len(sessions) == 2
        assert sessions[0]["agent_id"] == "agent_123"


# ---------------------------------------------------------------------------
# Wait / poll
# ---------------------------------------------------------------------------

class TestWaitForCompletion:
    def test_wait_completes_when_idle(self, client):
        mock_client_with_handler(
            client,
            lambda req: ok_json({"id": "sesn_test", "status": "idle"}),
        )
        result = client.wait_for_completion("sesn_test")
        assert result["status"] == "idle"

    def test_wait_polls_until_idle(self, client):
        states = ["running", "running", "idle"]
        call_count = [0]

        def handler(req):
            idx = min(call_count[0], len(states) - 1)
            call_count[0] += 1
            return ok_json({"id": "sesn_test", "status": states[idx]})

        client._config.poll_interval = 0.01
        mock_client_with_handler(client, handler)
        result = client.wait_for_completion("sesn_test", max_wait_seconds=10)
        assert result["status"] == "idle"
        assert call_count[0] >= 3

    def test_wait_timeout(self, client):
        client._config.poll_interval = 0.01
        mock_client_with_handler(
            client,
            lambda req: ok_json({"id": "sesn_test", "status": "running"}),
        )
        with pytest.raises(SessionTimeoutError):
            client.wait_for_completion("sesn_test", max_wait_seconds=0.05)


# ---------------------------------------------------------------------------
# Session lifecycle
# ---------------------------------------------------------------------------

class TestSessionLifecycle:
    def test_cancel_session(self, client):
        mock_client_with_handler(
            client,
            lambda req: ok_json({"id": "evt_int", "type": "user.interrupt"}),
        )
        client.cancel_session("sesn_test")  # should not raise

    def test_delete_session(self, client):
        mock_client_with_handler(client, lambda req: httpx.Response(204))
        client.delete_session("sesn_test")  # should not raise

    def test_archive_session(self, client):
        mock_client_with_handler(
            client,
            lambda req: ok_json({
                "id": "sesn_test",
                "archived_at": "2026-04-03T20:00:00Z",
            }),
        )
        result = client.archive_session("sesn_test")
        assert result["archived_at"] is not None

    def test_update_session(self, client):
        mock_client_with_handler(
            client,
            lambda req: ok_json({"id": "sesn_test", "title": "New Title"}),
        )
        result = client.update_session("sesn_test", {"title": "New Title"})
        assert result["title"] == "New Title"


# ---------------------------------------------------------------------------
# Memory Store operations
# ---------------------------------------------------------------------------

class TestMemoryStoreOperations:
    def test_create_memory_store(self, client):
        mock_client_with_handler(
            client,
            lambda req: ok_json({"id": "memstore_01HxAbCdEf", "name": "Test Store"}),
        )
        store_id = client.create_memory_store("Test Store", "Test description")
        assert store_id.startswith("memstore_")

    def test_add_memory(self, client):
        mock_client_with_handler(
            client,
            lambda req: ok_json({
                "id": "mem_01AbCdEfGh",
                "path": "/preferences/test.md",
                "content": "Test content",
            }),
        )
        mem = client.add_memory("memstore_01", "/preferences/test.md", "Test content")
        assert mem["path"] == "/preferences/test.md"

    def test_list_memory_stores(self, client):
        mock_client_with_handler(
            client,
            lambda req: ok_json({
                "data": [
                    {"id": "memstore_01", "name": "Store 1"},
                    {"id": "memstore_02", "name": "Store 2"},
                ]
            }),
        )
        stores = client.list_memory_stores()
        assert len(stores) == 2


# ---------------------------------------------------------------------------
# Dream operations
# ---------------------------------------------------------------------------

class TestDreamOperations:
    def test_create_dream_requires_sessions(self, client):
        with pytest.raises(ValueError, match="At least one session_id"):
            client.create_dream("memstore_01", [])

    def test_create_dream_session_limit(self, client):
        with pytest.raises(ValueError, match="Maximum 100 sessions"):
            client.create_dream("memstore_01", [f"sesn_{i}" for i in range(101)])

    def test_create_dream_success(self, client):
        mock_client_with_handler(
            client,
            lambda req: ok_json({
                "id": "drm_01AbCDefGhIjKlMnOpQrStUv",
                "type": "dream",
                "status": "pending",
            }),
        )
        dream_id = client.create_dream("memstore_01", ["sesn_1", "sesn_2"])
        assert dream_id.startswith("drm_")

    def test_get_dream_status(self, client):
        mock_client_with_handler(
            client,
            lambda req: ok_json({
                "id": "drm_01",
                "status": "running",
                "usage": {"input_tokens": 1000, "output_tokens": 200},
            }),
        )
        status = client.get_dream_status("drm_01")
        assert status["status"] == "running"

    def test_wait_for_dream_complete(self, client):
        client._config.poll_interval = 0.01
        mock_client_with_handler(
            client,
            lambda req: ok_json({
                "id": "drm_01",
                "status": "completed",
                "outputs": [{"type": "memory_store", "memory_store_id": "memstore_new"}],
            }),
        )
        result = client.wait_for_dream("drm_01")
        assert result["status"] == "completed"

    def test_cancel_dream(self, client):
        mock_client_with_handler(
            client,
            lambda req: ok_json({"id": "drm_01", "status": "canceled"}),
        )
        result = client.cancel_dream("drm_01")
        assert result["status"] == "canceled"


# ---------------------------------------------------------------------------
# Error handling
# ---------------------------------------------------------------------------

class TestErrorHandling:
    def test_managed_agent_error_from_response(self):
        resp = httpx.Response(
            429,
            json={
                "type": "error",
                "error": {"type": "rate_limit_error", "message": "Rate limit exceeded"},
            },
            headers={"request-id": "req_abc123"},
        )
        error = ManagedAgentError.from_response(resp)
        assert error.status_code == 429
        assert error.error_type == "rate_limit_error"
        assert error.request_id == "req_abc123"

    def test_error_from_non_json_response(self):
        resp = httpx.Response(500, content=b"Internal Server Error")
        error = ManagedAgentError.from_response(resp)
        assert error.status_code == 500
        assert error.error_type is None

    def test_http_error_propagates(self, client):
        mock_client_with_handler(
            client,
            lambda req: error_json(401, "authentication_error", "Invalid API key"),
        )
        with pytest.raises(ManagedAgentError) as exc_info:
            client.retrieve_agent("agent_nonexistent")
        assert exc_info.value.status_code == 401
        assert exc_info.value.error_type == "authentication_error"


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

class TestConfiguration:
    def test_missing_api_key_raises(self):
        import os

        old = os.environ.pop("ANTHROPIC_API_KEY", None)
        try:
            with pytest.raises(ValueError, match="api_key"):
                ManagedAgentConfig()
        finally:
            if old is not None:
                os.environ["ANTHROPIC_API_KEY"] = old

    def test_config_defaults(self):
        config = ManagedAgentConfig(api_key="test-key", base_url="https://api.anthropic.com")
        assert config.base_url == "https://api.anthropic.com"
        assert config.api_version == "2023-06-01"
        assert config.timeout == 120.0
        assert config.poll_interval == 2.0

    def test_client_context_manager(self, config):
        with ManagedAgentClient(config=config) as c:
            assert c._config.api_key == "test-key-001"
        # Close the client opened inside the context manager
        # (it was already closed by __exit__)
