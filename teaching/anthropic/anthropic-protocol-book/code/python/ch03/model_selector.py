"""
Chapter 3: Model Selector and Cost Estimator.

Provides:
- ModelSelector: selects the optimal Claude model based on task characteristics.
- TokenCounter: estimates token counts for text and complete API requests.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any


# ---------------------------------------------------------------------------
# Model Registry
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ModelSpec:
    """Immutable specification for a single Claude model."""

    api_id: str
    display_name: str
    description: str
    context_window: int
    max_output: int
    input_price_per_mtok: float   # USD per million input tokens
    output_price_per_mtok: float  # USD per million output tokens
    cache_write_5m_mult: float    # multiplier on base input price (5-min cache)
    cache_write_1h_mult: float    # multiplier on base input price (1-hour cache)
    cache_read_mult: float        # multiplier on base input price (cache hit)
    batch_discount: float         # 0.5 = 50% off for Batch API
    generation: int               # model generation number for ordering
    tier: str                     # "flagship" | "balanced" | "speed"
    supports_extended_thinking: bool = False
    supports_adaptive_thinking: bool = False


# Complete model registry sourced from official Anthropic docs (May 2026).
MODEL_REGISTRY: dict[str, ModelSpec] = {
    # ── Current Primary Models ──
    "claude-opus-4-7": ModelSpec(
        api_id="claude-opus-4-7",
        display_name="Claude Opus 4.7",
        description="Most capable model for complex reasoning and agentic coding",
        context_window=1_000_000,
        max_output=128_000,
        input_price_per_mtok=5.00,
        output_price_per_mtok=25.00,
        cache_write_5m_mult=1.25,
        cache_write_1h_mult=2.00,
        cache_read_mult=0.10,
        batch_discount=0.50,
        generation=4,
        tier="flagship",
        supports_adaptive_thinking=True,
    ),
    "claude-sonnet-4-6": ModelSpec(
        api_id="claude-sonnet-4-6",
        display_name="Claude Sonnet 4.6",
        description="Best combination of speed and intelligence",
        context_window=1_000_000,
        max_output=64_000,
        input_price_per_mtok=3.00,
        output_price_per_mtok=15.00,
        cache_write_5m_mult=1.25,
        cache_write_1h_mult=2.00,
        cache_read_mult=0.10,
        batch_discount=0.50,
        generation=4,
        tier="balanced",
        supports_extended_thinking=True,
    ),
    "claude-haiku-4-5": ModelSpec(
        api_id="claude-haiku-4-5-20251001",
        display_name="Claude Haiku 4.5",
        description="Fastest model with near-frontier intelligence",
        context_window=200_000,
        max_output=64_000,
        input_price_per_mtok=1.00,
        output_price_per_mtok=5.00,
        cache_write_5m_mult=1.25,
        cache_write_1h_mult=2.00,
        cache_read_mult=0.10,
        batch_discount=0.50,
        generation=4,
        tier="speed",
    ),
    # ── Legacy / Still Available Models ──
    "claude-opus-4-6": ModelSpec(
        api_id="claude-opus-4-6",
        display_name="Claude Opus 4.6",
        description="Previous flagship; migrate to Opus 4.7",
        context_window=1_000_000,
        max_output=128_000,
        input_price_per_mtok=5.00,
        output_price_per_mtok=25.00,
        cache_write_5m_mult=1.25,
        cache_write_1h_mult=2.00,
        cache_read_mult=0.10,
        batch_discount=0.50,
        generation=4,
        tier="flagship",
        supports_extended_thinking=True,
    ),
    "claude-sonnet-4-5": ModelSpec(
        api_id="claude-sonnet-4-5-20250929",
        display_name="Claude Sonnet 4.5",
        description="Previous balanced model; migrate to Sonnet 4.6",
        context_window=200_000,
        max_output=64_000,
        input_price_per_mtok=3.00,
        output_price_per_mtok=15.00,
        cache_write_5m_mult=1.25,
        cache_write_1h_mult=2.00,
        cache_read_mult=0.10,
        batch_discount=0.50,
        generation=4,
        tier="balanced",
        supports_extended_thinking=True,
    ),
    "claude-opus-4-5": ModelSpec(
        api_id="claude-opus-4-5-20251101",
        display_name="Claude Opus 4.5",
        description="Older flagship; migrate to Opus 4.7",
        context_window=200_000,
        max_output=64_000,
        input_price_per_mtok=5.00,
        output_price_per_mtok=25.00,
        cache_write_5m_mult=1.25,
        cache_write_1h_mult=2.00,
        cache_read_mult=0.10,
        batch_discount=0.50,
        generation=4,
        tier="flagship",
        supports_extended_thinking=True,
    ),
    "claude-opus-4-1": ModelSpec(
        api_id="claude-opus-4-1-20250805",
        display_name="Claude Opus 4.1",
        description="Legacy model at 3x current pricing; migrate urgently",
        context_window=200_000,
        max_output=32_000,
        input_price_per_mtok=15.00,
        output_price_per_mtok=75.00,
        cache_write_5m_mult=1.25,
        cache_write_1h_mult=2.00,
        cache_read_mult=0.10,
        batch_discount=0.50,
        generation=4,
        tier="flagship",
        supports_extended_thinking=True,
    ),
    # ── Deprecated Models ──
    "claude-sonnet-4": ModelSpec(
        api_id="claude-sonnet-4-20250514",
        display_name="Claude Sonnet 4",
        description="DEPRECATED; retires June 15, 2026. Migrate to Sonnet 4.6.",
        context_window=200_000,
        max_output=64_000,
        input_price_per_mtok=3.00,
        output_price_per_mtok=15.00,
        cache_write_5m_mult=1.25,
        cache_write_1h_mult=2.00,
        cache_read_mult=0.10,
        batch_discount=0.50,
        generation=4,
        tier="balanced",
        supports_extended_thinking=True,
    ),
    "claude-opus-4": ModelSpec(
        api_id="claude-opus-4-20250514",
        display_name="Claude Opus 4",
        description="DEPRECATED; retires June 15, 2026. Migrate to Opus 4.7.",
        context_window=200_000,
        max_output=32_000,
        input_price_per_mtok=15.00,
        output_price_per_mtok=75.00,
        cache_write_5m_mult=1.25,
        cache_write_1h_mult=2.00,
        cache_read_mult=0.10,
        batch_discount=0.50,
        generation=4,
        tier="flagship",
        supports_extended_thinking=True,
    ),
}


# ---------------------------------------------------------------------------
# Model Selector
# ---------------------------------------------------------------------------

@dataclass
class SelectionResult:
    """The result of a model selection decision."""

    model_id: str
    model: ModelSpec
    reasoning: str


class ModelSelector:
    """Selects optimal Claude model based on task characteristics.

    Selection logic follows the decision tree from section 3.2.2,
    prioritizing capability-fit over raw power.

    Usage::

        selector = ModelSelector()
        result = selector.select(
            task_complexity="high",
            budget="medium",
            context_needed=500_000,
        )
        print(result.model_id)  # "claude-sonnet-4-6"
    """

    MODELS: dict[str, ModelSpec] = MODEL_REGISTRY

    def select(
        self,
        task_complexity: str,
        budget: str,
        context_needed: int = 0,
        *,
        latency_sensitive: bool = False,
        requires_long_context: bool = False,
    ) -> SelectionResult:
        """Select the most appropriate model for the given task.

        Args:
            task_complexity: One of 'low', 'medium', 'high', 'agentic'.
            budget: One of 'low', 'medium', 'high'.
            context_needed: Estimated tokens required for the full context.
            latency_sensitive: Whether sub-second latency is required.
            requires_long_context: Whether the task needs >200k context window.

        Returns:
            SelectionResult with model_id, ModelSpec, and reasoning.
        """
        _validate_param(task_complexity, "task_complexity", {"low", "medium", "high", "agentic"})
        _validate_param(budget, "budget", {"low", "medium", "high"})

        # Rule 1: Long context (>200k) requires a 1M-window model.
        long_ctx_needed = requires_long_context or context_needed > 200_000
        if long_ctx_needed:
            # Sonnet 4.6 has 1M window at $3/$15 — best value for long context.
            if task_complexity in ("agentic",):
                return SelectionResult(
                    "claude-opus-4-7",
                    self.MODELS["claude-opus-4-7"],
                    "Agentic task with >200k context requires Opus 4.7 (1M window + top reasoning).",
                )
            return SelectionResult(
                "claude-sonnet-4-6",
                self.MODELS["claude-sonnet-4-6"],
                "Long context (>200k) task — Sonnet 4.6 provides 1M window at best value.",
            )

        # Rule 2: Agentic complexity always gets Opus.
        if task_complexity == "agentic":
            return SelectionResult(
                "claude-opus-4-7",
                self.MODELS["claude-opus-4-7"],
                "Agentic coding / complex multi-step reasoning requires Opus 4.7.",
            )

        # Rule 3: High complexity with low budget → Sonnet.
        if task_complexity == "high" and budget == "low":
            return SelectionResult(
                "claude-sonnet-4-6",
                self.MODELS["claude-sonnet-4-6"],
                "High-complexity task with low budget — Sonnet 4.6 offers near-Opus quality at 60% cost.",
            )

        # Rule 4: High complexity with better budget → Opus.
        if task_complexity == "high":
            return SelectionResult(
                "claude-opus-4-7",
                self.MODELS["claude-opus-4-7"],
                "High-complexity task with sufficient budget → Opus 4.7 for best quality.",
            )

        # Rule 5: Latency-sensitive or low budget → Haiku.
        if latency_sensitive or budget == "low":
            return SelectionResult(
                "claude-haiku-4-5",
                self.MODELS["claude-haiku-4-5"],
                (
                    "Latency-sensitive task → Haiku 4.5 (fastest)."
                    if latency_sensitive
                    else "Low budget → Haiku 4.5 at $1/$5 per MTok."
                ),
            )

        # Rule 6: Default → Sonnet 4.6 (sweet spot for most production workloads).
        return SelectionResult(
            "claude-sonnet-4-6",
            self.MODELS["claude-sonnet-4-6"],
            "Default: Sonnet 4.6 — best price/performance for general production use.",
        )

    def cost_estimate(
        self,
        model: str | ModelSpec,
        input_tokens: int,
        output_tokens: int,
        *,
        cache_hit: bool = False,
        cache_duration: str | None = None,
        batch: bool = False,
    ) -> float:
        """Estimate the USD cost of a single API request.

        Args:
            model: Model API ID string or ModelSpec instance.
            input_tokens: Number of input tokens (including cached if applicable).
            output_tokens: Expected/actual number of output tokens.
            cache_hit: Whether this request reads from an existing cache.
            cache_duration: If creating a new cache, "5m" or "1h".
            batch: Whether using the Batch API (50% discount).

        Returns:
            Estimated cost in USD.

        Raises:
            KeyError: If model string ID is not found in the registry.
        """
        spec = model if isinstance(model, ModelSpec) else self.MODELS[model]

        # Determine input price based on caching state.
        if cache_hit:
            input_price = spec.input_price_per_mtok * spec.cache_read_mult
        elif cache_duration == "5m":
            input_price = spec.input_price_per_mtok * spec.cache_write_5m_mult
        elif cache_duration == "1h":
            input_price = spec.input_price_per_mtok * spec.cache_write_1h_mult
        else:
            input_price = spec.input_price_per_mtok

        output_price = spec.output_price_per_mtok

        # Apply batch discount (50% off both input and output).
        if batch:
            input_price *= spec.batch_discount
            output_price *= spec.batch_discount

        input_cost = (input_tokens / 1_000_000) * input_price
        output_cost = (output_tokens / 1_000_000) * output_price

        return round(input_cost + output_cost, 6)

    def cost_estimate_multi(
        self,
        model: str | ModelSpec,
        num_requests: int,
        input_tokens_per_request: int,
        output_tokens_per_request: int,
        *,
        cached_input_tokens: int = 0,
        cache_duration: str | None = None,
        batch: bool = False,
    ) -> dict[str, float]:
        """Estimate total cost across multiple requests, factoring in cache writes.

        Args:
            model: Model API ID string or ModelSpec instance.
            num_requests: Total number of API requests.
            input_tokens_per_request: Input tokens per request (excluding cached portion).
            output_tokens_per_request: Output tokens per request.
            cached_input_tokens: Tokens shared across requests (system prompt, docs)
                that should use prompt caching. 0 means no caching.
            cache_duration: "5m" or "1h" for the cache write duration.
                Used only when cached_input_tokens > 0.
            batch: Whether using the Batch API.

        Returns:
            Dict with keys: total_cost, write_cost, read_cost,
            non_cached_cost, output_cost, savings_vs_no_cache.
        """
        spec = model if isinstance(model, ModelSpec) else self.MODELS[model]

        # Cost with caching.
        write_cost = 0.0
        read_cost = 0.0
        if cached_input_tokens > 0 and cache_duration:
            write_cost = self.cost_estimate(
                spec, cached_input_tokens, 0,
                cache_duration=cache_duration, batch=batch,
            )
            read_cost = self.cost_estimate(
                spec, cached_input_tokens * num_requests, 0,
                cache_hit=True, batch=batch,
            )

        non_cached_cost = self.cost_estimate(
            spec, input_tokens_per_request * num_requests, 0, batch=batch,
        ) if input_tokens_per_request > 0 else 0.0

        output_cost = self.cost_estimate(
            spec, 0, output_tokens_per_request * num_requests, batch=batch,
        )

        total_with_cache = write_cost + read_cost + non_cached_cost + output_cost

        # Cost without caching (for comparison).
        total_input_tokens = (
            (cached_input_tokens + input_tokens_per_request) * num_requests
        )
        total_no_cache = self.cost_estimate(
            spec, total_input_tokens, output_tokens_per_request * num_requests,
            batch=batch,
        )

        savings = total_no_cache - total_with_cache

        return {
            "total_cost": round(total_with_cache, 6),
            "write_cost": round(write_cost, 6),
            "read_cost": round(read_cost, 6),
            "non_cached_cost": round(non_cached_cost, 6),
            "output_cost": round(output_cost, 6),
            "no_cache_cost": round(total_no_cache, 6),
            "savings": round(savings, 6),
            "savings_pct": round(savings / total_no_cache * 100, 2) if total_no_cache > 0 else 0.0,
        }

    def cache_breakeven(self, model: str | ModelSpec) -> dict[str, float]:
        """Calculate the minimum number of cache reads needed to break even.

        Returns a dict with keys '5m_breakeven_reads' and '1h_breakeven_reads'.
        """
        spec = model if isinstance(model, ModelSpec) else self.MODELS[model]

        def _breakeven(write_mult: float) -> float:
            # write_price + n * read_price <= n * base_price
            # write_mult * base + n * read_mult * base <= n * base
            # write_mult + n * read_mult <= n
            # write_mult <= n * (1 - read_mult)
            # n >= write_mult / (1 - read_mult)
            return math.ceil(write_mult / (1 - spec.cache_read_mult))

        return {
            "5m_breakeven_reads": _breakeven(spec.cache_write_5m_mult),
            "1h_breakeven_reads": _breakeven(spec.cache_write_1h_mult),
        }


# ---------------------------------------------------------------------------
# Token Counter
# ---------------------------------------------------------------------------

# Characters-per-token estimates by content type.
CHAR_PER_TOKEN: dict[str, float] = {
    "english": 4.0,
    "chinese": 2.0,
    "code": 3.5,
    "json": 3.0,
    "general": 4.0,
}

# Tool system prompt overhead tokens (auto/any tool choice).
TOOL_SYSTEM_PROMPT_OVERHEAD = 346

# Per-message structural overhead (role tags, formatting).
MESSAGE_OVERHEAD_PER_MESSAGE = 5

# Per-content-block structural overhead.
CONTENT_BLOCK_OVERHEAD = 2


class TokenCounter:
    """Estimates token counts without requiring the Anthropic tokenizer.

    Uses empirical character-per-token ratios that approximate BPE tokenization.
    These are ESTIMATES — actual token counts may vary by ±20%.

    For Opus 4.7 (new tokenizer), token counts may be up to 35% higher
    than these estimates. Pass opus_47=True to apply an adjustment factor.

    Usage::

        counter = TokenCounter()
        tokens = counter.count("Hello, world!")
        request_tokens = counter.estimate_request_tokens(messages, system=sys_prompt)
    """

    def __init__(self, opus_47_adjustment: bool = False) -> None:
        """Initialize the token counter.

        Args:
            opus_47_adjustment: If True, apply a 1.2x multiplier to account
                for Opus 4.7's new tokenizer producing more tokens per text.
                Only enable when targeting claude-opus-4-7.
        """
        self._opus_47_adjustment = opus_47_adjustment
        self._adjustment_factor = 1.2 if opus_47_adjustment else 1.0

    def count(self, text: str, content_type: str = "general") -> int:
        """Estimate token count for a plain text string.

        Args:
            text: The text to count tokens for.
            content_type: One of 'english', 'chinese', 'code', 'json', 'general'.

        Returns:
            Estimated token count (integer).
        """
        if not text:
            return 0
        ratio = CHAR_PER_TOKEN.get(content_type, CHAR_PER_TOKEN["general"])
        raw = max(1, int(math.ceil(len(text) / ratio)))
        return max(1, int(round(raw * self._adjustment_factor)))

    def estimate_request_tokens(
        self,
        messages: list[dict[str, Any]],
        system: str | None = None,
        tools: list[dict[str, Any]] | None = None,
    ) -> dict[str, int]:
        """Estimate total token consumption for a full Messages API request.

        This estimates input tokens only. Output tokens are generated by the
        model and cannot be estimated in advance (use max_tokens as an upper bound).

        Args:
            messages: List of message dicts with 'role' and 'content'.
                Content can be a string or a list of content blocks.
            system: Optional system prompt string.
            tools: Optional list of tool definitions.

        Returns:
            Dict with keys: system_tokens, messages_tokens, tools_tokens,
            overhead_tokens, total_input_tokens.
        """
        system_tokens = 0
        if system:
            system_tokens = self.count(system)

        messages_tokens = 0
        for msg in messages:
            content = msg.get("content", "")
            if isinstance(content, str):
                messages_tokens += self.count(content)
            elif isinstance(content, list):
                for block in content:
                    if isinstance(block, dict):
                        if block.get("type") == "text":
                            messages_tokens += self.count(block.get("text", ""))
                        elif block.get("type") == "tool_use":
                            # Tool use blocks include name + input JSON
                            name = block.get("name", "")
                            input_data = block.get("input", {})
                            messages_tokens += self.count(name + str(input_data), "json")
                        elif block.get("type") == "tool_result":
                            result = block.get("content", "")
                            if isinstance(result, str):
                                messages_tokens += self.count(result)
                            elif isinstance(result, list):
                                for item in result:
                                    if isinstance(item, dict) and item.get("type") == "text":
                                        messages_tokens += self.count(item.get("text", ""))
                        elif block.get("type") == "image":
                            # Image tokens vary by size; rough estimate
                            messages_tokens += 200  # conservative minimum

            messages_tokens += MESSAGE_OVERHEAD_PER_MESSAGE

        # Tool definition tokens: names, descriptions, parameter schemas
        tools_tokens = 0
        if tools:
            for tool in tools:
                name = tool.get("name", "")
                desc = tool.get("description", "")
                schema = tool.get("input_schema", {})
                tools_tokens += self.count(name + desc + str(schema), "json")
                tools_tokens += CONTENT_BLOCK_OVERHEAD
            tools_tokens += TOOL_SYSTEM_PROMPT_OVERHEAD

        # Structural overhead for the request envelope
        overhead_tokens = CONTENT_BLOCK_OVERHEAD  # request structure

        total = system_tokens + messages_tokens + tools_tokens + overhead_tokens

        return {
            "system_tokens": system_tokens,
            "messages_tokens": messages_tokens,
            "tools_tokens": tools_tokens,
            "overhead_tokens": overhead_tokens,
            "total_input_tokens": total,
        }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _validate_param(value: str, name: str, allowed: set[str]) -> None:
    if value not in allowed:
        raise ValueError(
            f"Invalid {name} '{value}'. Must be one of: {', '.join(sorted(allowed))}"
        )


# ---------------------------------------------------------------------------
# Convenience: select_model_for_scenario (self-test question 3)
# ---------------------------------------------------------------------------

def select_model_for_scenario(task: dict[str, Any]) -> str:
    """Select a model for a given scenario dict.

    Implements the rules from self-test question 3.

    Args:
        task: Dict with keys like 'requires_long_context' (bool),
              'complexity' (str), 'budget' (str), 'latency_sensitive' (bool).

    Returns:
        Model API ID string.
    """
    requires_long_context = task.get("requires_long_context", False)
    complexity = task.get("complexity", "medium")
    budget = task.get("budget", "medium")
    latency_sensitive = task.get("latency_sensitive", False)

    if requires_long_context:
        return "claude-sonnet-4-6"
    if complexity == "agentic":
        return "claude-opus-4-7"
    if complexity == "high" and budget == "low":
        return "claude-sonnet-4-6"
    if complexity == "high":
        return "claude-opus-4-7"
    if latency_sensitive or budget == "low":
        return "claude-haiku-4-5"
    return "claude-sonnet-4-6"
