# 第 8 章：上下文管理 —— Prompt Caching 与 Compaction

## 8.1 概念全景

### 8.1.1 上下文：Agent 时代的稀缺资源

在大语言模型的工程实践中，**上下文窗口（Context Window）** 是开发者手中最核心也最昂贵的资源。每一次 API 调用，你不仅为模型生成的 output token 付费，更要为全部 input token 付费——而在长对话或复杂 Agent 场景中，input token 往往占据总成本的 70-90%。

以一个典型的 Claude Code 交互式会话为例：假设 System Prompt 约 15,000 token，工具定义约 3,000 token，对话进行 50 轮后累积的消息历史约 30,000 token。每轮请求都需要把全部 48,000 input token 发送给 API。50 轮下来，总 input token 消耗达到 **240 万 token**。按 Claude Sonnet 4 的定价（$3/MTok input），仅 input 成本就约 $7.20。

这就引出了本章的两个核心命题：

```
上下文 = 有限资源，需要主动管理
  ├── Prompt Caching ── 成本杠杆：复用已处理前缀，写入溢价 25%，读取折扣 90%
  └── Compaction      ── 窗口扩展器：自动或手动压缩历史，为新内容腾出空间
```

两者的协同使用，可以将长对话的 API 成本降低 **70-90%**，同时保持在上下文窗口限制内安全运行。

### 8.1.2 Prompt Caching 的核心思想

Prompt Caching 是 Anthropic 于 2024 年 8 月发布的 API 特性。其工作原理基于一个朴素的观察：**在多轮对话中，每次请求的前缀（System Prompt + 工具定义 + 早期消息历史）几乎完全相同**。与其让模型每次都从头处理这些重复内容，不如在服务端缓存处理结果，后续请求直接从缓存读取。

与传统 KV Cache 不同，Prompt Caching 是 **跨请求** 的——它允许不同 API 调用之间共享缓存。这意味着：

- Session 的第 1 轮：完整处理 System Prompt（15K token），支付标准 input 价格
- Session 的第 2-50 轮：System Prompt 从缓存读取，仅支付 10% 的读取价格
- 总成本从 $7.20 降至约 $1.20（input 部分），**节省 83%**

### 8.1.3 Compaction 的核心思想

Compaction 解决的是另一类问题：**上下文窗口被历史消息填满后，如何为新的交互腾出空间**。它在 Claude Code 和 Agent SDK 中以两种形式存在：

- **Auto-Compaction（自动压缩）**：当上下文使用率达到 75-92% 时自动触发，将早期对话历史替换为摘要
- **Manual Compaction（手动压缩）**：用户通过 `/compact` 命令（Claude Code）或调用 Compaction API 手动触发

Compaction 的工作方式是对早期消息进行**结构化摘要**——保留任务目标、关键决策、当前状态和未完成事项，丢弃冗余的工具输出和中间推理过程。

---

## 8.2 协议规范

### 8.2.1 Prompt Caching 协议定义

#### 8.2.1.1 `cache_control` 标记

Prompt Caching 通过在请求内容块上添加 `cache_control` 标记来工作。API 服务端会缓存从请求开头到最后一个 `cache_control` 标记之间的所有内容（包括 System Prompt、工具定义和消息历史）。

**核心协议参数：**

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `cache_control.type` | `string` | 是 | 固定值 `"ephemeral"`。所有缓存都是临时的，在 TTL 后自动过期 |
| `cache_control.scope` | `string` | 否 | 缓存共享范围。`"global"` 表示跨所有用户共享；省略则默认为组织级隔离 |
| `cache_control.ttl` | `string` | 否 | 缓存存活时间。默认 `"5m"`（5 分钟），符合条件的用户可获得 `"1h"`（1 小时） |

**使用约束：**

| 约束项 | 值 | 说明 |
|------|------|------|
| 最小可缓存 token 数 | 1024（Sonnet/Opus），2048（Haiku） | 前缀总 token 数低于此阈值则不缓存 |
| 最大断点数量 | 4 个 / 请求 | 每个 `cache_control` 标记创建一个缓存断点 |
| 默认 TTL | 5 分钟 | 每次缓存命中会重置 TTL 计时器 |
| 超长 TTL | 1 小时（限定用户） | Anthropic 内部员工或付费订阅用户（未超限）可用 |
| Beta 要求 | 无（已 GA） | 早期需要 `anthropic-beta: prompt-caching-2024-07-31` header，现已移除 |

