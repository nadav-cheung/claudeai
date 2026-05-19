/**
 * Chapter 14: Supervisor-Worker Pattern -- TypeScript.
 *
 * Implements a centralized coordinator (Supervisor) that pre-plans
 * task decomposition, dispatches subtasks to Worker agents, and
 * synthesizes results. Unlike Sub-Agent Orchestration, task allocation
 * happens upfront rather than dynamically during execution.
 *
 * Pattern:  Supervisor plans -> Workers execute -> Supervisor synthesizes
 */

import {
  AgentLoop,
  AgentLoopResult,
  AnthropicClient,
  ToolCallable,
} from "./AgentLoop";

// ---------------------------------------------------------------------------
// Data types
// ---------------------------------------------------------------------------

export interface WorkerDefinition {
  name: string;
  description: string;
  systemPrompt: string;
  tools: Record<string, unknown>[];
  model: string;
  maxIterations: number;
}

export interface WorkItem {
  workerName: string;
  description: string;
  expectedOutput: string;
  constraints: string[];
}

export interface WorkResult {
  workerName: string;
  description: string;
  success: boolean;
  output: string;
  iterations: number;
  toolCalls: number;
}

export interface SupervisorResult {
  success: boolean;
  answer: string;
  plan: WorkItem[];
  workResults: WorkResult[];
  totalIterations: number;
  totalToolCalls: number;
  totalTokens: number;
}

// ---------------------------------------------------------------------------
// Supervisor-Worker
// ---------------------------------------------------------------------------

/**
 * Supervisor-Worker pattern implementation.
 *
 * Usage:
 * ```typescript
 * const sw = new SupervisorWorker(client, toolExecutor);
 * sw.registerWorker("reviewer", "Code reviewer", "You review code...");
 * const result = await sw.run("Review the project for bugs");
 * ```
 */
export class SupervisorWorker {
  private readonly workers: Map<string, WorkerDefinition> = new Map();
  private readonly maxTokensPerResponse: number;
  private readonly model: string;

  constructor(
    private readonly client: AnthropicClient,
    private readonly toolExecutor: ToolCallable,
    options: {
      model?: string;
      maxTokensPerResponse?: number;
    } = {},
  ) {
    this.model = options.model ?? "claude-sonnet-4-20250514";
    this.maxTokensPerResponse = options.maxTokensPerResponse ?? 4096;
  }

  // ------------------------------------------------------------------
  // Worker registration
  // ------------------------------------------------------------------

  registerWorker(
    name: string,
    description: string,
    systemPrompt: string,
    opts: {
      tools?: Record<string, unknown>[];
      model?: string;
      maxIterations?: number;
    } = {},
  ): void {
    if (this.workers.has(name)) {
      throw new Error(`Worker '${name}' is already registered`);
    }
    this.workers.set(name, {
      name,
      description,
      systemPrompt,
      tools: opts.tools ?? [],
      model: opts.model ?? "claude-sonnet-4-20250514",
      maxIterations: opts.maxIterations ?? 10,
    });
  }

  unregisterWorker(name: string): void {
    this.workers.delete(name);
  }

  listWorkers(): { name: string; description: string }[] {
    const result: { name: string; description: string }[] = [];
    for (const w of this.workers.values()) {
      result.push({ name: w.name, description: w.description });
    }
    return result;
  }

  // ------------------------------------------------------------------
  // Plan phase
  // ------------------------------------------------------------------

  async plan(task: string): Promise<WorkItem[]> {
    if (this.workers.size === 0) {
      return [
        {
          workerName: "__main__",
          description: task,
          expectedOutput: "Complete the task",
          constraints: [],
        },
      ];
    }

    const workerDescriptions = Array.from(this.workers.values())
      .map((w) => `- ${w.name}: ${w.description}`)
      .join("\n");

    const planPrompt =
      "You are a work supervisor planning task execution.\n\n" +
      "Available Workers:\n" +
      `${workerDescriptions}\n\n` +
      `User Task: ${task}\n\n` +
      "Create a work plan by decomposing the task into work items. " +
      "Each work item should be assigned to the most appropriate worker.\n\n" +
      "Respond in JSON with a 'plan' array. Each item has:\n" +
      "- 'worker_name': name of the assigned worker\n" +
      "- 'description': clear, specific task description for the worker\n" +
      "- 'expected_output': what the worker should produce\n" +
      "- 'constraints': any limits or rules the worker must follow\n\n" +
      "Distribute work evenly. If a task doesn't fit any worker, " +
      "assign it to '__main__' for the supervisor to handle.";

    const response = await this.client.messages.create({
      model: this.model,
      max_tokens: 1024,
      messages: [{ role: "user", content: planPrompt }],
    });

    const text = this.extractText(
      response.content as { type: string; text?: string }[],
    );
    const plan = this.parsePlan(text);

    const valid = plan.filter(
      (item) =>
        item.workerName === "__main__" || this.workers.has(item.workerName),
    );
    return valid.length > 0
      ? valid
      : [
          {
            workerName: "__main__",
            description: task,
            expectedOutput: "Complete the task",
            constraints: [],
          },
        ];
  }

