/**
 * Chapter 17: Rate Limiter (TypeScript) — Token Bucket and Sliding Window.
 *
 * Implements the two most common rate-limiting algorithms for LLM API
 * production systems. Token Bucket is used server-side by Anthropic;
 * Sliding Window provides predictable burst control.
 *
 * Verified against docs.anthropic.com (May 2026):
 *   - Token bucket algorithm with continuous replenishment
 *   - Tier-based limits (RPM / ITPM / OTPM per model class)
 *   - 429 response with `retry-after` header
 */

// ---------------------------------------------------------------------------
// Domain types
// ---------------------------------------------------------------------------

export type UsageTier = "tier_1" | "tier_2" | "tier_3" | "tier_4";

export interface RateLimitConfig {
  rpm: number;
  itpm: number;
  otpm: number;
}

/** Default per-model rate limits (standard tier, May 2026). */
export const MODEL_RATE_LIMITS: Record<string, RateLimitConfig> = {
  "claude-opus-4-7":            { rpm: 50, itpm: 20_000, otpm:  8_000 },
  "claude-sonnet-4-6":          { rpm: 50, itpm: 20_000, otpm:  8_000 },
  "claude-haiku-4-5-20251001":  { rpm: 50, itpm: 50_000, otpm: 10_000 },
  "claude-opus-4-20250514":     { rpm: 50, itpm: 20_000, otpm:  8_000 },
  "claude-sonnet-4-20250514":   { rpm: 50, itpm: 20_000, otpm:  8_000 },
  "claude-sonnet-3-7-20250219": { rpm: 50, itpm: 20_000, otpm:  8_000 },
  "claude-sonnet-3-5-20241022": { rpm: 50, itpm: 40_000, otpm:  8_000 },
  "claude-haiku-3-5-20241022":  { rpm: 50, itpm: 50_000, otpm: 10_000 },
  "claude-opus-3-20240229":     { rpm: 50, itpm: 20_000, otpm:  4_000 },
  "claude-sonnet-3-20240229":   { rpm: 50, itpm: 40_000, otpm:  8_000 },
  "claude-haiku-3-20240307":    { rpm: 50, itpm: 50_000, otpm: 10_000 },
};

// ---------------------------------------------------------------------------
// Token Bucket
// ---------------------------------------------------------------------------

interface Bucket {
  capacity: number;
  fillRate: number;
  tokens: number;
  lastFill: number;
}

function createBucket(capacity: number): Bucket {
  return {
    capacity,
    fillRate: capacity / 60,
    tokens: capacity,
    lastFill: performance.now(),
  };
}

function refill(bucket: Bucket, now: number): void {
  const elapsed = (now - bucket.lastFill) / 1000; // ms → s
  if (elapsed <= 0) return;
  bucket.tokens = Math.min(bucket.capacity, bucket.tokens + elapsed * bucket.fillRate);
  bucket.lastFill = now;
}

export class TokenBucketRateLimiter {
  private requests: Bucket;
  private inputTokens: Bucket;
  private outputTokens: Bucket;

  constructor(
    capacityRpm: number,
    capacityItpm: number,
    capacityOtpm: number,
  ) {
    this.requests = createBucket(capacityRpm);
    this.inputTokens = createBucket(capacityItpm);
    this.outputTokens = createBucket(capacityOtpm);
  }

  /** Attempt to consume capacity from all three buckets atomically. */
  consume(
    requests: number = 1,
    inputTokens: number = 0,
    outputTokens: number = 0,
  ): boolean {
    const now = performance.now();
    refill(this.requests, now);
    refill(this.inputTokens, now);
    refill(this.outputTokens, now);

    if (
      this.requests.tokens >= requests &&
      this.inputTokens.tokens >= inputTokens &&
      this.outputTokens.tokens >= outputTokens
    ) {
      this.requests.tokens -= requests;
      this.inputTokens.tokens -= inputTokens;
      this.outputTokens.tokens -= outputTokens;
      return true;
    }
    return false;
  }

  /** Current available capacity: [requests, input_tokens, output_tokens]. */
  available(): [number, number, number] {
    const now = performance.now();
    refill(this.requests, now);
    refill(this.inputTokens, now);
    refill(this.outputTokens, now);
    return [
      this.requests.tokens,
      this.inputTokens.tokens,
      this.outputTokens.tokens,
    ];
  }

  /** Seconds until the requested capacity is available. */
  timeUntilAvailable(
    requests: number = 1,
    inputTokens: number = 0,
    outputTokens: number = 0,
  ): number {
    const now = performance.now();
    refill(this.requests, now);
    refill(this.inputTokens, now);
    refill(this.outputTokens, now);

    const wr = this.requests.fillRate > 0
      ? Math.max(0, (requests - this.requests.tokens) / this.requests.fillRate)
      : Infinity;
    const wi = this.inputTokens.fillRate > 0
      ? Math.max(0, (inputTokens - this.inputTokens.tokens) / this.inputTokens.fillRate)
      : Infinity;
    const wo = this.outputTokens.fillRate > 0
      ? Math.max(0, (outputTokens - this.outputTokens.tokens) / this.outputTokens.fillRate)
      : Infinity;
    return Math.max(wr, wi, wo);
  }

  /** Dimension names exceeding the warn threshold. */
  warnThresholdExceeded(): string[] {
    const [req, it, ot] = this.available();
    const warnings: string[] = [];
    if (req < this.requests.capacity * 0.25) warnings.push("rpm");
    if (it  < this.inputTokens.capacity * 0.25) warnings.push("itpm");
    if (ot  < this.outputTokens.capacity * 0.25) warnings.push("otpm");
    return warnings;
  }

  get limits(): [number, number, number] {
    return [this.requests.capacity, this.inputTokens.capacity, this.outputTokens.capacity];
  }
}

// ---------------------------------------------------------------------------
// Sliding Window
// ---------------------------------------------------------------------------

export class SlidingWindowRateLimiter {
  private timestamps: number[] = [];

  constructor(
    private maxRequests: number,
    private windowSeconds: number = 60,
  ) {}

  /** Attempt to record a request. Returns true if permitted. */
  allow(): boolean {
    const now = performance.now() / 1000;
    this.evict(now);
    if (this.timestamps.length < this.maxRequests) {
      this.timestamps.push(now);
      return true;
    }
    return false;
  }

  /** Number of requests in the current window. */
  currentCount(): number {
    this.evict(performance.now() / 1000);
    return this.timestamps.length;
  }

  /** Seconds until the oldest request exits the window. */
  timeUntilNextSlot(): number {
    const now = performance.now() / 1000;
    this.evict(now);
    if (this.timestamps.length < this.maxRequests) return 0;
    return Math.max(0, this.timestamps[0]! + this.windowSeconds - now);
  }

  /** Remaining slots in the window. */
  remaining(): number {
    return Math.max(0, this.maxRequests - this.currentCount());
  }

  private evict(now: number): void {
    const cutoff = now - this.windowSeconds;
    let lo = 0;
    let hi = this.timestamps.length;
    while (lo < hi) {
      const mid = (lo + hi) >>> 1;
      if (this.timestamps[mid]! < cutoff) lo = mid + 1;
      else hi = mid;
    }
    if (lo > 0) {
      this.timestamps = this.timestamps.slice(lo);
    }
  }
}
