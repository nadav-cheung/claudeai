/**
 * Tests for Chapter 1 Anthropic HTTP client (TypeScript).
 */

import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import {
  AnthropicClient,
  AnthropicError,
  AuthMethod,
  KeyRotator,
} from "./AnthropicClient";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function mockFetch(
  status: number,
  body: unknown,
  headers: Record<string, string> = {},
): void {
  const response = {
    ok: status >= 200 && status < 300,
    status,
    headers: new Headers(headers),
    json: async () => body as Record<string, unknown>,
  };
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  (globalThis as any).fetch = vi.fn().mockResolvedValue(response as Response);
}

function mockFetchSequence(
  ...responses: { status: number; body: unknown; headers?: Record<string, string> }[]
): void {
  let calls = 0;
  (globalThis as any).fetch = vi.fn().mockImplementation(() => {
    const r = responses[Math.min(calls, responses.length - 1)];
    calls++;
    return Promise.resolve({
      ok: r.status >= 200 && r.status < 300,
      status: r.status,
      headers: new Headers(r.headers ?? {}),
      json: async () => r.body as Record<string, unknown>,
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
    } as Response);
  });
}

const successBody = {
  id: "msg_01Xxxxxxxxxxxxx",
  type: "message",
  role: "assistant",
  content: [{ type: "text", text: "Hi there!" }],
  model: "claude-sonnet-4-20250514",
  stop_reason: "end_turn",
  stop_sequence: null,
  usage: { input_tokens: 5, output_tokens: 3 },
};

const sampleMessages = [
  {
    role: "user" as const,
    content: [{ type: "text" as const, text: "Hello" }],
  },
];

// ---------------------------------------------------------------------------
// KeyRotator
// ---------------------------------------------------------------------------

describe("KeyRotator", () => {
  it("round-robins through keys", () => {
    const kr = new KeyRotator(["key-a", "key-b", "key-c"]);
    const seen = new Set([kr.nextKey(), kr.nextKey(), kr.nextKey()]);
    expect(seen).toEqual(new Set(["key-a", "key-b", "key-c"]));
  });

  it("skips failed keys", () => {
    const kr = new KeyRotator(["key-a", "key-b"]);
    kr.markFailed("key-a");
    for (let i = 0; i < 5; i++) {
      expect(kr.nextKey()).toBe("key-b");
    }
  });

  it("throws when all keys are failed", () => {
    const kr = new KeyRotator(["key-a"]);
    kr.markFailed("key-a");
    expect(() => kr.nextKey()).toThrow("All API keys");
  });

  it("adds a new key", () => {
    const kr = new KeyRotator(["key-a"]);
    kr.addKey("key-b");
    const seen = new Set([kr.nextKey(), kr.nextKey()]);
    expect(seen).toEqual(new Set(["key-a", "key-b"]));
  });

  it("removes a key", () => {
    const kr = new KeyRotator(["key-a", "key-b"]);
    kr.removeKey("key-a");
    for (let i = 0; i < 5; i++) {
      expect(kr.nextKey()).toBe("key-b");
    }
  });

  it("rejects empty key arrays", () => {
    expect(() => new KeyRotator([])).toThrow("At least one");
  });

  it("reports active count correctly", () => {
    const kr = new KeyRotator(["a", "b", "c"]);
    expect(kr.activeCount).toBe(3);
    kr.markFailed("a");
    expect(kr.activeCount).toBe(2);
  });
});

// ---------------------------------------------------------------------------
// AnthropicError
// ---------------------------------------------------------------------------

describe("AnthropicError", () => {
  it("parses a valid error response body", async () => {
    mockFetch(401, {
      type: "error",
      error: { type: "authentication_error", message: "bad key" },
    });
    // We need to create a Response to parse.
    const resp = new Response(
      JSON.stringify({
        type: "error",
        error: { type: "authentication_error", message: "bad key" },
      }),
      { status: 401, headers: { "content-type": "application/json" } },
    );
    const err = await AnthropicError.fromResponse(resp);
    expect(err.statusCode).toBe(401);
    expect(err.errorType).toBe("authentication_error");
    expect(err.message).toContain("bad key");
  });

  it("handles non-JSON body gracefully", async () => {
    const resp = new Response("Internal Server Error", { status: 500 });
    const err = await AnthropicError.fromResponse(resp);
    expect(err.statusCode).toBe(500);
    expect(err.errorType).toBeNull();
  });

  it.each([
    [400, "invalid_request_error", false],
    [401, "authentication_error", false],
    [403, "permission_error", false],
    [404, "not_found_error", false],
    [413, "request_too_large", false],
    [429, "rate_limit_error", true],
    [500, "api_error", true],
    [529, "overloaded_error", true],
  ])(
    "status=%i type=%s => isRetryable=%s",
    (statusCode, errorType, expected) => {
      const err = new AnthropicError(
        "test",
        statusCode,
        errorType as AnthropicError["errorType"],
      );
      expect(err.isRetryable).toBe(expected);
    },
  );
});

// ---------------------------------------------------------------------------
// AnthropicClient
// ---------------------------------------------------------------------------

