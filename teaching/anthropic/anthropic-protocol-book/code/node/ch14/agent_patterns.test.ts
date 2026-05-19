/**
 * Tests for Chapter 14: Agent Loop, Reflexion Agent, Sub-Agent Orchestrator,
 * and Supervisor-Worker patterns (TypeScript).
 *
 * Uses mock Anthropic client responses. No real API calls are made.
 */

import { describe, it, expect, beforeEach } from "vitest";
import {
  AgentLoop,
  AnthropicClient,
  AnthropicResponse,
  ContentBlock,
  ToolCallable,
  ToolResult,
} from "./AgentLoop";
import { ReflexionAgent } from "./ReflexionAgent";
import { SubAgentOrchestrator } from "./SubAgentOrchestrator";
import { SupervisorWorker } from "./SupervisorWorker";

// ============================================================================
// Mock Client
// ============================================================================

class MockClient implements AnthropicClient {
  public callCount = 0;

  constructor(private readonly responses: AnthropicResponse[]) {}

  messages = {
    create: async (
      _params: Record<string, unknown>,
    ): Promise<AnthropicResponse> => {
      const resp = this.responses[this.callCount];
      this.callCount++;
      if (resp) return resp;
      return {
        stop_reason: "end_turn",
        content: [{ type: "text", text: "Default response" }],
        usage: { input_tokens: 10, output_tokens: 10 },
      };
    },
  };
}

// ============================================================================
// Tool Executor
// ============================================================================

function makeToolExecutor(
  toolsMap: Record<string, (...args: any[]) => unknown>,
): ToolCallable {
  return (name: string, input: Record<string, unknown>): ToolResult => {
    const handler = toolsMap[name];
    if (!handler) {
      return {
        toolUseId: "unknown",
        success: false,
        content: `Unknown tool: ${name}`,
        error: `Tool '${name}' not found`,
      };
    }
    try {
      const result = handler(input);
      return {
        toolUseId: "tool_001",
        success: true,
        content: String(result),
      };
    } catch (e: unknown) {
      return {
        toolUseId: "tool_001",
        success: false,
        content: String(e),
        error: e instanceof Error ? e.message : String(e),
      };
    }
  };
}

// ============================================================================
// AgentLoop Tests
// ============================================================================

