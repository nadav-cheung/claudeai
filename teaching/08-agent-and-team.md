---
title: "Agent 与多 Agent 协作"
description: "理解 Claude Code 中 Agent 子代理的生成机制、多 Agent 团队（Swarm）的创建与生命周期管理、消息传递系统，以及三种任务类型的实现差异。"
tags: [agent, multi-agent, team, swarm]
date: 2026-05-09
---

# 08 - Agent 与多 Agent 协作

> **本章目标**：理解 Claude Code 中 Agent 子代理的生成机制、多 Agent 团队（Swarm）的创建与生命周期管理、消息传递系统，以及三种任务类型（LocalAgentTask / InProcessTeammateTask / RemoteAgentTask）的实现差异。

---

## 目标

- 理解 Agent 工具的核心架构：同步/异步/后台执行
- 掌握 Agent 生成（spawning）的两种模式：fork 共享上下文 vs 独立子代理
- 了解团队（Team）的创建、成员管理和生命周期
- 理解三种任务后端（Local / InProcess / Remote）的适用场景
- 掌握消息传递（SendMessage）和团队协调机制
- 理解 Coordinator 模式和权限隔离

---

## 核心概念

### Agent 类型层次

Claude Code 的 Agent 系统采用分层架构：

```
主会话 (Main Session)
  │
  ├── 同步 Agent (sync)            ← 阻塞主线程，使用父级 abortController
  │     └── 直接返回结果给模型
  │
  ├── 异步 Agent (async)           ← 后台执行，有独立的 abortController
  │     └── LocalAgentTask         ← 后台任务管理
  │     └── 完成后通知主会话
  │
  └── 团队成员 (Teammate)          ← 多 Agent 协作
        ├── InProcessTeammateTask   ← 同进程，AsyncLocalStorage 隔离
        │     └── tmux/iTerm2 pane 展示
        └── RemoteAgentTask        ← 远程 CCR 环境
              └── 独立云环境执行
```

### 团队（Team/Swarm）概念

团队是多 Agent 协作的核心抽象：

```
Team (config.json)
  ├── lead (team-lead)        ← 主控 Agent，协调任务
  │     └── 在主会话中运行
  │
  ├── member-a (researcher)   ← 团队成员，独立 pane
  │     ├── tmuxPaneId        ← UI 展示
  │     ├── worktreePath      ← Git 工作树隔离
  │     ├── subscriptions     ← 订阅的消息频道
  │     └── mode              ← 权限模式
  │
  └── member-b (test-runner)  ← 另一个团队成员
        └── ...
```

### Agent 生成模式

```
1. Fork 模式 (共享上下文)
   ├── 克隆主会话的 system prompt
   ├── 通过 buildForkedMessages() 克隆消息到子代理上下文
   ├── 相同消息内容 → API 端利用 prompt cache（cache_control: ephemeral）
   └── 用于：Explore, Plan, 等一次性搜索任务

2. 独立模式 (隔离上下文)
   ├── 新的 system prompt
   ├── 仅传入 task prompt
   ├── 独立工具权限
   └── 用于：通用 Agent 任务、后台任务

3. Worktree 隔离
   ├── 创建 git worktree
   ├── Agent 在隔离的文件系统中操作
   ├── 完成后合并或丢弃
   └── 用于：可能产生文件冲突的并行任务
```

---

## 源码导览

### Agent 工具架构

```
src/tools/AgentTool/
├── AgentTool.tsx           ← Agent 工具主入口：调度逻辑
├── runAgent.ts             ← Agent 执行循环：query() 包装
├── forkSubagent.ts         ← Fork 模式：上下文共享和 prompt cache
├── built-in/               ← 内置 Agent 定义
│   └── generalPurposeAgent.ts
├── builtInAgents.ts        ← 内置 Agent 注册表
├── loadAgentsDir.ts        ← 从 .claude/agents/ 加载自定义 Agent
├── agentToolUtils.ts       ← 工具解析、进度追踪、结果处理
├── agentColorManager.ts    ← Agent 颜色分配（UI 区分）
├── agentDisplay.ts         ← Agent 显示信息
├── agentMemory.ts          ← Agent 记忆快照
├── agentMemorySnapshot.ts  ← 记忆快照序列化
├── constants.ts            ← 常量定义
├── prompt.ts               ← Agent 工具 prompt
├── resumeAgent.ts          ← Agent 恢复（断点续传）
├── UI.tsx                  ← 渲染组件
└── agentToolUtils.ts       ← 工具名解析和分类
```

