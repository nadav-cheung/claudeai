/**
 * Tests for Chapter 12: MCP Tasks (TypeScript).
 *
 * Tests the MCPTask class for task submission, status polling,
 * result retrieval, and cancellation. Connects to a TypeScript
 * MCPServer via subprocess (tsx).
 */

import { describe, it, expect, beforeAll, afterAll } from "vitest";
import { MCPClient } from "./MCPClient";
import { MCPTask, TASK_STATUS_COMPLETED, TASK_STATUS_CANCELLED, TERMINAL_STATUSES } from "./MCPTasks";
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
  serverScriptPath = resolve(tmpdir(), `mcp-task-test-server-${randomUUID()}.mjs`);

  writeFileSync(
    serverScriptPath,
    `
import { MCPServer } from '${ch12Dir}/MCPServer.ts';
const srv = new MCPServer("task-server", "1.0.0");
srv.registerTool({
  name: "quick_task",
  description: "Completes immediately",
  inputSchema: { type: "object", properties: {} },
  handler: async () => ({ content: [{ type: "text", text: "quick done" }], isError: false }),
  execution_taskSupport: "optional"
});
srv.registerTool({
  name: "slow_task",
  description: "Takes a moment",
  inputSchema: { type: "object", properties: { delay: { type: "number" } } },
  handler: async (args) => {
    const d = Number(args.delay) || 0;
    await new Promise(r => setTimeout(r, d * 1000));
    return { content: [{ type: "text", text: "slow done" }], isError: false };
  },
  execution_taskSupport: "optional"
});
await srv.runStdio();
`
  );
});

afterAll(() => {
  if (serverScriptPath) {
    try { unlinkSync(serverScriptPath); } catch {}
  }
});

async function createTaskManager(): Promise<{ client: MCPClient; taskMgr: MCPTask; cleanup: () => void }> {
  const client = new MCPClient();
  await client.connectStdio("npx", ["tsx", serverScriptPath!]);
  const taskMgr = new MCPTask(client);
  return { client, taskMgr, cleanup: () => client.disconnect() };
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe("MCPTask Submission", () => {
  it("submits a task and returns a task ID", async () => {
    const { taskMgr, cleanup } = await createTaskManager();
    try {
      const taskId = await taskMgr.submitTask("quick_task", {});
      expect(typeof taskId).toBe("string");
      expect(taskId.length).toBeGreaterThan(0);
    } finally {
      cleanup();
    }
  });

  it("submits a task with TTL", async () => {
    const { taskMgr, cleanup } = await createTaskManager();
    try {
      const taskId = await taskMgr.submitTask("quick_task", {}, 30000);
      expect(typeof taskId).toBe("string");
    } finally {
      cleanup();
    }
  });

  it("can get task status after submission", async () => {
    const { taskMgr, cleanup } = await createTaskManager();
    try {
      const taskId = await taskMgr.submitTask("quick_task", {});
      const status = await taskMgr.getTaskStatus(taskId);
      expect(status.taskId).toBe(taskId);
      expect(status.status).toBeDefined();
    } finally {
      cleanup();
    }
  });
});

describe("MCPTask Polling", () => {
  it("task eventually reaches completed status", async () => {
    const { taskMgr, cleanup } = await createTaskManager();
    try {
      const taskId = await taskMgr.submitTask("quick_task", {});

      for (let i = 0; i < 50; i++) {
        const status = await taskMgr.getTaskStatus(taskId);
        if (status.status === TASK_STATUS_COMPLETED) break;
        await new Promise((r) => setTimeout(r, 100));
      }

      const final = await taskMgr.getTaskStatus(taskId);
      expect(final.status).toBe(TASK_STATUS_COMPLETED);
    } finally {
      cleanup();
    }
  });

  it("task status includes timestamps", async () => {
    const { taskMgr, cleanup } = await createTaskManager();
    try {
      const taskId = await taskMgr.submitTask("quick_task", {});
      const status = await taskMgr.getTaskStatus(taskId);
      expect(status.createdAt).toBeDefined();
      expect(status.lastUpdatedAt).toBeDefined();
    } finally {
      cleanup();
    }
  });
});

describe("MCPTask waitForCompletion", () => {
  it("waits for completion and returns success", async () => {
    const { taskMgr, cleanup } = await createTaskManager();
    try {
      const taskId = await taskMgr.submitTask("quick_task", {});
      const result = await taskMgr.waitForCompletion(taskId, 10);
      expect(result.success).toBe(true);
    } finally {
      cleanup();
    }
  });

  it("submitAndWait is a convenience wrapper", async () => {
    const { taskMgr, cleanup } = await createTaskManager();
    try {
      const result = await taskMgr.submitAndWait("quick_task", {});
      expect(result.success).toBe(true);
    } finally {
      cleanup();
    }
  });
});

describe("MCPTask Result Retrieval", () => {
  it("getTaskResult returns content after completion", async () => {
    const { taskMgr, cleanup } = await createTaskManager();
    try {
      const taskId = await taskMgr.submitTask("quick_task", {});
      await taskMgr.waitForCompletion(taskId, 10);
      const result = await taskMgr.getTaskResult(taskId);
      expect(result.content).toBeDefined();
    } finally {
      cleanup();
    }
  });
});

describe("MCPTask Cancellation", () => {
  it("cancelling a completed task throws an error", async () => {
    const { taskMgr, cleanup } = await createTaskManager();
    try {
      const taskId = await taskMgr.submitTask("quick_task", {});
      await taskMgr.waitForCompletion(taskId, 5);
      await expect(taskMgr.cancelTask(taskId)).rejects.toThrow(/terminal/);
    } finally {
      cleanup();
    }
  });
});

describe("MCPTask Listing", () => {
  it("lists all tasks", async () => {
    const { taskMgr, cleanup } = await createTaskManager();
    try {
      await taskMgr.submitTask("quick_task", {});
      await new Promise((r) => setTimeout(r, 200));
      const result = await taskMgr.listTasks();
      expect(result.tasks.length).toBeGreaterThanOrEqual(1);
    } finally {
      cleanup();
    }
  });
});

describe("Task Constants", () => {
  it("correct terminal statuses", () => {
    expect(TERMINAL_STATUSES.has(TASK_STATUS_COMPLETED)).toBe(true);
    expect(TERMINAL_STATUSES.has(TASK_STATUS_CANCELLED)).toBe(true);
    expect(TERMINAL_STATUSES.has("working")).toBe(false);
  });
});