  // ------------------------------------------------------------------
  // Execute phase
  // ------------------------------------------------------------------

  async executeWork(item: WorkItem): Promise<WorkResult> {
    if (item.workerName === "__main__") {
      const loop = new AgentLoop(this.client, this.toolExecutor, {
        tools: [],
        systemPrompt:
          "You are a supervisor handling a task directly. " +
          "Complete the task thoroughly.",
        model: this.model,
        maxIterations: 10,
        maxTokensPerResponse: this.maxTokensPerResponse,
      });
      const result = await loop.run(item.description);
      return {
        workerName: "__main__",
        description: item.description,
        success: result.success,
        output: result.answer,
        iterations: result.iterations,
        toolCalls: result.toolCallsMade,
      };
    }

    const worker = this.workers.get(item.workerName);
    if (!worker) {
      return this.executeWork({
        workerName: "__main__",
        description: item.description,
        expectedOutput: item.expectedOutput,
        constraints: item.constraints,
      });
    }

    // Build worker task with constraints
    const taskParts = [item.description];
    if (item.expectedOutput) {
      taskParts.push(`\nExpected Output: ${item.expectedOutput}`);
    }
    if (item.constraints.length > 0) {
      taskParts.push(`\nConstraints: ${item.constraints.join("; ")}`);
    }
    const workerTask = taskParts.join("\n");

    const loop = new AgentLoop(this.client, this.toolExecutor, {
      tools: worker.tools,
      systemPrompt: worker.systemPrompt,
      model: worker.model,
      maxIterations: worker.maxIterations,
      maxTokensPerResponse: this.maxTokensPerResponse,
    });
    const result = await loop.run(workerTask);
    return {
      workerName: item.workerName,
      description: item.description,
      success: result.success,
      output: result.answer,
      iterations: result.iterations,
      toolCalls: result.toolCallsMade,
    };
  }

  // ------------------------------------------------------------------
  // Synthesize phase
  // ------------------------------------------------------------------

  async synthesize(
    task: string,
    plan: WorkItem[],
    results: WorkResult[],
  ): Promise<string> {
    let resultsText = "";
    results.forEach((result, i) => {
      const item = plan[i]!;
      resultsText +=
        `\n### Work Item ${i + 1} [${result.workerName}]\n` +
        `Task: ${item.description}\n` +
        `Expected: ${item.expectedOutput}\n` +
        `Success: ${result.success}\n` +
        `Output:\n${result.output}\n`;
    });

    const synPrompt =
      `Original Task: ${task}\n\n` +
      `Plan and Results:\n${resultsText}\n\n` +
      "Synthesize these results into a single comprehensive answer " +
      "that addresses the original task. If any work item failed, " +
      "note the limitation in your response.";

    const response = await this.client.messages.create({
      model: this.model,
      max_tokens: this.maxTokensPerResponse,
      messages: [{ role: "user", content: synPrompt }],
    });

    return this.extractText(
      response.content as { type: string; text?: string }[],
    );
  }

  // ------------------------------------------------------------------
  // Full run
  // ------------------------------------------------------------------

  async run(task: string): Promise<SupervisorResult> {
    const plan = await this.plan(task);

    const results: WorkResult[] = [];
    let totalIterations = 0;
    let totalToolCalls = 0;
    let totalTokens = 0;

    for (const item of plan) {
      const result = await this.executeWork(item);
      results.push(result);
      totalIterations += result.iterations;
      totalToolCalls += result.toolCalls;
    }

    const finalAnswer = await this.synthesize(task, plan, results);

    return {
      success: results.every((r) => r.success),
      answer: finalAnswer,
      plan,
      workResults: results,
      totalIterations,
      totalToolCalls,
      totalTokens,
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

  private parsePlan(text: string): WorkItem[] {
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
      const items = data.plan ?? [data];

      return items
        .filter((item: unknown): item is Record<string, unknown> =>
          typeof item === "object" && item !== null,
        )
        .map((item: Record<string, unknown>) => ({
          workerName: (item.worker_name as string) ?? "__main__",
          description: (item.description as string) ?? "",
          expectedOutput: (item.expected_output as string) ?? "",
          constraints: (item.constraints as string[]) ?? [],
        }));
    } catch {
      return [];
    }
  }
}
