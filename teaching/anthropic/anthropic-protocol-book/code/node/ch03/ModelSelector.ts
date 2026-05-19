/**
 * Chapter 3: Model Selector and Cost Estimator.
 *
 * Provides:
 * - ModelSelector: selects the optimal Claude model based on task characteristics.
 * - TokenCounter: estimates token counts for text and complete API requests.
 */

// ---------------------------------------------------------------------------
// Model Registry Types
// ---------------------------------------------------------------------------

export interface ModelSpec {
  readonly apiId: string;
  readonly displayName: string;
  readonly description: string;
  readonly contextWindow: number;
  readonly maxOutput: number;
  readonly inputPricePerMtok: number;
  readonly outputPricePerMtok: number;
  readonly cacheWrite5mMult: number;
  readonly cacheWrite1hMult: number;
  readonly cacheReadMult: number;
  readonly batchDiscount: number;
  readonly generation: number;
  readonly tier: "flagship" | "balanced" | "speed";
  readonly supportsExtendedThinking: boolean;
  readonly supportsAdaptiveThinking: boolean;
}

export interface SelectionResult {
  modelId: string;
  model: ModelSpec;
  reasoning: string;
}

export interface MultiCostResult {
  totalCost: number;
  writeCost: number;
  readCost: number;
  nonCachedCost: number;
  outputCost: number;
  noCacheCost: number;
  savings: number;
  savingsPct: number;
}

export interface TokenEstimate {
  systemTokens: number;
  messagesTokens: number;
  toolsTokens: number;
  overheadTokens: number;
  totalInputTokens: number;
}

export type TaskComplexity = "low" | "medium" | "high" | "agentic";
export type BudgetTier = "low" | "medium" | "high";
export type ContentType = "english" | "chinese" | "code" | "json" | "general";
export type CacheDuration = "5m" | "1h";

// ---------------------------------------------------------------------------
// Complete Model Registry
// ---------------------------------------------------------------------------

export const MODEL_REGISTRY: Record<string, ModelSpec> = {
  // ── Current Primary Models ──
  "claude-opus-4-7": {
    apiId: "claude-opus-4-7",
    displayName: "Claude Opus 4.7",
    description: "Most capable model for complex reasoning and agentic coding",
    contextWindow: 1_000_000,
    maxOutput: 128_000,
    inputPricePerMtok: 5.00,
    outputPricePerMtok: 25.00,
    cacheWrite5mMult: 1.25,
    cacheWrite1hMult: 2.00,
    cacheReadMult: 0.10,
    batchDiscount: 0.50,
    generation: 4,
    tier: "flagship",
    supportsExtendedThinking: false,
    supportsAdaptiveThinking: true,
  },
  "claude-sonnet-4-6": {
    apiId: "claude-sonnet-4-6",
    displayName: "Claude Sonnet 4.6",
    description: "Best combination of speed and intelligence",
    contextWindow: 1_000_000,
    maxOutput: 64_000,
    inputPricePerMtok: 3.00,
    outputPricePerMtok: 15.00,
    cacheWrite5mMult: 1.25,
    cacheWrite1hMult: 2.00,
    cacheReadMult: 0.10,
    batchDiscount: 0.50,
    generation: 4,
    tier: "balanced",
    supportsExtendedThinking: true,
    supportsAdaptiveThinking: false,
  },
  "claude-haiku-4-5": {
    apiId: "claude-haiku-4-5-20251001",
    displayName: "Claude Haiku 4.5",
    description: "Fastest model with near-frontier intelligence",
    contextWindow: 200_000,
    maxOutput: 64_000,
    inputPricePerMtok: 1.00,
    outputPricePerMtok: 5.00,
    cacheWrite5mMult: 1.25,
    cacheWrite1hMult: 2.00,
    cacheReadMult: 0.10,
    batchDiscount: 0.50,
    generation: 4,
    tier: "speed",
    supportsExtendedThinking: false,
    supportsAdaptiveThinking: false,
  },
  // ── Legacy / Still Available Models ──
  "claude-opus-4-6": {
    apiId: "claude-opus-4-6",
    displayName: "Claude Opus 4.6",
    description: "Previous flagship; migrate to Opus 4.7",
    contextWindow: 1_000_000,
    maxOutput: 128_000,
    inputPricePerMtok: 5.00,
    outputPricePerMtok: 25.00,
    cacheWrite5mMult: 1.25,
    cacheWrite1hMult: 2.00,
    cacheReadMult: 0.10,
    batchDiscount: 0.50,
    generation: 4,
    tier: "flagship",
    supportsExtendedThinking: true,
    supportsAdaptiveThinking: false,
  },
  "claude-sonnet-4-5": {
    apiId: "claude-sonnet-4-5-20250929",
    displayName: "Claude Sonnet 4.5",
    description: "Previous balanced model; migrate to Sonnet 4.6",
    contextWindow: 200_000,
    maxOutput: 64_000,
    inputPricePerMtok: 3.00,
    outputPricePerMtok: 15.00,
    cacheWrite5mMult: 1.25,
    cacheWrite1hMult: 2.00,
    cacheReadMult: 0.10,
    batchDiscount: 0.50,
    generation: 4,
    tier: "balanced",
    supportsExtendedThinking: true,
    supportsAdaptiveThinking: false,
  },
  "claude-opus-4-5": {
    apiId: "claude-opus-4-5-20251101",
    displayName: "Claude Opus 4.5",
    description: "Older flagship; migrate to Opus 4.7",
    contextWindow: 200_000,
    maxOutput: 64_000,
    inputPricePerMtok: 5.00,
    outputPricePerMtok: 25.00,
    cacheWrite5mMult: 1.25,
    cacheWrite1hMult: 2.00,
    cacheReadMult: 0.10,
    batchDiscount: 0.50,
    generation: 4,
    tier: "flagship",
    supportsExtendedThinking: true,
    supportsAdaptiveThinking: false,
  },
  "claude-opus-4-1": {
    apiId: "claude-opus-4-1-20250805",
    displayName: "Claude Opus 4.1",
    description: "Legacy model at 3x current pricing; migrate urgently",
    contextWindow: 200_000,
    maxOutput: 32_000,
    inputPricePerMtok: 15.00,
    outputPricePerMtok: 75.00,
    cacheWrite5mMult: 1.25,
    cacheWrite1hMult: 2.00,
    cacheReadMult: 0.10,
    batchDiscount: 0.50,
    generation: 4,
    tier: "flagship",
    supportsExtendedThinking: true,
    supportsAdaptiveThinking: false,
  },
};

