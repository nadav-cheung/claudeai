/**
 * Chapter 11: JSON-RPC 2.0 Message Parser (TypeScript).
 *
 * Protocol-level implementation of the JSON-RPC 2.0 specification as used by
 * the Model Context Protocol (MCP). Supports Request, Response, Error, and
 * Notification message types, round-trip serialization, and validation.
 *
 * Reference: https://www.jsonrpc.org/specification
 */

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

/** Standard JSON-RPC 2.0 error codes */
export const PARSE_ERROR = -32700;
export const INVALID_REQUEST = -32600;
export const METHOD_NOT_FOUND = -32601;
export const INVALID_PARAMS = -32602;
export const INTERNAL_ERROR = -32603;

// ---------------------------------------------------------------------------
// Message Types
// ---------------------------------------------------------------------------

/** A JSON-RPC 2.0 Request — MUST have a non-null id (per MCP spec). */
export interface JSONRPCRequest {
  readonly jsonrpc: "2.0";
  readonly id: string | number;
  readonly method: string;
  readonly params?: Record<string, unknown>;
}

/** A JSON-RPC 2.0 successful Response. */
export interface JSONRPCResponse {
  readonly jsonrpc: "2.0";
  readonly id: string | number;
  readonly result: unknown;
}

/** A JSON-RPC 2.0 Error response. */
export interface JSONRPCError {
  readonly jsonrpc: "2.0";
  readonly id: string | number;
  readonly error: {
    readonly code: number;
    readonly message: string;
    readonly data?: unknown;
  };
}

/** A JSON-RPC 2.0 Notification — one-way, MUST NOT have an id. */
export interface JSONRPCNotification {
  readonly jsonrpc: "2.0";
  readonly method: string;
  readonly params?: Record<string, unknown>;
}

/** Union of all JSON-RPC 2.0 message types. */
export type JSONRPCMessage =
  | JSONRPCRequest
  | JSONRPCResponse
  | JSONRPCError
  | JSONRPCNotification;

// ---------------------------------------------------------------------------
// Internal guards
// ---------------------------------------------------------------------------

interface RawMessage {
  jsonrpc?: unknown;
  id?: unknown;
  method?: unknown;
  result?: unknown;
  error?: unknown;
  params?: unknown;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function isStringOrNumber(value: unknown): value is string | number {
  return typeof value === "string" || typeof value === "number";
}

// ---------------------------------------------------------------------------
// Parser
// ---------------------------------------------------------------------------

export class JSONRPCParseError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "JSONRPCParseError";
  }
}

export class JSONRPCParser {
  /**
   * Parse a raw JSON string into a typed JSON-RPC 2.0 message.
   *
   * @throws {JSONRPCParseError} if the input is not valid JSON or does not
   *   conform to the JSON-RPC 2.0 specification.
   */
  parseMessage(raw: string): JSONRPCMessage {
    let obj: unknown;
    try {
      obj = JSON.parse(raw);
    } catch (err) {
      throw new JSONRPCParseError(
        `Invalid JSON: ${err instanceof Error ? err.message : String(err)}`,
      );
    }

    if (!isRecord(obj)) {
      throw new JSONRPCParseError(
        "JSON-RPC message must be a JSON object, not an array or scalar",
      );
    }

    const data = obj as RawMessage;

    // Validate jsonrpc version
    if (data.jsonrpc !== "2.0") {
      throw new JSONRPCParseError(
        `Invalid or missing 'jsonrpc' field: expected '2.0', got ${JSON.stringify(data.jsonrpc)}`,
      );
    }

    const hasId = "id" in data;
    const hasMethod = "method" in data;
    const hasResult = "result" in data;
    const hasError = "error" in data;

    // Notification (no id, has method)
    if (!hasId && hasMethod) {
      return {
        jsonrpc: "2.0",
        method: data.method as string,
        params: data.params as Record<string, unknown> | undefined,
      };
    }

    // Request (has id AND method, no result/error)
    if (hasId && hasMethod && !hasResult && !hasError) {
      if (data.id === null) {
        throw new JSONRPCParseError(
          "Request 'id' must not be null per MCP spec",
        );
      }
      if (!isStringOrNumber(data.id)) {
        throw new JSONRPCParseError(
          `Request 'id' must be string or number, got ${typeof data.id}`,
        );
      }
      return {
        jsonrpc: "2.0",
        id: data.id,
        method: data.method as string,
        params: data.params as Record<string, unknown> | undefined,
      };
    }

    // Per JSON-RPC 2.0: a response MUST NOT contain both result and error
    if (hasResult && hasError) {
      throw new JSONRPCParseError(
        "A JSON-RPC message must not contain both 'result' and 'error'",
      );
    }

    // Error (has id AND error, no result)
    if (hasId && hasError) {
      if (!isRecord(data.error)) {
        throw new JSONRPCParseError("'error' must be an object");
      }
      const err = data.error as Record<string, unknown>;
      if (!("code" in err)) {
        throw new JSONRPCParseError("'error' must contain 'code'");
      }
      if (typeof err.code !== "number") {
        throw new JSONRPCParseError("'error.code' must be a number");
      }
      if (!("message" in err) || typeof err.message !== "string") {
        throw new JSONRPCParseError("'error' must contain 'message'");
      }
      return {
        jsonrpc: "2.0",
        id: data.id as string | number,
        error: {
          code: err.code as number,
          message: err.message as string,
          data: err.data as unknown | undefined,
        },
      };
    }

    // Response (has id AND result, no error)
    if (hasId && hasResult && !hasError) {
      return {
        jsonrpc: "2.0",
        id: data.id as string | number,
        result: data.result,
      };
    }

    throw new JSONRPCParseError(
      "Cannot determine message type: structure does not match any JSON-RPC 2.0 message variant",
    );
  }

