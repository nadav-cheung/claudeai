"""
Chapter 17: Rate Limiter — Token Bucket and Sliding Window implementations.

Implements the two most common rate-limiting algorithms used in LLM API
production systems.  Token Bucket is the algorithm used by Anthropic's own
API; Sliding Window provides predictable burst control.

Verified against docs.anthropic.com (May 2026):
  - Token bucket algorithm with continuous replenishment
  - Tier-based limits (RPM / ITPM / OTPM per model class)
  - 429 response with ``retry-after`` header
  - Rate-limit response headers for observability
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from enum import Enum
from typing import Dict, List, Optional, Tuple


# ---------------------------------------------------------------------------
# Domain types
# ---------------------------------------------------------------------------


class UsageTier(str, Enum):
    """Anthropic usage tiers with spend thresholds and default rate limits.

    Per the Anthropic Console: Tier 1 is the default for new accounts.
    Higher tiers unlock with cumulative credit purchases.
    """

    TIER_1 = "tier_1"   # $5  purchase  → $100/mo  spend
    TIER_2 = "tier_2"   # $40 purchase  → $500/mo  spend
    TIER_3 = "tier_3"   # $200 purchase → $1,000/mo spend
    TIER_4 = "tier_4"   # $400 purchase → $5,000/mo spend


@dataclass(frozen=True)
class RateLimitConfig:
    """Rate-limit parameters for a single model class.

    All values are per-minute limits as documented at
    https://docs.anthropic.com/en/api/rate-limits.
    """

    rpm: int          # requests per minute
    itpm: int         # input tokens per minute
    otpm: int         # output tokens per minute

    # Percentage of limit at which we start warning (0.0–1.0)
    warn_threshold_pct: float = 0.75


# Default limits per model (standard tier, as of May 2026)
MODEL_RATE_LIMITS: Dict[str, RateLimitConfig] = {
    "claude-opus-4-7":              RateLimitConfig(50, 20_000, 8_000),
    "claude-sonnet-4-6":            RateLimitConfig(50, 20_000, 8_000),
    "claude-haiku-4-5-20251001":    RateLimitConfig(50, 50_000, 10_000),
    "claude-opus-4-20250514":       RateLimitConfig(50, 20_000, 8_000),
    "claude-sonnet-4-20250514":     RateLimitConfig(50, 20_000, 8_000),
    "claude-sonnet-3-7-20250219":   RateLimitConfig(50, 20_000, 8_000),
    "claude-sonnet-3-5-20241022":   RateLimitConfig(50, 40_000, 8_000),
    "claude-haiku-3-5-20241022":    RateLimitConfig(50, 50_000, 10_000),
    "claude-opus-3-20240229":       RateLimitConfig(50, 20_000, 4_000),
    "claude-sonnet-3-20240229":     RateLimitConfig(50, 40_000, 8_000),
    "claude-haiku-3-20240307":      RateLimitConfig(50, 50_000, 10_000),
}


# ---------------------------------------------------------------------------
# Token Bucket Rate Limiter
# ---------------------------------------------------------------------------


@dataclass
class _TokenBucket:
    """Internal state for a single token-bucket dimension (RPM, ITPM, OTPM)."""

    capacity: float     # max tokens
    fill_rate: float    # tokens per second
    tokens: float       # current token count
    last_fill: float    # last refill timestamp (monotonic seconds)


class TokenBucketRateLimiter:
    """Thread-safe token-bucket rate limiter for Anthropic API requests.

    Implements the same algorithm used server-side by Anthropic:
    tokens are continuously replenished at ``capacity / 60`` per second,
    up to ``capacity``.  When ``consume(n)`` returns ``False`` the caller
    should wait (or receive a 429) before retrying.

    Usage::

        limiter = TokenBucketRateLimiter(
            capacity_rpm=50, capacity_itpm=20_000, capacity_otpm=8_000,
        )
        if not limiter.consume(requests=1, input_tokens=500, output_tokens=200):
            # Rate limited — back off
            ...

    Thread-safety: all public methods acquire an internal lock.
    """

    def __init__(
        self,
        capacity_rpm: int,
        capacity_itpm: int,
        capacity_otpm: int,
    ) -> None:
        now = time.monotonic()
        self._lock = threading.Lock()
        self._requests = _TokenBucket(
            capacity=float(capacity_rpm),
            fill_rate=capacity_rpm / 60.0,
            tokens=float(capacity_rpm),
            last_fill=now,
        )
        self._input_tokens = _TokenBucket(
            capacity=float(capacity_itpm),
            fill_rate=capacity_itpm / 60.0,
            tokens=float(capacity_itpm),
            last_fill=now,
        )
        self._output_tokens = _TokenBucket(
            capacity=float(capacity_otpm),
            fill_rate=capacity_otpm / 60.0,
            tokens=float(capacity_otpm),
            last_fill=now,
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _refill(bucket: _TokenBucket, now: float) -> None:
        elapsed = now - bucket.last_fill
        if elapsed <= 0:
            return
        bucket.tokens = min(bucket.capacity, bucket.tokens + elapsed * bucket.fill_rate)
        bucket.last_fill = now

    def _try_consume(self, bucket: _TokenBucket, tokens: float, now: float) -> bool:
        self._refill(bucket, now)
        if bucket.tokens >= tokens:
            bucket.tokens -= tokens
            return True
        return False

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def consume(
        self,
        requests: int = 1,
        input_tokens: int = 0,
        output_tokens: int = 0,
    ) -> bool:
        """Attempt to consume capacity from all three buckets atomically.

        Returns ``True`` if all dimensions had sufficient capacity.
        Returns ``False`` if any dimension is exhausted (no tokens consumed).
        """
        now = time.monotonic()
        with self._lock:
            # Check all dimensions first (atomic all-or-nothing)
            self._refill(self._requests, now)
            self._refill(self._input_tokens, now)
            self._refill(self._output_tokens, now)

            ok = (
                self._requests.tokens >= requests
                and self._input_tokens.tokens >= input_tokens
                and self._output_tokens.tokens >= output_tokens
            )
            if not ok:
                return False

            self._requests.tokens -= requests
            self._input_tokens.tokens -= input_tokens
            self._output_tokens.tokens -= output_tokens
            return True

    def available(self) -> Tuple[float, float, float]:
        """Return current available capacity: (requests, input_tokens, output_tokens)."""
        now = time.monotonic()
        with self._lock:
            self._refill(self._requests, now)
            self._refill(self._input_tokens, now)
            self._refill(self._output_tokens, now)
            return (
                self._requests.tokens,
                self._input_tokens.tokens,
                self._output_tokens.tokens,
            )

    def time_until_available(
        self,
        requests: int = 1,
        input_tokens: int = 0,
        output_tokens: int = 0,
    ) -> float:
        """Estimated seconds until the requested capacity is available.

        Returns 0.0 if already available.
        """
        now = time.monotonic()
        with self._lock:
            self._refill(self._requests, now)
            self._refill(self._input_tokens, now)
            self._refill(self._output_tokens, now)

            wait_r = (
                max(0.0, (requests - self._requests.tokens) / self._requests.fill_rate)
                if self._requests.fill_rate > 0
                else float("inf")
            )
            wait_i = (
                max(0.0, (input_tokens - self._input_tokens.tokens) / self._input_tokens.fill_rate)
                if self._input_tokens.fill_rate > 0
                else float("inf")
            )
            wait_o = (
                max(0.0, (output_tokens - self._output_tokens.tokens) / self._output_tokens.fill_rate)
                if self._output_tokens.fill_rate > 0
                else float("inf")
            )
            return max(wait_r, wait_i, wait_o)

    def warn_threshold_exceeded(self) -> List[str]:
        """Return list of dimension names exceeding the warn threshold (75%)."""
        req, it, ot = self.available()
        warnings: List[str] = []
        if req < self._requests.capacity * 0.25:  # >75% consumed
            warnings.append("rpm")
        if it < self._input_tokens.capacity * 0.25:
            warnings.append("itpm")
        if ot < self._output_tokens.capacity * 0.25:
            warnings.append("otpm")
        return warnings

    @property
    def limits(self) -> Tuple[float, float, float]:
        return (
            self._requests.capacity,
            self._input_tokens.capacity,
            self._output_tokens.capacity,
        )


# ---------------------------------------------------------------------------
# Sliding Window Rate Limiter
# ---------------------------------------------------------------------------


class SlidingWindowRateLimiter:
    """Rate limiter using a sliding-window log for precise burst control.

    Unlike token bucket, which smooths bursts, sliding window enforces a
    strict maximum over any period of ``window_seconds``.  This is useful
    when downstream systems (or your own budget) require hard per-window
    caps rather than average-rate smoothing.

    Storage cost is O(requests in window).  For high-throughput systems
    with thousands of RPM, prefer TokenBucketRateLimiter.
    """

    def __init__(
        self,
        max_requests: int,
        window_seconds: float = 60.0,
    ) -> None:
        self._max_requests = max_requests
        self._window = window_seconds
        self._timestamps: List[float] = []
        self._lock = threading.Lock()

    def _evict(self, now: float) -> None:
        cutoff = now - self._window
        # Binary-search for the first timestamp >= cutoff
        lo, hi = 0, len(self._timestamps)
        while lo < hi:
            mid = (lo + hi) // 2
            if self._timestamps[mid] < cutoff:
                lo = mid + 1
            else:
                hi = mid
        if lo > 0:
            self._timestamps = self._timestamps[lo:]

    def allow(self) -> bool:
        """Check if a request is permitted right now.

        Returns ``True`` and records the timestamp if permitted.
        """
        now = time.monotonic()
        with self._lock:
            self._evict(now)
            if len(self._timestamps) < self._max_requests:
                self._timestamps.append(now)
                return True
            return False

    def current_count(self) -> int:
        """Number of requests recorded in the current window."""
        now = time.monotonic()
        with self._lock:
            self._evict(now)
            return len(self._timestamps)

    def time_until_next_slot(self) -> float:
        """Seconds until the oldest request exits the window.

        Returns 0.0 if there are fewer requests than the max.
        """
        now = time.monotonic()
        with self._lock:
            self._evict(now)
            if len(self._timestamps) < self._max_requests:
                return 0.0
            oldest = self._timestamps[0]
            return max(0.0, oldest + self._window - now)

    def remaining(self) -> int:
        """Remaining slots in the current window."""
        return max(0, self._max_requests - self.current_count())
