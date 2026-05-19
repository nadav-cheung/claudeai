# 第 9 章：Batch API —— 异步批量处理的协议与实践

## 9.1 概念全景

### 9.1.1 同步 vs 异步：两种处理范式

在前面章节中，我们使用的 Messages API 是**同步**的：发送请求，等待模型逐 token 生成，获取完整响应。这种模式适合交互式场景——聊天应用、代码助手、实时 Agent——用户期望在秒级获得响应。

但并非所有工作负载都需要即时响应。考虑以下场景：

- **大规模评测**：你需要用 10,000 个测试用例评估模型质量，每个用例独立运行。你关心的是聚合指标（准确率、通过率），而非单个用例的实时结果。
- **内容审核**：每天凌晨 3 点，你的系统需要对过去 24 小时产生的 50 万条用户评论进行批量审核。没有用户在线等待结果。
- **数据标注与增强**：你有 100 万条产品描述，需要为每条生成 SEO 标签和摘要。这是离线 ETL 任务，跑完通知你即可。
- **定期报告生成**：每周一生成上周的全部客户反馈分析报告，包含情绪分析、主题提取和趋势总结。

这些场景的共同特征：**吞吐量优先于延迟**。Batch API 正是为此而生。

### 9.1.2 成本与延迟的权衡

Batch API 的核心价值主张可用一句话概括：

> **用时间换金钱 —— 用 50% 的成本，接受最多 24 小时的等待。**

具体来说：

| 维度 | 实时 Messages API | Batch API |
|------|-------------------|-----------|
| 响应延迟 | 秒级（流式）或数十秒（非流式） | 分钟至小时级（多数在 1 小时内完成） |
| 成本 | 标准价格 | **50% 折扣** |
| 并发能力 | 受每分钟速率限制（RPM）约束 | 独立批次速率限制，可处理高达 100,000 个请求 |
| SLA | 无明确完成保证 | 24 小时内完成，超时自动过期 |
| 结果获取 | 同步返回 | 异步轮询 + JSONL 下载 |
| 适用场景 | 交互式应用 | 批量评估、离线处理、大规模数据标注 |

这个权衡并非 Anthropic 独有 —— 几乎所有大模型提供商（OpenAI、Google、AWS Bedrock）都提供了类似的批量推理折扣。背后的经济学原理很简单：**异步批处理允许提供商在负载低谷期调度计算资源，提高 GPU 利用率，从而将成本节约传递给用户**。

### 9.1.3 Message Batches API 能力边界

在深入协议之前，需要明确 Batch API 的能力边界：

**可以批处理的内容：**
- 任何标准 Messages API 请求（包括多轮对话、System 消息、Vision 图片分析）
- Tool Use 定义与调用（每个批次请求独立处理，可以使用不同工具）
- Structured Outputs（JSON Mode）
- Prompt Caching（缓存命中率 30%-98%，取决于流量模式）
- 混合请求类型（同一批次中可以包含不同模型、不同参数的请求）

**限制：**
- 单个批次最多 **100,000 个请求** 或 **256 MB**，以先到者为准
- 结果保留 **29 天**（从批次创建时间算起，非完成时间）
- 批次在 Workspace 级别隔离，只能被创建它的 API Key 所在 Workspace 访问
- 速率限制适用于批处理 HTTP 端点调用**和**批次内待处理的请求数
- 由于高吞吐量和并发处理，批次可能略微超过 Workspace 的配置消费限额

---

## 9.2 协议规范

### 9.2.1 MessageBatch 完整生命周期

MessageBatch 在其生命周期中经历明确的状态转换。理解这些状态是正确使用 Batch API 的基础。

```
                    ┌─────────────┐
                    │ in_progress │ ← 批次创建时的初始状态
                    └──────┬──────┘
                           │
              ┌────────────┼────────────┐
              │            │            │
              ▼            ▼            ▼
        ┌─────────┐  ┌──────────┐  ┌──────────┐
        │  ended  │  │ canceled │  │ expired  │
        └─────────┘  └──────────┘  └──────────┘
        所有请求已     用户主动     24 小时 SLA
        处理完毕      取消批次     到期未完成
```

**状态转换表：**

| 状态 | 含义 | 触发条件 | 可执行操作 |
|------|------|----------|-----------|
| `in_progress` | 批次正在处理中 | 创建批次后自动进入 | 查询状态、取消批次 |
| `ended` | 所有请求已处理完毕 | 批次中每个请求均完成（成功/失败/过期/取消） | 下载结果 |
| `canceled` | 用户手动取消 | 调用 cancel 端点 | 下载已完成请求的结果 |
| `expired` | 24 小时 SLA 到期 | 系统在 24 小时后自动将未完成批次标记为过期 | 仅能查看状态，无法获取结果 |

**关键时间窗口：**
- 创建后 24 小时内：批次要么完成，要么过期
- 创建后 29 天内：可以下载结果（仅限 `ended` 和部分 `canceled` 的批次）
- 超过 29 天：批次元数据仍可见，但结果不可下载

### 9.2.2 请求格式

