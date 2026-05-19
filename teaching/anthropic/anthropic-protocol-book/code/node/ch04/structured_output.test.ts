/**
 * Tests for Chapter 4 Structured Outputs client (TypeScript).
 */

import { describe, it, expect } from "vitest";
import {
  StructuredOutputClient,
  parseJsonResponse,
} from "./StructuredOutputClient";
import type { ClientLike, JsonSchema } from "./StructuredOutputClient";

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------

const colorSchema: JsonSchema = {
  type: "object",
  properties: {
    colors: { type: "array", items: { type: "string" } },
    count: { type: "integer" },
  },
  required: ["colors"],
};

const personSchema: JsonSchema = {
  type: "object",
  properties: {
    name: { type: "string" },
    age: { type: "integer" },
    email: { type: "string" },
  },
  required: ["name", "age"],
};

// ---------------------------------------------------------------------------
// Fake client
// ---------------------------------------------------------------------------

function fakeClient(responseText?: string): {
  client: ClientLike;
  lastParams: () => Record<string, unknown>;
} {
  let last: Record<string, unknown> = {};

  const client: ClientLike = {
    async post(params: Record<string, unknown>): Promise<Record<string, unknown>> {
      last = params;
      const text = responseText ?? '{"colors":["red","green","blue"],"count":3}';
      return {
        id: "msg_fake",
        type: "message",
        role: "assistant",
        content: [{ type: "text", text }],
        model: "claude-sonnet-4-20250514",
        stop_reason: "end_turn",
        stop_sequence: null,
        usage: { input_tokens: 50, output_tokens: 30 },
      };
    },
  };

  return { client, lastParams: () => last };
}

// ---------------------------------------------------------------------------
// StructuredOutputClient.create()
// ---------------------------------------------------------------------------

describe("StructuredOutputClient.create", () => {
  it("passes output_config with json_schema format", async () => {
    const { client, lastParams } = fakeClient();
    const sut = new StructuredOutputClient(client);

    await sut.create({
      model: "claude-sonnet-4-20250514",
      messages: [{ role: "user", content: "List colors" }],
      jsonSchema: colorSchema,
      system: "Be concise.",
    });

    const params = lastParams();
    expect(params.model).toBe("claude-sonnet-4-20250514");
    expect(params.system).toBe("Be concise.");
    expect(params.max_tokens).toBe(4096);
    const oc = params.output_config as Record<string, unknown>;
    expect(oc).toBeDefined();
    expect((oc.format as Record<string, unknown>).type).toBe("json_schema");
    expect((oc.format as Record<string, unknown>).schema).toEqual(colorSchema);
  });

  it("defaults maxTokens to 4096", async () => {
    const { client, lastParams } = fakeClient();
    const sut = new StructuredOutputClient(client);
    await sut.create({ model: "x", messages: [], jsonSchema: colorSchema });
    expect(lastParams().max_tokens).toBe(4096);
  });

  it("accepts custom maxTokens", async () => {
    const { client, lastParams } = fakeClient();
    const sut = new StructuredOutputClient(client);
    await sut.create({
      model: "x",
      messages: [],
      jsonSchema: colorSchema,
      maxTokens: 256,
    });
    expect(lastParams().max_tokens).toBe(256);
  });

  it("passes effort when provided", async () => {
    const { client, lastParams } = fakeClient();
    const sut = new StructuredOutputClient(client);
    await sut.create({
      model: "x",
      messages: [],
      jsonSchema: colorSchema,
      effort: "high",
    });
    const oc = lastParams().output_config as Record<string, unknown>;
    expect(oc.effort).toBe("high");
  });

  it("omits effort when not provided", async () => {
    const { client, lastParams } = fakeClient();
    const sut = new StructuredOutputClient(client);
    await sut.create({
      model: "x",
      messages: [],
      jsonSchema: colorSchema,
    });
    const oc = lastParams().output_config as Record<string, unknown>;
    expect(oc.effort).toBeUndefined();
  });

  it("forwards extra parameters", async () => {
    const { client, lastParams } = fakeClient();
    const sut = new StructuredOutputClient(client);
    await sut.create({
      model: "x",
      messages: [],
      jsonSchema: colorSchema,
      temperature: 0.3,
      top_p: 0.9,
    } as Record<string, unknown>);
    expect(lastParams().temperature).toBe(0.3);
    expect(lastParams().top_p).toBe(0.9);
  });

  it("returns the raw API response", async () => {
    const { client } = fakeClient();
    const sut = new StructuredOutputClient(client);
    const result = await sut.create({
      model: "x",
      messages: [],
      jsonSchema: colorSchema,
    });
    expect(result.id).toBe("msg_fake");
    expect(Array.isArray(result.content)).toBe(true);
  });
});

