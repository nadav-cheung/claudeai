/**
 * Chapter 17: ObservableClient (TypeScript) — production-grade Anthropic client.
 *
 * Wraps all Chapter 17 components into a single observable client with
 * rate limiting, retry, security, budget control, and metrics.
 */

import { TokenBucketRateLimiter } from "./RateLimiter.js";
import { RetryHandler, type BackoffConfig, type CircuitBreakerConfig } from "./RetryHandler.js";
import { PromptInjectionGuard, ToolPermissionScope, DataLeakPrevention } from "./SecurityGuard.js";
import { BudgetController, BudgetConfig, BudgetDecision, estimateCost, estimateInputTokens } from "./BudgetController.js";

// ---------------------------------------------------------------------------
// Metrics
// ---------------------------------------------------------------------------

export interface RequestMetrics {
  requestId: string;
  model: string;
  startTime: number;
  endTime: number;
  latencyMs: number;
  inputTokens: number;
  outputTokens: number;
  cacheReadTokens: number;
  cacheWriteTokens: number;
  cacheHit: boolean;
  estimatedCost: number;
  retryCount: number;
  rateLimited: boolean;
  budgetDecision: string;
  injectionSeverity: string;
  error?: string;
}

export class MetricsCollector {
  metrics: RequestMetrics[] = [];
  constructor(private maxSamples: number = 10_000) {}

  record(m: RequestMetrics): void {
    this.metrics.push(m);
    if (this.metrics.length > this.maxSamples) {
      this.metrics = this.metrics.slice(-this.maxSamples);
    }
  }

  get totalRequests(): number { return this.metrics.length; }
  get errorCount(): number { return this.metrics.filter((m) => m.error).length; }
  get errorRate(): number { return this.errorCount / Math.max(1, this.totalRequests); }
  get cacheHitRate(): number {
    const withCache = this.metrics.filter((m) => m.cacheReadTokens > 0).length;
    return withCache / Math.max(1, this.totalRequests);
  }
  get avgLatencyMs(): number {
    if (!this.metrics.length) return 0;
    return this.metrics.reduce((s, m) => s + m.latencyMs, 0) / this.metrics.length;
  }
  get totalInputTokens(): number { return this.metrics.reduce((s, m) => s + m.inputTokens, 0); }
  get totalOutputTokens(): number { return this.metrics.reduce((s, m) => s + m.outputTokens, 0); }
  get totalCost(): number { return this.metrics.reduce((s, m) => s + m.estimatedCost, 0); }

  latencyPercentile(pct: number): number {
    if (!this.metrics.length) return 0;
    const sorted = [...this.metrics].map((m) => m.latencyMs).sort((a, b) => a - b);
    const idx = Math.floor((pct / 100) * (sorted.length - 1));
    return sorted[Math.min(idx, sorted.length - 1)]!;
  }

  getSummary(): Record<string, unknown> {
    return {
      totalRequests: this.totalRequests,
      errorCount: this.errorCount,
      errorRate: Math.round(this.errorRate * 10000) / 10000,
      cacheHitRate: Math.round(this.cacheHitRate * 10000) / 10000,
      avgLatencyMs: Math.round(this.avgLatencyMs * 10) / 10,
      p50LatencyMs: Math.round(this.latencyPercentile(50) * 10) / 10,
      p95LatencyMs: Math.round(this.latencyPercentile(95) * 10) / 10,
      p99LatencyMs: Math.round(this.latencyPercentile(99) * 10) / 10,
      totalInputTokens: this.totalInputTokens,
      totalOutputTokens: this.totalOutputTokens,
      totalCost: Math.round(this.totalCost * 10000) / 10000,
    };
  }
}

// ---------------------------------------------------------------------------
// Custom errors
// ---------------------------------------------------------------------------

export class SecurityError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "SecurityError";
  }
}

export class BudgetExceededError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "BudgetExceededError";
  }
}

// ---------------------------------------------------------------------------
// ObservableClient
// ---------------------------------------------------------------------------

