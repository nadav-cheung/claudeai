/**
 * Tests for Chapter 12: MCP Server (TypeScript).
 *
 * Tests the MCPServer JSON-RPC handling, tool/resource/prompt
 * registration, capability negotiation, and task lifecycle.
 */

import { describe, it, expect, beforeEach } from "vitest";
import { MCPServer } from "./MCPServer";
import type { ToolDefinition, ResourceDefinition, PromptDefinition } from "./MCPServer";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function makeServer(): MCPServer {
  const srv = new MCPServer("test-server", "1.0.0");

  srv.registerTool({
    name: "echo",
    description: "Echo back the input",
    inputSchema: {
      type: "object",
      properties: { message: { type: "string" } },
      required: ["message"],
    },
    handler: async (args) => {
      return { content: [{ type: "text", text: String(args.message) }], isError: false };
    },
  });

  srv.registerTool({
    name: "add",
    description: "Add two numbers",
    inputSchema: {
      type: "object",
      properties: { a: { type: "integer" }, b: { type: "integer" } },
      required: ["a", "b"],
    },
    handler: async (args) => {
      return { content: [{ type: "text", text: String(Number(args.a) + Number(args.b)) }], isError: false };
    },
  });

  srv.registerTool({
    name: "failing_tool",
    description: "Always fails",
    inputSchema: { type: "object", properties: {} },
    handler: async (_args) => {
      throw new Error("intentional failure");
    },
  });

  srv.registerTool({
    name: "long_task",
    description: "A long-running task",
    inputSchema: { type: "object", properties: { duration: { type: "number" } } },
    handler: async (args) => ({
      content: [{ type: "text", text: `Done after ${args.duration ?? 0}s` }],
      isError: false,
    }),
    execution_taskSupport: "optional",
  });

  srv.registerResource(
    { uri: "test://config/server-info", name: "Server Info", mimeType: "application/json" },
    async () => JSON.stringify({ name: "test-server", version: "1.0.0" })
  );

  srv.registerResource({ uri: "test://data/empty", name: "Empty Resource", mimeType: "text/plain" });

  srv.registerPrompt(
    {
      name: "greeting",
      description: "Generate a greeting",
      arguments: [{ name: "name", description: "Name to greet", required: true }],
    },
    async (args) => `Write a warm greeting for ${args.name}.`
  );

  return srv;
}

async function initializeServer(srv: MCPServer): Promise<void> {
  await srv.handleMessage(
    JSON.stringify({
      jsonrpc: "2.0",
      id: 1,
      method: "initialize",
      params: {
        protocolVersion: "2025-11-25",
        capabilities: {},
        clientInfo: { name: "test-client", version: "1.0.0" },
      },
    })
  );
  await srv.handleMessage(
    JSON.stringify({ jsonrpc: "2.0", method: "notifications/initialized", params: {} })
  );
}

async function send(srv: MCPServer, method: string, params: Record<string, unknown>, id = 100): Promise<unknown> {
  const raw = await srv.handleMessage(
    JSON.stringify({ jsonrpc: "2.0", id, method, params })
  );
  if (raw === null) throw new Error(`No response for ${method}`);
  const resp = JSON.parse(raw);
  if (resp.error) throw new Error(resp.error.message);
  return resp.result;
}

