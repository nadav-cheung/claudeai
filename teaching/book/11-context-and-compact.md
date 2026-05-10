# 11 - 上下文管理与压缩

> **本章目标**：深入理解 Claude Code 如何管理对话上下文、如何在上下文接近限制时自动压缩消息。

---

## 1. 准备工作

### 1.1 阅读源码

**必读**：
- `src/services/compact/compact.ts` - 上下文压缩
- `src/context.ts` - System Prompt 构建

### 1.2 本章与 Mini-Claude 的关系

| Mini-Claude | Claude Code |
|-------------|-------------|
| 简单 messages 数组 | 完整上下文管理 |
| 无压缩 | 自动压缩算法 |
| 无 token 统计 | 完整 token 计数 |

---

## 2. 上下文窗口问题

### 2.1 什么是上下文窗口？

AI 模型有一个固定的"记忆容量"，称为**上下文窗口**（Context Window）：

```text
上下文窗口 (例如 200K tokens)
┌─────────────────────────────────────────────────┐
│  [System Prompt] [历史消息1] [历史消息2] ... [剩余空间] │
│                                                  │
│  ◄──────────────── 已使用 --------------------►  │
│                                                  │
│                          ◄──── 可用空间 ────►     │
└─────────────────────────────────────────────────┘
```

### 2.2 超出限制会怎样？

```text
如果消息太多，超过上下文窗口：
        │
        ▼
API 返回错误：max_tokens exceeded
        │
        ▼
对话无法继续！
```

---

## 3. Claude Code 的上下文管理

### 3.1 Token 计数

```typescript
// Claude Code 的 token 统计
interface ContextStats {
  systemPrompt: number;      // System prompt tokens
  messages: number;          // 对话消息 tokens
  tools: number;            // 工具定义 tokens
  available: number;        // 剩余可用 tokens
  total: number;            // 总计
}

// 估算 token 数量（简单方法：按字符数估算）
function estimateTokens(text: string): number {
  // 英文：约 4 字符 = 1 token
  // 中文：约 2 字符 = 1 token
  return Math.ceil(text.length / 4);
}

// 精确计算（使用 tiktoken）
import { encoding_for_model } from 'tiktoken';

function countTokens(text: string, model: string): number {
  const encoder = encoding_for_model(model);
  return encoder.encode(text).length;
}
```

### 3.2 上下文使用追踪

```typescript
// context.ts (简化)
export interface ContextWindow {
  maxTokens: number;
  usedTokens: number;
  remainingTokens: number;
}

export function calculateContextUsage(
  messages: Message[],
  systemPrompt: string,
  tools: Tool[]
): ContextWindow {
  const maxTokens = 200_000; // Claude 3.5 Sonnet

  const systemTokens = countTokens(systemPrompt);
  const messageTokens = sum(messages.map(m => countTokens(m.content)));
  const toolTokens = sum(tools.map(t => countTokens(JSON.stringify(t.input_schema))));

  const usedTokens = systemTokens + messageTokens + toolTokens;

  return {
    maxTokens,
    usedTokens,
    remainingTokens: maxTokens - usedTokens,
  };
}
```

---

## 4. 上下文压缩

### 4.1 压缩触发条件

```typescript
// 当剩余空间小于阈值时触发压缩
const COMPACT_THRESHOLD = 0.15; // 15% 剩余时压缩

function shouldCompact(context: ContextWindow): boolean {
  return context.remainingTokens < context.maxTokens * COMPACT_THRESHOLD;
}
```

### 4.2 压缩策略

Claude Code 使用**消息摘要**来压缩上下文：

```
压缩前：
┌─────────────────────────────────────────────────┐
│ [消息1] [消息2] [消息3] [消息4] [消息5] [消息6]   │
└─────────────────────────────────────────────────┘

压缩后：
┌─────────────────────────────────────────────────┐
│ [摘要: 消息1-4] [消息5] [消息6]                  │
└─────────────────────────────────────────────────┘
```

### 4.3 压缩实现

