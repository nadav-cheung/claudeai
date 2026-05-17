# 附录 J：分布式 Agent — 当你的框架从笔记本搬到 K8s

> 全书假设 Agent 运行在单个进程内。但当你的框架要服务多个用户、
> 部署在 Kubernetes 上时，单进程模型的每一个假设都需要重新审视。

---

## J.1 单进程 Agent 的五个隐含假设

当前卷五构建的 `AgentFramework` 依赖以下假设：

| 假设 | 单进程下 | 分布式下 |
|------|---------|---------|
| **状态在内存** | `AgentLoop` 的 `messages[]` 在堆内存中 | Pod 重启后消失 |
| **单用户** | 一个进程服务一个会话 | 多用户共享资源 |
| **调用是同步的** | `await client.createMessage()` | 可能被网络分区打断 |
| **工具是本地的** | `Bash("npm test")` 在当前机器执行 | 需要在目标 Pod 中执行 |
| **子 Agent 是本地的** | fork 在同一进程 | 子 Agent 可能在另一个节点 |

当你把 Agent 框架部署到 K8s 时，这五个假设全部崩塌。本节逐一解决。

---

## J.2 有状态 vs 无状态 Agent

### 无状态 Agent（适合简单任务）

```
用户请求 → 负载均衡 → Agent Pod (无状态)
                          ↓
                      每次请求是独立的
                      无对话历史
                      → 适合：单轮问答、代码片段生成
```

无状态 Agent 最简单的实现——每个请求是一个独立的 `POST /agent/run`，Agent 处理完返回结果，不保留任何状态。水平扩展容易（加 Pod 即可），但不能做多轮对话。

### 有状态 Agent（适合多轮对话）

```
用户会话 → Sticky Session → 固定 Agent Pod
                              ↓
                         对话历史在 Pod 内存中
                         如果 Pod 挂了 → 对话丢失
                              ↓
                         改进：Redis 做状态外存
```

```typescript
// → 有状态 Agent 的会话管理
import { Redis } from "ioredis"

class DistributedAgentManager {
  constructor(
    private redis: Redis,
    private framework: AgentFramework,
  ) {}

  async getOrCreateAgent(sessionId: string): Promise<AgentLoop> {
    // 1. 尝试从 Redis 恢复
    const serialized = await this.redis.get(`session:${sessionId}`)
    if (serialized) {
      return AgentLoop.deserialize(JSON.parse(serialized), this.framework)
    }

    // 2. 创建新 Agent
    const agent = this.framework.createAgent()

    // 3. 每次状态变化后异步保存
    agent.onStateChange(async (state) => {
      await this.redis.setex(
        `session:${sessionId}`,
        3600,  // 1 小时 TTL
        JSON.stringify(state.serialize()),
      )
    })

    return agent
  }

  async deleteSession(sessionId: string): Promise<void> {
    await this.redis.del(`session:${sessionId}`)
  }
}
```

### 选择无状态还是有状态

```
无状态 ← ── 光谱 ── → 有状态
   │                     │
适合：API 封装         适合：对话式 Agent
成本低，运维简单       成本高，需 Redis
不能多轮对话           支持多轮对话
```

---

## J.3 子 Agent 的跨进程调度

ch26（Agent 的克隆与协作）聚焦在单进程内的 fork。分布式下，子 Agent 运行在哪个节点上？

### 模型一：消息队列调度

```
主 Agent Pod ──→ Redis Queue ──→ Worker Pod (子 Agent)
    │                                    │
    └────── 结果回调 ←───────────────────┘
```

```typescript
// → 使用 BullMQ 做子 Agent 调度
import { Queue, Worker } from "bullmq"

// 主 Agent 创建子任务
const subAgentQueue = new Queue("subagent-tasks", { connection: redis })

async function spawnSubAgent(task: SubAgentTask): Promise<SubAgentResult> {
  const job = await subAgentQueue.add("execute", task, {
    timeout: 60_000,  // 子 Agent 超时 1 分钟
    attempts: 2,       // 失败重试 2 次
  })

  // 等待结果
  return job.waitUntilFinished(subAgentQueueEvents)
}

// Worker 端消费任务
const worker = new Worker("subagent-tasks", async (job) => {
  const agent = framework.createAgent({ /* 子 Agent 配置 */ })
  return agent.runSync(job.data.prompt)  // 同步执行
}, { connection: redis, concurrency: 5 })  // 5 个并发子 Agent
```

### 模型二：直接 HTTP 调用

