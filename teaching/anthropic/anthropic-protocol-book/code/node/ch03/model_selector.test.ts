/**
 * Tests for the Chapter 3 Model Selector and Token Counter.
 */

import { describe, it, expect } from "vitest";
import {
  ModelSelector,
  TokenCounter,
  selectModelForScenario,
  MODEL_REGISTRY,
} from "./ModelSelector.js";
import type { ModelSpec } from "./ModelSelector.js";

// ---------------------------------------------------------------------------
// ModelSelector Tests
// ---------------------------------------------------------------------------

describe("ModelSelector.select()", () => {
  const selector = new ModelSelector();

  // ── Agentic complexity ──

  it("selects Opus 4.7 for agentic tasks regardless of budget", () => {
    const result = selector.select("agentic", "high");
    expect(result.modelId).toBe("claude-opus-4-7");
  });

  it("selects Opus 4.7 for agentic tasks even with low budget", () => {
    const result = selector.select("agentic", "low");
    expect(result.modelId).toBe("claude-opus-4-7");
  });

  // ── Long context ──

  it("selects Sonnet 4.6 for long context tasks", () => {
    const result = selector.select("medium", "high", 0, { requiresLongContext: true });
    expect(result.modelId).toBe("claude-sonnet-4-6");
  });

  it("selects long context model when context_needed > 200k", () => {
    const result = selector.select("medium", "high", 500_000);
    expect(result.modelId).toBe("claude-sonnet-4-6");
  });

  it("selects Opus 4.7 for agentic + long context", () => {
    const result = selector.select("agentic", "high", 0, { requiresLongContext: true });
    expect(result.modelId).toBe("claude-opus-4-7");
  });

  // ── High complexity ──

  it("selects Sonnet 4.6 for high complexity with low budget", () => {
    const result = selector.select("high", "low");
    expect(result.modelId).toBe("claude-sonnet-4-6");
  });

  it("selects Opus 4.7 for high complexity with medium budget", () => {
    const result = selector.select("high", "medium");
    expect(result.modelId).toBe("claude-opus-4-7");
  });

  it("selects Opus 4.7 for high complexity with high budget", () => {
    const result = selector.select("high", "high");
    expect(result.modelId).toBe("claude-opus-4-7");
  });

  // ── Latency sensitive ──

  it("selects Haiku 4.5 for latency-sensitive tasks", () => {
    const result = selector.select("medium", "high", 0, { latencySensitive: true });
    expect(result.modelId).toBe("claude-haiku-4-5");
  });

  // ── Low budget ──

  it("selects Haiku 4.5 for low budget medium complexity", () => {
    const result = selector.select("medium", "low");
    expect(result.modelId).toBe("claude-haiku-4-5");
  });

  // ── Default ──

  it("defaults to Sonnet 4.6 for medium/high", () => {
    const result = selector.select("medium", "high");
    expect(result.modelId).toBe("claude-sonnet-4-6");
  });

  // ── Validation ──

  it("throws on invalid task complexity", () => {
    expect(() => selector.select("unknown" as never, "high")).toThrow(/taskComplexity/);
  });

  it("throws on invalid budget", () => {
    expect(() => selector.select("medium", "unlimited" as never)).toThrow(/budget/);
  });

  // ── Reasoning ──

  it("returns a reasoning string", () => {
    const result = selector.select("medium", "high");
    expect(result.reasoning.length).toBeGreaterThan(0);
  });

  it("returns the full ModelSpec", () => {
    const result = selector.select("medium", "high");
    expect(result.model.apiId).toBe(result.modelId);
  });
});

// ---------------------------------------------------------------------------
// CostEstimate Tests
// ---------------------------------------------------------------------------

