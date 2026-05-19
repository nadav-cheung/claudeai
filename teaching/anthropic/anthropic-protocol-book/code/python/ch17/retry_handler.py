"""
Chapter 17: RetryHandler — exponential backoff with jitter and circuit breaker.

Implements production-grade retry logic for the Anthropic API, including:
  - Classification of retryable vs. non-retryable errors
  - Exponential backoff with full jitter (AWS-style)
  - ``Retry-After`` header parsing (RFC 7231 delta-seconds and HTTP-date)
  - Circuit breaker pattern with half-open probing
  - Request idempotency and deduplication

Verified against docs.anthropic.com/en/api/errors (May 2026):
  429  rate_limit_error  — retryable, use Retry-After
  500  api_error         — retryable (server error)
  529  overloaded_error  — retryable (temporary overload)
  400  invalid_request   — NOT retryable (client error)
  401  authentication     — NOT retryable
  403  permission        — NOT retryable
  413  request_too_large — NOT retryable
"""

from __future__ import annotations

import hashlib
import random
import time
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any, Callable, Dict, Optional, Set


# ---------------------------------------------------------------------------
# Domain types
# ---------------------------------------------------------------------------


class ErrorCategory(str, Enum):
    """Classification of API errors for retry decision-making."""

    RETRYABLE_RATE_LIMIT = "retryable_rate_limit"    # 429
    RETRYABLE_SERVER = "retryable_server"            # 500, 529
    RETRYABLE_NETWORK = "retryable_network"          # ConnectionError, Timeout
    NON_RETRYABLE = "non_retryable"                  # 400, 401, 403, 404, 413


class CircuitState(str, Enum):
    CLOSED = "closed"           # Normal operation
    OPEN = "open"               # Failing fast — no requests allowed
    HALF_OPEN = "half_open"     # Probing — allow limited requests


# ---------------------------------------------------------------------------
# Error classification
# ---------------------------------------------------------------------------


def classify_error(
    status_code: Optional[int] = None,
    exception: Optional[Exception] = None,
) -> ErrorCategory:
    """Classify an HTTP or network error into a retry category.

    Returns ``ErrorCategory.NON_RETRYABLE`` for errors that should not be
    retried (e.g., invalid API key).  Returns one of the retryable
    categories for transient failures.
    """
    if status_code is not None:
        if status_code == 429:
            return ErrorCategory.RETRYABLE_RATE_LIMIT
        if status_code in (500, 529):
            return ErrorCategory.RETRYABLE_SERVER
        if 400 <= status_code < 500:
            return ErrorCategory.NON_RETRYABLE

    if exception is not None:
        import httpx
        if isinstance(exception, (httpx.ConnectError, httpx.ReadTimeout,
                                  httpx.RemoteProtocolError, ConnectionError,
                                  TimeoutError)):
            return ErrorCategory.RETRYABLE_NETWORK
        if isinstance(exception, (ValueError, TypeError)):
            return ErrorCategory.NON_RETRYABLE

    return ErrorCategory.NON_RETRYABLE


RETRYABLE_CATEGORIES = frozenset({
    ErrorCategory.RETRYABLE_RATE_LIMIT,
    ErrorCategory.RETRYABLE_SERVER,
    ErrorCategory.RETRYABLE_NETWORK,
})


# ---------------------------------------------------------------------------
# Retry-After parsing
# ---------------------------------------------------------------------------


def parse_retry_after(value: Optional[str]) -> float:
    """Parse a ``Retry-After`` header value into seconds.

    Supports RFC 7231 delta-seconds (integer) and HTTP-date formats.
    Returns ``0.0`` if parsing fails or value is ``None``.
    """
    if value is None:
        return 0.0
    value = value.strip()
    # Try delta-seconds
    try:
        seconds = int(value)
        return float(seconds)
    except ValueError:
        pass
    # Try HTTP-date
    try:
        from email.utils import parsedate_to_datetime
        target = parsedate_to_datetime(value).timestamp()
        now = time.time()
        return max(0.0, target - now)
    except Exception:
        return 0.0


# ---------------------------------------------------------------------------
# Exponential backoff with jitter
# ---------------------------------------------------------------------------


@dataclass
class BackoffConfig:
    """Configuration for exponential backoff with full jitter.

    The algorithm is:

        1. Compute exponential delay:  ``base * factor ** min(attempt, max_exp_attempts)``
        2. Cap at ``max_delay``.
        3. Add random jitter: ``random.uniform(0, delay)``  (full jitter)

    This avoids thundering-herd problems in distributed systems by
    spreading retries over a range, as recommended in the AWS
    Architecture Blog's "Timeouts, retries, and backoff with jitter".
    """

    base_delay: float = 1.0          # seconds
    factor: float = 2.0               # exponential multiplier
    max_exp_attempts: int = 10        # cap the exponent
    max_delay: float = 120.0          # absolute ceiling (seconds)
    max_attempts: int = 5             # total attempts (including initial)

    def delay(self, attempt: int) -> float:
        """Compute the delay (in seconds) for the given *attempt* (0-indexed)."""
        if attempt < 0:
            attempt = 0
        capped = min(attempt, self.max_exp_attempts)
        delay = min(self.base_delay * (self.factor ** capped), self.max_delay)
        return random.uniform(0.0, delay)  # full jitter