每个批次请求是一个包含两个字段的 JSON 对象：

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `custom_id` | `string` | 是 | 客户端定义的唯一标识符。批次内必须唯一。用于将结果映射回原始请求，因为结果返回顺序不保证与提交顺序一致 |
| `params` | `object` | 是 | 标准 Messages API 参数，必须包含 `model`、`max_tokens`、`messages`，可选 `system`、`tools`、`temperature`、`top_p`、`stop_sequences`、`metadata`、`thinking` 等 |

**完整请求示例：**

```json
{
  "requests": [
    {
      "custom_id": "eval-sentiment-001",
      "params": {
        "model": "claude-haiku-3-5-20241022",
        "max_tokens": 50,
        "temperature": 0,
        "system": "你是一个情感分析专家。请以 JSON 格式返回情感标签。",
        "messages": [
          {"role": "user", "content": "这家餐厅的服务太棒了，我一定会再来！"}
        ]
      }
    },
    {
      "custom_id": "eval-sentiment-002",
      "params": {
        "model": "claude-haiku-3-5-20241022",
        "max_tokens": 50,
        "temperature": 0,
        "system": "你是一个情感分析专家。请以 JSON 格式返回情感标签。",
        "messages": [
          {"role": "user", "content": "等了两个小时才上菜，非常失望。"}
        ]
      }
    },
    {
      "custom_id": "eval-summarize-003",
      "params": {
        "model": "claude-sonnet-4-20250514",
        "max_tokens": 200,
        "messages": [
          {"role": "user", "content": "请总结以下文章的主要内容：\n\n[长文本...]"}
        ]
      }
    }
  ]
}
```

**custom_id 最佳实践：**

由于结果顺序不保证与提交顺序一致，`custom_id` 是将结果关联回原始请求的唯一依据。推荐使用包含语义信息的命名方案：

```
{task_type}-{dataset}-{index}-{timestamp}
```

例如：`sentiment-yelp-reviews-00001-20260517`、`classify-news-articles-00142-v2`。

### 9.2.3 创建批次

**端点：** `POST /v1/messages/batches`

**请求头：**
```
x-api-key: {YOUR_API_KEY}
anthropic-version: 2023-06-01
content-type: application/json
```

**成功响应（200）：**

```json
{
  "id": "msgbatch_01ABCxyz...",
  "type": "message_batch",
  "processing_status": "in_progress",
  "request_counts": {
    "processing": 15000,
    "succeeded": 0,
    "errored": 0,
    "canceled": 0,
    "expired": 0
  },
  "created_at": "2026-05-17T10:00:00Z",
  "expires_at": "2026-05-18T10:00:00Z",
  "archived_at": null,
  "cancel_initiated_at": null,
  "results_url": null
}
```

**错误响应：**

| HTTP 状态码 | 含义 | 处理方式 |
|------------|------|---------|
| `401` | API Key 无效 | 检查认证信息 |
| `413` | 请求体超过 256 MB | 拆分为多个批次 |
| `429` | 速率限制 | 实现指数退避重试 |
| `400` | 请求格式错误（如缺少必填字段） | 验证请求结构 |

### 9.2.4 查询批次状态

**端点：** `GET /v1/messages/batches/{message_batch_id}`

轮询此端点可以监控批次处理进度。响应中包含最重要的字段：

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | `string` | 批次唯一标识符 |
| `processing_status` | `string` | 当前状态：`in_progress` / `ended` / `canceled` / `expired` |
| `request_counts` | `object` | 各状态请求的计数，包含 `processing`、`succeeded`、`errored`、`canceled`、`expired` |
| `created_at` | `string` | 创建时间（ISO 8601） |
| `ended_at` | `string` \| `null` | 完成时间 |
| `expires_at` | `string` | 过期时间（创建后 24 小时） |
| `results_url` | `string` \| `null` | 结果下载 URL（仅在 `ended` 时可用） |

**典型轮询序列：**

```
GET .../msgbatch_xxx → processing_status: "in_progress", request_counts.processing: 15000
GET .../msgbatch_xxx → processing_status: "in_progress", request_counts.processing: 8000
GET .../msgbatch_xxx → processing_status: "in_progress", request_counts.processing: 2000
GET .../msgbatch_xxx → processing_status: "ended",     request_counts.succeeded: 14980
                                                        request_counts.errored: 20
```

### 9.2.5 异步结果获取

**端点：** `GET /v1/messages/batches/{message_batch_id}/results`

当 `processing_status` 变为 `ended` 后，可以通过此端点获取结果。响应是 **JSONL 格式**（每行一个 JSON 对象），代表批次中每个请求的结果。由于结果集可能非常大（最多 100,000 条），**建议流式读取而非一次下载全部**。

**JSONL 行格式：**

```jsonl
{"custom_id":"eval-sentiment-001","result":{"type":"succeeded","message":{"id":"msg_01Xxx...","role":"assistant","model":"claude-haiku-3-5-20241022","content":[{"type":"text","text":"{\"sentiment\": \"positive\", \"confidence\": 0.95}"}],"stop_reason":"end_turn","stop_sequence":null,"usage":{"input_tokens":45,"output_tokens":25}}}}
{"custom_id":"eval-sentiment-002","result":{"type":"succeeded","message":{"id":"msg_02Xxx...","role":"assistant","model":"claude-haiku-3-5-20241022","content":[{"type":"text","text":"{\"sentiment\": \"negative\", \"confidence\": 0.92}"}],"stop_reason":"end_turn","stop_sequence":null,"usage":{"input_tokens":48,"output_tokens":26}}}}
{"custom_id":"eval-summarize-003","result":{"type":"errored","error":{"type":"invalid_request_error","message":"max_tokens must be greater than 0"}}}
{"custom_id":"eval-sentiment-999","result":{"type":"canceled"}}
{"custom_id":"eval-sentiment-1000","result":{"type":"expired"}}
```