// ---------------------------------------------------------------------------
// StructuredOutputClient.extract()
// ---------------------------------------------------------------------------

describe("StructuredOutputClient.extract", () => {
  it("extracts from a pure JSON response", async () => {
    const { client } = fakeClient(
      '{"name":"Alice","age":30,"email":"alice@example.com"}',
    );
    const sut = new StructuredOutputClient(client);

    const result = await sut.extract({
      model: "claude-sonnet-4-20250514",
      text: "Alice is 30 years old.",
      jsonSchema: personSchema,
    });

    expect(result.name).toBe("Alice");
    expect(result.age).toBe(30);
    expect(result.email).toBe("alice@example.com");
  });

  it("extracts from a markdown-fenced JSON response", async () => {
    const { client } = fakeClient(
      'Here is the result:\n```json\n{"name":"Bob","age":25}\n```',
    );
    const sut = new StructuredOutputClient(client);

    const result = await sut.extract({
      model: "x",
      text: "Bob is 25.",
      jsonSchema: personSchema,
    });

    expect(result.name).toBe("Bob");
    expect(result.age).toBe(25);
  });

  it("constructs an extraction prompt automatically", async () => {
    const { client, lastParams } = fakeClient('{"name":"Eve","age":40}');
    const sut = new StructuredOutputClient(client);

    await sut.extract({
      model: "x",
      text: "Eve is 40.",
      jsonSchema: personSchema,
      fieldDescription: "Get the person info.",
    });

    const messages = lastParams().messages as Record<string, unknown>[];
    const userMsg = messages[0] as Record<string, unknown>;
    expect(userMsg.content).toContain("Get the person info.");
    expect(userMsg.content).toContain("Eve is 40.");
    expect(lastParams().system).toBeDefined();
  });

  it("passes effort to create", async () => {
    const { client, lastParams } = fakeClient('{"name":"Dan","age":22}');
    const sut = new StructuredOutputClient(client);

    await sut.extract({
      model: "x",
      text: "Dan is 22.",
      jsonSchema: personSchema,
      effort: "low",
    });

    const oc = lastParams().output_config as Record<string, unknown>;
    expect(oc.effort).toBe("low");
  });

  it("handles complex nested schemas", async () => {
    const schema: JsonSchema = {
      type: "object",
      properties: {
        title: { type: "string" },
        tags: { type: "array", items: { type: "string" } },
        metadata: {
          type: "object",
          properties: {
            author: { type: "string" },
            priority: { type: "integer", enum: [1, 2, 3] },
          },
          required: ["author"],
        },
      },
      required: ["title", "tags"],
    };

    const { client } = fakeClient(
      JSON.stringify({
        title: "My Document",
        tags: ["important", "review"],
        metadata: { author: "Nadav", priority: 1 },
      }),
    );
    const sut = new StructuredOutputClient(client);

    const result = await sut.extract({
      model: "x",
      text: "Dummy",
      jsonSchema: schema,
    });

    expect(result.title).toBe("My Document");
    expect(result.tags).toEqual(["important", "review"]);
    const meta = result.metadata as Record<string, unknown>;
    expect(meta.author).toBe("Nadav");
    expect(meta.priority).toBe(1);
  });
});

// ---------------------------------------------------------------------------
// parseJsonResponse()
// ---------------------------------------------------------------------------

describe("parseJsonResponse", () => {
  it("parses pure JSON", () => {
    expect(parseJsonResponse('{"a":1,"b":"two"}')).toEqual({ a: 1, b: "two" });
  });

  it("parses JSON in a fenced block", () => {
    const text = 'Some intro text\n```json\n{"x": [1,2,3]}\n```\nSome outro';
    expect(parseJsonResponse(text)).toEqual({ x: [1, 2, 3] });
  });

  it("parses JSON in an untyped fenced block", () => {
    expect(parseJsonResponse('```\n{"key":"value"}\n```')).toEqual({ key: "value" });
  });

  it("parses JSON surrounded by text (outermost braces)", () => {
    const text = 'Sure! Here you go: {"items":["a","b"]} Hope that helps!';
    expect(parseJsonResponse(text)).toEqual({ items: ["a", "b"] });
  });

  it("handles nested braces", () => {
    expect(parseJsonResponse('{"outer":{"inner":[1,2,3]}}')).toEqual({
      outer: { inner: [1, 2, 3] },
    });
  });

  it("throws on garbage", () => {
    expect(() => parseJsonResponse("this is not json at all")).toThrow(
      "Could not parse JSON",
    );
  });

  it("parses empty object", () => {
    expect(parseJsonResponse("{}")).toEqual({});
  });
});