describe("AgentLoop", () => {
  it("completes in one turn with no tools", async () => {
    const client = new MockClient([
      {
        stop_reason: "end_turn",
        content: [{ type: "text", text: "The answer is 42." }],
        usage: { input_tokens: 50, output_tokens: 10 },
      },
    ]);
    const executor = makeToolExecutor({});
    const loop = new AgentLoop(client, executor);

    const result = await loop.run("What is the answer?");

    expect(result.success).toBe(true);
    expect(result.answer).toContain("42");
    expect(result.iterations).toBe(1);
    expect(result.toolCallsMade).toBe(0);
    expect(result.trajectory).toHaveLength(1);
    expect(result.trajectory[0]!.type).toBe("complete");
  });

  it("calls a tool then completes", async () => {
    const client = new MockClient([
      {
        stop_reason: "tool_use",
        content: [
          {
            type: "tool_use",
            id: "toolu_001",
            name: "get_weather",
            input: { location: "Beijing" },
          },
        ],
        usage: { input_tokens: 50, output_tokens: 20 },
      },
      {
        stop_reason: "end_turn",
        content: [
          { type: "text", text: "Beijing is sunny, 24C." },
        ],
        usage: { input_tokens: 80, output_tokens: 10 },
      },
    ]);
    const executor = makeToolExecutor({
      get_weather: (input: { location: string }) =>
        `Weather in ${input.location}: sunny, 24C`,
    });
    const loop = new AgentLoop(client, executor);

    const result = await loop.run("Weather in Beijing?");

    expect(result.success).toBe(true);
    expect(result.answer).toContain("sunny");
    expect(result.iterations).toBe(2);
    expect(result.toolCallsMade).toBe(1);
    expect(result.trajectory[0]!.type).toBe("tool_call");
    expect(result.trajectory[1]!.type).toBe("complete");
  });

  it("stops at maxIterations", async () => {
    const responses: AnthropicResponse[] = Array.from(
      { length: 5 },
      (_, i) => ({
        stop_reason: "tool_use",
        content: [
          {
            type: "tool_use",
            id: `toolu_${i}`,
            name: "ping",
            input: {},
          },
        ],
        usage: { input_tokens: 50, output_tokens: 10 },
      }),
    );

    const client = new MockClient(responses);
    const executor = makeToolExecutor({ ping: () => "pong" });
    const loop = new AgentLoop(client, executor, { maxIterations: 3 });

    const result = await loop.run("Ping forever");

    expect(result.iterations).toBe(3);
    expect(result.answer.toLowerCase()).toContain("maximum iterations");
    expect(result.toolCallsMade).toBe(3);
  });

  it("handles multiple tool calls in one turn", async () => {
    const client = new MockClient([
      {
        stop_reason: "tool_use",
        content: [
          {
            type: "tool_use",
            id: "t1",
            name: "get_weather",
            input: { location: "Tokyo" },
          },
          {
            type: "tool_use",
            id: "t2",
            name: "get_time",
            input: { timezone: "Asia/Tokyo" },
          },
        ],
        usage: { input_tokens: 60, output_tokens: 30 },
      },
      {
        stop_reason: "end_turn",
        content: [
          { type: "text", text: "Tokyo: sunny, 14:30 JST." },
        ],
        usage: { input_tokens: 100, output_tokens: 10 },
      },
    ]);
    const executor = makeToolExecutor({
      get_weather: (input: { location: string }) =>
        `Weather in ${input.location}: sunny`,
      get_time: (input: { timezone: string }) =>
        `Time in ${input.timezone}: 14:30`,
    });
    const loop = new AgentLoop(client, executor);

    const result = await loop.run("Tokyo weather and time?");

    expect(result.success).toBe(true);
    expect(result.toolCallsMade).toBe(2);
    expect(result.iterations).toBe(2);
  });

  it("handles tool execution errors gracefully", async () => {
    const client = new MockClient([
      {
        stop_reason: "tool_use",
        content: [
          {
            type: "tool_use",
            id: "t1",
            name: "failing_tool",
            input: {},
          },
        ],
        usage: { input_tokens: 50, output_tokens: 10 },
      },
      {
        stop_reason: "end_turn",
        content: [
          { type: "text", text: "The tool failed, but I can help." },
        ],
        usage: { input_tokens: 80, output_tokens: 10 },
      },
    ]);
    const executor = makeToolExecutor({
      failing_tool: () => {
        throw new Error("Boom");
      },
    });
    const loop = new AgentLoop(client, executor);

    const result = await loop.run("Try failing tool");

    expect(result.toolCallsMade).toBe(1);
    expect(result.trajectory[0]!.success).toBe(false);
  });

  it("handles stalled state (tool_use with no valid blocks)", async () => {
    const client = new MockClient([
      {
        stop_reason: "tool_use",
        content: [
          { type: "text", text: "I think I should use a tool..." },
        ],
        usage: { input_tokens: 30, output_tokens: 10 },
      },
    ]);
    const executor = makeToolExecutor({});
    const loop = new AgentLoop(client, executor);

    const result = await loop.run("Do something");

    expect(result.iterations).toBe(1);
    expect(result.trajectory[0]!.type).toBe("stalled");
  });

  it("records complete trajectory", async () => {
    const client = new MockClient([
      {
        stop_reason: "tool_use",
        content: [
          {
            type: "tool_use",
            id: "t1",
            name: "step1",
            input: { a: 1 },
          },
        ],
        usage: { input_tokens: 30, output_tokens: 10 },
      },
      {
        stop_reason: "end_turn",
        content: [{ type: "text", text: "Done." }],
        usage: { input_tokens: 50, output_tokens: 5 },
      },
    ]);
    const executor = makeToolExecutor({
      step1: (input: { a: number }) => `Result: ${input.a}`,
    });
    const loop = new AgentLoop(client, executor);

    const result = await loop.run("Task");

    expect(result.trajectory).toHaveLength(2);
    expect(result.trajectory[0]!.tool).toBe("step1");
    expect(result.trajectory[0]!.input).toEqual({ a: 1 });
    expect(result.trajectory[1]!.type).toBe("complete");
  });
});

