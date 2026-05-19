/**
 * Chapter 14: Reflexion Agent -- TypeScript.
 *
 * Extends ReAct Agent Loop with post-execution self-evaluation and
 * strategy adjustment. After each full trajectory, the agent reflects
 * on what worked, what failed, and how to improve before retrying.
 *
 * Pattern:  ReAct Loop -> Evaluate -> Reflect -> Adjust -> Retry
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

export interface ReflectionResult {
  success: boolean;
  strategyAdjustment: string;
  lessonsLearned: string[];
  shouldRetry: boolean;
  confidence: number; // 0.0 - 1.0
}

export interface ReflexionAgentResult {
  success: boolean;
  answer: string;
  totalIterations: number;
  totalToolCalls: number;
  totalTokens: number;
  reflectionCycles: number;
  allTrajectories: TrajectoryStep[][];
  reflections: ReflectionResult[];
}

export interface TrajectoryStep {
  iteration: number;
  type: string;
  text?: string;
  tool?: string;
  input?: Record<string, unknown>;
  success?: boolean;
  stopReason?: string;
}

// ---------------------------------------------------------------------------
// Reflexion Agent
// ---------------------------------------------------------------------------

/**
 * Agent that uses reflection to improve over multiple attempts.
 *
 * Usage:
 * ```typescript
 * const agent = new ReflexionAgent(client, toolExecutor);
 * const result = await agent.run("Debug the failing test suite");
 * ```
 */
export class ReflexionAgent {
  private readonly maxIterationsPerAttempt: number;
  private readonly maxReflectionCycles: number;
  private readonly maxTokensPerResponse: number;
  private readonly model: string;

  constructor(
    private readonly client: AnthropicClient,
    private readonly toolExecutor: ToolCallable,
    private readonly options: {
      tools?: Record<string, unknown>[];
      systemPrompt?: string;
      model?: string;
      maxIterationsPerAttempt?: number;
      maxReflectionCycles?: number;
      maxTokensPerResponse?: number;
    } = {},
  ) {
    this.maxIterationsPerAttempt = options.maxIterationsPerAttempt ?? 10;
    this.maxReflectionCycles = options.maxReflectionCycles ?? 3;
    this.maxTokensPerResponse = options.maxTokensPerResponse ?? 4096;
    this.model = options.model ?? "claude-sonnet-4-20250514";
  }

  // ------------------------------------------------------------------
  // Public API
  // ------------------------------------------------------------------

  async run(task: string): Promise<ReflexionAgentResult> {
    const allTrajectories: TrajectoryStep[][] = [];
    const reflections: ReflectionResult[] = [];
    let totalIterations = 0;
    let totalToolCalls = 0;
    let totalTokens = 0;
    let finalAnswer = "";
    let success = false;
    let cycles = 0;

    let currentTask = task;
    const accumulatedLessons: string[] = [];

    for (let cycle = 0; cycle < this.maxReflectionCycles; cycle++) {
      cycles++;

      // Build enhanced system prompt with accumulated lessons
      let enhancedPrompt = this.options.systemPrompt ?? "";
      if (accumulatedLessons.length > 0) {
        const lessonsText = accumulatedLessons
          .map((l) => `- ${l}`)
          .join("\n");
        enhancedPrompt = `${enhancedPrompt}\n\n## Previous Attempts & Lessons Learned\n\n${lessonsText}\n\nPlease apply these lessons in your approach.`;
      }

      // --- Execute ---
      const loop = new AgentLoop(this.client, this.toolExecutor, {
        tools: this.options.tools,
        systemPrompt: enhancedPrompt,
        model: this.model,
        maxIterations: this.maxIterationsPerAttempt,
        maxTokensPerResponse: this.maxTokensPerResponse,
      });
      const loopResult = await loop.run(currentTask);

      allTrajectories.push(loopResult.trajectory);
      totalIterations += loopResult.iterations;
      totalToolCalls += loopResult.toolCallsMade;
      totalTokens += loopResult.totalTokens;

      // --- Reflect ---
      const reflection = await this.reflect(loopResult.trajectory);
      reflections.push(reflection);

      if (reflection.success) {
        finalAnswer = loopResult.answer;
        success = true;
        break;
      }

      if (!reflection.shouldRetry) {
        finalAnswer =
          `${loopResult.answer}\n\n` +
          `[Reflection determined no further improvement is likely. ` +
          `Confidence: ${(reflection.confidence * 100).toFixed(0)}%]`;
        break;
      }

      // --- Adjust ---
      accumulatedLessons.push(...reflection.lessonsLearned);
      currentTask =
        `${task}\n\n` +
        `[Strategy Adjustment from Previous Attempt]:\n` +
        reflection.strategyAdjustment;
    }

    if (!success && cycles >= this.maxReflectionCycles) {
      finalAnswer =
        `${finalAnswer}\n\n` +
        `[Max reflection cycles (${this.maxReflectionCycles}) reached. ` +
        `Best effort result returned.]`;
    }

    return {
      success,
      answer: finalAnswer,
      totalIterations,
      totalToolCalls,
      totalTokens,
      reflectionCycles: cycles,
      allTrajectories,
      reflections,
    };
  }

