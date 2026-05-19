# 附录 A：API 快速参考表

> Anthropic API 全部端点、请求/响应字段、错误类型速查手册

---

## A.1 基础信息

| 项目 | 值 |
|------|-----|
| **Base URL** | `https://api.anthropic.com` |
| **Messages 端点** | `POST /v1/messages` |
| **Batch 端点** | `POST /v1/messages/batches` |
| **Memory Stores 端点** | `POST /v1/memory_stores` |
| **Dreams 端点** | `POST /v1/dreams` |
| **API 版本头** | `anthropic-version: 2023-06-01` |
| **认证方式一** | `x-api-key: sk-ant-api03-...` |
| **认证方式二** | `Authorization: Bearer sk-ant-api03-...` |
| **Content-Type** | `application/json` |

---

## A.2 Messages API（POST /v1/messages）

### A.2.1 请求参数

| 字段 | 类型 | 必填 | 说明 |
|------|------|:--:|------|
| `model` | string | **是** | 模型标识符，1-256 字符。如 `"claude-sonnet-4-6"`、`"claude-opus-4-7"` |
| `max_tokens` | integer | **是** | 生成的最大 token 数（>= 1）。不同模型有不同上限（32K-128K） |
| `messages` | object[] | **是** | 对话消息数组（最多 100,000 条），user/assistant 交替 |
| `messages[].role` | string | **是** | `"user"` 或 `"assistant"` |
| `messages[].content` | string \| object[] | **是** | 字符串（简写形式）或 Content Block 数组 |
| `system` | string \| object[] | 否 | 系统提示。字符串（简写）或 Text Block 数组（支持 cache_control） |
| `temperature` | number | 否 | 控制随机性。默认 1.0。范围 0.0-1.0。接近 0 更确定，1.0 最富创造性 |
| `top_p` | number | 否 | 核采样阈值。范围 0.0-1.0。从累积概率达到此值的 token 中采样 |
| `top_k` | integer | 否 | 仅从前 K 个最高概率 token 中采样（>= 0） |
| `stop_sequences` | string[] | 否 | 自定义停止序列。模型生成到这些文本时立即停止 |
| `stream` | boolean | 否 | 启用 SSE 流式响应。默认 false |
| `metadata` | object | 否 | 请求元数据，支持 `user_id` 子字段（最大 256 字符，须为不透明标识符） |
| `tools` | object[] | 否 | 工具定义数组（详见 A.2.3） |
| `tool_choice` | object | 否 | 工具选择策略。默认 `{"type": "auto"}` |
| `thinking` | object | 否 | Extended Thinking 配置。`{"type": "enabled", "budget_tokens": N}` 或 `{"type": "adaptive"}` |
| `service_tier` | string | 否 | 服务层级：`"auto"`（优先预留容量）或 `"standard_only"` |
| `output_config` | object | 否 | Structured Outputs 配置（详见 A.2.4） |

### A.2.2 响应字段

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | string | 消息唯一标识符（`msg_01X...`） |
| `type` | string | 固定值 `"message"` |
| `role` | string | 固定值 `"assistant"` |
| `content` | object[] | Content Block 数组（text、tool_use、thinking 等） |
| `model` | string | 实际使用的模型 ID |
| `stop_reason` | string | 停止原因（见下表） |
| `stop_sequence` | string \| null | 触发的停止序列（如有） |
| `usage` | object | Token 使用统计 |

**stop_reason 枚举值：**

| 值 | 含义 |
|------|------|
| `end_turn` | 模型自然结束回复 |
| `max_tokens` | 达到 `max_tokens` 限制，输出被截断 |
| `stop_sequence` | 遇到自定义停止序列 |
| `tool_use` | 模型请求调用工具（等待客户端返回 tool_result） |
| `pause_turn` | 长回合暂停（Beta） |
| `refusal` | 安全策略触发拒绝 |

**usage 对象字段：**

| 字段 | 类型 | 说明 |
|------|------|------|
| `input_tokens` | integer | 消耗的输入 token 总数 |
| `output_tokens` | integer | 消耗的输出 token 总数 |
| `cache_creation_input_tokens` | integer | 本次新写入缓存的 token 数 |
| `cache_read_input_tokens` | integer | 本次从缓存读取的 token 数 |

### A.2.3 工具定义格式