// ============================================================================
// ReflexionAgent Tests
// ============================================================================

describe("ReflexionAgent", () => {
  it("succeeds on first attempt", async () => {
    const client = new MockClient([
      // First attempt: success
      {
        stop_reason: "end_turn",
        content: [
          { type: "text", text: "Task completed successfully." },
        ],
        usage: { input_tokens: 50, output_tokens: 10 },
      },
      // Reflection: evaluator confirms success
      {
        stop_reason: "end_turn",
        content: [
          {
            type: "text",
            text: JSON.stringify({
              task_completed: true,
              strategy_adjustment: "",
              lessons_learned: ["Good approach"],
              should_retry: false,
              confidence: 0.95,
            }),
          },
        ],
        usage: { input_tokens: 50, output_tokens: 20 },
      },
    ]);
    const executor = makeToolExecutor({});
    const agent = new ReflexionAgent(client, executor, {
      maxReflectionCycles: 3,
    });

    const result = await agent.run("Simple task");

    expect(result.success).toBe(true);
    expect(result.reflectionCycles).toBe(1);
    expect(result.reflections).toHaveLength(1);
    expect(result.reflections[0]!.success).toBe(true);
  });

  it("retries after failure", async () => {
    const client = new MockClient([
      // First attempt: max iterations (failed)
      {
        stop_reason: "tool_use",
        content: [
          {
            type: "tool_use",
            id: "t1",
            name: "bad_tool",
            input: {},
          },
        ],
        usage: { input_tokens: 30, output_tokens: 10 },
      },
      // Reflection: not successful, retry
      {
        stop_reason: "end_turn",
        content: [
          {
            type: "text",
            text: JSON.stringify({
              task_completed: false,
              strategy_adjustment: "Try a different approach",
              lessons_learned: ["Bad tool did not help"],
              should_retry: true,
              confidence: 0.4,
            }),
          },
        ],
        usage: { input_tokens: 50, output_tokens: 20 },
      },
      // Second attempt: success
      {
        stop_reason: "end_turn",
        content: [
          { type: "text", text: "Task done with new approach." },
        ],
        usage: { input_tokens: 50, output_tokens: 10 },
      },
      // Second reflection: success
      {
        stop_reason: "end_turn",
        content: [
          {
            type: "text",
            text: JSON.stringify({
              task_completed: true,
              strategy_adjustment: "",
              lessons_learned: ["New approach worked"],
              should_retry: false,
              confidence: 0.9,
            }),
          },
        ],
        usage: { input_tokens: 50, output_tokens: 20 },
      },
    ]);
    const executor = makeToolExecutor({
      bad_tool: () => "some data",
    });
    const agent = new ReflexionAgent(client, executor, {
      maxIterationsPerAttempt: 1,
      maxReflectionCycles: 3,
    });

    const result = await agent.run("Complex task");

    expect(result.success).toBe(true);
    expect(result.reflectionCycles).toBe(2);
    expect(result.reflections[0]!.success).toBe(false);
    expect(result.reflections[1]!.success).toBe(true);
  });

  it("handles malformed reflection JSON with fallback", async () => {
    const client = new MockClient([
      // First attempt
      {
        stop_reason: "end_turn",
        content: [{ type: "text", text: "Done." }],
        usage: { input_tokens: 30, output_tokens: 10 },
      },
      // Malformed reflection -> triggers retry (fallback shouldRetry=true)
      {
        stop_reason: "end_turn",
        content: [
          {
            type: "text",
            text: "This is not valid JSON at all.",
          },
        ],
        usage: { input_tokens: 30, output_tokens: 10 },
      },
      // Second attempt (retry)
      {
        stop_reason: "end_turn",
        content: [{ type: "text", text: "Done again." }],
        usage: { input_tokens: 30, output_tokens: 10 },
      },
      // Second reflection (also malformed)
      {
        stop_reason: "end_turn",
        content: [
          {
            type: "text",
            text: "Not JSON either.",
          },
        ],
        usage: { input_tokens: 30, output_tokens: 10 },
      },
    ]);
    const executor = makeToolExecutor({});
    const agent = new ReflexionAgent(client, executor, {
      maxReflectionCycles: 2,
    });

    const result = await agent.run("Task");

    // Fallback defaults shouldRetry=true triggers second cycle
    expect(result.reflections).toHaveLength(2);
    expect(result.reflections[0]!.success).toBe(false);
    expect(result.reflections[0]!.shouldRetry).toBe(true);
    expect(result.reflections[1]!.success).toBe(false); // Also fallback
  });

  it("stops at max reflection cycles", async () => {
    const responses: AnthropicResponse[] = [];
    for (let i = 0; i < 3; i++) {
      responses.push({
        stop_reason: "end_turn",
        content: [{ type: "text", text: "Done." }],
        usage: { input_tokens: 30, output_tokens: 10 },
      });
      responses.push({
        stop_reason: "end_turn",
        content: [
          {
            type: "text",
            text: JSON.stringify({
              task_completed: false,
              strategy_adjustment: "Keep trying",
              lessons_learned: ["Not yet"],
              should_retry: true,
              confidence: 0.3,
            }),
          },
        ],
        usage: { input_tokens: 30, output_tokens: 20 },
      });
    }

    const client = new MockClient(responses);
    const executor = makeToolExecutor({});
    const agent = new ReflexionAgent(client, executor, {
      maxReflectionCycles: 2,
    });

    const result = await agent.run("Task");

    expect(result.reflectionCycles).toBe(2);
    expect(result.answer).toContain("Max reflection cycles");
  });
});

