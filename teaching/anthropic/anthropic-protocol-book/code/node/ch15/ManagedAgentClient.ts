/**
 * Chapter 15: Managed Agent Client (TypeScript).
 *
 * A dependency-free HTTP client for Anthropic's Managed Agents API.
 * Uses Node.js 22+ native fetch. Strict TypeScript with zero `any` usage.
 *
 * Supports:
 * - Agent CRUD (create, retrieve, update, list, archive)
 * - Environment CRUD
 * - Session lifecycle (create, retrieve, list, delete, archive)
 * - Event sending and listing
 * - Session status polling and cancellation
 * - Memory Store attachment
 * - Outcome definition
 * - Dream creation and monitoring
 */

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const DEFAULT_BASE_URL = "https://api.anthropic.com";
const DEFAULT_API_VERSION = "2023-06-01";
const MANAGED_AGENTS_BETA = "managed-agents-2026-04-01";
const DREAMING_BETA = "dreaming-2026-04-21";
const DEFAULT_TIMEOUT_MS = 120_000;
const DEFAULT_POLL_INTERVAL_MS = 2_000;

// ---------------------------------------------------------------------------
// Errors
// ---------------------------------------------------------------------------

export class ManagedAgentError extends Error {
  readonly statusCode: number;
  readonly errorType: string | null;
  readonly requestId: string | null;

  constructor(
    message: string,
    statusCode: number,
    errorType: string | null = null,
    requestId: string | null = null,
  ) {
    super(message);
    this.name = "ManagedAgentError";
    this.statusCode = statusCode;
    this.errorType = errorType;
    this.requestId = requestId;
  }

  static async fromResponse(response: Response): Promise<ManagedAgentError> {
    const statusCode = response.status;
    let errorType: string | null = null;
    let message = `HTTP ${statusCode}`;

    try {
      const body = (await response.json()) as Record<string, unknown>;
      if (body.error && typeof body.error === "object") {
        const err = body.error as Record<string, unknown>;
        errorType = (err.type as string) ?? null;
        message = (err.message as string) ?? message;
      }
    } catch {
      // Non-JSON body — use default message
    }

    const requestId = response.headers.get("request-id");
    return new ManagedAgentError(message, statusCode, errorType, requestId);
  }
}

export class SessionTimeoutError extends ManagedAgentError {
  constructor(message: string) {
    super(message, 0, "session_timeout", null);
    this.name = "SessionTimeoutError";
  }
}

export class SessionFailedError extends ManagedAgentError {
  constructor(message: string) {
    super(message, 0, "session_failed", null);
    this.name = "SessionFailedError";
  }
}

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface ManagedAgentConfig {
  readonly apiKey: string;
  readonly baseUrl: string;
  readonly apiVersion: string;
  readonly timeoutMs: number;
  readonly pollIntervalMs: number;
}

export interface AgentConfig {
  readonly name: string;
  readonly model: string | { readonly id: string; readonly speed?: string };
  readonly system?: string;
  readonly tools?: readonly Record<string, unknown>[];
  readonly mcpServers?: readonly Record<string, unknown>[];
  readonly skills?: readonly Record<string, unknown>[];
  readonly multiagent?: Record<string, unknown>;
  readonly description?: string;
  readonly metadata?: Record<string, string>;
}

export interface EnvironmentConfig {
  readonly name: string;
  readonly config: {
    readonly type: "cloud";
    readonly networking?: { readonly type: "unrestricted" | "limited" };
    readonly packages?: Record<string, readonly string[]>;
  };
  readonly description?: string;
  readonly metadata?: Record<string, string>;
}

export interface SessionStatus {
  readonly id: string;
  readonly status: "created" | "running" | "idle" | "archived" | "deleted";
  readonly agentId?: string;
  readonly environmentId?: string;
  readonly createdAt?: string;
  readonly updatedAt?: string;
  readonly archivedAt?: string | null;
  readonly outcomeEvaluations?: readonly OutcomeEvaluation[];
  readonly [key: string]: unknown;
}