| 字段 | 类型 | 必填 | 说明 |
|------|------|:--:|------|
| `name` | string | **是** | 工具唯一名称，1-64 字符，仅字母数字下划线连字符 |
| `description` | string | 否 | 工具功能描述（强烈建议提供） |
| `input_schema` | object | **是** | JSON Schema 格式的输入参数定义。必须 `type: "object"` |
| `strict` | boolean | 否 | 启用 Strict Tool Use（grammar-constrained sampling） |
| `defer_loading` | boolean | 否 | 延迟加载（需配合 Tool Search Tool） |
| `allowed_callers` | string[] | 否 | 允许调用的上下文列表（`"direct"` 或 `"code_execution_20260120"`） |
| `input_examples` | object[] | 否 | 工具使用示例（1-5 个） |

**tool_choice 参数格式：**

| 值 | 说明 |
|------|------|
| `{"type": "auto"}` | Claude 自动判断（默认） |
| `{"type": "any"}` | 必须使用至少一个工具 |
| `{"type": "tool", "name": "X"}` | 必须使用指定工具 |
| `{"type": "auto", "disable_parallel_tool_use": true}` | 自动模式，最多一个工具 |
| `{"type": "any", "disable_parallel_tool_use": true}` | 强制模式，恰好一个工具 |

### A.2.4 Structured Outputs 配置（output_config）

| 字段 | 类型 | 必填 | 说明 |
|------|------|:--:|------|
| `output_config` | object | 否 | 输出配置容器 |
| `output_config.format` | object | 是 | 输出格式描述 |
| `output_config.format.type` | string | 是 | 固定值 `"json_schema"` |
| `output_config.format.schema` | object | 是 | JSON Schema 对象（Draft 2020-12 子集，顶层必须 `type: "object"`） |
| `output_config.effort` | string | 否 | 约束执行等级：`"low"`、`"medium"`（默认）、`"high"`、`"xhigh"`、`"max"` |

### A.2.5 Content Block 类型速查（请求）

| Block 类型 | 简要结构 | 使用场景 |
|-----------|---------|---------|
| `text` | `{"type":"text", "text":"...", "cache_control":...}` | 纯文本内容 |
| `image` (base64) | `{"type":"image", "source":{"type":"base64", "media_type":"image/png", "data":"..."}}` | 本地图像 |
| `image` (URL) | `{"type":"image", "source":{"type":"url", "url":"https://..."}}` | 网络图像 |
| `tool_use` | `{"type":"tool_use", "id":"toolu_...", "name":"...", "input":{}}` | 助手发出的工具调用（仅响应） |
| `tool_result` | `{"type":"tool_result", "tool_use_id":"toolu_...", "content":"...", "is_error":false}` | 工具执行结果（仅请求） |
| `thinking` | `{"type":"thinking", "thinking":"...", "signature":"..."}` | 扩展思考内容（仅响应） |
| `redacted_thinking` | `{"type":"redacted_thinking", "data":"..."}` | 被安全加密的思考内容（仅响应） |

### A.2.6 Image Block 支持的格式与限制

| 格式 | MIME Type | 说明 |
|------|-----------|------|
| JPEG | `image/jpeg` | 最适合照片 |
| PNG | `image/png` | 无损，适合图表和截图 |
| GIF | `image/gif` | 动图仅首帧被分析 |
| WebP | `image/webp` | 现代格式 |

- base64 编码图像建议不超过 5 MB
- URL 引用图像建议不超过 10 MB
- 大于 1568 像素（任意维度）的图像被缩放至长边 1568 像素
- Token 消耗约 = `(width × height) / 750`

---

## A.3 Streaming API（SSE 事件类型）

### A.3.1 SSE 事件完整列表

| 事件类型 | 方向 | 关键字段 | 说明 |
|----------|------|---------|------|
| `message_start` | Server→Client | `message.id`, `message.model`, `message.usage` | 消息开始，content 数组为空 |
| `content_block_start` | Server→Client | `index`, `content_block` | 内容块开始 |
| `content_block_delta` | Server→Client | `index`, `delta` | 内容块增量（最高频事件） |
| `content_block_stop` | Server→Client | `index` | 内容块结束 |
| `message_delta` | Server→Client | `delta.stop_reason`, `usage.output_tokens` | 消息级增量更新 |
| `message_stop` | Server→Client | （无额外数据） | 消息流结束 |
| `ping` | Server→Client | （无额外数据） | 心跳保活 |
| `error` | Server→Client | `error.type`, `error.message` | 流内错误 |

### A.3.2 Delta 类型

