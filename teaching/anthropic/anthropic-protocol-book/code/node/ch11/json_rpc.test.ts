/**
 * Tests for Chapter 11: JSON-RPC 2.0 Message Parser (TypeScript).
 */

import { describe, it, expect } from "vitest";
import {
  JSONRPCParser,
  JSONRPCParseError,
  makeRequest,
  makeResponse,
  makeError,
  makeNotification,
  JSONRPCRequest,
  JSONRPCResponse,
  JSONRPCError,
  JSONRPCNotification,
} from "./JSONRPC";

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------

function parser(): JSONRPCParser {
  return new JSONRPCParser();
}

// ---------------------------------------------------------------------------
// Request Tests
// ---------------------------------------------------------------------------

describe("JSONRPCRequest", () => {
  it("should create and serialize a request", () => {
    const req = makeRequest(1, "test/echo", { message: "hello" });
    const raw = parser().serialize(req);
    const parsed = JSON.parse(raw);
    expect(parsed).toEqual({
      jsonrpc: "2.0",
      id: 1,
      method: "test/echo",
      params: { message: "hello" },
    });
  });

  it("should parse a minimal request", () => {
    const msg = parser().parseMessage(
      '{"jsonrpc":"2.0","id":1,"method":"ping"}',
    );
    expect(msg).toMatchObject({ jsonrpc: "2.0", id: 1, method: "ping" });
    // verify it is a request (has id AND method)
    expect("method" in msg && "id" in msg).toBe(true);
  });

  it("should parse a request with string id", () => {
    const msg = parser().parseMessage(
      '{"jsonrpc":"2.0","id":"req-abc","method":"fetch"}',
    );
    const req = msg as JSONRPCRequest;
    expect(req.id).toBe("req-abc");
    expect(req.method).toBe("fetch");
  });

  it("should parse request with params", () => {
    const msg = parser().parseMessage(
      '{"jsonrpc":"2.0","id":2,"method":"add","params":{"a":1,"b":2}}',
    );
    const req = msg as JSONRPCRequest;
    expect(req.params).toEqual({ a: 1, b: 2 });
  });

  it("should round-trip a request", () => {
    const original = makeRequest(42, "tools/list", { cursor: "abc" });
    const raw = parser().serialize(original);
    const parsed = parser().parseMessage(raw) as JSONRPCRequest;
    expect(parsed.id).toBe(original.id);
    expect(parsed.method).toBe(original.method);
    expect(parsed.params).toEqual(original.params);
  });

  it("should reject null id per MCP spec", () => {
    expect(() =>
      parser().parseMessage(
        '{"jsonrpc":"2.0","id":null,"method":"test"}',
      ),
    ).toThrow(JSONRPCParseError);
  });

  it("should reject non-string/number id", () => {
    expect(() =>
      parser().parseMessage(
        '{"jsonrpc":"2.0","id":[1,2],"method":"test"}',
      ),
    ).toThrow(JSONRPCParseError);
  });
});

// ---------------------------------------------------------------------------
// Response Tests
// ---------------------------------------------------------------------------

describe("JSONRPCResponse", () => {
  it("should create and serialize a response", () => {
    const resp = makeResponse(1, { status: "ok" });
    const raw = parser().serialize(resp);
    const parsed = JSON.parse(raw);
    expect(parsed).toEqual({
      jsonrpc: "2.0",
      id: 1,
      result: { status: "ok" },
    });
  });

  it("should parse a response", () => {
    const msg = parser().parseMessage(
      '{"jsonrpc":"2.0","id":3,"result":{"name":"Alice","age":30}}',
    );
    const resp = msg as JSONRPCResponse;
    expect(resp.id).toBe(3);
    expect(resp.result).toEqual({ name: "Alice", age: 30 });
  });

  it("should handle null result", () => {
    const msg = parser().parseMessage(
      '{"jsonrpc":"2.0","id":5,"result":null}',
    );
    const resp = msg as JSONRPCResponse;
    expect(resp.result).toBeNull();
  });

  it("should round-trip a response", () => {
    const original = makeResponse("abc", [1, 2, 3]);
    const raw = parser().serialize(original);
    const parsed = parser().parseMessage(raw) as JSONRPCResponse;
    expect(parsed.id).toBe(original.id);
    expect(parsed.result).toEqual(original.result);
  });

  it("should reject message with both result and error", () => {
    expect(() =>
      parser().parseMessage(
        '{"jsonrpc":"2.0","id":1,"result":"ok","error":{"code":-1,"message":"err"}}',
      ),
    ).toThrow("must not contain both");
  });
});

// ---------------------------------------------------------------------------
// Error Tests
// ---------------------------------------------------------------------------

