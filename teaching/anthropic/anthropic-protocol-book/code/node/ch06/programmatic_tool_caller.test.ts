/**
 * Tests for Chapter 6: Programmatic Tool Caller (TypeScript).
 */

import { describe, it, expect, beforeEach } from "vitest";
import { ProgrammaticToolCaller } from "./ProgrammaticToolCaller";

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------

let caller: ProgrammaticToolCaller;
beforeEach(() => {
  caller = new ProgrammaticToolCaller();
});

// ---------------------------------------------------------------------------
// Code execution
// ---------------------------------------------------------------------------

describe("Code execution", () => {
  it("handles empty code", () => {
    const result = caller.executeCode("");
    expect(result.return_code).toBe(0);
    expect(result.stderr).toBe("No tool calls found in code");
  });

  it("extracts tool calls from orchestration code", () => {
    const code = `
team = await get_team_members("engineering")
expenses = await get_expenses("emp_123", "Q3")
budget = await get_budget_by_level("senior")
`;
    const result = caller.executeCode(code);
    expect(result.return_code).toBe(0);
    expect(caller.pendingCalls).toHaveLength(3);
    expect(caller.hasPendingCalls).toBe(true);

    const names = caller.pendingCalls.map((c) => c.tool_name);
    expect(names).toEqual([
      "get_team_members",
      "get_expenses",
      "get_budget_by_level",
    ]);
  });

  it("extracts mixed await and non-await calls", () => {
    const code = `
data = query_database(sql="SELECT * FROM orders")
result = await process_data(data["items"])
`;
    caller.executeCode(code);
    const names = caller.pendingCalls.map((c) => c.tool_name);
    expect(names).toHaveLength(2);
    expect(names).toContain("query_database");
    expect(names).toContain("process_data");
  });

  it("returns error for code with no tool calls", () => {
    const result = caller.executeCode("x = 1 + 2\ny = x * 3");
    expect(result.stderr).toBe("No tool calls found in code");
    expect(caller.hasPendingCalls).toBe(false);
  });

  it("resets previous pending calls on re-execution", () => {
    caller.executeCode("result = tool_a()");
    expect(caller.pendingCalls).toHaveLength(1);

    caller.executeCode("result = tool_b()");
    expect(caller.pendingCalls).toHaveLength(1);
    expect(caller.pendingCalls[0]!.tool_name).toBe("tool_b");
  });
});

// ---------------------------------------------------------------------------
// Tool call extraction
// ---------------------------------------------------------------------------

describe("Tool call extraction", () => {
  it("extracts with await", () => {
    const calls = caller.extractToolCalls(
      "result = await get_data(param='value')",
    );
    expect(calls).toHaveLength(1);
    expect(calls[0]!.tool_name).toBe("get_data");
  });

  it("extracts multiple calls", () => {
    const calls = caller.extractToolCalls(
      "a = foo()\nb = bar()\nc = baz()",
    );
    expect(calls).toHaveLength(3);
  });

  it("generates unique tool_use_ids", () => {
    const calls = caller.extractToolCalls("a()\nb()\nc()");
    const ids = calls.map((c) => c.tool_use_id);
    expect(new Set(ids).size).toBe(3);
  });

  it("handles empty code", () => {
    expect(caller.extractToolCalls("")).toEqual([]);
  });
});

// ---------------------------------------------------------------------------
// Result processing
// ---------------------------------------------------------------------------

describe("Result processing", () => {
  it("processes a single result", () => {
    const output = caller.processToolResults([
      { tool_name: "get_weather", result: "Sunny, 72F" },
    ]);
    const parsed = JSON.parse(output);
    expect(parsed.tool_name).toBe("get_weather");
    expect(parsed.result).toBe("Sunny, 72F");
  });

  it("processes multiple results", () => {
    const output = caller.processToolResults([
      { tool_name: "a", result: 1 },
      { tool_name: "b", result: 2 },
    ]);
    const lines = output.split("\n");
    expect(lines).toHaveLength(2);
  });

  it("processes empty results", () => {
    expect(caller.processToolResults([])).toBe("");
  });

  it("formats tool_result for API", () => {
    const formatted = caller.formatToolResultForApi(
      "toolu_abc123",
      "Success",
    );
    expect(formatted.type).toBe("tool_result");
    expect(formatted.tool_use_id).toBe("toolu_abc123");
    expect(formatted.content).toBe("Success");
  });
});

// ---------------------------------------------------------------------------
// Container management
// ---------------------------------------------------------------------------

describe("Container management", () => {
  it("starts with null container", () => {
    expect(caller.containerId).toBeNull();
  });

  it("sets and retrieves container ID", () => {
    caller.setContainer("container_xyz789");
    expect(caller.containerId).toBe("container_xyz789");
  });

  it("resets container and pending calls", () => {
    caller.setContainer("container_123");
    caller.executeCode("result = tool_a()");
    expect(caller.hasPendingCalls).toBe(true);

    caller.resetContainer();
    expect(caller.containerId).toBeNull();
    expect(caller.hasPendingCalls).toBe(false);
  });

  it("has no pending calls initially", () => {
    expect(caller.hasPendingCalls).toBe(false);
  });
});

// ---------------------------------------------------------------------------
// End-to-end workflows
// ---------------------------------------------------------------------------

describe("End-to-end workflows", () => {
  it("budget compliance workflow", () => {
    const code = `
team = await get_team_members("engineering")
levels = list(set(m["level"] for m in team))
budget_results = await get_budget_by_level(level)
expenses = await get_expenses(m["id"], "Q3")
print(json.dumps(exceeded))
`;
    caller.executeCode(code);
    const names = caller.pendingCalls.map((c) => c.tool_name);
    expect(names).toContain("get_team_members");
    expect(names).toContain("get_budget_by_level");
    expect(names).toContain("get_expenses");
  });

  it("conditional tool selection workflow", () => {
    const code = `
file_info = await get_file_info(path)
if file_info["size"] < 10000:
    content = await read_full_file(path)
else:
    content = await read_file_summary(path)
print(content)
`;
    caller.executeCode(code);
    const names = caller.pendingCalls.map((c) => c.tool_name);
    expect(names).toContain("get_file_info");
    expect(names).toContain("read_full_file");
    expect(names).toContain("read_file_summary");
  });

  it("batch processing of 5 regions", () => {
    const code = `
data_west = await query_database("SELECT * FROM sales WHERE region='West'")
data_east = await query_database("SELECT * FROM sales WHERE region='East'")
data_central = await query_database("SELECT * FROM sales WHERE region='Central'")
data_north = await query_database("SELECT * FROM sales WHERE region='North'")
data_south = await query_database("SELECT * FROM sales WHERE region='South'")
`;
    caller.executeCode(code);
    const names = caller.pendingCalls.map((c) => c.tool_name);
    expect(names).toHaveLength(5);
    expect(names.every((n) => n === "query_database")).toBe(true);
  });
});
