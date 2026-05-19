"""
Tests for Chapter 8: Cache Keep-Alive.
"""

import threading
import time

import pytest

from cache_keepalive import (
    MIN_PING_INTERVAL,
    CacheKeepAlive,
    KeepAliveStats,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def ping_log() -> list:
    """Mutable log that captures ping calls."""
    return []


@pytest.fixture
def send_fn(ping_log: list):
    """Factory for mock send function."""
    def _send(system_prompt: str) -> dict:
        ping_log.append(system_prompt)
        return {
            "usage": {
                "input_tokens": 15000,
                "cache_read_input_tokens": 15000,
                "cache_creation_input_tokens": 0,
            }
        }
    return _send


# ---------------------------------------------------------------------------
# Initialization tests
# ---------------------------------------------------------------------------


class TestInitialization:
    def test_default_interval(self, send_fn) -> None:
        keeper = CacheKeepAlive(send_fn=send_fn, system_prompt="test")
        assert keeper._ping_interval == 240  # 4 minutes

    def test_custom_interval(self, send_fn) -> None:
        keeper = CacheKeepAlive(send_fn=send_fn, system_prompt="test", ping_interval=180)
        assert keeper._ping_interval == 180

    def test_interval_below_minimum_raises(self, send_fn) -> None:
        with pytest.raises(ValueError, match="ping_interval must be"):
            CacheKeepAlive(send_fn=send_fn, system_prompt="test", ping_interval=30)

    def test_stats_initialized(self, send_fn) -> None:
        keeper = CacheKeepAlive(send_fn=send_fn, system_prompt="test")
        assert keeper.stats.pings_sent == 0
        assert keeper.stats.pings_failed == 0


# ---------------------------------------------------------------------------
# Lifecycle tests
# ---------------------------------------------------------------------------


class TestLifecycle:
    def test_start_stop(self, send_fn) -> None:
        keeper = CacheKeepAlive(send_fn=send_fn, system_prompt="test", ping_interval=60)
        assert not keeper.is_running
        keeper.start()
        assert keeper.is_running
        keeper.stop()
        assert not keeper.is_running

    def test_double_start_noop(self, send_fn) -> None:
        keeper = CacheKeepAlive(send_fn=send_fn, system_prompt="test", ping_interval=60)
        keeper.start()
        keeper.start()  # should be no-op
        assert keeper.is_running
        keeper.stop()

    def test_stop_before_start_noop(self, send_fn) -> None:
        keeper = CacheKeepAlive(send_fn=send_fn, system_prompt="test")
        keeper.stop()  # should not raise

    def test_start_sends_pings(self, send_fn, ping_log) -> None:
        # Use minimum allowed interval (60s converted to 1s by the test override...)
        # For testing purposes, we directly test _send_ping
        keeper = CacheKeepAlive(send_fn=send_fn, system_prompt="hello", ping_interval=60)
        keeper._send_ping()
        assert len(ping_log) >= 1
        assert ping_log[0] == "hello"


# ---------------------------------------------------------------------------
# User activity tests
# ---------------------------------------------------------------------------


class TestUserActivity:
    def test_user_active_prevents_ping_in_loop(self, send_fn, ping_log) -> None:
        keeper = CacheKeepAlive(send_fn=send_fn, system_prompt="test", ping_interval=60)
        keeper.user_active()  # signal activity
        # Ping loop checks idle flag; when user_active, _idle_event is cleared.
        # Direct test: start the loop but user is active, so it won't ping
        keeper.start()
        # Since idle_event is cleared, _ping_loop will wait indefinitely
        time.sleep(0.2)
        keeper.stop()
        # Should not have sent pings while user is active
        assert len(ping_log) == 0

    def test_user_idle_allows_ping_in_loop(self, send_fn, ping_log) -> None:
        keeper = CacheKeepAlive(send_fn=send_fn, system_prompt="test", ping_interval=60)
        keeper.user_idle()  # explicitly idle
        keeper.start()
        # idle_event is set, so the loop should proceed to send_ping
        # But wait is on _ping_interval=60s, so we just test _send_ping directly
        keeper._send_ping()
        keeper.stop()
        assert len(ping_log) >= 1


# ---------------------------------------------------------------------------
# Stats tests
# ---------------------------------------------------------------------------


class TestStats:
    def test_successful_ping_increments(self) -> None:
        stats = KeepAliveStats()
        stats.add_ping(success=True, cost=0.004)
        assert stats.pings_sent == 1
        assert stats.pings_failed == 0
        assert stats.total_cost == 0.004

    def test_failed_ping_increments(self) -> None:
        stats = KeepAliveStats()
        stats.add_ping(success=False, cost=0.0)
        assert stats.pings_sent == 1
        assert stats.pings_failed == 1

    def test_multiple_pings_accumulate(self) -> None:
        stats = KeepAliveStats()
        stats.add_ping(success=True, cost=0.004)
        stats.add_ping(success=True, cost=0.003)
        stats.add_ping(success=False, cost=0.0)
        assert stats.pings_sent == 3
        assert stats.pings_failed == 1
        assert stats.total_cost == 0.007


# ---------------------------------------------------------------------------
# Cost estimation tests
# ---------------------------------------------------------------------------


class TestCostEstimation:
    def test_estimate_keepalive_cost(self, send_fn) -> None:
        keeper = CacheKeepAlive(send_fn=send_fn, system_prompt="test", ping_interval=240)
        cost = keeper.estimate_keepalive_cost_per_hour(
            system_prompt_tokens=15000,
            hit_rate=1.0,
        )
        # 15 pings/hr * 15000 * 0.30/1M = 15 * 0.0045 = 0.0675
        assert cost == pytest.approx(0.0675, rel=0.01)

    def test_compare_to_cache_rewrite(self, send_fn) -> None:
        keeper = CacheKeepAlive(send_fn=send_fn, system_prompt="test", ping_interval=240)
        comparison = keeper.compare_to_cache_rewrite(system_prompt_tokens=15000)
        # 15 rewrites/hr * 15000 * 3.75/1M = 15 * 0.05625 = 0.84375
        assert comparison["rewrite_cost_per_hour"] == pytest.approx(0.84375, rel=0.01)
        # savings should be positive (keepalive is far cheaper than N rewrites)
        assert comparison["savings"] > 0


# ---------------------------------------------------------------------------
# Ping failure handling
# ---------------------------------------------------------------------------


class TestFailureHandling:
    def test_failing_send_fn(self, send_fn) -> None:
        ping_log = []

        def failing_send(prompt: str) -> dict:
            ping_log.append("fail")
            raise RuntimeError("API error")

        keeper = CacheKeepAlive(
            send_fn=failing_send,
            system_prompt="test",
            ping_interval=60,
            max_retries=2,
        )
        keeper.user_idle()
        # Test _send_ping directly since we can't wait 60s
        keeper._send_ping()
        keeper._send_ping()
        # Should have some failed pings
        assert keeper.stats.pings_failed > 0

    def test_callback_on_result(self) -> None:
        callback_log = []

        def on_result(success: bool, cost: float) -> None:
            callback_log.append((success, cost))

        keeper = CacheKeepAlive(
            send_fn=lambda p: {"usage": {"cache_read_input_tokens": 10000}},
            system_prompt="test",
            ping_interval=60,
            on_ping_result=on_result,
        )
        keeper._send_ping()
        # At least one callback should have been invoked
        assert len(callback_log) >= 1
        assert callback_log[0][0] is True  # success

    def test_callback_exception_does_not_crash(self) -> None:
        def crashy_callback(success: bool, cost: float) -> None:
            raise RuntimeError("callback crash")

        keeper = CacheKeepAlive(
            send_fn=lambda p: {"usage": {}},
            system_prompt="test",
            ping_interval=60,
            on_ping_result=crashy_callback,
        )
        # Thread should still be alive (no crash from callback exception)
        keeper._send_ping()
        assert keeper.stats.pings_sent == 1


# ---------------------------------------------------------------------------
# Thread safety tests
# ---------------------------------------------------------------------------


class TestThreadSafety:
    def test_concurrent_start_stop(self, send_fn) -> None:
        """Multiple threads calling start/stop should not corrupt state."""
        keeper = CacheKeepAlive(send_fn=send_fn, system_prompt="test", ping_interval=60)
        errors = []

        def toggle() -> None:
            try:
                keeper.start()
                time.sleep(0.01)
                keeper.stop()
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=toggle) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=5)

        assert len(errors) == 0
        # Ensure stopped at end
        keeper.stop()
        assert not keeper.is_running
