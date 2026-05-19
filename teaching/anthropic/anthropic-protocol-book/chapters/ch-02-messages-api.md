# 第 2 章：Messages API 核心协议

> **本章目标**：深入理解 Anthropic Messages API 的协议核心——Content Block 类型系统、消息构建规则、模型参数体系与多模态交互协议。完成本章后，你将拥有一个不依赖官方 SDK、类型安全、完全可运行的请求构建器，能够生成符合协议规范的任意 Messages API 请求。

---

## 2.1 概念全景

### Messages API 在协议栈中的位置

如果说第 1 章构建的 HTTP 客户端是"通信管道"，那么本章聚焦的 Messages API 就是管道中流动的"语言"。它定义了客户端与 Claude 模型之间每一次对话的完整语法——消息如何组织、内容如何编码、参数如何控制生成行为。

Anthropic Messages API 的端点极为简洁：

```
POST https://api.anthropic.com/v1/messages
```

与 OpenAI 为对话（`/v1/chat/completions`）、补全（`/v1/completions`）、编辑等不同功能创建不同端点不同，Anthropic 将所有消息交互收敛到这一个端点。功能差异不再通过 URL 路径区分，而是通过 **Content Block 类型系统**在统一的请求体中表达。这一设计哲学可以概括为：

> **一个端点，多种 Block 类型。**

这意味着：文本对话、图像理解、工具调用、多轮对话——这些看似不同的交互模式，在协议层是同一概念的不同组合方式。

### 设计哲学：Content Block 抽象模型

Messages API 的核心创新在于 **Content Block**（内容块）抽象。它不是将消息内容视为扁平的字符串，而是将其建模为类型化的结构块数组。每条消息由一个或多个 Content Block 组成，每个 Block 通过 `type` 字段明确标识其语义。

四种核心 Content Block 类型构成了协议的完整表达能力：

| Block 类型 | 语义 | 使用场景 |
|-----------|------|---------|
| `text` | 文本内容 | 对话文本、提示词、系统指令 |
| `image` | 图像内容 | 视觉理解、多模态交互 |
| `tool_use` | 工具调用请求 | 模型请求调用外部工具 |
| `tool_result` | 工具执行结果 | 将工具返回值传回模型 |

这种设计的优势是多方面的：

**1. 多模态是一等公民。** 图像不是通过特殊参数"附加"到文本上的——它和文本一样，只是消息中的一个 Block。一个用户消息可以同时包含文本 Block 和图像 Block，排列顺序就是模型理解的顺序。

**2. 工具调用显式可追踪。** OpenAI 的函数调用隐藏在 `choices[0].message.tool_calls` 中，而 Anthropic 的工具调用是一个显式的 `tool_use` Content Block。你可以看到工具调用的完整 JSON 结构，调试时一目了然。

**3. 内容可组合。** 同一个抽象同时服务于请求和响应。你发送文本 Block，模型返回文本 Block；你发送工具结果 Block，模型可以在此之上继续推理。一致性降低了心智负担。

**4. 类型安全天然内建。** 每个 Block 都有明确的 `type` 字段，API 在网关层就能拒绝类型不明确或结构不规范的请求，减少因输入格式错误导致的意外行为。

### 与 OpenAI Chat Completions API 的关键差异

对于熟悉 OpenAI API 的开发者，以下对比表提供了快速概念映射：

| 概念 | Anthropic Messages API | OpenAI Chat Completions API |
|------|------------------------|---------------------------|
| 端点 | `POST /v1/messages`（唯一） | `POST /v1/chat/completions` |
| 消息内容 | 字符串 或 Content Block 数组 | 字符串 或 多部分数组（仅 vision） |
| 系统提示 | 顶层 `system` 参数 | `messages` 数组中 `role: "system"` |
| 图像 | `image` Content Block（base64 或 URL） | `image_url` content part |
| 工具调用 | `tool_use` + `tool_result` Content Blocks | `tool_calls` + `role: "tool"` |
| 工具定义 | `tools` 数组（含 `input_schema`） | `tools` 数组（含 `parameters`） |
| 停止原因 | `end_turn`, `max_tokens`, `stop_sequence`, `tool_use`, `pause_turn`, `refusal` | `stop`, `length`, `tool_calls`, `content_filter` |
| API 版本 | `anthropic-version` 请求头 | 无显式版本头（URL 路径版本化） |
| 扩展思考 | `thinking` 配置（可见推理过程） | 不支持（o1 系列为独立 API） |

关键的一点：**Anthropic Messages API 中没有 `system` 角色**。系统提示通过顶层 `system` 参数传递，而非混在消息数组中。这个设计选择使得"指令"和"对话"在结构上清晰分离。

### 本章学习成果

完成本章的学习和编码练习后，你将能够：

