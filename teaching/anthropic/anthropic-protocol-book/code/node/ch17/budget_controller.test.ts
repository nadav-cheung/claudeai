/**
 * Tests for Chapter 17: BudgetController.
 */
import { describe, it, expect } from "vitest";
import {
  BudgetController,
  BudgetConfig,
  estimateCost,
  estimateInputTokens,
} from "./BudgetController.js";

describe("estimateCost", () => {
  it("sonnet input cost", () => {
    const cost = estimateCost("claude-sonnet-4-20250514", 1_000_000);
    expect(cost).toBeCloseTo(3.00, 0);
  });

  it("opus cost", () => {
    const cost = estimateCost("claude-opus-4-20250514", 1_000_000, 1_000_000);
    expect(cost).toBeCloseTo(90.00, 0);
  });

  it("haiku input cost", () => {
    const cost = estimateCost("claude-haiku-3-5-20241022", 1_000_000);
    expect(cost).toBeCloseTo(0.80, 1);
  });

  it("cache read cheaper than fresh input", () => {
    const fresh = estimateCost("claude-sonnet-4-20250514", 1_000_000);
    const cached = estimateCost("claude-sonnet-4-20250514", 0, 0, 0, 1_000_000);
    expect(cached).toBeLessThan(fresh);
    expect(cached).toBeCloseTo(0.30, 0);
  });

  it("unknown model falls back to sonnet", () => {
    const cost = estimateCost("unknown-model", 1_000_000);
    expect(cost).toBeCloseTo(3.00, 0);
  });

  it("zero tokens costs zero", () => {
    expect(estimateCost("claude-sonnet-4-20250514")).toBe(0);
  });
});

describe("estimateInputTokens", () => {
  it("empty text", () => expect(estimateInputTokens("")).toBe(0));
  it("single word", () => expect(estimateInputTokens("Hello")).toBeGreaterThan(0));
  it("long text", () => {
    const text = "The quick brown fox ".repeat(100);
    const tokens = estimateInputTokens(text);
    expect(tokens).toBeGreaterThan(400);
    expect(tokens).toBeLessThan(800);
  });
});

describe("BudgetController", () => {
  const defaultConfig: BudgetConfig = { hardLimit: 500, warnThreshold: 0.75, period: "monthly", autoDowngrade: true };

  it("initial allow", () => {
    const ctrl = new BudgetController(defaultConfig);
    const [decision, model] = ctrl.check("claude-sonnet-4-20250514", 1000);
    expect(decision).toBe("allow");
    expect(model).toBe("claude-sonnet-4-20250514");
  });

  it("warn near threshold", () => {
    const ctrl = new BudgetController({ hardLimit: 100, warnThreshold: 0.5, period: "monthly", autoDowngrade: false });
    ctrl.record("claude-sonnet-4-20250514", 20_000_000); // ~$60
    const [decision] = ctrl.check("claude-sonnet-4-20250514", 1000);
    expect(decision).toBe("warn");
  });

  it("block exceeded", () => {
    const ctrl = new BudgetController({ hardLimit: 10, warnThreshold: 0.75, period: "monthly", autoDowngrade: true });
    ctrl.record("claude-sonnet-4-20250514", 1_000_000, 1_000_000);
    expect(ctrl.spent).toBeGreaterThan(10);
    expect(ctrl.check("claude-sonnet-4-20250514", 100)[0]).toBe("block");
  });

  it("block projected", () => {
    const ctrl = new BudgetController({ hardLimit: 10, warnThreshold: 0.75, period: "monthly", autoDowngrade: false });
    const [decision] = ctrl.check("claude-opus-4-20250514", 1_000_000, 1_000_000);
    expect(decision).toBe("block");
  });

  it("auto downgrade", () => {
    const ctrl = new BudgetController({ hardLimit: 20, warnThreshold: 0.5, period: "monthly", autoDowngrade: true });
    ctrl.record("claude-sonnet-4-20250514", 5_000_000);
    const [decision, model] = ctrl.check("claude-opus-4-20250514", 1000);
    expect(decision).toBe("downgrade");
    expect(model).not.toBe("claude-opus-4-20250514");
  });

  it("spend tracking", () => {
    const ctrl = new BudgetController(defaultConfig);
    ctrl.record("claude-haiku-3-5-20241022", 1_000_000);
    expect(ctrl.spent).toBeGreaterThan(0);
    expect(ctrl.remaining).toBeLessThan(500);
  });

  it("model breakdown", () => {
    const ctrl = new BudgetController(defaultConfig);
    ctrl.record("claude-sonnet-4-20250514", 1_000_000);
    ctrl.record("claude-haiku-3-5-20241022", 1_000_000);
    const breakdown = ctrl.getModelBreakdown();
    expect(breakdown["claude-sonnet-4-20250514"]).toBeDefined();
    expect(breakdown["claude-haiku-3-5-20241022"]).toBeDefined();
  });

  it("summary", () => {
    const ctrl = new BudgetController(defaultConfig);
    const summary = ctrl.getSummary();
    expect(summary.spent).toBe(0);
    expect(summary.remaining).toBe(500);
    expect(summary.utilizationPct).toBe(0);
  });
});
