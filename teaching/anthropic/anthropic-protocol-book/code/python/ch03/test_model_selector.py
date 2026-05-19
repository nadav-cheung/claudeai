"""
Tests for the Chapter 3 Model Selector and Token Counter.
"""

from __future__ import annotations

import math

import pytest

from model_selector import (
    MODEL_REGISTRY,
    ModelSelector,
    ModelSpec,
    TokenCounter,
    select_model_for_scenario,
)


# ---------------------------------------------------------------------------
# ModelSelector Tests
# ---------------------------------------------------------------------------

class TestModelSelector:
    """Tests for ModelSelector.select() decision logic."""

    @pytest.fixture
    def selector(self) -> ModelSelector:
        return ModelSelector()

    # ── Agentic complexity ──

    def test_select_agentic_always_opus(self, selector: ModelSelector) -> None:
        result = selector.select(task_complexity="agentic", budget="high")
        assert result.model_id == "claude-opus-4-7"

    def test_select_agentic_even_with_low_budget(self, selector: ModelSelector) -> None:
        result = selector.select(task_complexity="agentic", budget="low")
        assert result.model_id == "claude-opus-4-7"

    # ── Long context ──

    def test_select_long_context_uses_sonnet_46(self, selector: ModelSelector) -> None:
        result = selector.select(
            task_complexity="medium", budget="high",
            requires_long_context=True,
        )
        assert result.model_id == "claude-sonnet-4-6"

    def test_select_context_above_200k_uses_long_context_model(
        self, selector: ModelSelector,
    ) -> None:
        result = selector.select(
            task_complexity="medium", budget="high",
            context_needed=500_000,
        )
        assert result.model_id == "claude-sonnet-4-6"

    def test_select_long_context_agentic_uses_opus(
        self, selector: ModelSelector,
    ) -> None:
        result = selector.select(
            task_complexity="agentic", budget="high",
            requires_long_context=True,
        )
        assert result.model_id == "claude-opus-4-7"

    # ── High complexity ──

    def test_select_high_complexity_low_budget_sonnet(
        self, selector: ModelSelector,
    ) -> None:
        result = selector.select(task_complexity="high", budget="low")
        assert result.model_id == "claude-sonnet-4-6"

    def test_select_high_complexity_medium_budget_opus(
        self, selector: ModelSelector,
    ) -> None:
        result = selector.select(task_complexity="high", budget="medium")
        assert result.model_id == "claude-opus-4-7"

    def test_select_high_complexity_high_budget_opus(
        self, selector: ModelSelector,
    ) -> None:
        result = selector.select(task_complexity="high", budget="high")
        assert result.model_id == "claude-opus-4-7"

    # ── Latency sensitive ──

    def test_select_latency_sensitive_haiku(self, selector: ModelSelector) -> None:
        result = selector.select(
            task_complexity="medium", budget="high",
            latency_sensitive=True,
        )
        assert result.model_id == "claude-haiku-4-5"

    # ── Low budget ──

    def test_select_low_budget_defaults_haiku(self, selector: ModelSelector) -> None:
        result = selector.select(
            task_complexity="medium", budget="low",
        )
        assert result.model_id == "claude-haiku-4-5"

    # ── Default ──

    def test_select_defaults_to_sonnet(self, selector: ModelSelector) -> None:
        result = selector.select(
            task_complexity="medium", budget="high",
        )
        assert result.model_id == "claude-sonnet-4-6"

    # ── Validation ──

    def test_select_raises_on_invalid_complexity(self, selector: ModelSelector) -> None:
        with pytest.raises(ValueError, match="task_complexity"):
            selector.select(task_complexity="unknown", budget="high")

    def test_select_raises_on_invalid_budget(self, selector: ModelSelector) -> None:
        with pytest.raises(ValueError, match="budget"):
            selector.select(task_complexity="medium", budget="unlimited")

    # ── Reasoning string ──

    def test_select_returns_reasoning(self, selector: ModelSelector) -> None:
        result = selector.select(
            task_complexity="medium", budget="high",
        )
        assert len(result.reasoning) > 0
        assert isinstance(result.reasoning, str)

    def test_select_returns_model_spec(self, selector: ModelSelector) -> None:
        result = selector.select(
            task_complexity="medium", budget="high",
        )
        assert isinstance(result.model, ModelSpec)
        assert result.model.api_id == result.model_id


