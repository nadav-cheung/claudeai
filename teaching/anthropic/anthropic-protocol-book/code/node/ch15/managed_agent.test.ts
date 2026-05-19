/**
 * Tests for Chapter 15 Managed Agent Client (TypeScript).
 *
 * Uses vitest with mocked fetch to avoid real network calls.
 */

import { describe, it, expect, beforeEach, vi } from "vitest";
import {
  ManagedAgentClient,
  ManagedAgentError,
  SessionTimeoutError,
  SessionFailedError,
  type AgentConfig,
  type EnvironmentConfig,
  type SessionStatus,
} from "./ManagedAgentClient";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function makeResponse(
  status: number,
  body: unknown,
  headers: Record<string, string> = {},
): Response {
  return {
    ok: status >= 200 && status < 300,
    status,
    headers: new Headers(headers),
    json: async () => body,
    text: async () => JSON.stringify(body),
    arrayBuffer: async () => new ArrayBuffer(0),
    blob: async () => new Blob(),
    formData: async () => new FormData(),
    clone: function () {
      return this;
    },
    body: null,
    bodyUsed: false,
    redirected: false,
    type: "basic" as ResponseType,
    url: "",
  } as Response;
}

function mockFetch(
  handler: (url: string, init: RequestInit) => Response | Promise<Response>,
): void {
  vi.spyOn(globalThis, "fetch").mockImplementation(
    (input: unknown, init?: RequestInit) => {
      const url = typeof input === "string" ? input : (input as URL).toString();
      const result = handler(url, init ?? {});
      return Promise.resolve(result);
    },
  );
}

// Agent fixtures
const agentResponse = {
  id: "agent_01HqR2k7vXbZ9mNpL3wYcT8f",
  type: "agent",
  name: "Test Agent",
  model: { id: "claude-sonnet-4-6", speed: "standard" },
  version: 1,
  created_at: "2026-04-03T18:24:10.412Z",
  archived_at: null,
};

const envResponse = {
  id: "env_01XyZAbCdEfGhIjKlMnOpQrSt",
  type: "environment",
  name: "Test Env",
  created_at: "2026-04-03T18:00:00.000Z",
};

function createClient(): ManagedAgentClient {
  return new ManagedAgentClient({ apiKey: "test-key-001" });
}

// ---------------------------------------------------------------------------
// Agent operations
// ---------------------------------------------------------------------------

describe("Agent operations", () => {
  it("should create an agent with required fields", async () => {
    const client = createClient();
    mockFetch((url, init) => {
      if (url.endsWith("/v1/agents") && init.method === "POST") {
        return makeResponse(200, agentResponse);
      }
      return makeResponse(404, { error: { message: "Not found" } });
    });

    const id = await client.createAgent({
      name: "Test Agent",
      model: "claude-sonnet-4-6",
      system: "You are a test agent.",
    });
    expect(id).toBe("agent_01HqR2k7vXbZ9mNpL3wYcT8f");
  });

  it("should throw if name is missing", async () => {
    const client = createClient();
    await expect(
      client.createAgent({ name: "", model: "claude-sonnet-4-6" }),
    ).rejects.toThrow("Missing required field: name");
  });

  it("should normalize model string to object", async () => {
    const client = createClient();
    let capturedBody: Record<string, unknown> | undefined;

    mockFetch((url, init) => {
      if (url.endsWith("/v1/agents") && init.method === "POST") {
        capturedBody = JSON.parse((init.body as string) ?? "{}") as Record<string, unknown>;
        return makeResponse(200, agentResponse);
      }
      return makeResponse(404, {});
    });

    await client.createAgent({
      name: "Test Agent",
      model: "claude-opus-4-7",
    });
    expect(capturedBody).toBeDefined();
    expect((capturedBody!["model"] as Record<string, unknown>).id).toBe("claude-opus-4-7");
  });

  it("should retrieve an agent", async () => {
    const client = createClient();
    mockFetch(() => makeResponse(200, agentResponse));

    const agent = await client.retrieveAgent("agent_01Hq");
    expect(agent["name"]).toBe("Test Agent");
  });

  it("should list agents", async () => {
    const client = createClient();
    mockFetch((url) => {
      if (url.includes("/v1/agents?")) {
        return makeResponse(200, { data: [agentResponse] });
      }
      return makeResponse(404, {});
    });

    const agents = await client.listAgents();
    expect(agents).toHaveLength(1);
    expect(agents[0]?.["name"]).toBe("Test Agent");
  });

  it("should archive an agent", async () => {
    const client = createClient();
    const archived = { ...agentResponse, archived_at: "2026-04-03T19:00:00Z" };
    mockFetch(() => makeResponse(200, archived));

    const result = await client.archiveAgent("agent_01Hq");
    expect(result["archived_at"]).not.toBeNull();
  });
});

