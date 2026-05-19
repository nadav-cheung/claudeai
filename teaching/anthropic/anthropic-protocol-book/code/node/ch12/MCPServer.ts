/**
 * Chapter 12: MCP Server (TypeScript).
 *
 * Protocol-level implementation of an MCP-compliant server supporting
 * tool registration, resource exposure, prompt templates, and both
 * stdio and HTTP transports. Implements JSON-RPC 2.0 message handling,
 * capability negotiation, and task lifecycle.
 *
 * MCP Specification: modelcontextprotocol.io/specification/2025-11-25
 */

import { createInterface } from "node:readline";
import type { Interface } from "node:readline";

// ────────────────────────────────────────────────────────────────
// Data types
// ────────────────────────────────────────────────────────────────

export interface ContentBlock {
  type: "text" | "image" | "resource";
  text?: string;
  data?: string;
  mimeType?: string;
  uri?: string;
}

export interface ToolDefinition {
  name: string;
  description: string;
  inputSchema: Record<string, unknown>;
  handler: (args: Record<string, unknown>) => Promise<ToolResult> | ToolResult;
  execution_taskSupport?: "required" | "optional" | "forbidden";
}

export interface ToolResult {
  content: ContentBlock[];
  isError: boolean;
  _meta?: Record<string, unknown>;
}

export interface ResourceDefinition {
  uri: string;
  name: string;
  description?: string;
  mimeType?: string;
}

export interface PromptDefinition {
  name: string;
  description?: string;
  arguments?: Array<{ name: string; description?: string; required?: boolean }>;
}

export interface Task {
  taskId: string;
  status: "working" | "input_required" | "completed" | "failed" | "cancelled";
  statusMessage?: string;
  createdAt: string;
  lastUpdatedAt: string;
  ttl: number | null;
  pollInterval: number;
}

interface JSONRPCRequest {
  jsonrpc: "2.0";
  id?: number | string;
  method: string;
  params?: Record<string, unknown>;
}

interface JSONRPCResponse {
  jsonrpc: "2.0";
  id: number | string;
  result?: unknown;
  error?: { code: number; message: string; data?: unknown };
}

interface ToolHandler {
  definition: ToolDefinition;
  handler: (args: Record<string, unknown>) => Promise<ToolResult> | ToolResult;
}

interface ResourceHandler {
  definition: ResourceDefinition;
  reader?: (uri: string) => Promise<string> | string;
}

interface PromptHandler {
  definition: PromptDefinition;
  handler?: (args: Record<string, unknown>) => Promise<unknown> | unknown;
}

// ────────────────────────────────────────────────────────────────
// MCPServer
// ────────────────────────────────────────────────────────────────

export class MCPServer {
  static readonly PROTOCOL_VERSION = "2025-11-25";

  readonly name: string;
  readonly version: string;

  private tools = new Map<string, ToolHandler>();
  private resources = new Map<string, ResourceHandler>();
  private prompts = new Map<string, PromptHandler>();
  private tasks = new Map<string, Task>();
  private taskCallbacks = new Map<string, { tool: ToolHandler; arguments: Record<string, unknown> }>();
  private initialized = false;
  private clientInfo: Record<string, unknown> = {};

  constructor(name: string, version: string) {
    this.name = name;
    this.version = version;
  }

  // ── Registration ────────────────────────────────────────

  registerTool(definition: ToolDefinition): void {
    this.tools.set(definition.name, { definition, handler: definition.handler });
  }

  registerResource(definition: ResourceDefinition, reader?: (uri: string) => Promise<string> | string): void {
    this.resources.set(definition.uri, { definition, reader });
  }

  registerPrompt(definition: PromptDefinition, handler?: (args: Record<string, unknown>) => Promise<unknown> | unknown): void {
    this.prompts.set(definition.name, { definition, handler });
  }

  // ── Capabilities ────────────────────────────────────────

  buildCapabilities(): Record<string, unknown> {
    const caps: Record<string, unknown> = {};
    if (this.tools.size > 0) {
      caps.tools = { listChanged: false };
    }
    if (this.resources.size > 0) {
      caps.resources = { subscribe: false, listChanged: false };
    }
    if (this.prompts.size > 0) {
      caps.prompts = { listChanged: false };
    }
    caps.tasks = {
      list: {},
      cancel: {},
      requests: { tools: { call: {} } },
    };
    return caps;
  }

