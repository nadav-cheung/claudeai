"""
Tests for the Chapter 1 Anthropic HTTP client.

These tests mock the httpx transport layer to avoid real network calls.
"""

from __future__ import annotations

import json
import os

import httpx
import pytest

from client import (
    AnthropicClient,
    AnthropicError,
    AsyncAnthropicClient,
    AuthMethod,
    ClientConfig,
    KeyRotator,
    _RequestBuilder,
    compute_retry_delay,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def sample_messages() -> list[dict]:
    return [{"role": "user", "content": [{"type": "text", "text": "Hello"}]}]


@pytest.fixture
def success_body() -> dict:
    return {
        "id": "msg_01Xxxxxxxxxxxxx",
        "type": "message",
        "role": "assistant",
        "content": [{"type": "text", "text": "Hi there!"}],
        "model": "claude-sonnet-4-20250514",
        "stop_reason": "end_turn",
        "stop_sequence": None,
        "usage": {"input_tokens": 5, "output_tokens": 3},
    }


def _mock_response(status_code: int, body: dict | str, headers: dict | None = None) -> httpx.Response:
    """Build a synthetic httpx.Response for testing."""
    if headers is None:
        headers = {}
    content = body if isinstance(body, str) else json.dumps(body)
    return httpx.Response(
        status_code=status_code,
        content=content.encode("utf-8"),
        headers=headers,
        request=httpx.Request("POST", "https://api.anthropic.com/v1/messages"),
    )


# ---------------------------------------------------------------------------
# ClientConfig
# ---------------------------------------------------------------------------

class TestClientConfig:
    def test_defaults_from_env(self, monkeypatch):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test-env")
        cfg = ClientConfig()
        assert cfg.api_key == "sk-test-env"
        assert cfg.auth_method == AuthMethod.API_KEY

    def test_explicit_api_key(self):
        cfg = ClientConfig(api_key="sk-explicit")
        assert cfg.api_key == "sk-explicit"

    def test_missing_key_raises(self, monkeypatch):
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        with pytest.raises(ValueError, match="api_key"):
            ClientConfig(api_key="")

    def test_custom_base_url(self):
        cfg = ClientConfig(api_key="sk-test", base_url="https://custom.example.com")
        assert cfg.base_url == "https://custom.example.com"

    def test_custom_auth_method(self):
        cfg = ClientConfig(api_key="sk-test", auth_method=AuthMethod.BEARER)
        assert cfg.auth_method == AuthMethod.BEARER


# ---------------------------------------------------------------------------
# _RequestBuilder
# ---------------------------------------------------------------------------

class TestRequestBuilder:
    def test_build_headers_api_key(self):
        headers = _RequestBuilder.build_headers("sk-test", AuthMethod.API_KEY, "2023-06-01")
        assert headers["x-api-key"] == "sk-test"
        assert headers["Content-Type"] == "application/json"
        assert headers["anthropic-version"] == "2023-06-01"
        assert "Authorization" not in headers

    def test_build_headers_bearer(self):
        headers = _RequestBuilder.build_headers("sk-test", AuthMethod.BEARER, "2023-06-01")
        assert headers["Authorization"] == "Bearer sk-test"
        assert "x-api-key" not in headers

    def test_build_body_minimal(self):
        body = _RequestBuilder.build_body(
            messages=[{"role": "user", "content": [{"type": "text", "text": "Hi"}]}],
            model="claude-sonnet-4-20250514",
            max_tokens=100,
        )
        assert body["model"] == "claude-sonnet-4-20250514"
        assert body["max_tokens"] == 100
        assert "system" not in body

    def test_build_body_with_system(self):
        body = _RequestBuilder.build_body(
            messages=[],
            model="claude-sonnet-4-20250514",
            max_tokens=1,
            system="You are helpful.",
        )
        assert body["system"] == "You are helpful."

    def test_build_body_drops_none_optional_fields(self):
        body = _RequestBuilder.build_body(
            messages=[],
            model="m",
            max_tokens=1,
            temperature=None,
            top_p=None,
        )
        assert "temperature" not in body
        assert "top_p" not in body


# ---------------------------------------------------------------------------
# AnthropicError
# ---------------------------------------------------------------------------

class TestAnthropicError:
    def test_from_response_valid_json(self):
        resp = _mock_response(
            401,
            {"type": "error", "error": {"type": "authentication_error", "message": "bad key"}},
        )
        err = AnthropicError.from_response(resp)
        assert err.status_code == 401
        assert err.error_type == "authentication_error"
        assert "bad key" in str(err)

    def test_from_response_non_json_body(self):
        resp = _mock_response(500, "Internal Server Error")
        err = AnthropicError.from_response(resp)
        assert err.status_code == 500
        assert err.error_type is None

    @pytest.mark.parametrize(
        "status_code,error_type,expected",
        [
            (400, "invalid_request_error", False),
            (401, "authentication_error", False),
            (403, "permission_error", False),
            (404, "not_found_error", False),
            (413, "request_too_large", False),
            (429, "rate_limit_error", True),
            (500, "api_error", True),
            (529, "overloaded_error", True),
        ],
    )
    def test_is_retryable(self, status_code, error_type, expected):
        err = AnthropicError(message="test", status_code=status_code, error_type=error_type)
        assert err.is_retryable == expected


# ---------------------------------------------------------------------------
# KeyRotator
# ---------------------------------------------------------------------------

class TestKeyRotator:
    def test_round_robin(self):
        kr = KeyRotator(["key-a", "key-b", "key-c"])
        seen = {kr.next_key() for _ in range(3)}
        assert seen == {"key-a", "key-b", "key-c"}

    def test_marks_failed_key(self):
        kr = KeyRotator(["key-a", "key-b"])
        kr.mark_failed("key-a")
        # Should only ever return key-b now.
        for _ in range(5):
            assert kr.next_key() == "key-b"

    def test_all_keys_failed_raises(self):
        kr = KeyRotator(["key-a"])
        kr.mark_failed("key-a")
        with pytest.raises(AnthropicError, match="All API keys"):
            kr.next_key()

    def test_add_key(self):
        kr = KeyRotator(["key-a"])
        kr.add_key("key-b")
        seen = {kr.next_key() for _ in range(2)}
        assert seen == {"key-a", "key-b"}

    def test_remove_key(self):
        kr = KeyRotator(["key-a", "key-b"])
        kr.remove_key("key-a")
        for _ in range(5):
            assert kr.next_key() == "key-b"

    def test_empty_keys_raises(self):
        with pytest.raises(ValueError, match="At least one"):
            KeyRotator([])

    def test_active_count(self):
        kr = KeyRotator(["a", "b", "c"])
        assert kr.active_count == 3
        kr.mark_failed("a")
        assert kr.active_count == 2


# ---------------------------------------------------------------------------
# compute_retry_delay
# ---------------------------------------------------------------------------

class TestComputeRetryDelay:
    def test_exponential_backoff(self):
        d1 = compute_retry_delay(1, base_delay=1.0)
        d2 = compute_retry_delay(2, base_delay=1.0)
        d3 = compute_retry_delay(3, base_delay=1.0)
        # Base: 1, 2, 4 (plus jitter up to 25%)
        assert 1.0 <= d1 < 1.3
        assert 2.0 <= d2 < 2.6
        assert 4.0 <= d3 < 5.2

    def test_uses_retry_after_header(self):
        resp = _mock_response(429, {}, headers={"retry-after": "42"})
        assert compute_retry_delay(1, resp) == 42.0


# ---------------------------------------------------------------------------
# AnthropicClient (sync) - mocked transport
# ---------------------------------------------------------------------------

class TestAnthropicClient:
    def test_successful_request(self, sample_messages, success_body):
        def _handler(request: httpx.Request) -> httpx.Response:
            return _mock_response(200, success_body)

        with httpx.Client(transport=httpx.MockTransport(_handler)) as http:
            client = AnthropicClient(config=ClientConfig(api_key="sk-test"))
            client._client = http
            result = client.post(
                messages=sample_messages,
                model="claude-sonnet-4-20250514",
                max_tokens=100,
            )
        assert result["id"] == "msg_01Xxxxxxxxxxxxx"
        assert result["type"] == "message"

    def test_auth_error_no_retry(self, sample_messages):
        call_count = 0

        def _handler(request: httpx.Request) -> httpx.Response:
            nonlocal call_count
            call_count += 1
            return _mock_response(
                401,
                {"type": "error", "error": {"type": "authentication_error", "message": "bad key"}},
            )

        with httpx.Client(transport=httpx.MockTransport(_handler)) as http:
            client = AnthropicClient(config=ClientConfig(api_key="sk-test"))
            client._client = http
            with pytest.raises(AnthropicError) as exc_info:
                client.post(
                    messages=sample_messages,
                    model="claude-sonnet-4-20250514",
                    max_tokens=100,
                    max_retries=2,
                )
            assert exc_info.value.status_code == 401
            assert exc_info.value.error_type == "authentication_error"
        # 401 should NOT be retried.
        assert call_count == 1

    def test_429_is_retried(self, sample_messages, success_body):
        call_count = 0

        def _handler(request: httpx.Request) -> httpx.Response:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return _mock_response(
                    429,
                    {"type": "error", "error": {"type": "rate_limit_error", "message": "slow down"}},
                    headers={"retry-after": "0.01"},
                )
            return _mock_response(200, success_body)

        with httpx.Client(transport=httpx.MockTransport(_handler)) as http:
            client = AnthropicClient(config=ClientConfig(api_key="sk-test"))
            client._client = http
            result = client.post(
                messages=sample_messages,
                model="claude-sonnet-4-20250514",
                max_tokens=100,
                max_retries=3,
            )
        assert result["type"] == "message"
        assert call_count == 2

    def test_500_is_retried(self, sample_messages, success_body):
        call_count = 0

        def _handler(request: httpx.Request) -> httpx.Response:
            nonlocal call_count
            call_count += 1
            if call_count <= 2:
                return _mock_response(500, {"type": "error", "error": {"type": "api_error", "message": "boom"}})
            return _mock_response(200, success_body)

        with httpx.Client(transport=httpx.MockTransport(_handler)) as http:
            client = AnthropicClient(config=ClientConfig(api_key="sk-test"))
            client._client = http
            result = client.post(
                messages=sample_messages,
                model="claude-sonnet-4-20250514",
                max_tokens=100,
                max_retries=3,
            )
        assert result["type"] == "message"
        assert call_count == 3

    def test_max_retries_exhausted(self, sample_messages):
        call_count = 0

        def _handler(request: httpx.Request) -> httpx.Response:
            nonlocal call_count
            call_count += 1
            return _mock_response(500, {"type": "error", "error": {"type": "api_error", "message": "boom"}})

        with httpx.Client(transport=httpx.MockTransport(_handler)) as http:
            client = AnthropicClient(config=ClientConfig(api_key="sk-test"))
            client._client = http
            with pytest.raises(AnthropicError) as exc_info:
                client.post(
                    messages=sample_messages,
                    model="claude-sonnet-4-20250514",
                    max_tokens=100,
                    max_retries=2,
                )
        # Initial + 2 retries = 3 total calls.
        assert call_count == 3

    def test_400_not_retried(self, sample_messages):
        call_count = 0

        def _handler(request: httpx.Request) -> httpx.Response:
            nonlocal call_count
            call_count += 1
            return _mock_response(
                400,
                {"type": "error", "error": {"type": "invalid_request_error", "message": "bad request"}},
            )

        with httpx.Client(transport=httpx.MockTransport(_handler)) as http:
            client = AnthropicClient(config=ClientConfig(api_key="sk-test"))
            client._client = http
            with pytest.raises(AnthropicError) as exc_info:
                client.post(
                    messages=sample_messages,
                    model="claude-sonnet-4-20250514",
                    max_tokens=100,
                    max_retries=3,
                )
            assert exc_info.value.status_code == 400
        assert call_count == 1

    def test_post_with_retry_convenience(self, sample_messages, success_body):
        def _handler(request: httpx.Request) -> httpx.Response:
            return _mock_response(200, success_body)

        with httpx.Client(transport=httpx.MockTransport(_handler)) as http:
            client = AnthropicClient(config=ClientConfig(api_key="sk-test"))
            client._client = http
            result = client.post_with_retry(
                messages=sample_messages,
                model="claude-sonnet-4-20250514",
                max_tokens=100,
            )
        assert result["type"] == "message"

    def test_key_rotation_marks_401_failed(self, sample_messages, success_body):
        call_count = 0

        def _handler(request: httpx.Request) -> httpx.Response:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return _mock_response(401, {"type": "error", "error": {"type": "authentication_error", "message": "bad"}})
            return _mock_response(200, success_body)

        with httpx.Client(transport=httpx.MockTransport(_handler)) as http:
            client = AnthropicClient(
                config=ClientConfig(api_key="sk-test"),
                keys=["key-bad", "key-good"],
            )
            client._client = http
            result = client.post(
                messages=sample_messages,
                model="claude-sonnet-4-20250514",
                max_tokens=100,
                max_retries=0,
            )
        assert result["type"] == "message"
        assert client._key_rotator.active_count == 1


# ---------------------------------------------------------------------------
# AnthropicClient context manager
# ---------------------------------------------------------------------------

class TestAnthropicClientContextManager:
    def test_context_manager(self):
        with AnthropicClient(config=ClientConfig(api_key="sk-test")) as client:
            assert isinstance(client, AnthropicClient)


# ---------------------------------------------------------------------------
# AsyncAnthropicClient - mocked transport
# ---------------------------------------------------------------------------

class TestAsyncAnthropicClient:
    @pytest.mark.anyio
    async def test_successful_request(self, sample_messages, success_body):
        def _handler(request: httpx.Request) -> httpx.Response:
            return _mock_response(200, success_body)

        async with httpx.AsyncClient(transport=httpx.MockTransport(_handler)) as http:
            client = AsyncAnthropicClient(config=ClientConfig(api_key="sk-test"))
            client._client = http
            result = await client.post(
                messages=sample_messages,
                model="claude-sonnet-4-20250514",
                max_tokens=100,
            )
        assert result["id"] == "msg_01Xxxxxxxxxxxxx"

    @pytest.mark.anyio
    async def test_error_response(self, sample_messages):
        def _handler(request: httpx.Request) -> httpx.Response:
            return _mock_response(
                401,
                {"type": "error", "error": {"type": "authentication_error", "message": "nope"}},
            )

        async with httpx.AsyncClient(transport=httpx.MockTransport(_handler)) as http:
            client = AsyncAnthropicClient(config=ClientConfig(api_key="sk-test"))
            client._client = http
            with pytest.raises(AnthropicError) as exc_info:
                await client.post(
                    messages=sample_messages,
                    model="claude-sonnet-4-20250514",
                    max_tokens=100,
                )
            assert exc_info.value.status_code == 401

    @pytest.mark.anyio
    async def test_429_retry(self, sample_messages, success_body):
        call_count = 0

        def _handler(request: httpx.Request) -> httpx.Response:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return _mock_response(
                    429,
                    {"type": "error", "error": {"type": "rate_limit_error", "message": "wait"}},
                    headers={"retry-after": "0.01"},
                )
            return _mock_response(200, success_body)

        async with httpx.AsyncClient(transport=httpx.MockTransport(_handler)) as http:
            client = AsyncAnthropicClient(config=ClientConfig(api_key="sk-test"))
            client._client = http
            result = await client.post(
                messages=sample_messages,
                model="claude-sonnet-4-20250514",
                max_tokens=100,
                max_retries=2,
            )
        assert result["type"] == "message"
        assert call_count == 2

    @pytest.mark.anyio
    async def test_post_with_retry_convenience(self, sample_messages, success_body):
        def _handler(request: httpx.Request) -> httpx.Response:
            return _mock_response(200, success_body)

        async with httpx.AsyncClient(transport=httpx.MockTransport(_handler)) as http:
            client = AsyncAnthropicClient(config=ClientConfig(api_key="sk-test"))
            client._client = http
            result = await client.post_with_retry(
                messages=sample_messages,
                model="claude-sonnet-4-20250514",
                max_tokens=100,
            )
        assert result["type"] == "message"

    @pytest.mark.anyio
    async def test_async_context_manager(self):
        async with AsyncAnthropicClient(config=ClientConfig(api_key="sk-test")) as client:
            assert isinstance(client, AsyncAnthropicClient)
