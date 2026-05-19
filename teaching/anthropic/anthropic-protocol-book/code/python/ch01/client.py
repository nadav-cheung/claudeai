"""
Chapter 1: Anthropic API HTTP Client.

A dependency-free implementation of the Anthropic Messages API client,
supporting both synchronous and asynchronous usage patterns.
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

import httpx


# ---------------------------------------------------------------------------
# Enums & Constants
# ---------------------------------------------------------------------------

class AuthMethod(Enum):
    """Authentication strategy for the Anthropic API."""

    API_KEY = "api-key"  # x-api-key header
    BEARER = "bearer"  # Authorization: Bearer header


DEFAULT_BASE_URL = "https://api.anthropic.com/v1/messages"
DEFAULT_API_VERSION = "2023-06-01"
DEFAULT_TIMEOUT = 60.0
DEFAULT_MAX_RETRIES = 3

# Error types that warrant a retry (transient failures).
RETRYABLE_ERROR_TYPES: frozenset[str] = frozenset({
    "rate_limit_error",
    "api_error",
    "overloaded_error",
})

# HTTP status codes that warrant a retry.
RETRYABLE_STATUS_CODES: frozenset[int] = frozenset({429, 500, 529})


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------

class AnthropicError(Exception):
    """Structured error raised for all Anthropic API failures."""

    def __init__(
        self,
        message: str,
        *,
        status_code: int,
        error_type: str | None = None,
        request_id: str | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.error_type = error_type
        self.request_id = request_id

    @classmethod
    def from_response(cls, response: httpx.Response) -> AnthropicError:
        """Parse an HTTP response body into an AnthropicError."""
        status_code = response.status_code
        error_type = None
        message = f"HTTP {status_code}"

        try:
            body = response.json()
        except (json.JSONDecodeError, ValueError):
            # Body is not valid JSON; construct a minimal error.
            return cls(message, status_code=status_code)

        if isinstance(body, dict) and "error" in body:
            err = body["error"]
            if isinstance(err, dict):
                error_type = err.get("type")
                message = err.get("message", message)

        request_id = response.headers.get("request-id")
        return cls(message, status_code=status_code, error_type=error_type, request_id=request_id)

    @property
    def is_retryable(self) -> bool:
        """Whether this error indicates a transient condition worth retrying."""
        return (
            self.status_code in RETRYABLE_STATUS_CODES
            or self.error_type in RETRYABLE_ERROR_TYPES
        )


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

@dataclass
class ClientConfig:
    """Immutable-ish configuration for the Anthropic client.

    All optional fields fall back to environment variables or sensible defaults,
    so the common case of reading a single API key from the environment requires
    zero configuration.
    """

    api_key: str = field(
        default_factory=lambda: os.environ.get("ANTHROPIC_API_KEY", "")
    )
    auth_method: AuthMethod = AuthMethod.API_KEY
    base_url: str = field(
        default_factory=lambda: os.environ.get("ANTHROPIC_BASE_URL", DEFAULT_BASE_URL)
    )
    api_version: str = DEFAULT_API_VERSION
    timeout: float = DEFAULT_TIMEOUT

    def __post_init__(self) -> None:
        if not self.api_key:
            raise ValueError(
                "api_key must be provided or set via ANTHROPIC_API_KEY environment variable"
            )


# ---------------------------------------------------------------------------
# Shared helpers (mixed into both sync and async clients via composition)
# ---------------------------------------------------------------------------

class _RequestBuilder:
    """Stateless helper that knows how to assemble HTTP requests."""

    @staticmethod
    def build_headers(
        api_key: str,
        auth_method: AuthMethod,
        api_version: str,
    ) -> dict[str, str]:
        """Build the HTTP headers required for an Anthropic API request."""
        headers: dict[str, str] = {
            "Content-Type": "application/json",
            "anthropic-version": api_version,
        }
        if auth_method == AuthMethod.API_KEY:
            headers["x-api-key"] = api_key
        else:
            headers["Authorization"] = f"Bearer {api_key}"
        return headers

    @staticmethod
    def build_body(
        messages: list[dict[str, Any]],
        model: str,
        max_tokens: int,
        *,
        system: str | None = None,
        stop_sequences: list[str] | None = None,
        temperature: float | None = None,
        top_p: float | None = None,
        top_k: int | None = None,
        tools: list[dict[str, Any]] | None = None,
        metadata: dict[str, Any] | None = None,
        output_config: dict[str, Any] | None = None,
        thinking: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Assemble the JSON request body, dropping None-valued optional fields."""
        body: dict[str, Any] = {
            "model": model,
            "max_tokens": max_tokens,
            "messages": messages,
        }
        if system is not None:
            body["system"] = system
        if stop_sequences is not None:
            body["stop_sequences"] = stop_sequences
        if temperature is not None:
            body["temperature"] = temperature
        if top_p is not None:
            body["top_p"] = top_p
        if top_k is not None:
            body["top_k"] = top_k
        if tools is not None:
            body["tools"] = tools
        if metadata is not None:
            body["metadata"] = metadata
        if output_config is not None:
            body["output_config"] = output_config
        if thinking is not None:
            body["thinking"] = thinking
        return body