// ============================================================================
// SubAgentOrchestrator Tests
// ============================================================================

describe("SubAgentOrchestrator", () => {
  it("registers and lists sub-agents", () => {
    const client = new MockClient([]);
    const executor = makeToolExecutor({});
    const orch = new SubAgentOrchestrator(client, executor);
    orch.registerSubAgent("reviewer", "Code reviewer", "You review code");
    orch.registerSubAgent("tester", "Test writer", "You write tests");

    const agents = orch.listSubAgents();
    expect(agents).toHaveLength(2);
    expect(agents[0]!.name).toBe("reviewer");
    expect(agents[1]!.name).toBe("tester");
  });

  it("throws on duplicate registration", () => {
    const client = new MockClient([]);
    const executor = makeToolExecutor({});
    const orch = new SubAgentOrchestrator(client, executor);
    orch.registerSubAgent("r", "desc", "prompt");
    expect(() =>
      orch.registerSubAgent("r", "desc2", "prompt2"),
    ).toThrow(/already registered/);
  });

  it("unregisters sub-agents", () => {
    const client = new MockClient([]);
    const executor = makeToolExecutor({});
    const orch = new SubAgentOrchestrator(client, executor);
    orch.registerSubAgent("r", "desc", "prompt");
    expect(orch.listSubAgents()).toHaveLength(1);
    orch.unregisterSubAgent("r");
    expect(orch.listSubAgents()).toHaveLength(0);
  });

  it("decomposes simple task without sub-agents", async () => {
    const client = new MockClient([
      {
        stop_reason: "end_turn",
        content: [
          {
            type: "text",
            text: JSON.stringify({
              subtasks: [
                {
                  agent_name: "main",
                  task_description: "Do it",
                  priority: 0,
                },
              ],
            }),
          },
        ],
        usage: { input_tokens: 30, output_tokens: 10 },
      },
    ]);
    const executor = makeToolExecutor({});
    const orch = new SubAgentOrchestrator(client, executor);

    const subtasks = await orch.decompose("Simple task");
    expect(subtasks).toHaveLength(1);
    expect(subtasks[0]!.agentName).toBe("main");
  });

  it("decomposes task with registered sub-agents", async () => {
    const client = new MockClient([
      {
        stop_reason: "end_turn",
        content: [
          {
            type: "text",
            text: JSON.stringify({
              subtasks: [
                {
                  agent_name: "reviewer",
                  task_description: "Review code",
                  priority: 0,
                },
                {
                  agent_name: "tester",
                  task_description: "Write tests",
                  priority: 1,
                },
              ],
            }),
          },
        ],
        usage: { input_tokens: 30, output_tokens: 10 },
      },
    ]);
    const executor = makeToolExecutor({});
    const orch = new SubAgentOrchestrator(client, executor);
    orch.registerSubAgent("reviewer", "Reviews code", "Review prompt");
    orch.registerSubAgent("tester", "Writes tests", "Test prompt");

    const subtasks = await orch.decompose("Review and test");
    expect(subtasks).toHaveLength(2);
    expect(subtasks[0]!.agentName).toBe("reviewer");
    expect(subtasks[1]!.agentName).toBe("tester");
  });

  it("dispatches to correct sub-agent", async () => {
    const client = new MockClient([
      {
        stop_reason: "end_turn",
        content: [
          { type: "text", text: "Code reviewed: no issues found." },
        ],
        usage: { input_tokens: 30, output_tokens: 10 },
      },
    ]);
    const executor = makeToolExecutor({});
    const orch = new SubAgentOrchestrator(client, executor);
    orch.registerSubAgent("reviewer", "Reviews code", "You review code");

    const result = await orch.dispatch({
      agentName: "reviewer",
      taskDescription: "Review auth.py",
    });

    expect(result.success).toBe(true);
    expect(result.agentName).toBe("reviewer");
    expect(result.result.answer.toLowerCase()).toContain("reviewed");
  });

  it("falls back to main for unknown agent", async () => {
    const client = new MockClient([
      {
        stop_reason: "end_turn",
        content: [{ type: "text", text: "Done by main." }],
        usage: { input_tokens: 30, output_tokens: 10 },
      },
    ]);
    const executor = makeToolExecutor({});
    const orch = new SubAgentOrchestrator(client, executor);

    const result = await orch.dispatch({
      agentName: "nonexistent",
      taskDescription: "Do something",
    });

    expect(result.agentName).toBe("main");
    expect(result.result.answer).toContain("Done by main");
  });

  it("synthesizes multiple results", async () => {
    const client = new MockClient([
      {
        stop_reason: "end_turn",
        content: [
          {
            type: "text",
            text: "Synthesized: Code is clean and tests pass.",
          },
        ],
        usage: { input_tokens: 30, output_tokens: 10 },
      },
    ]);
    const executor = makeToolExecutor({});
    const orch = new SubAgentOrchestrator(client, executor);

    const final = await orch.synthesize("Review and test", [
      {
        agentName: "reviewer",
        taskDescription: "Review",
        success: true,
        result: {
          success: true,
          answer: "Code is clean",
          iterations: 1,
          toolCallsMade: 0,
          totalTokens: 20,
          trajectory: [],
        },
      },
      {
        agentName: "tester",
        taskDescription: "Test",
        success: true,
        result: {
          success: true,
          answer: "All tests pass",
          iterations: 1,
          toolCallsMade: 0,
          totalTokens: 20,
          trajectory: [],
        },
      },
    ]);

    expect(final.success).toBe(true);
    expect(final.answer.toLowerCase()).toContain("clean");
  });
});