// ---------------------------------------------------------------------------
// Environment operations
// ---------------------------------------------------------------------------

describe("Environment operations", () => {
  it("should create an environment", async () => {
    const client = createClient();
    mockFetch((url, init) => {
      if (url.endsWith("/v1/environments") && init.method === "POST") {
        return makeResponse(200, envResponse);
      }
      return makeResponse(404, {});
    });

    const config: EnvironmentConfig = {
      name: "Test Env",
      config: {
        type: "cloud",
        networking: { type: "unrestricted" },
      },
    };
    const id = await client.createEnvironment(config);
    expect(id).toBe("env_01XyZAbCdEfGhIjKlMnOpQrSt");
  });

  it("should throw if name is missing", async () => {
    const client = createClient();
    await expect(
      client.createEnvironment({
        name: "",
        config: { type: "cloud" },
      }),
    ).rejects.toThrow("Missing required field: name");
  });

  it("should list environments", async () => {
    const client = createClient();
    mockFetch((url) => {
      if (url.includes("/v1/environments?")) {
        return makeResponse(200, { data: [envResponse] });
      }
      return makeResponse(404, {});
    });

    const envs = await client.listEnvironments();
    expect(envs).toHaveLength(1);
  });

  it("should delete an environment", async () => {
    const client = createClient();
    mockFetch(() => makeResponse(204, null));

    await expect(
      client.deleteEnvironment("env_test"),
    ).resolves.toBeUndefined();
  });
});

// ---------------------------------------------------------------------------
// Session operations
// ---------------------------------------------------------------------------