### 9.2.6 四种 Result Type 详解

| 结果类型 | 含义 | 包含字段 | 是否计费 |
|---------|------|---------|---------|
| `succeeded` | 请求成功处理 | `result.message`：完整的 Messages API 响应 | **是**（按批次价格） |
| `errored` | 请求处理失败（参数错误、服务端错误等） | `result.error`：标准错误对象（含 `type` 和 `message`） | **否** |
| `canceled` | 用户取消批次，此请求未发送给模型 | 仅 `result.type` | **否** |
| `expired` | 24 小时到期，此请求未发送给模型 | 仅 `result.type` | **否** |

**重要：** 单个请求的失败（`errored`）不会影响同一批次中其他请求的处理。每个请求独立调度、独立执行、独立计费。

**错误类型的可恢复性分析：**

`errored` 结果中的错误对象包含 `type` 字段，指示错误类别。理解不同错误类型的可恢复性对于生产系统至关重要：

| 错误类型 | 含义 | 可恢复 | 处理建议 |
|---------|------|--------|---------|
| `invalid_request_error` | 请求参数不合法（如缺少 `max_tokens`、`model` 字段无效） | 否 | 修复请求参数后重新提交 |
| `authentication_error` | API Key 无效或无权访问该模型 | 否 | 检查认证信息和 Workspace 权限 |
| `permission_error` | Workspace 无权访问指定模型 | 否 | 更换可用模型或升级 Workspace 权限 |
| `not_found_error` | 指定的模型不存在 | 否 | 检查模型 ID 拼写和可用性 |
| `rate_limit_error` | 超出速率限制 | **是** | 等待后重试，减小批次规模 |
| `overloaded_error` | Anthropic 服务端暂时过载 | **是** | 指数退避后重试；批次 API 自身会处理内部重试，此错误出现在请求级别表示重试已耗尽 |
| `api_error` | Anthropic 内部服务器错误（500） | **是** | 等待后重试；这是临时性服务端故障 |

在实际生产中，**`overloaded_error` 和 `api_error` 是你应该自动重试的两类错误**。其余错误类型需要人工审查和修复。我们将在 9.5.2 节中提供完整的错误分类和重试模式。

### 9.2.7 取消批次

**端点：** `POST /v1/messages/batches/{message_batch_id}/cancel`

取消一个正在进行中的批次。已在处理的请求将完成并获得正常结果；尚未开始的请求将被标记为 `canceled` 且不计费。

取消操作的响应是被取消批次的完整状态对象，其中 `processing_status` 已更新为 `canceled`。

```json
{
  "id": "msgbatch_01ABCxyz...",
  "processing_status": "canceled",
  "request_counts": {
    "processing": 0,
    "succeeded": 5230,
    "errored": 12,
    "canceled": 9758,
    "expired": 0
  }
}
```

### 9.2.8 列出批次

**端点：** `GET /v1/messages/batches?limit=20&after_id={batch_id}`

列出当前 Workspace 中的所有批次，按创建时间降序排列。支持基于游标的分页（通过 `after_id` 参数）。

### 9.2.9 50% 折扣模型与成本计算

Batch API 所有模型的使用价格均为标准价格的 **50%**。这是异步处理的直接经济激励。

**批次价格表（每百万 Token）：**

| 模型 | 标准输入价格 | Batch 输入价格 | 标准输出价格 | Batch 输出价格 |
|------|------------|---------------|------------|---------------|
| Claude Opus 4 | $15.00 | **$7.50** | $75.00 | **$37.50** |
| Claude Sonnet 4 / 3.7 | $3.00 | **$1.50** | $15.00 | **$7.50** |
| Claude Sonnet 3.5 | $3.00 | **$1.50** | $15.00 | **$7.50** |
| Claude Haiku 3.5 | $0.80 | **$0.40** | $4.00 | **$2.00** |
| Claude Opus 3 | $15.00 | **$7.50** | $75.00 | **$37.50** |
| Claude Haiku 3 | $0.25 | **$0.125** | $1.25 | **$0.625** |

**成本节约计算器：**

以一个典型的大规模评测任务为例：

```
任务：评估 50,000 条文本的情感分类
模型：Claude Haiku 3.5
输入/请求：~100 tokens
输出/请求：~30 tokens

实时 API 成本：
  输入：50,000 × 100 / 1,000,000 × $0.80  = $4.00
  输出：50,000 × 30 / 1,000,000 × $4.00   = $6.00
  合计：$10.00

Batch API 成本：
  输入：50,000 × 100 / 1,000,000 × $0.40  = $2.00
  输出：50,000 × 30 / 1,000,000 × $2.00   = $3.00
  合计：$5.00

节省：$5.00 (50%)
```

