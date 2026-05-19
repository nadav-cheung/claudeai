/**
 * Tests for Chapter 17: RetryHandler, backoff, circuit breaker, idempotency.
 */
import { describe, it, expect, vi } from "vitest";
import {
  classifyError,
  parseRetryAfter,
  backoffDelay,
  DEFAULT_BACKOFF,
  CircuitBreaker,
  CircuitBreakerOpenError,
  IdempotencyRegistry,
  generateIdempotencyKey,
  RetryHandler,
  MaxRetriesExceededError,
  NonRetryableError,
} from "./RetryHandler.js";

describe("classifyError", () => {
  it("429 is rate limit", () => expect(classifyError(429)).toBe("retryable_rate_limit"));
  it("500 is server", () => expect(classifyError(500)).toBe("retryable_server"));
  it("529 is server", () => expect(classifyError(529)).toBe("retryable_server"));
  it("400 is non-retryable", () => expect(classifyError(400)).toBe("non_retryable"));
  it("401 is non-retryable", () => expect(classifyError(401)).toBe("non_retryable"));
  it("403 is non-retryable", () => expect(classifyError(403)).toBe("non_retryable"));
});

describe("parseRetryAfter", () => {
  it("parses delta seconds", () => expect(parseRetryAfter("30")).toBe(30));
  it("null returns 0", () => expect(parseRetryAfter(null)).toBe(0));
  it("empty returns 0", () => expect(parseRetryAfter("")).toBe(0));
  it("invalid returns 0", () => expect(parseRetryAfter("not-a-number")).toBe(0));
});

describe("backoffDelay", () => {
  it("first attempt is within [0, baseDelay]", () => {
    for (let i = 0; i < 20; i++) {
      const d = backoffDelay(DEFAULT_BACKOFF, 0);
      expect(d).toBeGreaterThanOrEqual(0);
      expect(d).toBeLessThanOrEqual(DEFAULT_BACKOFF.baseDelay);
    }
  });

  it("grows exponentially", () => {
    for (let i = 0; i < 10; i++) {
      const d = backoffDelay(DEFAULT_BACKOFF, 3);
      expect(d).toBeGreaterThanOrEqual(0);
      expect(d).toBeLessThanOrEqual(DEFAULT_BACKOFF.baseDelay * 8);
    }
  });

  it("respects maxDelay", () => {
    const cfg = { ...DEFAULT_BACKOFF, maxDelay: 5 };
    for (let i = 0; i < 20; i++) {
      expect(backoffDelay(cfg, 50)).toBeLessThanOrEqual(5);
    }
  });
});

describe("CircuitBreaker", () => {
  it("starts closed", () => {
    const cb = new CircuitBreaker();
    expect(cb.state).toBe("closed");
    expect(cb.allowRequest()).toBe(true);
  });

  it("opens after failures", () => {
    const cb = new CircuitBreaker({ failureThreshold: 3 });
    for (let i = 0; i < 3; i++) cb.recordFailure();
    expect(cb.state).toBe("open");
    expect(cb.allowRequest()).toBe(false);
  });

  it("transitions through half-open to closed", async () => {
    const cb = new CircuitBreaker({ failureThreshold: 1, resetTimeout: 0.01, successThreshold: 2 });
    cb.recordFailure();
    expect(cb.state).toBe("open");
    await vi.waitFor(() => expect(cb.allowRequest()).toBe(true), { timeout: 100 });
    expect(cb.state).toBe("half_open");
    cb.recordSuccess();
    cb.recordSuccess();
    expect(cb.state).toBe("closed");
  });

  it("half-open failure reopens", async () => {
    const cb = new CircuitBreaker({ failureThreshold: 1, resetTimeout: 0.01 });
    cb.recordFailure();
    await vi.waitFor(() => expect(cb.allowRequest()).toBe(true), { timeout: 100 });
    cb.recordFailure();
    expect(cb.state).toBe("open");
  });
});

describe("IdempotencyRegistry", () => {
  it("acquires new key", () => {
    const reg = new IdempotencyRegistry();
    expect(reg.tryAcquire("key1")).toBe(true);
  });

  it("rejects duplicate", () => {
    const reg = new IdempotencyRegistry();
    reg.tryAcquire("key1");
    expect(reg.tryAcquire("key1")).toBe(false);
  });

  it("completes and retrieves", () => {
    const reg = new IdempotencyRegistry();
    reg.tryAcquire("key1");
    reg.complete("key1", { result: "ok" });
    expect(reg.getCompleted("key1")).toEqual({ result: "ok" });
  });
});

describe("RetryHandler", () => {
  it("successful call no retry", async () => {
    const handler = new RetryHandler();
    let calls = 0;
    const result = await handler.execute(async () => { calls++; return "ok"; });
    expect(result).toBe("ok");
    expect(calls).toBe(1);
  });

  it("retries then succeeds", async () => {
    const handler = new RetryHandler({ backoff: { ...DEFAULT_BACKOFF, baseDelay: 0.001, maxAttempts: 5 } });
    let calls = 0;
    const result = await handler.execute(async () => {
      calls++;
      if (calls < 3) throw new Error("transient");
      return "ok";
    });
    expect(result).toBe("ok");
    expect(calls).toBe(3);
  });

  it("max retries exceeded", async () => {
    const handler = new RetryHandler({ backoff: { ...DEFAULT_BACKOFF, baseDelay: 0.001, maxAttempts: 3 } });
    await expect(
      handler.execute(async () => { throw new Error("always fails"); }),
    ).rejects.toThrow(MaxRetriesExceededError);
  });

  it("non-retryable raises immediately", async () => {
    const handler = new RetryHandler();
    await expect(
      handler.execute(async () => { throw Object.assign(new Error("bad"), { statusCode: 400 }); }),
    ).rejects.toThrow(NonRetryableError);
  });

  it("calls onRetry callback", async () => {
    const handler = new RetryHandler({ backoff: { ...DEFAULT_BACKOFF, baseDelay: 0.001, maxAttempts: 5 } });
    const retries: number[] = [];
    let first = true;
    await handler.execute(
      async () => {
        if (first) { first = false; throw new Error("fail"); }
        return "ok";
      },
      { onRetry: (n) => retries.push(n) },
    );
    expect(retries).toEqual([1]);
  });
});