export interface SessionResult {
  readonly session: SessionStatus;
  readonly events: readonly Record<string, unknown>[];
}

export interface SessionSummary {
  readonly id: string;
  readonly status: string;
  readonly agentId?: string;
  readonly title?: string;
  readonly createdAt?: string;
  readonly [key: string]: unknown;
}

export interface OutcomeEvaluation {
  readonly outcomeId: string;
  readonly result: string;
  readonly explanation?: string;
  readonly iteration?: number;
}

export interface DreamStatus {
  readonly id: string;
  readonly status: "pending" | "running" | "completed" | "failed" | "canceled";
  readonly outputs?: readonly { readonly type: string; readonly memory_store_id: string }[];
  readonly usage?: {
    readonly input_tokens: number;
    readonly output_tokens: number;
    readonly cache_creation_input_tokens: number;
    readonly cache_read_input_tokens: number;
  };
  readonly error?: string | null;
  readonly [key: string]: unknown;
}

export interface MemoryConfig {
  readonly path: string;
  readonly content: string;
}

// ---------------------------------------------------------------------------
// Default configuration
// ---------------------------------------------------------------------------

export function createDefaultConfig(
  overrides: Partial<ManagedAgentConfig> = {},
): ManagedAgentConfig {
  const apiKey =
    overrides.apiKey ?? process.env["ANTHROPIC_API_KEY"] ?? "";
  if (!apiKey) {
    throw new Error(
      "apiKey must be provided or set via ANTHROPIC_API_KEY environment variable",
    );
  }
  return {
    apiKey,
    baseUrl: overrides.baseUrl ?? process.env["ANTHROPIC_BASE_URL"] ?? DEFAULT_BASE_URL,
    apiVersion: overrides.apiVersion ?? DEFAULT_API_VERSION,
    timeoutMs: overrides.timeoutMs ?? DEFAULT_TIMEOUT_MS,
    pollIntervalMs: overrides.pollIntervalMs ?? DEFAULT_POLL_INTERVAL_MS,
  };
}

// ---------------------------------------------------------------------------
// Client
// ---------------------------------------------------------------------------

export class ManagedAgentClient {
  private readonly config: ManagedAgentConfig;

  constructor(config: Partial<ManagedAgentConfig> = {}) {
    this.config = createDefaultConfig(config);
  }

  // ------------------------------------------------------------------
  // Internal helpers
  // ------------------------------------------------------------------

  private headers(extraBetas: string[] = []): HeadersInit {
    const betas = [MANAGED_AGENTS_BETA, ...extraBetas];
    return {
      "x-api-key": this.config.apiKey,
      "anthropic-version": this.config.apiVersion,
      "anthropic-beta": betas.join(","),
      "Content-Type": "application/json",
    };
  }

  private async fetchWithError<T>(
    path: string,
    init: RequestInit,
  ): Promise<T> {
    const url = `${this.config.baseUrl}${path}`;
    const response = await fetch(url, {
      ...init,
      signal: AbortSignal.timeout(this.config.timeoutMs),
    });

    if (!response.ok) {
      throw await ManagedAgentError.fromResponse(response);
    }

    // 204 No Content
    if (response.status === 204) {
      return undefined as unknown as T;
    }

    return (await response.json()) as T;
  }

  private async get<T>(
    path: string,
    extraBetas: string[] = [],
  ): Promise<T> {
    return this.fetchWithError<T>(path, {
      method: "GET",
      headers: this.headers(extraBetas),
    });
  }

  private async post<T>(
    path: string,
    body: Record<string, unknown>,
    extraBetas: string[] = [],
  ): Promise<T> {
    return this.fetchWithError<T>(path, {
      method: "POST",
      headers: this.headers(extraBetas),
      body: JSON.stringify(body),
    });
  }