对于更大的任务或更贵的模型，节约效果更加显著：

```
任务：Claude Opus 4 处理 10,000 篇长篇文档分析
输入/请求：~5,000 tokens
输出/请求：~1,000 tokens

实时 API：$900 + $750 = $1,650
Batch API：$450 + $375 = $825
节省：$825
```

### 9.2.10 Batch + Cache 组合策略

Prompt Caching 与 Batch API 可以叠加使用，提供更深层的成本优化。

**工作机制：**

在批次内，当多个请求共享相同的 prompt 前缀（如相同的 system 消息或长文档上下文）时，批次处理引擎会在**尽力而为（best-effort）**的基础上尝试复用缓存。由于批次请求是异步且并发处理的，缓存命中率取决于流量模式——通常在 30%-98% 之间。

**缓存 TTL 选项：**

| TTL 类型 | 有效期 | 写入价格 | 适用场景 |
|----------|--------|---------|---------|
| 默认（5 分钟） | 5 分钟，每次命中自动刷新 | 标准输入价格的 125%（如 Sonnet 4 为 $3.75/MTok） | 批次内密集请求，短时间内大量相同前缀的请求 |
| 1 小时 | 1 小时（不自动刷新） | 标准输入价格的 200%（如 Sonnet 4 为 $6.00/MTok） | 批次跨越较长时间窗口，如分批次提交相同模板的请求 |

**在批次请求中启用 Prompt Caching：**

```json
{
  "custom_id": "batch-cached-001",
  "params": {
    "model": "claude-sonnet-4-20250514",
    "max_tokens": 500,
    "system": [
      {
        "type": "text",
        "text": "你是一位资深文学评论家。你擅长分析文本中的主题、象征意义和写作风格。",
        "cache_control": {"type": "ephemeral"}
      }
    ],
    "messages": [
      {
        "role": "user",
        "content": "请分析《百年孤独》的开篇段落中的魔幻现实主义元素..."
      }
    ]
  }
}
```

**批次内提高缓存命中率的策略：**

1. **在所有请求中包含完全相同的 `cache_control` 块**——即使一个字节的差异也会导致缓存未命中
2. **保持稳定的请求流**，防止缓存在 5 分钟默认 TTL 后过期
3. **尽可能多地共享可缓存内容**——将不变的内容（system prompt、上下文文档）放在 prompt 开头并标记为可缓存
4. **对于跨越较长时间窗口的批次，使用 1 小时 TTL**——通过 `"cache_control": {"type": "ephemeral", "ttl": 3600}`
5. **先做一次实时 API 调用预热**——这会将内容写入缓存，后续批次请求可以读取

**组合成本模型：**

缓存写入 + 批次折扣 = 双重叠加：

```
实时 API：Sonnet 4 输入 $3.00/MTok（基准）
Batch API：$1.50/MTok（50% 折后价格）
Batch + Cache Write：$1.875/MTok（批次折扣 × 缓存写入溢价 125%）
Batch + Cache Hit：$0.15/MTok（批次折扣 × 缓存命中价格 10%）
```

这意味着对于高缓存命中率的批次工作负载，**输入 Token 成本可以降到基准价格的 5%**。

**批次内缓存的"尽力而为"语义：**

与实时 API 中的缓存不同，批次内的 Prompt Caching 具有"尽力而为"特性。这源于批处理引擎的架构特征：

1. **并发处理导致竞态窗口**：批次引擎并行处理大量请求。当请求 A 写入缓存时，请求 B 可能已经在处理中而无法受益于 A 刚写入的缓存。这就是为什么缓存命中率在 30%-98% 之间波动——初始批次中最早处理的那批请求将承担缓存写入成本，后续请求才能享受缓存命中。

2. **5 分钟 TTL 的批次意义**：对于大多数在 1 小时内完成的中等批次，5 分钟的默认 TTL 通常足够——处理密集度足以在 TTL 窗口内产生大量命中。但对于超大批次（接近 100,000 请求），请求可能分散在数十分钟内，这时 1 小时 TTL 更有优势。

3. **预热策略**：如果你提前知道批次中的静态内容，可以先发送一个带有相同 `cache_control` 标记的小规模实时 API 请求，将内容写入缓存。然后立即提交批次——所有批次请求都能命中这个预热的缓存。

4. **缓存不命中时的成本**：如果缓存未命中，你支付的是标准的批次输入价格（即 50% 折扣的标准价格），而不是缓存写入价格。因此，即使缓存命中率不理想，你也只是失去了额外优惠，不会产生额外成本。

**真实场景示例：**

假设你有一个文档问答评测任务，需要向 10,000 篇不同文档各问 10 个问题（共 100,000 个请求）。每篇文档 5,000 token，每个问题 50 token。

策略 A（不做缓存）：每个请求输入 = 5,050 token，100,000 请求 = 505M 输入 token。
策略 B（缓存文档前缀）：每个请求输入 = 50 token（仅问题部分，文档从缓存读取）。但第一批请求中的每一个文档的第一个问题仍需要写入缓存（5,000 token），后续 9 个问题全部命中缓存。

实际效果取决于批处理引擎的调度。一个好的策略是：**按文档分组提交批次**，每个文档 10 个问题紧邻排列，最大化同一文档的缓存复用窗口。

