/**
 * Chapter 12: MCP Client (TypeScript).
 *
 * Protocol-level implementation of an MCP-compliant client supporting
 * connection management, capability negotiation, tool discovery and
 * invocation, resource reading, and automatic reconnection with
 * exponential backoff. Supports stdio and HTTP transports.
 *
 * MCP Specification: modelcontextprotocol.io/specification/2025-11-25
 */

import { spawn, type ChildProcess } from "node:child_process";
import { createInterface } from "node:readline";
import type { Interface } from "node:readline";
import http from "node:http";

// ────────────────────────────────────────────────────────────────
// Data types
// ────────────────────────────────────────────────────────────────

export interface ServerInfo {
  name: string;
  version: string;
  protocolVersion: string;
  capabilities: Record<string, unknown>;
  instructions?: string;
}

interface JSONRPCRequest {
  jsonrpc: "2.0";
  id: number;
  method: string;
  params: Record<string, unknown>;
}

interface JSONRPCResponse {
  jsonrpc: "2.0";
  id: number;
  result?: unknown;
  error?: { code: number; message: string; data?: unknown };
}

interface PendingRequest {
  resolve: (value: unknown) => void;
  reject: (reason: Error) => void;
  timer: ReturnType<typeof setTimeout>;
}

// ────────────────────────────────────────────────────────────────
// MCPClient
// ────────────────────────────────────────────────────────────────

export class MCPClient {
  static readonly PROTOCOL_VERSION = "2025-11-25";

  private process: ChildProcess | null = null;
  private rl: Interface | null = null;
  private httpUrl: string | null = null;
  private requestId = 0;
  private pending = new Map<number, PendingRequest>();
  private serverInfo: ServerInfo = {
    name: "",
    version: "",
    protocolVersion: "",
    capabilities: {},
  };
  private initialized = false;
  private connected = false;

  // ── Connection ──────────────────────────────────────────

  async connectStdio(command: string, args: string[], env?: Record<string, string>): Promise<ServerInfo> {
    this.process = spawn(command, args, {
      stdio: ["pipe", "pipe", "pipe"],
      env: { ...process.env, ...env },
    });

    this.rl = createInterface({
      input: this.process.stdout!,
      terminal: false,
    });

    this.rl.on("line", (line: string) => {
      this.onLine(line);
    });

    this.connected = true;

    // Perform initialization
    this.serverInfo = await this.initialize();
    this.initialized = true;

    // Send initialized notification
    this.sendNotification("notifications/initialized", {});

    return this.serverInfo;
  }

  async connectHTTP(url: string): Promise<ServerInfo> {
    this.httpUrl = url.replace(/\/$/, "");
    this.connected = true;
    this.serverInfo = await this.initialize();
    this.initialized = true;
    this.sendNotification("notifications/initialized", {});
    return this.serverInfo;
  }

  disconnect(): void {
    this.connected = false;
    if (this.rl) {
      this.rl.close();
      this.rl = null;
    }
    if (this.process) {
      this.process.kill();
      this.process = null;
    }
    this.httpUrl = null;
    this.initialized = false;

    // Reject all pending requests
    for (const [, pending] of this.pending) {
      pending.reject(new Error("Client disconnected"));
    }
    this.pending.clear();
  }

  // ── Reconnection ────────────────────────────────────────

  async reconnectWithBackoff(options: {
    command?: string;
    args?: string[];
    maxRetries?: number;
    baseDelay?: number;
    maxDelay?: number;
  }): Promise<ServerInfo> {
    if (this.connected) {
      this.disconnect();
    }

    const maxRetries = options.maxRetries ?? 5;
    const baseDelay = options.baseDelay ?? 1.0;
    const maxDelay = options.maxDelay ?? 30.0;

    for (let attempt = 1; attempt <= maxRetries; attempt++) {
      try {
        if (this.httpUrl) {
          return await this.connectHTTP(this.httpUrl);
        } else if (options.command) {
          return await this.connectStdio(options.command, options.args ?? []);
        } else {
          throw new Error("No connection configuration available");
        }
      } catch (exc) {
        if (attempt === maxRetries) {
          throw new Error(`Failed to reconnect after ${maxRetries} attempts: ${String(exc)}`);
        }
        const delay = Math.min(baseDelay * Math.pow(2, attempt - 1), maxDelay);
        await new Promise((resolve) => setTimeout(resolve, delay * 1000));
      }
    }

    throw new Error("Reconnection failed");
  }

  // ── Capability negotiation ──────────────────────────────

  private async initialize(): Promise<ServerInfo> {
    const result = (await this.sendRequest("initialize", {
      protocolVersion: MCPClient.PROTOCOL_VERSION,
      capabilities: {
        roots: { listChanged: true },
        sampling: {},
      },
      clientInfo: { name: "mcp-client-book", version: "1.0.0" },
    })) as Record<string, unknown>;

    return {
      name: (result.serverInfo as Record<string, string>)?.name ?? "",
      version: (result.serverInfo as Record<string, string>)?.version ?? "",
      protocolVersion: (result.protocolVersion as string) ?? "",
      capabilities: (result.capabilities as Record<string, unknown>) ?? {},
      instructions: result.instructions as string | undefined,
    };
  }

