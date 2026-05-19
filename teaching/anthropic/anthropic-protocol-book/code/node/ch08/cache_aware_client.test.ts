/**
 * Tests for Chapter 8: Cache-Aware Client (TypeScript).
 */

import { describe, it, expect } from "vitest";

import {
  CacheAwareClient,
  cacheBreakevenAnalysis,
  DEFAULT_WRITE_PRICE_PER_MTok,
  DEFAULT_READ_PRICE_PER_MTok,
  DEFAULT_BASE_PRICE_PER_MTok,
  MAX_BREAKPOINTS,
  MIN_CACHEABLE_TOKENS_DEFAULT,
} from "./CacheAwareClient";

import type { MessagesRequest, ApiResponse } from "./CacheAwareClient";

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------

function makeClient(): CacheAwareClient {
  return new CacheAwareClient();
}

function makeRequest(): MessagesRequest {
  return {
    model: "claude-sonnet-4-20250514",
    max_tokens: 1024,
    system: [
      { type: "text", text: "You are an expert programmer." },
    ],
    messages: [
      { role: "user", content: "Write a function." },
      { role: "assistant", content: "Here is the function..." },
    ],
  };
}

// ---------------------------------------------------------------------------
// Cache marker injection tests
// ---------------------------------------------------------------------------

describe("CacheAwareClient - Cache marker injection", () => {
  it("injects cache_control at specified message index", () => {
    const client = makeClient();
    const req = makeRequest();
    const result = client.createWithCache(req, [0]);
    const content = result.messages[0]!.content;
    expect(Array.isArray(content)).toBe(true);
    const lastBlock = (content as Record<string, unknown>[]).at(-1);
    expect(lastBlock).toHaveProperty("cache_control");
    expect((lastBlock as any).cache_control).toEqual({ type: "ephemeral" });
  });

  it("supports negative index for last message", () => {
    const client = makeClient();
    const req = makeRequest();
    const result = client.createWithCache(req, [-1]);
    const content = result.messages[result.messages.length - 1]!.content;
    const lastBlock = (content as Record<string, unknown>[]).at(-1);
    expect((lastBlock as any).cache_control).toEqual({ type: "ephemeral" });
  });

  it("converts string system prompt to block array with cache_control", () => {
    const client = makeClient();
    const req: MessagesRequest = {
      model: "test",
      max_tokens: 100,
      system: "You are helpful.",
      messages: [{ role: "user", content: "Hi" }],
    };
    const result = client.createWithCache(req, [0]);
    expect(Array.isArray(result.system)).toBe(true);
    const system = result.system as Record<string, unknown>[];
    const lastBlock = system.at(-1);
    expect((lastBlock as any).cache_control).toEqual({ type: "ephemeral" });
  });

  it("does not modify messages when cachePoints is empty", () => {
    const client = makeClient();
    const req = makeRequest();
    const result = client.createWithCache(req, []);
    expect(result.messages).toEqual(req.messages);
  });

  it("throws on too many breakpoints", () => {
    const client = makeClient();
    const req = makeRequest();
    expect(() =>
      client.createWithCache(req, [0, 1, 2, 3, 4]),
    ).toThrow(/Too many cache points/);
  });

  it("ignores out-of-range indices", () => {
    const client = makeClient();
    const req = makeRequest();
    const result = client.createWithCache(req, [100]);
    expect(result.messages).toEqual(req.messages);
  });

  it("injects multiple breakpoints correctly", () => {
    const client = makeClient();
    const req: MessagesRequest = {
      model: "test",
      max_tokens: 100,
      messages: [
        { role: "user", content: "A" },
        { role: "assistant", content: "B" },
        { role: "user", content: "C" },
        { role: "assistant", content: "D" },
      ],
    };
    const result = client.createWithCache(req, [0, 2]);
    for (const i of [0, 2]) {
      const content = result.messages[i]!.content as Record<string, unknown>[];
      const lastBlock = content.at(-1);
      expect((lastBlock as any).cache_control).toEqual({ type: "ephemeral" });
    }
  });

  it("does not mutate original request (deep clone)", () => {
    const client = makeClient();
    const req = makeRequest();
    const original = JSON.stringify(req);
    client.createWithCache(req, [0]);
    expect(JSON.stringify(req)).toBe(original);
  });
});

