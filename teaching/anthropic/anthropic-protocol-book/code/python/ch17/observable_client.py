"""
Chapter 17: ObservableClient — production-grade Anthropic client.

Wraps all Chapter 17 components (rate limiting, retry, security, budget)
into a single, observable client suitable for production deployment.
Includes structured logging, metrics collection, and distributed tracing support.

Usage::

    client = ObservableClient(
        api_key="sk-ant-...",
        rate_limiter=TokenBucketRateLimiter(50, 20_000, 8_000),
        retry_handler=RetryHandler(BackoffConfig(max_attempts=5)),
        security_guard=PromptInjectionGuard(),
        budget_ctrl=BudgetController(BudgetConfig(hard_limit=500.0)),
    )

    response = client.messages_create(
        model="claude-sonnet-4-20250514",
        messages=[{"role": "user", "content": "Hello"}],
        max_tokens=1024,
    )
"""

from __future__ import annotations

import json
import logging
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple

from budget_controller import (
    BudgetConfig,
    BudgetController,
    BudgetDecision,
    BudgetExceededError,
    estimate_cost,
    estimate_input_tokens,
)
from rate_limiter import TokenBucketRateLimiter
from retry_handler import (
    BackoffConfig,
    CircuitBreakerConfig,
    CircuitBreakerOpenError,
    MaxRetriesExceededError,
    NonRetryableError,
    RetryHandler,
)
from security_guard import (
    DataLeakPrevention,
    InjectionSeverity,
    PromptInjectionGuard,
    ToolPermissionScope,
    ToolPermissionScopeConfig,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Metrics
# ---------------------------------------------------------------------------


@dataclass
class RequestMetrics:
    """Per-request observability metrics."""

    request_id: str
    model: str
    start_time: float
    end_time: float = 0.0
    latency_ms: float = 0.0
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0
    cache_hit: bool = False
    estimated_cost: float = 0.0
    retry_count: int = 0
    rate_limited: bool = False
    budget_decision: str = "allow"
    injection_severity: str = "none"
    error: Optional[str] = None


class MetricsCollector:
    """Collect and aggregate request metrics for observability.

    Supports:
      - Cumulative counters (total requests, errors, cache hits)
      - Latency distribution (p50, p95, p99 approximations via reservoir)
      - Token consumption rate
    """

    def __init__(self, max_samples: int = 10_000) -> None:
        self.metrics: List[RequestMetrics] = []
        self.max_samples = max_samples

    def record(self, m: RequestMetrics) -> None:
        self.metrics.append(m)
        if len(self.metrics) > self.max_samples:
            self.metrics = self.metrics[-self.max_samples:]

    # ------------------------------------------------------------------
    # Aggregations
    # ------------------------------------------------------------------

    @property
    def total_requests(self) -> int:
        return len(self.metrics)

    @property
    def error_count(self) -> int:
        return sum(1 for m in self.metrics if m.error is not None)

    @property
    def error_rate(self) -> float:
        return self.error_count / max(1, self.total_requests)

    @property
    def cache_hit_rate(self) -> float:
        requests_with_cache = sum(1 for m in self.metrics if m.cache_read_tokens > 0)
        return requests_with_cache / max(1, self.total_requests)

    @property
    def avg_latency_ms(self) -> float:
        if not self.metrics:
            return 0.0
        return sum(m.latency_ms for m in self.metrics) / len(self.metrics)

    @property
    def total_input_tokens(self) -> int:
        return sum(m.input_tokens for m in self.metrics)

    @property
    def total_output_tokens(self) -> int:
        return sum(m.output_tokens for m in self.metrics)

    @property
    def total_cost(self) -> float:
        return sum(m.estimated_cost for m in self.metrics)

    def latency_percentile(self, pct: float) -> float:
        """Approximate latency percentile (e.g., 95 for p95)."""
        if not self.metrics:
            return 0.0
        sorted_lat = sorted(m.latency_ms for m in self.metrics)
        idx = int((pct / 100.0) * (len(sorted_lat) - 1))
        return sorted_lat[min(idx, len(sorted_lat) - 1)]

    def get_summary(self) -> Dict[str, object]:
        return {
            "total_requests": self.total_requests,
            "error_count": self.error_count,
            "error_rate": round(self.error_rate, 4),
            "cache_hit_rate": round(self.cache_hit_rate, 4),
            "avg_latency_ms": round(self.avg_latency_ms, 1),
            "p50_latency_ms": round(self.latency_percentile(50), 1),
            "p95_latency_ms": round(self.latency_percentile(95), 1),
            "p99_latency_ms": round(self.latency_percentile(99), 1),
            "total_input_tokens": self.total_input_tokens,
            "total_output_tokens": self.total_output_tokens,
            "total_cost": round(self.total_cost, 4),
        }


# ---------------------------------------------------------------------------
# Observable Client
# ---------------------------------------------------------------------------


@dataclass
class ObservableClientConfig:
    """Configuration for the production-grade client."""

    api_key: str
    base_url: str = "https://api.anthropic.com"
    api_version: str = "2023-06-01"
    default_model: str = "claude-sonnet-4-20250514"
    default_max_tokens: int = 4096


class ObservableClient:
    """Production-grade Anthropic API client with all Chapter 17 safeguards.

    Integrates:
      - TokenBucketRateLimiter: proactive rate limiting
      - RetryHandler: exponential backoff + circuit breaker
      - PromptInjectionGuard: input validation
      - BudgetController: cost control with auto-downgrade
      - MetricsCollector: observability and monitoring
      - ToolPermissionScope: tool access control
      - DataLeakPrevention: audit logging and sensitive data filtering
    """

    def __init__(
        self,
        config: ObservableClientConfig,
        rate_limiter: Optional[TokenBucketRateLimiter] = None,
        retry_handler: Optional[RetryHandler] = None,
        security_guard: Optional[PromptInjectionGuard] = None,
        budget_ctrl: Optional[BudgetController] = None,
        tool_scope: Optional[ToolPermissionScope] = None,
    ) -> None:
        self.config = config
        self._rate_limiter = rate_limiter or TokenBucketRateLimiter(50, 20_000, 8_000)
        self._retry = retry_handler or RetryHandler(
            BackoffConfig(max_attempts=5),
            CircuitBreakerConfig(failure_threshold=5),
        )
        self._guard = security_guard or PromptInjectionGuard()
        self._budget = budget_ctrl or BudgetController(BudgetConfig(hard_limit=500.0))
        self._tool_scope = tool_scope or ToolPermissionScope()
        self._dlp = DataLeakPrevention(guard=self._guard)
        self._metrics = MetricsCollector()

        # HTTP client (created per-instance — use a session for connection reuse)
        self._http: Any = None  # set on first use

    # ------------------------------------------------------------------
    # Core API
    # ------------------------------------------------------------------

    def messages_create(
        self,
        messages: List[Dict[str, object]],
        model: Optional[str] = None,
        max_tokens: Optional[int] = None,
        system: Optional[str] = None,
        tools: Optional[List[Dict[str, object]]] = None,
        temperature: Optional[float] = None,
        metadata: Optional[Dict[str, object]] = None,
        trace_id: Optional[str] = None,
    ) -> Dict[str, object]:
        """Send a Messages API request with full production safeguards.

        This method:
        1. Scans user messages for prompt injection
        2. Checks the budget controller (allow/warn/block/downgrade)
        3. Waits for rate limiter capacity
        4. Makes the API call with retry + circuit breaker
        5. Records metrics
        6. Returns the response

        Args:
            messages: List of message objects (role + content).
            model: Model ID (defaults to config.default_model).
            max_tokens: Max output tokens (defaults to config.default_max_tokens).
            system: Optional system prompt.
            tools: Optional tool definitions.
            temperature: Optional temperature.
            metadata: Optional metadata to attach to the request.
            trace_id: Optional distributed trace ID (for observability).

        Returns:
            The API response as a dict (same shape as the JSON response).

        Raises:
            BudgetExceededError: Budget is exhausted.
            SecurityError: Prompt injection detected.
            Various: propagated from RetryHandler.
        """
        effective_model = model or self.config.default_model
        effective_max = max_tokens or self.config.default_max_tokens
        trace_id = trace_id or str(uuid.uuid4())

        # 1. Security: scan user messages for injection
        user_content = self._extract_user_content(messages)
        detection = self._guard.scan(user_content)
        if detection.severity in (InjectionSeverity.HIGH, InjectionSeverity.CRITICAL):
            logger.error(
                "Prompt injection blocked | severity=%s | patterns=%s | trace_id=%s",
                detection.severity.value,
                detection.patterns_matched,
                trace_id,
            )
            raise SecurityError(
                f"Prompt injection detected (severity={detection.severity.value}): "
                f"{detection.reason}"
            )

        # 2. Budget: check spending
        estimated_input = estimate_input_tokens(user_content)
        budget_decision, approved_model = self._budget.check(
            effective_model, estimated_input, effective_max,
        )
        if budget_decision == BudgetDecision.BLOCK:
            raise BudgetExceededError(
                f"Budget exhausted: spent ${self._budget.spent:.2f} of "
                f"${self._budget.config.hard_limit:.2f}"
            )
        if budget_decision == BudgetDecision.DOWNGRADE:
            logger.info(
                "Auto-downgrading model %s → %s (budget tight)",
                effective_model, approved_model,
            )
            effective_model = approved_model

        if budget_decision == BudgetDecision.WARN:
            logger.warning(
                "Budget warning: %.1f%% utilized, %.1f%% threshold",
                self._budget.utilization_pct,
                self._budget.config.warn_threshold * 100,
            )

        # 3. Rate limiting: wait for capacity
        if not self._rate_limiter.consume(
            requests=1,
            input_tokens=estimated_input,
            output_tokens=effective_max,
        ):
            wait = self._rate_limiter.time_until_available(
                1, estimated_input, effective_max,
            )
            logger.info("Rate limiter: waiting %.1fs for capacity", wait)
            time.sleep(wait)
            # Try again
            self._rate_limiter.consume(1, estimated_input, effective_max)

        # 4. Execute with retry
        metrics = RequestMetrics(
            request_id=trace_id,
            model=effective_model,
            start_time=time.time(),
            budget_decision=budget_decision.value,
            injection_severity=detection.severity.value,
        )

        def _call() -> Dict[str, object]:
            return self._make_api_request(
                messages=messages,
                model=effective_model,
                max_tokens=effective_max,
                system=system,
                tools=tools,
                temperature=temperature,
                metadata=metadata,
            )

        retry_count = 0

        def _on_retry(attempt: int, exc: Exception) -> None:
            nonlocal retry_count
            retry_count = attempt
            logger.warning("Retry attempt %d/%d: %s", attempt,
                           self._retry.backoff.max_attempts, exc)

        try:
            response = self._retry.execute(_call, on_retry=_on_retry)
        except (MaxRetriesExceededError, NonRetryableError, CircuitBreakerOpenError) as exc:
            metrics.error = str(exc)
            metrics.end_time = time.time()
            metrics.latency_ms = (metrics.end_time - metrics.start_time) * 1000
            self._metrics.record(metrics)
            raise

        # 5. Record
        usage = response.get("usage", {})
        input_tokens = usage.get("input_tokens", 0)
        output_tokens = usage.get("output_tokens", 0)
        cache_read = usage.get("cache_read_input_tokens", 0)
        cache_create = usage.get("cache_creation_input_tokens", 0)

        # Budget
        self._budget.record(
            effective_model, input_tokens, output_tokens,
            cache_write_tokens=cache_create, cache_read_tokens=cache_read,
        )

        # Metrics
        metrics.end_time = time.time()
        metrics.latency_ms = (metrics.end_time - metrics.start_time) * 1000
        metrics.input_tokens = input_tokens
        metrics.output_tokens = output_tokens
        metrics.cache_read_tokens = cache_read
        metrics.cache_write_tokens = cache_create
        metrics.cache_hit = cache_read > 0
        metrics.estimated_cost = estimate_cost(
            effective_model, input_tokens, output_tokens, cache_create, cache_read,
        )
        metrics.retry_count = retry_count
        self._metrics.record(metrics)

        # Structured log
        logger.info(
            "Request completed | model=%s | latency=%.0fms | tokens_in=%d | "
            "tokens_out=%d | cache_hit=%s | cost=$%.5f | trace_id=%s",
            effective_model,
            metrics.latency_ms,
            input_tokens,
            output_tokens,
            metrics.cache_hit,
            metrics.estimated_cost,
            trace_id,
        )

        return response

    # ------------------------------------------------------------------
    # Tool security
    # ------------------------------------------------------------------

    def check_tool_call(
        self,
        tool_name: str,
        tool_input: Dict[str, object],
    ) -> bool:
        """Check if a tool call is allowed under the current security scope."""
        decision = self._tool_scope.check(tool_name, tool_input)
        if not decision.allowed:
            logger.warning("Tool call blocked: %s — %s", tool_name, decision.reason)
            return False
        return True

    def audit_tool_result(
        self,
        tool_name: str,
        tool_input: Dict[str, object],
        tool_result: object,
    ) -> None:
        """Audit-log a tool execution result."""
        self._dlp.audit_tool_call(tool_name, tool_input, tool_result)

    # ------------------------------------------------------------------
    # Observability
    # ------------------------------------------------------------------

    @property
    def metrics(self) -> MetricsCollector:
        """Return the metrics collector for monitoring."""
        return self._metrics

    @property
    def budget(self) -> BudgetController:
        """Return the budget controller for querying spend status."""
        return self._budget

    def health_check(self) -> Dict[str, object]:
        """Return a comprehensive health/status overview."""
        return {
            "budget": self._budget.get_summary(),
            "metrics": self._metrics.get_summary(),
            "rate_limiter": {
                "available": self._rate_limiter.available(),
                "limits": self._rate_limiter.limits,
                "warnings": self._rate_limiter.warn_threshold_exceeded(),
            },
        }

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _extract_user_content(
        self,
        messages: List[Dict[str, object]],
    ) -> str:
        """Extract concatenated user message text for injection scanning."""
        parts: List[str] = []
        for msg in messages:
            if msg.get("role") != "user":
                continue
            content = msg.get("content", "")
            if isinstance(content, str):
                parts.append(content)
            elif isinstance(content, list):
                for block in content:
                    if isinstance(block, dict):
                        parts.append(str(block.get("text", "")))
        return " ".join(parts)

    def _make_api_request(
        self,
        messages: List[Dict[str, object]],
        model: str,
        max_tokens: int,
        system: Optional[str] = None,
        tools: Optional[List[Dict[str, object]]] = None,
        temperature: Optional[float] = None,
        metadata: Optional[Dict[str, object]] = None,
    ) -> Dict[str, object]:
        """Execute the actual HTTP request (no retry logic — that is in execute())."""
        import httpx

        if self._http is None:
            self._http = httpx.Client(
                base_url=self.config.base_url,
                headers={
                    "x-api-key": self.config.api_key,
                    "anthropic-version": self.config.api_version,
                    "content-type": "application/json",
                },
                timeout=120.0,
            )

        body: Dict[str, object] = {
            "model": model,
            "max_tokens": max_tokens,
            "messages": messages,
        }
        if system:
            body["system"] = system
        if tools:
            body["tools"] = tools
        if temperature is not None:
            body["temperature"] = temperature
        if metadata:
            body["metadata"] = metadata

        resp = self._http.post("/v1/messages", json=body)
        if resp.status_code >= 400:
            if resp.status_code == 429:
                header = resp.headers.get("retry-after")
                raise RateLimitError(
                    f"Rate limited (429). Retry-After: {header}",
                    status_code=429,
                    retry_after=header,
                )
            raise HTTPError(
                f"API error {resp.status_code}: {resp.text[:500]}",
                status_code=resp.status_code,
                response=resp,
            )
        return resp.json()


# ---------------------------------------------------------------------------
# Custom exceptions
# ---------------------------------------------------------------------------


class SecurityError(Exception):
    """Raised when prompt injection or security policy violation is detected."""
    pass


class RateLimitError(Exception):
    """Raised on 429 responses."""

    def __init__(self, message: str, status_code: int = 429,
                 retry_after: Optional[str] = None) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.retry_after = retry_after


class HTTPError(Exception):
    """Raised on non-2xx HTTP responses."""

    def __init__(self, message: str, status_code: int,
                 response: Any = None) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.response = response