describe("ModelSelector.costEstimate()", () => {
  const selector = new ModelSelector();

  it("calculates standard Opus cost for 1M/1M tokens", () => {
    const cost = selector.costEstimate("claude-opus-4-7", 1_000_000, 1_000_000);
    expect(cost).toBeCloseTo(30.0); // $5 + $25
  });

  it("calculates standard Sonnet cost for 1M/1M tokens", () => {
    const cost = selector.costEstimate("claude-sonnet-4-6", 1_000_000, 1_000_000);
    expect(cost).toBeCloseTo(18.0); // $3 + $15
  });

  it("calculates standard Haiku cost for 1M/1M tokens", () => {
    const cost = selector.costEstimate("claude-haiku-4-5", 1_000_000, 1_000_000);
    expect(cost).toBeCloseTo(6.0); // $1 + $5
  });

  it("returns 0 for zero tokens", () => {
    const cost = selector.costEstimate("claude-opus-4-7", 0, 0);
    expect(cost).toBe(0);
  });

  it("applies cache read multiplier (0.1x)", () => {
    const cost = selector.costEstimate("claude-opus-4-7", 1_000_000, 0, { cacheHit: true });
    expect(cost).toBeCloseTo(0.50); // $5 * 0.1
  });

  it("applies 5m cache write multiplier (1.25x)", () => {
    const cost = selector.costEstimate("claude-opus-4-7", 1_000_000, 0, { cacheDuration: "5m" });
    expect(cost).toBeCloseTo(6.25); // $5 * 1.25
  });

  it("applies 1h cache write multiplier (2x)", () => {
    const cost = selector.costEstimate("claude-opus-4-7", 1_000_000, 0, { cacheDuration: "1h" });
    expect(cost).toBeCloseTo(10.00); // $5 * 2.0
  });

  it("applies batch discount (50%)", () => {
    const cost = selector.costEstimate("claude-sonnet-4-6", 1_000_000, 1_000_000, { batch: true });
    expect(cost).toBeCloseTo(9.0); // $1.50 + $7.50
  });

  it("combines batch and cache read (5% of base)", () => {
    const cost = selector.costEstimate("claude-opus-4-7", 1_000_000, 0, { cacheHit: true, batch: true });
    expect(cost).toBeCloseTo(0.25); // $5 * 0.5 * 0.1
  });

  it("accepts a ModelSpec instance", () => {
    const spec = MODEL_REGISTRY["claude-opus-4-7"]!;
    const cost = selector.costEstimate(spec, 1_000_000, 0);
    expect(cost).toBeCloseTo(5.00);
  });

  it("throws on unknown model ID", () => {
    expect(() => selector.costEstimate("unknown-model", 1000, 100)).toThrow(/Unknown model/);
  });
});

// ---------------------------------------------------------------------------
// CostEstimateMulti Tests
// ---------------------------------------------------------------------------

describe("ModelSelector.costEstimateMulti()", () => {
  const selector = new ModelSelector();

  it("calculates cost without caching", () => {
    const result = selector.costEstimateMulti(
      "claude-sonnet-4-6", 100, 5_000, 500,
      { cachedInputTokens: 0 },
    );
    expect(result.writeCost).toBe(0);
    expect(result.readCost).toBe(0);
    expect(result.savingsPct).toBe(0);
    expect(result.totalCost).toBeGreaterThan(0);
  });

  it("calculates cost with caching and detects savings", () => {
    const result = selector.costEstimateMulti(
      "claude-sonnet-4-6", 100, 3_000, 500,
      { cachedInputTokens: 20_000, cacheDuration: "5m" },
    );
    expect(result.writeCost).toBeGreaterThan(0);
    expect(result.readCost).toBeGreaterThan(0);
    expect(result.savings).toBeGreaterThan(0);
    expect(result.savingsPct).toBeGreaterThan(0);
  });

  it("applies batch discount in multi scenario", () => {
    const result = selector.costEstimateMulti(
      "claude-haiku-4-5", 10_000, 2_000, 200,
      { batch: true },
    );
    expect(result.totalCost).toBeLessThan(30);
  });

  it("shows cache is cheaper after breakeven reads", () => {
    const result = selector.costEstimateMulti(
      "claude-opus-4-7", 10, 1_000, 200,
      { cachedInputTokens: 50_000, cacheDuration: "5m" },
    );
    expect(result.savings).toBeGreaterThan(0);
    expect(result.totalCost).toBeLessThan(result.noCacheCost);
  });
});

// ---------------------------------------------------------------------------
// CacheBreakeven Tests
// ---------------------------------------------------------------------------

