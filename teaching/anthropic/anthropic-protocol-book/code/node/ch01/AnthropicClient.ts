/**
 * Chapter 1: Anthropic API HTTP Client (TypeScript).
 *
 * A dependency-free implementation of the Anthropic Messages API client
 * using Node.js 22+ native fetch. Strict TypeScript with zero `any` usage.
 */

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const DEFAULT_BASE_URL = "https://api.anthropic.com/v1/messages";
const DEFAULT_API_VERSION = "2023-06-01";
const DEFAULT_TIMEOUT_MS = 60_000;
const DEFAULT_MAX_RETRIES = 3;

/** HTTP status codes whose responses warrant a retry. */
const RETRYABLE_STATUS_CODES: ReadonlySet<number> = new Set([
  429, 500, 529,
]);

/** Error type strings whose responses warrant a retry. */
const RETRYABLE_ERROR_TYPES: ReadonlySet<string> = new Set([
  "rate_limit_error",
  "api_error",
  "overloaded_error",
]);

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export enum AuthMethod {
  ApiKey = "api-key",
  Bearer = "bearer",
}

export interface ClientConfig {
  readonly apiKey: string;
  readonly authMethod: AuthMethod;
  readonly baseUrl: string;
  readonly apiVersion: string;
  readonly timeoutMs: number;
}

/** Content block types accepted in request messages. */
export type ContentBlock =
  | TextBlock
  | ImageBlock
  | ToolUseBlock
  | ToolResultBlock;

export interface TextBlock {
  readonly type: "text";
  readonly text: string;
}

export interface ImageBlock {
  readonly type: "image";
  readonly source: {
    readonly type: "base64";
    readonly media_type: string;
    readonly data: string;
  };
}

export interface ToolUseBlock {
  readonly type: "tool_use";
  readonly id: string;
  readonly name: string;
  readonly input: Record<string, unknown>;
}

export interface ToolResultBlock {
  readonly type: "tool_result";
  readonly tool_use_id: string;
  readonly content: string;
}

export interface Message {
  readonly role: "user" | "assistant";
  readonly content: readonly ContentBlock[];
}

export interface ToolDefinition {
  readonly name: string;
  readonly description: string;
  readonly input_schema: Record<string, unknown>;
}

export interface RequestBody {
  readonly model: string;
  readonly max_tokens: number;
  readonly messages: readonly Message[];
  readonly system?: string;
  readonly stop_sequences?: readonly string[];
  readonly temperature?: number;
  readonly top_p?: number;
  readonly top_k?: number;
  readonly tools?: readonly ToolDefinition[];
  readonly metadata?: Record<string, unknown>;
}

export interface UsageInfo {
  readonly input_tokens: number;
  readonly output_tokens: number;
}

export type StopReason = "end_turn" | "max_tokens" | "stop_sequence" | "tool_use";

export interface SuccessResponse {
  readonly id: string;
  readonly type: "message";
  readonly role: "assistant";
  readonly content: readonly ContentBlock[];
  readonly model: string;
  readonly stop_reason: StopReason;
  readonly stop_sequence: string | null;
  readonly usage: UsageInfo;
}

// ---------------------------------------------------------------------------
// Error types
// ---------------------------------------------------------------------------

export type AnthropicErrorType =
  | "invalid_request_error"
  | "authentication_error"
  | "permission_error"
  | "not_found_error"
  | "request_too_large"
  | "rate_limit_error"
  | "api_error"
  | "overloaded_error";

export class AnthropicError extends Error {
  public readonly statusCode: number;
  public readonly errorType: AnthropicErrorType | null;
  public readonly requestId: string | null;

  constructor(
    message: string,
    statusCode: number,
    errorType: AnthropicErrorType | null = null,
    requestId: string | null = null,
  ) {
    super(message);
    this.name = "AnthropicError";
    this.statusCode = statusCode;
    this.errorType = errorType;
    this.requestId = requestId;
  }

  /** Whether this error indicates a transient condition worth retrying. */
  get isRetryable(): boolean {
    return (
      RETRYABLE_STATUS_CODES.has(this.statusCode) ||
      (this.errorType !== null && RETRYABLE_ERROR_TYPES.has(this.errorType))
    );
  }