### 多 Agent 协作架构

```
src/utils/swarm/
├── teamHelpers.ts          ← 团队文件管理：CRUD、成员操作
├── constants.ts            ← 常量：TEAM_LEAD_NAME, 环境变量
├── spawnInProcess.ts       ← 进程内队友生成
├── spawnUtils.ts           ← 生成工具函数
├── teammateInit.ts         ← 队友初始化
├── teammateModel.ts        ← 队友模型选择
├── teammateLayoutManager.ts ← 队友 UI 布局管理
├── teammatePromptAddendum.ts ← 队友系统 prompt 附加
├── leaderPermissionBridge.ts ← Leader 权限桥接
├── permissionSync.ts       ← 权限同步
├── reconnection.ts         ← 重连逻辑
├── It2SetupPrompt.tsx      ← IT2 设置 prompt
├── inProcessRunner.ts      ← 进程内执行器
└── backends/               ← 后端实现
    ├── types.ts            ← BackendType 定义
    └── registry.ts         ← 后端注册表

src/tools/TeamCreateTool/   ← 团队创建工具
src/tools/TeamDeleteTool/   ← 团队删除工具
src/tools/SendMessageTool/  ← 消息传递工具
```

### 任务管理架构

```
src/tasks/
├── types.ts                ← Task 接口和 TaskStateBase
├── pillLabel.ts            ← 任务标签显示
├── stopTask.ts             ← 停止任务
├── LocalAgentTask/         ← 本地后台 Agent 任务
│   └── LocalAgentTask.tsx
├── InProcessTeammateTask/  ← 进程内队友任务
│   ├── InProcessTeammateTask.tsx
│   └── types.ts
├── RemoteAgentTask/        ← 远程 Agent 任务
│   └── RemoteAgentTask.tsx
├── LocalMainSessionTask.ts ← 主会话任务
└── LocalShellTask/         ← Shell 后台任务
```

---

## 数据流图

### Agent 工具调用流程

```
Claude 模型返回 tool_use: Agent({ prompt, description, subagent_type, ... })
  │
  ▼
AgentTool.call(input, context)
  │
  ├── 1. 解析 Agent 定义
  │     ├── subagent_type → 查找 builtInAgents 或 .claude/agents/ 目录
  │     ├── 检查 MCP 服务器要求 (filterAgentsByMcpRequirements)
  │     └── 检查权限 (filterDeniedAgents, getDenyRuleForAgent)
  │
  ├── 2. 判断执行模式
  │     ├── isAsync? → LocalAgentTask (后台)
  │     ├── isTeammate? → InProcessTeammateTask (团队)
  │     ├── isolation: "worktree"? → 创建 git worktree
  │     └── 默认 → 同步执行
  │
  ├── 3. Fork 模式检查
  │     ├── isForkSubagentEnabled? → buildForkedMessages()
  │     │     └── 克隆主会话上下文 → prompt cache 命中
  │     └── 否则 → 独立 prompt
  │
  ├── 4. 构建工具池 (assembleToolPool)
  │     ├── 解析 allowedTools
  │     └── resolveAgentTools() → 过滤不适用的工具
  │
  ├── 5. 初始化 Agent MCP 服务器
  │     └── initializeAgentMcpServers()
  │         ├── 字符串引用 → 共享父级的 MCP 客户端
  │         └── 内联定义 → 新建连接，Agent 结束时清理
  │
  ├── 6. 创建子代理上下文
  │     └── createSubagentContext(parent, options)
  │         ├── 共享 setAppState (同步)
  │         └── 独立 abortController (异步)
  │
  └── 7. runAgent() → 执行循环
        ├── for await (const message of query({...}))
        │     ├── 转发 stream_event 到父级
        │     ├── 记录 transcript (recordSidechainTranscript)
        │     └── yield message
        └── finally: 清理 MCP、hooks、transcript、bash 任务
```

### 团队创建流程