describe("ModelSelector.cacheBreakeven()", () => {
  const selector = new ModelSelector();

  it("returns 2 reads for 5m breakeven", () => {
    const result = selector.cacheBreakeven("claude-opus-4-7");
    expect(result["5mBreakevenReads"]).toBe(2);
  });

  it("returns 3 reads for 1h breakeven", () => {
    const result = selector.cacheBreakeven("claude-opus-4-7");
    expect(result["1hBreakevenReads"]).toBe(3);
  });

  it("returns identical breakeven for all current models", () => {
    for (const modelId of ["claude-opus-4-7", "claude-sonnet-4-6", "claude-haiku-4-5"]) {
      const result = selector.cacheBreakeven(modelId);
      expect(result["5mBreakevenReads"]).toBe(2);
      expect(result["1hBreakevenReads"]).toBe(3);
    }
  });
});

// ---------------------------------------------------------------------------
// TokenCounter Tests
// ---------------------------------------------------------------------------

describe("TokenCounter", () => {
  const counter = new TokenCounter();

  it("returns 0 for empty string", () => {
    expect(counter.count("")).toBe(0);
  });

  it("returns at least 1 for non-empty text", () => {
    expect(counter.count("Hello")).toBeGreaterThanOrEqual(1);
  });

  it("uses ~4 chars per token for English", () => {
    const text = "Hello, world! This is a test.";
    const tokens = counter.count(text);
    const expected = Math.ceil(text.length / 4);
    expect(tokens).toBe(expected);
  });

  it("uses ~2 chars per token for Chinese", () => {
    const text = "你好世界这是一个测试";
    const tokens = counter.count(text, "chinese");
    const expected = Math.ceil(text.length / 2);
    expect(tokens).toBe(expected);
  });

  it("uses ~3.5 chars per token for code", () => {
    const text = "def foo(x): return x + 1";
    const tokens = counter.count(text, "code");
    const expected = Math.ceil(text.length / 3.5);
    expect(tokens).toBe(expected);
  });

  it("uses ~3 chars per token for JSON", () => {
    const text = '{"key": "value", "num": 42}';
    const tokens = counter.count(text, "json");
    const expected = Math.ceil(text.length / 3);
    expect(tokens).toBe(expected);
  });

  it("applies Opus 4.7 adjustment factor", () => {
    const adjustedCounter = new TokenCounter(true);
    const text = "Hello, world! This is a test.";
    const standard = Math.ceil(text.length / 4);
    const adjusted = adjustedCounter.count(text);
    expect(adjusted).toBe(Math.round(standard * 1.2));
  });

  it("estimates request tokens for simple messages", () => {
    const messages = [{ role: "user", content: "Hello, Claude!" }];
    const result = counter.estimateRequestTokens(messages);
    expect(result.totalInputTokens).toBeGreaterThan(0);
    expect(result.messagesTokens).toBeGreaterThan(0);
    expect(result.systemTokens).toBe(0);
    expect(result.toolsTokens).toBe(0);
  });

  it("includes system prompt tokens", () => {
    const messages = [{ role: "user", content: "Hi" }];
    const result = counter.estimateRequestTokens(messages, "You are a helpful assistant.");
    expect(result.systemTokens).toBeGreaterThan(0);
    expect(result.totalInputTokens).toBeGreaterThan(result.messagesTokens);
  });

  it("includes tool definition tokens", () => {
    const messages = [{ role: "user", content: "What is the weather?" }];
    const tools = [{
      name: "get_weather",
      description: "Get the current weather",
      input_schema: { type: "object", properties: { location: { type: "string" } } },
    }];
    const result = counter.estimateRequestTokens(messages, null, tools);
    expect(result.toolsTokens).toBeGreaterThan(0);
    expect(result.toolsTokens).toBeGreaterThanOrEqual(346);
  });

  it("handles content blocks array", () => {
    const messages = [{
      role: "user",
      content: [
        { type: "text", text: "Hello" },
        { type: "text", text: "World" },
      ],
    }];
    const result = counter.estimateRequestTokens(messages);
    expect(result.messagesTokens).toBeGreaterThan(0);
  });

  it("handles tool use and tool result blocks", () => {
    const messages = [
      { role: "user", content: "What is the weather?" },
      {
        role: "assistant",
        content: [{ type: "tool_use", name: "get_weather", input: { location: "Beijing" } }],
      },
      {
        role: "user",
        content: [{ type: "tool_result", content: "Sunny, 25C" }],
      },
    ];
    const result = counter.estimateRequestTokens(messages);
    expect(result.totalInputTokens).toBeGreaterThan(0);
  });

  it("returns a breakdown with all keys", () => {
    const messages = [{ role: "user", content: "Hi" }];
    const result = counter.estimateRequestTokens(messages, "Be helpful.");
    const sum = result.systemTokens + result.messagesTokens + result.toolsTokens + result.overheadTokens;
    expect(result.totalInputTokens).toBe(sum);
  });
});

