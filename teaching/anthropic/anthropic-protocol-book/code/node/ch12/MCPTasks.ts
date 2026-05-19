/**
 * Chapter 12: MCP Tasks (SEP-1686) - TypeScript.
 *
 * Implements the MCP Tasks specification for asynchronous task execution.
 * Provides task submission, status polling, result retrieval, listing,
 * and cancellation. Designed to work with MCPClient.
 *
 * MCP Tasks Spec: modelcontextprotocol.io/specification/2025-11-25/basic/utilities/tasks
 * SEP-1686: modelcontextprotocol.io/seps/1686-tasks
 * SEP-2663: modelcontextprotocol.io/seps/2663-tasks-extension
 */

import type { MCPClient } from "./MCPClient";

// ────────────────────────────────────────────────────────────────
// Constants
// ────────────────────────────────────────────────────────────────

export const TASK_STATUS_WORKING = "working";
export const TASK_STATUS_INPUT_REQUIRED = "input_required";
export const TASK_STATUS_COMPLETED = "completed";
export const TASK_STATUS_FAILED = "failed";
export const TASK_STATUS_CANCELLED = "cancelled";

export const TERMINAL_STATUSES = new Set([
  TASK_STATUS_COMPLETED,
  TASK_STATUS_FAILED,
  TASK_STATUS_CANCELLED,
]);

export interface TaskStatus {
  taskId: string;
  status: string;
  statusMessage?: string;
  createdAt: string;
  lastUpdatedAt: string;
  ttl: number | null;
  pollInterval?: number;
}

export interface TaskResult {
  success: boolean;
  result?: Record<string, unknown>;
  error?: string;
}

// ────────────────────────────────────────────────────────────────
// MCPTask
// ────────────────────────────────────────────────────────────────

export class MCPTask {
  private client: MCPClient;
  private tasks = new Map<string, TaskStatus>();

  constructor(client: MCPClient) {
    this.client = client;
  }

  // ── Task submission ────────────────────────────────────

  async submitTask(
    toolName: string,
    args: Record<string, unknown>,
    ttl?: number
  ): Promise<string> {
    const params: Record<string, unknown> = {
      name: toolName,
      arguments: args,
      task: {} as Record<string, unknown>,
    };
    if (ttl !== undefined) {
      (params.task as Record<string, unknown>).ttl = ttl;
    }

    const response = (await this.client.sendRequest("tools/call", params)) as Record<string, unknown>;
    const taskData = response.task as Record<string, unknown> | undefined;

    if (!taskData || !taskData.taskId) {
      throw new Error(
        "Server did not return task data. Does the server support task-augmented tools/call?"
      );
    }

    const taskId = taskData.taskId as string;
    this.tasks.set(taskId, taskData as unknown as TaskStatus);
    return taskId;
  }

  // ── Status polling ─────────────────────────────────────

  async getTaskStatus(taskId: string): Promise<TaskStatus> {
    const result = (await this.client.sendRequest("tasks/get", {
      taskId,
    })) as TaskStatus;
    this.tasks.set(taskId, result);
    return result;
  }

  async waitForCompletion(
    taskId: string,
    timeout = 60.0,
    pollInterval?: number
  ): Promise<TaskResult> {
    const start = Date.now();
    const defaultInterval = 1.0;

    while (true) {
      const elapsed = (Date.now() - start) / 1000;
      if (elapsed >= timeout) {
        throw new Error(`Task ${taskId} did not complete within ${timeout}s`);
      }

      const status = await this.getTaskStatus(taskId);
      const currentStatus = status.status;

      if (TERMINAL_STATUSES.has(currentStatus)) {
        if (currentStatus === TASK_STATUS_COMPLETED) {
          const result = await this.getTaskResult(taskId);
          return { success: true, result: result as Record<string, unknown> };
        } else if (currentStatus === TASK_STATUS_FAILED) {
          return {
            success: false,
            error: status.statusMessage ?? "Task failed",
          };
        } else if (currentStatus === TASK_STATUS_CANCELLED) {
          return { success: false, error: "Task was cancelled" };
        }
      }

      let interval = pollInterval ?? status.pollInterval ?? defaultInterval;
      // Convert ms to seconds if value is large
      if (interval > 1) interval = interval / 1000;
      interval = Math.min(interval, timeout - elapsed);

      await new Promise((resolve) => setTimeout(resolve, interval * 1000));
    }
  }

  // ── Result retrieval ───────────────────────────────────

  async getTaskResult(taskId: string): Promise<Record<string, unknown>> {
    return (await this.client.sendRequest("tasks/result", {
      taskId,
    })) as Record<string, unknown>;
  }

  // ── Task listing ───────────────────────────────────────

  async listTasks(cursor?: string): Promise<{ tasks: TaskStatus[]; nextCursor: string | null }> {
    const params: Record<string, unknown> = {};
    if (cursor) params.cursor = cursor;
    return (await this.client.sendRequest("tasks/list", params)) as {
      tasks: TaskStatus[];
      nextCursor: string | null;
    };
  }

  // ── Task cancellation ──────────────────────────────────

  async cancelTask(taskId: string): Promise<TaskStatus> {
    return (await this.client.sendRequest("tasks/cancel", {
      taskId,
    })) as TaskStatus;
  }

  // ── High-level helpers ─────────────────────────────────

  async submitAndWait(
    toolName: string,
    args: Record<string, unknown>,
    options?: { ttl?: number; timeout?: number }
  ): Promise<TaskResult> {
    const taskId = await this.submitTask(toolName, args, options?.ttl);
    return await this.waitForCompletion(taskId, options?.timeout ?? 60.0);
  }

  async pollUntil(
    taskId: string,
    predicate: (status: TaskStatus) => boolean,
    timeout = 60.0,
    pollInterval = 1.0
  ): Promise<TaskStatus> {
    const start = Date.now();

    while (true) {
      const elapsed = (Date.now() - start) / 1000;
      if (elapsed >= timeout) {
        throw new Error(`Polling timeout after ${timeout}s`);
      }

      const status = await this.getTaskStatus(taskId);
      if (predicate(status)) {
        return status;
      }

      await new Promise((resolve) => setTimeout(resolve, pollInterval * 1000));
    }
  }
}