1. 理解 Content Block 类型系统的设计理念，知道何时使用每种 Block。
2. 使用自建的 `message_builder.py` / `MessageBuilder.ts` 构建任意复杂度的 API 请求——从简单的单轮文本对话到包含图像、工具调用历史的多轮交互。
3. 理解每个模型参数（temperature、top_p、top_k 等）的精确语义和合理取值。
4. 正确组织多轮对话的上下文，避免常见的上下文污染和角色顺序错误。
5. 处理图像输入的各种方式（base64、URL、本地文件），理解格式和大小限制。

本章构建的请求构建器将与第 1 章的 HTTP 客户端集成，形成完整的 API 调用链路。

---

## 2.2 协议规范逐层拆解

### 2.2.1 请求端点与认证头

Messages API 只有一个端点：

```
POST https://api.anthropic.com/v1/messages
```

必需的 HTTP 头：

```
x-api-key: sk-ant-api03-xxxxxxxxxxxxx
anthropic-version: 2023-06-01
content-type: application/json
```

`anthropic-version` 头的值为 `2023-06-01`（当前推荐版本）。这个版本日期的语义是：API 行为将与指定日期时的接口定义一致。当 Anthropic 引入向后不兼容的变更时，需要更新此版本号才能使用新特性。

### 2.2.2 角色系统

Messages API 只有两种消息角色：

| 角色 | 值 | 说明 |
|------|-----|------|
| 用户 | `user` | 代表人类用户或客户端。可以是提问、指令，或返回工具执行结果。 |
| 助手 | `assistant` | 代表 Claude 模型。在请求中用于提供历史对话上下文，在响应中是模型生成的唯一角色。 |

**没有 `system` 角色。** 系统提示通过顶层 `system` 参数传递（见 2.2.6 节）。

**角色交替规则：** 模型训练为在 `user` 和 `assistant` 交替的对话轮次上运作。连续的相同角色消息会被 API 自动合并为一个轮次。正确的多轮对话结构如下：

```json
[
  {"role": "user", "content": "你好。"},
  {"role": "assistant", "content": "你好！有什么可以帮助你的？"},
  {"role": "user", "content": "请用简单的中文解释什么是 LLM。"}
]
```

**填充助手回复（Prefill）：** 如果消息数组的最后一条是 `assistant` 角色，模型将从该消息的内容之后继续生成。这可以用于约束模型输出的开头：

```json
[
  {"role": "user", "content": "太阳的希腊名字是？ (A) Sol (B) Helios (C) Sun"},
  {"role": "assistant", "content": "最佳答案是 ("}
]
```

模型将从 `"最佳答案是 ("` 之后继续，大概率输出 `"B)"` 或 `"B) Helios"`。

**消息数量限制：** 单个请求最多 100,000 条消息（实践中极少达到此限制）。

### 2.2.3 多轮对话的上下文构建

Messages API 是**无状态**的——服务器不维护会话。每一轮对话都需要客户端将完整的历史消息发送给 API。这是 RESTful API 的标准模式，但也意味着上下文管理的责任完全在客户端。

构建多轮对话上下文的正确流程：

1. 第一轮：发送 `[user: "你好"]`，获得 `assistant: "你好！..."`
2. 第二轮：发送 `[user: "你好", assistant: "你好！...", user: "我的第二个问题"]`
3. 第 N 轮：追加最新的 user 消息，保持历史完整

**关键原则：**

- **不要修改历史 assistant 消息。** 一旦模型返回了某条回复，应原样保留在对话历史中。
- **工具调用轮次需要保留完整的 tool_use → tool_result 链路。** 中间缺少任何一个环节都会导致上下文断裂。
- **截断策略需要谨慎。** 简单地丢弃旧消息可能导致对话逻辑不连贯。合理做法是保留最近的 N 轮完整对话，或使用语义摘要替换早期轮次。

以下是一个包含工具调用的多轮对话示例：

```json
[
  {"role": "user", "content": "旧金山的天气如何？"},
  {"role": "assistant", "content": [
    {"type": "tool_use", "id": "toolu_01A", "name": "get_weather", "input": {"city": "San Francisco"}}
  ]},
  {"role": "user", "content": [
    {"type": "tool_result", "tool_use_id": "toolu_01A", "content": "晴朗，18°C"}
  ]},
  {"role": "assistant", "content": "旧金山当前天气晴朗，气温18°C。"},
  {"role": "user", "content": "那明天呢？"}
]
```

注意工具结果的 `role` 是 `user`。在概念上，工具执行是"客户端替用户完成的"，所以结果以 `user` 角色传回。

### 2.2.4 多模态 Content Block 详解

Content Block 是 Messages API 的核心数据结构。每个 Block 由 `type` 字段辨识，其具体结构取决于类型。

#### Text Block

纯文本内容块。最简单也最常用的类型。

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `type` | `"text"` | 是 | 固定值 |
| `text` | string | 是 | 文本内容 |
| `cache_control` | object \| null | 否 | 临时缓存控制断点，`{"type": "ephemeral"}` |
| `citations` | array \| null | 否 | 文本引文标注（响应中用） |