export interface ObservableClientConfig {
  apiKey: string;
  baseUrl?: string;
  apiVersion?: string;
  defaultModel?: string;
  defaultMaxTokens?: number;
}

export class ObservableClient {
  private config: Required<ObservableClientConfig>;
  private rateLimiter: TokenBucketRateLimiter;
  private retry: RetryHandler;
  private guard: PromptInjectionGuard;
  budget: BudgetController;
  private toolScope: ToolPermissionScope;
  private dlp: DataLeakPrevention;
  metrics: MetricsCollector;

  constructor(
    config: ObservableClientConfig,
    opts?: {
      rateLimiter?: TokenBucketRateLimiter;
      retryHandler?: RetryHandler;
      securityGuard?: PromptInjectionGuard;
      budgetCtrl?: BudgetController;
      toolScope?: ToolPermissionScope;
    },
  ) {
    this.config = {
      baseUrl: "https://api.anthropic.com",
      apiVersion: "2023-06-01",
      defaultModel: "claude-sonnet-4-20250514",
      defaultMaxTokens: 4096,
      ...config,
    };
    this.rateLimiter = opts?.rateLimiter ?? new TokenBucketRateLimiter(50, 20_000, 8_000);
    this.retry = opts?.retryHandler ?? new RetryHandler();
    this.guard = opts?.securityGuard ?? new PromptInjectionGuard();
    this.budget = opts?.budgetCtrl ?? new BudgetController();
    this.toolScope = opts?.toolScope ?? new ToolPermissionScope();
    this.dlp = new DataLeakPrevention(this.guard);
    this.metrics = new MetricsCollector();
  }

  // ------------------------------------------------------------------
  // Tool Security
  // ------------------------------------------------------------------

  checkToolCall(toolName: string, toolInput: Record<string, unknown>): boolean {
    const decision = this.toolScope.check(toolName, toolInput);
    if (!decision.allowed) {
      console.warn(`Tool call blocked: ${toolName} — ${decision.reason}`);
      return false;
    }
    return true;
  }

  auditToolResult(
    toolName: string,
    toolInput: Record<string, unknown>,
    toolResult: unknown,
  ): void {
    this.dlp.auditToolCall(toolName, toolInput, toolResult);
  }

  // ------------------------------------------------------------------
  // Observability
  // ------------------------------------------------------------------

  healthCheck(): Record<string, unknown> {
    return {
      budget: this.budget.getSummary(),
      metrics: this.metrics.getSummary(),
      rateLimiter: {
        available: this.rateLimiter.available(),
        limits: this.rateLimiter.limits,
        warnings: this.rateLimiter.warnThresholdExceeded(),
      },
    };
  }

  // ------------------------------------------------------------------
  // Core API (mockable — uses fetch)
  // ------------------------------------------------------------------