# ---------------------------------------------------------------------------
# Multi-Key Support
# ---------------------------------------------------------------------------

class KeyRotator:
    """Round-robin key rotation with automatic failure marking.

    When a key receives a 401 response it is presumed invalid and removed
    from the rotation pool. Other keys continue to be served.
    """

    def __init__(self, keys: list[str]) -> None:
        if not keys:
            raise ValueError("At least one API key is required")
        self._keys: list[str] = list(keys)
        self._failed: set[str] = set()

    def next_key(self) -> str:
        """Return the next available key, skipping failed ones."""
        available = [k for k in self._keys if k not in self._failed]
        if not available:
            raise AnthropicError(
                "All API keys have been marked as failed",
                status_code=0,
                error_type="key_rotation_exhausted",
            )
        # Round-robin across available keys using modulo.
        self._current_index: int = getattr(self, "_current_index", -1) + 1
        idx = self._current_index % len(available)
        return available[idx]

    def mark_failed(self, key: str) -> None:
        """Remove a key from rotation (call on 401)."""
        self._failed.add(key)

    def add_key(self, key: str) -> None:
        """Add a new key to the rotation."""
        if key not in self._keys:
            self._keys.append(key)

    def remove_key(self, key: str) -> None:
        """Remove a key entirely from the pool."""
        self._keys = [k for k in self._keys if k != key]
        self._failed.discard(key)

    @property
    def active_count(self) -> int:
        """Number of keys currently considered valid."""
        return len(self._keys) - len(self._failed)


# ---------------------------------------------------------------------------
# Retry Logic
# ---------------------------------------------------------------------------

def compute_retry_delay(
    attempt: int,
    response: httpx.Response | None = None,
    *,
    base_delay: float = 1.0,
) -> float:
    """Calculate the delay before the next retry attempt.

    - If the response contains a Retry-After header that value is used directly.
    - Otherwise exponential backoff: base_delay * 2^(attempt-1) with jitter.
    """
    if response is not None:
        retry_after = response.headers.get("retry-after")
        if retry_after is not None:
            try:
                return float(retry_after)
            except (ValueError, TypeError):
                pass

    delay = base_delay * (2 ** (attempt - 1))
    # Add up to 25% jitter to avoid thundering-herd problems.
    jitter = delay * 0.25 * (hash(str(time.monotonic())) % 1000) / 1000.0  # noqa: S001
    return delay + jitter


def _is_retryable_response(status_code: int, error_type: str | None) -> bool:
    """Determine whether a response should trigger a retry."""
    if status_code in RETRYABLE_STATUS_CODES:
        return True
    if error_type in RETRYABLE_ERROR_TYPES:
        return True
    return False


# ---------------------------------------------------------------------------
# Synchronous Client
# ---------------------------------------------------------------------------

