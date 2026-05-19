/**
 * Chapter 8: Cache-Aware Client (TypeScript).
 *
 * A client wrapper that injects cache_control markers into Anthropic API
 * requests and provides cost estimation / breakeven analysis for Prompt Caching.
 *
 * Verified against Anthropic Prompt Caching spec:
 *   - cache_control: { type: "ephemeral" }
 *   - min tokens: 1024 (Sonnet/Opus), 2048 (Haiku)
 *   - max breakpoints: 4 per request
 *   - TTL: 5 min (default ephemeral)
 *   - Pricing: cache write = base * 1.25, cache read = base * 0.10
 */

// ---------------------------------------------------------------------------
// Pricing constants (Claude Sonnet 4, per million tokens)
// ---------------------------------------------------------------------------

export const DEFAULT_WRITE_PRICE_PER_MTok = 3.75;  // $3.75/MTok cache write
export const DEFAULT_READ_PRICE_PER_MTok = 0.30;   // $0.30/MTok cache read
export const DEFAULT_BASE_PRICE_PER_MTok = 3.00;   // $3.00/MTok standard input

// Protocol constraints
export const MIN_CACHEABLE_TOKENS_DEFAULT = 1024;  // Sonnet/Opus
export const MAX_BREAKPOINTS = 4;
export const DEFAULT_CACHE_TTL_SECONDS = 300;      // 5 minutes

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface CacheControl {
  type: "ephemeral";
  scope?: "global";
  ttl?: "5m" | "1h";
}

export interface TextBlock {
  type: "text";
  text: string;
  cache_control?: CacheControl;
}

export interface MessageParam {
  role: "user" | "assistant";
  content: string | (TextBlock | Record<string, unknown>)[];
}

export interface MessagesRequest {
  model: string;
  max_tokens: number;
  system?: string | TextBlock[];
  messages: MessageParam[];
  [key: string]: unknown;
}

export interface UsageBlock {
  input_tokens?: number;
  output_tokens?: number;
  cache_creation_input_tokens?: number;
  cache_read_input_tokens?: number;
}

export interface ApiResponse {
  usage?: UsageBlock;
  [key: string]: unknown;
}

export interface CacheUsage {
  inputTokens: number;
  outputTokens: number;
  cacheCreationTokens: number;
  cacheReadTokens: number;
  uncachedInputTokens: number;
  cacheHitRatio: number;
}

export interface SavingsScenario {
  requests: number;
  noCacheCost: number;
  withCacheCost: number;
  savings: number;
  savingsPct: number;
}

export interface CacheBreakevenResult {
  breakevenReads: number;
  savings: SavingsScenario[];
  isWorthwhile: boolean;
}

export interface BreakevenAnalysisResult {
  breakevenReads: number;
  savingsAt5: number;
  savingsAt10: number;
  savingsAt50: number;
  savingsAt100: number;
  isWorthwhile: boolean;
  viableWithin5minTTL: boolean;
}

// ---------------------------------------------------------------------------
// CacheAwareClient
// ---------------------------------------------------------------------------

export class CacheAwareClient {
  constructor(
    public readonly writePrice: number = DEFAULT_WRITE_PRICE_PER_MTok,
    public readonly readPrice: number = DEFAULT_READ_PRICE_PER_MTok,
    public readonly basePrice: number = DEFAULT_BASE_PRICE_PER_MTok,
    public readonly minCacheableTokens: number = MIN_CACHEABLE_TOKENS_DEFAULT,
    public readonly maxBreakpoints: number = MAX_BREAKPOINTS,
  ) {}

  // ----------------------------------------------------------------
  // Cache marker injection
  // ----------------------------------------------------------------