describe("Session operations", () => {
  it("should start a session with explicit environment", async () => {
    const client = createClient();
    const sessionResponse = {
      id: "sesn_01AbCdEf",
      type: "session",
      status: "created",
    };
    const eventResponse = { id: "evt_01", type: "user.message" };

    mockFetch((url, init) => {
      if (url.endsWith("/v1/sessions") && init.method === "POST") {
        return makeResponse(200, sessionResponse);
      }
      if (url.includes("/events") && init.method === "POST") {
        return makeResponse(200, eventResponse);
      }
      return makeResponse(404, {});
    });

    const sessionId = await client.startSession("agent_123", "Hello", {
      environmentId: "env_test",
    });
    expect(sessionId).toBe("sesn_01AbCdEf");
  });

  it("should auto-discover environment when none provided", async () => {
    const client = createClient();
    mockFetch((url, init) => {
      if (url.includes("/v1/environments?")) {
        return makeResponse(200, {
          data: [
            { id: "env_old", created_at: "2026-04-01T00:00:00Z" },
            { id: "env_new", created_at: "2026-04-03T00:00:00Z" },
          ],
        });
      }
      if (url.endsWith("/v1/sessions") && init.method === "POST") {
        // Verify env_new was used (latest)
        const body = JSON.parse((init.body as string) ?? "{}") as Record<string, unknown>;
        expect(body["environment_id"]).toBe("env_new");
        return makeResponse(200, { id: "sesn_ok", status: "created" });
      }
      if (url.includes("/events") && init.method === "POST") {
        return makeResponse(200, { id: "evt_01" });
      }
      return makeResponse(404, {});
    });

    const sessionId = await client.startSession("agent_123", "Task");
    expect(sessionId).toBe("sesn_ok");
  });

  it("should get session status", async () => {
    const client = createClient();
    const statusBody: SessionStatus = {
      id: "sesn_test",
      status: "running",
    };
    mockFetch(() => makeResponse(200, statusBody));

    const status = await client.getSessionStatus("sesn_test");
    expect(status.status).toBe("running");
  });

  it("should get session result", async () => {
    const client = createClient();
    mockFetch((url) => {
      if (url.includes("/events")) {
        return makeResponse(200, {
          data: [{ type: "user.message", content: [{ type: "text", text: "Hi" }] }],
        });
      }
      return makeResponse(200, { id: "sesn_test", status: "idle" });
    });

    const result = await client.getSessionResult("sesn_test");
    expect(result.session.status).toBe("idle");
    expect(result.events).toHaveLength(1);
  });

  it("should send follow-up message", async () => {
    const client = createClient();
    mockFetch(() =>
      makeResponse(200, {
        id: "evt_02",
        type: "user.message",
        content: [{ type: "text", text: "Follow-up" }],
      }),
    );

    const resp = await client.sendMessage("sesn_test", "Follow-up");
    expect(resp["type"]).toBe("user.message");
  });

  it("should send tool result", async () => {
    const client = createClient();
    mockFetch(() =>
      makeResponse(200, { id: "evt_03", type: "user.custom_tool_result" }),
    );

    const resp = await client.sendToolResult(
      "sesn_test",
      "sevt_abc",
      "Result data",
      false,
    );
    expect(resp["type"]).toBe("user.custom_tool_result");
  });

  it("should define outcome", async () => {
    const client = createClient();
    mockFetch(() =>
      makeResponse(200, { id: "evt_outcome", type: "user.define_outcome" }),
    );

    const rubric = "# Test Rubric\n- Criterion 1\n- Criterion 2";
    const resp = await client.defineOutcome(
      "sesn_test",
      "Task description",
      rubric,
      3,
    );
    expect(resp["type"]).toBe("user.define_outcome");
  });

  it("should list sessions with agent filter", async () => {
    const client = createClient();
    mockFetch((url) => {
      if (url.includes("agent_id=agent_123")) {
        return makeResponse(200, {
          data: [
            { id: "sesn_1", agentId: "agent_123", status: "idle" },
            { id: "sesn_2", agentId: "agent_123", status: "archived" },
          ],
        });
      }
      return makeResponse(404, {});
    });

    const sessions = await client.listSessions("agent_123");
    expect(sessions).toHaveLength(2);
  });
});

// ---------------------------------------------------------------------------
// Wait / poll
// ---------------------------------------------------------------------------

describe("Wait for completion", () => {
  it("should return immediately when session is idle", async () => {
    const client = new ManagedAgentClient({
      apiKey: "test-key",
      pollIntervalMs: 10,
    });
    mockFetch(() =>
      makeResponse(200, { id: "sesn_test", status: "idle" }),
    );

    const result = await client.waitForCompletion("sesn_test");
    expect(result.status).toBe("idle");
  });

  it("should poll until idle", async () => {
    const client = new ManagedAgentClient({
      apiKey: "test-key",
      pollIntervalMs: 5,
    });

    let calls = 0;
    mockFetch(() => {
      calls++;
      if (calls < 3) {
        return makeResponse(200, { id: "sesn_test", status: "running" });
      }
      return makeResponse(200, { id: "sesn_test", status: "idle" });
    });

    const result = await client.waitForCompletion("sesn_test", 10);
    expect(result.status).toBe("idle");
    expect(calls).toBeGreaterThanOrEqual(3);
  });

  it("should throw on timeout", async () => {
    const client = new ManagedAgentClient({
      apiKey: "test-key",
      pollIntervalMs: 2,
    });
    mockFetch(() =>
      makeResponse(200, { id: "sesn_test", status: "running" }),
    );

    await expect(
      client.waitForCompletion("sesn_test", 0.01),
    ).rejects.toThrow(SessionTimeoutError);
  });

  it("should throw on failed session", async () => {
    const client = new ManagedAgentClient({
      apiKey: "test-key",
      pollIntervalMs: 5,
    });
    mockFetch(() =>
      makeResponse(200, { id: "sesn_test", status: "failed" }),
    );

    await expect(
      client.waitForCompletion("sesn_test", 5),
    ).rejects.toThrow(SessionFailedError);
  });
});

