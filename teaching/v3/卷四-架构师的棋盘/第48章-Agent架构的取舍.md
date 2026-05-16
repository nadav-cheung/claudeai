# 第 48 章：Agent 架构的取舍

> 源码验证日期：2026-05-15，基于 commit `0d81bb6`

你在第 47 章看到 `queryLoop` 如何用一个大 AsyncGenerator 驱动整个 agentic loop。但 Claude Code 不只有一个 loop。当主 agent 需要委托工作时，它会启动子 agent——探索代码、规划方案、在后台执行长时间任务。子 agent 有自己的 `agentId`、自己的 `readFileState`、自己的 `abortController`、自己的消息流。

这不是唯一的做法。你可以让子 agent 直接访问父 agent 的所有状态——共享消息队列、共享文件缓存、共享权限上下文。那样更简单，也更危险。

这一章讨论 agent 隔离与共享之间的权衡。

---

## 本章路线图

```mermaid
graph LR
    CH41["第41章<br/>为什么是TypeScript"] --> CH42["第42章"]
    CH42["第42章<br/>为什么是React/Ink"] --> CH43["第43章"]
    CH43["第43章<br/>为什么用Zod"] --> CH44["第44章"]
    CH44["第44章<br/>工具系统的演进"] --> CH45["第45章"]
    CH45["第45章<br/>安全与便利"] --> CH46["第46章"]
    CH46["第46章<br/>有限窗口"] --> CH47["第47章"]
    CH47["第47章<br/>大AsyncGenerator"] --> CH48["第48章"]
    CH48["第48章<br/>Agent架构"] --> CH49["第49章"]
    CH49["第49章<br/>开放协议"] --> CH50["第50章"]
    CH50["第50章<br/>性能的故事"] --> CH51["第51章"]
    CH51["第51章<br/>纵深防御"] --> CH52["第52章"]

    style CH41 fill:#e0e0e0,stroke:#999
    style CH42 fill:#e0e0e0,stroke:#999
    style CH43 fill:#e0e0e0,stroke:#999
    style CH44 fill:#e0e0e0,stroke:#999
    style CH45 fill:#e0e0e0,stroke:#999
    style CH46 fill:#e0e0e0,stroke:#999
    style CH47 fill:#e0e0e0,stroke:#999
    style CH48 fill:#4a90d9,stroke:#2c5f8a,color:#fff,stroke-width:3px
    style CH49 fill:#e0e0e0,stroke:#999
    style CH50 fill:#e0e0e0,stroke:#999
    style CH51 fill:#e0e0e0,stroke:#999
    style CH52 fill:#e0e0e0,stroke:#999
```

---

## 现状：隔离与共享的光谱

Claude Code 的 agent 架构不是简单的"隔离"或"共享"二选一。它是一个光谱，不同的 agent 类型位于光谱的不同位置。

### 同步 Agent：深度共享

同步 agent（`isAsync: false`）与父级共享最多：

- **`setAppState`**：直接共享，子 agent 的状态变更立即反映到父级
- **`setResponseLength`**：共享，子 agent 的输出长度计入父级的显示
- **`abortController`**：共享同一个，用户按 Esc 同时取消父子

代价是同步 agent 阻塞父级。父 agent 必须等子 agent 完成后才能继续。这是一种线程模型里的 "join" 语义。

### 异步 Agent：近乎完全隔离

异步 agent（`isAsync: true`）获得自己的世界：

- **`abortController`**：独立的 `new AbortController()`，不与父级联动
- **`setAppState`**：不共享。异步 agent 通过 `rootSetAppState`（`setAppStateForTasks`）向根 AppState 写入特定字段
- **`readFileState`**：从父级克隆（`cloneFileStateCache`），但之后独立演化
- **权限**：`shouldAvoidPermissionPrompts` 设为 true，自动拒绝所有需要用户确认的操作

异步 agent 是真正的后台任务。它有自己的 transcript 文件、自己的 metadata、自己的生命周期。父级通过 `task_status` attachment 了解异步 agent 的进展。

### Fork Subagent：精密的上下文共享

`forkSubagent` 是最有趣的设计。它不是"启动一个新 agent"，而是从父级的当前对话分叉出一个工作进程。关键在于 `buildForkedMessages` 函数：

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

为什么用占位符？因为 prompt cache 的要求。为了让所有 fork 子进程共享缓存前缀，它们必须产生字节完全相同的 API 请求前缀。占位符确保了这一点——只有最后的 directive 文本不同，前面的一切都一样。这最大化了缓存命中率。

Fork 子进程继承父级的完整工具集（`tools: ['*']`）、父级的模型（`model: 'inherit'`）、父级的系统提示（通过 `override.systemPrompt` 传入已经渲染好的字节），而不是重新渲染。

### 上下文继承：selective pass-through

`runAgent` 不把父级的所有信息都传给子 agent。它做了一系列选择性的裁剪。

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

### 资源清理的精密编排

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

## 当时还有什么选择

### 选择一：完全共享——线程模型

所有 agent 共享同一个状态空间。像多线程编程一样，通过锁或消息队列协调。

优点是实现简单——子 agent 直接读写父级的数据，不需要序列化或传递。缺点是灾难性的：一个子 agent 的 bug 可以污染父级的整个状态，权限隔离不可能实现，调试是一场噩梦。

更具体的例子：如果异步 agent 共享父级的 `readFileState`，一个后台 agent 读取文件后更新缓存，这个缓存可能覆盖父级 agent 正在使用的缓存数据。在编程助手场景里，文件可能在这段时间被修改了——父级 agent 拿到的是后台 agent 缓存的旧版本，而不是磁盘上的最新版本。

