# 06 - 上下文管理与压缩 (Context Management and Compaction)

> **本章目标**：理解 Claude Code 如何管理有限的上下文窗口 (Context Window)，包括消息结构、token 估算、压缩触发条件、compact 算法、微压缩 (MicroCompact)、会话记忆压缩 (Session Memory Compact) 等机制。掌握当对话超出上下文窗口时，系统如何优雅地压缩历史消息而不丢失关键信息。

---

## 核心概念

### 1. 上下文窗口 (Context Window)

Claude 模型有固定的上下文窗口大小（通常 200K token，1M token 模型可用）：

```
src/utils/context.ts
├── MODEL_CONTEXT_WINDOW_DEFAULT = 200_000
├── COMPACT_MAX_OUTPUT_TOKENS = 20_000
├── getContextWindowForModel(model, betas) — 获取模型的上下文窗口大小
├── has1mContext(model) — 检查是否启用 1M 上下文
└── modelSupports1M(model) — 检查模型是否支持 1M 上下文
```

上下文窗口不是全部可用于历史消息——系统需要预留空间给：
- 系统提示词 (System Prompt)
- 工具定义 (Tool Definitions)
- 输出 token (Max Output Tokens)

### 2. 消息类型体系

```
src/utils/messages.ts
├── UserMessage          — 用户消息（包括 tool_result），来自 @anthropic-ai/sdk
├── AssistantMessage     — 模型回复（包括 tool_use），来自 @anthropic-ai/sdk
├── SystemMessage        — 系统消息（包括 compact boundary），来自 @anthropic-ai/sdk
├── AttachmentMessage    — 附件消息（hook 输出、skill 发现等）
├── ProgressMessage      — 进度消息
└── SystemCompactBoundaryMessage — 压缩边界标记
```

关键设计：`SystemCompactBoundaryMessage` 标记压缩发生的位置，系统只保留边界之后的消息作为有效上下文。

### 3. 压缩触发条件

```
src/services/compact/autoCompact.ts
├── getAutoCompactThreshold(model) — 自动压缩阈值
├── AUTOCOMPACT_BUFFER_TOKENS = 13_000 — 缓冲区
├── WARNING_THRESHOLD_BUFFER_TOKENS = 20_000 — 警告阈值
└── ERROR_THRESHOLD_BUFFER_TOKENS = 20_000 — 错误阈值
```

三种压缩触发方式：
1. **自动压缩** — token 使用量超过 `context_window - 13_000` 时自动触发
2. **手动压缩** — 用户输入 `/compact` 命令
3. **API 错误触发** — 收到 `prompt_too_long` 错误时强制压缩

### 4. 压缩策略层级

```
优先级从高到低：

1. Session Memory Compact — 使用会话记忆替代完整历史
2. MicroCompact — 清理旧的工具结果，保留近期消息
3. Full Compact — 调用 AI 生成对话摘要
4. Prompt-Too-Long 重试 — 截断最旧的 API 轮次
```

---

## 源码导览

### Token 估算 (tokenEstimation.ts)

```
src/services/tokenEstimation.ts
```

Token 估算有两个层级：

1. **粗略估算** — `roughTokenCountEstimation()` 和 `roughTokenCountEstimationForMessages()`
   - 用于自动压缩触发判断
   - 不调用 API，基于启发式规则估算
   - 比精确计数快得多

2. **精确计数** — `tokenCountWithEstimation()`
   - 使用 Anthropic API 的 `/messages/count_tokens` 端点
   - 支持 Bedrock 和 Vertex AI 的 token 计数接口
   - 带有 VCR (Video Cassette Recorder) 录制/回放支持用于测试

```typescript
// tokenEstimation.ts 中的关键函数签名
export function roughTokenCountEstimation(text: string): number
export function roughTokenCountEstimationForMessages(messages: Message[]): number
export async function tokenCountWithEstimation(
  messages: Message[],
  tools: Tool[],
  model: string,
  options?: { thinkingBudget?: number }
): Promise<number>
```

### 上下文工具函数 (context.ts)

```
src/utils/context.ts
```

这个文件管理模型的上下文窗口配置：

