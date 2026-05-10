---
title: "第10章：Agent的克隆和协作"
description: "Claude Code 如何像细胞分裂一样创建子Agent？Agent forking 怎么让父Agent和子Agent共享上下文？Team/Swarm 系统又如何让多个 Agent 像团队一样协作？本章深入 src/tools/AgentTool/ 目录，拆解 Agent 克隆、子Agent生命周期、团队协调和消息通信的完整实现。"
tags: [agent-forking, subagent, team-swarm, spawn-teammate, mailbox, prompt-cache, isolation, lifecycle]
date: 2026-05-10
---

# 第10章：Agent的克隆和协作

上一章我们看了 Claude Code 怎么跟外部世界打交道——HTTP请求、MCP协议、工具调用。但有一种场景比"跟外部通信"更微妙：**跟自己通信**。

什么意思？想象你正在改一个大型项目的Bug。你要同时搜索代码、跑测试、查文档、改文件。一个人做这些事，得一件一件来。但如果能"分身"——让另一个自己去找Bug原因，另一个自己跑测试，另一个自己查文档——然后把结果汇总回来呢？

Claude Code 的 Agent 系统就是干这个的。它能让一个 Agent "克隆"出子Agent（subagent），把任务分给它们，然后收集结果。更进一步，多个 Agent 还能组成一个"团队"（Team/Swarm），在终端里各自占一个窗格，互相发消息协作。

这一章，我们拆开 Agent 克隆和协作的秘密。

---

## 这是什么

Claude Code 的 Agent 系统有三层能力：

**第一层：Subagent（子Agent）**。这是最基本的"分身术"。当主Agent遇到一个子任务时（比如"帮我搜索所有包含 TODO 的文件"），它可以调用 AgentTool，创建一个子Agent来处理。子Agent运行完毕后，结果返回给主Agent。这个过程就像一个函数调用——发起、执行、返回结果。

**第二层：Fork（分叉）**。这是一种特殊的子Agent。普通子Agent会得到一个新的系统提示词，从零开始理解任务。而 Fork 子Agent 会**继承父Agent的完整对话上下文**——就像你把脑中的所有想法复制一份给"分身"。这意味着 Fork 出的子Agent不需要重新解释背景，直接就能干活。关键是，多个 Fork 子Agent能共享相同的 API 请求前缀，命中 prompt cache（提示缓存），省下大量 token。

**第三层：Team/Swarm（团队协作）**。这是最高级的协作模式。多个 Agent 各自是一个独立的 Claude Code 进程，在终端的不同窗格里运行。它们通过文件系统上的"邮箱"（mailbox）互相发消息，由一个"队长"（team-lead）分配任务、收集结果。每个 Agent 有自己的名字、颜色和权限模式。

用现实类比：Subagent 像你叫同事帮个忙，他干完就走了。Fork 像你克隆了一个自己，分身跟你一样了解情况。Team 像你组建了一个项目组，大家各干各的、随时沟通。

---

## 打开源码

Agent 系统的核心代码集中在 `src/tools/AgentTool/` 目录下。我们先看看这个目录的文件清单：

| 文件 | 职责 |
|------|------|
| `AgentTool.tsx` | Agent 工具的主体，处理调用请求，决定走哪条路径 |
| `runAgent.ts` | 子Agent的执行引擎，启动一个独立的 query 循环 |
| `forkSubagent.ts` | Fork 分叉的逻辑：构建消息、防止递归分叉 |
| `builtInAgents.ts` | 内置Agent类型的注册表（general-purpose、Explore等） |
| `loadAgentsDir.ts` | 从文件系统加载自定义Agent定义 |
| `agentToolUtils.ts` | 共享的工具函数：进度追踪、结果提取 |

团队协作的代码则分布在其他地方：

| 文件 | 职责 |
|------|------|
| `src/tools/shared/spawnMultiAgent.ts` | 创建新的 teammate 进程 |
| `src/utils/teammateMailbox.ts` | 文件系统的邮箱消息系统 |
| `src/utils/teamDiscovery.ts` | 团队发现和成员状态查询 |
| `src/utils/forkedAgent.ts` | Fork Agent 的查询循环和上下文隔离 |

这些文件加起来超过 3000 行代码，但核心思路其实清晰。让我们一层一层拆开。

---

## 它怎么工作

### Subagent：创建一个子Agent

