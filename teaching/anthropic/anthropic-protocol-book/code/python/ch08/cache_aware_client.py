"""
Chapter 8: Cache-Aware Client.

A client wrapper that injects cache_control markers into Anthropic API
requests and provides cost estimation / breakeven analysis for Prompt Caching.

Verified against Anthropic Prompt Caching spec:
  - cache_control: { type: "ephemeral" } (no beta header required)
  - min tokens: 1024 (Sonnet/Opus), 2048 (Haiku)
  - max breakpoints: 4 per request
  - TTL: 5 min (default ephemeral)
  - Pricing: cache write = base * 1.25, cache read = base * 0.10
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


# ---------------------------------------------------------------------------
# Pricing constants (Claude Sonnet 4, per million tokens)
# ---------------------------------------------------------------------------

DEFAULT_WRITE_PRICE_PER_MTok = 3.75   # $3.75/MTok cache write
DEFAULT_READ_PRICE_PER_MTok = 0.30    # $0.30/MTok cache read
DEFAULT_BASE_PRICE_PER_MTok = 3.00    # $3.00/MTok standard input

# Protocol constraints
MIN_CACHEABLE_TOKENS_DEFAULT = 1024   # Sonnet/Opus
MAX_BREAKPOINTS = 4
DEFAULT_CACHE_TTL_SECONDS = 300       # 5 minutes


@dataclass
class CacheUsage:
    """Extracted caching usage statistics from an API response."""

    input_tokens: int = 0
    output_tokens: int = 0
    cache_creation_tokens: int = 0
    cache_read_tokens: int = 0

    @property
    def uncached_input_tokens(self) -> int:
        return self.input_tokens - self.cache_creation_tokens - self.cache_read_tokens

    @property
    def cache_hit_ratio(self) -> float:
        if self.input_tokens == 0:
            return 0.0
        return self.cache_read_tokens / self.input_tokens


@dataclass
class CacheBreakevenResult:
    """Result of a cache breakeven analysis."""

    breakeven_reads: float
    savings: List[Dict[str, float]]
    is_worthwhile: bool

    def __repr__(self) -> str:
        lines = [
            f"CacheBreakevenResult(",
            f"  breakeven_reads={self.breakeven_reads:.1f},",
            f"  is_worthwhile={self.is_worthwhile},",
            f"  savings={self.savings}",
            f")",
        ]
        return "\n".join(lines)


class CacheAwareClient:
    """Client wrapper that adds Prompt Caching awareness to Anthropic API calls.

    Handles:
      - Injecting cache_control markers at specified positions
      - Estimating cost savings from caching
      - Breakeven analysis for cache decisions
      - Usage extraction from API responses

    Usage::

        client = CacheAwareClient(base_price=3.00)
        request = {"system": "You are an expert...", "messages": [...]}
        result = client.create_with_cache(request, cache_points=[0, -1])
        savings = client.estimate_cache_savings(prompt_tokens=15000, expected_requests=10.0)
    """

    def __init__(
        self,
        write_price_per_mtok: float = DEFAULT_WRITE_PRICE_PER_MTok,
        read_price_per_mtok: float = DEFAULT_READ_PRICE_PER_MTok,
        base_price_per_mtok: float = DEFAULT_BASE_PRICE_PER_MTok,
        min_cacheable_tokens: int = MIN_CACHEABLE_TOKENS_DEFAULT,
        max_breakpoints: int = MAX_BREAKPOINTS,
    ) -> None:
        self.write_price = write_price_per_mtok
        self.read_price = read_price_per_mtok
        self.base_price = base_price_per_mtok
        self.min_cacheable_tokens = min_cacheable_tokens
        self.max_breakpoints = max_breakpoints

    # ------------------------------------------------------------------
    # Cache marker injection
    # ------------------------------------------------------------------

    def create_with_cache(
        self,
        request: Dict[str, Any],
        cache_points: List[int],
    ) -> Dict[str, Any]:
        """Inject cache_control markers at specified positions in the request.

        Args:
            request: A Messages API request dict with optional 'system' and
                     required 'messages' keys.
            cache_points: List of integer indices into `request["messages"]`
                          where cache_control breakpoints should be placed.
                          Use negative indices to count from the end.

        Returns:
            A new request dict with cache_control markers injected.

        Raises:
            ValueError: If too many breakpoints are requested.
        """
        if len(cache_points) > self.max_breakpoints:
            raise ValueError(
                f"Too many cache points: {len(cache_points)} > max {self.max_breakpoints}"
            )

        result = {**request}

        # Handle system prompt caching
        if "system" in result and cache_points:
            result["system"] = self._inject_cache_into_system(result["system"])

        # Handle message-level caching
        messages = list(result.get("messages", []))
        if messages and cache_points:
            messages = self._inject_cache_into_messages(messages, cache_points)

        result["messages"] = messages
        return result

    def _inject_cache_into_system(
        self, system: Any
    ) -> Any:
        """Add cache_control to system prompt content blocks.

        Handles both string and list-of-blocks system formats.
        """
        if isinstance(system, str):
            return [
                {
                    "type": "text",
                    "text": system,
                    "cache_control": {"type": "ephemeral"},
                }
            ]
        if isinstance(system, list):
            result = []
            for i, block in enumerate(system):
                block_copy = dict(block)
                # Place cache_control on the last text block
                if i == len(system) - 1:
                    block_copy["cache_control"] = {"type": "ephemeral"}
                result.append(block_copy)
            return result
        return system

    def _inject_cache_into_messages(
        self,
        messages: List[Dict[str, Any]],
        cache_points: List[int],
    ) -> List[Dict[str, Any]]:
        """Inject cache_control into message content at specified indices."""
        normalized_points: List[int] = []
        for pt in cache_points:
            if pt < 0:
                normalized = len(messages) + pt
            else:
                normalized = pt
            if 0 <= normalized < len(messages):
                normalized_points.append(normalized)

        # De-duplicate and sort
        normalized_points = sorted(set(normalized_points))

        result: List[Dict[str, Any]] = []
        for i, msg in enumerate(messages):
            msg_copy = dict(msg)
            if i in normalized_points:
                content = msg_copy.get("content", "")
                if isinstance(content, str):
                    msg_copy["content"] = [
                        {
                            "type": "text",
                            "text": content,
                            "cache_control": {"type": "ephemeral"},
                        }
                    ]
                elif isinstance(content, list):
                    new_content = []
                    for j, block in enumerate(content):
                        block_copy = dict(block)
                        if j == len(content) - 1:
                            block_copy["cache_control"] = {"type": "ephemeral"}
                        new_content.append(block_copy)
                    msg_copy["content"] = new_content
            result.append(msg_copy)

        return result

    # ------------------------------------------------------------------
    # Cost estimation
    # ------------------------------------------------------------------

    def estimate_cache_savings(
        self,
        prompt_tokens: int,
        expected_requests: float,
    ) -> float:
        """Estimate dollar savings from using Prompt Caching.

        Args:
            prompt_tokens: Size of the cacheable prompt prefix in tokens.
            expected_requests: Expected number of requests within the TTL window
                               that will share this cached prefix.

        Returns:
            Estimated savings in dollars (positive = saves money).
        """
        if expected_requests < 1:
            return 0.0

        # Cost without caching: every request pays full base price
        no_cache_cost = (
            prompt_tokens * expected_requests * self.base_price / 1_000_000
        )

        # Cost with caching: first request writes, subsequent read
        cache_write_cost = prompt_tokens * self.write_price / 1_000_000
        cache_reads = expected_requests - 1
        cache_read_cost = (
            prompt_tokens * cache_reads * self.read_price / 1_000_000
        )
        with_cache_cost = cache_write_cost + cache_read_cost

        return no_cache_cost - with_cache_cost

    def should_cache(
        self,
        prompt_tokens: int,
        requests_per_5min: float,
    ) -> bool:
        """Determine whether Prompt Caching is worthwhile.

        Args:
            prompt_tokens: Size of the cacheable prompt prefix in tokens.
            requests_per_5min: Expected requests within the 5-minute TTL window.

        Returns:
            True if caching is expected to save money.
        """
        if prompt_tokens < self.min_cacheable_tokens:
            return False
        if requests_per_5min <= 1:
            return False
        return self.estimate_cache_savings(prompt_tokens, requests_per_5min) > 0

    # ------------------------------------------------------------------
    # Breakeven analysis
    # ------------------------------------------------------------------

    def breakeven_analysis(
        self,
        prompt_tokens: int,
    ) -> CacheBreakevenResult:
        """Compute breakeven point and savings projections for caching.

        Args:
            prompt_tokens: Size of the cacheable prompt prefix in tokens.

        Returns:
            CacheBreakevenResult with breakeven point and savings data.
        """
        write_cost = prompt_tokens * self.write_price / 1_000_000
        read_cost_per_req = prompt_tokens * self.read_price / 1_000_000
        base_cost_per_req = prompt_tokens * self.base_price / 1_000_000

        # Breakeven: write_cost + (n-1)*read_cost = n*base_cost
        # write_cost - read_cost = n*(base_cost - read_cost)
        # n = (write_cost - read_cost) / (base_cost - read_cost)
        if base_cost_per_req <= read_cost_per_req:
            breakeven_reads = float("inf")
        else:
            breakeven_reads = (
                (write_cost - read_cost_per_req)
                / (base_cost_per_req - read_cost_per_req)
            )

        # Savings at various request counts
        scenarios = [5, 10, 50, 100]
        savings: List[Dict[str, float]] = []
        for n in scenarios:
            no_cache = n * base_cost_per_req
            with_cache = write_cost + (n - 1) * read_cost_per_req
            savings.append({
                "requests": float(n),
                "no_cache_cost": round(no_cache, 6),
                "with_cache_cost": round(with_cache, 6),
                "savings": round(no_cache - with_cache, 6),
                "savings_pct": round((no_cache - with_cache) / no_cache * 100, 1)
                if no_cache > 0
                else 0.0,
            })

        return CacheBreakevenResult(
            breakeven_reads=round(breakeven_reads, 1),
            savings=savings,
            is_worthwhile=breakeven_reads < float("inf"),
        )

    # ------------------------------------------------------------------
    # Usage extraction
    # ------------------------------------------------------------------

    @staticmethod
    def extract_usage(response: Dict[str, Any]) -> CacheUsage:
        """Extract caching usage statistics from an API response.

        Handles both real Anthropic API responses and simulated responses.
        """
        usage = response.get("usage", {})
        return CacheUsage(
            input_tokens=usage.get("input_tokens", 0),
            output_tokens=usage.get("output_tokens", 0),
            cache_creation_tokens=usage.get("cache_creation_input_tokens", 0),
            cache_read_tokens=usage.get("cache_read_input_tokens", 0),
        )

    @staticmethod
    def monitor_cache_hit_rate(
        usages: List[CacheUsage],
    ) -> Dict[str, float]:
        """Compute aggregate cache metrics from a list of usage snapshots.

        Args:
            usages: A list of CacheUsage objects from consecutive API calls.

        Returns:
            Dict with 'hit_rate', 'write_rate', and 'waste_rate' as fractions.
        """
        total_input = sum(u.input_tokens for u in usages)
        total_read = sum(u.cache_read_tokens for u in usages)
        total_write = sum(u.cache_creation_tokens for u in usages)

        if total_input == 0:
            return {"hit_rate": 0.0, "write_rate": 0.0, "waste_rate": 0.0}

        return {
            "hit_rate": round(total_read / total_input, 4),
            "write_rate": round(total_write / total_input, 4),
            "waste_rate": round(
                max(0, total_write - total_read) / max(1, total_input), 4
            ),
        }


# ---------------------------------------------------------------------------
# Standalone convenience function
# ---------------------------------------------------------------------------


def cache_breakeven_analysis(
    write_price_per_mtok: float = DEFAULT_WRITE_PRICE_PER_MTok,
    read_price_per_mtok: float = DEFAULT_READ_PRICE_PER_MTok,
    base_price_per_mtok: float = DEFAULT_BASE_PRICE_PER_MTok,
    cacheable_tokens: int = 15000,
) -> Dict[str, Any]:
    """Standalone function for breakeven analysis (per self-test question).

    Args:
        write_price_per_mtok: Cache write price per million tokens.
        read_price_per_mtok: Cache read price per million tokens.
        base_price_per_mtok: Standard input price per million tokens.
        cacheable_tokens: Size of the cacheable prompt prefix.

    Returns:
        Dict with breakeven point, savings projections, and viability flag.
    """
    client = CacheAwareClient(
        write_price_per_mtok=write_price_per_mtok,
        read_price_per_mtok=read_price_per_mtok,
        base_price_per_mtok=base_price_per_mtok,
    )
    result = client.breakeven_analysis(cacheable_tokens)

    # Check if breakeven achievable within 5-min TTL (pessimistic: 5 req/5min)
    viable_in_5min = result.breakeven_reads <= 5

    return {
        "breakeven_reads": result.breakeven_reads,
        "savings_at_5": result.savings[0]["savings_pct"] if len(result.savings) > 0 else 0,
        "savings_at_10": result.savings[1]["savings_pct"] if len(result.savings) > 1 else 0,
        "savings_at_50": result.savings[2]["savings_pct"] if len(result.savings) > 2 else 0,
        "savings_at_100": result.savings[3]["savings_pct"] if len(result.savings) > 3 else 0,
        "is_worthwhile": result.is_worthwhile,
        "viable_within_5min_ttl": viable_in_5min,
    }
