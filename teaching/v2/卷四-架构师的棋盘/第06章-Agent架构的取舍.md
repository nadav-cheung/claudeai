---
title: "第06章：Agent架构的取舍"
description: "Agent 隔离还是共享？何时 fork、何时共享上下文？上下文继承、prompt cache 共享、权限模型的架构权衡。"
tags: [architecture, agent, fork, subagent, context-sharing, prompt-cache, trade-offs, volume-4]
date: 2026-05-10
prev: ./第05章-有限窗口的智慧.md
next: ./第07章-开放协议的价值.md
---

# 第06章：Agent架构的取舍

你在卷二第十章追踪过 Agent 的完整生命周期——从用户输入到 agent 启动，从工具执行到结果回传。你知道了每个步骤怎么运转。但有一个问题一直悬在空中：**为什么 agent 要这样隔离？**

`runAgent` 启动一个子 agent 时，它做了一件关键的事：创建一个全新的 `ToolUseContext`。子 agent 有自己的 `agentId`、自己的 `readFileState`、自己的 `abortController`、自己的消息流。父子之间通过一个精心设计的接口通信，而不是共享内存。

这不是唯一的做法。你也可以让子 agent 直接访问父 agent 的所有状态——共享消息队列、共享文件缓存、共享权限上下文。那样更简单，也更危险。

这一章讨论这个选择。

---

## 现状：隔离与共享的精密平衡

Claude Code 的 agent 架构不是一个简单的"隔离"或"共享"的二选一。它是一个光谱，不同的 agent 类型位于光谱的不同位置。

### 同步 Agent：深度共享

同步 agent（`isAsync: false`）与父级共享最多：

- **`setAppState`**：直接共享，子 agent 的状态变更立即反映到父级
- **`setResponseLength`**：共享，子 agent 的输出长度计入父级的显示
- **`abortController`**：共享同一个，用户按 Esc 同时取消父子

代价是同步 agent 阻塞父级。父 agent 必须等子 agent 完成后才能继续。这是一种线程模型里的"join"语义。

### 异步 Agent：近乎完全隔离

异步 agent（`isAsync: true`）获得自己的世界：

- **`abortController`**：独立的 `new AbortController()`，不与父级联动
- **`setAppState`**：不共享。异步 agent 通过 `rootSetAppState`（`setAppStateForTasks`）向根 AppState 写入特定字段
- **`readFileState`**：从父级克隆（`cloneFileStateCache`），但之后独立演化
- **权限**：`shouldAvoidPermissionPrompts` 设为 true，自动拒绝所有需要用户确认的操作

异步 agent 是真正的后台任务。它有自己的 transcript 文件、自己的 metadata、自己的生命周期。父级通过 `task_status` attachment 了解异步 agent 的进展。

### Fork Subagent：精密的上下文共享

`forkSubagent` 是最有趣的设计。它不是传统的"启动一个新 agent"，而是从父级的当前对话分叉出一个工作进程。关键在于 `buildForkedMessages` 函数：

```typescript
export function buildForkedMessages(
  directive: string,
  assistantMessage: AssistantMessage,
): MessageType[] {
```

它保留父级 assistant 消息的所有 `tool_use` 块，然后用一个统一的占位符替换所有 `tool_result`：

```typescript
const FORK_PLACEHOLDER_RESULT = 'Fork started — processing in background'
```

为什么要用占位符？因为 prompt cache 的要求。为了让所有 fork 子进程共享缓存前缀，它们必须产生字节完全相同的 API 请求前缀。占位符确保了这一点——只有最后的 directive 文本不同，前面的一切都一样。这最大化了缓存命中率。

Fork 子进程继承父级的完整工具集（`tools: ['*']`）、父级的模型（`model: 'inherit'`）、父级的系统提示（通过 `override.systemPrompt` 传入已经渲染好的字节），而不是重新渲染。

### 上下文继承：selective pass-through

`runAgent` 不把父级的所有信息都传给子 agent。它做了一系列选择性的裁剪：

**省略 CLAUDE.md**：对于 Explore 和 Plan 这种只读 agent，`omitClaudeMd` 会跳过 CLAUDE.md 的注入。注释里说这节省了每周 5-15 Gtok 的 token 消耗。这些 agent 不需要知道 commit 规则或 PR 模板——它们只是搜索和规划。

**省略 gitStatus**：同样地，Explore 和 Plan agent 不需要父会话开始时的 git 状态快照（可能高达 40KB）。如果它们需要 git 信息，自己跑 `git status` 拿到的是最新数据。

**权限隔离**：`allowedTools` 参数允许父级精确控制子 agent 的工具权限。这不是共享，而是白名单：

```typescript
if (allowedTools !== undefined) {
  toolPermissionContext = {
    ...toolPermissionContext,
    alwaysAllowRules: {
      cliArg: state.toolPermissionContext.alwaysAllowRules.cliArg,
      session: [...allowedTools],
    },
  }
}
```

注意 `cliArg` 保留——SDK 级别的权限（来自 `--allowedTools`）不应被子 agent 继承过滤。

---

## 当时还有什么选择

在设计 agent 架构时，有几条截然不同的路。

### 选择一：完全共享——线程模型

所有 agent 共享同一个状态空间。像多线程编程一样，通过锁或消息队列协调。

优点是实现简单——子 agent 直接读写父级的数据，不需要序列化或传递。缺点是灾难性的：一个子 agent 的 bug 可以污染父级的整个状态，权限隔离不可能实现，调试是一场噩梦。

### 选择二：完全隔离——进程模型