一切从 `AgentTool.call()` 开始。当 AI 决定要委托一个任务时，它调用 Agent 工具，传入 prompt（任务描述）和 subagent_type（Agent类型）。

`AgentTool.tsx`（约第239行）的 `call()` 方法首先决定走哪条路：

```typescript
// 文件：src/tools/AgentTool/AgentTool.tsx，约第319-323行
const effectiveType = subagent_type
  ?? (isForkSubagentEnabled() ? undefined : GENERAL_PURPOSE_AGENT.agentType);
const isForkPath = effectiveType === undefined;
```

这段逻辑很精炼：如果指定了 `subagent_type`，用它。如果没指定但 Fork 功能开启了，走 Fork 路径。如果都没指定，默认用 `general-purpose`。

假设走普通 Subagent 路径。系统找到对应的 Agent 定义后，进入关键的决策点——**同步还是异步**：

```typescript
// 文件：src/tools/AgentTool/AgentTool.tsx，约第567行
const shouldRunAsync =
  (run_in_background === true || selectedAgent.background === true
   || isCoordinator || forceAsync || assistantForceAsync
   || (proactiveModule?.isProactiveActive() ?? false))
  && !isBackgroundTasksDisabled;
```

同步模式：主Agent会"卡住"等子Agent干完，拿到结果才继续。就像你打电话叫外卖，等外卖到了才吃饭。

异步模式：主Agent发出任务后立刻继续自己的事。子Agent在后台运行，干完了发一个通知。就像你点了外卖，继续工作，外卖到了有人通知你。

### RunAgent：子Agent的执行引擎

无论同步还是异步，子Agent的实际执行都由 `runAgent()` 函数驱动。这个函数在 `src/tools/AgentTool/runAgent.ts`（约第248行），它是整个子Agent系统的核心。

`runAgent()` 做了这些事：

**1. 创建隔离的上下文**

```typescript
// 文件：src/tools/AgentTool/runAgent.ts，约第700行
const agentToolUseContext = createSubagentContext(toolUseContext, {
  options: agentOptions,
  agentId,
  agentType: agentDefinition.agentType,
  messages: initialMessages,
  readFileState: agentReadFileState,
  abortController: agentAbortController,
  getAppState: agentGetAppState,
  shareSetAppState: !isAsync,
  shareSetResponseLength: true,
});
```

子Agent不能随意修改父Agent的状态。`createSubagentContext()` 创建了一个隔离的上下文——子Agent有自己的消息队列、文件缓存、中断控制器。默认情况下，子Agent的 `setAppState` 是一个空函数（no-op），防止子Agent意外修改父Agent的 UI 状态。

**2. 组装工具集**

子Agent使用的工具集可能与父Agent不同。普通子Agent会通过 `resolveAgentTools()` 得到适合自己角色的工具。比如 Explore Agent 不需要写文件的工具。

**3. 启动查询循环**

```typescript
// 文件：src/tools/AgentTool/runAgent.ts，约第748行
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
  // 处理每一条消息...
}
```

这就是我们在第二章看到的那个 `query()` 函数！子Agent拥有自己的查询循环，像一个小型 Agent 独立运行。

**4. 清理**

子Agent运行结束后，`runAgent()` 在 `finally` 块里做清理工作：关闭 MCP 连接、清理 hook、释放文件缓存、杀死残留的 shell 任务。就像酒店退房——不管你是正常离开还是被赶出去，房间都要打扫干净。

### Fork：继承父Agent的记忆

Fork 是一种特殊的 Subagent。普通 Subagent 的 system prompt 是根据自己的角色重新生成的，跟父Agent的 system prompt 不同。但 Fork 子Agent直接继承父Agent的 system prompt。

为什么？因为**缓存**。

Anthropic API 的 prompt cache（提示缓存）机制有一个特点：如果多个 API 请求的前缀完全相同（包括 system prompt、tools 定义、历史消息），就可以复用缓存，跳过重复计算，节省大量输入 token。Fork 子Agent继承父Agent的完整上下文，意味着它们的 API 请求前缀跟父Agent几乎一样——只有最后那条指令不同。这大幅提高了缓存命中率。

`forkSubagent.ts`（约第107行）的 `buildForkedMessages()` 函数实现了这个巧妙的缓存策略：