**示例：**

```json
{"type": "text", "text": "请总结以下文档的内容。"}
```

**简写形式：** 当消息的 `content` 字段直接使用字符串时，等价于一个包含单个 Text Block 的数组。以下两者完全等价：

```json
{"role": "user", "content": "Hello, Claude"}
```

```json
{"role": "user", "content": [{"type": "text", "text": "Hello, Claude"}]}
```

简写形式在纯文本对话中大幅减少了代码的冗长程度。

#### Image Block

图像内容块。支持两种来源方式：base64 编码数据和 URL 引用。

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `type` | `"image"` | 是 | 固定值 |
| `source` | object | 是 | 图像来源，见下表 |
| `cache_control` | object \| null | 否 | 临时缓存控制 |

**Source 对象（base64）：**

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `type` | `"base64"` | 是 | 固定值 |
| `media_type` | string | 是 | MIME 类型：`image/jpeg`, `image/png`, `image/gif`, `image/webp` |
| `data` | string | 是 | base64 编码的图像数据 |

**Source 对象（URL）：**

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `type` | `"url"` | 是 | 固定值 |
| `url` | string | 是 | 图像的 HTTP/HTTPS URL |

**支持的图像格式与限制：**

| 格式 | MIME Type | 说明 |
|------|-----------|------|
| JPEG | `image/jpeg` | 最常见格式，适合照片 |
| PNG | `image/png` | 无损格式，适合图表和截图 |
| GIF | `image/gif` | 支持动图（仅首帧被分析） |
| WebP | `image/webp` | 现代格式，兼具 JPEG 和 PNG 优势 |

**大小限制：**
- base64 编码图像：建议不超过 5 MB（原始文件大小）
- URL 引用图像：建议不超过 10 MB
- API 不强制执行硬性上限，但超大图像会增加延迟且可能被截断

**成本注意事项：** 图像按 token 计费。token 消耗取决于图像尺寸——越大的图像消耗越多 token。Anthropic 的图像 token 计算公式约为 `(width * height) / 750` tokens。一张 800x600 的图像约消耗 640 tokens。

**示例：**

```json
{
  "type": "image",
  "source": {
    "type": "base64",
    "media_type": "image/png",
    "data": "iVBORw0KGgoAAAANSUhEUgAAAAE..."
  }
}
```

**最佳实践：** 在发送前将图像缩放至合理尺寸。一张 4000x3000 的照片和一张 800x600 的缩略图在视觉理解效果上差异很小，但 token 成本相差约 25 倍。

#### Tool Use Block

工具调用请求块。出现在 assistant 角色的消息中，表示模型请求调用一个工具。

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `type` | `"tool_use"` | 是 | 固定值 |
| `id` | string | 是 | 此工具调用的唯一 ID，格式 `toolu_XXXX...` |
| `name` | string | 是 | 要调用的工具名称 |
| `input` | object | 是 | 工具输入参数，符合工具的 `input_schema` 定义 |

**示例：**

```json
{
  "type": "tool_use",
  "id": "toolu_01D7FLrfh4GYq7yT1ULFeyMV",
  "name": "get_stock_price",
  "input": {"ticker": "^GSPC"}
}
```

`id` 字段至关重要——它是后续 `tool_result` 与此工具调用匹配的唯一标识。

#### Tool Result Block

工具执行结果块。出现在 user 角色的消息中，将工具执行结果返回给模型。

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `type` | `"tool_result"` | 是 | 固定值 |
| `tool_use_id` | string | 是 | 对应的 `tool_use` 块的 `id` |
| `content` | string \| array | 是 | 工具执行结果（文本或嵌套 Content Block 数组） |
| `is_error` | boolean \| null | 否 | 工具执行是否失败（默认不传或 false） |

**`is_error` 的行为：**
- 不传或 `false`：模型会正常使用此结果继续推理。
- `true`：模型知道工具执行失败，可能尝试不同的参数或告知用户错误。

**示例：**

```json
{
  "type": "tool_result",
  "tool_use_id": "toolu_01D7FLrfh4GYq7yT1ULFeyMV",
  "content": "259.75 USD",
  "is_error": false
}
```

### 2.2.5 模型参数详解

控制模型生成行为的参数。正确理解每个参数的语义是获得高质量输出的基础。