  // ── JSON-RPC handling ───────────────────────────────────

  private makeResponse(id: number | string, result: unknown): JSONRPCResponse {
    return { jsonrpc: "2.0", id, result };
  }

  private makeError(id: number | string, code: number, message: string, data?: unknown): JSONRPCResponse {
    return { jsonrpc: "2.0", id, error: { code, message, ...(data !== undefined ? { data } : {}) } };
  }

  async handleMessage(raw: string): Promise<string | null> {
    let msg: JSONRPCRequest;
    try {
      msg = JSON.parse(raw);
    } catch {
      return JSON.stringify(this.makeError(0, -32700, "Parse error"));
    }

    const { method, id, params = {} } = msg;
    const msgId = id ?? 0;

    // Handle initialize and initialized notification (must work before initialized flag)
    if (method === "initialize") {
      return this.handleInitialize(params, id ?? 0);
    }
    if (method === "notifications/initialized") {
      return this.handleInitialized(params, id ?? 0);
    }

    // Block other requests until initialized
    if (!this.initialized && method) {
      if (id !== undefined) {
        return JSON.stringify(this.makeError(msgId, -32000, "Server not initialized"));
      }
      return null;
    }

    // Dispatch by method
    const handlers: Record<string, (p: Record<string, unknown>, id: number | string) => Promise<string | null>> = {
      "notifications/initialized": this.handleInitialized.bind(this),
      "tools/list": this.handleToolsList.bind(this),
      "tools/call": this.handleToolsCall.bind(this),
      "resources/list": this.handleResourcesList.bind(this),
      "resources/read": this.handleResourcesRead.bind(this),
      "prompts/list": this.handlePromptsList.bind(this),
      "prompts/get": this.handlePromptsGet.bind(this),
      "tasks/get": this.handleTasksGet.bind(this),
      "tasks/result": this.handleTasksResult.bind(this),
      "tasks/list": this.handleTasksList.bind(this),
      "tasks/cancel": this.handleTasksCancel.bind(this),
      "ping": this.handlePing.bind(this),
    };

    const handler = handlers[method];
    if (!handler) {
      if (id !== undefined) {
        return JSON.stringify(this.makeError(msgId, -32601, `Method not found: ${method}`));
      }
      return null;
    }

    return handler(params, msgId);
  }

  // ── Lifecycle ────────────────────────────────────────────

  private async handleInitialize(params: Record<string, unknown>, id: number | string): Promise<string> {
    this.clientInfo = (params.clientInfo as Record<string, unknown>) ?? {};
    return JSON.stringify(
      this.makeResponse(id, {
        protocolVersion: MCPServer.PROTOCOL_VERSION,
        capabilities: this.buildCapabilities(),
        serverInfo: { name: this.name, version: this.version },
      })
    );
  }

  private async handleInitialized(_params: Record<string, unknown>, _id: number | string): Promise<null> {
    this.initialized = true;
    return null;
  }

  private async handlePing(_params: Record<string, unknown>, id: number | string): Promise<string> {
    return JSON.stringify(this.makeResponse(id, {}));
  }

  // ── Tools ────────────────────────────────────────────────

  private async handleToolsList(_params: Record<string, unknown>, id: number | string): Promise<string> {
    const tools = Array.from(this.tools.values()).map((t) => {
      const d: Record<string, unknown> = {
        name: t.definition.name,
        description: t.definition.description,
        inputSchema: t.definition.inputSchema,
      };
      if (t.definition.execution_taskSupport) {
        d.execution = { taskSupport: t.definition.execution_taskSupport };
      }
      return d;
    });
    return JSON.stringify(this.makeResponse(id, { tools }));
  }

