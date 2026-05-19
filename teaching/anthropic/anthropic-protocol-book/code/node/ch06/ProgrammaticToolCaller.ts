/**
 * Chapter 6: Programmatic Tool Caller (TypeScript).
 *
 * Client-side orchestration logic for Anthropic's Programmatic Tool
 * Calling feature. Simulates code execution tool call extraction,
 * manages pending tool calls, and formats results.
 */

export interface CodeExecutionResult {
  stdout: string;
  stderr: string;
  return_code: number;
}

export interface ProgrammaticToolCallRecord {
  tool_name: string;
  input_data: Record<string, unknown>;
  caller_tool_id: string;
  tool_use_id: string;
}

/**
 * Programmatic Tool Caller.
 *
 * Usage:
 * ```typescript
 * const caller = new ProgrammaticToolCaller();
 * caller.executeCode('result = await query_database("SELECT * FROM orders")');
 * console.log(caller.pendingCalls);
 * ```
 */
export class ProgrammaticToolCaller {
  private _containerId: string | null = null;
  private _pendingCalls: ProgrammaticToolCallRecord[] = [];

  // ------------------------------------------------------------------
  // Code execution simulation
  // ------------------------------------------------------------------

  executeCode(code: string): CodeExecutionResult {
    this._pendingCalls = [];
    const toolCalls = this.extractToolCalls(code);

    if (toolCalls.length === 0) {
      return {
        stdout: "",
        stderr: "No tool calls found in code",
        return_code: 0,
      };
    }

    this._pendingCalls = toolCalls;

    return {
      stdout: "",
      stderr: "",
      return_code: 0,
    };
  }

  /**
   * Extract function call patterns from orchestration code.
   *
   * Matches:
   * - ``await tool_name(...)``
   * - ``tool_name(...)``
   */
  extractToolCalls(code: string): ProgrammaticToolCallRecord[] {
    const calls: ProgrammaticToolCallRecord[] = [];
    const pattern = /(?:await\s+)?(\w+)\s*\(([^)]*)\)/g;
    let match: RegExpExecArray | null;

    while ((match = pattern.exec(code)) !== null) {
      calls.push({
        tool_name: match[1]!,
        input_data: {},
        caller_tool_id: "",
        tool_use_id: `toolu_${calls.length.toString().padStart(4, "0")}`,
      });
    }

    return calls;
  }

  // ------------------------------------------------------------------
  // Result processing
  // ------------------------------------------------------------------

  processToolResults(
    results: Array<{ tool_name: string; result: unknown }>,
  ): string {
    return results.map((r) => JSON.stringify(r)).join("\n");
  }

  formatToolResultForApi(
    toolUseId: string,
    resultContent: string,
  ): Record<string, unknown> {
    return {
      type: "tool_result",
      tool_use_id: toolUseId,
      content: resultContent,
    };
  }

  // ------------------------------------------------------------------
  // Container management
  // ------------------------------------------------------------------

  get containerId(): string | null {
    return this._containerId;
  }

  setContainer(containerId: string): void {
    this._containerId = containerId;
  }

  resetContainer(): void {
    this._containerId = null;
    this._pendingCalls = [];
  }

  get pendingCalls(): ProgrammaticToolCallRecord[] {
    return [...this._pendingCalls];
  }

  get hasPendingCalls(): boolean {
    return this._pendingCalls.length > 0;
  }
}