  async messagesCreate(params: {
    messages: Array<{ role: string; content: string | unknown[] }>;
    model?: string;
    maxTokens?: number;
    system?: string;
    tools?: unknown[];
    temperature?: number;
    metadata?: Record<string, unknown>;
    traceId?: string;
  }): Promise<Record<string, unknown>> {
    const effectiveModel = params.model ?? this.config.defaultModel;
    const effectiveMax = params.maxTokens ?? this.config.defaultMaxTokens;
    const traceId = params.traceId ?? crypto.randomUUID();

    // 1. Security: scan user messages
    const userContent = this.extractUserContent(params.messages);
    const detection = this.guard.scan(userContent);
    if (detection.severity === "high" || detection.severity === "critical") {
      throw new SecurityError(
        `Prompt injection detected (severity=${detection.severity}): ${detection.reason}`,
      );
    }

    // 2. Budget: check
    const estimatedInput = estimateInputTokens(userContent);
    const [decision, approvedModel] = this.budget.check(effectiveModel, estimatedInput, effectiveMax);
    const modelToUse = decision === "block" ? effectiveModel : approvedModel;

    if (decision === "block") {
      throw new BudgetExceededError(
        `Budget exhausted: spent $${this.budget.spent.toFixed(2)} of $${this.budget.config.hardLimit.toFixed(2)}`,
      );
    }

    // 3. Rate limiting
    const metrics: RequestMetrics = {
      requestId: traceId,
      model: modelToUse,
      startTime: performance.now(),
      endTime: 0,
      latencyMs: 0,
      inputTokens: 0,
      outputTokens: 0,
      cacheReadTokens: 0,
      cacheWriteTokens: 0,
      cacheHit: false,
      estimatedCost: 0,
      retryCount: 0,
      rateLimited: false,
      budgetDecision: decision,
      injectionSeverity: detection.severity,
    };

    try {
      const response = await this.retry.execute(
        async () => {
          if (!this.rateLimiter.consume(1, estimatedInput, effectiveMax)) {
            metrics.rateLimited = true;
            const wait = this.rateLimiter.timeUntilAvailable(1, estimatedInput, effectiveMax);
            await new Promise((r) => setTimeout(r, Math.max(0, wait * 1000)));
            this.rateLimiter.consume(1, estimatedInput, effectiveMax);
          }

          const url = `${this.config.baseUrl}/v1/messages`;
          const body: Record<string, unknown> = {
            model: modelToUse,
            max_tokens: effectiveMax,
            messages: params.messages,
          };
          if (params.system) body.system = params.system;
          if (params.tools) body.tools = params.tools;
          if (params.temperature !== undefined) body.temperature = params.temperature;
          if (params.metadata) body.metadata = params.metadata;

          const resp = await fetch(url, {
            method: "POST",
            headers: {
              "x-api-key": this.config.apiKey,
              "anthropic-version": this.config.apiVersion,
              "content-type": "application/json",
            },
            body: JSON.stringify(body),
          });

          if (!resp.ok) {
            const errorBody = await resp.text().catch(() => "");
            const err: any = new Error(`API error ${resp.status}: ${errorBody.slice(0, 500)}`);
            err.statusCode = resp.status;
            err.headers = Object.fromEntries(resp.headers.entries());
            throw err;
          }

          return (await resp.json()) as Record<string, unknown>;
        },
        {
          onRetry: (attempt) => {
            metrics.retryCount = attempt;
            console.warn(`Retry attempt ${attempt}/${this.retry.backoff.maxAttempts}`);
          },
        },
      );

      // Record
      const usage = (response as any)?.usage ?? {};
      const it = usage.input_tokens ?? 0;
      const ot = usage.output_tokens ?? 0;
      const cr = usage.cache_read_input_tokens ?? 0;
      const cw = usage.cache_creation_input_tokens ?? 0;

      this.budget.record(modelToUse, it, ot, cw, cr);

      metrics.endTime = performance.now();
      metrics.latencyMs = metrics.endTime - metrics.startTime;
      metrics.inputTokens = it;
      metrics.outputTokens = ot;
      metrics.cacheReadTokens = cr;
      metrics.cacheWriteTokens = cw;
      metrics.cacheHit = cr > 0;
      metrics.estimatedCost = estimateCost(modelToUse, it, ot, cw, cr);
      this.metrics.record(metrics);

      return response;
    } catch (err) {
      metrics.error = String(err);
      metrics.endTime = performance.now();
      metrics.latencyMs = metrics.endTime - metrics.startTime;
      this.metrics.record(metrics);
      throw err;
    }
  }

  private extractUserContent(
    messages: Array<{ role: string; content: string | unknown[] }>,
  ): string {
    const parts: string[] = [];
    for (const msg of messages) {
      if (msg.role !== "user") continue;
      if (typeof msg.content === "string") {
        parts.push(msg.content);
      } else if (Array.isArray(msg.content)) {
        for (const block of msg.content) {
          if (typeof block === "object" && block !== null && "text" in block) {
            parts.push(String((block as any).text));
          }
        }
      }
    }
    return parts.join(" ");
  }
}