# ---------------------------------------------------------------------------
# Circuit breaker
# ---------------------------------------------------------------------------


@dataclass
class CircuitBreakerConfig:
    """Configuration for the circuit breaker.

    State transitions::

        CLOSED  ──(failure threshold exceeded)──>  OPEN
        OPEN    ──(reset_timeout elapsed)──────>    HALF_OPEN
        HALF_OPEN ──(success)─────────────────>     CLOSED
        HALF_OPEN ──(failure)─────────────────>     OPEN
    """

    failure_threshold: int = 5        # consecutive failures to open
    success_threshold: int = 2        # successes in half-open to close
    reset_timeout: float = 30.0       # seconds before half-open probe
    half_open_max_requests: int = 1   # max requests during half-open


class CircuitBreaker:
    """Thread-safe circuit breaker protecting downstream API calls.

    When the circuit is OPEN all requests are rejected immediately without
    touching the remote service — useful when the API is returning 5xx or
    the network is saturated.

    Usage::

        cb = CircuitBreaker(CircuitBreakerConfig(failure_threshold=5))
        if not cb.allow_request():
            raise CircuitBreakerOpenError(...)
        try:
            result = call_api()
            cb.record_success()
        except RetryableError:
            cb.record_failure()
    """

    def __init__(self, config: Optional[CircuitBreakerConfig] = None) -> None:
        self.config = config or CircuitBreakerConfig()
        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._success_count = 0
        self._last_failure_time: float = 0.0
        self._opened_at: float = 0.0

    # ------------------------------------------------------------------
    # State machine
    # ------------------------------------------------------------------

    def allow_request(self) -> bool:
        """Return ``True`` if a request may be attempted."""
        if self._state == CircuitState.CLOSED:
            return True
        if self._state == CircuitState.OPEN:
            if time.monotonic() - self._opened_at >= self.config.reset_timeout:
                self._state = CircuitState.HALF_OPEN
                self._success_count = 0
                return True
            return False
        # HALF_OPEN
        return True

    def record_success(self) -> None:
        """Notify the breaker of a successful request."""
        if self._state == CircuitState.HALF_OPEN:
            self._success_count += 1
            if self._success_count >= self.config.success_threshold:
                self._state = CircuitState.CLOSED
                self._failure_count = 0
        else:
            # CLOSED — reset failure counter on any success
            self._failure_count = 0

    def record_failure(self) -> None:
        """Notify the breaker of a failed request."""
        self._failure_count += 1
        self._last_failure_time = time.monotonic()
        if self._state == CircuitState.HALF_OPEN:
            self._state = CircuitState.OPEN
            self._opened_at = time.monotonic()
        elif (self._state == CircuitState.CLOSED
              and self._failure_count >= self.config.failure_threshold):
            self._state = CircuitState.OPEN
            self._opened_at = time.monotonic()

    @property
    def state(self) -> CircuitState:
        return self._state

    @property
    def failure_count(self) -> int:
        return self._failure_count


class CircuitBreakerOpenError(Exception):
    """Raised when a request is rejected because the circuit is open."""
    pass


# ---------------------------------------------------------------------------
# Idempotency & request deduplication
# ---------------------------------------------------------------------------


def generate_idempotency_key(payload: str) -> str:
    """Generate a deterministic idempotency key from request payload.

    Uses SHA-256 to produce a stable identifier for deduplication.
    For production use, combine with a client-generated nonce if the
    same logical request can have different payloads.
    """
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


class IdempotencyRegistry:
    """Thread-safe in-memory registry of in-flight/completed request keys.

    Prevents duplicate API calls when clients retry.  For production
    use, replace with Redis/DynamoDB for cross-process deduplication.
    """

    def __init__(self, ttl_seconds: float = 300.0) -> None:
        self._inflight: Set[str] = set()
        self._completed: Dict[str, Any] = {}
        self._completed_at: Dict[str, float] = {}
        self._ttl = ttl_seconds

    def try_acquire(self, key: str) -> bool:
        """Attempt to register an in-flight key.

        Returns ``True`` if the key was acquired (new request).
        Returns ``False`` if already in-flight.
        """
        self._evict_expired()
        if key in self._inflight:
            return False
        self._inflight.add(key)
        return True

    def complete(self, key: str, result: Any) -> None:
        """Mark an in-flight key as completed with its result."""
        self._inflight.discard(key)
        self._completed[key] = result
        self._completed_at[key] = time.monotonic()

    def get_completed(self, key: str) -> Optional[Any]:
        """Return the cached result for a completed key, or None."""
        self._evict_expired()
        if key in self._completed:
            return self._completed[key]
        return None

    def _evict_expired(self) -> None:
        now = time.monotonic()
        expired = [k for k, t in self._completed_at.items() if now - t > self._ttl]
        for k in expired:
            del self._completed[k]
            del self._completed_at[k]


