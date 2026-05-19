# 第5章：Streaming 与 Extended Thinking

> 实时交互与深度推理 —— 流式响应与扩展思考协议全解

---

## 5.1 概念全景

### 5.1.1 SSE 协议在 Anthropic 生态中的定位

HTTP 协议本质上是"请求-响应"模型。客户端发出一个请求，服务器返回一个响应，连接关闭。这种模式对于静态文档、REST API 查询等场景非常高效，但对于生成式 AI 却有着致命的用户体验缺陷。

想象一下，你向 Claude 提了一个复杂的问题，它可能需要 30 秒才能生成完整个回答。在传统的非流式模式下，你盯着空白页面等待 30 秒，然后一次性看到全部回答。这种体验堪比 1998 年的拨号上网。

Server-Sent Events（SSE）协议改变了这一切。SSE 是 HTTP 协议的一个标准扩展（定义于 HTML Standard 的 Server-sent events 章节），允许服务器在单个 HTTP 连接上持续推送数据到客户端。它的核心理念是：不等待全部数据准备好，而是"准备好多少，发送多少"。

在 Anthropic 生态中，SSE 是流式响应的底层传输协议。当你设置 `"stream": true` 发送请求时，Anthropic API 不再返回一个完整的 JSON 响应体，而是一个 `text/event-stream` 类型的流。这个流由一系列命名事件组成，每个事件携带着增量数据——一个 token、一个工具调用片段、一个思考过程块。

### 5.1.2 流式 vs 非流式：两种交互范式的本质区别

| 维度 | 非流式 (Non-Streaming) | 流式 (Streaming) |
|------|----------------------|-------------------|
| 响应方式 | 完整生成后一次性返回 | 逐 token 增量推送 |
| 首字节时间 (TTFB) | 可能 10-30 秒 | 通常 200-500 毫秒 |
| 用户感知 | "等待" | "边看边生成" |
| 内存模型 | 完整响应对象在内存中 | 事件流，可按需丢弃 |
| 取消机制 | 无法中途取消 | 关闭连接即可中断 |
| 适用场景 | 批处理、后台任务、短回答 | 聊天界面、代码生成、实时渲染 |
| API 调用 | `client.messages.create(stream=False)` | `client.messages.create(stream=True)` 或 `client.messages.stream()` |

首字节时间（TTFB, Time To First Byte）是衡量交互体验的核心指标。研究表明，用户对响应速度的主观感知在 100ms 以内为"即时"，100-300ms 为"轻微延迟"，超过 1s 则明显感到"等待"。流式响应将 TTFB 从 10-30 秒降低到几百毫秒——因为第一个 token 生成即可开始发送，无需等待全部内容完成。

但流式并非毫无代价。它引入了事件解析复杂度、网络断连风险、累积状态管理等问题。非流式虽然慢，但协议简单——一个完整的 JSON 对象，没有中间状态，适合批处理和需要完整结构的场景。

### 5.1.3 Extended Thinking：推理的元认知层

Extended Thinking（扩展思考）是 Anthropic 为 Claude 引入的一项独特能力。它与流式不属于同一个维度——它改变的是**内容的性质**，而不是**传输的方式**。

在标准模式下，Claude 的"思考"是隐式的——你只看到最终回答，不知道 AI 在生成过程中经历了怎样的推理过程。Extended Thinking 将这个过程显式化：Claude 在给出最终答案之前，先生成一个"思考块"（thinking block），记录其内部推理过程。

这个思考块具有以下特性：

1. **独立性**：思考块是独立的内容块（content block），与文本块（text block）分离
2. **可选可见性**：开发者可以决定是否向用户展示思考过程
3. **签名验证**：每个思考块附带一个加密签名（signature），用于验证思考内容的真实性
4. **Token 预算**：通过 `budget_tokens` 参数控制思考的"深度"——预算越大，推理越充分
5. **自适应模式**：使用 `type: "adaptive"` 让模型自行决定思考深度

从协议角度看，Extended Thinking 的流式传输与普通文本流完全相同——同样是 SSE 事件，只是 delta 类型从 `text_delta` 变为 `thinking_delta`，并在结束时附加 `signature_delta`。

### 5.1.4 本章学习路线

本章将带你从三个层次深入理解 Streaming 与 Extended Thinking：

- **协议层**：SSE 协议的完整 RFC 规范，Anthropic 的 7 种事件类型的精确语义
- **实现层**：用 Python 和 TypeScript 从零构建 SSE 解析器、流处理器、思考处理器——不依赖任何 SSE 库
- **工程层**：何时选用流式、如何优化思考预算、签名验证的安全实践

---

## 5.2 协议规范

### 5.2.1 SSE 协议基础