  /**
   * Parse a JSON-RPC 2.0 batch array (an array of messages).
   */
  parseBatch(raw: string): JSONRPCMessage[] {
    let arr: unknown;
    try {
      arr = JSON.parse(raw);
    } catch (err) {
      throw new JSONRPCParseError(
        `Invalid JSON: ${err instanceof Error ? err.message : String(err)}`,
      );
    }

    if (!Array.isArray(arr)) {
      throw new JSONRPCParseError("Batch must be a JSON array");
    }

    return arr.map((item) => this.parseMessage(JSON.stringify(item)));
  }

  /**
   * Serialize a typed message back to a JSON-RPC 2.0 JSON string.
   */
  serialize(msg: JSONRPCMessage): string {
    if (this._isRequest(msg)) {
      const obj: Record<string, unknown> = {
        jsonrpc: msg.jsonrpc,
        id: msg.id,
        method: msg.method,
      };
      if (msg.params !== undefined) {
        obj.params = msg.params;
      }
      return JSON.stringify(obj);
    }

    if (this._isResponse(msg)) {
      return JSON.stringify({
        jsonrpc: msg.jsonrpc,
        id: msg.id,
        result: msg.result,
      });
    }

    if (this._isError(msg)) {
      return JSON.stringify({
        jsonrpc: msg.jsonrpc,
        id: msg.id,
        error: msg.error,
      });
    }

    if (this._isNotification(msg)) {
      const obj: Record<string, unknown> = {
        jsonrpc: msg.jsonrpc,
        method: msg.method,
      };
      if (msg.params !== undefined) {
        obj.params = msg.params;
      }
      return JSON.stringify(obj);
    }

    throw new TypeError(`Unknown message type`);
  }

  /**
   * Serialize a list of messages as a JSON-RPC 2.0 batch array.
   */
  serializeBatch(messages: JSONRPCMessage[]): string {
    const items = messages.map((msg) => JSON.parse(this.serialize(msg)));
    return JSON.stringify(items);
  }

  // ---- type guards ----

  private _isRequest(msg: JSONRPCMessage): msg is JSONRPCRequest {
    return "method" in msg && "id" in msg && !("result" in msg) && !("error" in msg);
  }

  private _isResponse(msg: JSONRPCMessage): msg is JSONRPCResponse {
    return "result" in msg && "id" in msg && !("error" in msg) && !("method" in msg);
  }

  private _isError(msg: JSONRPCMessage): msg is JSONRPCError {
    return "error" in msg && "id" in msg;
  }

  private _isNotification(msg: JSONRPCMessage): msg is JSONRPCNotification {
    return "method" in msg && !("id" in msg);
  }
}

// ---------------------------------------------------------------------------
// Factory helpers
// ---------------------------------------------------------------------------

export function makeRequest(
  id: string | number,
  method: string,
  params?: Record<string, unknown>,
): JSONRPCRequest {
  return params !== undefined
    ? { jsonrpc: "2.0", id, method, params }
    : { jsonrpc: "2.0", id, method };
}

export function makeResponse(
  id: string | number,
  result: unknown,
): JSONRPCResponse {
  return { jsonrpc: "2.0", id, result };
}

export function makeError(
  id: string | number,
  code: number,
  message: string,
  data?: unknown,
): JSONRPCError {
  return {
    jsonrpc: "2.0",
    id,
    error: data !== undefined ? { code, message, data } : { code, message },
  };
}

export function makeNotification(
  method: string,
  params?: Record<string, unknown>,
): JSONRPCNotification {
  return params !== undefined
    ? { jsonrpc: "2.0", method, params }
    : { jsonrpc: "2.0", method };
}
