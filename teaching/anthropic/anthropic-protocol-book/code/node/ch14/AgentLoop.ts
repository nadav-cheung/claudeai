/**
 * Chapter 14: Agent Loop (ReAct pattern) -- TypeScript.
 *
 * Implements the foundational agent execution loop:
 *     Perceive -> Reason -> Act -> Observe
 *
 * Uses the Anthropic Messages API + Tool Use to build an autonomous
 * agent that iteratively reasons about its task, calls tools, observes
 * results, and decides when the task is complete.
 */

// ---------------------------------------------------------------------------
// Data types
// ---------------------------------------------------------------------------

export interface ToolCall {
  toolId: string;
  name: string;
  input: Record<string, unknown>;
}

export interface ToolCallable {
  (toolName: string, input: Record<string, unknown>): ToolResult;
}

export interface ToolResult {
  toolUseId: string;
  success: boolean;
  content: string;
  error?: string;
}

export interface AgentLoopResult {
  success: boolean;
  answer: string;
  iterations: number;
  toolCallsMade: number;
  totalTokens: number;
  trajectory: TrajectoryStep[];
}

export interface TrajectoryStep {
  iteration: number;
  type: "tool_call" | "complete" | "stalled" | "max_iterations" | "unknown_stop";
  text?: string;
  tool?: string;
  input?: Record<string, unknown>;
  success?: boolean;
  stopReason?: string;
}

// Minimal Anthropic client interface
export interface AnthropicClient {
  messages: {
    create(params: {
      model: string;
      max_tokens: number;
      messages: Record<string, unknown>[];
      system?: string;
      tools?: Record<string, unknown>[];
    }): Promise<AnthropicResponse>;
  };
}

export interface AnthropicResponse {
  stop_reason: string;
  content: ContentBlock[];
  usage: {
    input_tokens: number;
    output_tokens: number;
  };
}

export type ContentBlock =
  | { type: "text"; text: string }
  | { type: "tool_use"; id: string; name: string; input: Record<string, unknown> };

// ---------------------------------------------------------------------------
// Agent Loop
// ---------------------------------------------------------------------------

/**
 * Core ReAct-style agent loop.
 *
 * Usage:
 * ```typescript
 * const loop = new AgentLoop(client, toolExecutor);
 * const result = await loop.run("Find all Python files and count lines");
 * ```
 */
export class AgentLoop {
  private readonly maxIterations: number;
  private readonly maxTokensPerResponse: number;
  private readonly model: string;

  constructor(
    private readonly client: AnthropicClient,
    private readonly toolExecutor: ToolCallable,
    private readonly options: {
      tools?: Record<string, unknown>[];
      systemPrompt?: string;
      model?: string;
      maxIterations?: number;
      maxTokensPerResponse?: number;
    } = {},
  ) {
    this.maxIterations = options.maxIterations ?? 10;
    this.maxTokensPerResponse = options.maxTokensPerResponse ?? 4096;
    this.model = options.model ?? "claude-sonnet-4-20250514";
  }

  // ------------------------------------------------------------------
  // Public API
  // ------------------------------------------------------------------

  async run(task: string): Promise<AgentLoopResult> {
    const messages: Record<string, unknown>[] = [
      { role: "user", content: task },
    ];
    let iterations = 0;
    let toolCallsMade = 0;
    let totalTokens = 0;
    const trajectory: TrajectoryStep[] = [];
    let finalAnswer = "";

    while (iterations < this.maxIterations) {
      iterations++;

      // --- PERCEIVE & REASON ---
      const response = await this.callModel(messages);
      totalTokens +=
        (response.usage?.input_tokens ?? 0) +
        (response.usage?.output_tokens ?? 0);

      const stopReason = response.stop_reason ?? "";
      const contentBlocks: ContentBlock[] = this.extractContent(response);

      if (stopReason === "end_turn") {
        finalAnswer = this.extractText(contentBlocks);
        trajectory.push({
          iteration: iterations,
          type: "complete",
          text: finalAnswer,
        });
        break;
      }

      if (stopReason === "tool_use") {
        const toolCalls = this.parseToolCalls(contentBlocks);
        if (toolCalls.length === 0) {
          finalAnswer = "[Agent stopped with no actionable tool calls]";
          trajectory.push({ iteration: iterations, type: "stalled" });
          break;
        }

        // Append assistant message with tool_use blocks
        messages.push({ role: "assistant", content: contentBlocks });

        // Execute tools and collect results
        const toolResults: Record<string, unknown>[] = [];
        for (const tc of toolCalls) {
          toolCallsMade++;
          const result = this.toolExecutor(tc.name, tc.input);
          toolResults.push({
            type: "tool_result",
            tool_use_id: tc.toolId,
            content: result.content,
            is_error: !result.success,
          });
          trajectory.push({
            iteration: iterations,
            type: "tool_call",
            tool: tc.name,
            input: tc.input,
            success: result.success,
          });
        }

        messages.push({ role: "user", content: toolResults });
        continue;
      }

      // Unknown stop_reason
      finalAnswer = this.extractText(contentBlocks);
      trajectory.push({
        iteration: iterations,
        type: "unknown_stop",
        stopReason,
      });
      break;
    }

    // Reached max iterations
    if (iterations >= this.maxIterations && !finalAnswer) {
      finalAnswer = `[Reached maximum iterations (${this.maxIterations}). Task may be incomplete.]`;
      trajectory.push({
        iteration: iterations,
        type: "max_iterations",
      });
    }

    return {
      success: iterations <= this.maxIterations,
      answer: finalAnswer,
      iterations,
      toolCallsMade,
      totalTokens,
      trajectory,
    };
  }

  // ------------------------------------------------------------------
  // Internal helpers
  // ------------------------------------------------------------------

  private async callModel(
    messages: Record<string, unknown>[],
  ): Promise<AnthropicResponse> {
    const params: Record<string, unknown> = {
      model: this.model,
      max_tokens: this.maxTokensPerResponse,
      messages,
    };
    if (this.options.systemPrompt) {
      params.system = this.options.systemPrompt;
    }
    if (this.options.tools && this.options.tools.length > 0) {
      params.tools = this.options.tools;
    }
    return await this.client.messages.create(
      params as Parameters<AnthropicClient["messages"]["create"]>[0],
    );
  }

  private extractContent(response: AnthropicResponse): ContentBlock[] {
    const content = response.content;
    if (Array.isArray(content)) return content as ContentBlock[];
    if (typeof content === "string") {
      return [{ type: "text", text: content }];
    }
    return [];
  }

  private extractText(blocks: ContentBlock[]): string {
    return blocks
      .filter((b): b is { type: "text"; text: string } => b.type === "text")
      .map((b) => b.text)
      .join("\n");
  }

  private parseToolCalls(blocks: ContentBlock[]): ToolCall[] {
    const calls: ToolCall[] = [];
    for (const block of blocks) {
      if (block.type === "tool_use") {
        let input = block.input;
        if (typeof input === "string") {
          try {
            input = JSON.parse(input);
          } catch {
            // Keep as string if parse fails
          }
        }
        calls.push({
          toolId: block.id ?? "",
          name: block.name ?? "",
          input: input as Record<string, unknown>,
        });
      }
    }
    return calls;
  }
}