function setupServer(): MCPServer {
  const srv = makeServer();
  // Initialize synchronously by using the sync handleMessage
  return srv;
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe("MCPServer Initialization", () => {
  it("returns capabilities and server info on initialize", async () => {
    const srv = new MCPServer("my-srv", "2.0.0");
    const raw = await srv.handleMessage(
      JSON.stringify({
        jsonrpc: "2.0",
        id: 1,
        method: "initialize",
        params: {
          protocolVersion: "2025-11-25",
          capabilities: {},
          clientInfo: { name: "c", version: "1.0" },
        },
      })
    );
    const resp = JSON.parse(raw!);
    expect(resp.id).toBe(1);
    expect(resp.result.protocolVersion).toBe("2025-11-25");
    expect(resp.result.serverInfo.name).toBe("my-srv");
    expect(resp.result.serverInfo.version).toBe("2.0.0");
  });

  it("rejects non-initialize requests before initialized", async () => {
    const srv = new MCPServer("test", "1.0");
    const raw = await srv.handleMessage(
      JSON.stringify({ jsonrpc: "2.0", id: 2, method: "tools/list", params: {} })
    );
    const resp = JSON.parse(raw!);
    expect(resp.error).toBeDefined();
    expect(resp.error.code).toBe(-32000);
  });

  it("accepts requests after initialized notification", async () => {
    const srv = new MCPServer("test", "1.0");
    await srv.handleMessage(
      JSON.stringify({
        jsonrpc: "2.0",
        id: 1,
        method: "initialize",
        params: {
          protocolVersion: "2025-11-25",
          capabilities: {},
          clientInfo: { name: "c", version: "1.0" },
        },
      })
    );
    await srv.handleMessage(
      JSON.stringify({ jsonrpc: "2.0", method: "notifications/initialized", params: {} })
    );
    const raw = await srv.handleMessage(
      JSON.stringify({ jsonrpc: "2.0", id: 2, method: "tools/list", params: {} })
    );
    const resp = JSON.parse(raw!);
    expect(resp.result).toBeDefined();
  });
});

describe("MCPServer Tools", () => {
  let srv: MCPServer;

  beforeEach(async () => {
    srv = makeServer();
    await initializeServer(srv);
  });

  it("lists all registered tools", async () => {
    const result = await send(srv, "tools/list", {}, 10) as Record<string, unknown>;
    const tools = result.tools as Array<Record<string, unknown>>;
    const names = tools.map((t) => t.name);
    expect(names).toContain("echo");
    expect(names).toContain("add");
    expect(names).toContain("failing_tool");
    expect(names).toContain("long_task");
  });

  it("calls echo tool", async () => {
    const result = (await send(srv, "tools/call", { name: "echo", arguments: { message: "hello" } }, 11)) as Record<string, unknown>;
    expect(result.isError).toBe(false);
    const content = result.content as Array<Record<string, unknown>>;
    expect(content[0]!.text).toBe("hello");
  });

  it("calls add tool", async () => {
    const result = (await send(srv, "tools/call", { name: "add", arguments: { a: 10, b: 32 } }, 12)) as Record<string, unknown>;
    const content = result.content as Array<Record<string, unknown>>;
    expect(content[0]!.text).toBe("42");
  });

  it("returns error for unknown tool", async () => {
    const raw = await srv.handleMessage(
      JSON.stringify({ jsonrpc: "2.0", id: 13, method: "tools/call", params: { name: "nonexistent", arguments: {} } })
    );
    const resp = JSON.parse(raw!);
    expect(resp.error).toBeDefined();
    expect(resp.error.code).toBe(-32602);
  });

  it("returns isError true for failing tools", async () => {
    const result = (await send(srv, "tools/call", { name: "failing_tool", arguments: {} }, 14)) as Record<string, unknown>;
    expect(result.isError).toBe(true);
  });
});

describe("MCPServer Resources", () => {
  let srv: MCPServer;

  beforeEach(async () => {
    srv = makeServer();
    await initializeServer(srv);
  });

  it("lists resources", async () => {
    const result = (await send(srv, "resources/list", {}, 20)) as Record<string, unknown>;
    const resources = result.resources as Array<Record<string, unknown>>;
    const uris = resources.map((r) => r.uri);
    expect(uris).toContain("test://config/server-info");
    expect(uris).toContain("test://data/empty");
  });

  it("reads resource with reader", async () => {
    const result = (await send(srv, "resources/read", { uri: "test://config/server-info" }, 21)) as Record<string, unknown>;
    const contents = result.contents as Array<Record<string, unknown>>;
    expect(contents).toHaveLength(1);
    expect(contents[0]!.text).toContain("test-server");
  });

  it("errors on unknown resource", async () => {
    const raw = await srv.handleMessage(
      JSON.stringify({ jsonrpc: "2.0", id: 23, method: "resources/read", params: { uri: "nonexistent://uri" } })
    );
    const resp = JSON.parse(raw!);
    expect(resp.error.code).toBe(-32002);
  });
});

describe("MCPServer Prompts", () => {
  let srv: MCPServer;

  beforeEach(async () => {
    srv = makeServer();
    await initializeServer(srv);
  });

  it("lists prompts", async () => {
    const result = (await send(srv, "prompts/list", {}, 30)) as Record<string, unknown>;
    const prompts = result.prompts as Array<Record<string, unknown>>;
    const names = prompts.map((p) => p.name);
    expect(names).toContain("greeting");
  });

  it("gets prompt", async () => {
    const result = (await send(srv, "prompts/get", { name: "greeting", arguments: { name: "Alice" } }, 31)) as Record<string, unknown>;
    const messages = result.messages as Array<Record<string, unknown>>;
    const content = messages[0]!.content as Record<string, unknown>;
    expect(content.text).toContain("Alice");
  });
});

describe("MCPServer Tasks", () => {
  let srv: MCPServer;

  beforeEach(async () => {
    srv = makeServer();
    await initializeServer(srv);
  });

  it("creates task via tools/call with task param", async () => {
    const result = (await send(
      srv,
      "tools/call",
      { name: "long_task", arguments: { duration: 1 }, task: { ttl: 60000 } },
      40
    )) as Record<string, unknown>;
    const task = result.task as Record<string, unknown>;
    expect(task).toBeDefined();
    expect(task.status).toBe("working");
    expect(task.taskId).toBeDefined();
  });

  it("tasks/get returns task status", async () => {
    const createResult = (await send(
      srv,
      "tools/call",
      { name: "long_task", arguments: { duration: 0 }, task: { ttl: 60000 } },
      41
    )) as Record<string, unknown>;
    const taskId = (createResult.task as Record<string, unknown>).taskId as string;

    // Wait for completion
    await new Promise((r) => setTimeout(r, 200));

    const status = (await send(srv, "tasks/get", { taskId }, 42)) as Record<string, unknown>;
    expect(status.status).toBe("completed");
  });

  it("tasks/cancel handles race with completion", async () => {
    const createResult = (await send(
      srv,
      "tools/call",
      { name: "long_task", arguments: { duration: 0 }, task: { ttl: 60000 } },
      43
    )) as Record<string, unknown>;
    const taskId = (createResult.task as Record<string, unknown>).taskId as string;

    // For fast tasks, cancel may fail because the task completes first.
    // Both outcomes are valid - test that the response is either cancelled or error.
    try {
      const cancelled = (await send(srv, "tasks/cancel", { taskId }, 44)) as Record<string, unknown>;
      // If we got here, cancel succeeded
      expect(cancelled.status).toBe("cancelled");
    } catch {
      // Cancel failed (task already terminal), verify it's terminal
      const status = (await send(srv, "tasks/get", { taskId }, 45)) as Record<string, unknown>;
      expect(["completed", "failed", "cancelled"]).toContain(status.status);
    }
  });

  it("cancel on terminal task fails", async () => {
    const createResult = (await send(
      srv,
      "tools/call",
      { name: "long_task", arguments: { duration: 0 }, task: { ttl: 60000 } },
      45
    )) as Record<string, unknown>;
    const taskId = (createResult.task as Record<string, unknown>).taskId as string;

    // Wait for completion
    await new Promise((r) => setTimeout(r, 200));

    const raw = await srv.handleMessage(
      JSON.stringify({ jsonrpc: "2.0", id: 46, method: "tasks/cancel", params: { taskId } })
    );
    const resp = JSON.parse(raw!);
    expect(resp.error).toBeDefined();
  });

  it("tasks/result includes related-task meta", async () => {
    const createResult = (await send(
      srv,
      "tools/call",
      { name: "long_task", arguments: { duration: 0 }, task: { ttl: 60000 } },
      47
    )) as Record<string, unknown>;
    const taskId = (createResult.task as Record<string, unknown>).taskId as string;

    await new Promise((r) => setTimeout(r, 200));

    const result = (await send(srv, "tasks/result", { taskId }, 48)) as Record<string, unknown>;
    expect(result._meta).toBeDefined();
  });

  it("tasks/list returns all tasks", async () => {
    await send(
      srv,
      "tools/call",
      { name: "long_task", arguments: { duration: 0 }, task: { ttl: 60000 } },
      49
    );
    await new Promise((r) => setTimeout(r, 50));

    const list = (await send(srv, "tasks/list", {}, 50)) as Record<string, unknown>;
    const tasks = list.tasks as Array<Record<string, unknown>>;
    expect(tasks.length).toBeGreaterThanOrEqual(1);
  });
});

describe("MCPServer Error Handling", () => {
  let srv: MCPServer;

  beforeEach(async () => {
    srv = makeServer();
    await initializeServer(srv);
  });

  it("handles parse error", async () => {
    const raw = await srv.handleMessage("not valid json{{{");
    const resp = JSON.parse(raw!);
    expect(resp.error.code).toBe(-32700);
  });

  it("handles method not found", async () => {
    const raw = await srv.handleMessage(
      JSON.stringify({ jsonrpc: "2.0", id: 60, method: "nonexistent/method", params: {} })
    );
    const resp = JSON.parse(raw!);
    expect(resp.error.code).toBe(-32601);
  });

  it("handles ping", async () => {
    const result = await send(srv, "ping", {}, 61);
    expect(result).toEqual({});
  });
});