如果子 Agent 作为独立 HTTP 服务部署：

```
主 Agent ──→ POST /subagent/run ──→ 子 Agent 服务
                │
                └── 超时怎么办？
```

两种模型的选择：

| 维度 | 消息队列 | HTTP 直接调用 |
|------|---------|-------------|
| 可靠性 | 高（持久化+重试） | 中（网络失败即丢失） |
| 延迟 | 较高（队列开销） | 较低 |
| 运维 | 需要 Redis/RabbitMQ | 只需 HTTP |
| 适用 | 长时间子任务 | 短查询 |

---

## J.4 幂等性：分布式 Agent 的核心挑战

工具调用不是幂等的。`Edit("auth.ts", old, new)` 执行两次会破坏文件。`Bash("npm publish")` 执行两次是灾难。

### 策略：幂等键 + 结果缓存

```typescript
// → 幂等工具执行包装
class IdempotentToolExecutor {
  private results = new Map<string, ToolResult>()  // 生产环境用 Redis

  async execute(
    toolName: string,
    input: Record<string, unknown>,
    idempotencyKey: string,  // 由调用方生成
  ): Promise<ToolResult> {
    // 1. 检查是否已执行
    const cached = this.results.get(idempotencyKey)
    if (cached) {
      console.log(`[idempotent] ${toolName} 已执行过，返回缓存结果`)
      return cached
    }

    // 2. 执行工具
    const result = await this.executeTool(toolName, input)

    // 3. 缓存结果（24h TTL）
    this.results.set(idempotencyKey, result)

    return result
  }
}

// 幂等键的生成
function generateIdempotencyKey(
  sessionId: string,
  turn: number,
  toolName: string,
): string {
  return `${sessionId}:turn-${turn}:${toolName}`
}
```

### 哪些工具可以安全重试

| 工具 | 幂等性 | 分布式对策 |
|------|--------|-----------|
| Read / Grep / Glob | ✓ 天然幂等 | 无特殊处理 |
| Edit / Write | ✗ 不幂等 | 幂等键 + 内容 hash 对比 |
| Bash | ✗ 取决于命令 | 区分只读命令和写命令 |
| WebSearch / WebFetch | ~ 近似幂等 | 结果可能不同，但无副作用 |

---

## J.5 分布式 Session 持久化

与专家 1（存储工程师）的发现呼应。Session 需要序列化到 Redis/DB：

```typescript
// → Session 序列化格式
interface SerializedSession {
  id: string
  messages: Array<{
    role: "user" | "assistant"
    content: string | ContentBlockParam[]
  }>
  metadata: {
    model: string
    turnCount: number
    totalTokens: { input: number; output: number }
    sessionCost: number
    startedAt: string
    lastActivityAt: string
  }
}

// 代理层：透明持久化
class PersistentAgentLoop {
  constructor(
    private inner: AgentLoop,
    private store: SessionStore,
    private sessionId: string,
  ) {}

  async *run(input: string): AsyncGenerator<AgentEvent> {
    for await (const event of this.inner.run(input)) {
      yield event
      // 每个事件后增量保存
      if (event.type === "tool_result" || event.type === "response") {
        await this.store.save(this.sessionId, this.inner.serialize())
      }
    }
  }
}
```

---

## J.6 分布式下的可观测性

ch38（调试的艺术→结构化可观测性）建立的单 Agent 指标在分布式下需要聚合：

```
Pod-1: turn.count avg=4.2, error.rate=3%
Pod-2: turn.count avg=3.8, error.rate=5%
Pod-3: turn.count avg=12.1, error.rate=15%  ← 这个 Pod 有问题！

聚合层（Prometheus + Grafana）
  → avg.turn.count: (4.2+3.8+12.1)/3 = 6.7
  → 但掩盖了 Pod-3 的异常！
```

**关键**：分布式可观测性需要同时看**全局聚合**和**逐实例**指标。单看聚合会被异常 Pod 的平均值掩盖。

---

## 试一试

1. **用 Redis 实现 SessionStore**。在 `AgentLoop` 的每个 `yield` 后增量保存状态。
2. **用 BullMQ 实现子 Agent 调度**。创建 3 个 Worker，主 Agent 把子任务推入队列。
3. **压测你的 Agent 框架**。用 `wrk` 或 `k6` 发 100 并发请求，观察 token 消耗和延迟分布。

---

> 单进程 Agent 是一只独狼。分布式 Agent 是一个狼群。狼群的挑战不在个体能力，而在协作。