describe("AnthropicClient", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    // Ensure a default mock fetch in case a test doesn't set one up.
    (globalThis as any).fetch = vi.fn();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("makes a successful request", async () => {
    mockFetch(200, successBody);
    const client = new AnthropicClient({
      config: { apiKey: "sk-test" },
    });
    const result = await client.post({
      messages: sampleMessages,
      model: "claude-sonnet-4-20250514",
      maxTokens: 100,
    });
    expect(result.id).toBe("msg_01Xxxxxxxxxxxxx");
  });

  it("throws on 401 with no retry", async () => {
    mockFetch(401, {
      type: "error",
      error: { type: "authentication_error", message: "bad key" },
    });
    const client = new AnthropicClient({
      config: { apiKey: "sk-test" },
    });
    await expect(
      client.post({
        messages: sampleMessages,
        model: "claude-sonnet-4-20250514",
        maxTokens: 100,
        maxRetries: 2,
      }),
    ).rejects.toThrow(AnthropicError);
    // The single fetch call.
    expect((globalThis as any).fetch).toHaveBeenCalledTimes(1);
  });

  it("retries on 429 and succeeds", async () => {
    mockFetchSequence(
      {
        status: 429,
        body: {
          type: "error",
          error: { type: "rate_limit_error", message: "slow down" },
        },
        headers: { "retry-after": "0.01" },
      },
      { status: 200, body: successBody },
    );
    const client = new AnthropicClient({
      config: { apiKey: "sk-test" },
    });
    const result = await client.post({
      messages: sampleMessages,
      model: "claude-sonnet-4-20250514",
      maxTokens: 100,
      maxRetries: 3,
    });
    expect(result.id).toBe("msg_01Xxxxxxxxxxxxx");
    expect((globalThis as any).fetch).toHaveBeenCalledTimes(2);
  });

  it("retries on 500 and succeeds after two failures", async () => {
    mockFetchSequence(
      {
        status: 500,
        body: {
          type: "error",
          error: { type: "api_error", message: "boom" },
        },
      },
      {
        status: 500,
        body: {
          type: "error",
          error: { type: "api_error", message: "boom again" },
        },
      },
      { status: 200, body: successBody },
    );
    const client = new AnthropicClient({
      config: { apiKey: "sk-test" },
    });
    const result = await client.post({
      messages: sampleMessages,
      model: "claude-sonnet-4-20250514",
      maxTokens: 100,
      maxRetries: 3,
    });
    expect(result.id).toBe("msg_01Xxxxxxxxxxxxx");
    expect((globalThis as any).fetch).toHaveBeenCalledTimes(3);
  });

  it("throws after exhausting retries", async () => {
    mockFetchSequence(
      {
        status: 500,
        body: {
          type: "error",
          error: { type: "api_error", message: "boom" },
        },
      },
      {
        status: 500,
        body: {
          type: "error",
          error: { type: "api_error", message: "boom" },
        },
      },
      {
        status: 500,
        body: {
          type: "error",
          error: { type: "api_error", message: "boom" },
        },
      },
    );
    const client = new AnthropicClient({
      config: { apiKey: "sk-test" },
    });
    await expect(
      client.post({
        messages: sampleMessages,
        model: "claude-sonnet-4-20250514",
        maxTokens: 100,
        maxRetries: 2,
      }),
    ).rejects.toThrow(AnthropicError);
    // 1 initial + 2 retries = 3
    expect((globalThis as any).fetch).toHaveBeenCalledTimes(3);
  });

  it("does NOT retry on 400", async () => {
    mockFetch(400, {
      type: "error",
      error: { type: "invalid_request_error", message: "bad request" },
    });
    const client = new AnthropicClient({
      config: { apiKey: "sk-test" },
    });
    await expect(
      client.post({
        messages: sampleMessages,
        model: "claude-sonnet-4-20250514",
        maxTokens: 100,
        maxRetries: 3,
      }),
    ).rejects.toThrow(AnthropicError);
    expect((globalThis as any).fetch).toHaveBeenCalledTimes(1);
  });

  it("postWithRetry applies default retries", async () => {
    mockFetch(200, successBody);
    const client = new AnthropicClient({
      config: { apiKey: "sk-test" },
    });
    const result = await client.postWithRetry({
      messages: sampleMessages,
      model: "claude-sonnet-4-20250514",
      maxTokens: 100,
    });
    expect(result.id).toBe("msg_01Xxxxxxxxxxxxx");
  });

  it("marks failed key on 401 with key rotation", async () => {
    mockFetchSequence(
      {
        status: 401,
        body: {
          type: "error",
          error: { type: "authentication_error", message: "bad" },
        },
      },
      { status: 200, body: successBody },
    );
    const client = new AnthropicClient({
      config: { apiKey: "sk-fallback" },
      keys: ["key-bad", "key-good"],
    });
    const result = await client.post({
      messages: sampleMessages,
      model: "claude-sonnet-4-20250514",
      maxTokens: 100,
      maxRetries: 0,
    });
    expect(result.id).toBe("msg_01Xxxxxxxxxxxxx");
  });

  it("uses ANTHROPIC_API_KEY from environment", async () => {
    mockFetch(200, successBody);
    process.env["ANTHROPIC_API_KEY"] = "sk-from-env";
    const client = new AnthropicClient({}); // No explicit config.
    await client.post({
      messages: sampleMessages,
      model: "claude-sonnet-4-20250514",
      maxTokens: 100,
    });
    const fetchCalls = (globalThis as any).fetch.mock.calls as unknown[][];
    const reqHeaders = fetchCalls[0][1].headers as Record<string, string>;
    expect(reqHeaders["x-api-key"]).toBe("sk-from-env");
    delete process.env["ANTHROPIC_API_KEY"];
  });
});
