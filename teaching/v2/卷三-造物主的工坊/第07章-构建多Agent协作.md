---
title: "第07章：构建多Agent协作"
description: "从单一 Agent 到多 Agent 协作——学习 Claude Code 中 Agent 的定义、启动、工具分配和结果收集。理解 AgentTool 的架构，掌握 spawn、fork 和 teammate 三种协作模式。"
tags: [agent, multi-agent, AgentTool, spawn, fork, teammate, subagent, coordination, parallel]
date: 2026-05-10
---

# 第07章：构建多Agent协作

到目前为止，我们一直在讨论单个工具——一个工具做一件事。但有些任务太复杂了，需要多个"工人"协同完成。比如你想同时搜索三个数据库，或者让一个 Agent 做研究、另一个 Agent 写代码。

Claude Code 通过 `AgentTool` 实现了多 Agent 协作。这不是一个普通工具——它是一个**工具工厂**，能够启动独立的子进程（Agent），每个子进程都有自己的系统提示词、工具集和对话历史。

这一章，我们深入 `src/tools/AgentTool/` 目录，理解多 Agent 协作是如何构建的。

---

## 目标

完成这一章后，你将能够：

1. 理解 `AgentDefinition` 的结构——一个 Agent 由什么组成
2. 掌握 Agent 启动的完整流程——从输入解析到子进程运行
3. 理解三种协作模式：spawn（类型化 Agent）、fork（继承式分支）、teammate（独立协作者）
4. 学会为 Agent 分配工具和配置权限
5. 理解结果收集和生命周期管理

---

## 动手

### 第一步：认识 AgentDefinition——Agent 的蓝图

每个 Agent 都由一个 `AgentDefinition` 定义。这是 Agent 的"基因"，决定了它的行为、能力和边界：

```typescript
// 文件：src/tools/AgentTool/loadAgentsDir.ts（简化）
type AgentDefinition = {
  agentType: string              // Agent 的类型标识，如 "Explore"、"Plan"
  whenToUse: string              // 什么时候使用这个 Agent
  tools?: string[]               // Agent 可以使用的工具白名单
  disallowedTools?: string[]     // Agent 不能使用的工具黑名单
  model?: string                 // 模型偏好
  permissionMode?: PermissionMode // 权限模式
  maxTurns?: number              // 最大对话轮数
  skills?: string[]              // 预加载的技能
  hooks?: HooksSettings          // Agent 的钩子配置
  mcpServers?: AgentMcpServerSpec[] // Agent 专属的 MCP 服务器
  getSystemPrompt: (context) => string  // Agent 的系统提示词
}
```

这些字段控制了 Agent 的方方面面：

- **`tools` 和 `disallowedTools`**——控制 Agent 能用什么工具。没有配置时，Agent 可以使用所有工具
- **`permissionMode`**——控制 Agent 的权限级别。比如 `plan` 模式下 Agent 不能执行写操作
- **`maxTurns`**——限制 Agent 的最大对话轮数，防止失控
- **`mcpServers`**——Agent 可以自带 MCP 服务器，不依赖全局配置

Claude Code 内置了几个 Agent。让我们看看它们的定义：

```typescript
// 文件：src/tools/AgentTool/builtInAgents.ts
export function getBuiltInAgents(): AgentDefinition[] {
  const agents: AgentDefinition[] = [
    GENERAL_PURPOSE_AGENT,    // 通用 Agent
    STATUSLINE_SETUP_AGENT,   // 状态栏设置
  ]

  if (areExplorePlanAgentsEnabled()) {
    agents.push(EXPLORE_AGENT, PLAN_AGENT)  // 探索和规划
  }

  // ...
  return agents
}
```

其中 `Explore` Agent 是一个只读的搜索工具，它的定义大致是：