```typescript
// 文件：src/tools/AgentTool/forkSubagent.ts，约第107-169行
export function buildForkedMessages(
  directive: string,
  assistantMessage: AssistantMessage,
): MessageType[] {
  // 1. 保留父Agent的完整 assistant 消息（所有 tool_use blocks）
  const fullAssistantMessage = { ...assistantMessage, ... };

  // 2. 给每个 tool_use block 构建相同的占位符 tool_result
  const toolResultBlocks = toolUseBlocks.map(block => ({
    type: 'tool_result',
    tool_use_id: block.id,
    content: [{ type: 'text', text: FORK_PLACEHOLDER_RESULT }],
  }));

  // 3. 把占位符结果 + 每个子Agent的专属指令合成一条 user 消息
  const toolResultMessage = createUserMessage({
    content: [...toolResultBlocks, { type: 'text', text: buildChildMessage(directive) }],
  });

  return [fullAssistantMessage, toolResultMessage];
}
```

关键在于：所有 Fork 子Agent共享**完全相同的** assistant 消息和 tool_result 占位符——只有最后那条指令文本（directive）不同。这样 API 请求的前缀完全一致，缓存命中率极高。

Fork 子Agent收到的指令也很特别。`buildChildMessage()` 函数（约第171行）生成一段严格的规则：

```text
STOP. READ THIS FIRST.
You are a forked worker process. You are NOT the main agent.
RULES (non-negotiable):
1. Do NOT spawn sub-agents; execute directly.
2. Do NOT converse, ask questions, or suggest next steps
3. USE your tools directly: Bash, Read, Write, etc.
...
```

这段指令告诉 Fork 子Agent：你是工人，不是管理者。不要创建子Agent，不要问问题，直接用工具干活。这防止了递归分叉——如果子Agent又去 Fork，就会无穷无尽。

系统还有第二道防线：`isInForkChild()` 函数（约第78行）通过检查消息历史中是否存在 fork 标记来检测递归。

### Team/Swarm：组建Agent团队

Fork 和 Subagent 是"父子关系"——父Agent创建子Agent，子Agent完成后结果返回给父。但 Team 模式是"同事关系"——多个 Agent 平等地协作。

创建 Teammate 的入口也在 `AgentTool.call()` 里。当调用参数同时包含 `team_name`（团队名）和 `name`（Agent名）时，系统走 `spawnTeammate()` 路径：

```typescript
// 文件：src/tools/AgentTool/AgentTool.tsx，约第284-316行
if (teamName && name) {
  const result = await spawnTeammate({
    name,
    prompt,
    description,
    team_name: teamName,
    use_splitpane: true,
    plan_mode_required: spawnMode === 'plan',
    model: model ?? agentDef?.model,
    agent_type: subagent_type,
  }, toolUseContext);
  // ...
}
```

`spawnTeammate()` 定义在 `src/tools/shared/spawnMultiAgent.ts`（约第1088行）。它支持两种后端：

**进程内模式（in-process）**：Teammate 在同一个 Node.js 进程内运行，通过 AsyncLocalStorage 维护独立的上下文。这是默认模式，不需要额外软件。

**Tmux/iTerm2 模式**：每个 Teammate 是一个独立的 Claude Code 进程，运行在终端模拟器的独立窗格里。需要安装 tmux 或使用 iTerm2。这种模式下的 Teammate 有真正的隔离——独立的进程、独立的工作目录。

进程内模式的 spawn 流程（约第840行）做了这些事：

1. 生成唯一的 Agent ID 和颜色
2. 调用 `spawnInProcessTeammate()` 创建运行环境
3. 调用 `startInProcessTeammate()` 启动独立的查询循环
4. 在 AppState 中注册 teammate 信息
5. 写入团队文件（`.claude/teams/{team_name}/`）

### 邮箱：Agent之间的消息系统

多个 Agent 要协作，必须能互相通信。Claude Code 用了一个简单而可靠的方案：**基于文件的邮箱系统**。

`src/utils/teammateMailbox.ts` 实现了这个系统。每个 Agent 有一个收件箱文件，路径格式是：

```
~/.claude/teams/{team_name}/inboxes/{agent_name}.json
```

发消息就是往对方的收件箱文件追加一条 JSON 记录。收消息就是读自己的收件箱文件。