### 9.2.11 支持的模型

Batch API 目前支持以下模型（截至 2026 年 5 月）：

- Claude Opus 4 (`claude-opus-4-20250514`)
- Claude Sonnet 4 (`claude-sonnet-4-20250514`)
- Claude Sonnet 3.7 (`claude-3-7-sonnet-20250219`)
- Claude Sonnet 3.5 (`claude-3-5-sonnet-20240620` / `claude-3-5-sonnet-20241022`)
- Claude Haiku 3.5 (`claude-3-5-haiku-20241022`)
- Claude Haiku 3 (`claude-3-haiku-20240307`)
- Claude Opus 3 (`claude-3-opus-20240229`)

**模型选择策略：**

Batch API 的场景特性使得模型选择与实时 API 有所不同。由于不追求快速响应，你可以根据任务的复杂度而非延迟来选择模型：

- **简单分类/标注任务**（情感分析、意图识别、是否判断）→ **Claude Haiku 3.5**：每 100 万输出 Token 仅 $2.00（批次价），成本效益极高。对于 10 万条评论的情感分类，Haiku 3.5 的批次成本约为 $0.50-$2.00。

- **中等复杂度任务**（摘要生成、翻译、数据提取）→ **Claude Sonnet 4**：在质量和成本之间取得平衡。适合需要准确理解上下文但不需要顶级推理能力的任务。

- **高难度推理任务**（法律文档分析、复杂数学推理、多步骤逻辑判断）→ **Claude Opus 4**：虽然批次价格为 $37.50/MTok 输出，但对于需要最高准确率的评测和质量敏感的场景，Opus 的准确性值得额外成本。

- **成本极度敏感**（500 万+ 条推文的情感标注）→ **Claude Haiku 3**：$0.125/MTok 输入 + $0.625/MTok 输出的批次价格几乎是免费级别的。

一个实用原则：**先在 100-200 条的样本上用不同模型做质量对比，确认质量达标后，选择满足质量需求的最便宜模型进行大规模批处理**。

### 9.2.12 使用场景与反模式

**适合 Batch API 的场景：**

| 场景 | 典型规模 | 批处理价值 |
|------|---------|-----------|
| **模型评测（Evals）** | 1,000-100,000 个测试用例 | 50% 成本节约，不需要实时响应 |
| **批量分类/标注** | 10,000-1,000,000 条文本 | 离线处理，延迟不敏感 |
| **数据增强生成** | 5,000-500,000 条合成数据 | 大规模吞吐 |
| **定期报告生成** | 100-10,000 个报告 | 周期性任务，无人等待 |
| **搜索/推荐索引构建** | 50,000-1,000,000 个查询 | 一次性批量处理 |
| **翻译任务** | 1,000-100,000 个文档 | 非交互式，成本敏感 |

**不适合 Batch API 的反模式：**

| 反模式 | 为什么不适合 | 替代方案 |
|--------|------------|---------|
| **聊天/对话应用** | 用户期望秒级响应 | 标准 Messages API + Streaming |
| **少量请求（< 50 个）** | 管理开销 > 成本节约 | 直接使用标准 API |
| **依赖请求间顺序** | 批次请求独立且并发处理，无顺序保证 | 标准 API + 请求-响应循环 |
| **需要实时响应的 Agent** | 延迟不可接受 | 标准 API + Tool Use + Streaming |
| **有严格时效要求的生产流程** | 24 小时 SLA 可能不够快 | 标准 API + 异步任务队列（如 Celery） |
| **单步决策（一次只处理一个）** | 批处理框架的复杂度 > 收益 | 直接调用标准 API |

一条判断法则：**如果你的 QPS（每秒查询数）足够高，使得你在 1-3 小时内会自然积累成百上千个请求，那么 Batch API 就是正确的选择。如果每个请求都是用户在线等待的，用实时 API。**

**深入反模式分析：**

以下通过具体案例说明何时不应使用 Batch API：

**反模式 1：用 Batch 替代实时 API 来"省钱"**

某个聊天应用开发者想：既然 Batch 半价，为什么不把用户消息缓存起来，每 10 分钟提交一次批次？这是典型的 **延迟换成本** 的滥用。用户等待 10 分钟才收到回复是不可接受的。正确的做法是使用实时 API + Prompt Caching（也可节约成本，且延迟不变）。

**反模式 2：用 Batch 处理有依赖关系的多步任务**

如果你需要先让 Claude 分析一个问题，然后根据分析结果决定下一步（例如：先判断是否需要调用工具，然后调用工具，再分析工具结果），批次无法支持这种模式。每个批次请求都是独立且隔离的——它不知道其他请求的结果。处理流程型任务应使用标准 Messages API + Tool Use 循环。

**反模式 3：用 Batch 替代任务队列系统**

Batch API 不是一个通用任务队列。它没有优先级概念、没有调度策略、没有依赖管理。如果你需要复杂的任务编排（如 DAG 工作流、条件分支、回调通知），应该使用专门的任务队列系统（Celery、BullMQ、Temporal 等），将 Batch API 仅用于"调用模型"这一环节。

**反模式 4：忽略结果保留期进行懒加载处理**

