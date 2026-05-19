/**
 * Chapter 16: LangChain Integration with Anthropic Claude (TypeScript).
 *
 * Demonstrates:
 *   - ChatAnthropic instantiation and configuration
 *   - Tool binding with bindTools
 *   - ChatPromptTemplate with MessagesPlaceholder
 *   - ConversationBufferMemory
 *   - Agent loop with tool execution
 */

import { ChatAnthropic } from "@langchain/anthropic";
import {
  AIMessage,
  HumanMessage,
  ToolMessage,
  type BaseMessage,
} from "@langchain/core/messages";
import {
  ChatPromptTemplate,
  MessagesPlaceholder,
} from "@langchain/core/prompts";
import type { StructuredTool } from "@langchain/core/tools";

// ---------------------------------------------------------------------------
// 1. ChatAnthropic instantiation
// ---------------------------------------------------------------------------

export interface ModelConfig {
  model?: string;
  temperature?: number;
  maxTokens?: number;
  timeout?: number;
  maxRetries?: number;
}

const DEFAULT_MODEL = "claude-sonnet-4-20250514";

export function createModel(config: ModelConfig = {}): ChatAnthropic {
  return new ChatAnthropic({
    model: config.model ?? DEFAULT_MODEL,
    temperature: config.temperature ?? 0.3,
    maxTokens: config.maxTokens ?? 1024,
    timeout: config.timeout ?? 60_000,
    maxRetries: config.maxRetries ?? 2,
  });
}

// ---------------------------------------------------------------------------
// 2. Basic invocation
// ---------------------------------------------------------------------------

export async function basicInvoke(
  model: ChatAnthropic,
  userInput: string,
): Promise<string> {
  const response = await model.invoke([new HumanMessage(userInput)]);
  return typeof response.content === "string"
    ? response.content
    : JSON.stringify(response.content);
}

export async function* streamingInvoke(
  model: ChatAnthropic,
  userInput: string,
): AsyncGenerator<string> {
  const stream = await model.stream([new HumanMessage(userInput)]);
  for await (const chunk of stream) {
    if (chunk.content) {
      yield typeof chunk.content === "string"
        ? chunk.content
        : JSON.stringify(chunk.content);
    }
  }
}

// ---------------------------------------------------------------------------
// 3. Tool definitions
// ---------------------------------------------------------------------------

export function getWeather(location: string): string {
  const weatherData: Record<string, string> = {
    "san francisco": "Sunny, 72°F, wind 5mph NW",
    "new york": "Cloudy, 58°F, wind 10mph NE",
    beijing: "Partly cloudy, 25°C, wind 3m/s SE",
    london: "Rainy, 12°C, wind 8m/s SW",
    tokyo: "Clear, 20°C, wind 2m/s N",
    sydney: "Sunny, 28°C, wind 4m/s E",
  };
  return (
    weatherData[location.toLowerCase()] ??
    `Weather data unavailable for ${location}`
  );
}

export function calculator(expression: string): string {
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
}

// ---------------------------------------------------------------------------
// 4. Tool binding and execution
// ---------------------------------------------------------------------------

export function bindToolsToModel(
  model: ChatAnthropic,
  tools: StructuredTool[],
): ChatAnthropic {
  return model.bindTools(tools) as unknown as ChatAnthropic;
}

export async function executeToolCalls(
  response: AIMessage,
  tools: StructuredTool[],
): Promise<ToolMessage[]> {
  const toolsByName = new Map(tools.map((t) => [t.name, t]));
  const results: ToolMessage[] = [];

  const toolCalls = (response as any).tool_calls ?? [];
  for (const tc of toolCalls) {
    const toolName: string = tc.name ?? "";
    const toolArgs: Record<string, unknown> = tc.args ?? {};
    const toolId: string = tc.id ?? "";

    const tool = toolsByName.get(toolName);
    const observation = tool
      ? String(await tool.invoke(toolArgs))
      : `Error: unknown tool '${toolName}'`;

    results.push(new ToolMessage({ content: observation, tool_call_id: toolId }));
  }

  return results;
}

// ---------------------------------------------------------------------------
// 5. Prompt templates
// ---------------------------------------------------------------------------

export function createChatPrompt(config: {
  systemPrompt?: string;
  includeHistory?: boolean;
  includeScratchpad?: boolean;
}): ChatPromptTemplate {
  const messages: Array<[string, string] | MessagesPlaceholder> = [];

  if (config.systemPrompt) {
    messages.push(["system", config.systemPrompt]);
  }

  if (config.includeHistory !== false) {
    messages.push(new MessagesPlaceholder("history"));
  }

  messages.push(["human", "{input}"]);

  if (config.includeScratchpad !== false) {
    messages.push(new MessagesPlaceholder("agent_scratchpad"));
  }

  return ChatPromptTemplate.fromMessages(messages);
}

// ---------------------------------------------------------------------------
// 6. ConversationBufferMemory
// ---------------------------------------------------------------------------

export class ConversationBufferMemory {
  private messages: (HumanMessage | AIMessage)[] = [];

  addUserMessage(content: string): void {
    this.messages.push(new HumanMessage(content));
  }

  addAIMessage(content: string): void {
    this.messages.push(new AIMessage(content));
  }

  getMessages(): (HumanMessage | AIMessage)[] {
    return [...this.messages];
  }

  clear(): void {
    this.messages = [];
  }

  get messageCount(): number {
    return this.messages.length;
  }
}

// ---------------------------------------------------------------------------
// 7. Agent loop
// ---------------------------------------------------------------------------

export async function runAgentLoop(
  model: ChatAnthropic,
  tools: StructuredTool[],
  userInput: string,
  memory?: ConversationBufferMemory,
  maxIterations: number = 5,
): Promise<string> {
  if (!memory) {
    memory = new ConversationBufferMemory();
  }

  memory.addUserMessage(userInput);
  const messages: BaseMessage[] = memory.getMessages();

  for (let i = 0; i < maxIterations; i++) {
    const response: AIMessage = (await model.invoke(messages)) as AIMessage;

    const toolCalls = (response as any).tool_calls;
    if (!toolCalls || toolCalls.length === 0) {
      const content =
        typeof response.content === "string"
          ? response.content
          : JSON.stringify(response.content);
      memory.addAIMessage(content);
      return content;
    }

    // Execute tool calls
    const toolResults = await executeToolCalls(response, tools);
    messages.push(response);
    messages.push(...toolResults);
  }

  // Fallback
  const fallback = (await model.invoke(messages)) as AIMessage;
  return typeof fallback.content === "string"
    ? fallback.content
    : JSON.stringify(fallback.content);
}
