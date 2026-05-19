/**
 * Chapter 6: Tool Registry (TypeScript).
 *
 * Protocol-level implementation of Anthropic's Tool Use feature.
 * Manages tool definitions, deferred loading, allowed callers,
 * and API format conversion for the Messages API.
 */

export interface JsonSchema {
  type: "object";
  properties: Record<string, Record<string, unknown>>;
  required?: string[];
  additionalProperties?: boolean;
}

export interface ToolDefinition {
  name: string;
  description: string;
  input_schema: JsonSchema;
  handler: (...args: any[]) => any;
  defer_loading?: boolean;
  allowed_callers?: string[];
  input_examples?: Record<string, unknown>[];
  strict?: boolean;
}

export interface ToolCall {
  tool_name: string;
  input: Record<string, unknown>;
}

export interface ToolResult {
  success: boolean;
  result?: unknown;
  error?: string;
}

const REQUIRED_CODE_EXEC_CALLER = "code_execution_20260120";

/**
 * Central registry for tool definitions, execution, and API formatting.
 *
 * Usage:
 * ```typescript
 * const registry = new ToolRegistry();
 * registry.register("get_weather", "Get weather for a location",
 *   { type: "object", properties: { location: { type: "string" } }, required: ["location"] },
 *   (input) => `Weather: 72F`
 * );
 * const tools = registry.toApiFormat();
 * ```
 */
export class ToolRegistry {
  private tools: Map<string, ToolDefinition> = new Map();
  private searchEnabled: boolean = false;
  private codeExecutionEnabled: boolean = false;

  // ------------------------------------------------------------------
  // Registration
  // ------------------------------------------------------------------

  register(
    name: string,
    description: string,
    input_schema: JsonSchema,
    handler: (...args: any[]) => any,
    options: {
      defer_loading?: boolean;
      allowed_callers?: string[];
      input_examples?: Record<string, unknown>[];
      strict?: boolean;
    } = {},
  ): void {
    if (this.tools.has(name)) {
      throw new Error(`Tool '${name}' is already registered`);
    }
    if (typeof handler !== "function") {
      throw new Error(`Handler for tool '${name}' must be a function`);
    }
    if (!input_schema || input_schema.type !== "object") {
      throw new Error(
        "input_schema must be a JSON Schema object with type='object'",
      );
    }

    this.tools.set(name, {
      name,
      description,
      input_schema,
      handler,
      defer_loading: options.defer_loading ?? false,
      allowed_callers: options.allowed_callers,
      input_examples: options.input_examples,
      strict: options.strict ?? false,
    });
  }

  unregister(name: string): void {
    this.tools.delete(name);
  }

  // ------------------------------------------------------------------
  // Queries
  // ------------------------------------------------------------------

  get(name: string): ToolDefinition | undefined {
    return this.tools.get(name);
  }

  listNames(): string[] {
    return Array.from(this.tools.keys());
  }

  getDeferredTools(): ToolDefinition[] {
    return Array.from(this.tools.values()).filter((t) => t.defer_loading);
  }

  getImmediateTools(): ToolDefinition[] {
    return Array.from(this.tools.values()).filter((t) => !t.defer_loading);
  }

  getProgrammaticTools(): ToolDefinition[] {
    return Array.from(this.tools.values()).filter(
      (t) =>
        t.allowed_callers !== undefined &&
        t.allowed_callers.includes(REQUIRED_CODE_EXEC_CALLER),
    );
  }

  getStrictTools(): ToolDefinition[] {
    return Array.from(this.tools.values()).filter((t) => t.strict);
  }

  count(): number {
    return this.tools.size;
  }

  // ------------------------------------------------------------------
  // API format
  // ------------------------------------------------------------------

  toApiFormat(): Record<string, unknown>[] {
    const result: Record<string, unknown>[] = [];
    for (const tool of this.tools.values()) {
      const entry: Record<string, unknown> = {
        name: tool.name,
        description: tool.description,
        input_schema: tool.input_schema,
      };
      if (tool.defer_loading) entry["defer_loading"] = true;
      if (tool.allowed_callers) entry["allowed_callers"] = tool.allowed_callers;
      if (tool.input_examples) entry["input_examples"] = tool.input_examples;
      if (tool.strict) entry["strict"] = true;
      result.push(entry);
    }
    return result;
  }

  toSearchIndexFormat(): Record<string, unknown>[] {
    const result: Record<string, unknown>[] = [];
    for (const tool of this.tools.values()) {
      if (tool.defer_loading) {
        result.push({
          name: tool.name,
          description: tool.description,
          input_schema: tool.input_schema,
        });
      }
    }
    return result;
  }

  // ------------------------------------------------------------------
  // Execution
  // ------------------------------------------------------------------

  execute(toolName: string, inputData: Record<string, unknown>): ToolResult {
    const tool = this.tools.get(toolName);
    if (!tool) {
      throw new Error(`Tool '${toolName}' not found in registry`);
    }
    try {
      const result = tool.handler(inputData);
      return { success: true, result };
    } catch (e: unknown) {
      return {
        success: false,
        error: e instanceof Error ? e.message : String(e),
      };
    }
  }

  executeMany(calls: ToolCall[]): ToolResult[] {
    return calls.map((call) => this.execute(call.tool_name, call.input));
  }

  // ------------------------------------------------------------------
  // Feature toggles
  // ------------------------------------------------------------------

  enableToolSearch(): void {
    this.searchEnabled = true;
  }

  enableCodeExecution(): void {
    this.codeExecutionEnabled = true;
  }

  get isSearchEnabled(): boolean {
    return this.searchEnabled;
  }

  get isCodeExecutionEnabled(): boolean {
    return this.codeExecutionEnabled;
  }
}