批次结果在创建 29 天后过期。如果你的下游处理管道设计为"有空再处理"，但可能超过 29 天才执行，结果可能已不可用。在创建批次的同时建立监控告警，确保在 29 天窗口内下载和处理所有结果。

### 9.2.13 批处理速率限制

Batch API 有两层速率限制需要理解：

**HTTP 端点速率限制：** 对 `/v1/messages/batches` 的 POST 和 GET 请求有独立的速率限制。创建批次的速率远低于实时 Messages API——通常每分钟允许创建少量批次（具体数值取决于你的 Workspace 配额）。这意味着你需要合理安排批次提交节奏，避免短时间大量 POST 触发 429 错误。

**批次内请求处理速率限制：** 你提交到批次中的请求不是立即全部处理的。Anthropic 会根据当前负载和你的 Workspace 用量历史平滑调度批次内请求的处理速度。在高峰期，处理速度可能放缓，导致更多的请求在 24 小时内无法完成而过期。

**应对策略：**
- 对于超大规模任务（>1,000,000 个请求），分多天提交批次
- 监控批次的 `expired` 计数——如果过高，说明当前处理速率不足，应减小每日提交量
- 使用多个批次而非单个巨无霸批次，以便在部分批次过期时快速重新提交

---

## 9.3 Python 实现

本章的 Python 实现位于 `code/python/ch09/batch_client.py`，提供了一个无 SDK 依赖的、直连 HTTP 的 `BatchClient` 类，完整覆盖了 MessageBatch 的整个生命周期。

### 9.3.1 安装依赖

```bash
pip install httpx
```

### 9.3.2 核心类设计

```python
from batch_client import BatchClient, MessageRequest

client = BatchClient(api_key="sk-ant-...")

# 创建批次
batch_id = client.create_batch([
    MessageRequest(
        custom_id="task-001",
        params={
            "model": "claude-haiku-3-5-20241022",
            "max_tokens": 100,
            "messages": [{"role": "user", "content": "分析这段文本的情感..."}]
        }
    ),
    # ... 更多请求
])

# 同步等待完成
results = client.wait_for_completion(batch_id, poll_interval=30)
```

**`BatchClient` 公开 API：**

| 方法 | 返回值 | 说明 |
|------|--------|------|
| `create_batch(requests)` | `str` (batch_id) | 创建新批次 |
| `get_batch_status(batch_id)` | `BatchInfo` | 查询批次状态 |
| `get_batch_results(batch_id)` | `list[BatchResult]` | 下载并解析 JSONL 结果 |
| `cancel_batch(batch_id)` | `BatchInfo` | 取消批次 |
| `list_batches(limit, after_id)` | `list[BatchInfo]` | 列出所有批次 |
| `wait_for_completion(batch_id, poll_interval, max_wait)` | `list[BatchResult]` | 轮询直到完成并返回结果 |

**领域类型：**

```python
@dataclass
class MessageRequest:
    custom_id: str       # 客户端定义的唯一请求 ID
    params: dict         # Messages API 参数

@dataclass
class BatchInfo:
    id: str
    processing_status: BatchProcessingStatus  # in_progress/ended/canceled/expired
    request_counts: dict                       # {succeeded: N, errored: N, ...}
    created_at: str
    ended_at: str
    expires_at: str
    results_url: str | None

@dataclass
class BatchResult:
    custom_id: str
    result_type: ResultType  # succeeded/errored/canceled/expired
    message: dict | None     # 成功的消息响应
    error: dict | None       # 错误详情
```

### 9.3.3 完整使用示例

**场景：情感分析评测**

```python
from batch_client import BatchClient, MessageRequest

client = BatchClient(api_key="sk-ant-...")

# 准备 100 条评测数据
reviews = [
    ("review-001", "这家餐厅服务太棒了！"),
    ("review-002", "等了两个小时，非常失望。"),
    # ... 共 100 条
]

requests = [
    MessageRequest(
        custom_id=rid,
        params={
            "model": "claude-haiku-3-5-20241022",
            "max_tokens": 50,
            "temperature": 0,
            "system": "你是一个情感分析专家。请仅返回一个词：positive、negative 或 neutral。",
            "messages": [{"role": "user", "content": text}]
        }
    )
    for rid, text in reviews
]

# 提交批次
batch_id = client.create_batch(requests)
print(f"批次已创建：{batch_id}")

# 等待完成（最长 24 小时）
results = client.wait_for_completion(batch_id, poll_interval=60)

# 分析结果
succeeded = [r for r in results if r.result_type == "succeeded"]
errored = [r for r in results if r.result_type == "errored"]

print(f"成功：{len(succeeded)}，失败：{len(errored)}")
for r in errored:
    print(f"  {r.custom_id}: {r.error}")

# 构建评测结果
predictions = {
    r.custom_id: r.message["content"][0]["text"].strip()
    for r in succeeded
}
```

### 9.3.4 Batch + Cache 组合使用