| 参数 | 类型 | 必填 | 默认值 | 范围 | 说明 |
|------|------|------|--------|------|------|
| `model` | string | **是** | 无 | 长度 1-256 | 模型标识符。如 `"claude-sonnet-4-20250514"`, `"claude-opus-4-7"` |
| `max_tokens` | integer | **是** | 无 | >= 1 | 生成的最大 token 数。模型可能在此之前自然停止。不同模型有不同上限。 |
| `messages` | object[] | **是** | 无 | 最多 100,000 条 | 对话消息数组，user/assistant 交替 |
| `system` | string \| object[] | 否 | 无 | — | 系统提示（文本字符串或 Text Block 数组） |
| `temperature` | number | 否 | 1.0 | 0.0 - 1.0 | 控制随机性。接近 0 更确定（适合分析/选择题），接近 1 更富创造性（适合创意写作） |
| `top_p` | number | 否 | — | 0.0 - 1.0 | 核采样。从累积概率达到此阈值的 token 中采样。通常与 temperature 二选一使用 |
| `top_k` | integer | 否 | — | >= 0 | 仅从概率最高的 K 个 token 中采样。消除"长尾"低概率选项 |
| `stop_sequences` | string[] | 否 | — | — | 自定义停止序列。模型生成到这些文本时立即停止 |
| `stream` | boolean | 否 | false | — | 启用流式响应（Server-Sent Events） |
| `metadata` | object | 否 | — | — | 请求元数据，目前仅支持 `user_id` 子字段 |
| `tools` | object[] | 否 | — | — | 工具定义数组（详见第 6 章） |
| `tool_choice` | object | 否 | `{"type": "auto"}` | — | 控制工具选择策略：`auto`（自动）、`any`（必须使用工具）、`tool`（指定工具）、`none`（不使用工具） |
| `thinking` | object | 否 | — | — | 扩展思考配置。`{"type": "enabled", "budget_tokens": N}`。最小 budget 1,024 tokens |
| `service_tier` | string | 否 | — | `auto` \| `standard_only` | 服务层级。`auto` 优先使用预留容量 |
| `cache_control` | object | 否 | — | — | 顶层缓存控制。自动应用到请求中最后一个可缓存的 Block |

#### 参数组合建议

**确定性与创意性控制：**

| 场景 | temperature | top_p | top_k | 说明 |
|------|-------------|-------|-------|------|
| 代码生成、选择题、事实问答 | 0.0 - 0.3 | — | — | 低随机性，输出更一致 |
| 通用对话 | 0.7 - 1.0 | — | — | 默认值 1.0，适合大多数场景 |
| 创意写作、头脑风暴 | 1.0 | — | — | 最大随机性 |
| 高级控制（减少重复） | — | 0.9 | 40-50 | 仅限需要精细调节的场景 |

**一个重要事实：** 即使 `temperature = 0.0`，多次调用同一 prompt 仍可能产生略有不同的结果。Claude 不是完全确定性的——参数控制的是概率分布的形状，而非消除所有随机性。

#### metadata.user_id 的使用

`metadata.user_id` 用于传递用户的匿名标识符：

```json
{
  "metadata": {
    "user_id": "13803d75-b4b5-4c3e-b2a2-6f21399b021b"
  }
}
```

**重要安全要求：**
- 必须使用 UUID、哈希值或其他**不透明**标识符。
- **严禁**包含姓名、邮箱或电话号码等个人身份信息（PII）。
- Anthropic 可能使用此 ID 辅助滥用检测。
- 最大长度 256 字符。

### 2.2.6 系统提示的两种传递方式

Anthropic Messages API 支持两种系统提示传递方式，这在设计上值得注意。

#### 方式一：顶层 `system` 参数（推荐）

```json
{
  "model": "claude-sonnet-4-20250514",
  "max_tokens": 1024,
  "system": "你是一个有帮助的AI助手。回答应该简洁明了。",
  "messages": [
    {"role": "user", "content": "什么是量子计算？"}
  ]
}
```

这是 Anthropic 推荐的方式。`system` 参数在结构上独立于对话消息，语义清晰——"这是给模型的指令"。

**作为 Text Block 数组：** `system` 也可以是一组 Text Block，支持 `cache_control`：

```json
{
  "system": [
    {
      "type": "text",
      "text": "你是一个有帮助的AI助手。",
      "cache_control": {"type": "ephemeral"}
    }
  ]
}
```

这在系统提示长且固定（适合缓存）的场景中非常有用。

#### 方式二：消息数组中的 user 角色

```json
{
  "messages": [
    {"role": "user", "content": "你是一个有帮助的AI助手。回答应该简洁明了。\n\n什么是量子计算？"}
  ]
}
```

将指令拼接在第一条 user 消息中。技术上可行，但不推荐：
- 指令和用户输入混在一起，语义不清晰。
- 多轮对话中难以区分哪些是"系统级指令"、哪些是"用户输入"。
- 无法独立对系统指令使用 prompt caching。

**建议：** 始终使用顶层 `system` 参数传递系统提示。将指令和对话数据在结构上分离。

### 2.2.7 视觉能力：图像理解协议

Claude 3 系列及更新模型（Sonnet 4、Opus 4 等）具备视觉理解能力。图像通过 `image` Content Block 传入，模型可以：