# ---------------------------------------------------------------------------
# CostEstimate Tests
# ---------------------------------------------------------------------------

class TestCostEstimate:
    """Tests for ModelSelector.cost_estimate()."""

    @pytest.fixture
    def selector(self) -> ModelSelector:
        return ModelSelector()

    def test_standard_opus_cost(self, selector: ModelSelector) -> None:
        cost = selector.cost_estimate("claude-opus-4-7", 1_000_000, 1_000_000)
        assert cost == pytest.approx(30.0)  # $5 + $25

    def test_standard_sonnet_cost(self, selector: ModelSelector) -> None:
        cost = selector.cost_estimate("claude-sonnet-4-6", 1_000_000, 1_000_000)
        assert cost == pytest.approx(18.0)  # $3 + $15

    def test_standard_haiku_cost(self, selector: ModelSelector) -> None:
        cost = selector.cost_estimate("claude-haiku-4-5", 1_000_000, 1_000_000)
        assert cost == pytest.approx(6.0)  # $1 + $5

    def test_zero_tokens_zero_cost(self, selector: ModelSelector) -> None:
        cost = selector.cost_estimate("claude-opus-4-7", 0, 0)
        assert cost == 0.0

    def test_cache_read_cost(self, selector: ModelSelector) -> None:
        # Cache read is 0.1x base input price.
        cost = selector.cost_estimate(
            "claude-opus-4-7", 1_000_000, 0, cache_hit=True,
        )
        assert cost == pytest.approx(0.50)  # $5 * 0.1

    def test_cache_write_5m_cost(self, selector: ModelSelector) -> None:
        cost = selector.cost_estimate(
            "claude-opus-4-7", 1_000_000, 0, cache_duration="5m",
        )
        assert cost == pytest.approx(6.25)  # $5 * 1.25

    def test_cache_write_1h_cost(self, selector: ModelSelector) -> None:
        cost = selector.cost_estimate(
            "claude-opus-4-7", 1_000_000, 0, cache_duration="1h",
        )
        assert cost == pytest.approx(10.00)  # $5 * 2.0

    def test_batch_discount(self, selector: ModelSelector) -> None:
        cost = selector.cost_estimate(
            "claude-sonnet-4-6", 1_000_000, 1_000_000, batch=True,
        )
        assert cost == pytest.approx(9.00)  # $1.50 + $7.50

    def test_batch_plus_cache_read(self, selector: ModelSelector) -> None:
        # Batch + Cache Read: 50% * 0.1 = 5% of base input price.
        cost = selector.cost_estimate(
            "claude-opus-4-7", 1_000_000, 0, cache_hit=True, batch=True,
        )
        assert cost == pytest.approx(0.25)  # $5 * 0.5 * 0.1

    def test_accepts_model_spec_instance(self, selector: ModelSelector) -> None:
        spec = MODEL_REGISTRY["claude-opus-4-7"]
        cost = selector.cost_estimate(spec, 1_000_000, 0)
        assert cost == pytest.approx(5.00)

    def test_partial_tokens(self, selector: ModelSelector) -> None:
        cost = selector.cost_estimate("claude-haiku-4-5", 500, 250)
        assert cost > 0
        assert cost < 0.01  # very small


# ---------------------------------------------------------------------------
# CostEstimate Multi Tests
# ---------------------------------------------------------------------------