```python
from batch_client import BatchClient

client = BatchClient()

# 使用 1 小时 TTL 的缓存友好请求
requests = [
    BatchClient.make_cacheable_request(
        custom_id=f"doc-qa-{i:05d}",
        model="claude-sonnet-4-20250514",
        max_tokens=300,
        user_message=question,
        system_prompt="你是一个文档分析专家。请基于提供的文档内容回答问题。",
        cache_ttl=3600  # 1 小时 TTL
    )
    for i, question in enumerate(questions)
]

batch_id = client.create_batch(requests)
results = client.wait_for_completion(batch_id)
```

运行测试验证实现：

```bash
cd code/python/ch09 && pytest test_batch_client.py -v
```

测试覆盖了 18 个场景，包括创建批次、状态查询、JSONL 结果解析、取消操作、轮询等待、超时/过期/取消的错误处理，以及缓存请求工厂方法。

---

## 9.4 Node.js 实现

本章的 TypeScript 实现位于 `code/node/ch09/BatchClient.ts`，与 Python 端保持相同的协议级设计。

### 9.4.1 核心类设计

```typescript
import { BatchClient, MessageRequest } from "./BatchClient";

const client = new BatchClient("sk-ant-...");

// 创建批次
const batchId = await client.createBatch([
  {
    custom_id: "task-001",
    params: {
      model: "claude-haiku-3-5-20241022",
      max_tokens: 100,
      messages: [{ role: "user", content: "分析这段文本的情感..." }]
    }
  }
]);

// 同步等待完成
const results = await client.waitForCompletion(batchId, 30);
```

**`BatchClient` 公开 API（与 Python 端对称）：**

| 方法 | 返回值 | 说明 |
|------|--------|------|
| `createBatch(requests)` | `Promise<string>` | 创建新批次 |
| `getBatchStatus(batchId)` | `Promise<BatchInfo>` | 查询批次状态 |
| `getBatchResults(batchId)` | `Promise<BatchResult[]>` | 下载并解析 JSONL 结果 |
| `cancelBatch(batchId)` | `Promise<BatchInfo>` | 取消批次 |
| `listBatches(limit, afterId?)` | `Promise<BatchInfo[]>` | 列出所有批次 |
| `waitForCompletion(batchId, pollInterval?, maxWait?)` | `Promise<BatchResult[]>` | 轮询直到完成 |

**TypeScript 类型定义：**

```typescript
type BatchProcessingStatus = "in_progress" | "ended" | "canceled" | "expired";
type ResultType = "succeeded" | "errored" | "canceled" | "expired";

interface MessageRequest {
  custom_id: string;
  params: Record<string, unknown>;
}

interface BatchInfo {
  id: string;
  processing_status: BatchProcessingStatus;
  request_counts: Record<string, number>;
  created_at: string;
  ended_at: string;
  expires_at: string;
  results_url: string | null;
  raw: Record<string, unknown>;
}

interface BatchResult {
  custom_id: string;
  result_type: ResultType;
  message: Record<string, unknown> | null;
  error: Record<string, unknown> | null;
  raw: Record<string, unknown>;
}
```

### 9.4.2 Cache-Friendly 请求工厂

```typescript
const req = BatchClient.makeCacheableRequest({
  custom_id: "cached-001",
  model: "claude-sonnet-4-20250514",
  max_tokens: 500,
  user_message: "请分析这个文档的核心论点...",
  system_prompt: "你是一个学术论文审稿人...",
  cache_ttl: 3600  // 1 小时
});
```

运行测试验证：

```bash
cd code/node && npx vitest run ch09/
```

---

## 9.5 最佳实践

### 9.5.1 轮询策略

**指数退避（不推荐）：**

由于批次完成的准确时间不可预测，纯指数退避可能导致不必要的等待。

**固定间隔轮询（推荐）：**

```python
# 对于预计 1 小时内完成的小批次（< 1,000 请求）
poll_interval = 30  # 每 30 秒检查一次

# 对于大中批次（1,000-10,000 请求）
poll_interval = 60  # 每 1 分钟检查一次

# 对于大批次（> 10,000 请求）
poll_interval = 120  # 每 2 分钟检查一次
```

**自适应轮询（高级）：**

```python
def adaptive_poll(client, batch_id, initial_interval=30, min_interval=10, max_interval=300):
    """根据进度自我调整轮询间隔。"""
    interval = initial_interval
    prev_processed = 0

    while True:
        info = client.get_batch_status(batch_id)
        if info.processing_status != "in_progress":
            break

        total = sum(info.request_counts.values())
        processed = info.request_counts.get("succeeded", 0) + \
                   info.request_counts.get("errored", 0)
        remaining = total - processed

        if remaining == 0:
            interval = min_interval  # 即将完成，加速轮询
        elif processed > prev_processed:
            # 处理速度：调整至每处理 10% 检查一次
            interval = max(min_interval, min(max_interval, interval))
        else:
            interval = min(max_interval, interval * 1.5)  # 无进展，放慢

        prev_processed = processed
        time.sleep(interval)
```

### 9.5.2 错误处理：单请求错误 vs 批次级错误

关键在于理解两个错误层面：

**单请求错误（可恢复/可忽略）：**
- 某个请求参数错误（`invalid_request_error`）
- 某个请求触发安全过滤（`content_blocked`）
- 单请求不会影响同批次的其他请求

**批次级错误（需要人工介入）：**
- 整个批次在 24 小时内未完成（`expired`）
- 批次创建时的认证错误（401）
- 批次被意外取消