- `tools: [Read, Grep, Glob, Bash]`（只读工具）
- `disallowedTools: [Write, Edit]`（不能写文件）
- `maxTurns: 20`（限制轮数）
- `omitClaudeMd: true`（不需要 CLAUDE.md 上下文，节省 token）

### 第二步：Agent 的输入——启动参数

当 AI 调用 AgentTool 时，它传递一组参数来控制 Agent 的启动：

```typescript
// 文件：src/tools/AgentTool/AgentTool.tsx
const baseInputSchema = lazySchema(() => z.object({
  description: z.string()
    .describe('A short (3-5 word) description of the task'),
  prompt: z.string()
    .describe('The task for the agent to perform'),
  subagent_type: z.string().optional()
    .describe('The type of specialized agent to use for this task'),
  model: z.enum(['sonnet', 'opus', 'haiku']).optional()
    .describe("Optional model override for this agent"),
  run_in_background: z.boolean().optional()
    .describe('Set to true to run this agent in the background'),
}))
```

关键参数解释：

- **`prompt`**——给 Agent 的任务描述。这是最重要的参数。Agent 看不到父 Agent 的对话历史（除非是 fork 模式），所以 `prompt` 需要包含足够的上下文
- **`subagent_type`**——选择哪种类型的 Agent。不指定时使用 `GENERAL_PURPOSE_AGENT`
- **`run_in_background`**——是否在后台运行。前台 Agent 会阻塞父 Agent，后台 Agent 异步运行，完成后通知

### 第三步：Agent 的启动流程——runAgent

当 AI 调用 AgentTool 时，核心函数 `runAgent` 被调用。让我们追踪它的完整流程：

```typescript
// 文件：src/tools/AgentTool/runAgent.ts
export async function* runAgent({
  agentDefinition,
  promptMessages,
  toolUseContext,
  canUseTool,
  isAsync,
  // ...
}): AsyncGenerator<Message, void> {
```

`runAgent` 是一个异步生成器——它逐步产出消息，而不是一次性返回。这个设计让 UI 可以实时显示 Agent 的进展。

启动流程按以下顺序进行：

**3a. 创建 Agent 上下文。** Agent 获得自己的 `toolUseContext`——包括独立的消息历史、文件状态缓存和权限设置：

```typescript
const agentToolUseContext = createSubagentContext(toolUseContext, {
  options: agentOptions,
  agentId,
  agentType: agentDefinition.agentType,
  messages: initialMessages,
  readFileState: agentReadFileState,
  abortController: agentAbortController,
  getAppState: agentGetAppState,
  // ...
})
```

**3b. 工具分配。** Agent 的工具集由 `resolveAgentTools` 决定：

```typescript
const resolvedTools = resolveAgentTools(
  agentDefinition,
  availableTools,
  isAsync,
).resolvedTools
```

如果 Agent 定义了 `tools` 白名单，只有列表中的工具被分配。如果定义了 `disallowedTools` 黑名单，被列出的工具被移除。如果两者都没定义，Agent 获得完整的工具集。

**3c. 权限继承。** Agent 的权限可以独立于父 Agent：

```typescript
const agentGetAppState = () => {
  const state = toolUseContext.getAppState()
  let toolPermissionContext = state.toolPermissionContext

  // Agent 可以覆盖权限模式（但 bypass 和 acceptEdits 永远优先）
  if (agentPermissionMode &&
      state.toolPermissionContext.mode !== 'bypassPermissions' &&
      state.toolPermissionContext.mode !== 'acceptEdits') {
    toolPermissionContext = {
      ...toolPermissionContext,
      mode: agentPermissionMode,
    }
  }

  // 后台 Agent 不能弹出权限对话框
  if (isAsync) {
    toolPermissionContext = {
      ...toolPermissionContext,
      shouldAvoidPermissionPrompts: true,
    }
  }
  // ...
}
```

注意一个关键的安全设计：**父 Agent 的 `bypassPermissions` 模式永远优先于子 Agent 的权限设置**。即使子 Agent 定义了自己的权限模式，如果父 Agent 在 bypass 模式下，子 Agent 也会 bypass。