// ---------------------------------------------------------------------------
// Token Counter Constants
// ---------------------------------------------------------------------------

const CHAR_PER_TOKEN: Record<ContentType, number> = {
  english: 4.0,
  chinese: 2.0,
  code: 3.5,
  json: 3.0,
  general: 4.0,
};

const TOOL_SYSTEM_PROMPT_OVERHEAD = 346;
const MESSAGE_OVERHEAD_PER_MESSAGE = 5;
const CONTENT_BLOCK_OVERHEAD = 2;

// ---------------------------------------------------------------------------
// Model Selector
// ---------------------------------------------------------------------------

export class ModelSelector {
  static readonly MODELS = MODEL_REGISTRY;

  /**
   * Select the optimal model for the given task characteristics.
   *
   * Implements the decision tree from section 3.2.2.
   */
  select(
    taskComplexity: TaskComplexity,
    budget: BudgetTier,
    contextNeeded: number = 0,
    options?: {
      latencySensitive?: boolean;
      requiresLongContext?: boolean;
    },
  ): SelectionResult {
    this._validateParam(taskComplexity, "taskComplexity", new Set(["low", "medium", "high", "agentic"]));
    this._validateParam(budget, "budget", new Set(["low", "medium", "high"]));

    const latencySensitive = options?.latencySensitive ?? false;
    const requiresLongContext = options?.requiresLongContext ?? false;
    const longCtxNeeded = requiresLongContext || contextNeeded > 200_000;

    // Rule 1: Long context (>200k).
    if (longCtxNeeded) {
      if (taskComplexity === "agentic") {
        return this._result("claude-opus-4-7",
          "Agentic task with >200k context requires Opus 4.7 (1M window + top reasoning).");
      }
      return this._result("claude-sonnet-4-6",
        "Long context (>200k) task — Sonnet 4.6 provides 1M window at best value.");
    }

    // Rule 2: Agentic complexity.
    if (taskComplexity === "agentic") {
      return this._result("claude-opus-4-7",
        "Agentic coding / complex multi-step reasoning requires Opus 4.7.");
    }

    // Rule 3: High complexity + low budget → Sonnet.
    if (taskComplexity === "high" && budget === "low") {
      return this._result("claude-sonnet-4-6",
        "High-complexity task with low budget — Sonnet 4.6 offers near-Opus quality at 60% cost.");
    }

    // Rule 4: High complexity + better budget → Opus.
    if (taskComplexity === "high") {
      return this._result("claude-opus-4-7",
        "High-complexity task with sufficient budget → Opus 4.7 for best quality.");
    }

    // Rule 5: Latency-sensitive or low budget → Haiku.
    if (latencySensitive || budget === "low") {
      return this._result("claude-haiku-4-5",
        latencySensitive
          ? "Latency-sensitive task → Haiku 4.5 (fastest)."
          : "Low budget → Haiku 4.5 at $1/$5 per MTok.");
    }

    // Rule 6: Default → Sonnet.
    return this._result("claude-sonnet-4-6",
      "Default: Sonnet 4.6 — best price/performance for general production use.");
  }