- 描述图像内容
- 回答关于图像的问题
- 从图像中提取文本（OCR）
- 分析图表、流程图和界面截图
- 比较和对比多张图像

**多图像支持：** 一个 user 消息中可以包含多张图像。模型会按 Block 顺序依次处理：

```json
{
  "role": "user",
  "content": [
    {"type": "text", "text": "比较这两张图表的差异："},
    {"type": "image", "source": {"type": "url", "url": "https://example.com/chart1.png"}},
    {"type": "image", "source": {"type": "url", "url": "https://example.com/chart2.png"}}
  ]
}
```

**文本与图像的排列顺序很重要。** 将文本指令放在图像**之前**（如上例），模型会先理解任务再分析图像，通常效果更好。交错排列的图像和文本（如：文本→图A→文本→图B）可以让模型在分析每张图之前获得针对性指令。

**分辨率与质量权衡：**
- 更高分辨率的图像提供更多细节，但消耗更多 token。
- 对于 OCR 任务（从图像中读取文字），确保文字在图像中清晰可辨。
- 对于照片描述，800x600 通常是足够的。
- 大于 1568 像素（任意维度）的图像会被缩放到长边 1568 像素。

**局限性：**
- 模型不擅长精确的空间定位（如"在坐标 (342, 518) 处的对象"）。
- 小文本或有噪声背景的文本可能被误读。
- 医学影像（X 光、CT）等需要专业领域知识的图像分析能力有限。

---

## 2.3 Python 实现

本章的 Python 实现位于 `code/python/ch02/message_builder.py`。以下是核心设计决策和关键代码段。

### 架构设计

```python
ContentBlock (抽象基类)
├── TextBlock         — {"type": "text", "text": "..."}
├── ImageBlock        — {"type": "image", "source": {...}}
├── ToolUseBlock      — {"type": "tool_use", "id": "...", ...}
└── ToolResultBlock   — {"type": "tool_result", "tool_use_id": "...", ...}

Message               — {"role": "...", "content": ...}
MessageRequest        — 完整的 POST /v1/messages 请求体
```

所有类使用 `@dataclass` 实现，自带类型注解。`to_dict()` 方法将对象序列化为符合 API 规范的 `dict`。

### 关键设计决策

**1. 工厂方法优先于直接构造器。** `ImageBlock.from_base64()`, `ImageBlock.from_url()`, `ImageBlock.from_file()` 提供了三种创建图像块的安全途径。它们各自处理输入验证（格式检查、大小检查、数据清理）。

**2. 数据 URI 前缀自动剥离。** 从前端传来的 base64 数据常带有 `data:image/png;base64,` 前缀，`from_base64()` 自动处理这种情况。

**3. 参数验证在构造时完成。** `MessageRequest.__post_init__()` 对所有必填字段和数值范围进行检查。无效请求在序列化之前就会被拒绝，符合"fail fast"原则。

**4. 可选字段仅在非 None 时输出。** `to_dict()` 只输出用户显式设置的字段。这与 API 的设计一致——未设置的字段使用服务端默认值。

**5. `ContentBlock.from_dict()` 提供反序列化。** 这对解析 API 响应或从存储中恢复请求非常有用。

### 使用示例

```python
from message_builder import (
    Message, MessageRequest, TextBlock, ImageBlock,
    simple_text_request, multimodal_request
)

# 最简单的文本请求
req = simple_text_request("讲个笑话")
print(req.to_json(indent=2))

# 包含图像的多模态请求
req = multimodal_request(
    text="描述这张图片",
    images=[ImageBlock.from_file("./photo.jpg")],
    model="claude-sonnet-4-20250514",
    system="你是一个图片描述助手。",
)

# 包含工具调用的多轮对话
req = MessageRequest(
    model="claude-sonnet-4-20250514",
    messages=[
        Message.user("巴黎天气怎么样？"),
        Message.assistant([
            ToolUseBlock("toolu_01", "get_weather", {"city": "Paris"})
        ]),
        Message.user([
            ToolResultBlock.from_success("toolu_01", "晴，22°C")
        ]),
    ],
    max_tokens=1024,
    tools=[...],  # 工具定义见第6章
)

# 直接发送 HTTP 请求
import httpx
response = httpx.post(
    "https://api.anthropic.com/v1/messages",
    headers={
        "x-api-key": "...",
        "anthropic-version": "2023-06-01",
        "content-type": "application/json",
    },
    json=req.to_dict(),
)
```

完整的代码、测试和更多使用模式请参考 `code/python/ch02/message_builder.py`。

### 运行测试

```bash
cd code/python/ch02
python -m pytest test_message_builder.py -v
```

测试覆盖所有 Content Block 类型、Message 构造、MessageRequest 验证和序列化，以及边界情况处理。

---

## 2.4 Node.js/TypeScript 实现