```typescript
// 文件：src/utils/teammateMailbox.ts，约第134行
export async function writeToMailbox(
  recipientName: string,
  message: Omit<TeammateMessage, 'read'>,
  teamName?: string,
): Promise<void> {
  // 文件锁防止并发写入冲突
  let release = await lockfile.lock(inboxPath, { ... });
  const messages = await readMailbox(recipientName, teamName);
  messages.push({ ...message, read: false });
  await writeFile(inboxPath, jsonStringify(messages, null, 2), 'utf-8');
  await release();
}
```

注意那个文件锁（lockfile）——多个 Agent 可能同时往同一个收件箱写消息。没有锁就会互相覆盖。这跟多线程编程里的锁是一个道理，只不过这里的"线程"是独立的进程。

邮箱系统不仅支持普通文本消息，还支持多种结构化协议消息：

- **任务分配**（`task_assignment`）：队长给队员分配任务
- **权限请求**（`permission_request`）：队员向队长请求工具权限
- **计划审批**（`plan_approval_request`）：队员提交执行计划等队长批准
- **关闭请求**（`shutdown_request`）：队长通知队员可以退出了
- **空闲通知**（`idle_notification`）：队员告诉队长自己闲下来了

这些结构化消息不会被当作普通文本展示给 AI，而是被 `useInboxPoller` 分别路由到对应的处理队列。

### 生命周期：从出生到退休

一个子Agent或 Teammate 的完整生命周期是这样的：

**1. Spawn（创建）**：父Agent或队长决定需要一个新Agent。系统分配 ID、选择模型、设置权限、准备上下文。

**2. Assign（分配任务）**：子Agent收到初始 prompt（通过构造函数参数），Teammate 通过邮箱收到第一条任务消息。

**3. Monitor（监控）**：`runAgent()` 的 `for await...of` 循环持续产出消息。每条消息都被记录到 transcript（会话记录）中，用于事后追溯。进度通过 `onProgress` 回调实时报告给父Agent。

**4. Collect（收集结果）**：子Agent运行结束后，最后一条 assistant 消息就是它的"工作报告"。同步模式下直接返回；异步模式下通过 `task_notification` 通知父Agent。

**5. Shutdown（关闭）**：`runAgent()` 的 `finally` 块执行清理。对于 Teammate，队长可以发送 `shutdown_request` 消息，Teammate 可以批准或拒绝。

```typescript
// 文件：src/tools/AgentTool/runAgent.ts，约第816-858行（finally 块）
finally {
  await mcpCleanup();           // 关闭 MCP 连接
  clearSessionHooks(...);       // 清理 hook
  cleanupAgentTracking(...);    // 清理缓存追踪
  agentToolUseContext.readFileState.clear(); // 释放文件缓存
  unregisterPerfettoAgent(agentId);          // 注销追踪
  clearAgentTranscriptSubdir(agentId);       // 清理目录
  killShellTasksForAgent(agentId, ...);      // 杀死残留 shell
}
```

注意那个 `killShellTasksForAgent()`——如果子Agent启动了后台 shell 任务（比如一个一直在运行的测试监听器），子Agent自己退出了但 shell 任务还在。这个函数确保不会留下"僵尸进程"。

### 隔离：Worktree模式

Agent 还有一种特别的隔离方式：**Git Worktree**。当你设置 `isolation: "worktree"` 时，子Agent会在一个独立的 git worktree 中工作——同一个仓库，但一份独立的工作副本。

```typescript
// 文件：src/tools/AgentTool/AgentTool.tsx，约第590行
if (effectiveIsolation === 'worktree') {
  const slug = `agent-${earlyAgentId.slice(0, 8)}`;
  worktreeInfo = await createAgentWorktree(slug);
}
```

这样子Agent可以随意修改文件，不会影响主Agent的工作区。等子Agent完成后，系统检查 worktree 是否有实际改动。有改动就保留（等主Agent决定是否合并），没改动就自动清理。

---

## 对比Java

如果你学过 Java，Agent 系统的很多概念会让你觉得眼熟。

**Subagent vs Thread/Runnable**。Java 里你可以 `new Thread(() -> doWork()).start()` 来启动一个子线程。Claude Code 的 Subagent 本质上也是这个模式——创建一个独立执行单元，给它任务，等它完成。区别在于 Subagent 的"线程"不是 OS 线程，而是一个独立的 LLM 查询循环。

**Fork vs ForkJoinPool**。Java 的 `ForkJoinPool` 允许你把一个大任务拆成多个子任务并行执行，子任务共享父任务的上下文（比如同一个数组的不同区间）。Claude Code 的 Fork 也是这个思路——子Agent继承父Agent的对话上下文，就像 ForkJoinTask 的子任务共享父任务的工作内存。而且 Fork 的缓存优化策略跟 Java 的 work-stealing 有异曲同工之妙：都是为了减少重复计算。

