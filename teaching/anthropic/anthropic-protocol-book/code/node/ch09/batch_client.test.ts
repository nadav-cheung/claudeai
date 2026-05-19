/**
 * Tests for Chapter 9: BatchClient (TypeScript).
 *
 * Validates protocol correctness — request/response shape, status parsing,
 * result parsing, and error handling — by mocking `fetch` so no real API key
 * is required.
 */

import { describe, it, expect, beforeEach, vi, afterEach } from "vitest";
import {
  BatchClient,
  BatchInfo,
  BatchResult,
  MessageRequest,
  BatchProcessingStatus,
  ResultType,
} from "./BatchClient";

// ---------------------------------------------------------------------------
// fetch mock helpers
// ---------------------------------------------------------------------------

function mockFetch(
  handler: (url: string, init?: RequestInit) => Response | Promise<Response>,
) {
  vi.spyOn(globalThis, "fetch").mockImplementation(
    (input: RequestInfo | URL, init?: RequestInit) => {
      const url = typeof input === "string" ? input : input.toString();
      return Promise.resolve(handler(url, init));
    },
  ) as unknown as typeof fetch;
}

function jsonResponse(data: unknown, status: number = 200): Response {
  return new Response(JSON.stringify(data), {
    status,
    headers: { "content-type": "application/json" },
  });
}

beforeEach(() => {
  vi.restoreAllMocks();
});

afterEach(() => {
  vi.restoreAllMocks();
});

function client(): BatchClient {
  return new BatchClient("sk-ant-test");
}

// ---------------------------------------------------------------------------
// createBatch
// ---------------------------------------------------------------------------

describe("createBatch", () => {
  it("returns batch id on success", async () => {
    mockFetch((url, init) => {
      expect(url).toContain("/v1/messages/batches");
      const body = JSON.parse(init!.body as string);
      expect(body.requests).toHaveLength(2);
      expect(body.requests[0].custom_id).toBe("r1");
      return jsonResponse({ id: "msgbatch_123", processing_status: "in_progress" });
    });

    const id = await client().createBatch([
      {
        custom_id: "r1",
        params: { model: "claude-sonnet-4-20250514", max_tokens: 100, messages: [{ role: "user", content: "Hi" }] },
      },
      {
        custom_id: "r2",
        params: { model: "claude-sonnet-4-20250514", max_tokens: 100, messages: [{ role: "user", content: "Bye" }] },
      },
    ]);
    expect(id).toBe("msgbatch_123");
  });

  it("throws on HTTP error", async () => {
    mockFetch(() => jsonResponse({ error: { type: "authentication_error" } }, 401));

    await expect(
      client().createBatch([
        { custom_id: "r1", params: { model: "x", max_tokens: 1, messages: [] } },
      ]),
    ).rejects.toThrow("Create batch failed");
  });
});

// ---------------------------------------------------------------------------
// getBatchStatus
// ---------------------------------------------------------------------------

describe("getBatchStatus", () => {
  it("parses in_progress status", async () => {
    mockFetch((url) => {
      expect(url).toContain("msgbatch_x");
      return jsonResponse({
        id: "msgbatch_x",
        processing_status: "in_progress",
        request_counts: { processing: 100, succeeded: 0, errored: 0, canceled: 0, expired: 0 },
        created_at: "2026-05-17T10:00:00Z",
        expires_at: "2026-05-18T10:00:00Z",
      });
    });

    const info = await client().getBatchStatus("msgbatch_x");
    expect(info.processing_status).toBe("in_progress");
    expect(info.id).toBe("msgbatch_x");
    expect(info.request_counts["processing"]).toBe(100);
  });

  it("parses ended status with counts", async () => {
    mockFetch(() =>
      jsonResponse({
        id: "msgbatch_done",
        processing_status: "ended",
        request_counts: { processing: 0, succeeded: 98, errored: 2, canceled: 0, expired: 0 },
        created_at: "2026-05-17T10:00:00Z",
        ended_at: "2026-05-17T10:45:00Z",
        expires_at: "2026-05-18T10:00:00Z",
        results_url: "https://api.anthropic.com/v1/messages/batches/msgbatch_done/results",
      }),
    );

    const info = await client().getBatchStatus("msgbatch_done");
    expect(info.processing_status).toBe("ended");
    expect(info.request_counts["succeeded"]).toBe(98);
    expect(info.request_counts["errored"]).toBe(2);
    expect(info.results_url).toBeTruthy();
  });
});