TypeScript 实现遵循与 Python 版本相同的架构，但利用了 TypeScript 的静态类型系统提供额外的编译期安全保障。

### 架构设计

```typescript
ContentBlock (抽象类)
├── TextBlock
├── ImageBlock
├── ToolUseBlock
└── ToolResultBlock

Message
MessageRequest
```

### 关键差异

**1. 强类型化。** 所有接口（`TextBlockDict`, `ImageBlockDict`, `ToolUseBlockDict`, `ToolResultBlockDict`）精确描述了 API 的 JSON 结构。TypeScript 编译器会在构建时捕获类型错误。

**2. `MessageRequest` 使用参数对象模式。** 构造函数接受一个配置对象而非多个位置参数，让可选参数的设置更清晰：

```typescript
const req = new MessageRequest({
  model: "claude-sonnet-4-20250514",
  messages: [Message.user("Hi")],
  maxTokens: 1024,
  temperature: 0.7,
});
```

**3. `ContentBlock.fromDict()` 支持类型窄化。** 根据 `type` 字段返回正确的子类实例，使用 `instanceof` 检查后可安全访问子类特有的属性。

### 使用示例

```typescript
import {
  Message, MessageRequest, TextBlock, ImageBlock,
  ToolUseBlock, ToolResultBlock,
  simpleTextRequest, multimodalRequest,
} from "./MessageBuilder.js";

// 简单文本请求
const req = simpleTextRequest("讲个笑话");
console.log(req.toJsonString(2));

// 多模态请求
const req2 = multimodalRequest("描述这张图片", [
  ImageBlock.fromUrl("https://example.com/photo.jpg"),
]);

// 类型安全：编译时捕获错误
// ❌ TypeScript 编译错误：
// new ImageBlock({ type: "wrong" } as any);

// ✅ 正确的创建方式：
const img = ImageBlock.fromBase64("...", "image/png");
```

### 运行测试

```bash
cd code/node
npx vitest run ch02/message_builder.test.ts
```

---

## 2.5 最佳实践

### 2.5.1 多轮对话上下文管理

**原则 1：不可变性。** 一旦 assistant 消息被记录下来，永远不要修改其内容。如果你需要"纠正"模型的输出，通过下一条 user 消息进行引导，而非修改历史。

```python
# ✅ 正确：通过后续消息引导
messages = [
    Message.user("1+1等于几？"),
    Message.assistant("等于3。"),  # 模型的错误回答
    Message.user("再检查一下。1+1等于几？"),
]

# ❌ 错误：修改历史 assistant 消息
messages[1].content = "等于2。"  # 不要这样做
```

**原则 2：上下文窗口感知。** 不同的 Claude 模型有不同的上下文窗口。在构建长对话时，监控累计 token 数。当接近上限时，考虑：

- 对早期对话轮次做摘要，替换详细的历史记录。
- 优先保留最近的 N 轮完整对话。
- 使用 prompt caching 缓存重复的前缀（如系统提示）。

**原则 3：工具调用的完整性。** 涉及工具调用的对话轮次必须完整保留：

```
user → assistant(tool_use) → user(tool_result) → assistant(最终回复)
```

缺少 `tool_result` 就删除历史 `tool_use` 会导致模型产生困惑。

### 2.5.2 图像优化

**尺寸优化：**

| 场景 | 建议最大尺寸 | 理由 |
|------|-------------|------|
| 照片描述 | 800x600 | 足够识别对象和场景 |
| OCR 文字提取 | 1568x长边 | 文字需要更高清晰度 |
| 图表/UI 分析 | 1200x900 | 细节重要但不需要全分辨率 |
| 多图对比 | 每张 512x512 | 降低总体 token 消耗 |

**格式选择：**
- 照片 → JPEG（质量 80%）
- 截图、图表、UI → PNG
- 需要透明背景 → PNG
- 现代平台，需要更小文件 → WebP

**base64 vs URL：**
- base64：适合本地文件、动态生成的图像、离线场景
- URL：适合已在 CDN 上的图像、公共网络资源
- 优先使用 URL——避免在请求体中传输大量 base64 数据

```python
# ✅ 好的做法：在编码前压缩图像
from PIL import Image
img = Image.open("large_photo.jpg")
img.thumbnail((800, 600))
img.save("compressed.jpg", quality=80)
block = ImageBlock.from_file("compressed.jpg")

# ❌ 不够好：直接编码原始大小的图像
block = ImageBlock.from_file("large_photo.jpg")  # 可能 10MB+
```

### 2.5.3 参数调优

**temperature 的选择策略：**

```python
# 确定性任务（代码、数学、事实问答）
req = MessageRequest(
    model="claude-sonnet-4-20250514",
    messages=[Message.user(prompt)],
    max_tokens=4096,
    temperature=0.0,  # 最小随机性
)

# 创意写作
req = MessageRequest(
    model="claude-sonnet-4-20250514",
    messages=[Message.user(prompt)],
    max_tokens=4096,
    temperature=0.9,  # 高创造性
)
```