  private async del(path: string): Promise<void> {
    const url = `${this.config.baseUrl}${path}`;
    const response = await fetch(url, {
      method: "DELETE",
      headers: this.headers(),
      signal: AbortSignal.timeout(this.config.timeoutMs),
    });
    if (!response.ok) {
      throw await ManagedAgentError.fromResponse(response);
    }
  }

  // ------------------------------------------------------------------
  // Agent operations
  // ------------------------------------------------------------------

  async createAgent(config: AgentConfig): Promise<string> {
    if (!config.name) {
      throw new Error("Missing required field: name");
    }
    if (!config.model) {
      throw new Error("Missing required field: model");
    }

    const body: Record<string, unknown> = {
      name: config.name,
      model:
        typeof config.model === "string"
          ? { id: config.model, speed: "standard" }
          : config.model,
    };

    if (config.system !== undefined) body["system"] = config.system;
    if (config.tools !== undefined) body["tools"] = config.tools;
    if (config.mcpServers !== undefined) body["mcp_servers"] = config.mcpServers;
    if (config.skills !== undefined) body["skills"] = config.skills;
    if (config.multiagent !== undefined) body["multiagent"] = config.multiagent;
    if (config.description !== undefined) body["description"] = config.description;
    if (config.metadata !== undefined) body["metadata"] = config.metadata;

    const resp = await this.post<{ id: string }>("/v1/agents", body);
    return resp.id;
  }

  async retrieveAgent(agentId: string): Promise<Record<string, unknown>> {
    return this.get<Record<string, unknown>>(`/v1/agents/${agentId}`);
  }

  async updateAgent(
    agentId: string,
    updates: Record<string, unknown>,
  ): Promise<Record<string, unknown>> {
    if (!("version" in updates)) {
      const current = await this.retrieveAgent(agentId);
      updates["version"] = current["version"];
    }
    return this.post<Record<string, unknown>>(`/v1/agents/${agentId}`, updates);
  }

  async listAgents(limit = 20): Promise<Record<string, unknown>[]> {
    const resp = await this.get<{ data: Record<string, unknown>[] }>(
      `/v1/agents?limit=${limit}`,
    );
    return resp.data;
  }

  async archiveAgent(agentId: string): Promise<Record<string, unknown>> {
    return this.post<Record<string, unknown>>(
      `/v1/agents/${agentId}/archive`,
      {},
    );
  }

  // ------------------------------------------------------------------
  // Environment operations
  // ------------------------------------------------------------------

  async createEnvironment(config: EnvironmentConfig): Promise<string> {
    if (!config.name) {
      throw new Error("Missing required field: name");
    }
    const resp = await this.post<{ id: string }>(
      "/v1/environments",
      config as unknown as Record<string, unknown>,
    );
    return resp.id;
  }

  async retrieveEnvironment(
    environmentId: string,
  ): Promise<Record<string, unknown>> {
    return this.get<Record<string, unknown>>(
      `/v1/environments/${environmentId}`,
    );
  }

  async listEnvironments(limit = 20): Promise<Record<string, unknown>[]> {
    const resp = await this.get<{ data: Record<string, unknown>[] }>(
      `/v1/environments?limit=${limit}`,
    );
    return resp.data;
  }

  async deleteEnvironment(environmentId: string): Promise<void> {
    await this.del(`/v1/environments/${environmentId}`);
  }

  // ------------------------------------------------------------------
  // Session operations
  // ------------------------------------------------------------------

