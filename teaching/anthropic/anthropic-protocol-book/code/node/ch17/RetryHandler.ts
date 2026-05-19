/**
 * Chapter 17: RetryHandler (TypeScript) — exponential backoff, jitter,
 * circuit breaker, and idempotency.
 *
 * Verified against docs.anthropic.com/en/api/errors (May 2026):
 *   429 rate_limit_error  — retryable
 *   500 api_error         — retryable
 *   529 overloaded_error  — retryable
 *   400-413               — NOT retryable
 */

// ---------------------------------------------------------------------------
// Domain types
// ---------------------------------------------------------------------------

export type ErrorCategory =
  | "retryable_rate_limit"
  | "retryable_server"
  | "retryable_network"
  | "non_retryable";

export type CircuitState = "closed" | "open" | "half_open";

export const RETRYABLE_CATEGORIES: ReadonlySet<ErrorCategory> = new Set([
  "retryable_rate_limit",
  "retryable_server",
  "retryable_network",
]);

// ---------------------------------------------------------------------------
// Error classification
// ---------------------------------------------------------------------------

export function classifyError(
  statusCode?: number,
  error?: unknown,
): ErrorCategory {
  if (statusCode !== undefined) {
    if (statusCode === 429) return "retryable_rate_limit";
    if (statusCode === 500 || statusCode === 529) return "retryable_server";
    if (statusCode >= 400 && statusCode < 500) return "non_retryable";
  }
  // Known network errors are retryable
  if (error instanceof TypeError || (error as any)?.code === "ECONNREFUSED") {
    return "retryable_network";
  }
  // Known non-retryable errors (validation, type errors)
  if (error instanceof RangeError || error instanceof SyntaxError) {
    return "non_retryable";
  }
  // Unknown errors: default to retryable_server (could be transient)
  return "retryable_server";
}

// ---------------------------------------------------------------------------
// Retry-After parsing (RFC 7231)
// ---------------------------------------------------------------------------

export function parseRetryAfter(value: string | null): number {
  if (!value) return 0;
  const trimmed = value.trim();
  // delta-seconds
  const delta = Number(trimmed);
  if (Number.isInteger(delta) && delta >= 0) return delta;
  // HTTP-date
  try {
    const target = Date.parse(trimmed);
    if (!isNaN(target)) return Math.max(0, (target - Date.now()) / 1000);
  } catch { /* fall through */ }
  return 0;
}

// ---------------------------------------------------------------------------
// Exponential backoff with jitter
// ---------------------------------------------------------------------------

export interface BackoffConfig {
  baseDelay: number;       // seconds
  factor: number;
  maxExpAttempts: number;
  maxDelay: number;         // seconds
  maxAttempts: number;
}

export const DEFAULT_BACKOFF: BackoffConfig = {
  baseDelay: 1.0,
  factor: 2.0,
  maxExpAttempts: 10,
  maxDelay: 120.0,
  maxAttempts: 5,
};

export function backoffDelay(config: BackoffConfig, attempt: number): number {
  const capped = Math.min(Math.max(attempt, 0), config.maxExpAttempts);
  const delay = Math.min(
    config.baseDelay * Math.pow(config.factor, capped),
    config.maxDelay,
  );
  return Math.random() * delay; // full jitter
}

// ---------------------------------------------------------------------------
// Circuit breaker
// ---------------------------------------------------------------------------

export interface CircuitBreakerConfig {
  failureThreshold: number;
  successThreshold: number;
  resetTimeout: number;       // seconds
  halfOpenMaxRequests: number;
}

export const DEFAULT_CB_CONFIG: CircuitBreakerConfig = {
  failureThreshold: 5,
  successThreshold: 2,
  resetTimeout: 30,
  halfOpenMaxRequests: 1,
};

export class CircuitBreaker {
  config: CircuitBreakerConfig;
  state: CircuitState = "closed";
  failureCount = 0;
  private successCount = 0;
  private openedAt = 0;

  constructor(config?: Partial<CircuitBreakerConfig>) {
    this.config = { ...DEFAULT_CB_CONFIG, ...config };
  }

  allowRequest(): boolean {
    if (this.state === "closed") return true;
    if (this.state === "open") {
      if ((Date.now() - this.openedAt) / 1000 >= this.config.resetTimeout) {
        this.state = "half_open";
        this.successCount = 0;
        return true;
      }
      return false;
    }
    // half_open
    return true;
  }

  recordSuccess(): void {
    if (this.state === "half_open") {
      this.successCount++;
      if (this.successCount >= this.config.successThreshold) {
        this.state = "closed";
        this.failureCount = 0;
      }
    } else {
      this.failureCount = 0;
    }
  }

