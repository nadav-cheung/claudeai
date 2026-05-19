/**
 * Chapter 17: BudgetController (TypeScript) — hard limit, soft alert,
 * and auto-downgrade for LLM API cost control.
 *
 * Based on Anthropic's pricing model and spend-limit tier system
 * (docs.anthropic.com, May 2026).
 */

// ---------------------------------------------------------------------------
// Domain types
// ---------------------------------------------------------------------------

export type BudgetDecision = "allow" | "warn" | "block" | "downgrade";
export type BudgetPeriod = "daily" | "weekly" | "monthly";

export interface ModelPricing {
  inputPricePerMTok: number;
  outputPricePerMTok: number;
  cacheWritePricePerMTok: number;
  cacheReadPricePerMTok: number;
}

/** Current pricing (May 2026). */
export const MODEL_PRICING: Record<string, ModelPricing> = {
  "claude-opus-4-7": {
    inputPricePerMTok: 5.00, outputPricePerMTok: 25.00,
    cacheWritePricePerMTok: 6.25, cacheReadPricePerMTok: 0.50,
  },
  "claude-sonnet-4-6": {
    inputPricePerMTok: 3.00, outputPricePerMTok: 15.00,
    cacheWritePricePerMTok: 3.75, cacheReadPricePerMTok: 0.30,
  },
  "claude-haiku-4-5-20251001": {
    inputPricePerMTok: 1.00, outputPricePerMTok: 5.00,
    cacheWritePricePerMTok: 1.25, cacheReadPricePerMTok: 0.10,
  },
  "claude-opus-4-20250514": {
    inputPricePerMTok: 15.00, outputPricePerMTok: 75.00,
    cacheWritePricePerMTok: 18.75, cacheReadPricePerMTok: 1.50,
  },
  "claude-sonnet-4-20250514": {
    inputPricePerMTok: 3.00, outputPricePerMTok: 15.00,
    cacheWritePricePerMTok: 3.75, cacheReadPricePerMTok: 0.30,
  },
  "claude-haiku-3-5-20241022": {
    inputPricePerMTok: 0.80, outputPricePerMTok: 4.00,
    cacheWritePricePerMTok: 1.00, cacheReadPricePerMTok: 0.08,
  },
};

/** Estimate cost of an API call in USD. */
export function estimateCost(
  model: string,
  inputTokens: number = 0,
  outputTokens: number = 0,
  cacheWriteTokens: number = 0,
  cacheReadTokens: number = 0,
): number {
  const pricing = MODEL_PRICING[model] ?? MODEL_PRICING["claude-sonnet-4-20250514"]!;
  return (
    (inputTokens / 1_000_000) * pricing.inputPricePerMTok +
    (outputTokens / 1_000_000) * pricing.outputPricePerMTok +
    (cacheWriteTokens / 1_000_000) * pricing.cacheWritePricePerMTok +
    (cacheReadTokens / 1_000_000) * pricing.cacheReadPricePerMTok
  );
}

/** Quick token-count estimate: ~4 chars per token. */
export function estimateInputTokens(text: string): number {
  if (!text) return 0;
  return Math.max(1, Math.floor(text.length / 4));
}

export interface SpendRecord {
  timestamp: number;
  model: string;
  inputTokens: number;
  outputTokens: number;
  cost: number;
}

// ---------------------------------------------------------------------------
// BudgetController
// ---------------------------------------------------------------------------

export interface BudgetConfig {
  hardLimit: number;
  warnThreshold: number;  // fraction 0-1
  period: BudgetPeriod;
  autoDowngrade: boolean;
  downgradeMap?: Record<string, string>;
}

export const DEFAULT_BUDGET_CONFIG: BudgetConfig = {
  hardLimit: 500.0,
  warnThreshold: 0.75,
  period: "monthly",
  autoDowngrade: true,
};

const DEFAULT_DOWNGRADE_MAP: Record<string, string> = {
  "claude-opus-4-20250514": "claude-sonnet-4-20250514",
  "claude-sonnet-4-20250514": "claude-haiku-3-5-20241022",
};

export class BudgetController {
  spent = 0;
  private records: SpendRecord[] = [];
  private downgradeMap: Record<string, string>;

  constructor(private config: BudgetConfig = DEFAULT_BUDGET_CONFIG) {
    this.downgradeMap = config.downgradeMap ?? DEFAULT_DOWNGRADE_MAP;
  }

  /** Check budget before an API call. Returns [decision, effectiveModel]. */
  check(
    model: string,
    inputTokens: number,
    outputTokens: number = 0,
  ): [BudgetDecision, string] {
    const estimated = estimateCost(model, inputTokens, outputTokens);
    const projected = this.spent + estimated;
    const warnLimit = this.config.hardLimit * this.config.warnThreshold;

    // Hard block
    if (this.spent >= this.config.hardLimit) return ["block", model];
    if (projected > this.config.hardLimit) return ["block", model];

    // Warning zone
    if (projected >= warnLimit || this.spent >= warnLimit) {
      if (this.config.autoDowngrade) {
        const cheaper = this.findDowngrade(model);
        if (cheaper !== model) {
          const cheaperCost = estimateCost(cheaper, inputTokens, outputTokens);
          if (this.spent + cheaperCost < this.config.hardLimit) {
            return ["downgrade", cheaper];
          }
        }
      }
      return ["warn", model];
    }

    return ["allow", model];
  }

  /** Record actual spend after an API call. */
  record(
    model: string,
    inputTokens: number = 0,
    outputTokens: number = 0,
    cacheWriteTokens: number = 0,
    cacheReadTokens: number = 0,
  ): SpendRecord {
    const cost = estimateCost(model, inputTokens, outputTokens, cacheWriteTokens, cacheReadTokens);
    const rec: SpendRecord = {
      timestamp: Date.now(),
      model,
      inputTokens,
      outputTokens,
      cost,
    };
    this.records.push(rec);
    this.spent += cost;
    return rec;
  }

  get remaining(): number {
    return Math.max(0, this.config.hardLimit - this.spent);
  }

  get utilizationPct(): number {
    if (this.config.hardLimit <= 0) return 100;
    return Math.min(100, (this.spent / this.config.hardLimit) * 100);
  }

  getSummary(): Record<string, unknown> {
    return {
      spent: Math.round(this.spent * 10000) / 10000,
      remaining: Math.round(this.remaining * 10000) / 10000,
      hardLimit: this.config.hardLimit,
      utilizationPct: Math.round(this.utilizationPct * 10) / 10,
      period: this.config.period,
      totalCalls: this.records.length,
    };
  }

  getModelBreakdown(): Record<string, number> {
    const breakdown: Record<string, number> = {};
    for (const rec of this.records) {
      breakdown[rec.model] = (breakdown[rec.model] ?? 0) + rec.cost;
    }
    for (const k of Object.keys(breakdown)) {
      breakdown[k] = Math.round(breakdown[k]! * 1_000_000) / 1_000_000;
    }
    return breakdown;
  }

  private findDowngrade(model: string): string {
    return this.downgradeMap[model] ?? model;
  }
}