  /**
   * Estimate the USD cost of a single API request.
   */
  costEstimate(
    model: string | ModelSpec,
    inputTokens: number,
    outputTokens: number,
    options?: {
      cacheHit?: boolean;
      cacheDuration?: CacheDuration;
      batch?: boolean;
    },
  ): number {
    const spec = typeof model === "string" ? this._getModel(model) : model;
    const cacheHit = options?.cacheHit ?? false;
    const cacheDuration = options?.cacheDuration;
    const batch = options?.batch ?? false;

    let inputPrice = spec.inputPricePerMtok;

    if (cacheHit) {
      inputPrice *= spec.cacheReadMult;
    } else if (cacheDuration === "5m") {
      inputPrice *= spec.cacheWrite5mMult;
    } else if (cacheDuration === "1h") {
      inputPrice *= spec.cacheWrite1hMult;
    }

    let outputPrice = spec.outputPricePerMtok;

    if (batch) {
      inputPrice *= spec.batchDiscount;
      outputPrice *= spec.batchDiscount;
    }

    const inputCost = (inputTokens / 1_000_000) * inputPrice;
    const outputCost = (outputTokens / 1_000_000) * outputPrice;

    return Math.round((inputCost + outputCost) * 1_000_000) / 1_000_000;
  }

  /**
   * Estimate total cost across multiple requests with optional caching.
   */
  costEstimateMulti(
    model: string | ModelSpec,
    numRequests: number,
    inputTokensPerRequest: number,
    outputTokensPerRequest: number,
    options?: {
      cachedInputTokens?: number;
      cacheDuration?: CacheDuration;
      batch?: boolean;
    },
  ): MultiCostResult {
    const spec = typeof model === "string" ? this._getModel(model) : model;
    const cachedInputTokens = options?.cachedInputTokens ?? 0;
    const cacheDuration = options?.cacheDuration;
    const batch = options?.batch ?? false;

    let writeCost = 0;
    let readCost = 0;

    if (cachedInputTokens > 0 && cacheDuration) {
      writeCost = this.costEstimate(spec, cachedInputTokens, 0, { cacheDuration, batch });
      readCost = this.costEstimate(spec, cachedInputTokens * numRequests, 0, { cacheHit: true, batch });
    }

    const nonCachedCost = inputTokensPerRequest > 0
      ? this.costEstimate(spec, inputTokensPerRequest * numRequests, 0, { batch })
      : 0;

    const outputCost = this.costEstimate(spec, 0, outputTokensPerRequest * numRequests, { batch });

    const totalWithCache = writeCost + readCost + nonCachedCost + outputCost;

    const totalInputTokens = (cachedInputTokens + inputTokensPerRequest) * numRequests;
    const totalNoCache = this.costEstimate(spec, totalInputTokens, outputTokensPerRequest * numRequests, { batch });

    const savings = totalNoCache - totalWithCache;
    const savingsPct = totalNoCache > 0 ? Math.round((savings / totalNoCache) * 10000) / 100 : 0;

    return {
      totalCost: Math.round(totalWithCache * 1_000_000) / 1_000_000,
      writeCost: Math.round(writeCost * 1_000_000) / 1_000_000,
      readCost: Math.round(readCost * 1_000_000) / 1_000_000,
      nonCachedCost: Math.round(nonCachedCost * 1_000_000) / 1_000_000,
      outputCost: Math.round(outputCost * 1_000_000) / 1_000_000,
      noCacheCost: Math.round(totalNoCache * 1_000_000) / 1_000_000,
      savings: Math.round(savings * 1_000_000) / 1_000_000,
      savingsPct,
    };
  }

  /**
   * Calculate the minimum number of cache reads needed to break even.
   */
  cacheBreakeven(model: string | ModelSpec): { "5mBreakevenReads": number; "1hBreakevenReads": number } {
    const spec = typeof model === "string" ? this._getModel(model) : model;

    const breakeven = (writeMult: number): number => {
      return Math.ceil(writeMult / (1 - spec.cacheReadMult));
    };

    return {
      "5mBreakevenReads": breakeven(spec.cacheWrite5mMult),
      "1hBreakevenReads": breakeven(spec.cacheWrite1hMult),
    };
  }

  // ── Private helpers ──

  private _result(modelId: string, reasoning: string): SelectionResult {
    return {
      modelId,
      model: this._getModel(modelId),
      reasoning,
    };
  }