```
Claude 模型: TeamCreate({ team_name, description, agent_type })
  │
  ▼
TeamCreateTool.call()
  │
  ├── 1. generateUniqueTeamName(name)
  │     └── 如果已存在 → generateWordSlug() 随机名
  │
  ├── 2. 创建团队目录
  │     └── ~/.claude/teams/{team-name}/config.json
  │
  ├── 3. writeTeamFile(teamName, teamFile)
  │     {
  │       name, description, createdAt,
  │       leadAgentId, leadSessionId,
  │       members: [{
  │         agentId: "team-lead@team-name",
  │         name: "team-lead",
  │         joinedAt, tmuxPaneId, cwd
  │       }]
  │     }
  │
  ├── 4. registerTeamForSessionCleanup(teamName)
  │     └── 注册到 sessionCreatedTeams Set
  │         └── 退出时自动清理未删除的团队
  │
  ├── 5. ensureTasksDir(teamName)
  │     └── ~/.claude/tasks/{team-name}/
  │
  └── 6. setLeaderTeamName(teamName)
        └── 标记当前会话为团队 leader
```

### 消息传递流程

```
Agent A: SendMessage({ to: "researcher", message: "..." })
  │
  ▼
SendMessageTool.call()
  │
  ├── 1. parseAddress(to)
  │     ├── "researcher" → teammate 名
  │     ├── "*" → 广播
  │     ├── "uds:<path>" → UDS 本地对等
  │     └── "bridge:<session>" → Remote Control
  │
  ├── 2. 查找目标 Agent
  │     ├── readTeamFileAsync(teamName)
  │     ├── findTeammateTaskByAgentId(agentId)
  │     └── isLocalAgentTask() → 后台任务消息队列
  │
  ├── 3. 结构化消息
  │     ├── shutdown_request / shutdown_response
  │     ├── plan_approval_response
  │     └── 自由文本消息
  │
  ├── 4. 投递消息
  │     ├── writeToMailbox(target, message)  ← 队友邮箱
  │     ├── queuePendingMessage(taskId, msg) ← 后台任务队列
  │     └── 广播: 遍历所有成员逐一投递
  │
  └── 5. 返回发送确认
```

---

## 关键代码

### AgentTool 输入 Schema

Agent 工具支持丰富的配置参数：

```typescript
// src/tools/AgentTool/AgentTool.tsx
const baseInputSchema = z.object({
  description: z.string(),       // 3-5 词任务描述
  prompt: z.string(),            // 具体任务指令
  subagent_type: z.string().optional(),  // Agent 类型
  model: z.enum(['sonnet', 'opus', 'haiku']).optional(),
  run_in_background: z.boolean().optional(),
})

// 多 Agent 参数（Swarm 模式）
const multiAgentInputSchema = z.object({
  name: z.string().optional(),          // Agent 名称（可寻址）
  team_name: z.string().optional(),     // 团队名
  mode: permissionModeSchema().optional(), // 权限模式
})

// 隔离参数
isolation: z.enum(['worktree', 'remote']).optional()
cwd: z.string().optional()
```

### runAgent 执行循环

`src/tools/AgentTool/runAgent.ts` 是 Agent 执行的核心：

```typescript
export async function* runAgent({
  agentDefinition, promptMessages, toolUseContext,
  canUseTool, isAsync, availableTools, ...
}): AsyncGenerator<Message, void> {

  // 1. 解析模型和权限
  const resolvedAgentModel = getAgentModel(...)
  const agentId = createAgentId()

  // 2. Fork 上下文处理
  const contextMessages = forkContextMessages
    ? filterIncompleteToolCalls(forkContextMessages) : []
  const initialMessages = [...contextMessages, ...promptMessages]

  // 3. 优化上下文（只读 Agent 省略 CLAUDE.md 和 gitStatus）
  const shouldOmitClaudeMd = agentDefinition.omitClaudeMd && !override?.userContext

  // 4. 初始化 Agent 专属 MCP 服务器
  const { clients, tools, cleanup } = await initializeAgentMcpServers(
    agentDefinition, parentClients
  )

  // 5. 创建隔离的子代理上下文
  const agentToolUseContext = createSubagentContext(toolUseContext, {
    options: agentOptions,
    agentId,
    agentType: agentDefinition.agentType,
    abortController: isAsync ? new AbortController() : toolUseContext.abortController,
  })

  // 6. 执行主循环
  try {
    for await (const message of query({
      messages: initialMessages,
      systemPrompt: agentSystemPrompt,
      canUseTool,
      toolUseContext: agentToolUseContext,
    })) {
      // 转发 API 指标
      if (message.type === 'stream_event') {
        toolUseContext.pushApiMetricsEntry?.(message.ttftMs)
        continue
      }
      // 记录 transcript
      if (isRecordableMessage(message)) {
        await recordSidechainTranscript([message], agentId, lastRecordedUuid)
        yield message
      }
    }
  } finally {
    // 清理：MCP、hooks、transcript、bash 任务
    await mcpCleanup()
    clearSessionHooks(rootSetAppState, agentId)
    killShellTasksForAgent(agentId, ...)
  }
}
```