| Delta 类型 | 包含字段 | 说明 |
|-----------|---------|------|
| `text_delta` | `text: string` | 文本增量 |
| `thinking_delta` | `thinking: string` | 思考过程增量 |
| `signature_delta` | `signature: string` | 思考块的加密签名 |
| `input_json_delta` | `partial_json: string` | 工具调用参数的增量 JSON |
| `citations_delta` | `citation: Citation` | 引用信息增量 |

---

## A.4 Batch API

### A.4.1 端点列表

| 方法 | 端点 | 说明 |
|------|------|------|
| POST | `/v1/messages/batches` | 创建新批次 |
| GET | `/v1/messages/batches/{batch_id}` | 查询批次状态 |
| GET | `/v1/messages/batches/{batch_id}/results` | 下载 JSONL 结果 |
| POST | `/v1/messages/batches/{batch_id}/cancel` | 取消批次 |
| GET | `/v1/messages/batches?limit=&after_id=` | 列出所有批次 |

### A.4.2 批次请求格式

| 字段 | 类型 | 必填 | 说明 |
|------|------|:--:|------|
| `requests` | object[] | **是** | 请求数组（最多 100,000 条或 256 MB） |
| `requests[].custom_id` | string | **是** | 客户端定义的唯一标识符。批次内必须唯一 |
| `requests[].params` | object | **是** | 标准 Messages API 参数（model, max_tokens, messages, 等） |

### A.4.3 批次状态转换

| 状态 | 含义 | 可执行操作 |
|------|------|-----------|
| `in_progress` | 批次处理中 | 查询状态、取消 |
| `ended` | 所有请求已处理完毕 | 下载结果 |
| `canceled` | 用户手动取消 | 下载已完成请求的结果 |
| `expired` | 24 小时 SLA 到期 | 仅能查看状态 |

### A.4.4 单请求结果类型

| 结果类型 | 含义 | 是否计费 |
|---------|------|:--:|
| `succeeded` | 请求成功处理 | **是** |
| `errored` | 请求处理失败（含 error 对象） | **否** |
| `canceled` | 批次取消，请求未发送 | **否** |
| `expired` | 24 小时到期，请求未发送 | **否** |

---

## A.5 Memory API

### A.5.1 Memory Store CRUD

| 操作 | HTTP 方法 | 端点 |
|------|-----------|------|
| 创建 Store | POST | `/v1/memory_stores` |
| 列举 Store | GET | `/v1/memory_stores` |
| 获取 Store | GET | `/v1/memory_stores/{id}` |
| 更新 Store | POST | `/v1/memory_stores/{id}` |
| 归档 Store | POST | `/v1/memory_stores/{id}/archive` |
| 删除 Store | DELETE | `/v1/memory_stores/{id}` |

### A.5.2 Memory CRUD

| 操作 | 说明 |
|------|------|
| 创建 | `client.beta.memory_stores.memories.create(store_id, path, content)` |
| 写入 (Upsert) | `client.beta.memory_stores.memories.write(store_id, path, content)` |
| 读取 | `client.beta.memory_stores.memories.retrieve(memory_id, store_id)` |
| 列举 | `client.beta.memory_stores.memories.list(store_id, path_prefix, ...)` |
| 更新 | `client.beta.memory_stores.memories.update(memory_id, store_id, content, ...)` |
| 删除 | `client.beta.memory_stores.memories.delete(memory_id, store_id)` |

### A.5.3 Memory Store 限制

| 限制项 | 数值 |
|--------|------|
| 每组织 Store 数量 | 1,000 |
| 每 Store Memory 数量 | 2,000 |
| 每 Store 存储容量 | 100 MB |
| 每 Memory 大小上限 | 100 KB（约 25K tokens） |
| 每 Session 可挂载 Store | 8 个 |
| Memory Version 保留期 | 30 天 |

### A.5.4 Dreams API

| 端点 | 方法 | 说明 |
|------|------|------|
| `/v1/dreams` | POST | 启动 Dreaming 作业 |

**Dreaming 请求参数：**

| 字段 | 类型 | 必填 | 说明 |
|------|------|:--:|------|
| `inputs` | object[] | **是** | 输入源：`memory_store` 类型（必需）和 `sessions` 类型（可选，上限 100 个会话） |
| `model` | string | **是** | 用于 Dreaming 的模型（`claude-opus-4-7` 或 `claude-sonnet-4-6`） |
| `instructions` | string | 否 | 指导 Dreaming 关注的重点（上限 4,096 字符） |

**所需 Beta Header：** `managed-agents-2026-04-01, dreaming-2026-04-21`