```typescript
// services/compact/compact.ts (简化)
export async function compactContext(
  messages: Message[],
  options: CompactOptions
): Promise<Message[]> {
  const { summarizeModel, threshold } = options;

  // 1. 找出需要压缩的消息
  const toCompact = selectMessagesToCompact(messages, threshold);

  // 2. 对选中消息生成摘要
  const summary = await summarizeMessages(toCompact);

  // 3. 替换为摘要消息
  const summarizedMessage: Message = {
    role: 'system',
    content: `[前 ${toCompact.length} 条消息的摘要]: ${summary}`,
  };

  // 4. 保留最近的消息（不压缩）
  const recentMessages = messages.slice(-3); // 保留最近3条

  // 5. 返回新的消息列表
  return [summarizedMessage, ...recentMessages];
}

async function summarizeMessages(messages: Message[]): Promise<string> {
  // 使用 AI 生成摘要
  const summaryRequest = {
    model: 'claude-3-haiku',
    messages: [
      {
        role: 'user',
        content: `请简要总结以下对话的要点（不超过100字）：\n\n${
          messages.map(m => `${m.role}: ${m.content}`).join('\n')
        }`,
      },
    ],
  };

  const response = await callClaudeApi(summaryRequest);
  return response.content[0].text;
}
```

---

## 5. Mini-Claude 的简单实现

### 5.1 基础版本

```typescript
// Mini-Claude: 简单的消息管理
class SimpleMessageStore {
  private messages: Message[] = [];
  private maxMessages = 50;

  add(message: Message) {
    this.messages.push(message);

    // 简单策略：超过上限就删除最早的
    if (this.messages.length > this.maxMessages) {
      this.messages = this.messages.slice(-this.maxMessages);
    }
  }

  getMessages(): Message[] {
    return this.messages;
  }
}
```

### 5.2 带 Token 统计的版本

```typescript
// Mini-Claude: 简单的 token 统计
class MessageStoreWithLimit {
  private messages: Message[] = [];
  private maxTokens = 100_000; // 简单设为 100K

  add(message: Message) {
    this.messages.push(message);
    this.compactIfNeeded();
  }

  private compactIfNeeded() {
    const totalTokens = this.estimateTokens();

    if (totalTokens > this.maxTokens) {
      // 简单策略：保留最近一半
      const keepCount = Math.floor(this.messages.length / 2);
      this.messages = this.messages.slice(-keepCount);
    }
  }

  private estimateTokens(): number {
    return this.messages.reduce((sum, msg) => {
      return sum + Math.ceil(msg.content.length / 4);
    }, 0);
  }
}
```

---

## 6. 实战练习

### 6.1 练习：实现消息截断

**目标**：为 Mini-Claude 添加简单的消息截断功能

**答案要点**：
```typescript
class TruncatingMessageStore {
  private messages: Message[] = [];
  private maxTokens = 50000;

  add(message: Message) {
    const messageTokens = Math.ceil(message.content.length / 4);

    // 如果单条消息就超过限制，截断它
    if (messageTokens > this.maxTokens) {
      const maxChars = this.maxTokens * 4;
      message.content = message.content.slice(0, maxChars) + '...(截断)';
    }

    this.messages.push(message);
    this.trimOldMessages();
  }

  private trimOldMessages() {
    let totalTokens = this.messages.reduce(
      (sum, m) => sum + Math.ceil(m.content.length / 4),
      0
    );

    // 从旧到新删除，直到在限制内
    while (totalTokens > this.maxTokens && this.messages.length > 2) {
      const removed = this.messages.shift()!;
      totalTokens -= Math.ceil(removed.content.length / 4);
    }
  }
}
```

---

## 7. 总结

| 方面 | Mini-Claude | Claude Code |
|------|-------------|-------------|
| 消息存储 | 简单数组 | 结构化存储 |
| Token 统计 | 无 | 精确计算 |
| 压缩触发 | 无 | 15% 阈值 |
| 压缩策略 | 删除旧消息 | AI 摘要 |
| System Prompt | 简单字符串 | 完整构建 |

---

## 下一篇

👉 [12 - MCP协议集成](../07-mcp-integration.md) —— 深入理解 MCP 协议如何扩展工具

`★ Insight ─────────────────────────────────────`
上下文管理是长对话的命脉。当对话变长时，如何保留重要信息、丢弃无用细节，是一个复杂的决策问题。Claude Code 的方案是"AI 摘要"——让 AI 自己决定哪些重要，然后用摘要替代原始消息。这比简单的"删除旧消息"聪明得多，但实现也更复杂。
`─────────────────────────────────────────────────`