**推荐分类处理模式：**

```python
results = client.wait_for_completion(batch_id)

# 分类处理四种结果
succeeded = []
retryable = []
permanent_errors = []
canceled_or_expired = []

for r in results:
    if r.result_type == "succeeded":
        succeeded.append(r)
    elif r.result_type == "errored":
        error_type = r.error.get("type", "")
        if error_type in ("overloaded_error", "internal_error"):
            retryable.append(r)  # 可以重新提交
        else:
            permanent_errors.append(r)  # 参数错误等需要修复
    elif r.result_type in ("canceled", "expired"):
        canceled_or_expired.append(r)

# 重新提交可重试的请求
if retryable:
    retry_requests = [
        # 从原始请求列表中查找对应 custom_id 的请求重新提交
    ]
    new_batch_id = client.create_batch(retry_requests)

# 记录永久错误用于调试
for r in permanent_errors:
    logger.error(f"Batch request {r.custom_id} failed: {r.error}")
```

### 9.5.3 成本优化清单

1. **模型选择**：简单任务使用 Haiku（便宜 10-60 倍），复杂推理使用 Sonnet 或 Opus
2. **max_tokens 精确设置**：不像实时场景那样可以宽松估算——20 个 token 的浪费乘以 100,000 个请求就是 2M 输出 token 的浪费
3. **Prompt Caching 叠加**：对于高重复前缀的场景，组合缓存可将输入成本降至基准的 5%
4. **先跑 Dry Run**：用单个实时 API 调用验证请求格式，避免 100,000 个请求因格式错误全部失败
5. **分批次处理**：超大数据集分成多个 10,000-50,000 请求的中等批次，便于管理、监控和重试
6. **利用 29 天结果保留期**：结果不需要立即处理，可以在闲暇时段逐步消费

### 9.5.4 生产部署检查清单

- [ ] **幂等性**：`custom_id` 的唯一性由调用方保证——如果重复提交同一批数据，应生成新的 `custom_id`
- [ ] **超时处理**：24 小时后未完成的请求会过期且不计费，需要检测并重新提交
- [ ] **结果 29 天窗口**：及时下载和处理结果，29 天后数据不再可用
- [ ] **速率限制**：批次创建也有速率限制——大容量用户应实现渐进式提交
- [ ] **消费限额**：由于并发处理的特性，批次可能略微超过 Workspace 消费限额
- [ ] **部分失败处理**：大批次几乎总有少数失败——建立完善的重试和错误分类机制
- [ ] **监控与告警**：对批次完成时间、成功率、错误率设置监控面板
- [ ] **成本追踪**：使用 `usage` 字段（在 `succeeded` 结果中）精确追踪每个请求的实际 Token 消耗

---

## 9.6 自测题

**题目 1（理论）**：描述 MessageBatch 的四种 `processing_status` 状态及其转换条件。如果一个批次中 500 个请求成功、3 个参数错误、2 个因取消未处理，该批次的 `processing_status` 是什么？`request_counts` 的各项数值是多少？

**题目 2（理论）**：Batch API 中四种 `result_type`（`succeeded`、`errored`、`canceled`、`expired`）的计费规则分别是什么？如果批次创建了 1,000 个请求，其中 950 个 succeeded、30 个 errored、20 个 expired，使用 Claude Haiku 3.5（每请求约 100 输入 + 30 输出 token），总费用是多少？

**题目 3（编码）**：使用 `BatchClient` 编写一个函数 `retry_failed_requests(client, original_requests, batch_id)`，该函数：
- 获取指定批次的结果
- 筛选出因 `overloaded_error` 或 `internal_error` 而失败的请求
- 用这些请求创建一个新批次
- 返回新批次的 ID 和重试请求数量

```python
from batch_client import BatchClient, MessageRequest

def retry_failed_requests(
    client: BatchClient,
    original_requests: list[MessageRequest],
    batch_id: str
) -> tuple[str, int]:
    """重试批次中因临时错误而失败的请求。"""
    # 你的实现
    pass
```

**题目 4（编码）**：编写一个函数 `estimate_batch_savings`，输入为请求数量 `n`、每请求平均输入 token 数 `input_tokens`、每请求平均输出 token 数 `output_tokens`、模型名称 `model`，返回实时 API 成本、Batch API 成本和节约百分比（保留一位小数）。支持至少三种模型的价格查询。正确处理 Batch API 的 50% 折扣。

```python
def estimate_batch_savings(
    n: int,
    input_tokens: int,
    output_tokens: int,
    model: str
) -> dict:
    """估算批次处理的成本节约。"""
    # 你的实现
    pass
```

---

> **本章小结：** Batch API 是以时间换金钱的异步批量处理协议。通过接受最多 24 小时的延迟，你可以获得 50% 的成本折扣和最高 100,000 请求的吞吐能力。理解 MessageBatch 的生命周期（in_progress -> ended / canceled / expired）和四种单请求结果类型（succeeded / errored / canceled / expired）是正确使用的基础。将 Prompt Caching 与 Batch API 组合使用可以进一步将输入成本降至基准的 5%-50%。记住核心判断法则：**高吞吐量离线任务用 Batch，用户在线等待用实时 API。**