class TestCostEstimateMulti:
    """Tests for ModelSelector.cost_estimate_multi()."""

    @pytest.fixture
    def selector(self) -> ModelSelector:
        return ModelSelector()

    def test_multi_no_cache(self, selector: ModelSelector) -> None:
        result = selector.cost_estimate_multi(
            "claude-sonnet-4-6",
            num_requests=100,
            input_tokens_per_request=5_000,
            output_tokens_per_request=500,
            cached_input_tokens=0,
        )
        assert result["write_cost"] == 0.0
        assert result["read_cost"] == 0.0
        assert result["savings_pct"] == 0.0
        assert result["total_cost"] > 0

    def test_multi_with_cache(self, selector: ModelSelector) -> None:
        result = selector.cost_estimate_multi(
            "claude-sonnet-4-6",
            num_requests=100,
            input_tokens_per_request=3_000,
            output_tokens_per_request=500,
            cached_input_tokens=20_000,
            cache_duration="5m",
        )
        assert result["write_cost"] > 0
        assert result["read_cost"] > 0
        assert result["savings"] > 0
        assert result["savings_pct"] > 0

    def test_multi_with_batch(self, selector: ModelSelector) -> None:
        result = selector.cost_estimate_multi(
            "claude-haiku-4-5",
            num_requests=10_000,
            input_tokens_per_request=2_000,
            output_tokens_per_request=200,
            cached_input_tokens=0,
            batch=True,
        )
        # Verify batch discount applied.
        assert result["total_cost"] < 30  # rough sanity check

    def test_multi_savings_calculation(self, selector: ModelSelector) -> None:
        """Cache should save money when enough reads occur."""
        result = selector.cost_estimate_multi(
            "claude-opus-4-7",
            num_requests=10,  # well above breakeven
            input_tokens_per_request=1_000,
            output_tokens_per_request=200,
            cached_input_tokens=50_000,
            cache_duration="5m",
        )
        assert result["savings"] > 0
        assert result["savings_pct"] > 0
        assert result["total_cost"] < result["no_cache_cost"]


# ---------------------------------------------------------------------------
# CacheBreakeven Tests
# ---------------------------------------------------------------------------

class TestCacheBreakeven:
    """Tests for ModelSelector.cache_breakeven()."""

    @pytest.fixture
    def selector(self) -> ModelSelector:
        return ModelSelector()

    def test_breakeven_5m_is_reasonable(self, selector: ModelSelector) -> None:
        result = selector.cache_breakeven("claude-opus-4-7")
        assert result["5m_breakeven_reads"] == 2  # 6.25 / (5 - 0.5) = 1.39 → ceil → 2

    def test_breakeven_1h_is_reasonable(self, selector: ModelSelector) -> None:
        result = selector.cache_breakeven("claude-opus-4-7")
        assert result["1h_breakeven_reads"] == 3  # 10 / (5 - 0.5) = 2.22 → ceil → 3

    def test_breakeven_all_models(self, selector: ModelSelector) -> None:
        """All current models should have the same cache multipliers,
        so breakeven should be identical."""
        for model_id in ("claude-opus-4-7", "claude-sonnet-4-6", "claude-haiku-4-5"):
            result = selector.cache_breakeven(model_id)
            assert result["5m_breakeven_reads"] == 2
            assert result["1h_breakeven_reads"] == 3


# ---------------------------------------------------------------------------
# TokenCounter Tests
# ---------------------------------------------------------------------------