// ---------------------------------------------------------------------------
// Model Registry Tests
// ---------------------------------------------------------------------------

describe("MODEL_REGISTRY", () => {
  it("contains all current primary models", () => {
    const expected = [
      "claude-opus-4-7",
      "claude-sonnet-4-6",
      "claude-haiku-4-5",
      "claude-opus-4-6",
      "claude-sonnet-4-5",
      "claude-opus-4-5",
      "claude-opus-4-1",
    ];
    for (const id of expected) {
      expect(MODEL_REGISTRY[id]).toBeDefined();
    }
  });

  it("has positive prices where output > input", () => {
    for (const spec of Object.values(MODEL_REGISTRY)) {
      expect(spec.inputPricePerMtok).toBeGreaterThan(0);
      expect(spec.outputPricePerMtok).toBeGreaterThan(0);
      expect(spec.outputPricePerMtok).toBeGreaterThan(spec.inputPricePerMtok);
    }
  });

  it("has valid context windows", () => {
    for (const spec of Object.values(MODEL_REGISTRY)) {
      expect(spec.contextWindow).toBeGreaterThan(0);
      expect(spec.maxOutput).toBeGreaterThan(0);
      expect(spec.maxOutput).toBeLessThanOrEqual(spec.contextWindow);
    }
  });

  it("has reasonable cache multipliers", () => {
    for (const spec of Object.values(MODEL_REGISTRY)) {
      expect(spec.cacheWrite5mMult).toBeGreaterThan(1.0);
      expect(spec.cacheWrite1hMult).toBeGreaterThan(spec.cacheWrite5mMult);
      expect(spec.cacheReadMult).toBeGreaterThan(0);
      expect(spec.cacheReadMult).toBeLessThan(1.0);
    }
  });

  it("has Opus 4.7 and 4.6 at same price but different thinking support", () => {
    const opus47 = MODEL_REGISTRY["claude-opus-4-7"]!;
    const opus46 = MODEL_REGISTRY["claude-opus-4-6"]!;
    expect(opus47.inputPricePerMtok).toBe(opus46.inputPricePerMtok);
    expect(opus47.outputPricePerMtok).toBe(opus46.outputPricePerMtok);
    expect(opus47.supportsAdaptiveThinking).toBe(true);
    expect(opus46.supportsExtendedThinking).toBe(true);
  });
});

// ---------------------------------------------------------------------------
// selectModelForScenario Tests (Self-test Q3)
// ---------------------------------------------------------------------------

describe("selectModelForScenario()", () => {
  it("selects Opus 4.7 for agentic tasks", () => {
    expect(selectModelForScenario({ complexity: "agentic", budget: "medium" }))
      .toBe("claude-opus-4-7");
  });

  it("selects Sonnet 4.6 for long context", () => {
    expect(selectModelForScenario({ requires_long_context: true, complexity: "medium", budget: "medium" }))
      .toBe("claude-sonnet-4-6");
  });

  it("selects Sonnet 4.6 for high complexity + low budget", () => {
    expect(selectModelForScenario({ complexity: "high", budget: "low" }))
      .toBe("claude-sonnet-4-6");
  });

  it("selects Opus 4.7 for high complexity + high budget", () => {
    expect(selectModelForScenario({ complexity: "high", budget: "high" }))
      .toBe("claude-opus-4-7");
  });

  it("selects Haiku 4.5 for latency-sensitive tasks", () => {
    expect(selectModelForScenario({ latency_sensitive: true, complexity: "medium", budget: "medium" }))
      .toBe("claude-haiku-4-5");
  });

  it("selects Haiku 4.5 for low budget", () => {
    expect(selectModelForScenario({ budget: "low", complexity: "medium" }))
      .toBe("claude-haiku-4-5");
  });

  it("defaults to Sonnet 4.6", () => {
    expect(selectModelForScenario({ complexity: "medium", budget: "medium" }))
      .toBe("claude-sonnet-4-6");
  });
});