// ---------------------------------------------------------------------------
// Cost estimation tests
// ---------------------------------------------------------------------------

describe("CacheAwareClient - Cost estimation", () => {
  it("estimates positive savings for multiple requests", () => {
    const client = makeClient();
    const savings = client.estimateCacheSavings(15000, 10);
    expect(savings).toBeGreaterThan(0);
  });

  it("estimates negative savings for single request", () => {
    const client = makeClient();
    const savings = client.estimateCacheSavings(15000, 1);
    expect(savings).toBeLessThan(0);
  });

  it("savings scale with token count", () => {
    const client = makeClient();
    const small = client.estimateCacheSavings(1000, 10);
    const large = client.estimateCacheSavings(50000, 10);
    expect(large).toBeGreaterThan(small);
  });

  it("shouldCache returns true for worthwhile scenarios", () => {
    const client = makeClient();
    expect(client.shouldCache(15000, 10)).toBe(true);
  });

  it("shouldCache returns false below min tokens", () => {
    const client = makeClient();
    expect(client.shouldCache(500, 10)).toBe(false);
  });

  it("shouldCache returns false for single request", () => {
    const client = makeClient();
    expect(client.shouldCache(15000, 1)).toBe(false);
  });

  it("respects custom pricing", () => {
    const client = new CacheAwareClient(5.0, 0.5, 4.0);
    const savings = client.estimateCacheSavings(10000, 5);
    // Expected ≈ 0.13
    expect(savings).toBeCloseTo(0.13, 1);
  });
});

// ---------------------------------------------------------------------------
// Breakeven analysis tests
// ---------------------------------------------------------------------------

describe("CacheAwareClient - Breakeven analysis", () => {
  it("returns breakeven at ~1.3 reads with default pricing", () => {
    const client = makeClient();
    const result = client.breakevenAnalysis(15000);
    expect(result.breakevenReads).toBeCloseTo(1.3, 0);
    expect(result.isWorthwhile).toBe(true);
  });

  it("shows high savings at 50 requests", () => {
    const client = makeClient();
    const result = client.breakevenAnalysis(15000);
    const s50 = result.savings.find((s) => s.requests === 50);
    expect(s50).toBeDefined();
    expect(s50!.savingsPct).toBeGreaterThan(80);
  });

  it("shows very high savings at 100 requests", () => {
    const client = makeClient();
    const result = client.breakevenAnalysis(15000);
    const s100 = result.savings.find((s) => s.requests === 100);
    expect(s100).toBeDefined();
    expect(s100!.savingsPct).toBeGreaterThan(85);
  });

  it("savings result has correct structure", () => {
    const client = makeClient();
    const result = client.breakevenAnalysis(15000);
    expect(result.savings).toHaveLength(4);
    for (const s of result.savings) {
      expect(s).toHaveProperty("requests");
      expect(s).toHaveProperty("noCacheCost");
      expect(s).toHaveProperty("withCacheCost");
      expect(s).toHaveProperty("savings");
      expect(s).toHaveProperty("savingsPct");
    }
  });
});

// ---------------------------------------------------------------------------
// Standalone breakeven function (self-test Question 4)
// ---------------------------------------------------------------------------

describe("cacheBreakevenAnalysis function", () => {
  it("returns basic breakeven with default pricing", () => {
    const result = cacheBreakevenAnalysis(3.75, 0.30, 3.00, 15000);
    expect(result.breakevenReads).toBeCloseTo(1.3, 0);
    expect(result.isWorthwhile).toBe(true);
  });

  it("is viable within 5-minute TTL at breakeven ~1.3", () => {
    const result = cacheBreakevenAnalysis(3.75, 0.30, 3.00, 15000);
    expect(result.viableWithin5minTTL).toBe(true);
  });

  it("returns not viable with extremely expensive write", () => {
    const result = cacheBreakevenAnalysis(30.0, 0.30, 3.00, 15000);
    // Write is 10x base: breakeven ~11 reads, not viable in 5-min TTL
    expect(result.breakevenReads).toBeGreaterThan(5);
    expect(result.viableWithin5minTTL).toBe(false);
  });

  it("returns savings projections in correct structure", () => {
    const result = cacheBreakevenAnalysis(undefined, undefined, undefined, 10000);
    expect(result).toHaveProperty("savingsAt5");
    expect(result).toHaveProperty("savingsAt10");
    expect(result).toHaveProperty("savingsAt50");
    expect(result).toHaveProperty("savingsAt100");
    expect(result.savingsAt100).toBeGreaterThan(result.savingsAt5);
  });
});