class TestTokenCounter:
    """Tests for TokenCounter.count() and estimate_request_tokens()."""

    @pytest.fixture
    def counter(self) -> TokenCounter:
        return TokenCounter()

    def test_empty_string_zero(self, counter: TokenCounter) -> None:
        assert counter.count("") == 0

    def test_short_text(self, counter: TokenCounter) -> None:
        tokens = counter.count("Hello")
        assert tokens >= 1

    def test_english_ratio(self, counter: TokenCounter) -> None:
        # ~4 chars per token for English
        text = "Hello, world! This is a test."
        tokens = counter.count(text)
        expected = math.ceil(len(text) / 4)
        assert tokens == expected

    def test_chinese_ratio(self, counter: TokenCounter) -> None:
        text = "你好世界这是一个测试"
        tokens = counter.count(text, "chinese")
        expected = math.ceil(len(text) / 2)
        assert tokens == expected

    def test_code_ratio(self, counter: TokenCounter) -> None:
        text = "def foo(x): return x + 1"
        tokens = counter.count(text, "code")
        expected = math.ceil(len(text) / 3.5)
        assert tokens == expected

    def test_json_ratio(self, counter: TokenCounter) -> None:
        text = '{"key": "value", "num": 42}'
        tokens = counter.count(text, "json")
        expected = math.ceil(len(text) / 3)
        assert tokens == expected

    def test_opus_47_adjustment(self) -> None:
        counter = TokenCounter(opus_47_adjustment=True)
        text = "Hello, world! This is a test."
        standard = math.ceil(len(text) / 4)
        adjusted = counter.count(text)
        assert adjusted == round(standard * 1.2)

    def test_estimate_simple_messages(self, counter: TokenCounter) -> None:
        messages = [
            {"role": "user", "content": "Hello, Claude!"},
        ]
        result = counter.estimate_request_tokens(messages)
        assert result["total_input_tokens"] > 0
        assert result["messages_tokens"] > 0
        assert result["system_tokens"] == 0
        assert result["tools_tokens"] == 0

    def test_estimate_with_system(self, counter: TokenCounter) -> None:
        messages = [{"role": "user", "content": "Hi"}]
        result = counter.estimate_request_tokens(
            messages,
            system="You are a helpful assistant.",
        )
        assert result["system_tokens"] > 0
        assert result["total_input_tokens"] > result["messages_tokens"]

    def test_estimate_with_tools(self, counter: TokenCounter) -> None:
        messages = [{"role": "user", "content": "What is the weather?"}]
        tools = [
            {
                "name": "get_weather",
                "description": "Get the current weather",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "location": {"type": "string"},
                    },
                },
            },
        ]
        result = counter.estimate_request_tokens(messages, tools=tools)
        assert result["tools_tokens"] > 0
        # Tool system prompt overhead should be included
        assert result["tools_tokens"] >= 346

    def test_estimate_content_blocks(self, counter: TokenCounter) -> None:
        messages = [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "Hello"},
                    {"type": "text", "text": "World"},
                ],
            },
        ]
        result = counter.estimate_request_tokens(messages)
        assert result["messages_tokens"] > 0

    def test_estimate_tool_result(self, counter: TokenCounter) -> None:
        messages = [
            {"role": "user", "content": "What is the weather?"},
            {
                "role": "assistant",
                "content": [
                    {
                        "type": "tool_use",
                        "name": "get_weather",
                        "input": {"location": "Beijing"},
                    },
                ],
            },
            {
                "role": "user",
                "content": [
                    {
                        "type": "tool_result",
                        "content": "Sunny, 25C",
                    },
                ],
            },
        ]
        result = counter.estimate_request_tokens(messages)
        assert result["total_input_tokens"] > 0

    def test_estimate_returns_breakdown(self, counter: TokenCounter) -> None:
        messages = [{"role": "user", "content": "Hi"}]
        result = counter.estimate_request_tokens(messages, system="Be helpful.")
        assert "system_tokens" in result
        assert "messages_tokens" in result
        assert "tools_tokens" in result
        assert "overhead_tokens" in result
        assert "total_input_tokens" in result
        assert result["total_input_tokens"] == (
            result["system_tokens"]
            + result["messages_tokens"]
            + result["tools_tokens"]
            + result["overhead_tokens"]
        )


# ---------------------------------------------------------------------------
# Model Registry Tests
# ---------------------------------------------------------------------------

