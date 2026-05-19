"""
Tests for Chapter 17: BudgetController.
"""

from __future__ import annotations

import pytest

from budget_controller import (
    BudgetConfig,
    BudgetController,
    BudgetDecision,
    BudgetExceededError,
    BudgetPeriod,
    MODEL_PRICING,
    estimate_cost,
    estimate_input_tokens,
    estimate_message_tokens,
)


# ---------------------------------------------------------------------------
# Cost estimation
# ---------------------------------------------------------------------------


class TestEstimateCost:
    def test_sonnet_input_cost(self) -> None:
        cost = estimate_cost("claude-sonnet-4-20250514", input_tokens=1_000_000)
        assert cost == pytest.approx(3.00, rel=0.01)

    def test_opus_cost(self) -> None:
        cost = estimate_cost(
            "claude-opus-4-20250514", input_tokens=1_000_000, output_tokens=1_000_000
        )
        assert cost == pytest.approx(90.00, rel=0.01)

    def test_haiku_input_cost(self) -> None:
        cost = estimate_cost("claude-haiku-3-5-20241022", input_tokens=1_000_000)
        assert cost == pytest.approx(0.80, rel=0.01)

    def test_cache_read_discount(self) -> None:
        # Sonnet: input $3/MTok, cache read $0.30/MTok
        cost_no_cache = estimate_cost("claude-sonnet-4-20250514", input_tokens=1_000_000)
        cost_with_cache = estimate_cost(
            "claude-sonnet-4-20250514", cache_read_tokens=1_000_000
        )
        assert cost_with_cache < cost_no_cache
        assert cost_with_cache == pytest.approx(0.30, rel=0.05)

    def test_unknown_model_fallback(self) -> None:
        cost = estimate_cost("unknown-model", input_tokens=1_000_000)
        # Falls back to sonnet pricing ($3/MTok)
        assert cost == pytest.approx(3.00, rel=0.01)

    def test_zero_tokens(self) -> None:
        cost = estimate_cost("claude-sonnet-4-20250514")
        assert cost == 0.0


# ---------------------------------------------------------------------------
# Token estimation
# ---------------------------------------------------------------------------


class TestTokenEstimation:
    def test_empty_text(self) -> None:
        assert estimate_input_tokens("") == 0

    def test_english_text(self) -> None:
        tokens = estimate_input_tokens("Hello world")
        assert tokens >= 1

    def test_long_text(self) -> None:
        text = "The quick brown fox " * 100  # ~2400 chars
        tokens = estimate_input_tokens(text)
        assert 500 <= tokens <= 700  # ~600 expected

    def test_message_tokens(self) -> None:
        messages = [
            {"role": "user", "content": "What is 2+2?"},
            {"role": "assistant", "content": "The answer is 4."},
        ]
        tokens = estimate_message_tokens(messages)
        assert tokens >= 1

    def test_multipart_content(self) -> None:
        messages = [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "Hello"},
                    {"type": "text", "text": "World"},
                ],
            }
        ]
        tokens = estimate_message_tokens(messages)
        assert tokens >= 1


# ---------------------------------------------------------------------------
# BudgetController
# ---------------------------------------------------------------------------


class TestBudgetController:
    """Tests for budget control decisions."""

    def test_initial_allow(self) -> None:
        ctrl = BudgetController(BudgetConfig(hard_limit=500.0))
        decision, model = ctrl.check("claude-sonnet-4-20250514", input_tokens=1000)
        assert decision == BudgetDecision.ALLOW
        assert model == "claude-sonnet-4-20250514"

    def test_warn_near_threshold(self) -> None:
        ctrl = BudgetController(BudgetConfig(hard_limit=100.0, warn_threshold=0.5, auto_downgrade=False))
        # Record enough to reach >50%
        ctrl.record("claude-sonnet-4-20250514", input_tokens=20_000_000)  # ~$60
        decision, model = ctrl.check("claude-sonnet-4-20250514", input_tokens=1000)
        assert decision == BudgetDecision.WARN

    def test_block_exceeded(self) -> None:
        ctrl = BudgetController(BudgetConfig(hard_limit=10.0))
        # Spend $3 + $15 = $18 > $10
        ctrl.record("claude-sonnet-4-20250514", input_tokens=1_000_000, output_tokens=1_000_000)
        assert ctrl.spent > 10.0
        decision, _ = ctrl.check("claude-sonnet-4-20250514", input_tokens=100)
        assert decision == BudgetDecision.BLOCK

    def test_block_projected(self) -> None:
        ctrl = BudgetController(BudgetConfig(hard_limit=10.0))
        # Try to make a call that would exceed budget
        decision, _ = ctrl.check(
            "claude-opus-4-20250514",
            input_tokens=1_000_000,
            output_tokens=1_000_000,  # ~$90 for Opus
        )
        assert decision == BudgetDecision.BLOCK

    def test_auto_downgrade(self) -> None:
        ctrl = BudgetController(
            BudgetConfig(hard_limit=20.0, warn_threshold=0.5, auto_downgrade=True)
        )
        # Spend ~$15 → above warn threshold
        ctrl.record("claude-sonnet-4-20250514", input_tokens=5_000_000)
        # Request Opus → should downgrade to Sonnet (already using Sonnet)
        decision, model = ctrl.check("claude-opus-4-20250514", input_tokens=1000)
        assert decision == BudgetDecision.DOWNGRADE
        assert model != "claude-opus-4-20250514"

    def test_spend_tracking(self) -> None:
        ctrl = BudgetController(BudgetConfig(hard_limit=500.0))
        ctrl.record("claude-haiku-3-5-20241022", input_tokens=1_000_000)
        assert ctrl.spent > 0.0
        assert ctrl.remaining < 500.0

    def test_model_breakdown(self) -> None:
        ctrl = BudgetController(BudgetConfig(hard_limit=500.0))
        ctrl.record("claude-sonnet-4-20250514", input_tokens=1_000_000)
        ctrl.record("claude-haiku-3-5-20241022", input_tokens=1_000_000)
        breakdown = ctrl.get_model_breakdown()
        assert "claude-sonnet-4-20250514" in breakdown
        assert "claude-haiku-3-5-20241022" in breakdown

    def test_summary(self) -> None:
        ctrl = BudgetController(BudgetConfig(hard_limit=500.0))
        summary = ctrl.get_summary()
        assert summary["spent"] == 0.0
        assert summary["remaining"] == 500.0
        assert summary["utilization_pct"] == 0.0

    def test_no_auto_downgrade(self) -> None:
        ctrl = BudgetController(
            BudgetConfig(hard_limit=20.0, warn_threshold=0.5, auto_downgrade=False)
        )
        ctrl.record("claude-sonnet-4-20250514", input_tokens=5_000_000)
        decision, model = ctrl.check("claude-opus-4-20250514", input_tokens=100)
        assert decision == BudgetDecision.WARN
        assert model == "claude-opus-4-20250514"  # No downgrade