  async startSession(
    agentId: string,
    task: string,
    options: {
      environmentId?: string;
      title?: string;
      resources?: readonly Record<string, unknown>[];
      vaultIds?: readonly string[];
    } = {},
  ): Promise<string> {
    let envId = options.environmentId;
    if (!envId) {
      const envs = await this.listEnvironments();
      if (envs.length === 0) {
        throw new Error(
          "No environment_id provided and no environments found. " +
            "Create one with createEnvironment() first.",
        );
      }
      // Use the most recently created environment
      envs.sort((a, b) => {
        const aDate = (a["created_at"] as string) ?? "";
        const bDate = (b["created_at"] as string) ?? "";
        return bDate.localeCompare(aDate);
      });
      envId = envs[0]?.["id"] as string;
    }

    const body: Record<string, unknown> = {
      agent: agentId,
      environment_id: envId,
    };
    if (options.title) body["title"] = options.title;
    if (options.resources) body["resources"] = options.resources;
    if (options.vaultIds) body["vault_ids"] = options.vaultIds;

    const resp = await this.post<{ id: string }>("/v1/sessions", body);
    const sessionId = resp.id;

    // Send the initial task message
    await this.sendEvent(sessionId, {
      type: "user.message",
      content: [{ type: "text", text: task }],
    });

    return sessionId;
  }

  private async sendEvent(
    sessionId: string,
    event: Record<string, unknown>,
  ): Promise<Record<string, unknown>> {
    return this.post<Record<string, unknown>>(
      `/v1/sessions/${sessionId}/events`,
      { events: [event] },
    );
  }

  async sendMessage(
    sessionId: string,
    text: string,
  ): Promise<Record<string, unknown>> {
    return this.sendEvent(sessionId, {
      type: "user.message",
      content: [{ type: "text", text }],
    });
  }

  async sendToolResult(
    sessionId: string,
    toolUseId: string,
    content: string,
    isError = false,
  ): Promise<Record<string, unknown>> {
    return this.sendEvent(sessionId, {
      type: "user.custom_tool_result",
      custom_tool_use_id: toolUseId,
      content: [{ type: "text", text: content }],
      is_error: isError,
    });
  }

  async defineOutcome(
    sessionId: string,
    description: string,
    rubric: string,
    maxIterations = 3,
  ): Promise<Record<string, unknown>> {
    return this.sendEvent(sessionId, {
      type: "user.define_outcome",
      description,
      rubric: { type: "text", content: rubric },
      max_iterations: maxIterations,
    });
  }

  // ------------------------------------------------------------------
  // Session status & polling
  // ------------------------------------------------------------------

  async getSessionStatus(sessionId: string): Promise<SessionStatus> {
    return this.get<SessionStatus>(`/v1/sessions/${sessionId}`);
  }

  async getSessionResult(sessionId: string): Promise<SessionResult> {
    const session = await this.getSessionStatus(sessionId);
    const events = await this.listEvents(sessionId);
    return { session, events };
  }

  async listEvents(
    sessionId: string,
    limit = 100,
  ): Promise<Record<string, unknown>[]> {
    const resp = await this.get<{ data: Record<string, unknown>[] }>(
      `/v1/sessions/${sessionId}/events?limit=${limit}`,
    );
    return resp.data;
  }

  async waitForCompletion(
    sessionId: string,
    maxWaitSeconds = 600,
  ): Promise<SessionStatus> {
    const started = Date.now();
    let interval = this.config.pollIntervalMs;

    while (true) {
      const status = await this.getSessionStatus(sessionId);
      const state = status.status;

      if (state === "idle" || state === "archived") {
        return status;
      }

      if (state === "failed" || state === "deleted") {
        throw new SessionFailedError(`Session ${sessionId} is in state: ${state}`);
      }

      const elapsed = (Date.now() - started) / 1000;
      if (elapsed >= maxWaitSeconds) {
        throw new SessionTimeoutError(
          `Session ${sessionId} did not complete within ${maxWaitSeconds}s`,
        );
      }

      // Exponential backoff: up to 30s
      await sleep(Math.min(interval, 30_000));
      interval *= 2;
    }
  }

  // ------------------------------------------------------------------
  // Session lifecycle
  // ------------------------------------------------------------------