// ============================================================================
// SupervisorWorker Tests
// ============================================================================

describe("SupervisorWorker", () => {
  it("runs simple task with no workers", async () => {
    const client = new MockClient([
      // Plan
      {
        stop_reason: "end_turn",
        content: [
          {
            type: "text",
            text: JSON.stringify({
              plan: [
                {
                  worker_name: "__main__",
                  description: "Answer the question",
                  expected_output: "An answer",
                  constraints: [],
                },
              ],
            }),
          },
        ],
        usage: { input_tokens: 30, output_tokens: 10 },
      },
      // Execute
      {
        stop_reason: "end_turn",
        content: [{ type: "text", text: "The answer is 42." }],
        usage: { input_tokens: 30, output_tokens: 10 },
      },
      // Synthesize
      {
        stop_reason: "end_turn",
        content: [
          { type: "text", text: "Final: The answer is 42." },
        ],
        usage: { input_tokens: 30, output_tokens: 10 },
      },
    ]);
    const executor = makeToolExecutor({});
    const sw = new SupervisorWorker(client, executor);

    const result = await sw.run("What is the answer?");

    expect(result.success).toBe(true);
    expect(result.answer).toContain("42");
    expect(result.plan).toHaveLength(1);
    expect(result.plan[0]!.workerName).toBe("__main__");
  });

  it("registers and lists workers", () => {
    const client = new MockClient([]);
    const executor = makeToolExecutor({});
    const sw = new SupervisorWorker(client, executor);
    sw.registerWorker("analyzer", "Data analyzer", "Analyze data");

    const workers = sw.listWorkers();
    expect(workers).toHaveLength(1);
    expect(workers[0]!.name).toBe("analyzer");
  });

  it("throws on duplicate worker registration", () => {
    const client = new MockClient([]);
    const executor = makeToolExecutor({});
    const sw = new SupervisorWorker(client, executor);
    sw.registerWorker("w", "desc", "prompt");
    expect(() => sw.registerWorker("w", "desc2", "prompt2")).toThrow(
      /already registered/,
    );
  });

  it("plans work across workers", async () => {
    const client = new MockClient([
      {
        stop_reason: "end_turn",
        content: [
          {
            type: "text",
            text: JSON.stringify({
              plan: [
                {
                  worker_name: "analyzer",
                  description: "Analyze data",
                  expected_output: "Analysis report",
                  constraints: [],
                },
              ],
            }),
          },
        ],
        usage: { input_tokens: 30, output_tokens: 10 },
      },
    ]);
    const executor = makeToolExecutor({});
    const sw = new SupervisorWorker(client, executor);
    sw.registerWorker("analyzer", "Analyzes data", "Analyze prompt");

    const plan = await sw.plan("Analyze the dataset");
    expect(plan).toHaveLength(1);
    expect(plan[0]!.workerName).toBe("analyzer");
  });

  it("worker executes with its own tools", async () => {
    const client = new MockClient([
      // Plan
      {
        stop_reason: "end_turn",
        content: [
          {
            type: "text",
            text: JSON.stringify({
              plan: [
                {
                  worker_name: "searcher",
                  description: "Search for info",
                  expected_output: "Search results",
                  constraints: [],
                },
              ],
            }),
          },
        ],
        usage: { input_tokens: 30, output_tokens: 10 },
      },
      // Worker: tool call then complete
      {
        stop_reason: "tool_use",
        content: [
          {
            type: "tool_use",
            id: "t1",
            name: "search",
            input: { query: "latest docs" },
          },
        ],
        usage: { input_tokens: 30, output_tokens: 10 },
      },
      {
        stop_reason: "end_turn",
        content: [
          { type: "text", text: "Found 5 relevant results." },
        ],
        usage: { input_tokens: 30, output_tokens: 10 },
      },
      // Synthesize
      {
        stop_reason: "end_turn",
        content: [
          {
            type: "text",
            text: "Synthesized: 5 results found.",
          },
        ],
        usage: { input_tokens: 30, output_tokens: 10 },
      },
    ]);

    const searchTools = [
      {
        name: "search",
        description: "Search the web",
        input_schema: {
          type: "object",
          properties: { query: { type: "string" } },
          required: ["query"],
        },
      },
    ];

    const executor = makeToolExecutor({
      search: (input: { query: string }) => `Results for ${input.query}`,
    });
    const sw = new SupervisorWorker(client, executor);
    sw.registerWorker("searcher", "Web searcher", "You search the web", {
      tools: searchTools,
    });

    const result = await sw.run("Search for latest docs");
    expect(result.success).toBe(true);
    expect(result.totalToolCalls).toBeGreaterThanOrEqual(1);
  });
});