// ---------------------------------------------------------------------------
// Session lifecycle
// ---------------------------------------------------------------------------

describe("Session lifecycle", () => {
  it("should cancel a session", async () => {
    const client = createClient();
    mockFetch(() =>
      makeResponse(200, { id: "evt_int", type: "user.interrupt" }),
    );
    await expect(
      client.cancelSession("sesn_test"),
    ).resolves.toBeUndefined();
  });

  it("should delete a session", async () => {
    const client = createClient();
    mockFetch(() => makeResponse(204, null));
    await expect(
      client.deleteSession("sesn_test"),
    ).resolves.toBeUndefined();
  });

  it("should archive a session", async () => {
    const client = createClient();
    mockFetch(() =>
      makeResponse(200, {
        id: "sesn_test",
        archived_at: "2026-04-03T20:00:00Z",
      }),
    );
    const result = await client.archiveSession("sesn_test");
    expect(result["archived_at"]).not.toBeNull();
  });

  it("should update a session", async () => {
    const client = createClient();
    mockFetch(() =>
      makeResponse(200, { id: "sesn_test", title: "New Title" }),
    );
    const result = await client.updateSession("sesn_test", {
      title: "New Title",
    });
    expect(result["title"]).toBe("New Title");
  });
});

// ---------------------------------------------------------------------------
// Memory Store operations
// ---------------------------------------------------------------------------

describe("Memory Store operations", () => {
  it("should create a memory store", async () => {
    const client = createClient();
    mockFetch(() =>
      makeResponse(200, {
        id: "memstore_01HxAbCdEf",
        name: "Test Store",
      }),
    );
    const id = await client.createMemoryStore("Test Store", "Desc");
    expect(id).toMatch(/^memstore_/);
  });

  it("should add a memory", async () => {
    const client = createClient();
    mockFetch(() =>
      makeResponse(200, {
        id: "mem_01AbCdEfGh",
        path: "/preferences/test.md",
        content: "Test content",
      }),
    );
    const mem = await client.addMemory(
      "memstore_01",
      "/preferences/test.md",
      "Test content",
    );
    expect(mem["path"]).toBe("/preferences/test.md");
  });

  it("should list memory stores", async () => {
    const client = createClient();
    mockFetch((url) => {
      if (url.includes("/v1/memory_stores?")) {
        return makeResponse(200, {
          data: [
            { id: "memstore_01", name: "S1" },
            { id: "memstore_02", name: "S2" },
          ],
        });
      }
      return makeResponse(404, {});
    });

    const stores = await client.listMemoryStores();
    expect(stores).toHaveLength(2);
  });
});

// ---------------------------------------------------------------------------
// Dream operations
// ---------------------------------------------------------------------------