  // ── Tools ────────────────────────────────────────────────

  async listTools(): Promise<Array<Record<string, unknown>>> {
    if (!this.serverInfo.capabilities.tools) return [];
    const result = (await this.sendRequest("tools/list", {})) as Record<string, unknown>;
    return (result.tools as Array<Record<string, unknown>>) ?? [];
  }

  async callTool(name: string, args: Record<string, unknown>): Promise<Record<string, unknown>> {
    return (await this.sendRequest("tools/call", { name, arguments: args })) as Record<string, unknown>;
  }

  async callToolAsTask(
    name: string,
    args: Record<string, unknown>,
    ttl?: number
  ): Promise<Record<string, unknown>> {
    const params: Record<string, unknown> = {
      name,
      arguments: args,
      task: {} as Record<string, unknown>,
    };
    if (ttl !== undefined) {
      (params.task as Record<string, unknown>).ttl = ttl;
    }
    return (await this.sendRequest("tools/call", params)) as Record<string, unknown>;
  }

  // ── Resources ────────────────────────────────────────────

  async listResources(): Promise<Array<Record<string, unknown>>> {
    if (!this.serverInfo.capabilities.resources) return [];
    const result = (await this.sendRequest("resources/list", {})) as Record<string, unknown>;
    return (result.resources as Array<Record<string, unknown>>) ?? [];
  }

  async readResource(uri: string): Promise<Record<string, unknown>> {
    return (await this.sendRequest("resources/read", { uri })) as Record<string, unknown>;
  }

  // ── Prompts ──────────────────────────────────────────────

  async listPrompts(): Promise<Array<Record<string, unknown>>> {
    if (!this.serverInfo.capabilities.prompts) return [];
    const result = (await this.sendRequest("prompts/list", {})) as Record<string, unknown>;
    return (result.prompts as Array<Record<string, unknown>>) ?? [];
  }

  async getPrompt(name: string, args?: Record<string, unknown>): Promise<Record<string, unknown>> {
    const params: Record<string, unknown> = { name };
    if (args) params.arguments = args;
    return (await this.sendRequest("prompts/get", params)) as Record<string, unknown>;
  }

  // ── Server Info ──────────────────────────────────────────

  getServerInfo(): ServerInfo {
    return this.serverInfo;
  }

  async ping(): Promise<boolean> {
    try {
      await this.sendRequest("ping", {});
      return true;
    } catch {
      return false;
    }
  }

  // ── Messaging ────────────────────────────────────────────

  async sendRequest(method: string, params: Record<string, unknown>): Promise<unknown> {
    const id = ++this.requestId;

    return new Promise<unknown>((resolve, reject) => {
      const timer = setTimeout(() => {
        this.pending.delete(id);
        reject(new Error(`Request ${method} timed out`));
      }, 30000);

      this.pending.set(id, { resolve, reject, timer });

      const request: JSONRPCRequest = {
        jsonrpc: "2.0",
        id,
        method,
        params,
      };

      this.writeLine(JSON.stringify(request));
    });
  }

  private sendNotification(method: string, params: Record<string, unknown>): void {
    const notification = JSON.stringify({ jsonrpc: "2.0", method, params });
    this.writeLine(notification);
  }

  private writeLine(data: string): void {
    if (this.httpUrl) {
      this.httpWriteLine(data);
    } else if (this.process?.stdin?.writable) {
      this.process.stdin.write(data + "\n");
    }
  }

  private httpWriteLine(data: string): void {
    if (!this.httpUrl) return;

    const url = new URL(this.httpUrl + "/mcp");
    const postData = data;

    const options = {
      hostname: url.hostname,
      port: url.port || 80,
      path: url.pathname,
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "Content-Length": Buffer.byteLength(postData),
        "MCP-Protocol-Version": MCPClient.PROTOCOL_VERSION,
      },
    };

    const req = http.request(options, (res) => {
      let body = "";
      res.on("data", (chunk) => (body += chunk));
      res.on("end", () => {
        try {
          const msg = JSON.parse(body) as JSONRPCResponse;
          this.onResponse(msg);
        } catch {
          // Skip malformed
        }
      });
    });
    req.on("error", () => {});
    req.write(postData);
    req.end();
  }

  private onLine(line: string): void {
    const trimmed = line.trim();
    if (!trimmed) return;

    try {
      const msg = JSON.parse(trimmed) as JSONRPCResponse;
      this.onResponse(msg);
    } catch {
      // Skip malformed JSON
    }
  }

  private onResponse(msg: JSONRPCResponse): void {
    if (msg.id !== undefined) {
      const pending = this.pending.get(msg.id);
      if (pending) {
        clearTimeout(pending.timer);
        this.pending.delete(msg.id);
        if (msg.error) {
          pending.reject(new Error(msg.error.message ?? "Unknown error"));
        } else {
          pending.resolve(msg.result);
        }
      }
    }
  }
}