  /**
   * Inject cache_control markers at specified positions in the request.
   */
  createWithCache(
    request: MessagesRequest,
    cachePoints: number[],
  ): MessagesRequest {
    if (cachePoints.length > this.maxBreakpoints) {
      throw new Error(
        `Too many cache points: ${cachePoints.length} > max ${this.maxBreakpoints}`,
      );
    }

    const result = structuredClone(request);

    // Handle system prompt caching
    if (result.system && cachePoints.length > 0) {
      result.system = this.injectCacheIntoSystem(result.system);
    }

    // Handle message-level caching
    if (result.messages.length > 0 && cachePoints.length > 0) {
      result.messages = this.injectCacheIntoMessages(result.messages, cachePoints);
    }

    return result;
  }

  private injectCacheIntoSystem(
    system: string | TextBlock[],
  ): TextBlock[] {
    if (typeof system === "string") {
      return [
        {
          type: "text",
          text: system,
          cache_control: { type: "ephemeral" },
        },
      ];
    }
    // Array of blocks: put cache_control on last text block
    return system.map((block, i) => {
      if (i === system.length - 1) {
        return { ...block, cache_control: { type: "ephemeral" } as CacheControl };
      }
      return { ...block };
    });
  }

  private injectCacheIntoMessages(
    messages: MessageParam[],
    cachePoints: number[],
  ): MessageParam[] {
    // Normalize negative indices and deduplicate
    const normalized = new Set<number>();
    for (const pt of cachePoints) {
      const idx = pt < 0 ? messages.length + pt : pt;
      if (idx >= 0 && idx < messages.length) {
        normalized.add(idx);
      }
    }
    const sorted = [...normalized].sort((a, b) => a - b);

    return messages.map((msg, i) => {
      if (!sorted.includes(i)) return { ...msg };

      const content = msg.content;
      if (typeof content === "string") {
        return {
          ...msg,
          content: [
            {
              type: "text",
              text: content,
              cache_control: { type: "ephemeral" },
            },
          ],
        };
      }
      // Array of blocks: put cache_control on last block
      return {
        ...msg,
        content: content.map((block, j) => {
          if (j === content.length - 1) {
            return { ...block, cache_control: { type: "ephemeral" } };
          }
          return { ...block };
        }),
      };
    });
  }

  // ----------------------------------------------------------------
  // Cost estimation
  // ----------------------------------------------------------------

  /**
   * Estimate dollar savings from using Prompt Caching.
   */
  estimateCacheSavings(
    promptTokens: number,
    expectedRequests: number,
  ): number {
    if (expectedRequests < 1) return 0;

    const noCacheCost =
      (promptTokens * expectedRequests * this.basePrice) / 1_000_000;

    const cacheWriteCost = (promptTokens * this.writePrice) / 1_000_000;
    const cacheReads = expectedRequests - 1;
    const cacheReadCost =
      (promptTokens * cacheReads * this.readPrice) / 1_000_000;
    const withCacheCost = cacheWriteCost + cacheReadCost;

    return noCacheCost - withCacheCost;
  }

  /**
   * Determine whether Prompt Caching is worthwhile.
   */
  shouldCache(
    promptTokens: number,
    requestsPer5min: number,
  ): boolean {
    if (promptTokens < this.minCacheableTokens) return false;
    if (requestsPer5min <= 1) return false;
    return this.estimateCacheSavings(promptTokens, requestsPer5min) > 0;
  }

  // ----------------------------------------------------------------
  // Breakeven analysis
  // ----------------------------------------------------------------

