/**
 * Chapter 9: BatchClient (TypeScript) — async bulk processing via the
 * Anthropic Message Batches API.
 *
 * Protocol-level implementation communicating directly over HTTP.
 * Covers the full MessageBatch lifecycle:
 *   create → poll status → retrieve results → interpret per-request outcomes.
 *
 * Verified against official docs (docs.anthropic.com, May 2026):
 *   - 50% cost discount on all models
 *   - 24-hour completion SLA (batches expire after 24h)
 *   - Results available for 29 days
 *   - Max 100 000 requests or 256 MB per batch
 *   - Per-request result types: succeeded, errored, canceled, expired
 *   - Prompt caching supported (5-min ephemeral TTL, best-effort)
 *   - 1-hour cache TTL available via cache_control ttl parameter
 */

// ---------------------------------------------------------------------------
// Domain types
// ---------------------------------------------------------------------------

export type BatchProcessingStatus =
  | "in_progress"
  | "ended"
  | "canceled"
  | "expired";

export type ResultType = "succeeded" | "errored" | "canceled" | "expired";

export interface MessageRequest {
  /** Client-defined unique identifier within the batch. */
  custom_id: string;
  /** Standard Messages API parameters (model, max_tokens, messages, …). */
  params: Record<string, unknown>;
}

export interface BatchInfo {
  id: string;
  processing_status: BatchProcessingStatus;
  request_counts: Record<string, number>;
  created_at: string;
  ended_at: string;
  expires_at: string;
  results_url: string | null;
  raw: Record<string, unknown>;
}

export interface BatchResult {
  custom_id: string;
  result_type: ResultType;
  /** Present when result_type is "succeeded". */
  message: Record<string, unknown> | null;
  /** Present when result_type is "errored". */
  error: Record<string, unknown> | null;
  raw: Record<string, unknown>;
}

export interface MakeCacheableRequestOptions {
  custom_id: string;
  model: string;
  max_tokens: number;
  user_message: string;
  system_prompt?: string;
  /** Seconds. If set, uses 1-hour TTL. Omit for default 5-min ephemeral. */
  cache_ttl?: number;
}

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const DEFAULT_BASE_URL = "https://api.anthropic.com";
const ANTHROPIC_VERSION = "2023-06-01";

// ---------------------------------------------------------------------------
// BatchClient
// ---------------------------------------------------------------------------

export class BatchClient {
  private readonly apiKey: string;
  private readonly baseUrl: string;

  constructor(apiKey?: string, baseUrl: string = DEFAULT_BASE_URL) {
    this.apiKey = apiKey ?? process.env["ANTHROPIC_API_KEY"] ?? "";
    this.baseUrl = baseUrl.replace(/\/$/, "");
  }

  // ------------------------------------------------------------------
  // Public API
  // ------------------------------------------------------------------

  /**
   * Create a new Message Batch and return its `batch_id`.
   *
   * The batch starts in `in_progress`.  Requests are processed
   * asynchronously and independently — one failure does not affect others.
   */
  async createBatch(requests: MessageRequest[]): Promise<string> {
    const body = {
      requests: requests.map((r) => ({
        custom_id: r.custom_id,
        params: r.params,
      })),
    };

    const resp = await fetch(`${this.baseUrl}/v1/messages/batches`, {
      method: "POST",
      headers: this._headers(),
      body: JSON.stringify(body),
    });

    if (!resp.ok) {
      throw new Error(
        `Create batch failed (${resp.status}): ${await resp.text()}`,
      );
    }

    const data = (await resp.json()) as { id: string };
    return data.id;
  }

  /**
   * Retrieve the current state of a Message Batch.
   */
  async getBatchStatus(batchId: string): Promise<BatchInfo> {
    const resp = await fetch(
      `${this.baseUrl}/v1/messages/batches/${batchId}`,
      { headers: this._headers() },
    );

    if (!resp.ok) {
      throw new Error(
        `Get batch status failed (${resp.status}): ${await resp.text()}`,
      );
    }

    const data = (await resp.json()) as Record<string, unknown>;
    return this._toBatchInfo(data);
  }

  /**
   * Download and parse a completed batch's JSONL results.
   *
   * Each line of the response is a JSON object representing one request's
   * outcome.  The `custom_id` field allows correlation back to original requests.
   */
  async getBatchResults(batchId: string): Promise<BatchResult[]> {
    const resp = await fetch(
      `${this.baseUrl}/v1/messages/batches/${batchId}/results`,
      { headers: this._headers() },
    );

    if (!resp.ok) {
      throw new Error(
        `Get batch results failed (${resp.status}): ${await resp.text()}`,
      );
    }

    const text = await resp.text();
    return text
      .trim()
      .split("\n")
      .filter((line) => line.trim().length > 0)
      .map((line) => this._parseResultLine(line));
  }

  /**
   * Cancel an in-progress batch.
   *
   * Already-processed requests retain their outcomes; pending requests
   * are marked `canceled` and you are not billed for them.
   */
  async cancelBatch(batchId: string): Promise<BatchInfo> {
    const resp = await fetch(
      `${this.baseUrl}/v1/messages/batches/${batchId}/cancel`,
      {
        method: "POST",
        headers: this._headers(),
      },
    );

    if (!resp.ok) {
      throw new Error(
        `Cancel batch failed (${resp.status}): ${await resp.text()}`,
      );
    }

    const data = (await resp.json()) as Record<string, unknown>;
    return this._toBatchInfo(data);
  }