  private _getModel(modelId: string): ModelSpec {
    const spec = MODEL_REGISTRY[modelId];
    if (!spec) {
      throw new Error(`Unknown model: ${modelId}`);
    }
    return spec;
  }

  private _validateParam(value: string, name: string, allowed: Set<string>): void {
    if (!allowed.has(value)) {
      throw new Error(
        `Invalid ${name} '${value}'. Must be one of: ${[...allowed].sort().join(", ")}`,
      );
    }
  }
}

// ---------------------------------------------------------------------------
// Token Counter
// ---------------------------------------------------------------------------

export class TokenCounter {
  private readonly opus47Adjustment: boolean;
  private readonly adjustmentFactor: number;

  constructor(opus47Adjustment: boolean = false) {
    this.opus47Adjustment = opus47Adjustment;
    this.adjustmentFactor = opus47Adjustment ? 1.2 : 1.0;
  }

  /**
   * Estimate token count for a plain text string.
   */
  count(text: string, contentType: ContentType = "general"): number {
    if (!text) return 0;
    const ratio = CHAR_PER_TOKEN[contentType] ?? CHAR_PER_TOKEN.general;
    const raw = Math.max(1, Math.ceil(text.length / ratio));
    return Math.max(1, Math.round(raw * this.adjustmentFactor));
  }

  /**
   * Estimate total input tokens for a full Messages API request.
   */
  estimateRequestTokens(
    messages: Array<Record<string, unknown>>,
    system?: string | null,
    tools?: Array<Record<string, unknown>> | null,
  ): TokenEstimate {
    let systemTokens = 0;
    if (system) {
      systemTokens = this.count(system);
    }

    let messagesTokens = 0;
    for (const msg of messages) {
      const content = msg.content;
      if (typeof content === "string") {
        messagesTokens += this.count(content);
      } else if (Array.isArray(content)) {
        for (const block of content) {
          if (typeof block === "object" && block !== null) {
            const b = block as Record<string, unknown>;
            if (b.type === "text") {
              messagesTokens += this.count(String(b.text ?? ""));
            } else if (b.type === "tool_use") {
              const name = String(b.name ?? "");
              const input = JSON.stringify(b.input ?? {});
              messagesTokens += this.count(name + input, "json");
            } else if (b.type === "tool_result") {
              const result = b.content;
              if (typeof result === "string") {
                messagesTokens += this.count(result);
              } else if (Array.isArray(result)) {
                for (const item of result) {
                  if (typeof item === "object" && item !== null && (item as Record<string, unknown>).type === "text") {
                    messagesTokens += this.count(String((item as Record<string, unknown>).text ?? ""));
                  }
                }
              }
            } else if (b.type === "image") {
              messagesTokens += 200; // conservative minimum
            }
          }
        }
      }
      messagesTokens += MESSAGE_OVERHEAD_PER_MESSAGE;
    }

    let toolsTokens = 0;
    if (tools) {
      for (const tool of tools) {
        const name = String(tool.name ?? "");
        const desc = String(tool.description ?? "");
        const schema = JSON.stringify(tool.input_schema ?? {});
        toolsTokens += this.count(name + desc + schema, "json");
        toolsTokens += CONTENT_BLOCK_OVERHEAD;
      }
      toolsTokens += TOOL_SYSTEM_PROMPT_OVERHEAD;
    }

    const overheadTokens = CONTENT_BLOCK_OVERHEAD;
    const total = systemTokens + messagesTokens + toolsTokens + overheadTokens;

    return {
      systemTokens,
      messagesTokens,
      toolsTokens,
      overheadTokens,
      totalInputTokens: total,
    };
  }
}

// ---------------------------------------------------------------------------
// Standalone function: select_model_for_scenario (Self-test Q3)
// ---------------------------------------------------------------------------

export interface ScenarioTask {
  requires_long_context?: boolean;
  complexity?: string;
  budget?: string;
  latency_sensitive?: boolean;
}

export function selectModelForScenario(task: ScenarioTask): string {
  const requiresLongContext = task.requires_long_context ?? false;
  const complexity = task.complexity ?? "medium";
  const budget = task.budget ?? "medium";
  const latencySensitive = task.latency_sensitive ?? false;

  if (requiresLongContext) return "claude-sonnet-4-6";
  if (complexity === "agentic") return "claude-opus-4-7";
  if (complexity === "high" && budget === "low") return "claude-sonnet-4-6";
  if (complexity === "high") return "claude-opus-4-7";
  if (latencySensitive || budget === "low") return "claude-haiku-4-5";
  return "claude-sonnet-4-6";
}