  private async handleToolsCall(params: Record<string, unknown>, id: number | string): Promise<string | null> {
    const toolName = params.name as string;
    const arguments_ = (params.arguments as Record<string, unknown>) ?? {};
    const taskParams = params.task as Record<string, unknown> | undefined;

    const tool = this.tools.get(toolName);
    if (!tool) {
      return JSON.stringify(this.makeError(id, -32602, `Unknown tool: ${toolName}`));
    }

    // Task augmentation
    if (taskParams) {
      return this.createTask(id, tool, arguments_, taskParams);
    }

    // Synchronous call
    try {
      const result = await tool.handler(arguments_);
      if (result.content) {
        return JSON.stringify(this.makeResponse(id, result));
      }
      const text = typeof result === "string" ? result : String(result);
      return JSON.stringify(
        this.makeResponse(id, {
          content: [{ type: "text", text }],
          isError: false,
        })
      );
    } catch (exc: unknown) {
      return JSON.stringify(
        this.makeResponse(id, {
          content: [{ type: "text", text: String(exc) }],
          isError: true,
        })
      );
    }
  }

  private async createTask(
    id: number | string,
    tool: ToolHandler,
    args: Record<string, unknown>,
    taskParams: Record<string, unknown>
  ): Promise<string> {
    const taskId = crypto.randomUUID();
    const now = new Date().toISOString();
    const ttl = (taskParams.ttl as number) ?? 60000;

    const task: Task = {
      taskId,
      status: "working",
      statusMessage: "Task accepted.",
      createdAt: now,
      lastUpdatedAt: now,
      ttl,
      pollInterval: 3000,
    };
    this.tasks.set(taskId, task);
    this.taskCallbacks.set(taskId, { tool, arguments: args });

    // Execute in background
    this.executeTaskBackground(taskId);

    return JSON.stringify(this.makeResponse(id, { task }));
  }

  private executeTaskBackground(taskId: string): void {
    const task = this.tasks.get(taskId);
    const cb = this.taskCallbacks.get(taskId);
    if (!task || !cb) return;

    Promise.resolve()
      .then(() => cb.tool.handler(cb.arguments))
      .then((result) => {
        task.status = "completed";
        task.statusMessage = "Task completed successfully.";
        task.lastUpdatedAt = new Date().toISOString();
      })
      .catch((exc: unknown) => {
        task.status = "failed";
        task.statusMessage = String(exc);
        task.lastUpdatedAt = new Date().toISOString();
      });
  }

  // ── Resources ────────────────────────────────────────────

  private async handleResourcesList(_params: Record<string, unknown>, id: number | string): Promise<string> {
    const resources = Array.from(this.resources.values()).map((r) => ({
      uri: r.definition.uri,
      name: r.definition.name,
      description: r.definition.description ?? "",
      mimeType: r.definition.mimeType ?? "text/plain",
    }));
    return JSON.stringify(this.makeResponse(id, { resources }));
  }

  private async handleResourcesRead(params: Record<string, unknown>, id: number | string): Promise<string> {
    const uri = params.uri as string;
    const resource = this.resources.get(uri);
    if (!resource) {
      return JSON.stringify(this.makeError(id, -32002, `Unknown resource: ${uri}`));
    }

    try {
      const text = resource.reader ? await resource.reader(uri) : `Resource at ${uri}`;
      return JSON.stringify(
        this.makeResponse(id, {
          contents: [
            {
              uri,
              mimeType: resource.definition.mimeType ?? "text/plain",
              text: String(text),
            },
          ],
        })
      );
    } catch (exc: unknown) {
      return JSON.stringify(this.makeError(id, -32603, String(exc)));
    }
  }

  // ── Prompts ──────────────────────────────────────────────

  private async handlePromptsList(_params: Record<string, unknown>, id: number | string): Promise<string> {
    const prompts = Array.from(this.prompts.values()).map((p) => ({
      name: p.definition.name,
      description: p.definition.description ?? "",
      ...(p.definition.arguments ? { arguments: p.definition.arguments } : {}),
    }));
    return JSON.stringify(this.makeResponse(id, { prompts }));
  }