describe("Dream operations", () => {
  it("should throw when no sessions provided", async () => {
    const client = createClient();
    await expect(client.createDream("memstore_01", [])).rejects.toThrow(
      "At least one session_id",
    );
  });

  it("should throw when too many sessions", async () => {
    const client = createClient();
    const manySessions = Array.from({ length: 101 }, (_, i) => `sesn_${i}`);
    await expect(
      client.createDream("memstore_01", manySessions),
    ).rejects.toThrow("Maximum 100 sessions");
  });

  it("should create a dream", async () => {
    const client = createClient();
    mockFetch(() =>
      makeResponse(200, {
        id: "drm_01AbCDefGhIjKlMnOpQrStUv",
        type: "dream",
        status: "pending",
      }),
    );

    const dreamId = await client.createDream("memstore_01", [
      "sesn_1",
      "sesn_2",
    ]);
    expect(dreamId).toMatch(/^drm_/);
  });

  it("should get dream status", async () => {
    const client = createClient();
    mockFetch(() =>
      makeResponse(200, {
        id: "drm_01",
        status: "running",
        usage: { input_tokens: 1000, output_tokens: 200 },
      }),
    );

    const status = await client.getDreamStatus("drm_01");
    expect(status.status).toBe("running");
  });

  it("should wait for dream completion", async () => {
    const client = new ManagedAgentClient({
      apiKey: "test-key",
      pollIntervalMs: 5,
    });
    mockFetch(() =>
      makeResponse(200, {
        id: "drm_01",
        status: "completed",
        outputs: [
          { type: "memory_store", memory_store_id: "memstore_new" },
        ],
      }),
    );

    const result = await client.waitForDream("drm_01");
    expect(result.status).toBe("completed");
  });

  it("should cancel a dream", async () => {
    const client = createClient();
    mockFetch(() =>
      makeResponse(200, { id: "drm_01", status: "canceled" }),
    );
    const result = await client.cancelDream("drm_01");
    expect(result["status"]).toBe("canceled");
  });
});

// ---------------------------------------------------------------------------
// Error handling
// ---------------------------------------------------------------------------

describe("Error handling", () => {
  it("should parse rate limit error from response", async () => {
    const resp = makeResponse(
      429,
      {
        type: "error",
        error: {
          type: "rate_limit_error",
          message: "Rate limit exceeded",
        },
      },
      { "request-id": "req_abc123" },
    );

    const error = await ManagedAgentError.fromResponse(resp);
    expect(error.statusCode).toBe(429);
    expect(error.errorType).toBe("rate_limit_error");
    expect(error.requestId).toBe("req_abc123");
  });

  it("should handle non-JSON error responses", async () => {
    const resp: Response = {
      ok: false,
      status: 500,
      headers: new Headers(),
      json: async () => {
        throw new Error("not json");
      },
      text: async () => "Internal Server Error",
      arrayBuffer: async () => new ArrayBuffer(0),
      blob: async () => new Blob(),
      formData: async () => new FormData(),
      body: null,
      bodyUsed: false,
      redirected: false,
      type: "basic" as ResponseType,
      url: "",
      clone: function () {
        return this;
      },
    } as Response;

    const error = await ManagedAgentError.fromResponse(resp);
    expect(error.statusCode).toBe(500);
    expect(error.errorType).toBeNull();
  });

  it("should propagate 401 errors properly", async () => {
    const client = createClient();
    mockFetch(() =>
      makeResponse(401, {
        type: "error",
        error: {
          type: "authentication_error",
          message: "Invalid API key",
        },
      }),
    );

    await expect(
      client.retrieveAgent("agent_nonexistent"),
    ).rejects.toThrow(ManagedAgentError);
  });
});

// ---------------------------------------------------------------------------
// Configuration
// ---------------------------------------------------------------------------

describe("Configuration", () => {
  it("should use defaults when only apiKey provided", () => {
    const client = new ManagedAgentClient({ apiKey: "test-key" });
    // If construction succeeds, defaults were applied
    expect(client).toBeDefined();
  });

  it("should throw without apiKey", () => {
    const oldKey = process.env["ANTHROPIC_API_KEY"];
    delete process.env["ANTHROPIC_API_KEY"];
    try {
      expect(() => new ManagedAgentClient()).toThrow("apiKey");
    } finally {
      if (oldKey) process.env["ANTHROPIC_API_KEY"] = oldKey;
    }
  });
});