  /**
   * Compute breakeven point and savings projections for caching.
   */
  breakevenAnalysis(promptTokens: number): CacheBreakevenResult {
    const writeCost = (promptTokens * this.writePrice) / 1_000_000;
    const readCostPerReq = (promptTokens * this.readPrice) / 1_000_000;
    const baseCostPerReq = (promptTokens * this.basePrice) / 1_000_000;

    let breakevenReads: number;
    if (baseCostPerReq <= readCostPerReq) {
      breakevenReads = Infinity;
    } else {
      breakevenReads =
        (writeCost - readCostPerReq) / (baseCostPerReq - readCostPerReq);
    }

    const scenarios = [5, 10, 50, 100];
    const savings: SavingsScenario[] = scenarios.map((n) => {
      const noCache = n * baseCostPerReq;
      const withCache = writeCost + (n - 1) * readCostPerReq;
      return {
        requests: n,
        noCacheCost: Math.round(noCache * 1_000_000) / 1_000_000,
        withCacheCost: Math.round(withCache * 1_000_000) / 1_000_000,
        savings: Math.round((noCache - withCache) * 1_000_000) / 1_000_000,
        savingsPct: noCache > 0
          ? Math.round(((noCache - withCache) / noCache) * 1000) / 10
          : 0,
      };
    });

    return {
      breakevenReads: Math.round(breakevenReads * 10) / 10,
      savings,
      isWorthwhile: breakevenReads < Infinity,
    };
  }

  // ----------------------------------------------------------------
  // Usage extraction
  // ----------------------------------------------------------------

  /**
   * Extract caching usage statistics from an API response.
   */
  static extractUsage(response: ApiResponse): CacheUsage {
    const usage = response.usage ?? {};
    const inputTokens = usage.input_tokens ?? 0;
    const outputTokens = usage.output_tokens ?? 0;
    const cacheCreationTokens = usage.cache_creation_input_tokens ?? 0;
    const cacheReadTokens = usage.cache_read_input_tokens ?? 0;
    const uncachedInputTokens =
      inputTokens - cacheCreationTokens - cacheReadTokens;
    const cacheHitRatio =
      inputTokens > 0 ? cacheReadTokens / inputTokens : 0;

    return {
      inputTokens,
      outputTokens,
      cacheCreationTokens,
      cacheReadTokens,
      uncachedInputTokens,
      cacheHitRatio,
    };
  }

  /**
   * Compute aggregate cache metrics from a list of usage snapshots.
   */
  static monitorCacheHitRate(usages: CacheUsage[]): {
    hitRate: number;
    writeRate: number;
    wasteRate: number;
  } {
    const totalInput = usages.reduce((s, u) => s + u.inputTokens, 0);
    const totalRead = usages.reduce((s, u) => s + u.cacheReadTokens, 0);
    const totalWrite = usages.reduce((s, u) => s + u.cacheCreationTokens, 0);

    if (totalInput === 0) {
      return { hitRate: 0, writeRate: 0, wasteRate: 0 };
    }

    return {
      hitRate: Math.round((totalRead / totalInput) * 10000) / 10000,
      writeRate: Math.round((totalWrite / totalInput) * 10000) / 10000,
      wasteRate:
        Math.round(
          (Math.max(0, totalWrite - totalRead) / Math.max(1, totalInput)) * 10000,
        ) / 10000,
    };
  }
}

// ---------------------------------------------------------------------------
// Standalone convenience function (self-test Question 4)
// ---------------------------------------------------------------------------

export function cacheBreakevenAnalysis(
  writePricePerMTok: number = DEFAULT_WRITE_PRICE_PER_MTok,
  readPricePerMTok: number = DEFAULT_READ_PRICE_PER_MTok,
  basePricePerMTok: number = DEFAULT_BASE_PRICE_PER_MTok,
  cacheableTokens: number = 15000,
): BreakevenAnalysisResult {
  const client = new CacheAwareClient(
    writePricePerMTok,
    readPricePerMTok,
    basePricePerMTok,
  );
  const result = client.breakevenAnalysis(cacheableTokens);

  const viableIn5min = result.breakevenReads <= 5;

  return {
    breakevenReads: result.breakevenReads,
    savingsAt5: result.savings[0]?.savingsPct ?? 0,
    savingsAt10: result.savings[1]?.savingsPct ?? 0,
    savingsAt50: result.savings[2]?.savingsPct ?? 0,
    savingsAt100: result.savings[3]?.savingsPct ?? 0,
    isWorthwhile: result.isWorthwhile,
    viableWithin5minTTL: viableIn5min,
  };
}