**Wire 格式示例：**

```json
{
  "model": "claude-sonnet-4-20250514",
  "max_tokens": 1024,
  "system": [
    {
      "type": "text",
      "text": "You are an expert programmer...",
      "cache_control": { "type": "ephemeral" }
    }
  ],
  "messages": [
    {
      "role": "user",
      "content": [
        {
          "type": "text",
          "text": "Read the file src/main.py",
          "cache_control": { "type": "ephemeral" }
        }
      ]
    }
  ]
}
```

**响应中的缓存信息：**

API 响应中的 `usage` 对象包含缓存相关的计费数据：

```json
{
  "usage": {
    "input_tokens": 15000,
    "output_tokens": 500,
    "cache_creation_input_tokens": 14800,
    "cache_read_input_tokens": 0
  }
}
```

- `cache_creation_input_tokens`：本次请求新写入缓存的 token 数，按 **写入价格** 计费
- `cache_read_input_tokens`：本次请求从缓存读取的 token 数，按 **读取价格** 计费
- `input_tokens - cache_creation_input_tokens - cache_read_input_tokens` = 未缓存的 token，按标准价格计费

#### 8.2.1.2 TTL 深度分析：从 60 分钟到 5 分钟的历史演进

Prompt Caching 的 TTL（Time-To-Live）策略经历了多次调整，理解这段历史对架构决策至关重要。

**TTL 时间线：**

| 时期 | TTL | 背景 |
|------|-----|------|
| 2024-08（发布） | 5 分钟（默认） | 初始发布，缓存为临时性设计 |
| 2024-10 ~ 2025-04 | 部分用户 60 分钟 | 通过 feature flag 向付费用户推广长 TTL |
| 2025-05 至今 | 5 分钟（默认），1 小时（限定用户） | 经济性和基础设施压力下收紧长 TTL 资格 |

**5 分钟 TTL 的工程影响：**

1. **Keep-Alive 模式成为刚需**：如果用户思考或操作时间超过 5 分钟，缓存即过期。需要主动发送"心跳"请求来维持缓存。

2. **批处理优先**：将多个请求在 5 分钟窗口内批量发送，最大化缓存复用。

3. **减少对缓存的状态依赖**：架构设计不应假设缓存一定命中，需要优雅降级处理缓存未命中。

4. **Latch 模式**：TTL 判断应在 session 启动时锁定，避免 session 中途 TTL 翻转导致缓存键变化。

#### 8.2.1.3 定价数学

Prompt Caching 的定价策略是：**写入选价高于标准输入，读取价大幅低于标准输入**。以 Claude Sonnet 4 为例：

| 计费类型 | 价格（$/MTok） | 相对标准输入 |
|----------|---------------|-------------|
| 标准 input | $3.00 | 基线（100%） |
| Cache write | $3.75 | +25%（溢价） |
| Cache read | $0.30 | -90%（折扣） |

**盈亏平衡分析：**

假设一个前缀大小为 P token 的 System Prompt，在 N 次请求中使用：

```
无缓存成本 = P × N × $3.00/MTok

有缓存成本 = P × $3.75/MTok（第 1 次写入）
           + P × (N-1) × $0.30/MTok（后续 N-1 次读取）
```

盈亏平衡点出现在当有缓存成本等于无缓存成本时：

```
3.75 + (N-1) × 0.30 = 3.00 × N
3.75 + 0.30N - 0.30 = 3.00N
3.45 = 2.70N
N ≈ 1.28
```

**结论：只要在缓存有效期内读取超过 1 次，Prompt Caching 就开始产生净节省。** 在实际应用中（几十甚至上百轮对话），节省率可达 80-90%。

**不同场景的节省效果：**