**3d. MCP 服务器初始化。** Agent 可以定义自己的 MCP 服务器，在启动时连接，结束时清理：

```typescript
const { clients: mergedMcpClients, tools: agentMcpTools, cleanup: mcpCleanup } =
  await initializeAgentMcpServers(agentDefinition, toolUseContext.options.mcpClients)
```

这意味着一个研究型 Agent 可以自带一个论文检索 MCP 服务器，不需要全局配置。

**3e. 进入查询循环。** Agent 的核心是一个 `query()` 循环——它不断与 AI 模型对话，执行工具调用，直到任务完成或达到轮数限制：

```typescript
for await (const message of query({
  messages: initialMessages,
  systemPrompt: agentSystemPrompt,
  userContext: resolvedUserContext,
  systemContext: resolvedSystemContext,
  canUseTool,
  toolUseContext: agentToolUseContext,
  querySource,
  maxTurns: maxTurns ?? agentDefinition.maxTurns,
})) {
  // 实时转发消息给父 Agent
  yield message
}
```

### 第四步：三种协作模式

Claude Code 支持三种 Agent 协作模式，各有适用场景。

**模式一：spawn——类型化 Agent。** 通过 `subagent_type` 指定一个预定义的 Agent 类型。这是最常用的模式：

```
Agent({
  subagent_type: "Explore",
  prompt: "Search the codebase for all files related to authentication",
  description: "auth search"
})
```

spawn 出来的 Agent 从零开始——没有父 Agent 的对话历史，只有 `prompt` 中提供的上下文。这意味着 `prompt` 必须足够详细，包含所有必要信息。

**模式二：fork——继承式分支。** 不指定 `subagent_type`（在启用 fork 功能时），Agent 会继承父 Agent 的完整对话历史：

```
Agent({
  prompt: "Check if the migration is safe",
  description: "migration review"
})
```

fork 的优势是子进程能看到父 Agent 之前的所有对话，不需要在 `prompt` 中重复上下文。它的代价是消耗更多的 token（因为对话历史很长）。

fork 的设计有一个精妙的优化——**prompt cache 共享**。所有 fork 子进程共享相同的 API 请求前缀（父 Agent 的对话历史），只有最后的指令不同。这意味着多个 fork 可以复用 prompt cache，大幅减少 token 消耗：

```typescript
// 文件：src/tools/AgentTool/forkSubagent.ts
export function buildForkedMessages(directive, assistantMessage) {
  // 保持完整的 assistant 消息（所有 tool_use 块）
  // 用相同的占位符替换所有 tool_result
  // 只有最后的指令文本不同
  // → 最大化 prompt cache 命中率
}
```

**模式三：teammate——独立协作者。** 通过 `name` 参数启动一个命名的 Agent，它成为团队的一员：

```
Agent({
  name: "researcher",
  prompt: "Research the latest authentication patterns",
  description: "auth research"
})
```

teammate 可以通过 `SendMessage({ to: "researcher" })` 被后续联系，形成一个持久化的协作网络。

### 第五步：结果收集——Agent 怎么汇报

Agent 完成任务后，它的结果会以消息的形式返回给父 Agent。`runAgent` 作为异步生成器，逐步 yield 消息：

```typescript
for await (const message of query({ ... })) {
  if (isRecordableMessage(message)) {
    await recordSidechainTranscript([message], agentId, lastRecordedUuid)
    yield message
  }
}
```

对于前台 Agent，结果直接作为工具调用的返回值，AI 在下一轮继续处理。对于后台 Agent，结果通过通知系统送达——AI 会在后续的对话轮中收到一条用户消息，包含 Agent 的完成通知。

Agent 的输出被记录在独立的 `subagents/` 子目录中，这样你可以在会话结束后回看每个 Agent 的完整对话记录。

