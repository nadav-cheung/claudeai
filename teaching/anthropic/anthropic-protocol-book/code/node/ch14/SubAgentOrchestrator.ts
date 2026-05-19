/**
 * Chapter 14: Sub-Agent Orchestrator -- TypeScript.
 *
 * Implements dynamic sub-agent delegation where the main agent decides
 * at runtime which specialized sub-agent to call for which subtask.
 *
 * Pattern:  Main Agent -> detect subtask -> dispatch to sub-agent
 *          -> collect result -> synthesize -> continue or complete
 */

import {
  AgentLoop,
  AgentLoopResult,
  AnthropicClient,
  ToolCallable,
  ToolResult,
} from "./AgentLoop";

// ---------------------------------------------------------------------------
// Data types
// ---------------------------------------------------------------------------

export interface SubAgentDefinition {
  name: string;
  description: string;
  systemPrompt: string;
  tools: Record<string, unknown>[];
  model: string;
  maxIterations: number;
}

export interface SubTask {
  agentName: string;
  taskDescription: string;
  context?: string;
  priority?: number;
}

export interface SubTaskResult {
  agentName: string;
  taskDescription: string;
  success: boolean;
  result: AgentLoopResult;
}

export interface OrchestratorResult {
  success: boolean;
  answer: string;
  totalIterations: number;
  totalToolCalls: number;
  totalTokens: number;
  subtaskResults: SubTaskResult[];
}

// ---------------------------------------------------------------------------
// Sub-Agent Orchestrator
// ---------------------------------------------------------------------------

/**
 * Orchestrates a main agent that dynamically delegates to sub-agents.
 *
 * Usage:
 * ```typescript
 * const orch = new SubAgentOrchestrator(client, toolExecutor);
 * orch.registerSubAgent("reviewer", "Code reviewer", "You review code...");
 * const result = await orch.run("Review the auth module and fix issues");
 * ```
 */