| 场景 | 请求数/5min | 缓存命中次数 | 节省比例 |
|------|-----------|------------|---------|
| 单轮问答 | 1 | 0 | 0%（无节省） |
| 简短对话（3 轮） | 3 | 2 | ~55% |
| 标准对话（10 轮） | 10 | 9 | ~80% |
| 长对话（50 轮） | 50 | 49 | ~88% |
| Agent 密集调用 | 100+ | 99+ | ~90% |

#### 8.2.1.4 缓存作用域与标记策略

缓存作用域决定了缓存的共享范围，是 Prompt Caching 高级用法的核心：

| 作用域 | Wire 表示 | 共享范围 | 适用场景 |
|--------|----------|---------|---------|
| `global` | `{ type: "ephemeral", scope: "global" }` | 所有用户共享 | System Prompt 中完全静态的部分（核心指令、行为规范） |
| 组织级（默认） | `{ type: "ephemeral" }`（省略 scope） | 同组织内用户共享 | 组织级共享的 System Prompt 部分 |
| 无标记 | 不添加 `cache_control` | 不缓存（按用户隔离） | 每次请求都不同的动态内容 |

**分层标记策略：**

优秀的分层标记将请求前缀划分为不同缓存作用域的片段：

```
┌─────────────────────────────────────────────────┐
│ System Prompt 块 1: 核心指令                       │
│ cache_control: { type: "ephemeral", scope: "global" }│  ← 全局共享缓存
├─────────────────────────────────────────────────┤
│ System Prompt 块 2: 组织级工作流                    │
│ cache_control: { type: "ephemeral" }              │  ← 组织级共享缓存
├─────────────────────────────────────────────────┤
│ System Prompt 块 3: 用户特定上下文 (CLAUDE.md)      │
│ 无 cache_control                                  │  ← 不缓存（每次不同）
├─────────────────────────────────────────────────┤
│ 工具定义                                          │
│ 无 cache_control                                  │  ← 影响缓存键但不独立标记
├─────────────────────────────────────────────────┤
│ 消息历史 [msg_1, msg_2, ..., msg_N-1]            │
│ 无 cache_control                                  │  ← 前缀匹配
├─────────────────────────────────────────────────┤
│ 消息 N（最后一条）                                  │
│ cache_control: { type: "ephemeral" }              │  ← 标记缓存终点
└─────────────────────────────────────────────────┘
```

**关键设计原则：**

1. **只放一个消息级标记**：API 服务端的 KV 缓存页管理器只保留最后一个 `cache_control` 位置的本地注意力 KV 页。放多个标记会浪费缓存空间且永远不会被恢复。

2. **静态/动态分界**：将 System Prompt 拆分为静态部分（用 global/org scope 标记）和动态部分（不标记），确保动态内容的变化不会使整个 System Prompt 缓存失效。

3. **后缀对齐**：所有变化的内容（用户新消息、新工具结果）应放在缓存断点之后，保持断点之前的前缀字节完全不变。

### 8.2.2 Compaction 协议

#### 8.2.2.1 自动触发机制

Compaction（上下文压缩）在 Anthropic 的 Agent 生态中主要通过 **客户端逻辑** 实现，而非服务端独立 API。Claude Code 和 Agent SDK 实现了多层压缩策略：

**触发条件：**

| 触发条件 | 阈值 | 行为 |
|---------|------|------|
| 上下文使用率 | 75-92% | 自动触发压缩，具体阈值因模型而异 |
| 时间衰减 | 距上次 API 响应 > 5 分钟 | 缓存已冷，直接清理旧的工具输出 |
| 手动触发 | 用户执行 `/compact` | 立即执行完整压缩 + 摘要生成 |
| Token 预算 | 超出工具结果预算 | 将大型工具结果替换为磁盘摘要 |

**压缩管线：**

```
监测上下文使用率 → 超过阈值？
  ├── 否 → 正常处理
  └── 是 → 判断缓存状态
           ├── 缓存有效（热态）→ Cached MC（通过 cache_edits API 删除内容）
           └── 缓存失效（冷态）→ Time-based MC（直接替换消息内容）
```

#### 8.2.2.2 Summarization vs Truncation

Compaction 的核心选择是：**对早期对话进行摘要（Summarization）还是截断（Truncation）**。