describe("JSONRPCError", () => {
  it("should create and serialize an error", () => {
    const err = makeError(1, -32601, "Method not found");
    const raw = parser().serialize(err);
    const parsed = JSON.parse(raw);
    expect(parsed).toEqual({
      jsonrpc: "2.0",
      id: 1,
      error: { code: -32601, message: "Method not found" },
    });
  });

  it("should parse error with data", () => {
    const msg = parser().parseMessage(
      JSON.stringify({
        jsonrpc: "2.0",
        id: 2,
        error: {
          code: -32602,
          message: "Invalid params",
          data: { field: "uri", reason: "missing" },
        },
      }),
    );
    const err = msg as JSONRPCError;
    expect(err.id).toBe(2);
    expect(err.error.code).toBe(-32602);
    expect(err.error.message).toBe("Invalid params");
    expect(err.error.data).toEqual({ field: "uri", reason: "missing" });
  });

  it("should parse minimal error", () => {
    const msg = parser().parseMessage(
      '{"jsonrpc":"2.0","id":99,"error":{"code":-32000,"message":"Server error"}}',
    );
    const err = msg as JSONRPCError;
    expect(err.error.code).toBe(-32000);
  });

  it("should reject error missing code field", () => {
    expect(() =>
      parser().parseMessage(
        '{"jsonrpc":"2.0","id":1,"error":{"message":"no code"}}',
      ),
    ).toThrow(JSONRPCParseError);
  });

  it("should reject non-integer error code", () => {
    expect(() =>
      parser().parseMessage(
        '{"jsonrpc":"2.0","id":1,"error":{"code":"abc","message":"bad"}}',
      ),
    ).toThrow(JSONRPCParseError);
  });

  it("should reject error missing message field", () => {
    expect(() =>
      parser().parseMessage(
        '{"jsonrpc":"2.0","id":1,"error":{"code":-1}}',
      ),
    ).toThrow(JSONRPCParseError);
  });

  it("should round-trip an error", () => {
    const original = makeError(
      "req-99",
      -32602,
      "Invalid params",
      { details: "bad type" },
    );
    const raw = parser().serialize(original);
    const parsed = parser().parseMessage(raw) as JSONRPCError;
    expect(parsed.id).toBe(original.id);
    expect(parsed.error.code).toBe(original.error.code);
    expect(parsed.error.message).toBe(original.error.message);
    expect(parsed.error.data).toEqual(original.error.data);
  });
});

// ---------------------------------------------------------------------------
// Notification Tests
// ---------------------------------------------------------------------------

describe("JSONRPCNotification", () => {
  it("should create and serialize a notification", () => {
    const notif = makeNotification("notifications/initialized");
    const raw = parser().serialize(notif);
    const parsed = JSON.parse(raw);
    expect(parsed).toEqual({
      jsonrpc: "2.0",
      method: "notifications/initialized",
    });
  });

  it("should parse notification with params", () => {
    const msg = parser().parseMessage(
      '{"jsonrpc":"2.0","method":"notifications/progress",' +
        '"params":{"progressToken":"t1","progress":50,"total":100}}',
    );
    const notif = msg as JSONRPCNotification;
    expect(notif.method).toBe("notifications/progress");
    expect(notif.params).toEqual({
      progressToken: "t1",
      progress: 50,
      total: 100,
    });
  });

  it("should parse notification without params", () => {
    const msg = parser().parseMessage(
      '{"jsonrpc":"2.0","method":"notifications/initialized"}',
    );
    const notif = msg as JSONRPCNotification;
    expect(notif.method).toBe("notifications/initialized");
    expect(notif.params).toBeUndefined();
  });

  it("should round-trip a notification", () => {
    const original = makeNotification(
      "notifications/resources/updated",
      { uri: "file:///project/src/main.rs" },
    );
    const raw = parser().serialize(original);
    const parsed = parser().parseMessage(raw) as JSONRPCNotification;
    expect(parsed.method).toBe(original.method);
    expect(parsed.params).toEqual(original.params);
  });
});

// ---------------------------------------------------------------------------
// Validation Tests
// ---------------------------------------------------------------------------

describe("Validation", () => {
  it("should reject invalid JSON", () => {
    expect(() => parser().parseMessage("not json")).toThrow(JSONRPCParseError);
  });

  it("should reject non-object (array)", () => {
    expect(() => parser().parseMessage("[1,2,3]")).toThrow(JSONRPCParseError);
  });

  it("should reject missing jsonrpc version", () => {
    expect(() =>
      parser().parseMessage('{"id":1,"method":"test"}'),
    ).toThrow(JSONRPCParseError);
  });

  it("should reject wrong jsonrpc version", () => {
    expect(() =>
      parser().parseMessage('{"jsonrpc":"1.0","id":1,"method":"test"}'),
    ).toThrow(JSONRPCParseError);
  });

  it("should reject ambiguous message", () => {
    expect(() =>
      parser().parseMessage('{"jsonrpc":"2.0","id":1}'),
    ).toThrow(JSONRPCParseError);
  });
});