---

## A.6 错误类型速查表

| HTTP 状态码 | 错误类型 | 触发场景 | 重试策略 |
|:----------:|---------|---------|---------|
| 400 | `invalid_request_error` | 请求体格式错误、缺少必填字段、参数值不合法、Schema 编译失败 | **不重试** —— 修复请求后重发 |
| 401 | `authentication_error` | API Key 无效、过期或缺失 | **不重试** —— 检查 Key |
| 403 | `permission_error` | API Key 无权访问请求的资源或模型 | **不重试** —— 检查权限 |
| 404 | `not_found_error` | 模型名称错误或资源不存在 | **不重试** —— 检查标识符 |
| 413 | `request_too_large` | Messages: 超过 32MB；Batch: 超过 256MB | **不重试** —— 压缩或分割请求 |
| 429 | `rate_limit_error` | 超过 RPM/TPM 限制 | **重试** —— `Retry-After` + 指数退避 |
| 500 | `api_error` | Anthropic 内部服务器错误 | **重试** —— 指数退避 |
| 529 | `overloaded_error` | Anthropic 服务过载 | **重试** —— `Retry-After` + 更长退避 |

**错误响应格式：**

```json
{
  "type": "error",
  "error": {
    "type": "authentication_error",
    "message": "invalid x-api-key"
  }
}
```

| 字段 | 类型 | 必填 | 说明 |
|------|------|:--:|------|
| `type` | string | **是** | 固定值 `"error"` |
| `error.type` | string | **是** | 错误类型（上表） |
| `error.message` | string | **是** | 人类可读的错误描述 |

---

## A.7 速率限制响应头

| Header | 说明 |
|--------|------|
| `retry-after` | 建议等待的秒数（429 时） |
| `anthropic-ratelimit-requests-limit` | RPM 上限 |
| `anthropic-ratelimit-requests-remaining` | 当前窗口剩余请求数 |
| `anthropic-ratelimit-requests-reset` | RPM 计数器重置时间（ISO 8601） |
| `anthropic-ratelimit-tokens-limit` | TPM 上限 |
| `anthropic-ratelimit-tokens-remaining` | 当前窗口剩余 token 数 |
| `anthropic-ratelimit-tokens-reset` | TPM 计数器重置时间（ISO 8601） |
| `anthropic-ratelimit-input-tokens-remaining` | 剩余输入 token 配额 |
| `anthropic-ratelimit-output-tokens-remaining` | 剩余输出 token 配额 |

---

## A.8 Prompt Caching 参数

| 参数 | 类型 | 必填 | 说明 |
|------|------|:--:|------|
| `cache_control.type` | string | **是** | 固定值 `"ephemeral"` |
| `cache_control.scope` | string | 否 | 缓存共享范围：`"global"`（跨用户）或省略（组织级隔离） |
| `cache_control.ttl` | string | 否 | 缓存存活时间：默认 `"5m"`，限定用户可用 `"1h"` |

**约束：** 最小可缓存 1,024 tokens（Sonnet/Opus）或 2,048 tokens（Haiku）。最多 4 个断点/请求。

---

## A.9 Extended Thinking 参数

| 参数 | 类型 | 必填 | 说明 |
|------|------|:--:|------|
| `thinking.type` | string | **是** | `"enabled"`（启用）或 `"adaptive"`（自适应） |
| `thinking.budget_tokens` | integer | 是（enabled 时） | 思考 token 预算，最小 1,024。`max_tokens` 必须大于此值 |
| `thinking.display` | string | 否 | 思考可见性控制 |

---

## A.10 Authentication

| 方式 | Header | 推荐场景 |
|------|--------|---------|
| `x-api-key` | `x-api-key: sk-ant-api03-...` | **推荐**。官方 SDK 默认，语义清晰，日志系统自动遮蔽 |
| Bearer Token | `Authorization: Bearer sk-ant-api03-...` | 兼容标准 API 网关和 OAuth 中间件 |

---

## A.11 请求/响应大小限制

| 限制项 | 数值 |
|--------|------|
| Messages 请求体上限 | 32 MB |
| Batch API 请求体上限 | 256 MB |
| 消息数组最大长度 | 100,000 条 |
| 单请求最大 tool_use 块数 | 约 100 个（受 token 限制） |
| cache_control 最大断点数 | 4 个 / 请求 |
| 单批次最大请求数 | 100,000 条 |
| Batch 结果保留期 | 29 天（从创建时间算起） |