```typescript
export const MODEL_CONTEXT_WINDOW_DEFAULT = 200_000

export function getContextWindowForModel(model: string, betas?: string[]): number {
  // 1. 环境变量覆盖 (CLAUDE_CODE_MAX_CONTEXT_TOKENS)
  // 2. [1m] 后缀检测 — 显式 1M 上下文
  // 3. 模型能力查询 — getModelCapability()
  // 4. 1M beta header 检测
  // 5. 默认 200K
}

export function modelSupports1M(model: string): boolean {
  const canonical = getCanonicalName(model)
  return canonical.includes('claude-sonnet-4') || canonical.includes('opus-4-6')
}
```

### Full Compact 核心 (compact.ts)

```
src/services/compact/compact.ts
```

这是压缩系统的核心，约 1500+ 行。主要功能：

#### `compactConversation()` — 主压缩函数

```
compactConversation(messages, toolUseContext, options)
  │
  ├─ stripImagesFromMessages() — 移除图片块（节省大量 token）
  ├─ stripReinjectedAttachments() — 移除会被重新注入的附件
  │
  ├─ 选择压缩策略：
  │   ├─ 尝试 Session Memory Compact（如果可用）
  │   └─ 回退到 Full Compact
  │
  ├─ Full Compact 流程：
  │   ├─ groupMessagesByApiRound() — 按 API 轮次分组
  │   ├─ 分割为 summarize_set + keep_set
  │   ├─ 构建 compact prompt (getCompactPrompt)
  │   ├─ 调用 forkedAgent 进行摘要
  │   └─ 生成摘要消息
  │
  ├─ createCompactBoundaryMessage() — 创建压缩边界标记
  │
  └─ buildPostCompactMessages() — 构建压缩后的消息列表
      ├─ 摘要消息
      ├─ 计划附件（如果存在活跃计划）
      ├─ 重新注入的附件
      └─ 压缩后的消息
```

#### 消息分组 (grouping.ts)

```
src/services/compact/grouping.ts — groupMessagesByApiRound()
```

消息按 API 轮次分组（不是按用户轮次），这允许在单轮对话（SDK/CCR 调用）中也能进行细粒度压缩：

```
API Round 1: [user_prompt] [assistant_response] [tool_results]
API Round 2: [assistant_response] [tool_results]
API Round 3: [assistant_response]
```

边界判断：当遇到一个新的 `AssistantMessage` 且其 `message.id` 与前一个不同时，就是新的一轮。

#### 图片剥离 (compact.ts:145)

```typescript
export function stripImagesFromMessages(messages: Message[]): Message[] {
  // 将图片块替换为 [image] 文本标记
  // 将文档块替换为 [document] 文本标记
  // 同时处理嵌套在 tool_result 中的图片/文档
}
```

这解决了压缩请求本身可能因包含大量图片而触发 `prompt_too_long` 的问题。

### 压缩提示词 (prompt.ts)

```
src/services/compact/prompt.ts
```

压缩提示词由 `getCompactPrompt()` 构建（`src/services/compact/prompt.ts`），包含详细的分析指令和输出格式要求：

```
分析指令：
1. 按时间顺序分析每条消息
2. 识别用户请求、方法、技术决策、代码模式
3. 记录错误和修复方式
4. 特别关注用户反馈

输出格式（9 个必填部分）：
1. Primary Request and Intent — 用户的主要请求
2. Key Technical Concepts — 关键技术概念
3. Files and Code Sections — 文件和代码
4. Errors and fixes — 错误和修复
5. Problem Solving — 问题解决
6. All user messages — 所有用户消息
7. Pending Tasks — 待处理任务
8. Current Work — 当前工作
9. Optional Next Step — 可选的下一步
```

Prompt 有两个版本：
- `getCompactPrompt()` — 全量压缩用，摘要覆盖全部历史
- `getPartialCompactPrompt(direction)` — 部分压缩用，`direction='from'` 压缩 pivot 之后，`direction='up_to'` 压缩 pivot 之前

还有 **Partial Compact**（部分压缩）变体，通过 `partialCompactConversation()` 实现，只压缩部分消息而不是整个对话历史，支持两种方向：

- **`from`** 模式：压缩 pivot 位置之后的所有消息，pivot 之前的保留（默认）
- **`up_to`** 模式：压缩 pivot 位置之前的所有消息，pivot 之后的保留

Partial Compact 用于用户手动选择压缩起点（如 `/compact` 带参数）的场景，比全量压缩更灵活。

### 微压缩 MicroCompact (microCompact.ts)

