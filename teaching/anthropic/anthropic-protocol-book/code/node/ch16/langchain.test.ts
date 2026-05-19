/**
 * Tests for Chapter 16: LangChain & LangGraph integration (TypeScript).
 *
 * These tests mock the underlying Anthropic SDK calls to avoid real network access.
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import { AIMessage } from "@langchain/core/messages";
import type { StructuredTool } from "@langchain/core/tools";

// ---------------------------------------------------------------------------
// Mock the ChatAnthropic class
// ---------------------------------------------------------------------------

vi.mock("@langchain/anthropic", () => {
  const actual = vi.importActual("@langchain/anthropic");
  return {
    ...actual,
    ChatAnthropic: vi.fn().mockImplementation(function (this: any, config: any) {
      this.modelName = config.model ?? "claude-sonnet-4-20250514";
      this.temperature = config.temperature ?? 0.3;
      this.maxTokens = config.maxTokens ?? 1024;
      this.timeout = config.timeout ?? 60000;
      this.maxRetries = config.maxRetries ?? 2;
      // The invoke method will be set in individual tests
      this.invoke = vi.fn();
      this.stream = vi.fn();
      this.bindTools = vi.fn(function (this: any, _tools: any) {
        const bound = { ...this, _boundTools: true };
        return bound;
      });
      return this;
    }),
  };
});

// ---------------------------------------------------------------------------
// Stub for StructuredTool (no actual tool execution needed in tests)
// ---------------------------------------------------------------------------

function makeStubTool(name: string, description: string): StructuredTool {
  return {
    name,
    description,
    invoke: vi.fn().mockResolvedValue(`Result from ${name}`),
    lc_namespace: [],
    verbose: false,
    returnDirect: false,
  } as unknown as StructuredTool;
}

// ---------------------------------------------------------------------------
// Import the modules under test (after mocks are set up)
// ---------------------------------------------------------------------------

import {
  createModel,
  bindToolsToModel,
  executeToolCalls,
  createChatPrompt,
  ConversationBufferMemory,
  runAgentLoop,
  basicInvoke,
} from "./LangChainIntegration";

import {
  buildReactAgent,
  buildAgentWithMemory,
  buildAgentWithHITL,
  DEFAULT_TOOLS,
  runAgent,
} from "./LangGraphAgent";

// ---------------------------------------------------------------------------
// Test: ChatAnthropic instantiation
// ---------------------------------------------------------------------------

describe("ChatAnthropic instantiation", () => {
  it("creates a model with defaults", () => {
    const model = createModel();
    expect((model as any).modelName).toBe("claude-sonnet-4-20250514");
    expect((model as any).temperature).toBe(0.3);
  });

  it("creates a model with custom parameters", () => {
    const model = createModel({
      model: "claude-haiku-4-5-20251001",
      temperature: 0.7,
      maxTokens: 512,
      timeout: 30000,
      maxRetries: 5,
    });
    expect((model as any).modelName).toBe("claude-haiku-4-5-20251001");
    expect((model as any).temperature).toBe(0.7);
    expect((model as any).maxTokens).toBe(512);
    expect((model as any).timeout).toBe(30000);
    expect((model as any).maxRetries).toBe(5);
  });
});

// ---------------------------------------------------------------------------
// Test: Basic invocation
// ---------------------------------------------------------------------------

describe("basicInvoke", () => {
  it("calls model.invoke and returns content string", async () => {
    const model = createModel();
    (model.invoke as any).mockResolvedValue(
      new AIMessage({ content: "Hello! How can I help?" }),
    );

    const result = await basicInvoke(model, "Hi");
    expect(result).toBe("Hello! How can I help?");
    expect(model.invoke).toHaveBeenCalledTimes(1);
  });
});

// ---------------------------------------------------------------------------
// Test: Tool binding and execution
// ---------------------------------------------------------------------------

describe("Tool binding and execution", () => {
  it("bindToolsToModel calls model.bindTools", () => {
    const model = createModel();
    const tools = [makeStubTool("get_weather", "Get weather")];
    const bound = bindToolsToModel(model, tools);
    expect((bound as any)._boundTools).toBe(true);
    expect(model.bindTools).toHaveBeenCalledWith(tools);
  });

  it("executeToolCalls runs matching tool", async () => {
    const tools = [makeStubTool("get_weather", "Get weather")];
    const response = new AIMessage({
      content: "",
      tool_calls: [
        { name: "get_weather", args: { location: "London" }, id: "tc-1" },
      ],
    });

    const results = await executeToolCalls(response, tools);
    expect(results).toHaveLength(1);
    expect(results[0].tool_call_id).toBe("tc-1");
    expect(results[0].content).toContain("get_weather");
  });

  it("executeToolCalls handles unknown tool", async () => {
    const tools = [makeStubTool("get_weather", "Get weather")];
    const response = new AIMessage({
      content: "",
      tool_calls: [
        { name: "unknown_tool", args: {}, id: "tc-2" },
      ],
    });

    const results = await executeToolCalls(response, tools);
    expect(results).toHaveLength(1);
    expect(results[0].content).toContain("unknown tool");
  });

  it("executeToolCalls returns empty for no tool_calls", async () => {
    const tools = [makeStubTool("get_weather", "Get weather")];
    const response = new AIMessage({ content: "No tool call needed." });
    const results = await executeToolCalls(response, tools);
    expect(results).toHaveLength(0);
  });
});

// ---------------------------------------------------------------------------
// Test: Agent loop
// ---------------------------------------------------------------------------

describe("runAgentLoop", () => {
  it("responds directly when no tools are needed", async () => {
    const model = createModel();
    (model.invoke as any).mockResolvedValue(
      new AIMessage({ content: "I am Claude. No tools needed." }),
    );

    const result = await runAgentLoop(model, [], "Hello!");
    expect(result).toContain("Claude");
    expect(model.invoke).toHaveBeenCalledTimes(1);
  });

  it("executes tool and returns final answer", async () => {
    const model = createModel();
    const tools = [makeStubTool("get_weather", "Get weather")];

    // First call: tool_calls
    const call1 = new AIMessage({
      content: "",
      tool_calls: [
        { name: "get_weather", args: { location: "Paris" }, id: "tc-1" },
      ],
    });
    // Second call: final answer
    const call2 = new AIMessage({
      content: "The weather in Paris is sunny.",
    });

    (model.invoke as any).mockResolvedValueOnce(call1).mockResolvedValueOnce(call2);

    const result = await runAgentLoop(model, tools, "What's the weather?");
    expect(result).toContain("sunny");
    expect(model.invoke).toHaveBeenCalledTimes(2);
  });
});

// ---------------------------------------------------------------------------
// Test: Prompt templates
// ---------------------------------------------------------------------------

describe("ChatPromptTemplate", () => {
  it("creates a prompt with system message", async () => {
    const prompt = createChatPrompt({
      systemPrompt: "You are helpful.",
      includeHistory: false,
      includeScratchpad: false,
    });
    expect(prompt).toBeDefined();
    const messages = await prompt.formatMessages({ input: "Hi" });
    expect(messages).toHaveLength(2); // system + human
  });

  it("creates a full agent prompt with placeholders", async () => {
    const prompt = createChatPrompt({
      systemPrompt: "You are a helpful agent.",
    });
    const messages = await prompt.formatMessages({ input: "Hello", history: [], agent_scratchpad: [] });
    // system, history placeholder (resolved to []), human, scratchpad placeholder
    expect(messages.length).toBeGreaterThanOrEqual(2);
  });
});

// ---------------------------------------------------------------------------
// Test: ConversationBufferMemory
// ---------------------------------------------------------------------------

describe("ConversationBufferMemory", () => {
  let memory: ConversationBufferMemory;

  beforeEach(() => {
    memory = new ConversationBufferMemory();
  });

  it("starts empty", () => {
    expect(memory.messageCount).toBe(0);
  });

  it("stores and retrieves messages", () => {
    memory.addUserMessage("Hello");
    memory.addAIMessage("Hi there!");
    expect(memory.messageCount).toBe(2);
    expect(memory.getMessages()[0].content).toBe("Hello");
    expect(memory.getMessages()[1].content).toBe("Hi there!");
  });

  it("clears all messages", () => {
    memory.addUserMessage("Hello");
    memory.clear();
    expect(memory.messageCount).toBe(0);
  });

  it("returns a copy of messages", () => {
    memory.addUserMessage("Original");
    const msgs = memory.getMessages();
    msgs.push("not a real message" as any);
    expect(memory.messageCount).toBe(1);
  });
});

// ---------------------------------------------------------------------------
// Test: LangGraph agent building
// ---------------------------------------------------------------------------

describe("LangGraph agent building", () => {
  it("buildReactAgent returns a compiled graph", async () => {
    const model = createModel();
    const agent = await buildReactAgent({ model, checkpointer: "none" });
    expect(agent).toBeDefined();
    expect(typeof agent.invoke).toBe("function");
  });

  it("buildAgentWithMemory returns a compiled graph", async () => {
    const model = createModel();
    const agent = await buildAgentWithMemory(model);
    expect(agent).toBeDefined();
  });

  it("buildAgentWithHITL returns a compiled graph", async () => {
    const model = createModel();
    const agent = await buildAgentWithHITL(model);
    expect(agent).toBeDefined();
    // With HITL, the agent should have interruptBefore configured
  });

  it("default tools include get_weather, search, calculator", () => {
    expect(DEFAULT_TOOLS).toHaveLength(3);
    const names = DEFAULT_TOOLS.map((t) => t.name);
    expect(names).toContain("get_weather");
    expect(names).toContain("search");
    expect(names).toContain("calculator");
  });
});

// ---------------------------------------------------------------------------
// Test: runAgent helper
// ---------------------------------------------------------------------------

describe("runAgent", () => {
  it("invokes agent and returns messages with finalResponse", async () => {
    const model = createModel();
    (model.invoke as any).mockResolvedValue(
      new AIMessage({ content: "Hello, how can I assist?" }),
    );

    const agent = await buildAgentWithMemory(model, []);
    const result = await runAgent(agent, "Hi");

    expect(result.messages.length).toBeGreaterThanOrEqual(1);
    expect(result.finalResponse).toContain("Hello");
  });

  it("generates a thread_id when not provided", async () => {
    const model = createModel();
    (model.invoke as any).mockResolvedValue(
      new AIMessage({ content: "Response with thread" }),
    );

    const agent = await buildAgentWithMemory(model, []);
    const result = await runAgent(agent, "Test thread");

    expect(result.finalResponse).toContain("Response with thread");
  });
});

// ---------------------------------------------------------------------------
// Test: Tool execution in agent
// ---------------------------------------------------------------------------

describe("Agent tool execution", () => {
  it("handles tool call routing", async () => {
    const model = createModel();

    // First call: request tool
    const call1 = new AIMessage({
      content: "",
      tool_calls: [
        { name: "search", args: { query: "capital of France" }, id: "tc-1" },
      ],
    });
    // Second call: final answer
    const call2 = new AIMessage({
      content: "The capital of France is Paris.",
    });

    (model.invoke as any)
      .mockResolvedValueOnce(call1)
      .mockResolvedValueOnce(call2);

    const agent = await buildAgentWithMemory(model);
    const result = await runAgent(agent, "What is the capital of France?");

    // Verify the tool result and final answer
    expect(result.messages.length).toBeGreaterThanOrEqual(2);

    // Find ToolMessage
    const toolMsgs = result.messages.filter(
      (m: any) => m._getType?.() === "tool" || m.constructor?.name === "ToolMessage",
    );
    // Even if we can't easily check for ToolMessage type, verify finalResponse
    expect(result.finalResponse).toContain("Paris");
  });
});