class TestModelRegistry:
    """Tests for the model registry data integrity."""

    def test_all_current_models_exist(self) -> None:
        expected = [
            "claude-opus-4-7",
            "claude-sonnet-4-6",
            "claude-haiku-4-5",
            "claude-opus-4-6",
            "claude-sonnet-4-5",
            "claude-opus-4-5",
            "claude-opus-4-1",
        ]
        for model_id in expected:
            assert model_id in MODEL_REGISTRY, f"Missing model: {model_id}"

    def test_prices_are_positive(self) -> None:
        for spec in MODEL_REGISTRY.values():
            assert spec.input_price_per_mtok > 0
            assert spec.output_price_per_mtok > 0
            assert spec.output_price_per_mtok > spec.input_price_per_mtok

    def test_context_windows_are_positive(self) -> None:
        for spec in MODEL_REGISTRY.values():
            assert spec.context_window > 0
            assert spec.max_output > 0
            assert spec.max_output <= spec.context_window

    def test_cache_multipliers_are_reasonable(self) -> None:
        for spec in MODEL_REGISTRY.values():
            assert spec.cache_write_5m_mult > 1.0
            assert spec.cache_write_1h_mult > spec.cache_write_5m_mult
            assert 0 < spec.cache_read_mult < 1.0

    def test_opus_47_vs_46_pricing_identical(self) -> None:
        opus47 = MODEL_REGISTRY["claude-opus-4-7"]
        opus46 = MODEL_REGISTRY["claude-opus-4-6"]
        assert opus47.input_price_per_mtok == opus46.input_price_per_mtok
        assert opus47.output_price_per_mtok == opus46.output_price_per_mtok
        # Same price but 4.7 has adaptive thinking, 4.6 has extended thinking.
        assert opus47.supports_adaptive_thinking
        assert opus46.supports_extended_thinking

    def test_opus_41_is_expensive(self) -> None:
        opus41 = MODEL_REGISTRY["claude-opus-4-1"]
        opus47 = MODEL_REGISTRY["claude-opus-4-7"]
        assert opus41.input_price_per_mtok == 3 * opus47.input_price_per_mtok
        assert opus41.output_price_per_mtok == 3 * opus47.output_price_per_mtok


# ---------------------------------------------------------------------------
# select_model_for_scenario Tests (Self-test Question 3)
# ---------------------------------------------------------------------------

class TestSelectModelForScenario:
    """Tests for the standalone select_model_for_scenario function."""

    def test_agentic_scenario(self) -> None:
        result = select_model_for_scenario({
            "complexity": "agentic",
            "budget": "medium",
        })
        assert result == "claude-opus-4-7"

    def test_long_context_scenario(self) -> None:
        result = select_model_for_scenario({
            "requires_long_context": True,
            "complexity": "medium",
            "budget": "medium",
        })
        assert result == "claude-sonnet-4-6"

    def test_high_complexity_low_budget(self) -> None:
        result = select_model_for_scenario({
            "complexity": "high",
            "budget": "low",
        })
        assert result == "claude-sonnet-4-6"

    def test_high_complexity_high_budget(self) -> None:
        result = select_model_for_scenario({
            "complexity": "high",
            "budget": "high",
        })
        assert result == "claude-opus-4-7"

    def test_latency_sensitive_scenario(self) -> None:
        result = select_model_for_scenario({
            "latency_sensitive": True,
            "complexity": "medium",
            "budget": "medium",
        })
        assert result == "claude-haiku-4-5"

    def test_low_budget_scenario(self) -> None:
        result = select_model_for_scenario({
            "budget": "low",
            "complexity": "medium",
        })
        assert result == "claude-haiku-4-5"

    def test_default_scenario(self) -> None:
        result = select_model_for_scenario({
            "complexity": "medium",
            "budget": "medium",
        })
        assert result == "claude-sonnet-4-6"