  async cancelSession(sessionId: string): Promise<void> {
    await this.sendEvent(sessionId, { type: "user.interrupt" });
  }

  async archiveSession(sessionId: string): Promise<Record<string, unknown>> {
    return this.post<Record<string, unknown>>(
      `/v1/sessions/${sessionId}/archive`,
      {},
    );
  }

  async deleteSession(sessionId: string): Promise<void> {
    await this.del(`/v1/sessions/${sessionId}`);
  }

  async updateSession(
    sessionId: string,
    updates: Record<string, unknown>,
  ): Promise<Record<string, unknown>> {
    return this.post<Record<string, unknown>>(
      `/v1/sessions/${sessionId}`,
      updates,
    );
  }

  async listSessions(
    agentId?: string,
    limit = 20,
  ): Promise<SessionSummary[]> {
    const params = new URLSearchParams({ limit: String(limit) });
    if (agentId) params.set("agent_id", agentId);
    const resp = await this.get<{ data: SessionSummary[] }>(
      `/v1/sessions?${params.toString()}`,
    );
    return resp.data;
  }

  // ------------------------------------------------------------------
  // Memory Store operations
  // ------------------------------------------------------------------

  async createMemoryStore(name: string, description = ""): Promise<string> {
    const resp = await this.post<{ id: string }>("/v1/memory_stores", {
      name,
      description,
    });
    return resp.id;
  }

  async addMemory(
    storeId: string,
    path: string,
    content: string,
  ): Promise<Record<string, unknown>> {
    return this.post<Record<string, unknown>>(
      `/v1/memory_stores/${storeId}/memories`,
      { path, content },
    );
  }

  async listMemoryStores(limit = 20): Promise<Record<string, unknown>[]> {
    const resp = await this.get<{ data: Record<string, unknown>[] }>(
      `/v1/memory_stores?limit=${limit}`,
    );
    return resp.data;
  }

  // ------------------------------------------------------------------
  // Dream operations
  // ------------------------------------------------------------------

  async createDream(
    storeId: string,
    sessionIds: readonly string[],
    options: {
      model?: string;
      instructions?: string;
    } = {},
  ): Promise<string> {
    if (sessionIds.length === 0) {
      throw new Error("At least one session_id is required");
    }
    if (sessionIds.length > 100) {
      throw new Error("Maximum 100 sessions per dream");
    }

    const resp = await this.post<{ id: string }>(
      "/v1/dreams",
      {
        inputs: [
          { type: "memory_store", memory_store_id: storeId },
          { type: "sessions", session_ids: sessionIds },
        ],
        model: options.model ?? "claude-sonnet-4-6",
        instructions: options.instructions ?? "",
      },
      [DREAMING_BETA],
    );
    return resp.id;
  }

  async getDreamStatus(dreamId: string): Promise<DreamStatus> {
    return this.get<DreamStatus>(`/v1/dreams/${dreamId}`, [DREAMING_BETA]);
  }

  async waitForDream(
    dreamId: string,
    maxWaitSeconds = 600,
  ): Promise<DreamStatus> {
    const started = Date.now();
    let interval = this.config.pollIntervalMs;

    while (true) {
      const dream = await this.getDreamStatus(dreamId);

      if (
        dream.status === "completed" ||
        dream.status === "failed" ||
        dream.status === "canceled"
      ) {
        return dream;
      }

      const elapsed = (Date.now() - started) / 1000;
      if (elapsed >= maxWaitSeconds) {
        throw new SessionTimeoutError(
          `Dream ${dreamId} did not complete within ${maxWaitSeconds}s`,
        );
      }

      await sleep(Math.min(interval, 30_000));
      interval *= 2;
    }
  }

  async cancelDream(dreamId: string): Promise<Record<string, unknown>> {
    return this.post<Record<string, unknown>>(
      `/v1/dreams/${dreamId}/cancel`,
      {},
      [DREAMING_BETA],
    );
  }
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}