  /**
   * List all batches in the workspace, newest first.
   */
  async listBatches(limit: number = 20, afterId?: string): Promise<BatchInfo[]> {
    const params = new URLSearchParams({ limit: String(limit) });
    if (afterId) params.set("after_id", afterId);

    const resp = await fetch(
      `${this.baseUrl}/v1/messages/batches?${params.toString()}`,
      { headers: this._headers() },
    );

    if (!resp.ok) {
      throw new Error(
        `List batches failed (${resp.status}): ${await resp.text()}`,
      );
    }

    const data = (await resp.json()) as { data?: Record<string, unknown>[] };
    return (data.data ?? []).map((b) => this._toBatchInfo(b));
  }

  /**
   * Block until the batch finishes, then return results.
   *
   * @param pollInterval - Seconds between status checks (default 60).
   * @param maxWait       - Maximum total wait in seconds (default 86 400 = 24h).
   * @throws If the batch expires, is canceled, or times out.
   */
  async waitForCompletion(
    batchId: string,
    pollInterval: number = 60,
    maxWait: number = 86400,
  ): Promise<BatchResult[]> {
    const deadline = Date.now() + maxWait * 1000;
    const terminal: Set<BatchProcessingStatus> = new Set([
      "ended",
      "canceled",
      "expired",
    ]);

    let info: BatchInfo | null = null;

    while (Date.now() < deadline) {
      info = await this.getBatchStatus(batchId);
      if (terminal.has(info.processing_status)) break;
      await this._sleep(pollInterval * 1000);
    }

    if (!info || !terminal.has(info.processing_status)) {
      throw new Error(
        `Batch ${batchId} did not complete within ${maxWait}s`,
      );
    }

    if (info.processing_status === "ended") {
      return this.getBatchResults(batchId);
    }

    if (info.processing_status === "expired") {
      throw new Error(`Batch ${batchId} expired (24h SLA exceeded)`);
    }

    throw new Error(`Batch ${batchId} was canceled`);
  }

  // ------------------------------------------------------------------
  // Batch + Cache combo helpers
  // ------------------------------------------------------------------

  /**
   * Factory for a request with prompt-caching enabled.
   *
   * When used inside a batch, the batch processing engine attempts to
   * re-use cached prefixes across requests that share identical content,
   * on a best-effort basis.  Cache hit rates typically range from 30-98%
   * depending on traffic patterns.
   *
   * The 1-hour TTL (``cache_ttl=3600``) is useful when batch requests
   * are spread out over a longer window, though batch cache behaviour
   * is still best-effort.
   */
  static makeCacheableRequest(opts: MakeCacheableRequestOptions): MessageRequest {
    const params: Record<string, unknown> = {
      model: opts.model,
      max_tokens: opts.max_tokens,
      messages: [{ role: "user", content: opts.user_message }],
    };

    if (opts.system_prompt) {
      const cacheControl: Record<string, unknown> = { type: "ephemeral" };
      if (opts.cache_ttl !== undefined) {
        cacheControl["ttl"] = opts.cache_ttl;
      }
      params["system"] = [
        {
          type: "text",
          text: opts.system_prompt,
          cache_control: cacheControl,
        },
      ];
    }

    return { custom_id: opts.custom_id, params };
  }

  // ------------------------------------------------------------------
  // Internal helpers
  // ------------------------------------------------------------------

  private _headers(): Record<string, string> {
    return {
      "x-api-key": this.apiKey,
      "anthropic-version": ANTHROPIC_VERSION,
      "content-type": "application/json",
    };
  }

  private _toBatchInfo(data: Record<string, unknown>): BatchInfo {
    return {
      id: String(data["id"] ?? ""),
      processing_status: String(
        data["processing_status"] ?? "in_progress",
      ) as BatchProcessingStatus,
      request_counts: (data["request_counts"] as Record<string, number>) ?? {},
      created_at: String(data["created_at"] ?? ""),
      ended_at: String(data["ended_at"] ?? ""),
      expires_at: String(data["expires_at"] ?? ""),
      results_url: data["results_url"] ? String(data["results_url"]) : null,
      raw: data,
    };
  }

  private _parseResultLine(line: string): BatchResult {
    const data = JSON.parse(line) as Record<string, unknown>;
    const customId = String(data["custom_id"] ?? "");
    const result = (data["result"] ?? {}) as Record<string, unknown>;
    const resultType = String(result["type"] ?? "errored") as ResultType;

    return {
      custom_id: customId,
      result_type: resultType,
      message:
        resultType === "succeeded"
          ? (result["message"] as Record<string, unknown> | null)
          : null,
      error:
        resultType === "errored"
          ? (result["error"] as Record<string, unknown> | null)
          : null,
      raw: data,
    };
  }

  private _sleep(ms: number): Promise<void> {
    return new Promise((resolve) => setTimeout(resolve, ms));
  }
}
