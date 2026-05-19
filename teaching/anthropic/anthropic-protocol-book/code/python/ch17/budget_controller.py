"""
Chapter 17: BudgetController — hard limit, soft alert, and auto-downgrade.

Implements a token-cost budget controller for production LLM applications.
Key features:
  - Per-session and per-period budget tracking
  - Three-tier decision: allow / warn / block
  - Soft alert when approaching budget threshold
  - Auto-downgrade to cheaper model when budget is tight
  - Token estimation before API calls (avoiding wasted spend on large prompts)

Based on Anthropic's pricing model and spend-limit tier system
(docs.anthropic.com, May 2026).
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Callable, Dict, List, Optional, Tuple


# ---------------------------------------------------------------------------
# Domain types
# ---------------------------------------------------------------------------


class BudgetDecision(str, Enum):
    """Outcome of a budget check before making an API call."""

    ALLOW = "allow"           # Proceed normally
    WARN = "warn"             # Proceed but log a warning (near limit)
    BLOCK = "block"           # Reject the request (budget exhausted)
    DOWNGRADE = "downgrade"   # Allow but switch to a cheaper model


class BudgetPeriod(str, Enum):
    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"


# ---------------------------------------------------------------------------
# Pricing model
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ModelPricing:
    """Token pricing per million tokens (MTok) for a specific model.

    Prices are in USD as of May 2026 (Anthropic pricing page).
    """

    input_price_per_mtok: float   # $ per million input tokens
    output_price_per_mtok: float  # $ per million output tokens
    cache_write_price_per_mtok: float = 0.0
    cache_read_price_per_mtok: float = 0.0


# Current pricing (May 2026)
MODEL_PRICING: Dict[str, ModelPricing] = {
    "claude-opus-4-7": ModelPricing(
        input_price_per_mtok=5.00, output_price_per_mtok=25.00,
        cache_write_price_per_mtok=6.25, cache_read_price_per_mtok=0.50,
    ),
    "claude-sonnet-4-6": ModelPricing(
        input_price_per_mtok=3.00, output_price_per_mtok=15.00,
        cache_write_price_per_mtok=3.75, cache_read_price_per_mtok=0.30,
    ),
    "claude-haiku-4-5-20251001": ModelPricing(
        input_price_per_mtok=1.00, output_price_per_mtok=5.00,
        cache_write_price_per_mtok=1.25, cache_read_price_per_mtok=0.10,
    ),
    "claude-opus-4-20250514": ModelPricing(
        input_price_per_mtok=15.00, output_price_per_mtok=75.00,
        cache_write_price_per_mtok=18.75, cache_read_price_per_mtok=1.50,
    ),
    "claude-sonnet-4-20250514": ModelPricing(
        input_price_per_mtok=3.00, output_price_per_mtok=15.00,
        cache_write_price_per_mtok=3.75, cache_read_price_per_mtok=0.30,
    ),
    "claude-haiku-3-5-20241022": ModelPricing(
        input_price_per_mtok=0.80, output_price_per_mtok=4.00,
        cache_write_price_per_mtok=1.00, cache_read_price_per_mtok=0.08,
    ),
}

# Downgrade chain: when budget is tight, try the next cheaper model
DOWNGRADE_CHAIN: List[str] = [
    "claude-opus-4-7",
    "claude-sonnet-4-6",
    "claude-haiku-4-5-20251001",
]


def estimate_cost(
    model: str,
    input_tokens: int = 0,
    output_tokens: int = 0,
    cache_write_tokens: int = 0,
    cache_read_tokens: int = 0,
) -> float:
    """Estimate the cost of an API call in USD.

    Args:
        model: The model ID (e.g., ``claude-sonnet-4-20250514``).
        input_tokens: Estimated or actual input tokens.
        output_tokens: Estimated output tokens (use ``max_tokens`` for upper-bound).
        cache_write_tokens: Tokens written to cache.
        cache_read_tokens: Tokens read from cache.

    Returns:
        Estimated cost in USD.
    """
    pricing = MODEL_PRICING.get(model)
    if pricing is None:
        # Fallback to sonnet pricing for unknown models
        pricing = MODEL_PRICING["claude-sonnet-4-20250514"]

    cost = 0.0
    cost += (input_tokens / 1_000_000) * pricing.input_price_per_mtok
    cost += (output_tokens / 1_000_000) * pricing.output_price_per_mtok
    cost += (cache_write_tokens / 1_000_000) * pricing.cache_write_price_per_mtok
    cost += (cache_read_tokens / 1_000_000) * pricing.cache_read_price_per_mtok
    return cost


# ---------------------------------------------------------------------------
# BudgetController
# ---------------------------------------------------------------------------


@dataclass
class BudgetConfig:
    """Configuration for budget control.

    The controller uses two thresholds:
      - ``warn_threshold`` (e.g., 0.75): when 75% of budget is consumed,
        decisions return ``WARN``.
      - ``hard_limit``: absolute max spend in the period.
    """

    hard_limit: float                          # Max spend in USD
    warn_threshold: float = 0.75               # Fraction of hard_limit for warnings
    period: BudgetPeriod = BudgetPeriod.MONTHLY
    auto_downgrade: bool = True                # If True, suggest cheaper model on WARN

    # Model override map: which model to downgrade to
    downgrade_map: Optional[Dict[str, str]] = None


@dataclass
class SpendRecord:
    """A single spending entry."""

    timestamp: float
    model: str
    input_tokens: int
    output_tokens: int
    cost: float


class BudgetController:
    """Track and control LLM API spending.

    Provides three-tier decision-making before each API call:

    - ``ALLOW``: budget is healthy, proceed.
    - ``WARN``: approaching limit, consider downgrading model.
    - ``BLOCK``: budget exhausted, reject the call.
    - ``DOWNGRADE``: auto-downgrade to a cheaper model (if enabled).

    Usage::

        ctrl = BudgetController(BudgetConfig(hard_limit=500.0))
        decision, model = ctrl.check("claude-opus-4-20250514", input_tokens=5000)
        if decision == BudgetDecision.BLOCK:
            raise BudgetExceededError(...)
        if decision == BudgetDecision.DOWNGRADE:
            model_to_use = model  # use the cheaper model
        # ... make API call ...
        ctrl.record("claude-sonnet-4-20250514", 5000, 200)
    """

    def __init__(self, config: BudgetConfig) -> None:
        self.config = config
        self._spent: float = 0.0
        self._records: List[SpendRecord] = []
        self._period_start: float = time.time()
        self._downgrade_map = config.downgrade_map or {
            "claude-opus-4-20250514": "claude-sonnet-4-20250514",
            "claude-sonnet-4-20250514": "claude-haiku-3-5-20241022",
        }

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def check(
        self,
        model: str,
        input_tokens: int,
        output_tokens: int = 0,
    ) -> Tuple[BudgetDecision, str]:
        """Check budget before making an API call.

        Args:
            model: The requested model ID.
            input_tokens: Estimated input tokens for this call.
            output_tokens: Estimated output tokens (upper bound).

        Returns:
            (decision, effective_model_to_use)
        """
        estimated = estimate_cost(model, input_tokens, output_tokens)
        projected = self._spent + estimated
        warn_limit = self.config.hard_limit * self.config.warn_threshold

        # Hard block
        if self._spent >= self.config.hard_limit:
            return (BudgetDecision.BLOCK, model)
        if projected > self.config.hard_limit:
            return (BudgetDecision.BLOCK, model)

        # Warning zone
        if projected >= warn_limit or self._spent >= warn_limit:
            if self.config.auto_downgrade:
                cheaper = self._find_downgrade(model)
                if cheaper != model:
                    cheaper_cost = estimate_cost(cheaper, input_tokens, output_tokens)
                    if self._spent + cheaper_cost < self.config.hard_limit:
                        return (BudgetDecision.DOWNGRADE, cheaper)
            return (BudgetDecision.WARN, model)

        # All good
        return (BudgetDecision.ALLOW, model)

    def record(
        self,
        model: str,
        input_tokens: int = 0,
        output_tokens: int = 0,
        cache_write_tokens: int = 0,
        cache_read_tokens: int = 0,
    ) -> SpendRecord:
        """Record actual spend after an API call completes."""
        cost = estimate_cost(
            model, input_tokens, output_tokens,
            cache_write_tokens, cache_read_tokens,
        )
        record = SpendRecord(
            timestamp=time.time(),
            model=model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost=cost,
        )
        self._records.append(record)
        self._spent += cost
        return record

    # ------------------------------------------------------------------
    # Query methods
    # ------------------------------------------------------------------

    @property
    def spent(self) -> float:
        """Total spent in the current period (USD)."""
        return self._spent

    @property
    def remaining(self) -> float:
        """Remaining budget in the current period (USD)."""
        return max(0.0, self.config.hard_limit - self._spent)

    @property
    def utilization_pct(self) -> float:
        """Budget utilization as a percentage (0–100)."""
        if self.config.hard_limit <= 0:
            return 100.0
        return min(100.0, (self._spent / self.config.hard_limit) * 100.0)

    def get_summary(self) -> Dict[str, object]:
        """Return a summary dictionary for monitoring."""
        return {
            "spent": round(self._spent, 4),
            "remaining": round(self.remaining, 4),
            "hard_limit": self.config.hard_limit,
            "utilization_pct": round(self.utilization_pct, 1),
            "period": self.config.period.value,
            "total_calls": len(self._records),
        }

    def get_model_breakdown(self) -> Dict[str, float]:
        """Return spend breakdown by model."""
        breakdown: Dict[str, float] = {}
        for rec in self._records:
            breakdown[rec.model] = breakdown.get(rec.model, 0.0) + rec.cost
        return {k: round(v, 6) for k, v in breakdown.items()}

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _find_downgrade(self, model: str) -> str:
        """Find the next cheaper model in the downgrade chain."""
        return self._downgrade_map.get(model, model)


class BudgetExceededError(Exception):
    """Raised when a request is blocked due to budget exhaustion."""
    pass


# ---------------------------------------------------------------------------
# Token estimator
# ---------------------------------------------------------------------------


def estimate_input_tokens(text: str) -> int:
    """Quick token-count estimate without API call.

    Uses a simple heuristic: ~4 characters per token for English text.
    For production use, call the Anthropic Token Counting API or use
    the ``tiktoken`` library with cl100k_base encoding.

    Accuracy: typically within +/- 20% for English text.
    """
    if not text:
        return 0
    # Simple heuristic: ~4 chars per token
    return max(1, len(text) // 4)


def estimate_message_tokens(messages: List[Dict[str, object]]) -> int:
    """Estimate total tokens for a messages array.

    Sums the character-based estimates for all ``content`` fields.
    """
    total = 0
    for msg in messages:
        content = msg.get("content", "")
        if isinstance(content, str):
            total += estimate_input_tokens(content)
        elif isinstance(content, list):
            for block in content:
                if isinstance(block, dict):
                    text = block.get("text", "")
                    if isinstance(text, str):
                        total += estimate_input_tokens(text)
    return max(1, total)