  static async fromResponse(response: Response): Promise<AnthropicError> {
    const statusCode = response.status;
    let errorType: AnthropicErrorType | null = null;
    let message = `HTTP ${statusCode}`;

    try {
      const body = (await response.json()) as Record<string, unknown>;
      const error = body["error"];
      if (error !== null && typeof error === "object") {
        const errObj = error as Record<string, unknown>;
        errorType = (errObj["type"] as AnthropicErrorType) ?? null;
        if (typeof errObj["message"] === "string") {
          message = errObj["message"];
        }
      }
    } catch {
      // Body is not valid JSON; keep the default message.
    }

    const requestId = response.headers.get("request-id");
    return new AnthropicError(message, statusCode, errorType, requestId);
  }
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function buildHeaders(
  apiKey: string,
  authMethod: AuthMethod,
  apiVersion: string,
): Record<string, string> {
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    "anthropic-version": apiVersion,
  };
  if (authMethod === AuthMethod.ApiKey) {
    headers["x-api-key"] = apiKey;
  } else {
    headers["Authorization"] = `Bearer ${apiKey}`;
  }
  return headers;
}

function buildBody(params: {
  messages: readonly Message[];
  model: string;
  maxTokens: number;
  system?: string;
  stopSequences?: readonly string[];
  temperature?: number;
  topP?: number;
  topK?: number;
  tools?: readonly ToolDefinition[];
  metadata?: Record<string, unknown>;
}): RequestBody {
  const body: Record<string, unknown> = {
    model: params.model,
    max_tokens: params.maxTokens,
    messages: params.messages,
  };
  if (params.system !== undefined) body["system"] = params.system;
  if (params.stopSequences !== undefined) body["stop_sequences"] = params.stopSequences;
  if (params.temperature !== undefined) body["temperature"] = params.temperature;
  if (params.topP !== undefined) body["top_p"] = params.topP;
  if (params.topK !== undefined) body["top_k"] = params.topK;
  if (params.tools !== undefined) body["tools"] = params.tools;
  if (params.metadata !== undefined) body["metadata"] = params.metadata;
  return body as unknown as RequestBody;
}

function computeRetryDelay(
  attempt: number,
  response?: Response,
  baseDelay: number = 1.0,
): number {
  if (response) {
    const retryAfter = response.headers.get("retry-after");
    if (retryAfter !== null) {
      const parsed = parseFloat(retryAfter);
      if (!isNaN(parsed)) return parsed;
    }
  }
  const delay = baseDelay * Math.pow(2, attempt - 1);
  // Add up to 25% deterministic jitter.
  const jitter = delay * 0.25 * ((attempt * 7 + 3) % 10) / 10;
  return delay + jitter;
}

function isRetryable(statusCode: number, errorType: string | null): boolean {
  if (RETRYABLE_STATUS_CODES.has(statusCode)) return true;
  if (errorType !== null && RETRYABLE_ERROR_TYPES.has(errorType)) return true;
  return false;
}

// ---------------------------------------------------------------------------
// KeyRotator
// ---------------------------------------------------------------------------

export class KeyRotator {
  private keys: string[];
  private failed: Set<string>;
  private index: number;

  constructor(keys: string[]) {
    if (keys.length === 0) {
      throw new Error("At least one API key is required");
    }
    this.keys = [...keys];
    this.failed = new Set();
    this.index = -1;
  }

  /** Return the next available key in round-robin order, skipping failed. */
  nextKey(): string {
    const available = this.keys.filter((k) => !this.failed.has(k));
    if (available.length === 0) {
      throw new AnthropicError(
        "All API keys have been marked as failed",
        0,
        null,
      );
    }
    this.index = (this.index + 1) % available.length;
    return available[this.index];
  }

  markFailed(key: string): void {
    this.failed.add(key);
  }

  addKey(key: string): void {
    if (!this.keys.includes(key)) {
      this.keys.push(key);
    }
  }

  removeKey(key: string): void {
    this.keys = this.keys.filter((k) => k !== key);
    this.failed.delete(key);
  }

  get activeCount(): number {
    return this.keys.length - this.failed.size;
  }
}

// ---------------------------------------------------------------------------
// AnthropicClient
// ---------------------------------------------------------------------------

export class AnthropicClient {
  private readonly config: ClientConfig;
  private readonly baseHeaders: Record<string, string>;
  private readonly keyRotator: KeyRotator | null;