```
src/services/compact/microCompact.ts
```

微压缩是一种轻量级压缩策略，不调用 AI 模型，而是直接清理旧的工具结果：

```typescript
// 可微压缩的工具类型
const COMPACTABLE_TOOLS = new Set([
  FILE_READ_TOOL_NAME,     // 文件读取
  ...SHELL_TOOL_NAMES,     // Bash/PowerShell
  GREP_TOOL_NAME,          // 搜索
  GLOB_TOOL_NAME,          // 文件匹配
  WEB_SEARCH_TOOL_NAME,    // Web 搜索
  WEB_FETCH_TOOL_NAME,     // Web 抓取
  FILE_EDIT_TOOL_NAME,     // 文件编辑
  FILE_WRITE_TOOL_NAME,    // 文件写入
])
```

微压缩的工作方式：
1. 遍历所有消息中的 tool_result 块
2. 对于可压缩工具，将旧的大结果替换为截断标记
3. 使用基于时间的配置决定哪些结果"足够旧"可以清理

```typescript
// 时间配置
export type TimeBasedMCConfig = {
  maxAgeMs: number        // 最大年龄（毫秒）
  maxResultSize: number   // 最大保留大小
  minMessagesAfterTool: number // 工具使用后最少保留的消息数
}
```

### 会话记忆压缩 (sessionMemoryCompact.ts)

```
src/services/compact/sessionMemoryCompact.ts
```

会话记忆压缩是最新的压缩策略，利用 CLAUDE.md 风格的会话记忆文件：

```typescript
// 配置
export const DEFAULT_SM_COMPACT_CONFIG = {
  minTokens: 10_000,          // 压缩后最少保留的 token
  minTextBlockMessages: 5,    // 最少保留的含文本消息数
  maxTokens: 40_000,          // 最大保留 token
}
```

工作原理：
1. 等待会话记忆提取完成（`waitForSessionMemoryExtraction()`）
2. 获取会话记忆内容（`getSessionMemoryContent()`）
3. 从最新的消息开始，按 API 轮次向前保留消息
4. 保留的 token 量在 `minTokens` 和 `maxTokens` 之间
5. 用会话记忆文件替代被丢弃的历史消息

优势：不需要调用 AI 模型生成摘要，速度更快且更可靠。

### 自动压缩控制 (autoCompact.ts)

```
src/services/compact/autoCompact.ts
```

```typescript
// 自动压缩阈值计算
export function getAutoCompactThreshold(model: string): number {
  const effectiveContextWindow = getEffectiveContextWindowSize(model)
  return effectiveContextWindow - AUTOCOMPACT_BUFFER_TOKENS  // 13_000
}

// 有效上下文窗口 = 总窗口 - 输出预留
export function getEffectiveContextWindowSize(model: string): number {
  let contextWindow = getContextWindowForModel(model, getSdkBetas())
  const reservedTokensForSummary = Math.min(
    getMaxOutputTokensForModel(model),
    20_000
  )
  return contextWindow - reservedTokensForSummary
}

// Token 状态监控
export function calculateTokenWarningState(tokenUsage, model) {
  const effectiveContextWindow = getEffectiveContextWindowSize(model)
  const percentLeft = 1 - tokenUsage / effectiveContextWindow
  return {
    percentLeft,
    isAboveWarningThreshold: percentLeft < 0.10,  // < 10% 剩余
    isAboveErrorThreshold: percentLeft < 0.05,     // < 5% 剩余
    isAboveAutoCompactThreshold: tokenUsage >= getAutoCompactThreshold(model),
  }
}

// 连续失败熔断器
const MAX_CONSECUTIVE_AUTOCOMPACT_FAILURES = 3
// 超过 3 次连续失败后停止尝试自动压缩
```

---

## 数据流图

### 自动压缩触发流程

```
每次 API 调用后
       │
       ▼
  tokenCountFromLastAPIResponse()
       │
       ▼
  calculateTokenWarningState()
       │
       ├── percentLeft < 10% → 显示警告
       ├── percentLeft < 5%  → 显示错误
       │
       └── isAboveAutoCompactThreshold?
              │
              ├─ No → 继续正常对话
              │
              └─ Yes → autoCompactIfNeeded()
                      │
                      ├── consecutiveFailures >= 3?
                      │   └─ Yes → 停止尝试（熔断）
                      │
                      └─ No → 尝试压缩
                              │
                              ├── trySessionMemoryCompaction()
                              │   └─ 使用会话记忆
                              │
                              ├── compactConversation()
                              │   └─ AI 摘要生成
                              │
                              └── 失败 → consecutiveFailures++
```

