# 09 - 记忆与持久化 (Memory and Persistence)

> **本章目标**：理解 Claude Code 中会话持久化、CLAUDE.md 指令加载、记忆文件系统、自动记忆提取、会话恢复和设置同步的完整机制。

---

## 目标

- 理解会话持久化的存储格式（JSONL）和读写机制
- 掌握 CLAUDE.md 的分层加载、优先级和 @include 机制
- 了解记忆（Memory）的类型体系：User / Project / Local / Managed / AutoMem / TeamMem
- 理解自动记忆提取的触发条件和 fork agent 执行模式
- 掌握会话恢复（session restore）的实现
- 了解设置同步和团队记忆同步机制

---

## 核心概念

### 持久化层次

Claude Code 的持久化系统分为多个层次：

```
持久化层次
  │
  ├── 1. 会话 Transcript
  │     └── ~/.claude/projects/<path>/sessions/<id>.jsonl
  │         └── 每行一条消息，支持断点恢复
  │
  ├── 2. CLAUDE.md 指令文件
  │     ├── ~/.claude/CLAUDE.md          ← User 级别
  │     ├── <project>/CLAUDE.md          ← Project 级别
  │     ├── <project>/.claude/CLAUDE.md  ← Project 级别（隐藏）
  │     ├── <project>/.claude/rules/*.md ← Project 规则
  │     ├── <project>/CLAUDE.local.md    ← Local 级别
  │     └── /etc/claude-code/CLAUDE.md   ← Managed 级别
  │
  ├── 3. 自动记忆 (AutoMem)
  │     └── ~/.claude/projects/<path>/memory/
  │         └── 带 frontmatter 的 markdown 文件
  │
  ├── 4. 会话记忆 (Session Memory)
  │     └── ~/.claude/session-memory/<id>.md
  │         └── 当前会话的摘要笔记
  │
  ├── 5. 团队记忆 (TeamMem)
  │     └── 团队共享的记忆文件
  │
  └── 6. 设置持久化
        ├── ~/.claude/settings.json           ← 用户设置
        ├── <project>/.claude/settings.json   ← 项目设置
        ├── <project>/.claude/settings.local.json ← 本地设置
        └── /etc/claude-code/settings.json    ← 管理设置
```

### 记忆类型体系

```typescript
// src/utils/memory/types.ts
export const MEMORY_TYPE_VALUES = [
  'User',       // 用户偏好和习惯
  'Project',    // 项目特定的模式和约定
  'Local',      // 本地环境特定信息
  'Managed',    // 企业管理的指令
  'AutoMem',    // 自动提取的持久记忆
  'TeamMem',    // 团队共享记忆
] as const
```

### CLAUDE.md 加载优先级

```
加载顺序（从低到高优先级）：
  1. Managed  — /etc/claude-code/CLAUDE.md
  2. User     — ~/.claude/CLAUDE.md
  3. Project  — 从根目录到 CWD 的 CLAUDE.md / .claude/CLAUDE.md / .claude/rules/*.md
  4. Local    — CLAUDE.local.md
  5. AutoMem  — ~/.claude/projects/<path>/memory/

加载规则：
  - 近 CWD 的文件后加载 → 模型更关注（recency bias）
  - 同目录中 .claude/CLAUDE.md 和 CLAUDE.md 都存在时，都加载
  - .claude/rules/ 下的所有 .md 文件都被加载
  - 支持 @include 指令包含外部文件
```

---

## 源码导览

### 1. 会话存储架构

```
src/utils/sessionStorage.ts
  ├── 会话 JSONL 读写
  ├── Transcript 消息序列化/反序列化
  ├── Agent 元数据写入
  ├── Sidechain transcript 管理
  └── 会话恢复状态管理

src/services/SessionMemory/
  ├── sessionMemory.ts        ← 会话记忆核心：提取、更新、阈值检查
  ├── sessionMemoryUtils.ts   ← 工具函数：配置、阈值、状态追踪
  └── prompts.ts              ← 提取 prompt 模板

src/services/extractMemories/
  ├── extractMemories.ts      ← 持久记忆提取：fork agent 模式
  └── prompts.ts              ← 提取 prompt 模板

src/utils/memory/
  ├── types.ts                ← 记忆类型定义
  └── versions.ts             ← 版本检测（git repo）

src/utils/claudemd.ts         ← CLAUDE.md 加载引擎
src/hooks/                    ← 钩子系统（记忆相关）
src/memdir/                   ← 记忆目录管理
```

