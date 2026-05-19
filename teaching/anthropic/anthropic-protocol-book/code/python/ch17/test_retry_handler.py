"""
Tests for Chapter 17: RetryHandler — backoff, jitter, circuit breaker, idempotency.
"""

from __future__ import annotations

import time

import pytest

from retry_handler import (
    BackoffConfig,
    CircuitBreaker,
    CircuitBreakerConfig,
    CircuitBreakerOpenError,
    CircuitState,
    ErrorCategory,
    IdempotencyRegistry,
    MaxRetriesExceededError,
    NonRetryableError,
    RetryHandler,
    classify_error,
    generate_idempotency_key,
    parse_retry_after,
)


# ---------------------------------------------------------------------------
# Error classification
# ---------------------------------------------------------------------------


class TestClassifyError:
    def test_429_is_rate_limit(self) -> None:
        assert classify_error(status_code=429) == ErrorCategory.RETRYABLE_RATE_LIMIT

    def test_500_is_server(self) -> None:
        assert classify_error(status_code=500) == ErrorCategory.RETRYABLE_SERVER

    def test_529_is_server(self) -> None:
        assert classify_error(status_code=529) == ErrorCategory.RETRYABLE_SERVER

    def test_400_is_non_retryable(self) -> None:
        assert classify_error(status_code=400) == ErrorCategory.NON_RETRYABLE

    def test_401_is_non_retryable(self) -> None:
        assert classify_error(status_code=401) == ErrorCategory.NON_RETRYABLE

    def test_403_is_non_retryable(self) -> None:
        assert classify_error(status_code=403) == ErrorCategory.NON_RETRYABLE

    def test_connection_error_is_network(self) -> None:
        assert classify_error(exception=ConnectionError()) == ErrorCategory.RETRYABLE_NETWORK

    def test_value_error_is_non_retryable(self) -> None:
        assert classify_error(exception=ValueError()) == ErrorCategory.NON_RETRYABLE


# ---------------------------------------------------------------------------
# Retry-After parsing
# ---------------------------------------------------------------------------


class TestParseRetryAfter:
    def test_delta_seconds(self) -> None:
        assert parse_retry_after("30") == 30.0

    def test_none(self) -> None:
        assert parse_retry_after(None) == 0.0

    def test_empty(self) -> None:
        assert parse_retry_after("") == 0.0

    def test_whitespace(self) -> None:
        assert parse_retry_after("  42  ") == 42.0

    def test_invalid_string(self) -> None:
        assert parse_retry_after("not-a-number") == 0.0


# ---------------------------------------------------------------------------
# Exponential backoff
# ---------------------------------------------------------------------------


class TestBackoffConfig:
    def test_first_attempt_zero(self) -> None:
        cfg = BackoffConfig(base_delay=1.0, factor=2.0)
        # attempt 0: delay = 1.0 * 2^0 = 1.0, with full jitter [0, 1.0)
        for _ in range(20):
            d = cfg.delay(0)
            assert 0.0 <= d <= 1.0

    def test_exponential_growth(self) -> None:
        cfg = BackoffConfig(base_delay=1.0, factor=2.0, max_delay=1000.0)
        # attempt 3: delay = 1.0 * 2^3 = 8.0, with jitter [0, 8.0)
        for _ in range(20):
            d = cfg.delay(3)
            assert 0.0 <= d <= 8.0

    def test_max_delay_cap(self) -> None:
        cfg = BackoffConfig(base_delay=1.0, factor=2.0, max_delay=10.0)
        # Very high attempt should still be capped
        for _ in range(20):
            d = cfg.delay(50)
            assert 0.0 <= d <= 10.0

    def test_max_exp_attempts_cap(self) -> None:
        cfg = BackoffConfig(base_delay=1.0, factor=2.0, max_exp_attempts=3, max_delay=1000.0)
        # attempt 10 should be capped to exponent 3: 1.0 * 2^3 = 8.0
        for _ in range(20):
            d = cfg.delay(10)
            assert d <= 8.0

    def test_negative_attempt_treated_as_zero(self) -> None:
        cfg = BackoffConfig(base_delay=1.0, factor=2.0)
        d = cfg.delay(-1)
        assert 0.0 <= d <= 1.0


# ---------------------------------------------------------------------------
# Circuit breaker
# ---------------------------------------------------------------------------