### 压缩消息处理流程

```
原始消息序列:
  [user_1] [assistant_1] [tool_result_1]
  [user_2] [assistant_2] [tool_result_2]
  [user_3] [assistant_3] [tool_result_3]
  [user_4] [assistant_4]

              │
              ▼ 压缩触发

groupMessagesByApiRound():
  Group 1: [user_1, assistant_1, tool_result_1]
  Group 2: [user_2, assistant_2, tool_result_2]
  Group 3: [user_3, assistant_3, tool_result_3]
  Group 4: [user_4, assistant_4]

              │
              ▼ 选择分割点

summarize_set = Group 1 + Group 2
keep_set = Group 3 + Group 4

              │
              ▼ 生成摘要

摘要消息 = AI("总结以下对话...", summarize_set)

              │
              ▼ 构建压缩后消息

[SystemCompactBoundaryMessage]     ← 压缩边界标记
[UserMessage: 对话摘要]              ← AI 生成的摘要
[AttachmentMessage: 计划(如有)]      ← 重新注入
[Group 3, Group 4]                  ← 保留的消息
```

### MicroCompact 工作流

```
遍历所有消息
       │
       ▼
  对于每条消息中的 tool_result：
       │
       ├── 工具不在 COMPACTABLE_TOOLS 中？→ 跳过
       ├── 消息太新（不满足 minMessagesAfterTool）？→ 跳过
       ├── 结果太小？→ 跳过
       │
       └── 符合条件 → 替换结果内容为:
           "[Old tool result content cleared]"
```

---

## 关键代码

### 1. Prompt-Too-Long 重试 (compact.ts:243)

当压缩请求本身也触发 `prompt_too_long` 时，系统会截断最旧的消息：

```typescript
export function truncateHeadForPTLRetry(
  messages: Message[],
  ptlResponse: AssistantMessage,
): Message[] | null {
  // 1. 按 API 轮次分组
  const groups = groupMessagesByApiRound(input)

  // 2. 计算需要丢弃的 token 量
  const tokenGap = getPromptTooLongTokenGap(ptlResponse)

  // 3. 从最旧的组开始丢弃，直到覆盖 token gap
  let acc = 0
  for (const g of groups) {
    acc += roughTokenCountEstimationForMessages(g)
    if (acc >= tokenGap) break
  }

  // 4. 如果丢弃后以 assistant 消息开头，添加合成 user 消息
  // （API 要求第一条消息必须是 role=user）
  if (sliced[0]?.type === 'assistant') {
    return [createUserMessage({ content: PTL_RETRY_MARKER, isMeta: true }), ...sliced]
  }
}
```

### 2. Post-Compact 资源重新注入 (compact.ts:122)

压缩后，系统需要重新注入一些关键信息：

```typescript
export const POST_COMPACT_MAX_FILES_TO_RESTORE = 5
export const POST_COMPACT_TOKEN_BUDGET = 50_000
export const POST_COMPACT_MAX_TOKENS_PER_FILE = 5_000
export const POST_COMPACT_SKILLS_TOKEN_BUDGET = 25_000
```

重新注入的内容包括：
- 最近读取的文件内容（最多 5 个文件，每个 5000 token）
- 活跃的计划
- MCP 工具指令
- 已发现的工具列表
- Skill 列表（有独立的 token 预算）

### 3. 压缩边界标记

压缩边界标记 (`SystemCompactBoundaryMessage`) 的作用：

```typescript
// src/utils/messages.ts
export function createCompactBoundaryMessage(): SystemCompactBoundaryMessage
export function getMessagesAfterCompactBoundary(messages: Message[]): Message[]
export function isCompactBoundaryMessage(message: Message): boolean
```

- 标记压缩发生的位置
- 系统只处理边界之后的消息作为有效上下文
- 防止压缩前的旧消息被再次引用

### 4. Session Memory Compact 的配置同步 (sessionMemoryCompact.ts)