### 2. 会话 JSONL 格式

会话以 JSONL (JSON Lines) 格式存储在 `~/.claude/projects/<path>/sessions/<session-id>.jsonl`：

```
每行一条记录，类型由 type 字段区分：
  - user:            用户消息
  - assistant:       模型响应
  - system:          系统消息（如 compact_boundary）
  - summary:         摘要消息（compaction 后）
  - progress:        进度消息
  - tool_result:     工具结果
  - file_history:    文件历史快照
  - attribution:     归因快照
  - context_collapse: 上下文压缩记录
```

---

## 数据流图

### CLAUDE.md 加载流程

```
getUserContext()
  │
  ├── 1. 收集所有 CLAUDE.md 路径
  │     ├── getManagedClaudeRulesDir() → Managed 级别
  │     ├── getUserClaudeRulesDir()    → User 级别
  │     └── 从 CWD 向上遍历到根目录：
  │         ├── CLAUDE.md
  │         ├── .claude/CLAUDE.md
  │         └── .claude/rules/*.md
  │
  ├── 2. 解析每个文件
  │     ├── 读取文件内容
  │     ├── 解析 frontmatter（如有）
  │     │     ├── 检测 agent 类型（仅对特定 agent 可见）
  │     │     ├── 检测 MCP 服务器定义
  │     │     └── 检测 hooks 定义
  │     ├── 处理 @include 指令
  │     │     ├── @path          → 相对路径
  │     │     ├── @./path        → 相对路径
  │     │     ├── @~/path        → Home 路径
  │     │     └── @/path         → 绝对路径
  │     └── 防止循环引用（已处理文件追踪）
  │
  ├── 3. 按优先级排序
  │     └── 近 CWD 的文件排在后面 → 模型更关注
  │
  ├── 4. 检查文件大小
  │     └── MAX_MEMORY_CHARACTER_COUNT = 40,000 字符
  │         └── 超出时截断并警告
  │
  ├── 5. 触发 InstructionsLoaded hooks
  │     └── executeInstructionsLoadedHooks()
  │
  └── 6. 返回 { claudeMd: "所有文件内容拼接" }
```

### 会话记忆提取流程

```
Post-sampling Hook (每次模型采样后)
  │
  ▼
extractSessionMemory(context)
  │
  ├── 1. 检查门控
  │     ├── querySource !== 'repl_main_thread' → 跳过（子代理不运行）
  │     ├── isSessionMemoryGateEnabled() → GrowthBook feature gate
  │     └── isAutoCompactEnabled() → 需要开启自动压缩
  │
  ├── 2. 检查阈值
  │     ├── shouldExtractMemory(messages)
  │     │     ├── 初始化阈值：minimumMessageTokensToInit（默认值）
  │     │     ├── 更新阈值：minimumTokensBetweenUpdate
  │     │     ├── 工具调用阈值：toolCallsBetweenUpdates
  │     │     └── 最后一个 assistant turn 无工具调用（安全点）
  │     └── 不满足 → 跳过
  │
  ├── 3. 设置文件
  │     └── setupSessionMemoryFile()
  │         ├── 创建 ~/.claude/session-memory/ 目录
  │         ├── 创建会话记忆文件（如不存在）
  │         └── 加载模板内容
  │
  ├── 4. 构建 prompt
  │     └── buildSessionMemoryUpdatePrompt(currentMemory, memoryPath)
  │
  ├── 5. 运行 Fork Agent
  │     └── runForkedAgent({
  │           promptMessages: [extractionPrompt],
  │           cacheSafeParams: createCacheSafeParams(context),
  │           canUseTool: createMemoryFileCanUseTool(memoryPath),
  │           querySource: 'session_memory',
  │         })
  │         └── canUseTool 仅允许 Edit 该记忆文件
  │
  └── 6. 记录指标
        └── logEvent('tengu_session_memory_extraction', { tokens, config })
```