### 第六步：生命周期管理——从启动到清理

Agent 的生命周期管理很重要——每个 Agent 都会占用资源（内存、API 连接、子进程），需要在结束时正确清理。`runAgent` 使用 try/finally 保证清理总是执行：

```typescript
// 文件：src/tools/AgentTool/runAgent.ts
try {
  for await (const message of query({ ... })) {
    yield message
  }
} finally {
  // 清理 Agent 专属的 MCP 服务器
  await mcpCleanup()
  // 清理 Agent 的 session hooks
  if (agentDefinition.hooks) {
    clearSessionHooks(rootSetAppState, agentId)
  }
  // 释放文件状态缓存
  agentToolUseContext.readFileState.clear()
  // 终止 Agent 启动的后台 shell 任务
  killShellTasksForAgent(agentId, ...)
  // 清理 todo 状态
  rootSetAppState(prev => {
    const { [agentId]: _removed, ...todos } = prev.todos
    return { ...prev, todos }
  })
}
```

这个 finally 块做了五件事：

1. **清理 MCP 连接**——关闭 Agent 专属的 MCP 服务器连接
2. **清理 hooks**——移除 Agent 注册的 session hooks
3. **释放缓存**——清空文件状态缓存，回收内存
4. **杀掉后台任务**——终止 Agent 启动的后台 shell 进程
5. **清理状态**——从 AppState 中移除 Agent 的 todo 列表

### 第七步：权限控制——哪些 Agent 能被使用

不是所有 Agent 都能被随意使用。权限系统支持按 Agent 类型进行控制：

```typescript
// 文件：src/utils/permissions/permissions.ts
export function getDenyRuleForAgent(context, agentToolName, agentType) {
  return getDenyRules(context).find(
    rule => rule.ruleValue.toolName === agentToolName &&
            rule.ruleValue.ruleContent === agentType
  ) || null
}
```

你可以配置 `Agent(Explore)` → deny 来禁用 Explore Agent。这个权限检查发生在 Agent 启动之前，被拒绝的 Agent 不会出现在可用列表中。

### 第八步：隔离——worktree 模式

有时候你希望 Agent 在一个隔离的环境中工作，不影响当前代码。AgentTool 支持通过 `isolation: "worktree"` 参数在 Git worktree 中运行 Agent：

```
Agent({
  isolation: "worktree",
  prompt: "Implement feature X",
  description: "feature implementation"
})
```

worktree 模式会创建一个 Git 工作树的副本，Agent 在副本中操作。如果 Agent 做了修改，worktree 的路径和分支会返回给父 Agent。如果没有修改，worktree 会被自动清理。

---

## 遇到问题？

### 问题 1：Agent 启动后没有反应

**症状**：调用了 AgentTool，但 Agent 似乎卡住了，没有输出。

**原因**：可能是 Agent 在等待权限确认（前台模式），或者 Agent 的 MCP 服务器连接超时（后台模式）。

**解决方案**：

- 前台 Agent：检查是否有权限提示等待确认
- 后台 Agent：检查 `/mcp` 状态，确认 MCP 服务器已连接
- 检查 `maxTurns` 是否太小（Agent 在达到轮数限制后自动停止）

### 问题 2：Agent 的工具不够用

**症状**：Agent 报错说没有某个工具。

**原因**：Agent 的工具集受到 `tools` 和 `disallowedTools` 的限制。如果 Agent 定义中没有包含需要的工具，它就无法使用。

**解决方案**：检查 Agent 定义中的 `tools` 列表。如果是自定义 Agent，把需要的工具加入列表。如果是内置 Agent，它的工具集是预定义的，不能修改。

### 问题 3：后台 Agent 的权限被自动拒绝

**症状**：后台 Agent 的工具调用被自动拒绝，而不是弹出确认对话框。