```typescript
// 从 GrowthBook 获取远程配置
export async function initializeSessionMemoryCompactConfig(): Promise<void> {
  if (configInitialized) return  // 只初始化一次

  const remoteConfig = getFeatureValue_CACHED_MAY_BE_STALE(
    'tengu_session_memory_compact_config',
    null
  )

  if (remoteConfig) {
    setSessionMemoryCompactConfig(remoteConfig)
  }
  configInitialized = true
}
```

这允许远程动态调整压缩参数，无需发布新版本。

### 5. 压缩 Hook (compact.ts 引用)

压缩过程支持外部 Hook：

```typescript
import { executePostCompactHooks, executePreCompactHooks } from '../../utils/hooks.ts'
```

- `PreCompact` Hook — 在压缩前运行，可以准备资源或记录日志
- `PostCompact` Hook — 在压缩完成后运行，可以进行清理或通知

---

## 练习

### 练习 1：追踪一次自动压缩

**类比 Java**：这类似于 Hibernate 一级缓存的 flush 策略——当缓存满时触发 flush，清理旧数据。

**场景**：token 使用量达到 187,000（200K 窗口）

**答案**：

1. **阈值计算**：`200,000 - 13,000 = 187,000` 触发压缩

2. **状态判断**：`percentLeft = 1 - 187000/200000 = 6.5%` < 10%，显示警告

3. **调用链**：`autoCompactIfNeeded()` → `trySessionMemoryCompact()` 或 `compactConversation()`

4. **分组**：`groupMessagesByApiRound()` 将消息按 API 轮次分组

5. **构建**：`buildPostCompactMessages()` 生成压缩后的消息列表

**思考题答案**：
13,000 buffer 是权衡：
- **太小**：压缩太频繁，AI 摘要开销大
- **太大**：接近 limit，API 可能直接拒绝

### 练习 2：MicroCompact vs Full Compact

**类比 Java**：这类似于 MyBatis 一级缓存 vs 二级缓存的策略差异。

**场景分析**：

| 场景 | MicroCompact | Full Compact |
|------|-------------|-------------|
| 读取 20 个文件后问新问题 | 清理旧文件读取结果 | 生成对话摘要 |
| 话题切换 3 次 | 清理旧的搜索结果 | 理解话题演进 |

**思考题答案**：
MicroCompact 退化为无效操作的情况：
- 所有工具结果都已很小（无内容可清理）
- 用户刚开启新对话（无"旧"结果）

### 练习 3：Session Memory Compact 分析

**答案**：

| 策略 | 优点 | 缺点 |
|------|------|------|
| Session Memory | 快（无 AI 调用）、可靠 | 信息可能丢失 |
| Full Compact | 信息保留完整 | 慢、依赖 AI |

**本质区别**：
- Session Memory：用外部文件替代历史，可能丢失细节
- Full Compact：用 AI 摘要替代历史，保留结构化信息

### 练习 4：上下文窗口管理

**答案**：

1. **配置优先级**：`CLAUDE_CODE_MAX_CONTEXT_TOKENS` > `getModelCapability()` > 默认 200K

2. **有效窗口 = 总窗口 - 输出预留**（约 180K 用于输入）

3. **预留太小的问题**：
   - 输出被截断
   - 响应不完整
   - API 可能报错

**Java 对比**：
```java
// Java 堆内存 vs 上下文窗口
int maxHeap = Runtime.getRuntime().maxMemory();  // 总堆
int reserved = 20_000;                          // 预留（类似输出预留）
int effective = maxHeap - reserved;               // 有效堆
```

---

## 练习答案速查

| 练习 | 核心答案 |
|------|---------|
| 1 | buffer 13K = 平衡压缩频率和 API 成功率 |
| 2 | MicroCompact 无旧内容时无效 |
| 3 | Session Memory 快但可能丢信息 |
| 4 | 预留太小 → 输出截断/响应不完整 |

---

## 上下文管理 vs Java 缓存

| 方面 | Claude Code | Java |
|------|-------------|------|
| 容量管理 | Token 计数 | 字节计数 |
| 淘汰策略 | 时间 + 阈值 | LRU/LFU |
| 压缩方式 | AI 摘要/Micro | 无等价 |
| 持久化 | 会话记忆文件 | 二级缓存 |
| 刷新 | 自动/手动 | flushMode |

---

## 下一篇

👉 [07-mcp-integration.md](./07-mcp-integration.md) — MCP 协议集成