  recordFailure(): void {
    this.failureCount++;
    if (this.state === "half_open") {
      this.state = "open";
      this.openedAt = Date.now();
    } else if (
      this.state === "closed" &&
      this.failureCount >= this.config.failureThreshold
    ) {
      this.state = "open";
      this.openedAt = Date.now();
    }
  }
}

// ---------------------------------------------------------------------------
// Idempotency
// ---------------------------------------------------------------------------

export function generateIdempotencyKey(_payload: string): string {
  // Use crypto.randomUUID() for production-grade uniqueness.
  // Payload-based idempotency keys are provided by the caller when needed.
  return crypto.randomUUID();
}

export class IdempotencyRegistry {
  private inflight = new Set<string>();
  private completed = new Map<string, unknown>();
  private completedAt = new Map<string, number>();

  constructor(private ttlSeconds: number = 300) {}

  tryAcquire(key: string): boolean {
    this.evictExpired();
    if (this.inflight.has(key)) return false;
    this.inflight.add(key);
    return true;
  }

  complete(key: string, result: unknown): void {
    this.inflight.delete(key);
    this.completed.set(key, result);
    this.completedAt.set(key, performance.now() / 1000);
  }

  getCompleted(key: string): unknown | undefined {
    this.evictExpired();
    return this.completed.get(key);
  }

  private evictExpired(): void {
    const now = performance.now() / 1000;
    for (const [k, t] of this.completedAt) {
      if (now - t > this.ttlSeconds) {
        this.completed.delete(k);
        this.completedAt.delete(k);
      }
    }
  }
}

// ---------------------------------------------------------------------------
// Custom errors
// ---------------------------------------------------------------------------

export class MaxRetriesExceededError extends Error {
  constructor(message: string, public lastError?: unknown) {
    super(message);
    this.name = "MaxRetriesExceededError";
  }
}

export class NonRetryableError extends Error {
  constructor(message: string, public originalError?: unknown) {
    super(message);
    this.name = "NonRetryableError";
  }
}

export class CircuitBreakerOpenError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "CircuitBreakerOpenError";
  }
}

// ---------------------------------------------------------------------------
// RetryHandler
// ---------------------------------------------------------------------------

export interface RetryHandlerOptions {
  backoff?: Partial<BackoffConfig>;
  circuit?: Partial<CircuitBreakerConfig>;
  idempotencyTtl?: number;
}

export class RetryHandler {
  backoff: BackoffConfig;
  private breaker: CircuitBreaker;
  private registry: IdempotencyRegistry;

  constructor(options: RetryHandlerOptions = {}) {
    this.backoff = { ...DEFAULT_BACKOFF, ...options.backoff };
    this.breaker = new CircuitBreaker(options.circuit);
    this.registry = new IdempotencyRegistry(options.idempotencyTtl);
  }

  async execute<T>(
    fn: () => Promise<T>,
    opts?: {
      idempotencyKey?: string;
      onRetry?: (attempt: number, error: unknown) => void;
    },
  ): Promise<T> {
    if (opts?.idempotencyKey) {
      const cached = this.registry.getCompleted(opts.idempotencyKey);
      if (cached !== undefined) return cached as T;
    }

    let lastError: unknown;

    for (let attempt = 0; attempt < this.backoff.maxAttempts; attempt++) {
      if (!this.breaker.allowRequest()) {
        throw new CircuitBreakerOpenError(
          `Circuit breaker is ${this.breaker.state}; ${this.breaker.failureCount} failures.`,
        );
      }

      try {
        const result = await fn();
        this.breaker.recordSuccess();
        if (opts?.idempotencyKey) {
          this.registry.complete(opts.idempotencyKey, result);
        }
        return result;
      } catch (err) {
        lastError = err;
        const category = this.classify(err);

        if (category === "non_retryable") {
          this.breaker.recordFailure();
          throw new NonRetryableError(`Non-retryable error: ${err}`, err);
        }

        this.breaker.recordFailure();

        if (attempt === this.backoff.maxAttempts - 1) break;

        const delay = backoffDelay(this.backoff, attempt);
        const retryAfter = this.extractRetryAfter(err);
        const wait = Math.max(delay, retryAfter);

        opts?.onRetry?.(attempt + 1, err);
        await new Promise((r) => setTimeout(r, wait * 1000));
      }
    }

    throw new MaxRetriesExceededError(
      `All ${this.backoff.maxAttempts} retry attempts exhausted.`,
      lastError,
    );
  }

  private classify(err: unknown): ErrorCategory {
    const status = (err as any)?.statusCode ?? (err as any)?.status;
    return classifyError(status, err);
  }

  private extractRetryAfter(err: unknown): number {
    const headers = (err as any)?.headers;
    if (headers?.["retry-after"]) {
      return parseRetryAfter(headers["retry-after"]);
    }
    return 0;
  }
}
