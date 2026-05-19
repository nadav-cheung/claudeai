"""
Tests for Chapter 17: TokenBucketRateLimiter and SlidingWindowRateLimiter.
"""

from __future__ import annotations

import time

import pytest

from rate_limiter import (
    MODEL_RATE_LIMITS,
    RateLimitConfig,
    SlidingWindowRateLimiter,
    TokenBucketRateLimiter,
    UsageTier,
)


class TestTokenBucketRateLimiter:
    """Tests for the token-bucket rate limiter."""

    def test_initial_capacity_full(self) -> None:
        limiter = TokenBucketRateLimiter(50, 20_000, 8_000)
        req, it, ot = limiter.available()
        assert req == 50.0
        assert it == 20_000.0
        assert ot == 8_000.0

    def test_consume_reduces_capacity(self) -> None:
        limiter = TokenBucketRateLimiter(50, 20_000, 8_000)
        assert limiter.consume(requests=1, input_tokens=500, output_tokens=200)
        req, it, ot = limiter.available()
        assert req == pytest.approx(49.0)
        assert it == pytest.approx(19500.0, abs=0.1)
        assert ot == pytest.approx(7800.0, abs=0.1)

    def test_consume_fails_when_exceeded(self) -> None:
        limiter = TokenBucketRateLimiter(10, 100, 100)
        # consume all requests
        for _ in range(10):
            assert limiter.consume(requests=1)
        # 11th should fail
        assert not limiter.consume(requests=1)

    def test_consume_all_or_nothing(self) -> None:
        limiter = TokenBucketRateLimiter(50, 20_000, 8_000)
        # Has enough requests but not enough tokens
        result = limiter.consume(requests=1, input_tokens=1_000_000, output_tokens=0)
        assert result is False
        # Should NOT have consumed the request slot
        req, it, ot = limiter.available()
        assert req == 50.0  # unchanged
        assert it == 20_000.0  # unchanged
        assert ot == 8_000.0  # unchanged

    def test_time_until_available_immediate(self) -> None:
        limiter = TokenBucketRateLimiter(50, 20_000, 8_000)
        t = limiter.time_until_available(requests=1, input_tokens=100, output_tokens=50)
        assert t == 0.0

    def test_time_until_available_positive(self) -> None:
        limiter = TokenBucketRateLimiter(50, 20_000, 8_000)
        # Consume all requests
        for _ in range(50):
            limiter.consume(requests=1)
        t = limiter.time_until_available(requests=1)
        # Fill rate is 50/60 ≈ 0.833 req/s, so need >0 seconds
        assert t > 0.0
        assert t <= 2.0  # should be ~1.2s

    def test_refill_over_time(self) -> None:
        limiter = TokenBucketRateLimiter(50, 20_000, 8_000)
        # Exhaust
        for _ in range(50):
            limiter.consume(requests=1)
        req, _, _ = limiter.available()
        assert req < 1.0
        # Wait for some refill (50/60 req/s ≈ 0.833 req/s)
        time.sleep(1.5)
        req, _, _ = limiter.available()
        assert req >= 1.0  # At least 1 request slot should be available

    def test_warn_threshold_exceeded(self) -> None:
        limiter = TokenBucketRateLimiter(50, 20_000, 8_000)
        warnings = limiter.warn_threshold_exceeded()
        assert warnings == []  # Full capacity, no warnings

        # Consume 80% of RPM
        for _ in range(40):
            limiter.consume(requests=1)
        warnings = limiter.warn_threshold_exceeded()
        assert "rpm" in warnings

    def test_model_rate_limits_have_all_tiers(self) -> None:
        for model, config in MODEL_RATE_LIMITS.items():
            assert config.rpm > 0
            assert config.itpm > 0
            assert config.otpm > 0

    def test_limits_property(self) -> None:
        limiter = TokenBucketRateLimiter(10, 100, 50)
        assert limiter.limits == (10.0, 100.0, 50.0)


class TestSlidingWindowRateLimiter:
    """Tests for the sliding-window rate limiter."""

    def test_initial_allow(self) -> None:
        limiter = SlidingWindowRateLimiter(max_requests=10, window_seconds=60.0)
        assert limiter.allow() is True
        assert limiter.current_count() == 1

    def test_exhausted_window(self) -> None:
        limiter = SlidingWindowRateLimiter(max_requests=3, window_seconds=60.0)
        for _ in range(3):
            assert limiter.allow() is True
        # 4th should fail
        assert limiter.allow() is False
        assert limiter.current_count() == 3

    def test_eviction_after_window(self) -> None:
        limiter = SlidingWindowRateLimiter(max_requests=1, window_seconds=0.01)
        assert limiter.allow() is True
        assert limiter.allow() is False
        time.sleep(0.02)
        # After window passes, the old request is evicted
        assert limiter.allow() is True

    def test_remaining(self) -> None:
        limiter = SlidingWindowRateLimiter(max_requests=10, window_seconds=60.0)
        assert limiter.remaining() == 10
        for _ in range(4):
            limiter.allow()
        assert limiter.remaining() == 6

    def test_time_until_next_slot_empty(self) -> None:
        limiter = SlidingWindowRateLimiter(max_requests=10, window_seconds=60.0)
        assert limiter.time_until_next_slot() == 0.0

    def test_time_until_next_slot_full(self) -> None:
        limiter = SlidingWindowRateLimiter(max_requests=1, window_seconds=60.0)
        limiter.allow()
        t = limiter.time_until_next_slot()
        assert t > 0.0
        assert t <= 60.0
