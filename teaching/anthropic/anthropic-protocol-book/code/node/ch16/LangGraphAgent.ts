/**
 * Chapter 16: LangGraph Agent with Anthropic Claude (TypeScript).
 *
 * Demonstrates:
 *   - StateGraph construction with nodes, edges, conditional edges
 *   - Checkpointing with MemorySaver
 *   - Human-in-the-Loop via interruptBefore
 *   - Complete ReAct agent loop with tool calling
 */

import { ChatAnthropic } from "@langchain/anthropic";
import { AIMessage, HumanMessage, ToolMessage } from "@langchain/core/messages";
import type { BaseMessage } from "@langchain/core/messages";
import { tool } from "@langchain/core/tools";
import { z } from "zod";
import { StateGraph, START, END, MemorySaver } from "@langchain/langgraph";
import type { CompiledStateGraph } from "@langchain/langgraph";

// ---------------------------------------------------------------------------
// State definition
// ---------------------------------------------------------------------------

/**
 * The state shape for our agent graph.
 * Uses a standard messages key with a reducer that appends new messages.
 */
export interface AgentState {
  messages: BaseMessage[];
}

// ---------------------------------------------------------------------------
// Tool definitions (using @langchain/core/tools)
// ---------------------------------------------------------------------------

const getWeather = tool(
  async ({ location }: { location: string }): Promise<string> => {
    const weatherData: Record<string, string> = {
      "san francisco": "Sunny, 72°F, wind 5mph NW",
      "new york": "Cloudy, 58°F, wind 10mph NE",
      london: "Rainy, 12°C, wind 8m/s SW",
      beijing: "Partly cloudy, 25°C, wind 3m/s SE",
    };
    return (
      weatherData[location.toLowerCase()] ??
      `No weather data for ${location}`
    );
  },
  {
    name: "get_weather",
    description: "Get the current weather for a location. Input is city name.",
    schema: z.object({
      location: z.string().describe("The city name, e.g. 'San Francisco'"),
    }),
  },
);

const search = tool(
  async ({ query }: { query: string }): Promise<string> => {
    const knowledge: Record<string, string> = {
      "capital of france": "Paris is the capital of France.",
      "largest planet": "Jupiter is the largest planet in our solar system.",
      "water boiling point": "Water boils at 100°C (212°F) at sea level.",
    };
    const queryLower = query.toLowerCase();
    for (const [key, value] of Object.entries(knowledge)) {
      if (key.includes(queryLower) || queryLower.includes(key)) {
        return value;
      }
    }
    return `No relevant results for: ${query}`;
  },
  {
    name: "search",
    description: "Search for factual information on a topic.",
    schema: z.object({
      query: z.string().describe("The search query"),
    }),
  },
);

const calc = tool(
  async ({ expression }: { expression: string }): Promise<string> => {
    const allowed = new Set("0123456789+-*/().% ");
    if (![...expression].every((c) => allowed.has(c))) {
      return "Error: expression contains disallowed characters";
    }
    try {
      const result = Function(`"use strict"; return (${expression})`)();
      return String(result);
    } catch (e) {
      return `Error evaluating expression: ${e}`;
    }
  },
  {
    name: "calculator",
    description:
      "Evaluate a mathematical expression. Supports +, -, *, /, (), %.",
    schema: z.object({
      expression: z.string().describe("The math expression to evaluate"),
    }),
  },
);

export const DEFAULT_TOOLS = [getWeather, search, calc];

// ---------------------------------------------------------------------------
// Builder: create a standard ReAct agent
// ---------------------------------------------------------------------------

export interface BuildAgentOptions {
  model: ChatAnthropic;
  tools?: typeof DEFAULT_TOOLS;
  checkpointer?: "memory" | "none";
  interruptBefore?: string[];
}

/**
 * Build a ReAct-style LangGraph agent.
 *
 * Graph structure:
 *
 *   START -> callModel ──(tool_calls?)──> tools -> callModel
 *                     └──(no calls)──> END
 */