**原因**：这是预期行为。后台 Agent 不能弹出 UI 对话框，所以当权限系统决定 `ask`（需要确认）时，后台 Agent 会自动变成 `deny`。

**解决方案**：为后台 Agent 预先配置好 allow 规则。比如在配置中添加 `Bash(npm test)` → allow，这样后台 Agent 执行测试时就不会被权限系统拦截。

### 问题 4：fork 子进程产生了意料之外的行为

**症状**：fork 出来的 Agent 不遵循指令，或者做了不该做的事情。

**原因**：fork 继承了父 Agent 的完整对话历史，包括系统提示词中的所有指令。如果父 Agent 的系统提示词中包含"默认使用 fork"之类的建议，子 Agent 也可能尝试 fork 自己——导致递归。

**解决方案**：fork 子进程会被注入一条特殊的 boilerplate 消息，明确告诉它"你不是主 Agent，不要 fork"。源码中有专门的递归检测：

```typescript
// 文件：src/tools/AgentTool/forkSubagent.ts
export function isInForkChild(messages) {
  return messages.some(m =>
    m.type === 'user' &&
    m.message.content.some(block =>
      block.type === 'text' &&
      block.text.includes(`<${FORK_BOILERPLATE_TAG}>`)
    )
  )
}
```

---

## 验证

让我们通过几个场景验证你的理解。

**测试 1：Agent 定义分析。** 分析以下 Agent 定义的语义：

```typescript
{
  agentType: "test-runner",
  whenToUse: "Run tests after writing code",
  tools: ["Bash", "Read"],
  maxTurns: 10,
  permissionMode: "acceptEdits"
}
```

这个 Agent：
- 叫 `test-runner`，用于在写完代码后运行测试
- 只能使用 `Bash` 和 `Read` 两个工具（不能写文件）
- 最多运行 10 轮对话
- 权限模式是 `acceptEdits`（自动接受编辑，但仍需确认危险操作）

**测试 2：spawn vs fork。** 以下场景应该用哪种模式？

- "搜索整个代码库中所有与支付相关的文件" → spawn with Explore（搜索任务，不需要父 Agent 的上下文）
- "基于我们刚才讨论的架构方案，实现 API 端点" → fork（需要父 Agent 的对话历史中的架构决策）
- "同时在三个代码库中查找 bug" → 三个并行的 spawn（独立任务，可以并行执行）

**测试 3：权限隔离。** 如果父 Agent 在 `bypassPermissions` 模式下，子 Agent 定义了 `permissionMode: "plan"`，子 Agent 实际的权限模式是什么？

答案是 `bypassPermissions`——因为源码中明确写了：`bypassPermissions` 和 `acceptEdits` 永远优先于子 Agent 的设置。

如果这三个测试你都理解了，说明你已经掌握了多 Agent 协作的核心机制。

---

## 回顾

这一章，我们深入了 Claude Code 的多 Agent 协作架构：

1. **AgentDefinition**——Agent 的蓝图，定义了它的能力、工具、权限和生命周期
2. **runAgent**——Agent 的启动器，负责创建上下文、分配工具、建立连接和清理资源
3. **三种模式**——spawn（类型化，从零开始）、fork（继承式，共享缓存）、teammate（持久协作者）
4. **工具分配**——通过 `tools` 和 `disallowedTools` 控制每个 Agent 的能力边界
5. **权限继承**——子 Agent 的权限受父 Agent 约束，bypass 模式不可被子覆盖
6. **生命周期管理**——finally 块保证资源总是被正确清理

多 Agent 协作的本质是**分而治之**——把复杂任务拆成独立的子任务，分配给专门的 Agent，然后收集结果。关键在于设计好每个 Agent 的能力边界，让它只做它擅长的事。

下一章，我们把这些知识整合起来，开发一个完整的插件。

---

[上一章：接入MCP Server](./第06章-接入MCP-Server.md) | [下一章：开发完整插件](./第08章-开发完整插件.md)