**max_tokens 的合理设置：**
- 不要设置得比实际需要的输出大太多。`max_tokens` 直接影响成本上限。
- 短回答：256-512
- 一般对话：1024-2048
- 长文生成：4096-8192

**stop_sequences 的使用场景：**

```python
# 生成列表，在遇到空行时停止
req = MessageRequest(
    ...,
    stop_sequences=["\n\n", "---"],
)

# 多轮对话中标记用户输入边界
req = MessageRequest(
    ...,
    stop_sequences=["Human:", "用户：", "\nQ:"],
)
```

### 2.5.4 常见错误与避免方法

| 错误 | 后果 | 正确做法 |
|------|------|---------|
| 在 messages 中使用 `system` 角色 | API 返回 400 错误 | 使用顶层 `system` 参数 |
| 修改历史 assistant 消息 | 上下文逻辑断裂 | 保持不可变性，通过新消息引导 |
| 连续的 user 或 assistant 消息 | 自动合并，可能丢失意图 | user/assistant 严格交替 |
| 图像未压缩直接 base64 | 请求体过大，延迟增加 | 发送前缩放至合理尺寸 |
| `max_tokens` 设置为 0 或负数 | API 返回 400 错误 | 最小值为 1 |
| temperature 超出 [0, 1] 范围 | API 返回 400 错误 | 保持在 0.0-1.0 之间 |
| `tool_use_id` 与 `tool_result` 不匹配 | 模型无法关联结果 | 严格匹配 ID |
| 在 URL 模式中使用 `file://` | API 无法访问本地文件 | 使用 base64 编码替代 |

### 2.5.5 正面模式

```python
# 模式 1：渐进式指令（在 assistant prefill 中引导格式）
{"role": "user", "content": "列出三种编程语言及其用途。"},
{"role": "assistant", "content": "{"}  # 强制 JSON 输出

# 模式 2：多图对比（图像间插文本说明）
{"role": "user", "content": [
    {"type": "text", "text": "第一张图是修改前的UI："},
    {"type": "image", "source": {"type": "url", "url": "..."}},
    {"type": "text", "text": "第二张图是修改后的UI。请列出所有差异："},
    {"type": "image", "source": {"type": "url", "url": "..."}},
]}

# 模式 3：带缓存控制的系统提示（适合多次重复使用同一提示的批处理场景）
request = MessageRequest(
    ...,
    system=[
        {"type": "text", "text": long_system_prompt,
         "cache_control": {"type": "ephemeral"}}
    ],
)
```

---

## 2.6 自测题

### 问题 1（概念）

Messages API 的 `system` 提示和 OpenAI API 的 `system` 消息有何不同？为什么 Anthropic 选择了顶层参数而非消息角色？

<details>
<summary>参考答案</summary>

Anthropic 使用顶层 `system` 参数而非 `"role": "system"` 的消息。主要差异：

1. **结构分离：** `system` 在请求体中独立存在，与对话消息数组平行。语义上明确区分"指令"和"对话"。
2. **没有 system 角色：** Messages API 只支持 `user` 和 `assistant` 两种角色。`system` 不是第三种角色，而是另一维度的概念（"给模型的元指令"）。
3. **支持数组：** `system` 可以是 Text Block 数组，支持 `cache_control`——这个功能在 OpenAI API 中需要以消息数组形式传递才能使用缓存。

这种设计反映了 Anthropic 对协议清晰性的追求——不同的概念用不同的数据结构表达，而非将一切都挤进消息数组。
</details>

### 问题 2（概念）

以下 Content Block 有什么错误？

```json
{
  "type": "image",
  "source": {
    "type": "file",
    "path": "/Users/me/photo.png"
  }
}
```

<details>
<summary>参考答案</summary>

两处错误：

1. **`source.type` 无效：** Image Block 只支持 `"base64"` 和 `"url"` 两种来源类型。`"file"` 不是有效的 source type。
2. **本地文件路径无法被 API 访问：** 即使 `source.type` 有效，API 服务器也无法访问客户端本地的文件路径（`/Users/me/photo.png`）。要发送本地文件，必须先读取为字节数据，进行 base64 编码，然后使用 `source.type: "base64"` 发送。

正确的做法是使用 `ImageBlock.from_file()` 方法（我们的实现中已处理）：

```json
{
  "type": "image",
  "source": {
    "type": "base64",
    "media_type": "image/png",
    "data": "iVBORw0KGgo..."
  }
}
```
</details>

### 问题 3（编码）

使用 Python `message_builder.py` 完成以下任务：

编写一个函数 `build_analysis_request(image_paths: list[str], question: str) -> MessageRequest`，它接受多个图像路径和一个问题字符串，返回一个格式正确的 MessageRequest：

