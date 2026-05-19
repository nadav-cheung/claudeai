/**
 * Chapter 8: Cache Keep-Alive (TypeScript).
 *
 * Implements the Keep-Alive Ping pattern for maintaining Prompt Cache warmth
 * during idle periods. Sends lightweight requests at a configurable interval
 * to reset the 5-minute ephemeral cache TTL.
 *
 * Architecture:
 *   - Uses setInterval-based background pinging
 *   - Only sends when idle (guard via user activity tracking)
 *   - Respects start/stop lifecycle for clean shutdown
 *   - Ping payload: system prompt only (no new messages), minimizing cost
 */

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

export const DEFAULT_PING_INTERVAL = 240;  // 4 minutes
export const MIN_PING_INTERVAL = 60;

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export type SendPingFn = (systemPrompt: string) => Promise<ApiPingResponse>;

export interface ApiPingResponse {
  usage?: {
    input_tokens?: number;
    cache_creation_input_tokens?: number;
    cache_read_input_tokens?: number;
  };
  [key: string]: unknown;
}

export interface KeepAliveStats {
  pingsSent: number;
  pingsFailed: number;
  cacheWritesSaved: number;
  totalCost: number;
}

// ---------------------------------------------------------------------------
// CacheKeepAlive
// ---------------------------------------------------------------------------

export class CacheKeepAlive {
  private sendFn: SendPingFn;
  private systemPrompt: string;
  private pingInterval: number;
  private maxRetries: number;
  private onPingResult?: (success: boolean, cost: number) => void;

  private timerId: ReturnType<typeof setInterval> | null = null;
  private idle: boolean = true;
  private consecutiveFailures: number = 0;

  public stats: KeepAliveStats = {
    pingsSent: 0,
    pingsFailed: 0,
    cacheWritesSaved: 0,
    totalCost: 0,
  };

  constructor(
    sendFn: SendPingFn,
    systemPrompt: string,
    pingInterval: number = DEFAULT_PING_INTERVAL,
    maxRetries: number = 3,
    onPingResult?: (success: boolean, cost: number) => void,
  ) {
    if (pingInterval < MIN_PING_INTERVAL) {
      throw new Error(
        `ping_interval must be >= ${MIN_PING_INTERVAL}s, got ${pingInterval}`,
      );
    }

    this.sendFn = sendFn;
    this.systemPrompt = systemPrompt;
    this.pingInterval = pingInterval * 1000; // convert to ms for setInterval
    this.maxRetries = maxRetries;
    this.onPingResult = onPingResult;
  }

  // ----------------------------------------------------------------
  // Lifecycle
  // ----------------------------------------------------------------

  get isRunning(): boolean {
    return this.timerId !== null;
  }

  start(): void {
    if (this.timerId !== null) return; // already running
    this.consecutiveFailures = 0;
    this.timerId = setInterval(() => {
      if (this.idle && this.consecutiveFailures < this.maxRetries) {
        this.sendPing();
      }
    }, this.pingInterval);
  }

  stop(): void {
    if (this.timerId !== null) {
      clearInterval(this.timerId);
      this.timerId = null;
    }
  }

  // ----------------------------------------------------------------
  // User activity signaling
  // ----------------------------------------------------------------

  userActive(): void {
    this.idle = false;
  }

  userIdle(): void {
    this.idle = true;
  }

  // ----------------------------------------------------------------
  // Internal ping
  // ----------------------------------------------------------------

  private async sendPing(): Promise<void> {
    let success = false;
    let cost = 0;

    try {
      const response = await this.sendFn(this.systemPrompt);
      const usage = response.usage ?? {};
      const readTokens = usage.cache_read_input_tokens ?? 0;
      const writeTokens = usage.cache_creation_input_tokens ?? 0;
      cost = (readTokens * 0.3) / 1_000_000 + (writeTokens * 3.75) / 1_000_000;

      this.consecutiveFailures = 0;
      success = true;
      this.stats.cacheWritesSaved += 1;
    } catch {
      this.consecutiveFailures += 1;
      if (this.consecutiveFailures >= this.maxRetries) {
        this.stop();
      }
    }

    this.stats.pingsSent += 1;
    if (!success) this.stats.pingsFailed += 1;
    this.stats.totalCost += cost;

    if (this.onPingResult) {
      try {
        this.onPingResult(success, cost);
      } catch {
        // callback failures must not break the loop
      }
    }
  }

  // ----------------------------------------------------------------
  // Cost analysis
  // ----------------------------------------------------------------

  estimateKeepaliveCostPerHour(
    systemPromptTokens: number,
    hitRate: number = 1.0,
  ): number {
    const pingIntervalSec = this.pingInterval / 1000;
    const pingsPerHour = 3600 / pingIntervalSec;

    const hitCost = (systemPromptTokens * 0.3) / 1_000_000 * hitRate;
    const missCost = (systemPromptTokens * 3.75) / 1_000_000 * (1 - hitRate);
    const costPerPing = hitCost + missCost;

    return Math.round(costPerPing * pingsPerHour * 1_000_000) / 1_000_000;
  }

  compareToCacheRewrite(
    systemPromptTokens: number,
  ): { keepaliveHourly: number; rewriteCostPerHour: number; savings: number } {
    const pingIntervalSec = this.pingInterval / 1000;
    const pingsPerHour = 3600 / pingIntervalSec;
    const hourly = this.estimateKeepaliveCostPerHour(systemPromptTokens);
    // Without keepalive: each expiry requires a cache rewrite
    const rewritePerHour =
      (systemPromptTokens * 3.75) / 1_000_000 * pingsPerHour;
    return {
      keepaliveHourly: hourly,
      rewriteCostPerHour: Math.round(rewritePerHour * 1_000_000) / 1_000_000,
      savings:
        Math.round((rewritePerHour - hourly) * 1_000_000) / 1_000_000,
    };
  }
}