SSE（Server-Sent Events）是 HTML Standard 的一部分，正式定义于 [WHATWG HTML Living Standard 的 9.2 章](https://html.spec.whatwg.org/multipage/server-sent-events.html)。它的设计哲学是：尽可能简单，用 HTTP 做传输，用文本做编码。

#### 5.2.1.1 HTTP 层面的约定

一个 SSE 连接是一个标准的 HTTP GET 或 POST 请求，但服务器返回的响应具有以下特征：

```
HTTP/1.1 200 OK
Content-Type: text/event-stream
Cache-Control: no-cache
Connection: keep-alive
Transfer-Encoding: chunked
```

关键响应头：
- `Content-Type: text/event-stream` —— 这是 SSE 的 MIME 类型，浏览器和中间代理据此识别流
- `Cache-Control: no-cache` —— 禁止缓存，确保客户端始终获取实时数据
- `Connection: keep-alive` —— 保持连接不关闭
- 响应体使用 `Transfer-Encoding: chunked` —— 允许服务器逐块发送数据而不预先声明总长度

#### 5.2.1.2 事件格式（RFC 规范）

SSE 的数据格式是纯文本的。每个"消息"由一个或多个字段组成，消息之间用空行（`\n\n`）分隔。

SSE 定义了四种标准字段：

```
field-name: field-value\n
```

**标准字段：**

| 字段名 | 说明 | 是否必需 |
|--------|------|---------|
| `data` | 事件数据。可以有多个 `data` 行，最终合并为一行 | 是（否则事件无数据） |
| `event` | 事件类型名称。省略时默认为 `"message"` | 否 |
| `id` | 事件 ID，用于断线重连时的 `Last-Event-ID` | 否 |
| `retry` | 服务器建议的重连间隔（毫秒） | 否 |

**解析规则（RFC 原文语义）：**

1. 流被分割为以空行（`\n\n`）分隔的消息块
2. 每个消息块内，每行是一个字段。格式为 `field:value`，冒号后可以有可选的空格
3. 以冒号 `:` 开头的行是注释，客户端应忽略
4. 如果字段名为空，整行被忽略
5. 如果字段值为空，该字段被设置为空字符串
6. 如果字段名是 `data`，值被追加到当前消息的 data buffer，追加时用 `\n` 分隔
7. 如果字段名是 `event`，值设置事件类型
8. 如果字段名是 `id`，值设置事件 ID（注意：id 字段不包含 `\0` 字符）
9. 如果字段名是 `retry`，且值为有效整数，更新重连间隔
10. 消息块结束时（遇到空行），触发一个事件

**示例：**

```
event: message_start
data: {"type": "message_start", "message": {"id": "msg_01...", ...}}

event: content_block_delta
data: {"type": "content_block_delta", "index": 0, "delta": {"type": "text_delta", "text": "Hello"}}

event: ping
data: {"type": "ping"}
```

#### 5.2.1.3 与 WebSocket 的对比

| 特性 | SSE | WebSocket |
|------|-----|-----------|
| 通信方向 | 单向（服务器 → 客户端） | 双向（全双工） |
| 协议基础 | HTTP/1.1 或 HTTP/2 | 独立协议（ws:// 或 wss://） |
| 自动重连 | 浏览器内置，`Last-Event-ID` | 需手动实现 |
| 二进制数据 | 不支持（仅 UTF-8 文本） | 支持 |
| 防火墙友好性 | 高（标准 HTTP 端口） | 较低（需要 Upgrade 握手） |
| 实现复杂度 | 极低 | 中等 |
| 适用场景 | 实时推送（股票、通知、LLM 流） | 聊天、游戏、协作编辑 |

对于 LLM API 流式响应，SSE 是天然的最佳选择：客户端发送请求，服务器持续推送 tokens，数据流是单向的，且 HTTP 协议的兼容性无与伦比。

### 5.2.2 Anthropic 流式事件类型

Anthropic API 的流式响应遵循标准 SSE 格式，但定义了自己的一组事件类型。每个 SSE 事件包含一个 `event:` 行指定事件类型，以及一个 `data:` 行包含 JSON 数据。JSON 数据中也有一个 `type` 字段，与事件名称一致。

#### 5.2.2.1 事件类型总览

| 事件类型 | 方向 | 语义 | 关键字段 |
|----------|------|------|----------|
| `message_start` | 服务器→客户端 | 消息开始。包含完整的 Message 对象，但 `content` 数组为空 | `message.id`, `message.model`, `message.usage` |
| `content_block_start` | 服务器→客户端 | 内容块开始。一个消息可有多个内容块（文本块、工具调用块、思考块） | `index`, `content_block` (含 `type` 字段) |
| `content_block_delta` | 服务器→客户端 | 内容块增量数据。这是流中频率最高的事件，每个 token 触发一次 | `index`, `delta` (含 `type` 和具体数据) |
| `content_block_stop` | 服务器→客户端 | 内容块结束。标志着该 index 的内容块已完整 | `index` |
| `message_delta` | 服务器→客户端 | 消息级别增量。包含 `stop_reason` 和累计 `usage` | `delta.stop_reason`, `usage.output_tokens` |
| `message_stop` | 服务器→客户端 | 消息流结束。标志着整个响应已完成 | （无额外数据） |
| `ping` | 服务器→客户端 | 心跳保活。防止连接因空闲被代理服务器关闭 | （无额外数据） |
| `error` | 服务器→客户端 | 流内错误。可能在流的任何位置出现 | `error.type`, `error.message` |

#### 5.2.2.2 事件流顺序

一个典型的 Anthropic 流式响应的完整事件序列如下：

```
1. message_start           ← 消息开始，包含 Message 对象（content 为空）
2. content_block_start     ← 内容块 0 开始（通常是 text 类型）
3. content_block_delta     ← 第一个 token
4. content_block_delta     ← 第二个 token
   ...（可能穿插 ping 事件）
N. content_block_delta     ← 最后一个 token
N+1. content_block_stop    ← 内容块 0 结束
N+2. [content_block_start] ← 如果有第二个内容块（如 tool_use），重复 2-4
N+3. message_delta         ← 消息级更新（stop_reason, usage）
N+4. message_stop          ← 流结束
```

#### 5.2.2.3 各事件类型详述

**`message_start`**

```
event: message_start
data: {"type": "message_start", "message": {"id": "msg_1nZdL29xx5MUA1yADyHTEsnR8uuvGzszyY", "type": "message", "role": "assistant", "content": [], "model": "claude-sonnet-4-5-20250929", "stop_reason": null, "stop_sequence": null, "usage": {"input_tokens": 25, "output_tokens": 1}}}
```

`message_start` 是流中的第一个事件。它携带一个完整的 `Message` 对象，但 `content` 数组为空（`[]`）。`usage` 字段显示了此时的 token 统计——`input_tokens` 已经确定，`output_tokens` 初始为 1（表示流的开始标记）。

注意：`stop_reason` 在此事件中为 `null`，因为消息尚未完成。最终值将在 `message_delta` 中给出。

**`content_block_start`**

```
event: content_block_start
data: {"type": "content_block_start", "index": 0, "content_block": {"type": "text", "text": ""}}
```

`content_block_start` 宣告一个新的内容块开始。关键字段：

- `index`（整数）：该内容块在最终 Message 的 `content` 数组中的索引，从 0 开始
- `content_block`（对象）：内容块的初始值。对于文本块，`text` 为空字符串 `""`；对于思考块，`thinking` 为空字符串；对于工具调用块，包含 `id`、`name` 和空的 `input`

内容块类型由 `content_block.type` 区分，可能的值为：
- `"text"` —— 文本内容块
- `"thinking"` —— 扩展思考内容块
- `"redacted_thinking"` —— 被安全系统加密的思考内容块（仅 Claude 3.7 Sonnet）
- `"tool_use"` —— 工具调用内容块
- `"server_tool_use"` —— 服务端工具调用（Beta）

**`content_block_delta`**

```
event: content_block_delta
data: {"type": "content_block_delta", "index": 0, "delta": {"type": "text_delta", "text": "Hello"}}
```

`content_block_delta` 是流中最核心的事件——每个 token 生成时触发一次。关键字段：

- `index`（整数）：指向之前 `content_block_start` 声明的索引
- `delta`（对象）：增量数据，其结构由 `delta.type` 决定

Delta 类型：

| Delta 类型 | 包含字段 | 说明 |
|-----------|---------|------|
| `text_delta` | `text: string` | 文本增量（一个或数个 tokens） |
| `thinking_delta` | `thinking: string` | 思考过程增量 |
| `signature_delta` | `signature: string` | 思考块的加密签名 |
| `input_json_delta` | `partial_json: string` | 工具调用参数的增量 JSON 片段 |
| `citations_delta` | `citation: Citation` | 引用信息增量 |

**`content_block_stop`**

```
event: content_block_stop
data: {"type": "content_block_stop", "index": 0}
```

`content_block_stop` 标志着索引为 `index` 的内容块已完整。此时可以将所有该块的增量拼接为完整内容。

**`message_delta`**

```
event: message_delta
data: {"type": "message_delta", "delta": {"stop_reason": "end_turn", "stop_sequence": null}, "usage": {"output_tokens": 15}}
```

`message_delta` 在最后一个内容块完成后发送，提供消息级别的最终更新：

- `delta.stop_reason`：停止原因，可能的值包括：
  - `"end_turn"` —— 自然结束
  - `"max_tokens"` —— 达到 max_tokens 上限
  - `"stop_sequence"` —— 触发了自定义停止序列
  - `"tool_use"` —— 模型请求调用工具
  - `"pause_turn"` —— 长回合暂停（Beta）
  - `"refusal"` —— 安全策略触发拒绝
- `delta.stop_sequence`：触发的停止序列字符串（如有）
- `usage`：最终的 token 使用量统计。注意 `usage.output_tokens` 是累计值，包含了所有思考 tokens 和文本 tokens

**`message_stop`**

```
event: message_stop
data: {"type": "message_stop"}
```

`message_stop` 是流中的最后一个事件。它没有多余数据——仅仅是一个信号，表示完整的 Message 对象已经可以构建。

**`ping`**

```
event: ping
data: {"type": "ping"}
```

`ping` 事件是 keepalive 机制。由于 SSE 连接可能长时间空闲（尤其是在 Extended Thinking 模式下，模型可能"沉思"数秒），中间代理（负载均衡器、Nginx 等）可能因超时关闭连接。`ping` 事件定期发送以保持连接活跃。

解析器必须正确处理并忽略 `ping` 事件——它们不携带任何应用层语义。

**`error`**

```
event: error
data: {"type": "error", "error": {"type": "overloaded_error", "message": "Overloaded"}}
```

`error` 事件可能在流的任何时刻出现——甚至在 `message_start` 之前。常见场景：

- `overloaded_error`（对应 HTTP 529）—— 服务过载
- `rate_limit_error`（对应 HTTP 429）—— 速率限制
- 流中异常中断

当收到 `error` 事件时，应立即停止处理流，并向用户展示适当的错误信息。

### 5.2.3 `text_stream` vs `message_stream` vs 原始事件

Anthropic SDK 提供了三种层次的流式抽象：

| 抽象层 | Python SDK | TypeScript SDK | 说明 |
|--------|-----------|----------------|------|
| 原始事件流 | `for event in stream:` | `for await (const event of stream)` | 直接访问 `message_start`、`content_block_delta` 等原始 SSE 事件 |
| 文本流 | `for text in stream.text_stream:` | `stream.on('text', fn)` | 仅接收文本增量（过滤所有非文本事件和工具调用） |
| 消息流 | `stream.get_final_message()` | `await stream.finalMessage()` | 累积所有事件，构建完整的 Message 对象 |

**原始事件流** 提供最大灵活性，适合需要精确控制事件处理的场景——例如自定义 UI 渲染、多模态内容处理、工具调用实时状态更新。

**文本流** 是最简洁的抽象。它在内部过滤 `content_block_delta` 事件中 `delta.type == "text_delta"` 的部分，只返回纯文本增量。适合聊天界面等纯文本场景。

**消息流** 在流结束后返回完整的 Message 对象，包含 token 使用量、停止原因、完整内容块列表。内存占用较高，但使用最方便。

### 5.2.4 Extended Thinking 协议

#### 5.2.4.1 启用扩展思考

在请求中设置 `thinking` 参数来启用 Extended Thinking：

```json
{
  "model": "claude-sonnet-4-5-20250929",
  "max_tokens": 16000,
  "thinking": {
    "type": "enabled",
    "budget_tokens": 8000
  },
  "messages": [
    {"role": "user", "content": "证明素数有无穷多个。"}
  ]
}
```

关键约束：

1. **`max_tokens` 必须大于 `budget_tokens`**：因为 `max_tokens` 是总输出上限（思考 + 文本），`budget_tokens` 是思考部分的预算。如果 `max_tokens <= budget_tokens`，API 会返回错误
2. **`budget_tokens` 的最小值**：通常为 1024 tokens。低于此值的思考可能不够充分
3. **思考 tokens 不可缓存**：与 Prompt Caching 不同，思考 tokens 不享受缓存折扣

**自适应模式（Adaptive Thinking）：**

```json
{
  "thinking": {
    "type": "adaptive"
  }
}
```

使用 `"adaptive"` 类型，模型会根据问题复杂度自行决定思考深度。对于简单问题（如"今天天气怎么样"），它可能几乎不思考；对于复杂问题（如"证明费马大定理的特例"），它会自动分配更多 tokens。

**思考可见性控制：**

```json
{
  "thinking": {
    "type": "enabled",
    "budget_tokens": 8000
  }
}
```

当不指定 `display` 参数时，思考内容默认包含在响应中。你也可以请求不显示思考内容，仅保留签名。

#### 5.2.4.2 思考内容块结构

启用 Extended Thinking 后，流式响应中的内容块顺序为：**思考块 → 文本块**（或工具调用块）。

**思考内容块（`thinking` 类型）：**

```json
{
  "type": "thinking",
  "thinking": "让我逐步分析这个问题...\n\n1. 首先回顾素数定义\n2. 使用反证法...",
  "signature": "EqQBCgIYAhIM1gbcDa9GJwZA2b3hGgxBdjrkzLoky3dl1pkiMOYds..."
}
```

- `thinking`（string）：模型的内部推理过程，人类可读
- `signature`（string）：加密签名，用于验证思考内容的真实性

**加密思考内容块（`redacted_thinking` 类型，仅 Claude 3.7 Sonnet）：**

```json
{
  "type": "redacted_thinking",
  "data": "EmwKAhgBEgy3va3pzix/LafPsn4aDFIT2Xlxh0L5L8rLVyIwxtE3rAFBa8cr3qpP..."
}
```

当 Claude 3.7 Sonnet 的思考内容被安全系统标记时，部分或全部内容可能被加密。`redacted_thinking` 块包含不可读的加密数据，但它仍然可以被传递回 API 以保持对话上下文。Claude 4 系列模型不产生 redacted thinking 块。

**流式传输中的思考事件序列：**

```
event: message_start
data: {"type": "message_start", "message": {...}}

event: content_block_start
data: {"type": "content_block_start", "index": 0, "content_block": {"type": "thinking", "thinking": ""}}

event: content_block_delta
data: {"type": "content_block_delta", "index": 0, "delta": {"type": "thinking_delta", "thinking": "让我逐步分析..."}}

event: content_block_delta
data: {"type": "content_block_delta", "index": 0, "delta": {"type": "thinking_delta", "thinking": "\n\n继续推理..."}}

event: content_block_delta
data: {"type": "content_block_delta", "index": 0, "delta": {"type": "signature_delta", "signature": "EqQBCgIYAhIM..."}}

event: content_block_stop
data: {"type": "content_block_stop", "index": 0}

event: content_block_start
data: {"type": "content_block_start", "index": 1, "content_block": {"type": "text", "text": ""}}

event: content_block_delta
data: {"type": "content_block_delta", "index": 1, "delta": {"type": "text_delta", "text": "根据我的分析..."}}

event: content_block_stop
data: {"type": "content_block_stop", "index": 1}

event: message_delta
data: {"type": "message_delta", "delta": {"stop_reason": "end_turn", "stop_sequence": null}, "usage": {"output_tokens": 320}}

event: message_stop
data: {"type": "message_stop"}
```

注意关键点：
1. 思考块的 `signature_delta` 在 `content_block_stop` 之前发送——这是最后一个 delta
2. 思考块结束后，才开始文本块
3. `message_delta` 中的 `usage.output_tokens` 包含了思考 tokens + 文本 tokens

#### 5.2.4.3 签名验证算法

思考块的签名（signature）是一个加密字符串。它的用途是：当你将思考块传递回 API 进行多轮对话时，API 通过验证签名来确认思考块确实由 Claude 生成且未被篡改。

**验证机制：**

1. 每个 `thinking` 内容块包含一个 `signature` 字段
2. 签名是思考内容的加密散列，由 Anthropic 的私钥签名
3. 当你将带有 `thinking` 块的 assistant 消息发送回 API 时，API 在内部验证签名
4. 如果签名不匹配（内容被修改）或缺失，API 返回错误

**关键协议约束：**

1. 在多轮对话中，如果使用了工具调用，必须将上一个 assistant 消息中的思考块完整返回
2. 如果上一个 assistant 消息同时包含思考和工具调用，所有内容块必须保持原始顺序
3. 你可以省略非工具调用场景中的历史思考块（API 会为你剥离），但推荐始终完整返回以保持一致性

**实现层面的注意事项：**

签名验证是 Anthropic 服务端行为——客户端不需要（也无法）独立验证签名。但客户端必须：
- 保留完整的 `signature` 字符串
- 在构造多轮对话的 assistant 消息时，原封不动地包含 signature
- 保持 `thinking` 和 `signature` 的配对关系

如果你需要测试对 redacted thinking 的处理，可以使用以下特殊测试字符串作为 prompt：

```
ANTHROPIC_MAGIC_STRING_TRIGGER_REDACTED_THINKING_46C9A13E193C177646C7398A98432ECCCE4C1253D5E2D82641AC0E52CC2876CB
```

### 5.2.5 Tree of Thoughts 与 Extended Thinking 的结合

Tree of Thoughts（ToT，思维树）是由 Yao 等人（2023）和 Long（2023）提出的推理框架。它是对 Chain-of-Thought（CoT，思维链）的泛化——不是沿着单一路径推理，而是在每个决策点探索多个分支，评估后选择最佳路径。

ToT 的四个核心步骤：

1. **思维分解（Thought Decomposition）**：将问题分解为中间步骤，每个步骤产生一个"思维"（thought）
2. **思维生成（Thought Generation）**：对每个步骤生成多个候选思维
3. **状态评估（State Evaluation）**：使用启发式方法（如"合理/可能/不可能"）评估每个思维
4. **搜索算法（Search Algorithm）**：使用 BFS（广度优先搜索）或 DFS（深度优先搜索）在思维树中搜索

当 Extended Thinking 与 ToT 策略结合时，可以产生强大的协同效应：

- **Extended Thinking 提供"底层推理引擎"**：Claude 的思考块在每个节点上自动进行深度推理
- **ToT 提供"高层搜索框架"**：在应用层管理思维的分支、评估和回溯

这种结合对于以下场景特别有效：
- 数学证明（需要在多个路径中选择）
- 代码架构设计（需要权衡不同方案）
- 复杂决策（需要考虑多个维度）

**ToT 提示词模板：**

```
请使用思维树方法解决以下问题。对于每个步骤：
1. 生成 3 个候选解决方案路径
2. 对每个路径评估可行性（高/中/低）
3. 选择最佳路径继续
4. 如果当前路径不可行，回溯到上一个分支点

问题：{problem}
```

### 5.2.6 流的中断与恢复

#### 5.2.6.1 主动中断

客户端可以通过以下方式中断流：

- **Python SDK**：退出 `with stream:` 上下文管理器，或调用 `stream.close()`
- **TypeScript SDK**：`break` 出 `for await` 循环，或使用 `AbortController`
- **原始 HTTP**：关闭 TCP 连接

注意：中断流不会节省已消耗的 tokens——它们已被计费。但可以防止更多 tokens 的生成。

#### 5.2.6.2 网络中断恢复

SSE 协议原生支持断线重连：

1. 服务器可以在事件中包含 `id` 字段
2. 客户端在重连时发送 `Last-Event-ID` HTTP 头
3. 服务器根据 ID 续传

但实际上，Anthropic API 的流式响应**不使用** SSE 的 `id` 机制进行恢复。每个流式请求是独立的——如果连接中断，需要重新发送完整的请求。这是因为 LLM 的生成过程是自回归的，无法从中间位置"恢复"。

**推荐的恢复策略：**

1. 客户端维护已接收的完整文本
2. 如果连接中断，将已接收的文本作为 assistant 消息附加到对话历史中
3. 重新发送请求，包含完整的对话历史

```python
# 恢复策略示意
async def resilient_stream(client, messages, model, max_tokens):
    accumulated_text = ""
    max_retries = 3

    for attempt in range(max_retries):
        try:
            async with client.messages.stream(
                model=model,
                max_tokens=max_tokens,
                messages=messages,
            ) as stream:
                async for text in stream.text_stream:
                    accumulated_text += text
                    yield text
            return  # success
        except (ConnectionError, TimeoutError) as e:
            if attempt < max_retries - 1:
                # 附加已接收内容，重新请求
                messages.append({
                    "role": "assistant",
                    "content": accumulated_text[:500] + "...[truncated]"
                })
                continue
            raise
```

### 5.2.7 流内错误处理

流内错误与普通的 HTTP 错误不同——它们出现在 SSE 流中而不是 HTTP 响应头中。处理策略：

```python
async for event in stream:
    if event.type == "error":
        # 流内错误
        error_type = event.error.get("type")
        error_message = event.error.get("message")
        logger.error(f"Stream error: {error_type} - {error_message}")

        if error_type == "overloaded_error":
            # 服务过载，等待后重试
            await asyncio.sleep(5)
            raise RetryableError(error_message)

        # 对于其他流内错误，立即停止处理
        break

    elif event.type == "content_block_delta":
        # 正常处理
        ...
```

常见流内错误类型：
- `overloaded_error`：服务过载，通常可重试
- `rate_limit_error`：速率限制，需要等待
- `invalid_request_error`：请求参数在流处理过程中被判定无效

---

## 5.3 Python 实现

### 5.3.1 SSE 解析器：`sse_parser.py`

SSE 解析器是流处理的基石。它接收原始字节流，按照 RFC 规范解析为结构化的 Python 字典。关键设计原则：

1. **零依赖**：不依赖任何第三方 SSE 库
2. **增量解析**：支持分块输入（网络缓冲区可能在任何位置截断）
3. **缓冲管理**：正确处理跨 chunk 的事件边界
4. **协议兼容**：完全遵循 WHATWG SSE 标准

核心算法（详见代码）：

```
SSEParser:
  - feed(chunk: bytes) -> list[dict]
    将新的字节数据追加到缓冲区
    查找 \n\n（事件分隔符）
    对每个完整事件调用 _parse_event()
    保留不完整事件在缓冲区中

  - _parse_event(event_text: str) -> dict | None
    按行分割事件文本
    解析 event: 字段 → 事件类型
    解析 data: 字段 → 合并 JSON 数据
    返回 {"event": "...", "data": {...}}
    忽略注释行（以 : 开头）和 ping 事件
```

### 5.3.2 流处理器：`stream_handler.py`

流处理器在 SSE 解析器之上，提供业务级别的语义封装：

```
StreamHandler:
  - handle_event(event: dict) -> str | None
    根据事件类型分派：
      message_start → 记录消息元数据
      content_block_start → 初始化内容块缓冲区
      content_block_delta → 提取增量文本/思考
      content_block_stop → 完成内容块
      message_delta → 记录使用量统计
      message_stop → 标记流结束
      ping → 忽略（心跳）
      error → 抛出异常
    返回：可展示的文本（或 None）
```

### 5.3.3 思考处理器：`thinking_handler.py`

思考处理器是 Extended Thinking 的专用组件：

```
ThinkingHandler:
  - start_thinking(budget_tokens: int)
    初始化思考会话

  - process_thinking_delta(thinking: str)
    累积思考增量

  - finalize_thinking(signature: str) -> bool
    验证签名（基本格式校验）
    返回校验结果

  - get_thinking_context() -> dict
    返回可传递回 API 的思考上下文
```

完整的实现代码位于：
- `code/python/ch05/sse_parser.py`
- `code/python/ch05/stream_handler.py`
- `code/python/ch05/thinking_handler.py`

测试文件：`code/python/ch05/test_ch05.py`

### 5.3.4 Python 实现要点

**跨 chunk 解析的缓冲区管理**

SSE 的最常见陷阱是事件跨越两个 TCP 数据包（chunk）的边界。例如：

```
Chunk 1: "event: content_block_delta\ndata: {\"type\": \"content_bloc"
Chunk 2: "k_delta\", \"index\": 0, ...}\n\n"
```

解析器必须在收到 Chunk 1 时暂存不完整的事件，待收到 Chunk 2 后拼接完整再解析。我们的 `SSEParser.feed()` 方法通过维护一个 `_buffer` 字节串来实现这一点。

**字段解析的边界情况**

SSE 协议有一些容易被忽略的细节：
- 注释行以 `:` 开头，应被忽略
- `data:` 字段可以有多个连续行，应合并为单个字符串
- 字段名后的空格是可选的（`event:foo` 和 `event: foo` 都合法）
- 空行（`\n\n`）必须触发事件派发，单独的 `\n` 是字段分隔

---

## 5.4 Node.js / TypeScript 实现

Node.js 实现的逻辑与 Python 版本完全对应，使用 TypeScript 的类型系统提供更强的编译期保障。

### 5.4.1 `SSEParser.ts`

```typescript
class SSEParser {
  private buffer: string = "";

  feed(chunk: string): ParsedEvent[] {
    this.buffer += chunk;
    const events: ParsedEvent[] = [];
    // 查找 \n\n 分隔符
    while (true) {
      const idx = this.buffer.indexOf("\n\n");
      if (idx === -1) break;
      const eventText = this.buffer.slice(0, idx);
      this.buffer = this.buffer.slice(idx + 2);
      const parsed = this.parseEvent(eventText);
      if (parsed) events.push(parsed);
    }
    return events;
  }

  private parseEvent(eventText: string): ParsedEvent | null {
    // 按行解析，提取 event 和 data 字段
    ...
  }
}
```

### 5.4.2 `StreamHandler.ts`

与 Python 版本一致的事件处理逻辑，使用 TypeScript 的判别联合类型（discriminated unions）来类型安全地处理不同事件类型。

### 5.4.3 `ThinkingHandler.ts`

TypeScript 版本的思考处理器，包含签名完整性校验和思考上下文构造。

完整的实现代码位于：
- `code/node/ch05/SSEParser.ts`
- `code/node/ch05/StreamHandler.ts`
- `code/node/ch05/ThinkingHandler.ts`

测试文件：`code/node/ch05/ch05.test.ts`

---

## 5.5 最佳实践

### 5.5.1 何时选流式，何时选非流式

**优先使用流式的场景：**

- 面向用户的聊天界面：改善感知速度
- 长文本生成（代码、文章、报告）：提供"生成进度感"
- 需要实时渲染的场景（如 Markdown 预览）
- 工具调用的实时状态展示
- 需要提前终止生成的场景

**优先使用非流式的场景：**

- 后台批处理任务（如数据标注、文档分析）
- 短回答（如分类、情感分析）
- 需要完整的结构化输出（如 JSON Schema 验证）
- 需要精确 Token 计数后才展示的场景
- Lambda/Serverless 函数（避免长连接超时）

**决策树：**

```
需要实时展示给用户？
  ├── 是 → 使用流式
  │     └── 需要思考可见？ → 启用 Extended Thinking + 流式
  └── 否 → 非流式
        └── 需要深度推理？ → 启用 Extended Thinking（非流式）
```

### 5.5.2 思考预算优化

`budget_tokens` 是 Extended Thinking 的核心调优参数。以下是一些经验法则：

| 场景 | 推荐 budget_tokens | 说明 |
|------|-------------------|------|
| 简单问答 | 1024-2048 | 事实类问题，不需要深度推理 |
| 代码生成 | 2048-4096 | 中等复杂度，需要算法设计 |
| 数学证明 | 4096-8000 | 需要严格的逻辑推导 |
| 架构设计 | 8000-16000 | 复杂的多维度权衡 |
| 科学研究 | 16000+ | 需要广泛探索和验证 |

**预算与成本的关系：**

思考 tokens 计入 `output_tokens` 计费。如果你设置 `budget_tokens=8000` 但模型实际只用了 3000 个思考 tokens，你只被收取 3000 个 output tokens 的费用。预算是一个**上限**，不是承诺使用量。

**自适应模式的选择：**

- 对于用户输入不可预测的开放域场景（如通用聊天机器人），使用 `"adaptive"` 模式
- 对于领域专业、可预测复杂度的场景（如法律文书分析），使用固定 `budget_tokens`

### 5.5.3 签名安全实践

虽然签名验证是 Anthropic 服务端的职责，但客户端仍需遵循以下安全实践：

1. **完整性保护**：在多轮对话中，始终原封不动地保留并传回 `thinking` 和 `signature` 字段
2. **顺序保持**：thinking 块必须位于其对应 assistant 消息的 text/tool_use 块之前
3. **不篡改内容**：永远不要修改 `thinking` 字段的内容——即使只是为了"清理格式"
4. **验证失败处理**：如果 API 返回签名验证错误，检查：
   - thinking 块是否被截断
   - thinking 块与 text 块的顺序是否正确
   - 在多工具调用场景中，所有块是否都完整保留
5. **日志脱敏**：在日志中记录签名时截断（如只记录前 20 个字符），因为完整的签名可能包含可恢复的思考内容

### 5.5.4 流式处理的工程实践

**内存管理：**

对于长时间运行的流式连接（如 Extended Thinking 可能持续数十秒），注意避免无限制地累积数据：

```python
# 坏实践：无限累积
all_text = ""
async for text in stream.text_stream:
    all_text += text  # 可能增长到数 MB

# 好实践：流式处理，按需保留
async for text in stream.text_stream:
    process(text)  # 处理即丢弃
```

**超时与保活：**

Extended Thinking 模式下，模型可能在 `content_block_start`（thinking）和第一个 `content_block_delta` 之间有几秒甚至十几秒的"沉默期"——它正在内部推理。确保：
- 客户端超时设置足够长（至少 60-120 秒）
- HTTP 库正确处理 `ping` 事件以维持连接
- 中间代理（Nginx、负载均衡器）的超时设置也相应调整

**错误降级：**

```python
try:
    # 尝试使用 Extended Thinking
    response = client.messages.create(
        model="claude-sonnet-4-5-20250929",
        max_tokens=16000,
        thinking={"type": "enabled", "budget_tokens": 8000},
        messages=messages,
    )
except AnthropicError as e:
    if "thinking" in str(e).lower():
        # 降级为普通模式
        logger.warning("Extended Thinking failed, falling back to standard mode")
        response = client.messages.create(
            model="claude-sonnet-4-5-20250929",
            max_tokens=8000,
            messages=messages,
        )
    else:
        raise
```

---

## 5.6 自测题

### 题目 1：SSE 解析器实现（编程题）

不依赖任何第三方 SSE 库，用你熟悉的语言实现一个 SSE 解析器。解析器需要：

1. 支持分块输入（chunked input）
2. 正确解析 `event:` 和 `data:` 字段
3. 正确处理多行 `data:` 合并
4. 正确处理 ping 事件（忽略）
5. 正确处理 `\n\n` 事件边界

使用以下测试输入验证你的实现：

```
event: message_start\ndata: {"type": "message_start", "message": {"id": "msg_01"}}\n\n
event: content_block_delta\ndata: {"type": "content_block_delta", "index": 0, "delta": {"type": "text_delta", "text": "Hello"}}\n\n
event: ping\ndata: {"type": "ping"}}\n\n
```

### 题目 2：思考签名验证（编程题）

给定一个 `thinking` 内容块：

```json
{
  "type": "thinking",
  "thinking": "Let me analyze this problem step by step...",
  "signature": "EqQBCgIYAhIM1gbcDa9GJwZA2b3hGgxBdjrkzLoky3dl1pkiMOYds..."
}
```

实现一个函数 `prepare_assistant_message(blocks)`，接收原始思考块和文本块的列表，构造一个可以安全传递回 API 的 assistant 消息对象。确保：

1. thinking 块在 text 块之前
2. 保留所有原始字段
3. 验证签名存在且非空
4. 为 `redacted_thinking` 块提供回退处理

### 题目 3：流式中断与恢复（设计题）

假设你正在构建一个聊天应用，用户在 Claude 生成回答的过程中点击了"停止生成"按钮，然后又发送了一条新消息。

1. 你如何构造第二条消息的 API 请求？需要包含哪些对话历史？
2. 已生成但未显示的思考 tokens 是否应该包含在历史中？为什么？
3. 如果 Extended Thinking 在工具调用后被中断（即模型生成了思考+工具调用，但用户在上传工具结果前点击了停止），你会如何处理？

### 题目 4：事件序列分析（分析题）

给定以下不完整的事件序列：

```
event: message_start
data: {"type": "message_start", "message": {"id": "msg_01", "content": [], ...}}

event: content_block_start
data: {"type": "content_block_start", "index": 0, "content_block": {"type": "thinking", "thinking": ""}}

event: content_block_delta
data: {"type": "content_block_delta", "index": 0, "delta": {"type": "thinking_delta", "thinking": "Let me check the weather..."}}

event: content_block_delta
data: {"type": "content_block_delta", "index": 0, "delta": {"type": "signature_delta", "signature": "abc123..."}}

event: content_block_stop
data: {"type": "content_block_stop", "index": 0}

event: content_block_start
data: {"type": "content_block_start", "index": 1, "content_block": {"type": "tool_use", "id": "toolu_01", "name": "get_weather", "input": {}}}

event: content_block_delta
data: {"type": "content_block_delta", "index": 1, "delta": {"type": "input_json_delta", "partial_json": "{\"location\": \"SF\"}"}}

event: error
data: {"type": "error", "error": {"type": "overloaded_error", "message": "Overloaded"}}
```

请回答：
1. 这个事件序列在协议层面是否合法？解释原因。
2. 收到 `error` 事件后，客户端应该如何处理？
3. 如果这是多轮对话中的第三轮，你如何构造第四轮的请求以正确恢复对话？

---

## 5.7 本章小结

本章从协议、实现和工程三个维度剖析了 Anthropic 的 Streaming 和 Extended Thinking 两大核心特性。

**SSE 协议**是流式响应的基础。它简单、基于 HTTP、单向推送，天然适合 LLM 的 token-by-token 生成模式。7 种事件类型（message_start、content_block_start、content_block_delta、content_block_stop、message_delta、message_stop、ping）构成了完整的流式语义。

**Extended Thinking** 将 Claude 的推理过程显式化。通过 `thinking` 内容块和加密签名的组合，它在保持安全性的同时，为开发者提供了前所未有的推理透明度。`budget_tokens` 参数允许你精确控制思考的深度与成本的平衡。

**工程实践方面**，关键决策包括：何时使用流式、如何设置思考预算、如何处理签名、如何管理连接生命周期。

下一章，我们将深入 Anthropic 的 Tool Use（函数调用）协议——如何让 Claude 与外部系统交互，调用 API、运行代码、搜索数据库。

---

*本章代码位于 `code/python/ch05/` 和 `code/node/ch05/`。所有代码均可用 `pytest` 和 `vitest` 测试验证。*