- 使用顶层 `system` 参数设置指令："你是一个多图像对比分析助手。"
- 每条消息应按 `[文本指令] [图像1] [图像2] ...` 的顺序组织
- `model` 默认使用 `claude-sonnet-4-20250514`，`max_tokens` 默认 2048

```python
# 你的代码：
from message_builder import MessageRequest, Message, TextBlock, ImageBlock
from typing import List

def build_analysis_request(image_paths: List[str], question: str) -> MessageRequest:
    # TODO: 实现
    pass

# 测试：
req = build_analysis_request(
    ["chart1.png", "chart2.png"],
    "这两个图表的趋势有什么不同？"
)
print(req.to_json(indent=2))
```

<details>
<summary>参考答案</summary>

```python
from message_builder import MessageRequest, Message, TextBlock, ImageBlock

def build_analysis_request(image_paths: list[str], question: str) -> MessageRequest:
    blocks = [TextBlock(text=question)]
    for path in image_paths:
        blocks.append(ImageBlock.from_file(path))
    
    return MessageRequest(
        model="claude-sonnet-4-20250514",
        messages=[Message(role="user", content=blocks)],
        max_tokens=2048,
        system="你是一个多图像对比分析助手。",
    )
```

关键点：
- 使用 `ImageBlock.from_file()` 自动处理文件读取和 base64 编码。
- 文本 Block 放在图像 Block 之前，模型先理解问题再分析图像。
- `system` 使用顶层参数而非混入消息中。
</details>

### 问题 4（编码）

以下 TypeScript 代码构造了一个多轮对话请求，但有几处问题。找出并修复所有问题：

```typescript
const req = new MessageRequest({
  model: "claude-sonnet-4-20250514",
  messages: [
    { role: "system", content: "你是一个天气助手。" },
    Message.user("旧金山天气？"),
    new Message("user", "上海天气呢？"),  // 连续 user 消息
  ],
  maxTokens: 0,
  temperature: 2.0,
});
```

<details>
<summary>参考答案</summary>

四处错误：

1. **`role: "system"` 无效：** Messages API 不支持 `system` 角色。系统提示应使用 `system` 参数：
   ```typescript
   system: "你是一个天气助手。"
   ```

2. **连续 `user` 消息：** 两条连续的 `user` 消息会被 API 自动合并。应使用 `Message.user()` 或 `new Message("user", ...)` 构造，但确保 user/assistant 交替：
   ```typescript
   // 移除第一条 plain object 格式的消息，统一使用 Message 类
   messages: [
     Message.user("旧金山天气？"),
   ]
   ```

3. **`maxTokens: 0` 无效：** `max_tokens` 必须 >= 1。
   ```typescript
   maxTokens: 1024,
   ```

4. **`temperature: 2.0` 超出范围：** `temperature` 必须在 [0.0, 1.0] 范围内。
   ```typescript
   temperature: 0.7,  // 或移除，使用默认值 1.0
   ```

修复后的代码：
```typescript
const req = new MessageRequest({
  model: "claude-sonnet-4-20250514",
  messages: [
    Message.user("旧金山天气如何？"),
  ],
  maxTokens: 1024,
  system: "你是一个天气助手。",
});
```
</details>

---

## 2.7 本章小结

本章深入拆解了 Anthropic Messages API 的核心协议层。我们从 Content Block 类型系统的设计哲学出发，逐步解析了四种 Content Block 的结构、角色系统的规则、模型参数的精确语义，以及视觉理解协议的细节。

关键收获：

1. **Content Block 是 Messages API 的核心抽象。** 文本、图像、工具调用、工具结果——所有交互都通过统一的 Block 类型系统表达，而非通过不同的端点或参数。

2. **协议设计遵循显式优于隐式的原则。** 工具调用不是隐藏的函数调用参数，而是显式的 `tool_use` Block；系统提示不是消息角色，而是顶层参数。每一步都可追踪、可调试。

3. **参数理解影响输出质量。** `temperature` 控制随机性、`max_tokens` 控制上限、`stop_sequences` 控制终止——每个参数都有明确的适用场景。盲目使用默认值会错过优化机会。

4. **类型安全的请求构建器是生产级代码的基础。** 我们构建的 `message_builder.py` 和 `MessageBuilder.ts` 在请求到达 API 之前就捕获了常见的格式错误和参数越界，符合"fail fast"原则。

在第 5 章中，我们将探索 Messages API 的高级特性——流式处理。你将学习 Server-Sent Events 协议、增量解析 Content Block、以及如何在流式响应的同时保持对生成内容的精确控制。

---

*本章代码：`code/python/ch02/message_builder.py` | `code/node/ch02/MessageBuilder.ts`*  
*测试：`code/python/ch02/test_message_builder.py` (73 tests) | `code/node/ch02/message_builder.test.ts` (62 tests)*  
*API 参考：https://docs.anthropic.com/en/api/messages*
