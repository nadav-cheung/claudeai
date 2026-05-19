/**
 * Tests for Chapter 6: Tool Registry (TypeScript).
 */

import { describe, it, expect, beforeEach } from "vitest";
import { ToolRegistry, ToolDefinition, JsonSchema } from "./ToolRegistry";

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------

function baseSchema(props: Record<string, Record<string, unknown>> = {}): JsonSchema {
  return { type: "object", properties: props, required: [] };
}

function populatedRegistry(): ToolRegistry {
  const r = new ToolRegistry();

  r.register(
    "get_weather",
    "Get current weather for a location",
    {
      type: "object",
      properties: {
        location: { type: "string", description: "City name" },
      },
      required: ["location"],
    },
    (input: Record<string, unknown>) => `Weather for ${input.location}: 72F`,
    { defer_loading: false },
  );

  r.register(
    "get_time",
    "Get current time for a timezone",
    {
      type: "object",
      properties: { timezone: { type: "string" } },
      required: ["timezone"],
    },
    (input: Record<string, unknown>) => `Time in ${input.timezone}: 14:30`,
    { strict: true },
  );

  r.register(
    "search_news",
    "Search recent news articles",
    {
      type: "object",
      properties: {
        query: { type: "string" },
        max_results: { type: "integer", default: 10 },
      },
      required: ["query"],
    },
    (input: Record<string, unknown>) =>
      [`News for ${input.query}`],
    { defer_loading: true },
  );

  r.register(
    "query_database",
    "Execute SQL query. Returns rows as JSON objects.",
    {
      type: "object",
      properties: { sql: { type: "string", description: "SQL query" } },
      required: ["sql"],
    },
    (_input: Record<string, unknown>) => [{ id: 1, name: "test" }],
    { allowed_callers: ["code_execution_20260120"] },
  );

  r.register(
    "send_slack",
    "Send message to Slack channel",
    {
      type: "object",
      properties: {
        channel: { type: "string" },
        text: { type: "string" },
      },
      required: ["channel", "text"],
    },
    (input: Record<string, unknown>) => ({ ok: true, channel: input.channel }),
    { defer_loading: true, allowed_callers: ["direct"] },
  );

  return r;
}

// ---------------------------------------------------------------------------
// Registration
// ---------------------------------------------------------------------------

describe("Registration", () => {
  it("registers a simple tool", () => {
    const r = new ToolRegistry();
    r.register("my_tool", "Test tool", baseSchema(), () => "done");
    expect(r.count()).toBe(1);
    expect(r.get("my_tool")).toBeDefined();
  });

  it("throws on duplicate registration", () => {
    const r = new ToolRegistry();
    r.register("dup", "First", baseSchema(), () => 1);
    expect(() =>
      r.register("dup", "Second", baseSchema(), () => 2),
    ).toThrow(/already registered/);
  });

  it("throws on non-callable handler", () => {
    const r = new ToolRegistry();
    expect(() =>
      r.register("bad", "Desc", baseSchema(), "not_a_fn" as any),
    ).toThrow(/must be a function/);
  });

  it("throws on invalid schema type", () => {
    const r = new ToolRegistry();
    expect(() =>
      r.register("bad", "Desc", { type: "string" } as any, () => null),
    ).toThrow(/type='object'/);
  });

  it("unregisters a tool", () => {
    const r = new ToolRegistry();
    r.register("t1", "d", baseSchema(), () => null);
    expect(r.count()).toBe(1);
    r.unregister("t1");
    expect(r.count()).toBe(0);
    // No-op for missing
    expect(() => r.unregister("nonexistent")).not.toThrow();
  });

  it("registers with all options", () => {
    const r = new ToolRegistry();
    r.register(
      "full_tool",
      "All options",
      {
        type: "object",
        properties: { x: { type: "integer" } },
        required: [],
      },
      (input: Record<string, unknown>) => (input.x as number) * 2,
      {
        defer_loading: true,
        allowed_callers: ["code_execution_20260120"],
        input_examples: [{ x: 5 }, { x: 10 }],
        strict: true,
      },
    );
    const tool = r.get("full_tool");
    expect(tool).toBeDefined();
    expect(tool!.defer_loading).toBe(true);
    expect(tool!.allowed_callers).toEqual(["code_execution_20260120"]);
    expect(tool!.strict).toBe(true);
    expect(tool!.input_examples).toHaveLength(2);
  });
});

// ---------------------------------------------------------------------------
// Queries
// ---------------------------------------------------------------------------