### 持久记忆提取流程

```
handleStopHooks (模型生成最终响应后)
  │
  ▼
extractAutoMemories(context)
  │
  ├── 1. 检查启用状态
  │     └── isAutoMemoryEnabled() → 检查设置
  │
  ├── 2. 扫描现有记忆文件
  │     └── scanMemoryFiles(autoMemPath)
  │         └── 读取所有 .md 文件 → formatMemoryManifest()
  │
  ├── 3. 构建提取 prompt
  │     └── buildExtractAutoOnlyPrompt() 或 buildExtractCombinedPrompt()
  │         ├── 分析最近 N 条消息
  │         ├── 检查现有记忆文件（避免重复）
  │         └── 指导 Agent 创建/更新记忆
  │
  ├── 4. 运行 Fork Agent
  │     └── runForkedAgent({
  │           canUseTool: 仅允许 FileEdit/FileWrite 在 memory 目录
  │           工具白名单: FileRead, Grep, Glob, Bash(只读), FileEdit, FileWrite
  │         })
  │
  └── 5. 记忆文件写入
        └── ~/.claude/projects/<path>/memory/
            └── 带类型 frontmatter 的 .md 文件
                ---
                type: User
                ---
                用户偏好内容...
```

**提取 prompt 示例**（`buildExtractAutoOnlyPrompt` 的实际内容）：

```
You are now acting as the memory extraction subagent. Analyze the most recent ~N messages above and use them to update your persistent memory systems.

Available tools: FileRead, GrepTool, GlobTool, read-only Bash (ls/find/cat/stat/wc/head/tail), and FileEdit/FileWrite for paths inside the memory directory only. Bash rm is not permitted.

You have a limited turn budget. FileEdit requires a prior FileRead of the same file, so: turn 1 — issue all FileRead calls in parallel; turn 2 — issue all FileEdit/FileWrite calls in parallel. Do not interleave reads and writes.

You MUST only use content from the last ~N messages to update your persistent memories. Do not waste turns investigating or verifying — no grepping source files, no git commands.

If the user explicitly asks you to remember something, save it immediately as whichever type fits best. If they ask you to forget something, find and remove the relevant entry.

[四类记忆类型定义: user, feedback, project, reference — 见 memoryTypes.ts]

## How to save memories
Saving a memory is a two-step process:
1. write the memory to its own file (e.g., `user_role.md`) with frontmatter format
2. add a pointer to that file in `MEMORY.md` index (max 150 chars per entry)
```

**Session Memory 模板**（会话记忆，用于 compaction 后恢复状态）：

```
# Session Title
_A short and distinctive 5-10 word descriptive title for the session. Super info dense, no filler_

# Current State
_What is actively being worked on right now? Pending tasks not yet completed. Immediate next steps._

# Task specification
_What did the user ask to build? Any design decisions or other explanatory context_

# Files and Functions
_What are the important files? In short, what do they contain and why are they relevant?_

# Workflow
_What bash commands are usually run and in what order? How to interpret their output if not obvious?_

# Errors & Corrections
_Errors encountered and how they were fixed. What did the user correct? What approaches failed and should not be tried again?_

# Codebase and System Documentation
_What are the important system components? How do they work/fit together?_

# Learnings
_What has worked well? What has not? What to avoid? Do not duplicate items from other sections_

# Key results
_If the user asked a specific output such as an answer to a question, a table, or other document, repeat the exact result here_

# Worklog
_Step by step, what was attempted, done? Very terse summary for each step_
```

### 会话恢复流程

