"""
Chapter 8: Cache Keep-Alive.

Implements the Keep-Alive Ping pattern for maintaining Prompt Cache warmth
during idle periods. Sends lightweight requests at a configurable interval
to reset the 5-minute ephemeral cache TTL.

Architecture:
  - Background thread sends ping requests at the configured interval
  - Only sends when idle (guard via user activity tracking)
  - Respects start/stop lifecycle for clean shutdown
  - Ping payload: system prompt only (no new messages), minimizing cost
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from typing import Any, Callable, Dict, Optional


# Default ping interval: 240 seconds (4 minutes), leaving 1-minute buffer
DEFAULT_PING_INTERVAL = 240

# Minimum safe interval to prevent excessive API calls
MIN_PING_INTERVAL = 60


@dataclass
class KeepAliveStats:
    """Statistics for a CacheKeepAlive session."""

    pings_sent: int = 0
    pings_failed: int = 0
    cache_writes_saved: int = 0  # estimated cache rewrites avoided
    total_cost: float = 0.0      # estimated total keep-alive cost in dollars

    def add_ping(self, success: bool, cost: float) -> None:
        self.pings_sent += 1
        if not success:
            self.pings_failed += 1
        self.total_cost += cost


class CacheKeepAlive:
    """Maintains Prompt Cache warmth during idle periods.

    When a user pauses between messages for more than 5 minutes (the default
    ephemeral cache TTL), the cached prefix expires. The next request must
    re-process the entire prefix at cache-write pricing (+25% premium).

    CacheKeepAlive sends periodic "ping" requests containing only the system
    prompt to reset the TTL timer, keeping the cache alive at minimal cost
    (~$0.0045/ping for a 15K-token system prompt at cache-read pricing).

    Usage::

        def send_ping(system_prompt: str) -> dict:
            # Your actual API call here
            return client.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=1,
                system=system_prompt,
                messages=[{"role": "user", "content": "ping"}],
            )

        keeper = CacheKeepAlive(
            send_fn=send_ping,
            system_prompt="You are an expert...",
            ping_interval=240,
        )
        keeper.start()
        # ... user thinks for several minutes ...
        keeper.user_active()  # signal user activity, skip next ping
        # ... user sends message, cache still warm ...
        keeper.stop()
    """

    def __init__(
        self,
        send_fn: Callable[[str], Any],
        system_prompt: str,
        ping_interval: int = DEFAULT_PING_INTERVAL,
        max_retries: int = 3,
        on_ping_result: Optional[Callable[[bool, float], None]] = None,
    ) -> None:
        """Initialize the keep-alive manager.

        Args:
            send_fn: Async-compatible function that sends a ping request.
                     Receives the system_prompt and returns a response dict.
            system_prompt: The system prompt to include in ping requests.
            ping_interval: Seconds between pings (default 240, minimum 60).
            max_retries: Maximum consecutive ping failures before stopping.
            on_ping_result: Optional callback invoked after each ping with
                           (success: bool, estimated_cost: float).
        """
        if ping_interval < MIN_PING_INTERVAL:
            raise ValueError(
                f"ping_interval must be >= {MIN_PING_INTERVAL}s, got {ping_interval}"
            )

        self._send_fn = send_fn
        self._system_prompt = system_prompt
        self._ping_interval = ping_interval
        self._max_retries = max_retries
        self._on_ping_result = on_ping_result

        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._idle_event = threading.Event()
        self._idle_event.set()  # start as idle

        self.stats = KeepAliveStats()
        self._consecutive_failures = 0
        self._lock = threading.Lock()

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def start(self) -> None:
        """Start the keep-alive background thread.

        Safe to call multiple times; subsequent calls are no-ops if already
        running.
        """
        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                return
            self._stop_event.clear()
            self._consecutive_failures = 0
            self._thread = threading.Thread(
                target=self._ping_loop,
                name="cache-keepalive",
                daemon=True,
            )
            self._thread.start()

    def stop(self) -> None:
        """Stop the keep-alive background thread.

        Blocks until the thread exits. Safe to call multiple times.
        """
        with self._lock:
            if self._thread is None:
                return
            self._stop_event.set()
            self._idle_event.set()  # wake up if sleeping

        if self._thread.is_alive():
            self._thread.join(timeout=10.0)

        with self._lock:
            self._thread = None

    @property
    def is_running(self) -> bool:
        with self._lock:
            return self._thread is not None and self._thread.is_alive()

    # ------------------------------------------------------------------
    # User activity signaling
    # ------------------------------------------------------------------

    def user_active(self) -> None:
        """Signal that the user is actively interacting.

        This resets the idle timer. The keep-alive will wait for the full
        ping_interval after this call before sending the next ping.
        """
        self._idle_event.clear()

    def user_idle(self) -> None:
        """Signal that the user has become idle.

        The keep-alive ping cycle will resume after the ping_interval.
        """
        self._idle_event.set()

    # ------------------------------------------------------------------
    # Internal ping loop
    # ------------------------------------------------------------------

    def _ping_loop(self) -> None:
        """Background thread: wait, then ping, repeat."""
        while not self._stop_event.is_set():
            # Wait for idle state or stop signal
            self._idle_event.wait(timeout=self._ping_interval)

            if self._stop_event.is_set():
                break

            # Double-check we're still idle
            if not self._idle_event.is_set():
                continue

            self._send_ping()

            # Exponential backoff on repeated failures
            if self._consecutive_failures >= self._max_retries:
                # Stop pinging; let the cache expire naturally
                break

            # Sleep for the remainder of the interval
            self._stop_event.wait(timeout=self._ping_interval)

    def _send_ping(self) -> None:
        """Send a single keep-alive ping."""
        success = False
        cost = 0.0

        try:
            response = self._send_fn(self._system_prompt)
            # Estimate cost from response usage if available
            usage = response.get("usage", {}) if isinstance(response, dict) else {}
            read_tokens = usage.get("cache_read_input_tokens", 0)
            write_tokens = usage.get("cache_creation_input_tokens", 0)
            # Approximate cost: read at $0.30/MTok, write at $3.75/MTok
            cost = read_tokens * 0.30 / 1_000_000 + write_tokens * 3.75 / 1_000_000

            self._consecutive_failures = 0
            success = True
            self.stats.cache_writes_saved += 1

        except Exception:
            self._consecutive_failures += 1

        self.stats.add_ping(success, cost)

        if self._on_ping_result:
            try:
                self._on_ping_result(success, cost)
            except Exception:
                pass  # callback failures must not break the loop

    # ------------------------------------------------------------------
    # Cost analysis
    # ------------------------------------------------------------------

    def estimate_keepalive_cost_per_hour(
        self,
        system_prompt_tokens: int,
        hit_rate: float = 1.0,
    ) -> float:
        """Estimate hourly keep-alive cost.

        Args:
            system_prompt_tokens: Size of system prompt in tokens.
            hit_rate: Expected cache hit rate (0.0-1.0).

        Returns:
            Estimated cost in dollars per hour.
        """
        pings_per_hour = 3600 / self._ping_interval

        # When cache hits: read pricing ($0.30/MTok)
        # When cache misses: write pricing ($3.75/MTok)
        hit_cost = (
            system_prompt_tokens * 0.30 / 1_000_000 * hit_rate
        )
        miss_cost = (
            system_prompt_tokens * 3.75 / 1_000_000 * (1 - hit_rate)
        )
        cost_per_ping = hit_cost + miss_cost

        return round(cost_per_ping * pings_per_hour, 6)

    def compare_to_cache_rewrite(
        self,
        system_prompt_tokens: int,
    ) -> Dict[str, float]:
        """Compare keep-alive cost against the cost of letting cache expire.

        Without keepalive, the cache expires every 5 minutes, requiring a
        full cache rewrite each time (~pings_per_hour rewrites per hour).
        Keepalive replaces those expensive rewrites with cheap reads.

        Returns:
            Dict with 'keepalive_hourly', 'rewrite_cost_per_hour', and 'savings'.
        """
        pings_per_hour = 3600 / self._ping_interval
        hourly = self.estimate_keepalive_cost_per_hour(system_prompt_tokens)
        # Without keepalive: each expiry means another cache write
        rewrite_per_hour = (
            system_prompt_tokens * 3.75 / 1_000_000 * pings_per_hour
        )
        return {
            "keepalive_hourly": hourly,
            "rewrite_cost_per_hour": round(rewrite_per_hour, 6),
            "savings": round(rewrite_per_hour - hourly, 6),
        }