  private async handlePromptsGet(params: Record<string, unknown>, id: number | string): Promise<string> {
    const promptName = params.name as string;
    const arguments_ = (params.arguments as Record<string, unknown>) ?? {};
    const prompt = this.prompts.get(promptName);

    if (!prompt) {
      return JSON.stringify(this.makeError(id, -32602, `Unknown prompt: ${promptName}`));
    }

    try {
      if (prompt.handler) {
        const result = await prompt.handler(arguments_);
        if (typeof result === "object" && result !== null && "messages" in result) {
          return JSON.stringify(this.makeResponse(id, result));
        }
        return JSON.stringify(
          this.makeResponse(id, {
            description: prompt.definition.description ?? "",
            messages: [{ role: "user", content: { type: "text", text: String(result) } }],
          })
        );
      }

      return JSON.stringify(
        this.makeResponse(id, {
          description: prompt.definition.description ?? "",
          messages: [{ role: "user", content: { type: "text", text: `Prompt: ${promptName}` } }],
        })
      );
    } catch (exc: unknown) {
      return JSON.stringify(this.makeError(id, -32603, String(exc)));
    }
  }

  // ── Tasks ────────────────────────────────────────────────

  private async handleTasksGet(params: Record<string, unknown>, id: number | string): Promise<string | null> {
    const taskId = params.taskId as string;
    const task = this.tasks.get(taskId);
    if (!task) {
      return JSON.stringify(this.makeError(id, -32602, `Task not found: ${taskId}`));
    }
    return JSON.stringify(this.makeResponse(id, task));
  }

  private async handleTasksResult(params: Record<string, unknown>, id: number | string): Promise<string> {
    const taskId = params.taskId as string;
    const task = this.tasks.get(taskId);
    if (!task) {
      return JSON.stringify(this.makeError(id, -32602, `Task not found: ${taskId}`));
    }
    // Block until terminal (simplified - polls internally)
    while (!this.isTerminal(task.status)) {
      await new Promise((resolve) => setTimeout(resolve, 100));
    }
    // Return a placeholder result; in production this would be the actual tool result
    return JSON.stringify(
      this.makeResponse(id, {
        content: [{ type: "text", text: `Task ${taskId} completed with status ${task.status}` }],
        isError: task.status === "failed",
        _meta: {
          "io.modelcontextprotocol/related-task": { taskId },
        },
      })
    );
  }

  private async handleTasksList(_params: Record<string, unknown>, id: number | string): Promise<string> {
    const tasks = Array.from(this.tasks.values());
    return JSON.stringify(this.makeResponse(id, { tasks, nextCursor: null }));
  }

  private async handleTasksCancel(params: Record<string, unknown>, id: number | string): Promise<string | null> {
    const taskId = params.taskId as string;
    const task = this.tasks.get(taskId);
    if (!task) {
      return JSON.stringify(this.makeError(id, -32602, `Task not found: ${taskId}`));
    }
    if (this.isTerminal(task.status)) {
      return JSON.stringify(
        this.makeError(id, -32602, `Cannot cancel task: already in terminal status '${task.status}'`)
      );
    }
    task.status = "cancelled";
    task.statusMessage = "The task was cancelled by request.";
    task.lastUpdatedAt = new Date().toISOString();
    return JSON.stringify(this.makeResponse(id, task));
  }

  private isTerminal(status: string): boolean {
    return status === "completed" || status === "failed" || status === "cancelled";
  }

  // ── Transport ────────────────────────────────────────────

  async runStdio(): Promise<void> {
    const rl = createInterface({
      input: process.stdin,
      output: process.stdout,
      terminal: false,
    });

    for await (const line of rl) {
      const trimmed = line.trim();
      if (!trimmed) continue;

      try {
        const response = await this.handleMessage(trimmed);
        if (response !== null) {
          process.stdout.write(response + "\n");
        }
      } catch {
        // Skip malformed lines
      }
    }
  }

  async runHTTP(host: string = "127.0.0.1", port: number = 8000): Promise<void> {
    const http = await import("node:http");
    const serverInstance = this;

    const server = http.createServer(async (req, res) => {
      if (req.method !== "POST") {
        res.writeHead(405);
        res.end();
        return;
      }

      let body = "";
      for await (const chunk of req) {
        body += chunk;
      }

      const response = await serverInstance.handleMessage(body.trim());

      if (response !== null) {
        res.writeHead(200, { "Content-Type": "application/json" });
        res.end(response);
      } else {
        res.writeHead(202);
        res.end();
      }
    });

    server.listen(port, host, () => {
      console.error(`MCP Server running on http://${host}:${port}/mcp`);
    });

    // Keep alive
    await new Promise(() => {});
  }
}