// ---------------------------------------------------------------------------
// Usage extraction tests
// ---------------------------------------------------------------------------

describe("CacheAwareClient - Usage extraction", () => {
  it("extracts from cache-write response", () => {
    const response: ApiResponse = {
      usage: {
        input_tokens: 15000,
        output_tokens: 500,
        cache_creation_input_tokens: 14800,
        cache_read_input_tokens: 0,
      },
    };
    const usage = CacheAwareClient.extractUsage(response);
    expect(usage.inputTokens).toBe(15000);
    expect(usage.cacheCreationTokens).toBe(14800);
    expect(usage.cacheReadTokens).toBe(0);
    expect(usage.uncachedInputTokens).toBe(200);
  });

  it("extracts from cache-hit response", () => {
    const response: ApiResponse = {
      usage: {
        input_tokens: 15000,
        cache_read_input_tokens: 14800,
        cache_creation_input_tokens: 0,
      },
    };
    const usage = CacheAwareClient.extractUsage(response);
    expect(usage.cacheHitRatio).toBeCloseTo(14800 / 15000, 2);
  });

  it("handles empty usage gracefully", () => {
    const response: ApiResponse = {};
    const usage = CacheAwareClient.extractUsage(response);
    expect(usage.inputTokens).toBe(0);
    expect(usage.cacheHitRatio).toBe(0);
  });

  it("monitors cache hit rate correctly", () => {
    const usages = [
      { inputTokens: 15000, outputTokens: 0, cacheCreationTokens: 14800, cacheReadTokens: 0, uncachedInputTokens: 200, cacheHitRatio: 0 },
      { inputTokens: 15000, outputTokens: 0, cacheCreationTokens: 0, cacheReadTokens: 14800, uncachedInputTokens: 200, cacheHitRatio: 0.98 },
      { inputTokens: 15000, outputTokens: 0, cacheCreationTokens: 0, cacheReadTokens: 14800, uncachedInputTokens: 200, cacheHitRatio: 0.98 },
    ];
    const metrics = CacheAwareClient.monitorCacheHitRate(usages);
    expect(metrics.hitRate).toBeCloseTo(29600 / 45000, 2);
    expect(metrics.wasteRate).toBeGreaterThanOrEqual(0);
  });

  it("monitor returns zeros for empty list", () => {
    const metrics = CacheAwareClient.monitorCacheHitRate([]);
    expect(metrics.hitRate).toBe(0);
    expect(metrics.writeRate).toBe(0);
    expect(metrics.wasteRate).toBe(0);
  });
});

// ---------------------------------------------------------------------------
// Protocol constants tests
// ---------------------------------------------------------------------------

describe("Protocol constants", () => {
  it("has correct pricing defaults", () => {
    expect(DEFAULT_WRITE_PRICE_PER_MTok).toBe(3.75);
    expect(DEFAULT_READ_PRICE_PER_MTok).toBe(0.30);
    expect(DEFAULT_BASE_PRICE_PER_MTok).toBe(3.00);
  });

  it("cache write is premium over base input", () => {
    expect(DEFAULT_WRITE_PRICE_PER_MTok).toBeGreaterThan(DEFAULT_BASE_PRICE_PER_MTok);
  });

  it("cache read is discounted from base input", () => {
    expect(DEFAULT_READ_PRICE_PER_MTok).toBeLessThan(DEFAULT_BASE_PRICE_PER_MTok);
  });

  it("max breakpoints is 4", () => {
    expect(MAX_BREAKPOINTS).toBe(4);
  });

  it("min cacheable tokens is 1024", () => {
    expect(MIN_CACHEABLE_TOKENS_DEFAULT).toBe(1024);
  });
});