### 团队文件管理

`src/utils/swarm/teamHelpers.ts` 管理团队状态文件：

```typescript
type TeamFile = {
  name: string
  description?: string
  createdAt: number
  leadAgentId: string
  leadSessionId?: string
  hiddenPaneIds?: string[]
  teamAllowedPaths?: TeamAllowedPath[]
  members: Array<{
    agentId: string           // "researcher@my-team"
    name: string              // "researcher"
    agentType?: string
    model?: string
    color?: string
    planModeRequired?: boolean
    joinedAt: number
    tmuxPaneId: string
    cwd: string
    worktreePath?: string
    sessionId?: string
    subscriptions: string[]   // 订阅的频道
    backendType?: BackendType
    isActive?: boolean
    mode?: PermissionMode
  }>
}
```

关键操作：
- `readTeamFile(teamName)` — 同步读取（React 渲染路径）
- `readTeamFileAsync(teamName)` — 异步读取（工具处理器路径）
- `writeTeamFile(teamName, teamFile)` — 写入
- `removeTeammateFromTeamFile(teamName, { agentId, name })` — 移除成员
- `setMemberMode(teamName, memberName, mode)` — 设置权限模式
- `setMemberActive(teamName, memberName, isActive)` — 设置活跃状态
- `cleanupSessionTeams()` — 会话结束时清理所有未删除的团队

### 三种任务类型

**LocalAgentTask** — 后台 Agent：

```typescript
// src/tasks/LocalAgentTask/LocalAgentTask.tsx
// 管理 run_in_background: true 的 Agent
// 特点：
//   - 独立的 AbortController
//   - 完成后通过 enqueueAgentNotification 通知主会话
//   - 支持 progress tracking（进度追踪）
//   - 支持摘要生成（startAgentSummarization）
```

**InProcessTeammateTask** — 进程内队友：

```typescript
// src/tasks/InProcessTeammateTask/InProcessTeammateTask.tsx
// 特点：
//   - 同一 Node.js 进程，使用 AsyncLocalStorage 隔离
//   - 团队感知身份（agentName@teamName）
//   - 支持 plan mode 审批流程
//   - 可空闲（等待工作）或活跃（处理中）
//   - 通过 killInProcessTeammate() 终止
```

**RemoteAgentTask** — 远程 Agent：

```typescript
// src/tasks/RemoteAgentTask/RemoteAgentTask.tsx
// 特点：
//   - 在远程 CCR (Claude Code Runtime) 环境执行
//   - 始终在后台运行
//   - 需要远程资格检查 (checkRemoteAgentEligibility)
//   - 支持会话 URL 获取 (getRemoteTaskSessionUrl)
```

### 队友系统 Prompt

每个队友会在系统 prompt 后追加一段通信指令：

```typescript
// src/utils/swarm/teammatePromptAddendum.ts
export const TEAMMATE_SYSTEM_PROMPT_ADDENDUM = `
# Agent Teammate Communication