class TestCircuitBreaker:
    def test_initial_state_closed(self) -> None:
        cb = CircuitBreaker()
        assert cb.state == CircuitState.CLOSED
        assert cb.allow_request() is True

    def test_opens_after_failures(self) -> None:
        cb = CircuitBreaker(CircuitBreakerConfig(failure_threshold=3))
        for _ in range(3):
            cb.record_failure()
        assert cb.state == CircuitState.OPEN
        assert cb.allow_request() is False

    def test_transitions_to_half_open(self) -> None:
        cb = CircuitBreaker(
            CircuitBreakerConfig(failure_threshold=1, reset_timeout=0.01)
        )
        cb.record_failure()
        assert cb.state == CircuitState.OPEN
        time.sleep(0.02)
        assert cb.allow_request() is True
        assert cb.state == CircuitState.HALF_OPEN

    def test_half_open_success_closes(self) -> None:
        cb = CircuitBreaker(
            CircuitBreakerConfig(
                failure_threshold=1, reset_timeout=0.01, success_threshold=2,
            )
        )
        cb.record_failure()
        time.sleep(0.02)
        cb.allow_request()
        cb.record_success()
        assert cb.state == CircuitState.HALF_OPEN  # not enough yet
        cb.record_success()
        assert cb.state == CircuitState.CLOSED

    def test_half_open_failure_reopens(self) -> None:
        cb = CircuitBreaker(
            CircuitBreakerConfig(failure_threshold=1, reset_timeout=0.01)
        )
        cb.record_failure()
        time.sleep(0.02)
        cb.allow_request()
        cb.record_failure()
        assert cb.state == CircuitState.OPEN

    def test_success_resets_counter_when_closed(self) -> None:
        cb = CircuitBreaker(CircuitBreakerConfig(failure_threshold=5))
        for _ in range(3):
            cb.record_failure()
        cb.record_success()
        assert cb.failure_count == 0


# ---------------------------------------------------------------------------
# Idempotency
# ---------------------------------------------------------------------------


class TestIdempotencyRegistry:
    def test_acquire_new_key(self) -> None:
        reg = IdempotencyRegistry()
        assert reg.try_acquire("key1") is True

    def test_acquire_duplicate(self) -> None:
        reg = IdempotencyRegistry()
        reg.try_acquire("key1")
        assert reg.try_acquire("key1") is False

    def test_complete_releases(self) -> None:
        reg = IdempotencyRegistry()
        reg.try_acquire("key1")
        reg.complete("key1", {"result": "ok"})
        # After completion, should not be in-flight (but no re-acquire needed)
        result = reg.get_completed("key1")
        assert result == {"result": "ok"}

    def test_get_completed_nonexistent(self) -> None:
        reg = IdempotencyRegistry()
        assert reg.get_completed("nonexistent") is None


class TestGenerateIdempotencyKey:
    def test_deterministic(self) -> None:
        k1 = generate_idempotency_key("hello")
        k2 = generate_idempotency_key("hello")
        assert k1 == k2

    def test_different_payloads(self) -> None:
        k1 = generate_idempotency_key("hello")
        k2 = generate_idempotency_key("world")
        assert k1 != k2

    def test_output_is_hex(self) -> None:
        k = generate_idempotency_key("test")
        assert len(k) == 64
        int(k, 16)  # should be valid hex


# ---------------------------------------------------------------------------
# RetryHandler integration
# ---------------------------------------------------------------------------


class TestRetryHandler:
    def test_successful_call_no_retry(self) -> None:
        handler = RetryHandler()
        call_count = [0]

        def fn() -> str:
            call_count[0] += 1
            return "ok"

        result = handler.execute(fn)
        assert result == "ok"
        assert call_count[0] == 1

    def test_retries_then_succeeds(self) -> None:
        handler = RetryHandler(
            BackoffConfig(base_delay=0.001, max_attempts=5),
        )
        call_count = [0]

        def fn() -> str:
            call_count[0] += 1
            if call_count[0] < 3:
                raise ConnectionError("transient")
            return "ok"

        result = handler.execute(fn)
        assert result == "ok"
        assert call_count[0] == 3

    def test_max_retries_exceeded(self) -> None:
        handler = RetryHandler(
            BackoffConfig(base_delay=0.001, max_attempts=3),
        )

        def fn() -> str:
            raise ConnectionError("always fails")

        with pytest.raises(MaxRetriesExceededError) as exc:
            handler.execute(fn)
        assert exc.value.last_error is not None

    def test_non_retryable_raises(self) -> None:
        handler = RetryHandler()

        def fn() -> str:
            raise ValueError("bad input")

        with pytest.raises(NonRetryableError):
            handler.execute(fn)

    def test_on_retry_callback(self) -> None:
        handler = RetryHandler(
            BackoffConfig(base_delay=0.001, max_attempts=5),
        )
        retries_log: list = []

        def fn() -> str:
            if not retries_log:
                raise ConnectionError("first")
            return "ok"

        result = handler.execute(fn, on_retry=lambda a, e: retries_log.append(a))
        assert result == "ok"
        assert retries_log == [1]

    def test_idempotency_prevents_duplicate(self) -> None:
        handler = RetryHandler()
        call_count = [0]

        def fn() -> dict:
            call_count[0] += 1
            return {"value": call_count[0]}

        key = "idem-test-1"
        r1 = handler.execute(fn, idempotency_key=key)
        r2 = handler.execute(fn, idempotency_key=key)
        assert r1 == r2
        assert call_count[0] == 1  # Only called once