export class SubAgentOrchestrator {
  private readonly subAgents: Map<string, SubAgentDefinition> = new Map();
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
    this.maxIterations = options.maxIterations ?? 15;
    this.maxTokensPerResponse = options.maxTokensPerResponse ?? 4096;
    this.model = options.model ?? "claude-sonnet-4-20250514";
  }

  // ------------------------------------------------------------------
  // Sub-agent registration
  // ------------------------------------------------------------------

  registerSubAgent(
    name: string,
    description: string,
    systemPrompt: string,
    opts: {
      tools?: Record<string, unknown>[];
      model?: string;
      maxIterations?: number;
    } = {},
  ): void {
    if (this.subAgents.has(name)) {
      throw new Error(`Sub-agent '${name}' is already registered`);
    }
    this.subAgents.set(name, {
      name,
      description,
      systemPrompt,
      tools: opts.tools ?? [],
      model: opts.model ?? "claude-sonnet-4-20250514",
      maxIterations: opts.maxIterations ?? 10,
    });
  }

  unregisterSubAgent(name: string): void {
    this.subAgents.delete(name);
  }

  listSubAgents(): { name: string; description: string }[] {
    const result: { name: string; description: string }[] = [];
    for (const sa of this.subAgents.values()) {
      result.push({ name: sa.name, description: sa.description });
    }
    return result;
  }

  // ------------------------------------------------------------------
  // Task decomposition
  // ------------------------------------------------------------------

  async decompose(task: string): Promise<SubTask[]> {
    if (this.subAgents.size === 0) {
      return [{ agentName: "main", taskDescription: task }];
    }

    const agentDescriptions = Array.from(this.subAgents.values())
      .map((sa) => `- ${sa.name}: ${sa.description}`)
      .join("\n");

    const decomposePrompt =
      "You are a task decomposition specialist. Given a complex task " +
      "and a set of available specialized agents, decompose the task " +
      "into subtasks that can be assigned to specific agents.\n\n" +
      "Available Agents:\n" +
      `${agentDescriptions}\n\n` +
      "Main Agent: General-purpose, handles coordination and tasks " +
      "not suited for other agents.\n\n" +
      `Task: ${task}\n\n` +
      "Respond in JSON format with a 'subtasks' array. Each subtask " +
      "has: 'agent_name' (must match an available agent or 'main'), " +
      "'task_description' (clear, specific), 'priority' (integer, " +
      "lower = higher priority).\n\n" +
      "Only decompose if the task truly benefits from specialization. " +
      "For simple tasks, return a single subtask for 'main'.";

    const response = await this.client.messages.create({
      model: this.model,
      max_tokens: 1024,
      messages: [{ role: "user", content: decomposePrompt }],
    });

    const text = this.extractText(
      response.content as { type: string; text?: string }[],
    );
    const subtasks = this.parseSubtasks(text);

    // Validate agent names
    const valid = subtasks.filter(
      (st) => st.agentName === "main" || this.subAgents.has(st.agentName),
    );
    return valid.length > 0
      ? valid
      : [{ agentName: "main", taskDescription: task }];
  }

  // ------------------------------------------------------------------
  // Dispatch
  // ------------------------------------------------------------------

  async dispatch(subtask: SubTask): Promise<SubTaskResult> {
    if (subtask.agentName === "main") {
      const loop = new AgentLoop(this.client, this.toolExecutor, {
        tools: this.options.tools,
        systemPrompt: this.options.systemPrompt,
        model: this.model,
        maxIterations: this.maxIterations,
        maxTokensPerResponse: this.maxTokensPerResponse,
      });
      const result = await loop.run(subtask.taskDescription);
      return {
        agentName: "main",
        taskDescription: subtask.taskDescription,
        success: result.success,
        result,
      };
    }

    const sa = this.subAgents.get(subtask.agentName);
    if (!sa) {
      return this.dispatch({
        agentName: "main",
        taskDescription: subtask.taskDescription,
      });
    }

    const loop = new AgentLoop(this.client, this.toolExecutor, {
      tools: sa.tools,
      systemPrompt: sa.systemPrompt,
      model: sa.model,
      maxIterations: sa.maxIterations,
      maxTokensPerResponse: this.maxTokensPerResponse,
    });
    const result = await loop.run(subtask.taskDescription);
    return {
      agentName: subtask.agentName,
      taskDescription: subtask.taskDescription,
      success: result.success,
      result,
    };
  }

  // ------------------------------------------------------------------
  // Synthesize
  // ------------------------------------------------------------------

  async synthesize(
    task: string,
    results: SubTaskResult[],
  ): Promise<AgentLoopResult> {
    let resultsText = "";
    results.forEach((r, i) => {
      resultsText +=
        `\n### Subtask ${i + 1} [${r.agentName}]\n` +
        `Task: ${r.taskDescription}\n` +
        `Success: ${r.success}\n` +
        `Result:\n${r.result.answer}\n`;
    });

    const synthesizePrompt =
      `Original Task: ${task}\n\n` +
      `Subtasks and Results:\n${resultsText}\n\n` +
      "Synthesize these results into a single comprehensive answer. " +
      "Address the original task fully. If any subtask failed, " +
      "note the gap and provide your best answer based on available " +
      "information.";

    const response = await this.client.messages.create({
      model: this.model,
      max_tokens: this.maxTokensPerResponse,
      messages: [{ role: "user", content: synthesizePrompt }],
    });

    const text = this.extractText(
      response.content as { type: string; text?: string }[],
    );
    return {
      success: results.every((r) => r.success),
      answer: text,
      iterations: 1,
      toolCallsMade: 0,
      totalTokens: 0,
      trajectory: [],
    };
  }

  // ------------------------------------------------------------------
  // Full orchestration run
  // ------------------------------------------------------------------

  async run(task: string): Promise<OrchestratorResult> {
    const subtasks = await this.decompose(task);

    const subtaskResults: SubTaskResult[] = [];
    let totalIterations = 0;
    let totalToolCalls = 0;
    let totalTokens = 0;

    for (const subtask of subtasks) {
      const result = await this.dispatch(subtask);
      subtaskResults.push(result);
      totalIterations += result.result.iterations;
      totalToolCalls += result.result.toolCallsMade;
      totalTokens += result.result.totalTokens;
    }

    const final = await this.synthesize(task, subtaskResults);

    return {
      success: final.success,
      answer: final.answer,
      totalIterations,
      totalToolCalls,
      totalTokens,
      subtaskResults,
    };
  }

  // ------------------------------------------------------------------
  // Internal helpers
  // ------------------------------------------------------------------

  private extractText(
    blocks: { type: string; text?: string }[],
  ): string {
    return blocks
      .filter((b) => b.type === "text")
      .map((b) => b.text ?? "")
      .join("\n");
  }

  private parseSubtasks(text: string): SubTask[] {
    try {
      let jsonStr = text;
      if (text.includes("```json")) {
        const start = text.indexOf("```json") + 7;
        const end = text.indexOf("```", start);
        jsonStr = text.substring(start, end).trim();
      } else if (text.includes("```")) {
        const start = text.indexOf("```") + 3;
        const end = text.indexOf("```", start);
        jsonStr = text.substring(start, end).trim();
      } else if (text.includes("{") && text.includes("}")) {
        const start = text.indexOf("{");
        const end = text.lastIndexOf("}") + 1;
        jsonStr = text.substring(start, end);
      }

      const data = JSON.parse(jsonStr);
      const items = data.subtasks ?? [data];

      return items
        .filter((item: unknown): item is Record<string, unknown> =>
          typeof item === "object" && item !== null,
        )
        .map((item: Record<string, unknown>) => ({
          agentName: (item.agent_name as string) ?? "main",
          taskDescription: (item.task_description as string) ?? "",
          priority: (item.priority as number) ?? 0,
        }));
    } catch {
      return [];
    }
  }
}