  // ------------------------------------------------------------------
  // Reflection engine
  // ------------------------------------------------------------------

  async reflect(trajectory: TrajectoryStep[]): Promise<ReflectionResult> {
    const trajectoryText = this.formatTrajectory(trajectory);

    const reflectionPrompt =
      "You are an agent strategy evaluator. Analyze the following " +
      "agent execution trajectory and determine:\n\n" +
      "1. Did the agent successfully complete the task? (yes/no)\n" +
      "2. What went well? (list specific effective actions)\n" +
      "3. What went wrong or was suboptimal? (list specific issues)\n" +
      "4. Should the agent retry with a different strategy? (yes/no)\n" +
      "5. If retrying, what specific adjustments should be made?\n" +
      "6. Your confidence in this assessment (0.0 to 1.0)\n\n" +
      "Respond in JSON format.\n\n" +
      "Trajectory:\n" +
      trajectoryText;

    const response = await this.client.messages.create({
      model: this.model,
      max_tokens: 1024,
      messages: [{ role: "user", content: reflectionPrompt }],
    });

    const text = this.extractText(
      response.content as { type: string; text?: string }[],
    );
    return this.parseReflection(text);
  }

  // ------------------------------------------------------------------
  // Internal helpers
  // ------------------------------------------------------------------

  private formatTrajectory(trajectory: TrajectoryStep[]): string {
    return trajectory
      .map((step) => {
        const iter = step.iteration;
        if (step.type === "tool_call") {
          return `[Iter ${iter}] Tool: ${step.tool} (success=${step.success})`;
        }
        if (step.type === "complete") {
          const text = (step.text ?? "").substring(0, 200);
          return `[Iter ${iter}] COMPLETE: ${text}`;
        }
        if (step.type === "max_iterations") {
          return `[Iter ${iter}] MAX_ITERATIONS reached`;
        }
        if (step.type === "stalled") {
          return `[Iter ${iter}] STALLED (no tool calls)`;
        }
        return `[Iter ${iter}] ${step.type}`;
      })
      .join("\n");
  }

  private extractText(
    blocks: { type: string; text?: string }[],
  ): string {
    return blocks
      .filter((b) => b.type === "text")
      .map((b) => b.text ?? "")
      .join("\n");
  }

  private parseReflection(text: string): ReflectionResult {
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
      return {
        success: data.task_completed ?? data.success ?? false,
        strategyAdjustment:
          data.strategy_adjustment ??
          data.adjustments ??
          "Retry with improved approach.",
        lessonsLearned: data.lessons_learned ?? data.lessons ?? [],
        shouldRetry: data.should_retry ?? true,
        confidence: data.confidence ?? 0.5,
      };
    } catch {
      return {
        success: false,
        strategyAdjustment:
          "Re-evaluate the approach and try a different strategy.",
        lessonsLearned: [
          "Previous approach did not yield clear results.",
        ],
        shouldRetry: true,
        confidence: 0.3,
      };
    }
  }
}