IMPORTANT: You are running as an agent in a team. To communicate with anyone on your team:
- Use the SendMessage tool with \`to: "<name>"\` to send messages to specific teammates
- Use the SendMessage tool with \`to: "*"\` sparingly for team-wide broadcasts

Just writing a response in text is not visible to others on your team - you MUST use the SendMessage tool.
`
```

### Fork 子代理机制

`src/tools/AgentTool/forkSubagent.ts` 实现了上下文共享：

```typescript
// Fork 模式通过克隆主会话消息来共享 prompt cache
export function buildForkedMessages(
  parentMessages: Message[],
  promptMessages: Message[],
): Message[] {
  // 1. 过滤不完整的工具调用
  const filtered = filterIncompleteToolCalls(parentMessages)
  // 2. 拼接上下文 + 新 prompt
  return [...filtered, ...promptMessages]
}

// Fork Agent 类型标识（用于防止无限递归 fork）
export const FORK_AGENT = 'fork'
```

### 团队清理机制

```typescript
// src/utils/swarm/teamHelpers.ts

// 会话结束时清理
export async function cleanupSessionTeams(): Promise<void> {
  const teams = Array.from(getSessionCreatedTeams())
  // 1. 先杀掉所有 pane 后端的队友进程
  await Promise.allSettled(teams.map(name => killOrphanedTeammatePanes(name)))
  // 2. 再清理团队目录、工作树、任务目录
  await Promise.allSettled(teams.map(name => cleanupTeamDirectories(name)))
}

// 清理单个团队的所有资源
export async function cleanupTeamDirectories(teamName: string): Promise<void> {
  // 1. 清理 git worktree
  // 2. 清理 ~/.claude/teams/{team-name}/
  // 3. 清理 ~/.claude/tasks/{team-name}/
}
```

---

## 练习

### 练习 1：Agent 生命周期

**类比 Java**：这类似于 Java 的 `ExecutorService` 管理 `Future` 任务——有同步等待和异步回调两种模式。

**答案**：

| 模式 | 行为 | Java 类比 |
|------|------|----------|
| sync | 阻塞主线程，共享 abortController | `Future.get()` |
| async | 后台执行，独立 abortController | `CompletableFuture.thenAccept()` |
| teammate | 独立 pane，同进程隔离 | `ForkJoinPool` |

### 练习 2：Fork 机制

**答案**：

**共享 prompt cache 的原理**：
```
主会话消息 → [user: hi, assistant: hi]
                 ↓ buildForkedMessages()
子代理消息 → [user: hi, assistant: hi, user: 分析这个文件]
```

**使用场景**：
- `isForkSubagentEnabled`：Explorer、Plan 等一次性任务
- `isInForkChild`：防止无限递归 fork

### 练习 3：团队清理

**答案**：

| 退出类型 | 清理方式 | 原因 |
|---------|---------|------|
| 正常退出 | 优雅清理资源 | 允许成员完成收尾工作 |
| SIGINT | 强制杀进程 | 不可取消的终止信号 |

### 练习 4：消息传递

**答案**：

| 消息类型 | 投递方式 | 说明 |
|---------|---------|------|
| shutdown_request | 邮箱系统 | 协调关闭流程 |
| plan_approval_response | 邮箱系统 | 计划审批 |
| 自由文本 | 邮箱系统 | 通过工具调用传递 |

### 练习 5：权限隔离

**答案**：
- **继承**：子代理默认继承父级的权限模式
- **覆盖**：`mode` 参数可显式指定子代理的权限模式
- **隔离**：`createSubagentContext()` 创建独立的上下文

---

## Agent vs Java 多线程

| 方面 | Claude Code Agent | Java 线程 |
|------|-----------------|----------|
| 创建 | `AgentTool` 工具 | `new Thread()` |
| 上下文 | fork/subagent | `InheritableThreadLocal` |
| 通信 | SendMessage | `BlockingQueue` |
| 隔离 | AsyncLocalStorage | 进程/ClassLoader |
| 生命周期 | 自动管理 | 手动管理 |

---

## 练习答案速查

| 练习 | 核心答案 |
|------|---------|
| 1 | sync=阻塞，async=独立线程，teammate=进程隔离 |
| 2 | fork 克隆消息共享 prompt cache |
| 3 | SIGINT 强制杀进程，正常退出优雅清理 |
| 4 | 消息通过邮箱系统投递 |
| 5 | 默认继承父级，可显式覆盖 |

---

## 下一篇

[09-memory-and-persistence.md](./09-memory-and-persistence.md) — 记忆与持久化