class AnthropicClient:
    """Synchronous HTTP client for the Anthropic Messages API.

    Usage::

        client = AnthropicClient()
        response = client.post(
            messages=[{"role": "user", "content": [{"type": "text", "text": "Hello"}]}],
            model="claude-sonnet-4-20250514",
            max_tokens=1024,
        )
    """

    def __init__(
        self,
        *,
        config: ClientConfig | None = None,
        api_key: str | None = None,
        keys: list[str] | None = None,
    ) -> None:
        self._config = config or ClientConfig(
            api_key=api_key or os.environ.get("ANTHROPIC_API_KEY", "")
        )
        self._headers = _RequestBuilder.build_headers(
            api_key=self._config.api_key,
            auth_method=self._config.auth_method,
            api_version=self._config.api_version,
        )
        self._client = httpx.Client(
            base_url=self._config.base_url,
            timeout=self._config.timeout,
            headers={"Content-Type": "application/json"},
        )
        self._key_rotator: KeyRotator | None = None
        if keys:
            self._key_rotator = KeyRotator(keys)

    def post(
        self,
        messages: list[dict[str, Any]],
        model: str,
        max_tokens: int,
        *,
        system: str | None = None,
        stop_sequences: list[str] | None = None,
        temperature: float | None = None,
        top_p: float | None = None,
        top_k: int | None = None,
        tools: list[dict[str, Any]] | None = None,
        metadata: dict[str, Any] | None = None,
        output_config: dict[str, Any] | None = None,
        thinking: dict[str, Any] | None = None,
        api_key: str | None = None,
        max_retries: int = 0,
    ) -> dict[str, Any]:
        """Send a request to the Messages API and return the parsed JSON response.

        Args:
            messages: List of message objects.
            model: Model identifier (e.g. "claude-sonnet-4-20250514").
            max_tokens: Hard cap on output tokens (required by the API).
            max_retries: Number of automatic retries for transient errors.

        Raises:
            AnthropicError: On any API-level or network error.
        """
        body = _RequestBuilder.build_body(
            messages=messages,
            model=model,
            max_tokens=max_tokens,
            system=system,
            stop_sequences=stop_sequences,
            temperature=temperature,
            top_p=top_p,
            top_k=top_k,
            tools=tools,
            metadata=metadata,
            output_config=output_config,
            thinking=thinking,
        )
        headers = self._resolve_headers(api_key)
        return self._request_with_retry("POST", "/", headers=headers, json=body, max_retries=max_retries)

    def post_with_retry(
        self,
        messages: list[dict[str, Any]],
        model: str,
        max_tokens: int,
        *,
        system: str | None = None,
        max_retries: int = DEFAULT_MAX_RETRIES,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Convenience wrapper that defaults to the standard retry count."""
        return self.post(
            messages=messages,
            model=model,
            max_tokens=max_tokens,
            system=system,
            max_retries=max_retries,
            **kwargs,
        )

    def _resolve_headers(self, override_key: str | None) -> dict[str, str]:
        """Determine the headers to use, accounting for key rotation."""
        if override_key is not None:
            return _RequestBuilder.build_headers(
                api_key=override_key,
                auth_method=self._config.auth_method,
                api_version=self._config.api_version,
            )
        if self._key_rotator is not None:
            key = self._key_rotator.next_key()
            return _RequestBuilder.build_headers(
                api_key=key,
                auth_method=self._config.auth_method,
                api_version=self._config.api_version,
            )
        return dict(self._headers)

    def _handle_401_for_rotation(self, headers: dict[str, str]) -> None:
        """If using key rotation and the request used a rotator-supplied key,
        mark it as failed so it is not used again."""
        if self._key_rotator is None:
            return
        key = headers.get("x-api-key") or _extract_bearer_key(headers)
        if key:
            self._key_rotator.mark_failed(key)

    def _request_with_retry(
        self,
        method: str,
        url: str,
        *,
        headers: dict[str, str],
        json: dict[str, Any],
        max_retries: int,
    ) -> dict[str, Any]:
        """Execute an HTTP request with optional retry logic."""
        # Resolve the full URL: combine base_url with the url path.
        # This is required when the client is replaced with a mock transport
        # that does not carry a base_url.
        full_url = self._config.base_url.rstrip("/") + "/" + url.lstrip("/")

        attempt = 0
        while True:
            attempt += 1
            try:
                response = self._client.request(method, full_url, headers=headers, json=json)
            except httpx.RequestError as exc:
                # Network-level errors (DNS, connection refused, timeout).
                if attempt <= max_retries:
                    time.sleep(compute_retry_delay(attempt))
                    continue
                raise AnthropicError(
                    f"Request failed after {attempt} attempts: {exc}",
                    status_code=0,
                    error_type="network_error",
                ) from exc

            if response.is_success:
                return response.json()

            error = AnthropicError.from_response(response)

            if response.status_code == 401 and self._key_rotator is not None:
                self._handle_401_for_rotation(headers)
                # Key rotation recovery: if another key is available,
                # retry with it. This is distinct from the standard retry
                # logic -- we are changing the auth context, not blindly
                # retrying the same request.
                # Do NOT consume a retry slot for this.
                if self._key_rotator.active_count > 0:
                    headers = self._resolve_headers(None)
                    continue

            can_retry = (
                attempt <= max_retries
                and _is_retryable_response(response.status_code, error.error_type)
            )

            if can_retry:
                delay = compute_retry_delay(attempt, response)
                time.sleep(delay)
                continue

            raise error

    def close(self) -> None:
        """Release the underlying HTTP connection pool."""
        self._client.close()

    def __enter__(self) -> AnthropicClient:
        return self

    def __exit__(self, *args: Any) -> None:
        self.close()


# ---------------------------------------------------------------------------
# Asynchronous Client
# ---------------------------------------------------------------------------

class AsyncAnthropicClient:
    """Asynchronous HTTP client for the Anthropic Messages API.

    Usage::

        async with AsyncAnthropicClient() as client:
            response = await client.post(
                messages=[{"role": "user", "content": [{"type": "text", "text": "Hello"}]}],
                model="claude-sonnet-4-20250514",
                max_tokens=1024,
            )
    """

    def __init__(
        self,
        *,
        config: ClientConfig | None = None,
        api_key: str | None = None,
        keys: list[str] | None = None,
    ) -> None:
        self._config = config or ClientConfig(
            api_key=api_key or os.environ.get("ANTHROPIC_API_KEY", "")
        )
        self._headers = _RequestBuilder.build_headers(
            api_key=self._config.api_key,
            auth_method=self._config.auth_method,
            api_version=self._config.api_version,
        )
        self._client = httpx.AsyncClient(
            base_url=self._config.base_url,
            timeout=self._config.timeout,
            headers={"Content-Type": "application/json"},
        )
        self._key_rotator: KeyRotator | None = None
        if keys:
            self._key_rotator = KeyRotator(keys)

    async def post(
        self,
        messages: list[dict[str, Any]],
        model: str,
        max_tokens: int,
        *,
        system: str | None = None,
        stop_sequences: list[str] | None = None,
        temperature: float | None = None,
        top_p: float | None = None,
        top_k: int | None = None,
        tools: list[dict[str, Any]] | None = None,
        metadata: dict[str, Any] | None = None,
        output_config: dict[str, Any] | None = None,
        thinking: dict[str, Any] | None = None,
        api_key: str | None = None,
        max_retries: int = 0,
    ) -> dict[str, Any]:
        """Send an asynchronous request to the Messages API."""
        body = _RequestBuilder.build_body(
            messages=messages,
            model=model,
            max_tokens=max_tokens,
            system=system,
            stop_sequences=stop_sequences,
            temperature=temperature,
            top_p=top_p,
            top_k=top_k,
            tools=tools,
            metadata=metadata,
            output_config=output_config,
            thinking=thinking,
        )
        headers = self._resolve_headers(api_key)
        return await self._request_with_retry(
            "POST", "/", headers=headers, json=body, max_retries=max_retries
        )

    async def post_with_retry(
        self,
        messages: list[dict[str, Any]],
        model: str,
        max_tokens: int,
        *,
        system: str | None = None,
        max_retries: int = DEFAULT_MAX_RETRIES,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Convenience wrapper with default retry count."""
        return await self.post(
            messages=messages,
            model=model,
            max_tokens=max_tokens,
            system=system,
            max_retries=max_retries,
            **kwargs,
        )

    def _resolve_headers(self, override_key: str | None) -> dict[str, str]:
        if override_key is not None:
            return _RequestBuilder.build_headers(
                api_key=override_key,
                auth_method=self._config.auth_method,
                api_version=self._config.api_version,
            )
        if self._key_rotator is not None:
            key = self._key_rotator.next_key()
            return _RequestBuilder.build_headers(
                api_key=key,
                auth_method=self._config.auth_method,
                api_version=self._config.api_version,
            )
        return dict(self._headers)

    def _handle_401_for_rotation(self, headers: dict[str, str]) -> None:
        if self._key_rotator is None:
            return
        key = headers.get("x-api-key") or _extract_bearer_key(headers)
        if key:
            self._key_rotator.mark_failed(key)

    async def _request_with_retry(
        self,
        method: str,
        url: str,
        *,
        headers: dict[str, str],
        json: dict[str, Any],
        max_retries: int,
    ) -> dict[str, Any]:
        last_exception: Exception | None = None
        full_url = self._config.base_url.rstrip("/") + "/" + url.lstrip("/")

        attempt = 0
        while True:
            attempt += 1
            try:
                response = await self._client.request(method, full_url, headers=headers, json=json)
            except httpx.RequestError as exc:
                if attempt <= max_retries:
                    await _async_sleep(compute_retry_delay(attempt))
                    continue
                raise AnthropicError(
                    f"Request failed after {attempt} attempts: {exc}",
                    status_code=0,
                    error_type="network_error",
                ) from exc

            if response.is_success:
                return response.json()

            error = AnthropicError.from_response(response)

            if response.status_code == 401 and self._key_rotator is not None:
                self._handle_401_for_rotation(headers)
                if self._key_rotator.active_count > 0:
                    headers = self._resolve_headers(None)
                    continue

            can_retry = (
                attempt <= max_retries
                and _is_retryable_response(response.status_code, error.error_type)
            )

            if can_retry:
                delay = compute_retry_delay(attempt, response)
                await _async_sleep(delay)
                last_exception = error
                continue

            raise error

    async def close(self) -> None:
        """Release the underlying async HTTP connection pool."""
        await self._client.aclose()

    async def __aenter__(self) -> AsyncAnthropicClient:
        return self

    async def __aexit__(self, *args: Any) -> None:
        await self.close()


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _extract_bearer_key(headers: dict[str, str]) -> str | None:
    """Extract the API key from a Bearer Authorization header."""
    auth = headers.get("Authorization", "")
    if auth.startswith("Bearer "):
        return auth[7:]
    return None


async def _async_sleep(seconds: float) -> None:
    """Async-compatible sleep."""
    import asyncio

    await asyncio.sleep(seconds)