| 维度 | Summarization（摘要） | Truncation（截断） |
|------|---------------------|-------------------|
| 数据保留 | 保留语义信息（任务目标、决策、状态） | 完全丢弃早期消息 |
| 上下文保真度 | 高（关键信息保留） | 低（可能丢失重要上下文） |
| Token 效率 | 中等（摘要本身占 token） | 高（彻底移除） |
| 实现复杂度 | 高（需要 LLM 生成摘要） | 低（数组切片） |
| 适用场景 | 长对话、复杂 Agent 任务 | 简单对话、短会话 |
| Claude Code 选择 | **首选**（通过 `/compact` 命令） | 降级方案（缓存冷态时使用） |

**摘要格式（Claude Code 风格）：**

压缩后的上下文以结构化摘要替换原始消息：

```
<summary>
## Task Goal
Implement user authentication with JWT

## Key Decisions
- Use HS256 algorithm for token signing
- Token expiry set to 24 hours
- Refresh token rotation enabled

## Current State
- auth.py: implemented login/logout endpoints
- middleware.py: JWT verification middleware done
- tests/: 8 of 12 tests passing

## Pending Items
- Password reset flow not yet implemented
- Rate limiting needs configuration
</summary>
```

#### 8.2.2.3 缓存保护与 Compaction 的协同

这是 Anthropic 上下文管理中最精妙的设计。传统的 Compaction 直接修改消息内容（将工具结果替换为摘要），这会**破坏请求前缀的字节一致性，导致 Prompt Caching 缓存失效**。

Claude Code 引入了两条互斥路径来解决此问题：

**路径 1：Time-based Microcompact（缓存冷态）**

当缓存已过期（距上次 API 调用 > 5 分钟）时，直接修改消息内容。因为缓存已经失效，修改消息不会产生额外的缓存失效成本。

```
for message in messages:
    if has_old_tool_result(message):
        message.content = "[Old tool result content cleared]"
```

**路径 2：Cached Microcompact（缓存热态）**

当缓存仍然有效时，**不修改消息内容**，而是通过 `cache_edits` API 告诉服务端删除缓存中某些工具结果的内容。这保持了请求前缀的字节一致性，缓存继续命中。

`cache_edits` 的工作方式：
1. 在 `tool_result` 块上添加 `cache_reference` 标记
2. 在后续请求中发送 `cache_edits` 块，指定要删除哪些 `cache_reference` 对应的内容
3. 服务端在 KV 缓存中删除这些内容，但保持前缀字节不变

```json
{
  "role": "user",
  "content": [
    {
      "type": "tool_result",
      "tool_use_id": "tool_001",
      "content": "Very large file content...",
      "cache_reference": "tool_001"
    },
    {
      "type": "cache_edits",
      "edits": [
        { "delete": "tool_001" }
      ]
    }
  ]
}
```

**关键约束**：一旦某个 `cache_edits` 块在某个消息位置被发送，后续所有请求都必须在**相同位置**重新发送它。这是因为 `cache_edits` 本身也是请求前缀的一部分。

### 8.2.3 Prompt Caching 架构模式

#### 8.2.3.1 Keep-Alive Ping 模式

**问题**：用户在两次消息之间可能思考几分钟，导致 5 分钟 TTL 过期。

**解决方案**：在用户思考期间，每隔 240 秒发送一次轻量级的 Keep-Alive 请求，仅包含 System Prompt（不含新消息），触发缓存读/写以重置 TTL 计时器。

**伪代码逻辑**：

```
timer = setInterval(240s):
    if idle and session_active:
        send_keepalive_request(system_prompt)
        // 不计入对话轮次，仅用于维持缓存
```

**成本分析**：

一个 15,000 token 的 System Prompt：
- 每次 Keep-Alive（缓存命中）：15K × $0.30/MTok = $0.0045
- 每 5 分钟一次，每小时 12 次：$0.054/小时
- 相比丢失缓存后重新写入的成本（$0.05625/次），每小时 Keep-Alive 成本低于 1 次缓存重写

#### 8.2.3.2 Request Batching 模式

**问题**：散发的独立请求无法共享缓存。