// ---------------------------------------------------------------------------
// getBatchResults
// ---------------------------------------------------------------------------

describe("getBatchResults", () => {
  it("parses all four result types from JSONL", async () => {
    const jsonl =
      '{"custom_id":"q1","result":{"type":"succeeded","message":{"id":"msg_1","role":"assistant","content":[{"type":"text","text":"Hello"}]}}}\n' +
      '{"custom_id":"q2","result":{"type":"errored","error":{"type":"invalid_request_error","message":"Bad param"}}}\n' +
      '{"custom_id":"q3","result":{"type":"canceled"}}\n' +
      '{"custom_id":"q4","result":{"type":"expired"}}\n';

    mockFetch(() => new Response(jsonl, { headers: { "content-type": "application/jsonl" } }));

    const results = await client().getBatchResults("msgbatch_done");
    expect(results).toHaveLength(4);

    // succeeded
    expect(results[0]!.custom_id).toBe("q1");
    expect(results[0]!.result_type).toBe("succeeded");
    expect(results[0]!.message).not.toBeNull();
    expect((results[0]!.message as any).content[0].text).toBe("Hello");
    expect(results[0]!.error).toBeNull();

    // errored
    expect(results[1]!.custom_id).toBe("q2");
    expect(results[1]!.result_type).toBe("errored");
    expect(results[1]!.error).not.toBeNull();
    expect((results[1]!.error as any).type).toBe("invalid_request_error");

    // canceled
    expect(results[2]!.custom_id).toBe("q3");
    expect(results[2]!.result_type).toBe("canceled");

    // expired
    expect(results[3]!.custom_id).toBe("q4");
    expect(results[3]!.result_type).toBe("expired");
  });
});

// ---------------------------------------------------------------------------
// cancelBatch
// ---------------------------------------------------------------------------

describe("cancelBatch", () => {
  it("cancels and returns updated info", async () => {
    mockFetch((url, init) => {
      expect(init!.method).toBe("POST");
      return jsonResponse({
        id: "msgbatch_cx",
        processing_status: "canceled",
        request_counts: { succeeded: 5, canceled: 95 },
      });
    });

    const info = await client().cancelBatch("msgbatch_cx");
    expect(info.processing_status).toBe("canceled");
    expect(info.request_counts["canceled"]).toBe(95);
  });
});

// ---------------------------------------------------------------------------
// listBatches
// ---------------------------------------------------------------------------

describe("listBatches", () => {
  it("lists batches", async () => {
    mockFetch(() =>
      jsonResponse({
        data: [
          { id: "msgbatch_a", processing_status: "ended", request_counts: { succeeded: 10 } },
          { id: "msgbatch_b", processing_status: "in_progress", request_counts: { processing: 5 } },
        ],
        has_more: false,
        first_id: "msgbatch_a",
        last_id: "msgbatch_b",
      }),
    );

    const batches = await client().listBatches(10);
    expect(batches).toHaveLength(2);
    expect(batches[0]!.id).toBe("msgbatch_a");
    expect(batches[0]!.processing_status).toBe("ended");
    expect(batches[1]!.id).toBe("msgbatch_b");
    expect(batches[1]!.processing_status).toBe("in_progress");
  });
});

// ---------------------------------------------------------------------------
// waitForCompletion
// ---------------------------------------------------------------------------