### 选择二：完全隔离——进程模型

每个 agent 是一个完全独立的进程，有自己的上下文、工具、权限。父子之间通过 IPC（进程间通信）传递消息。

优点是隔离彻底，安全性最高。缺点是代价太大：每个 agent 都需要完整的上下文初始化，工具定义要重复发送，prompt cache 完全无法共享。在编程助手的场景里，这会严重影响性能和成本。

完全隔离的另一个问题是工具权限。如果子 agent 完全独立，它需要自己的权限配置——用户需要为每个 agent 单独授权。这在体验上不可接受。

### 选择三：选择性共享——Actor 模型

每个 agent 是一个独立的 actor，有自己的状态和消息队列。父子之间通过消息传递通信，但可以选择性地共享某些资源（如文件缓存、权限上下文）。

这就是 Claude Code 实际上走的路。

---

## 为什么选了选择性共享

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

`shouldAvoidPermissionPrompts` 标志确保了异步 agent 的所有需要确认的操作被自动拒绝，而不是被自动批准。这是一个安全设计，不是功能限制——拒绝比批准更安全，因为错误的拒绝可以重试，错误的批准不可撤销。

### 理由三：上下文裁剪的 token 经济学

省略 CLAUDE.md 节省 5-15 Gtok/week，省略 gitStatus 节省 1-3 Gtok/week。对于只读的 Explore 和 Plan agent 来说，这些信息完全是浪费——它们不需要 commit 规则，不需要 PR 模板，不需要知道当前分支的状态。

这个裁剪决定背后的假设是：不同类型的 agent 需要不同的上下文。一个"搜索文件"的 agent 不需要"如何写 commit message"的指令。裁剪不是偷工减料，而是精准投喂。

### 理由四：资源生命周期管理

独立的 `abortController` 意味着用户可以取消主任务而不影响后台任务，也可以取消后台任务而不影响主任务。独立的 `readFileState` 意味着后台 agent 的文件读取不会干扰主 agent 的缓存。

这些独立性看似小细节，但在实际使用中至关重要。想象一下：你启动了一个后台 agent 来搜索代码库，同时继续在主对话中工作。如果后台 agent 的文件读取缓存污染了主 agent 的缓存，你拿到的可能是过时的文件内容。

---

## 如果重新设计

### 继承粒度可以更细

当前的继承模型是几个预定义的档次：同步、异步、fork。每个档次有固定的共享/隔离配置。一个更灵活的设计是允许每个 agent 定义自己需要继承什么。

比如，一个 "Explore" agent 可能只需要继承文件系统的访问权限和 git 仓库信息，不需要继承工具权限或 MCP 连接。当前的设计是全有或全无——要么继承所有 MCP 客户端（`mergedMcpClients`），要么不继承。

### Agent 间的协调机制缺失

当前的设计里，多个异步 agent 之间几乎没有协调。它们各自独立运行，不知道其他 agent 在做什么。如果两个 agent 同时修改同一个文件，冲突在它们各自完成时才会被发现。

`forkSubagent` 的 `buildChildMessage` 里有一条规则说 "Stay strictly within your directive's scope"，但这只是提示词层面的约束，不是架构层面的保证。

如果重新设计，可以引入一个轻量的协调层——比如一个共享的"文件锁"机制，或者一个 agent 间的消息总线。这会增加复杂性，但可以避免并行 agent 之间的资源冲突。

### 记忆的持久化

`agentMemory.ts` 引入了 agent 持久记忆的能力。三种作用域——`user`（全局）、`project`（项目级）、`local`（本地，不入版本控制）：

```typescript
export type AgentMemoryScope = 'user' | 'project' | 'local'
```

这是一个好的方向，但当前只有部分 agent 使用了它。如果重新设计，可以让所有 agent 都有可选的持久记忆——每次 agent 完成时自动保存关键发现，下次启动时自动加载。这会让 agent 在跨会话场景里更加有用。

---

## 试试看

### 练习一：追踪 fork 的缓存共享

在 `forkSubagent.ts` 中找到 `buildForkedMessages` 函数，追踪它如何构建 fork 子进程的消息列表。验证占位符替换的确保证了字节一致性。

### 练习二：观察权限隔离

在 `runAgent` 中找到 `allowedTools` 的处理逻辑。启动一个只允许 `Read` 和 `Grep` 工具的子 agent，观察它尝试调用 `Write` 时会发生什么。

### 练习三：追踪资源清理

在 `runAgent` 的 `finally` 块中加日志，观察 agent 结束时清理了哪些资源。特别注意 MCP 连接和文件缓存的清理。

---

## 检查点

- **Agent 架构是光谱**：同步（深度共享）到异步（近乎完全隔离），不是二选一
- **Fork Subagent 是最精密的设计**：占位符保证缓存共享，选择性继承保证安全性
- **被否决的方案**：完全共享（状态污染）、完全隔离（缓存无法共享）
- **核心约束是 Prompt Cache 经济学**：380 亿 token/天的缓存创建成本决定了共享策略
- **上下文裁剪节省 token**：省略 CLAUDE.md 和 gitStatus 每周节省 6-18 Gtok
- **权限隔离是安全设计**：异步 agent 自动拒绝需要确认的操作，而不是自动批准

---

> **导航**
>
> 上一章：[第 47 章：为什么 query.ts 是大 AsyncGenerator](./第47章-为什么query.ts是大AsyncGenerator.md)
>
> 下一章：[第 49 章：开放协议的价值](./第49章-开放协议的价值.md)