**解决方案**：将独立的请求在时间窗口内批量发送，最大化缓存共享。

```python
# 不使用批处理（差）
for question in questions:
    response = client.messages.create(
        system=system_prompt,  # 每次都重新处理
        messages=[{"role": "user", "content": question}]
    )
    # 如果间隔 > 5min，缓存全部失效

# 使用批处理（好）
batch = []
for question in questions:
    batch.append({"role": "user", "content": question})
response = client.messages.create(
    system=system_prompt,  # 只处理一次
    messages=batch          # 所有问题在同一个前缀下
)
```

#### 8.2.3.3 Fork 子进程缓存共享

**问题**：fork 出的子 Agent 各自发起 API 请求，如果不共享缓存前缀，每个 fork 都要重新处理大量 token。

**解决方案**：通过 `CacheSafeParams` 确保所有 fork 子进程的请求前缀与父线程完全一致：

```python
@dataclass
class CacheSafeParams:
    """必须与父线程一致的参数，以确保缓存共享。"""
    system_prompt: str          # 直接复用父线程已渲染的字节
    tools: List[dict]           # 相同的工具定义
    model: str                  # 相同的模型
    fork_context_messages: List[dict]  # 共享的消息前缀
    thinking_config: dict       # 相同的思考配置
```

**关键技巧**：
- 直接传递父线程已渲染的 System Prompt 字节，而非重新调用生成函数（重新生成可能因 GrowthBook 或其他 A/B 测试框架的状态差异产生不同结果）
- 所有 fork 子进程的 `tool_result` 使用相同的占位符文本
- 使用 `skipCacheWrite` 模式避免 fork 污染主线程的缓存

---

## 8.3 Python 实现

以下实现位于 `code/python/ch08/` 目录，提供了 Prompt Caching 和 Compaction 的完整 Python 封装。

### 8.3.1 CacheAwareClient

`CacheAwareClient` 封装了 Prompt Caching 的标记逻辑、成本估算和盈亏平衡分析。

```python
# code/python/ch08/cache_aware_client.py
```

完整实现包含：
- `create_with_cache()`：在指定位置注入 `cache_control` 标记
- `estimate_cache_savings()`：根据预期请求数计算缓存节省金额
- `should_cache()`：基于盈亏平衡分析判断是否值得缓存
- `extract_usage()`：从 API 响应中提取缓存使用数据

### 8.3.2 CacheKeepAlive

`CacheKeepAlive` 实现了 Keep-Alive Ping 模式，通过定时发送轻量级请求维持缓存热度。

```python
# code/python/ch08/cache_keepalive.py
```

完整实现包含：
- 可配置的 Ping 间隔（默认 240 秒）
- 自动后台线程管理
- 空闲检测（用户无操作时才发送 Keep-Alive）
- 优雅的启动/停止生命周期

### 8.3.3 CompactionHandler

`CompactionHandler` 实现了上下文压缩的触发判断和执行逻辑。

```python
# code/python/ch08/compaction_handler.py
```

完整实现包含：
- `should_compact()`：基于上下文使用率判断是否需要压缩
- `compact()`：执行摘要式压缩，将早期消息替换为结构化摘要
- 阈值可配置（默认 80%）
- 保留关键消息（System 消息、最近的 N 轮对话）

---

## 8.4 Node.js 实现

TypeScript 实现位于 `code/node/ch08/` 目录，接口与 Python 版本对称。

### 8.4.1 CacheAwareClient

```typescript
// code/node/ch08/CacheAwareClient.ts
```

### 8.4.2 CacheKeepAlive

```typescript
// code/node/ch08/CacheKeepAlive.ts
```

### 8.4.3 CompactionHandler

```typescript
// code/node/ch08/CompactionHandler.ts
```

---

## 8.5 最佳实践

### 8.5.1 Cache-Aware Prompt 结构化

**法则 1：稳定在前，变化在后**

将所有不经常变化的内容放在请求前缀的**前面**，将每轮变化的内容放在**后面**。这样缓存断点可以覆盖所有稳定前缀。