export async function buildReactAgent(
  options: BuildAgentOptions,
): Promise<CompiledStateGraph<AgentState, Partial<AgentState>, string>> {
  const { model, tools = DEFAULT_TOOLS, checkpointer = "none", interruptBefore } = options;

  // Bind tools to the model
  const modelWithTools = model.bindTools(tools);

  // Node: call the model
  const callModel = async (
    state: AgentState,
  ): Promise<Partial<AgentState>> => {
    const response = await modelWithTools.invoke(state.messages);
    return { messages: [response] };
  };

  // Node: execute tool calls
  const toolsByName = new Map(tools.map((t) => [t.name, t]));

  const executeTools = async (
    state: AgentState,
  ): Promise<Partial<AgentState>> => {
    const lastMessage = state.messages[state.messages.length - 1];
    if (!lastMessage) return { messages: [] };

    const aiMsg = lastMessage as AIMessage;
    const toolCalls = (aiMsg as any).tool_calls;
    if (!toolCalls || toolCalls.length === 0) {
      return { messages: [] };
    }

    const results: ToolMessage[] = [];
    for (const tc of toolCalls) {
      const tool = toolsByName.get(tc.name);
      const observation = tool
        ? String(await tool.invoke(tc.args))
        : `Error: unknown tool '${tc.name}'`;

      results.push(
        new ToolMessage({
          content: observation,
          tool_call_id: tc.id ?? "",
        }),
      );
    }

    return { messages: results };
  };

  // Routing function
  const shouldContinue = (
    state: AgentState,
  ): "tools" | "__end__" => {
    const lastMessage = state.messages[state.messages.length - 1];
    if (!lastMessage) return "__end__";
    const aiMsg = lastMessage as AIMessage;
    const toolCalls = (aiMsg as any).tool_calls;
    if (toolCalls && toolCalls.length > 0) {
      return "tools";
    }
    return "__end__";
  };

  // Build the graph
  const builder = new StateGraph<AgentState>({
    channels: { messages: { reducer: (a, b) => [...(a ?? []), ...(b ?? [])] } },
  });

  builder.addNode("callModel", callModel);
  builder.addNode("tools", executeTools);

  builder.addEdge(START, "callModel");
  builder.addConditionalEdges("callModel", shouldContinue, {
    tools: "tools",
    __end__: END,
  });
  builder.addEdge("tools", "callModel");

  // Compile with optional checkpointer
  const compilerOptions: Record<string, unknown> = {};
  if (checkpointer === "memory") {
    compilerOptions.checkpointer = new MemorySaver();
  }
  if (interruptBefore) {
    compilerOptions.interruptBefore = interruptBefore;
  }

  return builder.compile(compilerOptions) as CompiledStateGraph<
    AgentState,
    Partial<AgentState>,
    string
  >;
}

// ---------------------------------------------------------------------------
// Agent with in-memory checkpointing
// ---------------------------------------------------------------------------

export async function buildAgentWithMemory(
  model: ChatAnthropic,
  tools?: typeof DEFAULT_TOOLS,
): Promise<CompiledStateGraph<AgentState, Partial<AgentState>, string>> {
  return buildReactAgent({ model, tools, checkpointer: "memory" });
}

// ---------------------------------------------------------------------------
// Agent with Human-in-the-Loop (interrupt before tools)
// ---------------------------------------------------------------------------

export async function buildAgentWithHITL(
  model: ChatAnthropic,
  tools?: typeof DEFAULT_TOOLS,
): Promise<CompiledStateGraph<AgentState, Partial<AgentState>, string>> {
  return buildReactAgent({
    model,
    tools,
    checkpointer: "memory",
    interruptBefore: ["tools"],
  });
}

// ---------------------------------------------------------------------------
// Helper: run agent
// ---------------------------------------------------------------------------

export interface AgentRunResult {
  messages: BaseMessage[];
  finalResponse: string;
}

export async function runAgent(
  agent: CompiledStateGraph<AgentState, Partial<AgentState>, string>,
  userInput: string,
  threadId?: string,
): Promise<AgentRunResult> {
  const config = {
    configurable: {
      thread_id: threadId ?? `thread-${Date.now()}`,
    },
  };

  const result = await agent.invoke(
    { messages: [new HumanMessage(userInput)] },
    config,
  );

  const messages = result.messages ?? [];
  const lastMessage = messages[messages.length - 1];
  const finalResponse =
    lastMessage && "content" in lastMessage
      ? typeof lastMessage.content === "string"
        ? lastMessage.content
        : JSON.stringify(lastMessage.content)
      : "";

  return { messages, finalResponse };
}
