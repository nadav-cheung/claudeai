/**
 * Tests for Chapter 17: TokenBucketRateLimiter and SlidingWindowRateLimiter.
 */
import { describe, it, expect } from "vitest";
import { TokenBucketRateLimiter, SlidingWindowRateLimiter, MODEL_RATE_LIMITS } from "./RateLimiter.js";

describe("TokenBucketRateLimiter", () => {
  it("initial capacity is full", () => {
    const limiter = new TokenBucketRateLimiter(50, 20_000, 8_000);
    const [req, it, ot] = limiter.available();
    expect(req).toBeCloseTo(50, 0);
    expect(it).toBeCloseTo(20_000, 0);
    expect(ot).toBeCloseTo(8_000, 0);
  });

  it("consume reduces capacity", () => {
    const limiter = new TokenBucketRateLimiter(50, 20_000, 8_000);
    expect(limiter.consume(1, 500, 200)).toBe(true);
    const [req, it, ot] = limiter.available();
    expect(req).toBeCloseTo(49, 0);
    expect(it).toBeCloseTo(19_500, 0);
    expect(ot).toBeCloseTo(7_800, 0);
  });

  it("consume fails when exceeded", () => {
    const limiter = new TokenBucketRateLimiter(10, 100, 100);
    for (let i = 0; i < 10; i++) expect(limiter.consume()).toBe(true);
    expect(limiter.consume()).toBe(false);
  });

  it("consume is all-or-nothing", () => {
    const limiter = new TokenBucketRateLimiter(50, 20_000, 8_000);
    expect(limiter.consume(1, 1_000_000, 0)).toBe(false);
    const [req, it, ot] = limiter.available();
    expect(req).toBeCloseTo(50, 0);
    expect(it).toBeCloseTo(20_000, 0);
    expect(ot).toBeCloseTo(8_000, 0);
  });

  it("timeUntilAvailable is 0 when capacity available", () => {
    const limiter = new TokenBucketRateLimiter(50, 20_000, 8_000);
    expect(limiter.timeUntilAvailable(1, 100, 50)).toBe(0);
  });

  it("timeUntilAvailable is positive when exhausted", () => {
    const limiter = new TokenBucketRateLimiter(50, 20_000, 8_000);
    for (let i = 0; i < 50; i++) limiter.consume();
    expect(limiter.timeUntilAvailable(1)).toBeGreaterThan(0);
    expect(limiter.timeUntilAvailable(1)).toBeLessThanOrEqual(2);
  });

  it("warnThresholdExceeded detects consumption", () => {
    const limiter = new TokenBucketRateLimiter(50, 20_000, 8_000);
    expect(limiter.warnThresholdExceeded()).toEqual([]);
    for (let i = 0; i < 40; i++) limiter.consume();
    expect(limiter.warnThresholdExceeded()).toContain("rpm");
  });

  it("limits property returns capacities", () => {
    const limiter = new TokenBucketRateLimiter(10, 100, 50);
    expect(limiter.limits).toEqual([10, 100, 50]);
  });

  it("model rate limits have valid values", () => {
    for (const config of Object.values(MODEL_RATE_LIMITS)) {
      expect(config.rpm).toBeGreaterThan(0);
      expect(config.itpm).toBeGreaterThan(0);
      expect(config.otpm).toBeGreaterThan(0);
    }
  });
});

describe("SlidingWindowRateLimiter", () => {
  it("initially allows", () => {
    const limiter = new SlidingWindowRateLimiter(10, 60);
    expect(limiter.allow()).toBe(true);
    expect(limiter.currentCount()).toBe(1);
  });

  it("exhausts window", () => {
    const limiter = new SlidingWindowRateLimiter(3, 60);
    for (let i = 0; i < 3; i++) expect(limiter.allow()).toBe(true);
    expect(limiter.allow()).toBe(false);
    expect(limiter.currentCount()).toBe(3);
  });

  it("remaining tracks correctly", () => {
    const limiter = new SlidingWindowRateLimiter(10, 60);
    expect(limiter.remaining()).toBe(10);
    for (let i = 0; i < 4; i++) limiter.allow();
    expect(limiter.remaining()).toBe(6);
  });

  it("timeUntilNextSlot is 0 when not full", () => {
    const limiter = new SlidingWindowRateLimiter(10, 60);
    expect(limiter.timeUntilNextSlot()).toBe(0);
  });
});