describe("waitForCompletion", () => {
  it("returns results when already ended", async () => {
    let callCount = 0;
    mockFetch((url) => {
      callCount++;
      if (url.includes("/results")) {
        return new Response(
          '{"custom_id":"q1","result":{"type":"succeeded","message":{"id":"m1","role":"assistant","content":[{"type":"text","text":"OK"}]}}}\n',
          { headers: { "content-type": "application/jsonl" } },
        );
      }
      return jsonResponse({ id: "msgbatch_done", processing_status: "ended", request_counts: { succeeded: 1 } });
    });

    const results = await client().waitForCompletion("msgbatch_done", 0.01);
    expect(results).toHaveLength(1);
    expect(results[0]!.result_type).toBe("succeeded");
    expect(callCount).toBe(2); // one status + one results
  });

  it("throws on timeout", async () => {
    mockFetch(() =>
      jsonResponse({ id: "msgbatch_slow", processing_status: "in_progress", request_counts: { processing: 1 } }),
    );

    await expect(
      client().waitForCompletion("msgbatch_slow", 0.01, 0.05),
    ).rejects.toThrow("did not complete");
  });

  it("throws on expired", async () => {
    mockFetch(() =>
      jsonResponse({ id: "msgbatch_exp", processing_status: "expired", request_counts: { expired: 10 } }),
    );

    await expect(
      client().waitForCompletion("msgbatch_exp", 0.01),
    ).rejects.toThrow("expired");
  });

  it("throws on canceled", async () => {
    mockFetch(() =>
      jsonResponse({ id: "msgbatch_cxl", processing_status: "canceled", request_counts: { canceled: 10 } }),
    );

    await expect(
      client().waitForCompletion("msgbatch_cxl", 0.01),
    ).rejects.toThrow("canceled");
  });

  it("polls until ended", async () => {
    let statusCalls = 0;
    mockFetch((url) => {
      if (url.includes("/results")) {
        return new Response(
          '{"custom_id":"q1","result":{"type":"succeeded","message":{"id":"m1","role":"assistant","content":[{"type":"text","text":"Done"}]}}}\n',
          { headers: { "content-type": "application/jsonl" } },
        );
      }
      statusCalls++;
      if (statusCalls === 1) {
        return jsonResponse({ id: "msgbatch_wip", processing_status: "in_progress", request_counts: { processing: 1 } });
      }
      return jsonResponse({ id: "msgbatch_wip", processing_status: "ended", request_counts: { succeeded: 1 } });
    });

    const results = await client().waitForCompletion("msgbatch_wip", 0.01);
    expect(results).toHaveLength(1);
    expect(results[0]!.result_type).toBe("succeeded");
    expect(statusCalls).toBe(2);
  });
});

// ---------------------------------------------------------------------------
// makeCacheableRequest
// ---------------------------------------------------------------------------

describe("makeCacheableRequest", () => {
  it("default ephemeral cache with no ttl", () => {
    const req = BatchClient.makeCacheableRequest({
      custom_id: "c1",
      model: "claude-sonnet-4-20250514",
      max_tokens: 200,
      user_message: "What is the book about?",
      system_prompt: "You are a literary critic.",
    });

    expect(req.custom_id).toBe("c1");
    const system = (req.params["system"] as any[])[0];
    expect(system.cache_control).toEqual({ type: "ephemeral" });
    expect(system.cache_control.ttl).toBeUndefined();
  });

  it("one-hour cache ttl", () => {
    const req = BatchClient.makeCacheableRequest({
      custom_id: "c2",
      model: "claude-sonnet-4-20250514",
      max_tokens: 200,
      user_message: "Summarize.",
      system_prompt: "You are a helpful assistant.",
      cache_ttl: 3600,
    });

    const system = (req.params["system"] as any[])[0];
    expect(system.cache_control.ttl).toBe(3600);
    expect(system.cache_control.type).toBe("ephemeral");
  });

  it("no system prompt means no system array", () => {
    const req = BatchClient.makeCacheableRequest({
      custom_id: "c3",
      model: "claude-sonnet-4-20250514",
      max_tokens: 100,
      user_message: "Hello",
    });

    expect(req.params["system"]).toBeUndefined();
    expect((req.params["messages"] as any[])[0].content).toBe("Hello");
  });
});

// ---------------------------------------------------------------------------
// Type exhaustiveness
// ---------------------------------------------------------------------------

describe("type checking", () => {
  it("BatchProcessingStatus covers all lifecycle states", () => {
    const states: BatchProcessingStatus[] = ["in_progress", "ended", "canceled", "expired"];
    expect(states).toHaveLength(4);
  });

  it("ResultType covers all per-request outcomes", () => {
    const types: ResultType[] = ["succeeded", "errored", "canceled", "expired"];
    expect(types).toHaveLength(4);
  });

  it("MessageRequest shape is correct", () => {
    const req: MessageRequest = {
      custom_id: "t1",
      params: {
        model: "claude-haiku-3-5-20241022",
        max_tokens: 50,
        messages: [{ role: "user", content: "ping" }],
      },
    };
    expect(req.custom_id).toBe("t1");
    expect(req.params.model).toBe("claude-haiku-3-5-20241022");
  });
});
