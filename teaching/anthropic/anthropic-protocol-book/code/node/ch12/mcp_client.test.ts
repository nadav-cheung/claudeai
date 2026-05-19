/**
 * Tests for Chapter 12: MCP Client (TypeScript).
 *
 * Tests the MCPClient by connecting to an MCPServer via
 * a subprocess running a standalone TypeScript server.
 */

import { describe, it, expect, beforeAll, afterAll } from "vitest";
import { MCPClient } from "./MCPClient";
import { writeFileSync, unlinkSync } from "node:fs";
import { resolve, dirname } from "node:path";
import { fileURLToPath } from "node:url";
import { tmpdir } from "node:os";
import { randomUUID } from "node:crypto";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

const __dirname = dirname(fileURLToPath(import.meta.url));
const ch12Dir = resolve(__dirname);

let serverScriptPath: string | null = null;

beforeAll(() => {
  // Write a standalone MCP server script that uses absolute imports
  serverScriptPath = resolve(tmpdir(), `mcp-test-server-${randomUUID()}.mjs`);

  writeFileSync(
    serverScriptPath,
    `
import { MCPServer } from '${ch12Dir}/MCPServer.ts';
const srv = new MCPServer("test-server", "1.0.0");
srv.registerTool({
  name: "echo",
  description: "Echo",
  inputSchema: { type: "object", properties: { msg: { type: "string" } }, required: ["msg"] },
  handler: async (args) => ({ content: [{ type: "text", text: String(args.msg) }], isError: false })
});
srv.registerTool({
  name: "add",
  description: "Add two numbers",
  inputSchema: { type: "object", properties: { a: { type: "integer" }, b: { type: "integer" } }, required: ["a", "b"] },
  handler: async (args) => ({ content: [{ type: "text", text: String(Number(args.a) + Number(args.b)) }], isError: false })
});
srv.registerTool({
  name: "get_info",
  description: "Server info",
  inputSchema: { type: "object", properties: {} },
  handler: async (_args) => ({ content: [{ type: "text", text: JSON.stringify({ language: "typescript", version: "1.0.0" }) }], isError: false })
});
srv.registerResource(
  { uri: "test://hello", name: "Hello", mimeType: "text/plain" },
  async () => "Hello from TypeScript MCP Server!"
);
await srv.runStdio();
`
  );
});

afterAll(() => {
  if (serverScriptPath) {
    try { unlinkSync(serverScriptPath); } catch {}
  }
});

async function createConnectedClient(): Promise<{ client: MCPClient; cleanup: () => void }> {
  const client = new MCPClient();
  await client.connectStdio("npx", ["tsx", serverScriptPath!]);
  return { client, cleanup: () => client.disconnect() };
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe("MCPClient Connection (TypeScript Server via stdio)", () => {
  it("connects to the TypeScript server and gets server info", async () => {
    const { client, cleanup } = await createConnectedClient();
    try {
      const info = client.getServerInfo();
      expect(info.name).toBe("test-server");
      expect(info.version).toBe("1.0.0");
    } finally {
      cleanup();
    }
  });

  it("lists tools", async () => {
    const { client, cleanup } = await createConnectedClient();
    try {
      const tools = await client.listTools();
      expect(tools.length).toBe(3);
      const names = tools.map((t) => t.name);
      expect(names).toContain("echo");
      expect(names).toContain("add");
    } finally {
      cleanup();
    }
  });

  it("calls echo tool", async () => {
    const { client, cleanup } = await createConnectedClient();
    try {
      const result = await client.callTool("echo", { msg: "hello from TS" });
      const content = result.content as Array<Record<string, unknown>>;
      expect(content[0]!.text).toBe("hello from TS");
    } finally {
      cleanup();
    }
  });

  it("calls add tool", async () => {
    const { client, cleanup } = await createConnectedClient();
    try {
      const result = await client.callTool("add", { a: 40, b: 2 });
      const content = result.content as Array<Record<string, unknown>>;
      expect(content[0]!.text).toBe("42");
    } finally {
      cleanup();
    }
  });

  it("calls get_info tool to verify server language", async () => {
    const { client, cleanup } = await createConnectedClient();
    try {
      const result = await client.callTool("get_info", {});
      const content = result.content as Array<Record<string, unknown>>;
      const data = JSON.parse(content[0]!.text as string);
      expect(data.language).toBe("typescript");
    } finally {
      cleanup();
    }
  });

  it("reads a resource", async () => {
    const { client, cleanup } = await createConnectedClient();
    try {
      const result = await client.readResource("test://hello");
      const contents = result.contents as Array<Record<string, unknown>>;
      expect(contents[0]!.text).toContain("TypeScript MCP Server");
    } finally {
      cleanup();
    }
  });

  it("pings successfully", async () => {
    const { client, cleanup } = await createConnectedClient();
    try {
      expect(await client.ping()).toBe(true);
    } finally {
      cleanup();
    }
  });
});