```
用户执行 claude --resume 或 /resume
  │
  ▼
switchSession(sessionId)
  │
  ├── 1. 读取 JSONL 文件
  │     └── parseJSONL(sessionFilePath)
  │         └── 逐行解析消息
  │
  ├── 2. 反序列化消息
  │     ├── 重建 Message 对象
  │     ├── 恢复 content replacement 状态
  │     └── 重建 file history 快照
  │
  ├── 3. 处理 compaction 边界
  │     └── 遇到 compact_boundary → 标记后续消息为摘要后
  │
  ├── 4. 恢复工具状态
  │     ├── 重建文件状态缓存
  │     └── 恢复 MCP 客户端连接
  │
  └── 5. 继续对话
        └── 加载恢复的消息到 query() 循环
```

---

## 关键代码

### CLAUDE.md 加载引擎

`src/utils/claudemd.ts` 实现了完整的 CLAUDE.md 加载逻辑：

```typescript
// src/utils/claudemd.ts 头部注释
// 文件加载顺序：
// 1. Managed memory (/etc/claude-code/CLAUDE.md) - 全局指令
// 2. User memory (~/.claude/CLAUDE.md) - 私有全局指令
// 3. Project memory (CLAUDE.md, .claude/CLAUDE.md, .claude/rules/*.md)
// 4. Local memory (CLAUDE.local.md) - 私有项目指令
//
// 加载按优先级从低到高：后面的文件模型更关注

// @include 指令支持：
// - @path, @./relative/path, @~/home/path, @/absolute/path
// - 仅在叶文本节点工作（不在代码块内）
// - 循环引用防护
// - 不存在的文件静默忽略

const MAX_MEMORY_CHARACTER_COUNT = 40000  // 单文件最大字符数
```

支持的文本文件扩展名（防止加载二进制文件）：
```typescript
const TEXT_FILE_EXTENSIONS = new Set([
  '.md', '.txt', '.text',
  '.json', '.yaml', '.yml', '.toml',
  '.js', '.ts', '.jsx', '.tsx',
  '.py', '.rb', '.go', '.rs',
  '.sh', '.bash', '.zsh',
  '.css', '.html', '.xml', '.svg',
  '.gitignore', '.env',
])
```

### 会话记忆提取

`src/services/SessionMemory/sessionMemory.ts` 实现了会话记忆管理：

```typescript
// 触发条件检查
export function shouldExtractMemory(messages: Message[]): boolean {
  const currentTokenCount = tokenCountWithEstimation(messages)

  // 1. 初始化阈值
  if (!isSessionMemoryInitialized()) {
    if (!hasMetInitializationThreshold(currentTokenCount)) return false
    markSessionMemoryInitialized()
  }

  // 2. 更新阈值（必须满足 token 阈值）
  const hasMetTokenThreshold = hasMetUpdateThreshold(currentTokenCount)

  // 3. 工具调用阈值
  const toolCallsSinceLastUpdate = countToolCallsSince(messages, lastMemoryMessageUuid)
  const hasMetToolCallThreshold = toolCallsSinceLastUpdate >= getToolCallsBetweenUpdates()

  // 4. 安全点检查（最后 assistant turn 无工具调用）
  const hasToolCallsInLastTurn = hasToolCallsInLastAssistantTurn(messages)

  // 触发条件：token 阈值 + (工具调用阈值 OR 安全点)
  return (hasMetTokenThreshold && hasMetToolCallThreshold) ||
         (hasMetTokenThreshold && !hasToolCallsInLastTurn)
}
```

工具权限限制——只允许编辑记忆文件：
```typescript
export function createMemoryFileCanUseTool(memoryPath: string): CanUseToolFn {
  return async (tool, input) => {
    if (tool.name === FILE_EDIT_TOOL_NAME &&
        typeof input === 'object' && input?.file_path === memoryPath) {
      return { behavior: 'allow', updatedInput: input }
    }
    return {
      behavior: 'deny',
      message: `only ${FILE_EDIT_TOOL_NAME} on ${memoryPath} is allowed`,
    }
  }
}
```

### 持久记忆提取

`src/services/extractMemories/extractMemories.ts` 使用 fork agent 模式：