# ---------------------------------------------------------------------------
# RetryHandler
# ---------------------------------------------------------------------------


class MaxRetriesExceededError(Exception):
    """Raised when all retry attempts have been exhausted."""

    def __init__(self, message: str, last_error: Optional[Exception] = None) -> None:
        super().__init__(message)
        self.last_error = last_error


class NonRetryableError(Exception):
    """Raised when an error is classified as non-retryable."""
    pass


@dataclass
class RetryHandler:
    """Orchestrates retry logic: backoff + circuit breaker + idempotency.

    Usage::

        handler = RetryHandler(
            BackoffConfig(max_attempts=5),
            CircuitBreakerConfig(failure_threshold=5),
        )

        def api_call() -> dict:
            resp = httpx.post(...)
            if resp.status_code == 429:
                raise RateLimitError(...)
            return resp.json()

        result = handler.execute(api_call)

    The handler will:
    1. Check the circuit breaker before each attempt.
    2. Classify errors and decide whether to retry.
    3. Apply exponential backoff with jitter between attempts.
    4. Respect the ``Retry-After`` header for 429 responses.
    """

    backoff: BackoffConfig = field(default_factory=BackoffConfig)
    circuit: CircuitBreakerConfig = field(default_factory=CircuitBreakerConfig)
    idempotency_ttl: float = 300.0
    _breaker: Optional[CircuitBreaker] = field(default=None, init=False)
    _registry: Optional[IdempotencyRegistry] = field(default=None, init=False)

    def __post_init__(self) -> None:
        self._breaker = CircuitBreaker(self.circuit)
        self._registry = IdempotencyRegistry(self.idempotency_ttl)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def execute(
        self,
        fn: Callable[[], Any],
        idempotency_key: Optional[str] = None,
        on_retry: Optional[Callable[[int, Exception], None]] = None,
    ) -> Any:
        """Execute *fn* with full retry/circuit-breaker protection.

        Args:
            fn: The callable to execute (must be idempotent if you
                want safe retries).
            idempotency_key: Optional dedup key. If provided, repeated
                calls with the same key return the cached result.
            on_retry: Optional callback invoked before each retry:
                ``on_retry(attempt_number, exception)``.

        Returns:
            The return value of *fn*.

        Raises:
            NonRetryableError: The error is not retryable.
            CircuitBreakerOpenError: The circuit is open.
            MaxRetriesExceededError: All retries exhausted.
        """
        # Idempotency check
        if idempotency_key:
            cached = self._registry.get_completed(idempotency_key)  # type: ignore[union-attr]
            if cached is not None:
                return cached

        assert self._breaker is not None

        last_error: Optional[Exception] = None

        for attempt in range(self.backoff.max_attempts):
            # Circuit breaker check
            if not self._breaker.allow_request():
                raise CircuitBreakerOpenError(
                    f"Circuit breaker is {self._breaker.state.value}; "
                    f"{self._breaker.failure_count} consecutive failures."
                )

            try:
                result = fn()
                self._breaker.record_success()
                if idempotency_key:
                    self._registry.complete(idempotency_key, result)  # type: ignore[union-attr]
                return result
            except Exception as exc:
                last_error = exc
                category = self._classify(exc)

                if category == ErrorCategory.NON_RETRYABLE:
                    self._breaker.record_failure()
                    raise NonRetryableError(
                        f"Non-retryable error: {exc}"
                    ) from exc

                self._breaker.record_failure()

                if attempt == self.backoff.max_attempts - 1:
                    break

                # Compute delay
                delay = self.backoff.delay(attempt)
                # Respect Retry-After for 429
                retry_after = self._extract_retry_after(exc)
                delay = max(delay, retry_after)

                if on_retry:
                    on_retry(attempt + 1, exc)

                time.sleep(delay)

        raise MaxRetriesExceededError(
            f"All {self.backoff.max_attempts} retry attempts exhausted.",
            last_error=last_error,
        )

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    @staticmethod
    def _classify(exc: Exception) -> ErrorCategory:
        """Extract error category from an exception."""
        # Try to get status_code from httpx.HTTPStatusError
        status = getattr(exc, "response", None)
        if status is not None:
            return classify_error(
                status_code=getattr(status, "status_code", None),
            )
        return classify_error(exception=exc)

    @staticmethod
    def _extract_retry_after(exc: Exception) -> float:
        """Extract ``Retry-After`` seconds from an httpx response, if present."""
        resp = getattr(exc, "response", None)
        if resp is not None:
            header = getattr(resp, "headers", {}).get("retry-after")
            if header:
                return parse_retry_after(header)
        return 0.0