  constructor(params: {
    config?: Partial<ClientConfig>;
    keys?: string[];
  }) {
    const apiKey =
      params.config?.apiKey ?? process.env["ANTHROPIC_API_KEY"] ?? "";
    this.config = {
      apiKey,
      authMethod: params.config?.authMethod ?? AuthMethod.ApiKey,
      baseUrl: params.config?.baseUrl ?? DEFAULT_BASE_URL,
      apiVersion: params.config?.apiVersion ?? DEFAULT_API_VERSION,
      timeoutMs: params.config?.timeoutMs ?? DEFAULT_TIMEOUT_MS,
    };

    if (!this.config.apiKey && !params.keys) {
      throw new Error(
        "apiKey must be provided via config or ANTHROPIC_API_KEY environment variable",
      );
    }

    this.baseHeaders = buildHeaders(
      this.config.apiKey,
      this.config.authMethod,
      this.config.apiVersion,
    );

    this.keyRotator = params.keys ? new KeyRotator(params.keys) : null;
  }

  /** Send a request to the Messages API. */
  async post(params: {
    messages: readonly Message[];
    model: string;
    maxTokens: number;
    system?: string;
    stopSequences?: readonly string[];
    temperature?: number;
    topP?: number;
    topK?: number;
    tools?: readonly ToolDefinition[];
    metadata?: Record<string, unknown>;
    maxRetries?: number;
  }): Promise<SuccessResponse> {
    const body = buildBody(params);
    const headers = this.resolveHeaders();
    const maxRetries = params.maxRetries ?? 0;

    return this.requestWithRetry(headers, body, maxRetries);
  }

  /** Convenience method with default retry count. */
  async postWithRetry(params: {
    messages: readonly Message[];
    model: string;
    maxTokens: number;
    system?: string;
    stopSequences?: readonly string[];
    temperature?: number;
    topP?: number;
    topK?: number;
    tools?: readonly ToolDefinition[];
    metadata?: Record<string, unknown>;
    maxRetries?: number;
  }): Promise<SuccessResponse> {
    return this.post({
      ...params,
      maxRetries: params.maxRetries ?? DEFAULT_MAX_RETRIES,
    });
  }

  private resolveHeaders(): Record<string, string> {
    if (this.keyRotator) {
      const key = this.keyRotator.nextKey();
      return buildHeaders(key, this.config.authMethod, this.config.apiVersion);
    }
    return { ...this.baseHeaders };
  }

  private handle401ForRotation(headers: Record<string, string>): void {
    if (!this.keyRotator) return;
    const key = headers["x-api-key"];
    if (key) {
      this.keyRotator.markFailed(key);
      return;
    }
    const auth = headers["Authorization"];
    if (auth?.startsWith("Bearer ")) {
      this.keyRotator.markFailed(auth.slice(7));
    }
  }

  private async requestWithRetry(
    headers: Record<string, string>,
    body: RequestBody,
    maxRetries: number,
  ): Promise<SuccessResponse> {
    let attempt = 0;

    while (true) {
      attempt++;
      const controller = new AbortController();
      const timeoutId = setTimeout(
        () => controller.abort(new DOMException("Timeout", "TimeoutError")),
        this.config.timeoutMs,
      );

      let response: Response;
      try {
        response = await fetch(this.config.baseUrl, {
          method: "POST",
          headers,
          body: JSON.stringify(body),
          signal: controller.signal,
        });
      } catch (err: unknown) {
        clearTimeout(timeoutId);
        if (attempt <= maxRetries) {
          await sleep(computeRetryDelay(attempt));
          continue;
        }
        throw new AnthropicError(
          `Request failed after ${attempt} attempts: ${String(err)}`,
          0,
          null,
        );
      } finally {
        clearTimeout(timeoutId);
      }

      if (response.ok) {
        return (await response.json()) as SuccessResponse;
      }

      const error = await AnthropicError.fromResponse(response);

      if (response.status === 401) {
        this.handle401ForRotation(headers);
        // Key rotation recovery: if another key is available,
        // retry with it. This is a change of auth context, not a blind retry.
        if (this.keyRotator && this.keyRotator.activeCount > 0) {
          headers = this.resolveHeaders();
          continue;
        }
      }

      const canRetry =
        attempt <= maxRetries &&
        isRetryable(response.status, error.errorType);

      if (canRetry) {
        const delay = computeRetryDelay(attempt, response);
        await sleep(delay);
        continue;
      }

      throw error;
    }
  }
}

// ---------------------------------------------------------------------------
// Internal helpers
// ---------------------------------------------------------------------------

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}