```typescript
// 记忆提取 prompt 的核心指导
function opener(newMessageCount, existingMemories): string {
  return [
    `You are now acting as the memory extraction subagent. Analyze the most recent ~${newMessageCount} messages...`,
    '',
    `Available tools: FileRead, Grep, Glob, read-only Bash, and FileEdit/FileWrite for paths inside the memory directory only.`,
    '',
    `You have a limited turn budget. The efficient strategy is:
     turn 1 — issue all FileRead calls in parallel
     turn 2 — issue all FileWrite/FileEdit calls in parallel`,
    '',
    `You MUST only use content from the last ~${newMessageCount} messages.`,
  ].join('\n')
}
```

工具白名单（严格限制）：
```typescript
const ALLOWED_TOOLS = new Set([
  FILE_READ_TOOL_NAME,      // 读取文件
  GREP_TOOL_NAME,           // 搜索内容
  GLOB_TOOL_NAME,           // 文件匹配
  BASH_TOOL_NAME,           // 仅只读命令
  FILE_EDIT_TOOL_NAME,      // 编辑记忆文件
  FILE_WRITE_TOOL_NAME,     // 写入记忆文件
])
// 所有其他工具（MCP, Agent, 写入 Bash）都会被拒绝
```

### 记忆文件格式

记忆文件使用 frontmatter 标记类型：

```markdown
---
type: User
---

## 用户偏好

- 用户偏好使用 TypeScript 进行开发
- 测试框架使用 Vitest
- 喜欢使用函数式风格

---
type: Project
---

## 项目约定

- API 响应使用 camelCase
- 组件使用 PascalCase 命名
```

### 会话 JSONL 读写

`src/utils/sessionStorage.ts` 管理会话持久化：

```typescript
// 写入 agent 元数据（fire-and-forget）
void writeAgentMetadata(agentId, {
  agentType: agentDefinition.agentType,
  worktreePath,     // worktree 隔离路径
  description,      // 原始任务描述
})

// 记录 sidechain transcript
void recordSidechainTranscript(initialMessages, agentId)

// 更新 session name
updateSessionName(sessionId, name)
```

JSONL 格式支持增量写入和断点恢复：
- 每条消息一行 JSON
- 包含 UUID 用于 parent chain 追踪
- 支持 `compact_boundary` 标记压缩点
- 支持 `context_collapse` 记录压缩详情

### Agent 记忆管理

```
src/tools/AgentTool/
├── agentMemory.ts           ← Agent 记忆快照接口
└── agentMemorySnapshot.ts   ← 记忆快照序列化
```

Agent 的 transcript 被存储在 `~/.claude/projects/<path>/subagents/` 目录下：
- 每个 Agent 有独立的 transcript 文件
- 支持 `transcriptSubdir` 分组（如 workflows/runId/）
- Agent 完成后清理 transcript subdir 映射

---

## 练习

1. **CLAUDE.md 加载**：阅读 `src/utils/claudemd.ts`，追踪 `@include` 指令的解析逻辑。理解循环引用防护机制和文件扩展名白名单的作用。

2. **会话记忆阈值**：阅读 `src/services/SessionMemory/sessionMemory.ts` 和 `sessionMemoryUtils.ts`。理解 `shouldExtractMemory()` 的三重阈值（初始化 token / 更新 token / 工具调用数）如何协同工作，以及为什么最后一个 assistant turn 不能有工具调用。

3. **持久记忆提取**：阅读 `src/services/extractMemories/extractMemories.ts` 和 `prompts.ts`。理解为什么记忆提取使用 fork agent 模式而不是直接写入——考虑 prompt cache 共享和上下文隔离。

4. **会话 JSONL**：阅读 `src/utils/sessionStorage.ts` 中的写入函数。理解 `recordSidechainTranscript()` 的 `lastRecordedUuid` 参数如何维护消息的 parent chain。

5. **设置同步**：追踪 `getCurrentProjectConfig()` 和 `saveCurrentProjectConfig()` 的调用链。理解 `.claude/settings.json` 和 `.claude/settings.local.json` 的区别，以及为什么 `settings.local.json` 不被 git 追踪。

---

## 下一篇

👉 [10-skills-and-plugins.md](./10-skills-and-plugins.md) — Skills 与插件系统