// ---------------------------------------------------------------------------
// Batch Tests
// ---------------------------------------------------------------------------

describe("Batch", () => {
  it("should parse a batch of requests and notifications", () => {
    const raw = JSON.stringify([
      { jsonrpc: "2.0", id: 1, method: "ping" },
      { jsonrpc: "2.0", id: 2, method: "tools/list" },
      {
        jsonrpc: "2.0",
        method: "notifications/cancelled",
        params: { requestId: 1 },
      },
    ]);
    const messages = parser().parseBatch(raw);
    expect(messages).toHaveLength(3);
    expect("method" in messages[0]! && "id" in messages[0]!).toBe(true);
    expect("method" in messages[2]! && !("id" in messages[2]!)).toBe(true);
  });

  it("should handle empty batch", () => {
    const messages = parser().parseBatch("[]");
    expect(messages).toEqual([]);
  });

  it("should reject non-array batch", () => {
    expect(() => parser().parseBatch('{"a":1}')).toThrow(JSONRPCParseError);
  });

  it("should serialize batch", () => {
    const messages = [makeRequest(1, "ping"), makeResponse(2, "ok")];
    const raw = parser().serializeBatch(messages);
    const parsed = parser().parseBatch(raw);
    expect(parsed).toHaveLength(2);
  });

  it("should propagate errors in batch items", () => {
    const raw = JSON.stringify([
      { jsonrpc: "2.0", id: 1, method: "ok" },
      { jsonrpc: "2.0" }, // invalid
    ]);
    expect(() => parser().parseBatch(raw)).toThrow(JSONRPCParseError);
  });
});

// ---------------------------------------------------------------------------
// MCP Real-World Messages
// ---------------------------------------------------------------------------

describe("MCP real-world messages", () => {
  it("should parse initialize request", () => {
    const raw = JSON.stringify({
      jsonrpc: "2.0",
      id: 1,
      method: "initialize",
      params: {
        protocolVersion: "2025-03-26",
        capabilities: {
          roots: { listChanged: true },
          sampling: {},
        },
        clientInfo: { name: "TestClient", version: "1.0.0" },
      },
    });
    const msg = parser().parseMessage(raw) as JSONRPCRequest;
    expect(msg.method).toBe("initialize");
    expect(msg.params?.protocolVersion).toBe("2025-03-26");
    expect((msg.params?.capabilities as Record<string, unknown>).sampling).toEqual({});
  });

  it("should parse initialize response", () => {
    const raw = JSON.stringify({
      jsonrpc: "2.0",
      id: 1,
      result: {
        protocolVersion: "2025-03-26",
        capabilities: {
          tools: { listChanged: true },
          resources: { subscribe: true, listChanged: true },
        },
        serverInfo: { name: "TestServer", version: "2.0.0" },
      },
    });
    const msg = parser().parseMessage(raw) as JSONRPCResponse;
    const result = msg.result as Record<string, unknown>;
    const serverInfo = result.serverInfo as Record<string, unknown>;
    expect(serverInfo.name).toBe("TestServer");
  });

  it("should parse tools/list request", () => {
    const msg = parser().parseMessage(
      '{"jsonrpc":"2.0","id":2,"method":"tools/list","params":{"cursor":"p1"}}',
    );
    const req = msg as JSONRPCRequest;
    expect(req.method).toBe("tools/list");
  });

  it("should parse tools/call response", () => {
    const raw = JSON.stringify({
      jsonrpc: "2.0",
      id: 3,
      result: {
        content: [{ type: "text", text: "72F, sunny" }],
        isError: false,
      },
    });
    const msg = parser().parseMessage(raw) as JSONRPCResponse;
    const result = msg.result as Record<string, unknown>;
    expect(result.isError).toBe(false);
  });

  it("should parse sampling/createMessage request", () => {
    const raw = JSON.stringify({
      jsonrpc: "2.0",
      id: 10,
      method: "sampling/createMessage",
      params: {
        messages: [
          { role: "user", content: { type: "text", text: "Hello" } },
        ],
        maxTokens: 100,
      },
    });
    const msg = parser().parseMessage(raw) as JSONRPCRequest;
    expect(msg.method).toBe("sampling/createMessage");
  });

  it("should parse resource updated notification", () => {
    const raw = JSON.stringify({
      jsonrpc: "2.0",
      method: "notifications/resources/updated",
      params: { uri: "file:///project/main.rs" },
    });
    const msg = parser().parseMessage(raw) as JSONRPCNotification;
    expect(msg.params?.uri).toBe("file:///project/main.rs");
  });
});

// ---------------------------------------------------------------------------
// Error case: serialize unknown type
// ---------------------------------------------------------------------------

describe("serialize error", () => {
  it("should throw on unknown message type", () => {
    expect(() => parser().serialize({} as never)).toThrow(TypeError);
  });
});