```
正确顺序：
  System Prompt（稳定）→ 工具定义（稳定）→ 消息历史（半稳定）→ 最新消息（变化）

错误顺序：
  最新消息（变化）→ System Prompt（稳定）→ ...  // 前缀不稳定，缓存无法命中
```

**法则 2：所有变化的内容应放在缓存断点之后**

在最后一条消息上放置 `cache_control` 标记，确保之前的所有内容都被缓存。

**法则 3：避免"隐蔽的变化"破坏缓存**

以下看似无害的变化都会导致缓存完全失效：
- 修改工具定义中的 JSON 字段顺序
- System Prompt 中的空格或换行变化
- Feature flag 的运行时翻转
- 环境变量变化导致的动态内容差异

### 8.5.2 生产环境 Keep-Alive 策略

1. **Ping 间隔设置**：设为 240 秒（4 分钟），留出 1 分钟缓冲
2. **空闲检测**：只在用户无操作时发送 Ping，避免干扰正常对话
3. **失败处理**：Ping 失败不应中断用户会话，静默重试最多 3 次
4. **资源管理**：会话结束后立即停止 Ping 线程，避免资源泄漏

### 8.5.3 Compaction 阈值调优

| 应用场景 | 推荐阈值 | 理由 |
|---------|---------|------|
| 短对话（< 10 轮） | 不启用 | 压缩开销大于收益 |
| 中等对话（10-30 轮） | 85% | 保留充足的上下文用于连贯推理 |
| 长对话（30+ 轮） | 75% | 更早触发，为后续轮次留出更多空间 |
| 复杂 Agent 任务 | 80% | 平衡上下文保留和空间释放 |

### 8.5.4 缓存命中率监控

在生产环境中监控以下指标：

- **缓存命中率** = `cache_read_input_tokens / total_input_tokens`
- **缓存写入率** = `cache_creation_input_tokens / total_input_tokens`
- **缓存浪费率** = 缓存写入但从未命中的 token 比例

目标：缓存命中率 > 60%，缓存浪费率 < 20%。

---

## 8.6 自测题

### 题 1：概念理解

Prompt Caching 的 5 分钟 TTL 如何影响客户端架构设计？请列举至少 3 种应对策略。

### 题 2：协议理解

在一个请求中，cache_control 标记最多可以放几个？为什么 Claude Code 的设计选择每个请求只放一个消息级标记？

### 题 3：场景分析

一个应用有 10,000 个用户，每个用户的会话平均持续 30 轮对话。System Prompt 大小为 12,000 token，其中 8,000 token 对于所有用户完全相同（核心指令），另外 4,000 token 是用户特定的（包含用户偏好和自定义工作流）。请设计分层缓存策略，并计算相比无缓存的成本节省。

### 题 4：编程题 —— 实现缓存盈亏计算器

编写一个函数 `cache_breakeven_analysis(write_price_per_mtok, read_price_per_mtok, base_price_per_mtok, cacheable_tokens)`，返回：

1. 盈亏平衡点（最少需要多少次读取才能开始节省成本）
2. 在 5、10、50、100 次请求下的节省比例
3. 如果读取次数在 5 分钟 TTL 内无法达到盈亏平衡点，返回 `False`

请在 Python 和 TypeScript 中各实现一份。

---

## 本章小结

Prompt Caching 和 Compaction 是 Anthropic API 生态中两把关键的"成本手术刀"：

- **Prompt Caching** 通过跨请求缓存前缀来降低重复内容的处理成本，适用于任何前缀稳定的多轮对话场景。核心约束是字节一致性——任何前缀变化都会导致缓存失效。
- **Compaction** 通过智能摘要来回收被历史消息占用的上下文空间，同时尽可能保护缓存不被破坏。Cached Microcompact 路径通过 `cache_edits` API 实现了在不破坏缓存的前提下清理上下文。

两者的协同使用体现了 Anthropic 上下文工程的核心哲学：**在保护缓存前缀一致性的前提下，最大化上下文窗口的利用效率**。

在下一章中，我们将探讨 Anthropic API 的高级特性——Extended Thinking（扩展思考）和 Streaming（流式输出），理解 Claude 如何在生成质量与响应速度之间取得平衡。