describe("Queries", () => {
  let reg: ToolRegistry;
  beforeEach(() => { reg = populatedRegistry(); });

  it("gets an existing tool", () => {
    const tool = reg.get("get_weather");
    expect(tool).toBeDefined();
    expect(tool!.name).toBe("get_weather");
  });

  it("returns undefined for missing tool", () => {
    expect(reg.get("nonexistent")).toBeUndefined();
  });

  it("lists all names", () => {
    const names = reg.listNames();
    expect(names).toHaveLength(5);
    expect(names).toContain("get_weather");
    expect(names).toContain("search_news");
  });

  it("counts correctly", () => {
    expect(reg.count()).toBe(5);
  });

  it("gets deferred tools", () => {
    const deferred = reg.getDeferredTools();
    const names = deferred.map((t) => t.name);
    expect(names).toContain("search_news");
    expect(names).toContain("send_slack");
    expect(names).not.toContain("get_weather");
    expect(deferred).toHaveLength(2);
  });

  it("gets immediate tools", () => {
    const immediate = reg.getImmediateTools();
    const names = immediate.map((t) => t.name);
    expect(names).toContain("get_weather");
    expect(names).toContain("get_time");
    expect(names).toContain("query_database");
    expect(immediate).toHaveLength(3);
  });

  it("gets programmatic tools", () => {
    const pt = reg.getProgrammaticTools();
    const names = pt.map((t) => t.name);
    expect(names).toContain("query_database");
    expect(names).not.toContain("send_slack");
    expect(pt).toHaveLength(1);
  });

  it("gets strict tools", () => {
    const strict = reg.getStrictTools();
    expect(strict).toHaveLength(1);
    expect(strict[0]!.name).toBe("get_time");
  });
});

// ---------------------------------------------------------------------------
// API format
// ---------------------------------------------------------------------------

describe("API format", () => {
  let reg: ToolRegistry;
  beforeEach(() => { reg = populatedRegistry(); });

  it("generates API format with all tools", () => {
    const tools = reg.toApiFormat();
    expect(tools).toHaveLength(5);
    for (const t of tools) {
      expect(t).toHaveProperty("name");
      expect(t).toHaveProperty("description");
      expect(t).toHaveProperty("input_schema");
    }
  });

  it("includes deferred flags", () => {
    const tools = reg.toApiFormat();
    const deferred = tools.filter((t) => t.defer_loading === true);
    expect(deferred).toHaveLength(2);
  });

  it("includes allowed_callers", () => {
    const tools = reg.toApiFormat();
    const dbTool = tools.find((t) => t.name === "query_database")!;
    expect(dbTool.allowed_callers).toEqual(["code_execution_20260120"]);
  });

  it("includes strict flag", () => {
    const tools = reg.toApiFormat();
    const timeTool = tools.find((t) => t.name === "get_time")!;
    expect(timeTool.strict).toBe(true);
  });

  it("generates search index format (deferred only)", () => {
    const index = reg.toSearchIndexFormat();
    expect(index).toHaveLength(2);
    const names = index.map((e) => e.name);
    expect(names).toContain("search_news");
    expect(names).toContain("send_slack");
    expect(names).not.toContain("get_weather");
  });
});

// ---------------------------------------------------------------------------
// Execution
// ---------------------------------------------------------------------------

describe("Execution", () => {
  let reg: ToolRegistry;
  beforeEach(() => { reg = populatedRegistry(); });

  it("executes a tool successfully", () => {
    const result = reg.execute("get_weather", { location: "Tokyo" });
    expect(result.success).toBe(true);
    expect(result.result).toContain("Tokyo");
  });

  it("throws for missing tool", () => {
    expect(() => reg.execute("nonexistent", {})).toThrow(/not found/);
  });

  it("handles handler errors gracefully", () => {
    const r = new ToolRegistry();
    r.register("failing", "Always fails", baseSchema(), () => {
      throw new Error("boom");
    });
    const result = r.execute("failing", {});
    expect(result.success).toBe(false);
    expect(result.error).toContain("boom");
  });

  it("executes many in order", () => {
    const results = reg.executeMany([
      { tool_name: "get_weather", input: { location: "SF" } },
      { tool_name: "get_time", input: { timezone: "UTC" } },
    ]);
    expect(results).toHaveLength(2);
    expect(results[0]!.success).toBe(true);
    expect(results[1]!.success).toBe(true);
  });

  it("handles mixed success/failure in executeMany", () => {
    const r = new ToolRegistry();
    r.register("ok", "ok", baseSchema(), () => "good");
    r.register("fail", "fail", baseSchema(), () => {
      throw new Error("bad");
    });
    const results = r.executeMany([
      { tool_name: "ok", input: {} },
      { tool_name: "fail", input: {} },
    ]);
    expect(results[0]!.success).toBe(true);
    expect(results[1]!.success).toBe(false);
  });
});

// ---------------------------------------------------------------------------
// Feature toggles
// ---------------------------------------------------------------------------

describe("Feature toggles", () => {
  it("enables tool search", () => {
    const r = new ToolRegistry();
    expect(r.isSearchEnabled).toBe(false);
    r.enableToolSearch();
    expect(r.isSearchEnabled).toBe(true);
  });

  it("enables code execution", () => {
    const r = new ToolRegistry();
    expect(r.isCodeExecutionEnabled).toBe(false);
    r.enableCodeExecution();
    expect(r.isCodeExecutionEnabled).toBe(true);
  });
});