每个 agent 是一个完全独立的进程，有自己的上下文、工具、权限。父子之间通过 IPC（进程间通信）传递消息。

优点是隔离彻底，安全性最高。缺点是代价太大：每个 agent 都需要完整的上下文初始化，工具定义要重复发送，prompt cache 完全无法共享。在编程助手的场景里，这会严重影响性能和成本。

### 选择三：选择性共享——Actor 模型

每个 agent 是一个独立的 actor，有自己的状态和消息队列。父子之间通过消息传递通信，但可以选择性地共享某些资源（如文件缓存、权限上下文）。

这就是 Claude Code 实际上走的路。

---

## 为什么选了这个

### 理由一：Prompt Cache 的经济学

这是最重要的理由。在 Claude Code 的运营成本里，API 调用占大头。Prompt cache 可以把重复前缀的输入 token 成本降低 90%。但缓存有效的前提是请求前缀完全一致。

`forkSubagent.ts` 里的设计精确地服务于这个目标。Fork 子进程继承父级的系统提示字节（不是重新渲染）、继承工具定义、继承对话历史。唯一不同的是最后的 directive 文本。这意味着 fork 的第一次 API 调用几乎全是 cache read，极少 cache creation。

注释里有一段话精确地解释了这个设计：

```
For prompt cache sharing, all fork children must produce byte-identical
API request prefixes.
```

如果选择完全隔离，每个 agent 的每次调用都是 cache miss。以注释里提到的数据：这会增加约 380 亿 token/天的缓存创建成本。这不是理论推演，是实验测量的结果。

### 理由二：安全的纵深防御

异步 agent 运行在后台，不能弹出权限对话框。如果它继承了父级的完整权限，它可以在用户不知情的情况下执行任意命令。

`shouldAvoidPermissionPrompts` 标志确保了异步 agent 的所有需要确认的操作被自动拒绝，而不是被自动批准。这是一个安全设计，不是功能限制。

### 理由三：资源生命周期管理

`runAgent` 的 `finally` 块是一个精心设计的清理序列：

```typescript
} finally {
  await mcpCleanup()                    // 清理 MCP 服务器连接
  clearSessionHooks(rootSetAppState, agentId)  // 清理 hook 注册
  cleanupAgentTracking(agentId)          // 清理缓存追踪
  agentToolUseContext.readFileState.clear()    // 释放文件缓存
  initialMessages.length = 0             // 释放消息引用
  unregisterPerfettoAgent(agentId)       // 释放追踪注册
  clearAgentTranscriptSubdir(agentId)    // 释放 transcript 映射
  // 清理 todos、shell 任务...
}
```

如果 agent 共享父级的所有状态，这个清理就不可能做——你不知道哪些状态是 agent 独占的，哪些是与父级共享的。隔离让清理变得可能。

---

## 如果重新设计

### 继承粒度可以更细

当前的继承模型是几个预定义的档次：同步、异步、fork。每个档次有固定的共享/隔离配置。一个更灵活的设计是允许每个 agent 定义自己需要继承什么。

比如，一个 "Explore" agent 可能只需要继承文件系统的访问权限和 git 仓库信息，不需要继承工具权限或 MCP 连接。当前的设计是全有或全无——要么继承所有 MCP 客户端（`mergedMcpClients`），要么不继承。

### Agent 间的协调机制缺失

当前的设计里，多个异步 agent 之间几乎没有协调。它们各自独立运行，不知道其他 agent 在做什么。如果两个 agent 同时修改同一个文件，冲突在它们各自完成时才会被发现。

`forkSubagent` 的 `buildChildMessage` 里有一条规则说"Stay strictly within your directive's scope"，但这只是提示词层面的约束，不是架构层面的保证。

如果重新设计，可以引入一个轻量的协调层——比如一个共享的"文件锁"机制，或者一个 agent 间的消息总线。这会增加复杂性，但可以避免并行 agent 之间的资源冲突。

### 记忆的持久化

`agentMemory.ts` 引入了一个有趣的特性：agent 可以有持久的记忆。三种作用域——`user`（全局）、`project`（项目级）、`local`（本地，不入版本控制）：

```typescript
export type AgentMemoryScope = 'user' | 'project' | 'local'
```

这是一个好的方向，但当前只有部分 agent 使用了它。如果重新设计，可以让所有 agent 都有可选的持久记忆——每次 agent 完成时，自动保存关键发现；下次启动时自动加载。这会让 agent 在跨会话场景里更加有用。

---

## 你怎么看

Agent 架构的核心问题是：**你愿意为隔离付出多少代价？**

完全共享很简单，但一个 agent 的故障会波及整个系统。完全隔离很安全，但 cache miss 的成本可能让系统无法运营。Claude Code 选择了中间地带——选择性共享，基于 actor 模型，用最少的共享换取最大的 cache 命中率。

这个选择不是学术上的纯粹，而是工程上的务实。注释里那些精确的数字——"5-15 Gtok/week"、"380 亿 token/天"——告诉你这不是理论推演，是每天在跑的真实数据。

如果你在设计一个多 agent 系统，你应该问自己：你的 agent 之间需要共享什么？共享的粒度是什么？共享的代价（缓存失效、权限泄露、状态污染）是否可以接受？这些问题没有标准答案，但 Claude Code 的设计给了你一个参考点：以 prompt cache 为核心约束，围绕它设计共享策略。

最终，架构是约束的产物。理解了约束，就理解了选择。

---

> [上一章：有限窗口的智慧](./第05章-有限窗口的智慧.md) | [下一章：开放协议的价值](./第07章-开放协议的价值.md)
