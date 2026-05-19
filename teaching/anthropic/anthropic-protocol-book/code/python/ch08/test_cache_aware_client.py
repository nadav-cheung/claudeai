"""
Tests for Chapter 8: Cache-Aware Client.
"""

import pytest

from cache_aware_client import (
    CacheAwareClient,
    CacheBreakevenResult,
    CacheUsage,
    cache_breakeven_analysis,
    DEFAULT_BASE_PRICE_PER_MTok,
    DEFAULT_READ_PRICE_PER_MTok,
    DEFAULT_WRITE_PRICE_PER_MTok,
    MAX_BREAKPOINTS,
    MIN_CACHEABLE_TOKENS_DEFAULT,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def client() -> CacheAwareClient:
    return CacheAwareClient()


@pytest.fixture
def simple_request() -> dict:
    return {
        "model": "claude-sonnet-4-20250514",
        "max_tokens": 1024,
        "system": [
            {"type": "text", "text": "You are an expert programmer."}
        ],
        "messages": [
            {"role": "user", "content": "Write a function."},
            {"role": "assistant", "content": "Here is the function..."},
        ],
    }


# ---------------------------------------------------------------------------
# Cache marker injection tests
# ---------------------------------------------------------------------------


class TestCacheMarkerInjection:
    def test_inject_single_breakpoint(self, client: CacheAwareClient, simple_request: dict) -> None:
        result = client.create_with_cache(simple_request, cache_points=[0])
        msgs = result["messages"]
        # First message should have cache_control
        content = msgs[0]["content"]
        assert isinstance(content, list)
        assert content[-1].get("cache_control") == {"type": "ephemeral"}

    def test_inject_last_message_breakpoint(self, client: CacheAwareClient, simple_request: dict) -> None:
        result = client.create_with_cache(simple_request, cache_points=[-1])
        msgs = result["messages"]
        content = msgs[-1]["content"]
        assert isinstance(content, list)
        assert content[-1].get("cache_control") == {"type": "ephemeral"}

    def test_inject_system_string(self, client: CacheAwareClient) -> None:
        req = {
            "model": "test",
            "max_tokens": 100,
            "system": "You are helpful.",
            "messages": [{"role": "user", "content": "Hi"}],
        }
        result = client.create_with_cache(req, cache_points=[0])
        system = result["system"]
        assert isinstance(system, list)
        assert system[-1].get("cache_control") == {"type": "ephemeral"}

    def test_inject_no_cache_points(self, client: CacheAwareClient, simple_request: dict) -> None:
        result = client.create_with_cache(simple_request, cache_points=[])
        assert result["messages"] == simple_request["messages"]

    def test_too_many_breakpoints_raises(self, client: CacheAwareClient, simple_request: dict) -> None:
        with pytest.raises(ValueError, match="Too many cache points"):
            client.create_with_cache(simple_request, cache_points=[0, 1, 2, 3, 4])

    def test_out_of_range_points_ignored(self, client: CacheAwareClient, simple_request: dict) -> None:
        result = client.create_with_cache(simple_request, cache_points=[100])
        assert result["messages"] == simple_request["messages"]

    def test_multiple_breakpoints(self, client: CacheAwareClient) -> None:
        req = {
            "model": "test",
            "max_tokens": 100,
            "messages": [
                {"role": "user", "content": "A"},
                {"role": "assistant", "content": "B"},
                {"role": "user", "content": "C"},
                {"role": "assistant", "content": "D"},
            ],
        }
        result = client.create_with_cache(req, cache_points=[0, 2])
        msgs = result["messages"]
        for i in [0, 2]:
            content = msgs[i]["content"]
            assert isinstance(content, list)
            assert content[-1].get("cache_control") == {"type": "ephemeral"}
        # Other messages should not have cache_control
        for i in [1, 3]:
            assert "cache_control" not in str(msgs[i])

    def test_system_list_blocks_get_cache_on_last(self, client: CacheAwareClient) -> None:
        req = {
            "model": "test",
            "max_tokens": 100,
            "system": [
                {"type": "text", "text": "Block 1"},
                {"type": "text", "text": "Block 2"},
            ],
            "messages": [{"role": "user", "content": "Hi"}],
        }
        result = client.create_with_cache(req, cache_points=[0])
        system = result["system"]
        # First block should NOT have cache_control
        assert "cache_control" not in system[0]
        # Last block SHOULD have cache_control
        assert system[1].get("cache_control") == {"type": "ephemeral"}

    def test_original_request_not_mutated(self, client: CacheAwareClient, simple_request: dict) -> None:
        import copy
        original = copy.deepcopy(simple_request)
        client.create_with_cache(simple_request, cache_points=[0])
        assert simple_request == original


# ---------------------------------------------------------------------------
# Cost estimation tests
# ---------------------------------------------------------------------------


class TestCostEstimation:
    def test_estimate_savings_positive(self, client: CacheAwareClient) -> None:
        # 15000 tokens, 10 requests: should save significantly
        savings = client.estimate_cache_savings(15000, 10)
        assert savings > 0

    def test_estimate_savings_single_request(self, client: CacheAwareClient) -> None:
        savings = client.estimate_cache_savings(15000, 1)
        # Single request: write is more expensive than base, so negative savings
        assert savings < 0

    def test_estimate_savings_scales_with_tokens(self, client: CacheAwareClient) -> None:
        small = client.estimate_cache_savings(1000, 10)
        large = client.estimate_cache_savings(50000, 10)
        assert large > small

    def test_should_cache_true(self, client: CacheAwareClient) -> None:
        assert client.should_cache(15000, 10) is True

    def test_should_cache_false_below_min(self, client: CacheAwareClient) -> None:
        assert client.should_cache(500, 10) is False

    def test_should_cache_false_single_request(self, client: CacheAwareClient) -> None:
        assert client.should_cache(15000, 1) is False

    def test_custom_pricing(self) -> None:
        client = CacheAwareClient(
            write_price_per_mtok=5.00,
            read_price_per_mtok=0.50,
            base_price_per_mtok=4.00,
        )
        savings = client.estimate_cache_savings(10000, 5)
        # Expected: no_cache = 10000*5*4.00/1M = 0.20
        # with_cache = 10000*5.00/1M + 10000*4*0.50/1M = 0.05 + 0.02 = 0.07
        # savings = 0.13
        assert savings == pytest.approx(0.13, rel=0.01)


# ---------------------------------------------------------------------------
# Breakeven analysis tests
# ---------------------------------------------------------------------------


class TestBreakevenAnalysis:
    def test_breakeven_default_pricing(self, client: CacheAwareClient) -> None:
        result = client.breakeven_analysis(15000)
        # With default pricing (w=3.75, r=0.30, b=3.00):
        # breakeven = (w-r)/(b-r) = (3.45) / (2.70) ≈ 1.28
        assert result.breakeven_reads == pytest.approx(1.3, abs=0.1)
        assert result.is_worthwhile is True

    def test_breakeven_savings_at_50_requests(self, client: CacheAwareClient) -> None:
        result = client.breakeven_analysis(15000)
        savings_at_50 = next(s for s in result.savings if s["requests"] == 50)
        assert savings_at_50["savings_pct"] > 80

    def test_breakeven_savings_at_100_requests(self, client: CacheAwareClient) -> None:
        result = client.breakeven_analysis(15000)
        savings_at_100 = next(s for s in result.savings if s["requests"] == 100)
        assert savings_at_100["savings_pct"] > 85

    def test_breakeven_analysis_result_structure(self, client: CacheAwareClient) -> None:
        result = client.breakeven_analysis(15000)
        assert isinstance(result, CacheBreakevenResult)
        assert result.breakeven_reads > 0
        assert len(result.savings) == 4
        for s in result.savings:
            assert "requests" in s
            assert "no_cache_cost" in s
            assert "with_cache_cost" in s
            assert "savings" in s
            assert "savings_pct" in s


# ---------------------------------------------------------------------------
# Standalone breakeven function tests (self-test Question 4)
# ---------------------------------------------------------------------------


class TestCacheBreakevenAnalysisFunction:
    def test_basic_breakeven(self) -> None:
        result = cache_breakeven_analysis(
            write_price_per_mtok=3.75,
            read_price_per_mtok=0.30,
            base_price_per_mtok=3.00,
            cacheable_tokens=15000,
        )
        assert result["breakeven_reads"] == pytest.approx(1.3, abs=0.1)
        assert result["is_worthwhile"] is True

    def test_viable_within_5min(self) -> None:
        result = cache_breakeven_analysis(
            write_price_per_mtok=3.75,
            read_price_per_mtok=0.30,
            base_price_per_mtok=3.00,
            cacheable_tokens=15000,
        )
        # Breakeven at ~1.3 reads; 5 requests/5min is more than enough
        assert result["viable_within_5min_ttl"] is True

    def test_not_viable_with_expensive_write(self) -> None:
        result = cache_breakeven_analysis(
            write_price_per_mtok=30.00,
            read_price_per_mtok=0.30,
            base_price_per_mtok=3.00,
            cacheable_tokens=15000,
        )
        # Write is 10x base: breakeven ~11 reads, not viable in 5-min TTL
        assert result["breakeven_reads"] > 5
        assert result["viable_within_5min_ttl"] is False

    def test_savings_projections_structure(self) -> None:
        result = cache_breakeven_analysis(
            cacheable_tokens=10000,
        )
        assert "savings_at_5" in result
        assert "savings_at_10" in result
        assert "savings_at_50" in result
        assert "savings_at_100" in result
        assert result["savings_at_100"] > result["savings_at_5"]


# ---------------------------------------------------------------------------
# Usage extraction tests
# ---------------------------------------------------------------------------


class TestUsageExtraction:
    def test_extract_from_realistic_response(self) -> None:
        response = {
            "usage": {
                "input_tokens": 15000,
                "output_tokens": 500,
                "cache_creation_input_tokens": 14800,
                "cache_read_input_tokens": 0,
            }
        }
        usage = CacheAwareClient.extract_usage(response)
        assert usage.input_tokens == 15000
        assert usage.cache_creation_tokens == 14800
        assert usage.cache_read_tokens == 0
        assert usage.uncached_input_tokens == 200

    def test_extract_cache_hit_response(self) -> None:
        response = {
            "usage": {
                "input_tokens": 15000,
                "output_tokens": 500,
                "cache_creation_input_tokens": 0,
                "cache_read_input_tokens": 14800,
            }
        }
        usage = CacheAwareClient.extract_usage(response)
        assert usage.cache_hit_ratio == pytest.approx(14800 / 15000, rel=0.01)

    def test_extract_empty_usage(self) -> None:
        response = {"usage": {}}
        usage = CacheAwareClient.extract_usage(response)
        assert usage.input_tokens == 0
        assert usage.cache_hit_ratio == 0.0

    def test_monitor_cache_hit_rate(self) -> None:
        usages = [
            CacheUsage(input_tokens=15000, cache_creation_tokens=14800, cache_read_tokens=0),
            CacheUsage(input_tokens=15000, cache_creation_tokens=0, cache_read_tokens=14800),
            CacheUsage(input_tokens=15000, cache_creation_tokens=0, cache_read_tokens=14800),
        ]
        metrics = CacheAwareClient.monitor_cache_hit_rate(usages)
        assert metrics["hit_rate"] == pytest.approx(29600 / 45000, rel=0.01)
        assert 0 <= metrics["waste_rate"] <= 1.0

    def test_monitor_empty(self) -> None:
        metrics = CacheAwareClient.monitor_cache_hit_rate([])
        assert metrics["hit_rate"] == 0.0


# ---------------------------------------------------------------------------
# Protocol constants tests
# ---------------------------------------------------------------------------


class TestProtocolConstants:
    def test_pricing_defaults(self) -> None:
        assert DEFAULT_WRITE_PRICE_PER_MTok == 3.75
        assert DEFAULT_READ_PRICE_PER_MTok == 0.30
        assert DEFAULT_BASE_PRICE_PER_MTok == 3.00

    def test_write_is_premium(self) -> None:
        # Cache write must be more expensive than base input
        assert DEFAULT_WRITE_PRICE_PER_MTok > DEFAULT_BASE_PRICE_PER_MTok

    def test_read_is_discounted(self) -> None:
        # Cache read must be cheaper than base input
        assert DEFAULT_READ_PRICE_PER_MTok < DEFAULT_BASE_PRICE_PER_MTok

    def test_max_breakpoints(self) -> None:
        assert MAX_BREAKPOINTS == 4

    def test_min_cacheable_tokens(self) -> None:
        assert MIN_CACHEABLE_TOKENS_DEFAULT == 1024