**Team/Swarm vs ExecutorService + MessageQueue**。Java 里你可以用 `ExecutorService` 管理一组工作线程，用 `BlockingQueue` 或 `ConcurrentHashMap` 在线程间传递消息。Claude Code 的 Team 就是这个架构：每个 Teammate 是一个"工作线程"，邮箱系统就是消息队列。队长是主线程，负责调度。

**隔离 vs Docker 容器**。Worktree 隔离的概念跟 Docker 容器类似——给每个工作单元一个独立的环境。只不过 Docker 隔离的是整个文件系统，而 Worktree 只隔离 git 仓库的工作目录。这更像是 Java 的 `ClassLoader` 隔离——同一个 JVM 里不同的类加载器可以加载同一个类的不同版本，互不干扰。

一个关键区别：Java 的线程是轻量级的（相比进程），而 Claude Code 的每个 Teammate 可能是一个完整的进程（tmux 模式）。进程内模式更接近 Java 线程——共享同一个 Node.js 进程，通过 AsyncLocalStorage 实现上下文隔离，这跟 Java 的 `ThreadLocal` 非常相似。

```java
// Java 的 ThreadLocal
private static final ThreadLocal<UserContext> context = new ThreadLocal<>();

// Claude Code 的 AsyncLocalStorage（本质相同）
const agentContext = new AsyncLocalStorage<AgentContext>();
```

---

## 你能改什么

Agent 系统有很多可定制的点。以下是你可以从源码出发做的改动：

### 1. 创建自定义 Agent 类型

在 `.claude/agents/` 目录下放一个 Markdown 文件，就能注册新的 Agent 类型：

```markdown
---
description: "专门处理测试的 Agent"
tools: ["Bash", "Read", "Write"]
model: sonnet
max_turns: 50
---

你是一个测试专家。你的任务是运行测试、分析失败原因、修复测试。
```

系统启动时 `loadAgentsDir.ts` 会扫描这个目录，解析 frontmatter 里的配置，注册为新的 Agent 类型。

### 2. 调整 Fork 子Agent的行为规则

`forkSubagent.ts` 里的 `buildChildMessage()` 函数定义了 Fork 子Agent的行为规则。你可以修改这些规则来改变子Agent的工作风格——比如让它更详细地报告进展，或者允许它创建自己的子Agent（如果你确实需要递归分叉）。

### 3. 自定义消息类型

邮箱系统支持多种结构化消息。你可以在 `teammateMailbox.ts` 里添加新的消息类型，实现自定义的团队协作协议。比如添加一种 `code_review_request` 消息类型，让 Agent 之间互相审查代码。

### 4. 调整 Agent 的权限模式

每个 Agent 定义可以指定自己的 `permissionMode`。比如你可以创建一个只读 Agent（使用 `plan` 模式），或者一个完全自主的 Agent（使用 `bypassPermissions` 模式）。权限系统的实现在 `runAgent.ts` 的 `agentGetAppState` 函数里（约第416行），它会在子Agent的上下文中覆盖父Agent的权限设置。

### 5. 实现自定义的 Agent 调度策略

默认情况下，任务分配是手动的——主Agent或队长决定把任务给谁。但你可以基于 `teamDiscovery.ts` 的 `getTeammateStatuses()` 函数实现自动调度：检查哪个 Teammate 是空闲的（`status === 'idle'`），自动把新任务分配给它。这就是一个简单的负载均衡器。

---

Agent 系统是 Claude Code 架构里最精巧的部分之一。它同时支持三种协作模式（Subagent、Fork、Team），每种都有不同的隔离级别和通信机制。核心思想其实很简单——把复杂任务分解成独立的小任务，让多个执行单元并行处理。但实现细节处处体现了工程智慧：缓存共享、递归防护、文件锁、僵尸清理……每一个都是为了解决真实的并发问题。

下一章，我们来看另一个跨越时间的问题：Agent 怎么记住之前会话里发生过的事？这就是记忆系统——跨越会话的持久化存储。

---

[上一章：外部世界的入口](./第09章-外部世界的入口.md) | [下一章：跨越会话的记忆](./第11章-跨越会话的记忆.md)
