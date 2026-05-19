# 第 6 章：工具调用与函数执行 —— 让 Claude 从对话走向行动

## 6.1 概念全景

### 6.1.1 Tool Use 在 Agent 架构中的定位

在 Anthropic 的 Claude API 生态中，Tool Use（工具调用）是将语言模型从"对话引擎"升级为"行动引擎"的核心机制。如果说前几章介绍的 Messages API 提供了 Claude 理解世界的"感官"，Structured Outputs 赋予了它精确输出的"表达能力"，那么 Tool Use 则赋予了 Claude **改变世界的能力**——它可以查询数据库、发送邮件、操作文件、调用第三方 API、执行代码，乃至编排多步骤的自动化工作流。

Tool Use 在整个 Agent 架构中扮演着"桥梁"角色：

```
用户请求 → Claude（推理）→ 工具调用请求 → 客户端执行 → 返回结果 → Claude（继续推理）→ 最终响应
```

这个循环被称为 **Agentic Loop（智能体循环）**。Claude 本身不执行任何工具——它只发出结构化的工具调用请求。你的应用代码负责执行这些请求并将结果返回给 Claude，然后 Claude 根据结果继续推理。这种分工使得模型可以保持纯粹的语言理解与推理能力，而将"产生副作用"的能力交给可控的应用层。

### 6.1.2 Function Calling vs Tool Use：术语辨析

如果你来自 OpenAI 生态，你可能更熟悉"Function Calling"这个术语。两者的核心思想相同——允许模型请求调用外部函数——但在 Anthropic 的语境中，**Tool Use 是更宽泛的概念**：

| 维度 | OpenAI Function Calling | Anthropic Tool Use |
|------|------------------------|-------------------|
| 执行模式 | 模型请求调用，客户端执行 | 同，但增加三种执行模式（客户端执行、Anthropic-schema 客户端执行、服务端执行） |
| 并行调用 | 支持 | 支持，默认启用 |
| 严格模式 | 通过 `strict` 参数控制 | 通过 `strict: true` + grammar-constrained sampling 实现 |
| 高级特性 | 暂无内置工具搜索/PTC | Tool Search Tool / Programmatic Tool Calling / Tool Use Examples |
| Schema 定义 | `function` + `parameters` | `tool` 块，含 `name` / `description` / `input_schema` |
| 结果返回 | `tool` role message | `tool_result` 内容块，与 user/assistant role 交错 |

"Tool Use"一词更准确地描述了 Claude 的行为——它不仅仅是"调用一个函数并获取返回值"，而是在**使用工具来完成更宏大的目标**，包括搜索、发现、选择、编排工具。

### 6.1.3 三类工具执行模式

Anthropic 将工具按**代码在哪里执行**分为三类：

**1. 用户自定义工具（客户端执行）**

这是最常见的使用场景。你定义工具的 Schema，在你的应用代码中执行逻辑，然后把结果返回给 Claude。Claude 永远看不到你的实现——它只看到 Schema 和你返回的结果。

**2. Anthropic-Schema 工具（客户端执行，训练优化）**

对于常见的开发操作（运行 Shell 命令、编辑文件、控制浏览器、管理内存），Anthropic 发布了预定义的 Schema（如 `bash_20250124`、`text_editor_20250728` 等）。这些 Schema 经过了大量训练数据的优化——Claude 已经学会如何可靠地调用它们，容错性远高于你自己定义的等价工具。执行仍在客户端进行，但 Schema 是 Anthropic 提供的。

**3. 服务端执行工具**

对于 `web_search`、`web_fetch`、`code_execution`、`tool_search`，Anthropic 在服务端运行代码。你只需在请求中启用它们，Anthropic 的服务器处理所有执行逻辑。你永远不会构造 `tool_result` 块——服务端的内部循环在响应到达你之前就已经完成了执行。

### 6.1.4 何时使用 Tool Use

**适合使用 Tool Use 的场景：**

- **有副作用的操作**：发送邮件、写入文件、更新数据库记录
- **需要外部/新鲜数据**：当前价格、天气、数据库内容
- **需要结构化输出**：需要特定 JSON 结构的场景
- **对接已有系统**：数据库、内部 API、文件系统

**不适合使用 Tool Use 的场景：**

- 模型仅凭训练数据即可回答（摘要、翻译、常识问答）
- 简单的一问一答，没有需要执行的动作
- 工具调用延迟对轻量任务来说得不偿失

一条实用法则：**如果你正在写正则表达式从模型输出中提取决策，那个决策本就该是一个工具调用**。

---

## 6.2 协议规范

### 6.2.1 Standard Tool Use 协议

#### 6.2.1.1 工具定义

每个工具通过一个 JSON 对象定义，包含以下字段：

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `name` | `string` | 是 | 工具的唯一名称。仅允许字母、数字、下划线和连字符，不超过 64 个字符。建议使用 `service_action` 命名模式（如 `github_create_pr`） |
| `description` | `string` | 否（但强烈建议） | 工具功能的详细描述，包括何时使用、返回格式等。描述质量直接影响模型的选择准确率 |
| `input_schema` | `object` | 是 | JSON Schema 格式的输入参数定义。必须包含 `type: "object"`、`properties` 和 `required`（至少为空数组 `[]`） |
| `strict` | `boolean` | 否 | 设为 `true` 启用严格模式，见 6.2.2 |
| `defer_loading` | `boolean` | 否 | 设为 `true` 延迟加载，见 6.2.3.1 |
| `allowed_callers` | `string[]` | 否 | 允许哪些上下文调用此工具，见 6.2.3.2 |
| `input_examples` | `array` | 否 | 工具调用示例，见 6.2.3.3 |

**基础示例：**

```json
{
  "name": "get_weather",
  "description": "获取指定位置的当前天气信息。返回温度、湿度、风速等数据。",
  "input_schema": {
    "type": "object",
    "properties": {
      "location": {
        "type": "string",
        "description": "城市和州/省份，例如 'San Francisco, CA'"
      },
      "unit": {
        "type": "string",
        "enum": ["celsius", "fahrenheit"],
        "description": "温度单位"
      }
    },
    "required": ["location"]
  }
}
```

#### 6.2.1.2 `tool_choice` 参数

`tool_choice` 控制 Claude 是否以及如何使用工具：

| 值 | 类型 | 说明 |
|-----|------|------|
| `{"type": "auto"}` | 默认 | Claude 自行判断是否使用工具以及使用哪个工具 |
| `{"type": "any"}` | 强制 | Claude 必须使用至少一个工具，由模型自行选择 |
| `{"type": "tool", "name": "tool_name"}` | 指定 | Claude 必须使用指定的工具 |
| `{"type": "none"}` | 禁用 | Claude 不得使用任何工具（即使 tools 参数中提供了工具定义） |
| `{"type": "auto", "disable_parallel_tool_use": true}` | 默认+串行 | Claude 最多使用一个工具 |
| `{"type": "any", "disable_parallel_tool_use": true}` | 强制+串行 | Claude 恰好使用一个工具 |

**`auto` 与 `any` 的区别：**

- `auto` 时设置 `disable_parallel_tool_use: true`，Claude 最多使用一个工具
- `any` 时设置 `disable_parallel_tool_use: true`，Claude 恰好使用一个工具

**使用建议：**

```python
# 让 Claude 自由决定
tool_choice = {"type": "auto"}

# 强制使用工具
tool_choice = {"type": "any"}

# 强制使用特定工具
tool_choice = {"type": "tool", "name": "get_weather"}
```

#### 6.2.1.3 `tool_use` / `tool_result` 内容块生命周期

Tool Use 遵循一个严格的内容块生命周期：

**阶段 1：Claude 发出 tool_use 请求**

当 Claude 决定使用工具时，API 响应的 `content` 数组中包含 `tool_use` 类型的内容块：

```json
{
  "role": "assistant",
  "content": [
    {
      "type": "text",
      "text": "让我查询旧金山的天气。"
    },
    {
      "type": "tool_use",
      "id": "toolu_01A09qGm1QxK",
      "name": "get_weather",
      "input": {
        "location": "San Francisco, CA",
        "unit": "fahrenheit"
      }
    }
  ],
  "stop_reason": "tool_use"
}
```

关键字段：
- `type`: 始终为 `"tool_use"`
- `id`: 唯一标识符，在 `tool_result` 中必须引用
- `name`: 被调用的工具名称
- `input`: JSON 对象，包含工具参数

`stop_reason` 为 `"tool_use"` 表示 Claude 在等待工具执行结果。

**阶段 2：客户端返回 tool_result**

你执行工具后，将结果包装为 `tool_result` 内容块返回：

```json
{
  "role": "user",
  "content": [
    {
      "type": "tool_result",
      "tool_use_id": "toolu_01A09qGm1QxK",
      "content": "旧金山当前天气：68°F，晴，湿度 55%，风速 5mph"
    }
  ]
}
```

关键字段：
- `type`: 始终为 `"tool_result"`
- `tool_use_id`: 必须匹配原始 `tool_use` 块的 `id`
- `content`: 字符串或内容块数组。可包含 `text` 和/或 `image` 类型块
- `is_error`: 可选布尔值，设为 `true` 表示工具执行出错

**阶段 3：Claude 处理结果并可能继续**

Claude 接收 `tool_result` 后，`stop_reason` 再次为 `"tool_use"` 时可以继续执行更多工具。你可以用 `while` 循环驱动这个过程：

```python
while response.stop_reason == "tool_use":
    tool_results = []
    for block in response.content:
        if block.type == "tool_use":
            result = execute_tool(block.name, block.input)
            tool_results.append({
                "type": "tool_result",
                "tool_use_id": block.id,
                "content": result
            })
    messages.extend([
        {"role": "assistant", "content": response.content},
        {"role": "user", "content": tool_results}
    ])
    response = client.messages.create(
        model=model, messages=messages, tools=tools
    )
```

#### 6.2.1.4 并行工具调用（Parallel Tool Calling）

Claude 4 系列模型默认支持在单次响应中调用多个工具。并行调用可以显著减少延迟——当 Claude 需要查询三个不同城市的天气时，它可以在一次 API 往返中发出三个并行的 `get_weather` 请求。

**正确的结果格式——全部在一条 user 消息中：**

```json
{
  "role": "user",
  "content": [
    {"type": "tool_result", "tool_use_id": "toolu_01", "content": "SF: 68°F"},
    {"type": "tool_result", "tool_use_id": "toolu_02", "content": "NYC: 45°F"},
    {"type": "tool_result", "tool_use_id": "toolu_03", "content": "LA: 72°F"}
  ]
}
```

**常见错误：** 将每个 `tool_result` 放在单独的 user 消息中，这会让 Claude "学到"串行调用的模式，降低后续并行调用的概率。

**禁用并行调用：**

```python
# auto 模式：最多一个工具
tool_choice = {"type": "auto", "disable_parallel_tool_use": True}

# any/tool 模式：恰好一个工具
tool_choice = {"type": "any", "disable_parallel_tool_use": True}
```

### 6.2.2 Strict Tool Use

#### 6.2.2.1 `strict: true` 模式

设置 `strict: true` 后，Anthropic 使用 **grammar-constrained sampling**（语法约束采样）来保证 Claude 的工具输入严格符合你的 JSON Schema。底层使用了与 Structured Outputs 相同的编译管道。

**为什么需要 strict 模式？**

在没有 strict 模式的情况下，Claude 可能返回类型不兼容的值（如 `"2"` 而不是 `2`，`"two"` 而不是 `2`），或遗漏必填字段。对于生产级的 Agent 系统，这种不确定性会导致运行时错误和额外的重试验证逻辑。

Strict 模式保证：
- 工具 `input` 严格符合 `input_schema`
- 工具 `name` 始终有效
- 必填字段始终存在，类型始终正确

```python
{
    "name": "book_flight",
    "description": "预订航班",
    "strict": True,  # 启用严格模式
    "input_schema": {
        "type": "object",
        "properties": {
            "origin": {"type": "string"},
            "destination": {"type": "string"},
            "passengers": {"type": "integer", "minimum": 1, "maximum": 10},
            "departure_date": {"type": "string", "format": "date"}
        },
        "required": ["origin", "destination", "passengers", "departure_date"],
        "additionalProperties": False
    }
}
```

#### 6.2.2.2 支持的 JSON Schema 子集

Strict 模式下支持的 JSON Schema 关键字（与 Structured Outputs 共享相同的限制）：

| 支持的关键字 | 说明 |
|-------------|------|
| `type: "object"` | 根类型必须为 object |
| `properties` | 对象属性定义 |
| `required` | 必填字段数组 |
| `additionalProperties` | 必须设为 `false` |
| `type: "string"` | 字符串，可配合 `enum`、`pattern` |
| `type: "integer"` | 整数，可配合 `minimum`、`maximum` |
| `type: "number"` | 浮点数，可配合 `minimum`、`maximum` |
| `type: "boolean"` | 布尔值 |
| `type: "array"` | 数组，需指定 `items` |
| `type: "null"` | null 值 |
| `enum` | 枚举值约束 |
| `pattern` | 正则表达式约束（字符串） |
| `minimum` / `maximum` | 数值范围约束 |
| `minLength` / `maxLength` | 字符串长度约束 |
| `minItems` / `maxItems` | 数组长度约束 |
| `description` | 属性描述（非验证性） |
| `$ref` | 引用支持，用于复用定义 |
| `anyOf` | 联合类型（如 `{"type": ["string", "null"]}`） |

**不支持的关键字：**
- `oneOf` / `allOf` / `not`
- `if` / `then` / `else`
- `const`
- 递归引用
- 元数据关键字如 `title`、`examples`、`default`

注意事项：
- `input_schema` 的根 `type` 必须是 `"object"`
- `additionalProperties` 必须明确设为 `false`
- Schema 中不得包含 PHI（受保护的健康信息），因为编译后的 Schema 会被缓存
- 支持模型：Claude 3.5 Sonnet 及更高版本

### 6.2.3 Advanced Tool Use（2025 年新特性）

2025 年 11 月，Anthropic 发布了三项高级工具使用特性，标志着 Tool Use 从"简单函数调用"迈向"智能编排"。这些特性在 beta 阶段，需通过 `betas=["advanced-tool-use-2025-11-20"]` 启用。

#### 6.2.3.1 Tool Search Tool：按需工具发现

**问题背景：**

在多服务 MCP 集成场景中，工具定义消耗的 Token 数量惊人。一个典型的多服务设置：
- GitHub: 35 个工具 (~26K tokens)
- Slack: 11 个工具 (~21K tokens)
- Sentry: 5 个工具 (~3K tokens)
- Jira: 约 25 个工具 (~17K tokens)

在对话还没开始前，工具定义就可能消耗 70K+ tokens。Anthropic 内部甚至见过 134K tokens 被工具定义占据的情况。

**核心机制：**

Tool Search Tool 允许 Claude 按需动态发现工具，而不是预先加载所有工具定义：

```
传统方式：所有工具定义预先加载 → ~72K tokens
使用 Tool Search：仅加载 Tool Search Tool (~500 tokens) → 按需发现 3-5 个相关工具 (~3K tokens)
Token 节省：约 95%
```

**工作原理：**

1. 引入一个 Tool Search Tool (`tool_search_tool_regex_20251119` 或 `tool_search_tool_bm25_20251119`)
2. 将大多数工具标记为 `defer_loading: true`（不提前加载）
3. 保留 3-5 个高频工具为非延迟加载（`defer_loading: false` 或省略该字段）
4. Claude 看到 Tool Search Tool + 非延迟工具
5. 当 Claude 需要其他工具时，它通过 Tool Search Tool 搜索
6. API 返回 3-5 个最相关的 `tool_reference` 块
7. 这些引用被自动展开为完整工具定义，Claude 从中选择并调用

**两种搜索变体：**

| 变体 | 类型标识 | 查询方式 | 适用场景 |
|------|---------|---------|---------|
| Regex | `tool_search_tool_regex_20251119` | Python `re.search()` 正则表达式 | 精确名称匹配、前缀/后缀匹配 |
| BM25 | `tool_search_tool_bm25_20251119` | 自然语言查询 | 语义搜索、描述性匹配 |

**Regex 查询示例：**
- `"weather"` — 匹配名称/描述中包含 "weather" 的工具
- `"get_.*_data"` — 匹配 `get_user_data`、`get_weather_data` 等
- `"database.*query|query.*database"` — OR 模式
- `"(?i)slack"` — 大小写不敏感搜索
- 最大查询长度：200 字符

**API 响应格式：**

```json
{
  "role": "assistant",
  "content": [
    {
      "type": "server_tool_use",
      "id": "srvtoolu_01ABC123",
      "name": "tool_search_tool_regex",
      "input": {"query": "weather"}
    },
    {
      "type": "tool_search_tool_result",
      "tool_use_id": "srvtoolu_01ABC123",
      "content": {
        "type": "tool_search_tool_search_result",
        "tool_references": [
          {"type": "tool_reference", "tool_name": "get_weather"}
        ]
      }
    },
    {
      "type": "tool_use",
      "id": "toolu_01XYZ789",
      "name": "get_weather",
      "input": {"location": "San Francisco", "unit": "fahrenheit"}
    }
  ],
  "stop_reason": "tool_use"
}
```

**Token 节省数学：**

| 场景 | 传统方式 | 使用 Tool Search | 节省 |
|------|---------|-----------------|------|
| 50+ 个 MCP 工具 | ~77K tokens | ~8.7K tokens | ~89% |
| 100 个工具 | ~150K tokens | ~10K tokens | ~93% |
| 10 个工具 | ~5K tokens | ~2K tokens | ~60% |

**自定义搜索工具：**

你也可以实现自己的工具搜索逻辑（如基于 Embedding 的语义搜索）。返回标准的 `tool_result` 格式，内容中包含 `tool_reference` 块：

```json
{
  "type": "tool_result",
  "tool_use_id": "toolu_custom_search",
  "content": [
    {"type": "tool_reference", "tool_name": "discovered_tool_name"}
  ]
}
```

**Model Context Protocol (MCP) 集成：**

对于 MCP 服务器，你可以延迟加载整个服务器，同时保留特定高频工具：

```json
{
  "type": "mcp_toolset",
  "mcp_server_name": "google-drive",
  "default_config": {"defer_loading": true},
  "configs": {
    "search_files": {"defer_loading": false}
  }
}
```

**适用条件：**
- 10+ 个可用工具
- 工具定义消耗 >10K tokens
- 遇到工具选择准确性问题
- 构建多服务器 MCP 系统

**限制：**
- 最大工具数量：10,000 个
- 每次搜索返回 3-5 个最相关工具
- Regex 模式最大 200 字符
- Tool Search Tool 本身不能设置 `defer_loading: true`
- 至少需要一个非延迟加载的工具
- 不支持与 Tool Use Examples 组合使用
- 模型支持：Claude Sonnet 4.0+、Opus 4.0+、Haiku 4.5+

#### 6.2.3.2 Programmatic Tool Calling：代码编排工具调用

**问题背景：**

传统 Tool Use 的两个根本性局限：
1. **上下文污染**：每个中间结果都进入 Claude 的上下文。分析 10MB 日志文件时，整个文件进入上下文窗口，然而 Claude 只需要错误频率的摘要。
2. **推理开销**：每次工具调用都需要一次完整的模型推理。5 个工具的工作流意味着 5 次推理过程，Claude 必须"肉眼"解析每个结果、比较数值、综合结论。

**核心机制：**

Programmatic Tool Calling (PTC) 让 Claude 通过编写代码来编排工具调用，而非通过独立的 API 往返。Claude 编写 Python 代码同时调用多个工具，处理它们的输出，并控制哪些信息真正进入上下文窗口。

**工作流程：**

1. **标记工具：** 为工具添加 `allowed_callers: ["code_execution_20260120"]` 选择加入 PTC
2. **Claude 编写代码：** Claude 生成 Python 编排代码
3. **代码执行环境处理工具调用：** 代码调用工具时，你收到带 `caller` 字段的 `tool_use` 请求
4. **工具结果不进入上下文：** 结果在代码执行环境中处理，而非 Claude 的上下文
5. **仅最终输出进入上下文：** 代码执行完成后，只有 `stdout` 输出返回给 Claude

**效率提升：**

| 指标 | 传统方式 | 使用 PTC | 改善 |
|------|---------|---------|------|
| Token 消耗（复杂研究） | 43,588 | 27,297 | ↓37% |
| 推理次数（20 次调用） | 20+ | 1 | ↓95% |
| 内部知识检索准确率 | 25.6% | 28.5% | ↑2.9pp |
| GIA 基准 | 46.5% | 51.2% | ↑4.7pp |

**`allowed_callers` 字段：**

| 值 | 说明 |
|-----|------|
| `["direct"]` | 仅 Claude 可以直接调用（默认） |
| `["code_execution_20260120"]` | 仅可从代码执行环境调用 |
| `["direct", "code_execution_20260120"]` | 两种方式都可调用（不推荐，Claude 可能混淆何时用哪种方式） |

**`caller` 响应字段：**

直接调用：
```json
{"type": "tool_use", "id": "toolu_abc", "name": "query_db", "input": {...},
 "caller": {"type": "direct"}}
```

程序化调用：
```json
{"type": "tool_use", "id": "toolu_xyz", "name": "query_db", "input": {...},
 "caller": {"type": "code_execution_20260120", "tool_id": "srvtoolu_abc"}}
```

**容器生命周期：**

- 每个请求创建新容器（除非复用已有容器）
- 最大生命周期 30 天，空闲 4.5 分钟后清理
- 通过 `container` 字段返回容器 ID
- 响应中包含 `expires_at` 时间戳

**约束和限制：**

- 不支持 `strict: true` 工具
- 无法通过 `tool_choice` 强制某个工具的 PTC 调用
- 不支持 `disable_parallel_tool_use: true`
- MCP 连接器提供的工具不可 PTC 调用
- PTC 响应消息只能包含 `tool_result` 块，不能包含文本内容

**适用场景：**
- 处理大型数据集，仅需聚合或摘要
- 具有 3+ 个依赖工具调用的多步骤工作流
- 需要在 Claude 看到结果前过滤、排序或转换工具结果
- 并行操作（如检查 50 个端点）
- 中间数据不应影响 Claude 推理的任务

**不适用场景：**
- 简单的单次工具调用
- Claude 需要查看并推理所有中间结果的场景
- 响应很小的快速查找

#### 6.2.3.3 Tool Use Examples：工具使用示例标准

**问题背景：**

JSON Schema 只能定义结构（类型、必填字段、枚举值），但无法表达**使用模式**：
- 何时包含可选参数？
- 哪些参数组合有意义？
- 日期用什么格式？ID 用什么约定？
- `escalation.level` 如何与 `priority` 关联？

**核心机制：**

`input_examples` 字段允许你在工具定义中直接提供调用示例。Claude 从这些示例中学习：
- 格式惯例（日期格式 `2024-11-06`，ID 格式 `USR-12345`）
- 嵌套结构模式（如何构建 reporter 对象及其嵌套的 contact 对象）
- 可选参数相关性（严重 Bug → 完整联系信息 + 严格 SLA，功能请求 → 更少的元数据）

**示例定义：**

```json
{
  "name": "create_ticket",
  "input_schema": { /* 完整 Schema */ },
  "input_examples": [
    {
      "title": "Login page returns 500 error",
      "priority": "critical",
      "labels": ["bug", "authentication", "production"],
      "reporter": {
        "id": "USR-12345",
        "name": "Jane Smith",
        "contact": {"email": "jane@acme.com", "phone": "+1-555-0123"}
      },
      "due_date": "2024-11-06",
      "escalation": {"level": 2, "notify_manager": true, "sla_hours": 4}
    },
    {
      "title": "Add dark mode support",
      "labels": ["feature-request", "ui"],
      "reporter": {"id": "USR-67890", "name": "Alex Chen"}
    },
    {
      "title": "Update API documentation"
    }
  ]
}
```

**效果：** Anthropic 内部测试显示，复杂参数处理的准确率从 72% 提升至 90%。

**最佳实践：**
- 使用真实数据（真实的城市名称、合理的价格，而非 "string" 或 "value"）
- 展示多样性：最小化、部分和完整参数的示例
- 每个工具 1-5 个示例
- 只在 Schema 不足以表达正确用法的模糊处添加示例
- 不能与 Tool Search Tool 组合使用

---

## 6.3 Python 实现

### 6.3.1 ToolRegistry：工具注册与管理

`ToolRegistry` 是工具调用系统的基础设施。它管理工具定义的注册、延迟加载策略、允许调用者配置，并提供统一的 API 格式转换。

```python
# tool_registry.py
from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional


@dataclass
class ToolDefinition:
    """单个工具的完整定义。"""
    name: str
    description: str
    input_schema: Dict[str, Any]
    handler: Callable[..., Any]
    defer_loading: bool = False
    allowed_callers: Optional[List[str]] = None
    input_examples: Optional[List[Dict[str, Any]]] = None
    strict: bool = False

    def to_api_format(self) -> dict:
        """转换为 Anthropic API 工具格式。"""
        tool: Dict[str, Any] = {
            "name": self.name,
            "description": self.description,
            "input_schema": self.input_schema,
        }
        if self.defer_loading:
            tool["defer_loading"] = True
        if self.allowed_callers:
            tool["allowed_callers"] = self.allowed_callers
        if self.input_examples:
            tool["input_examples"] = self.input_examples
        if self.strict:
            tool["strict"] = True
        return tool


class ToolRegistry:
    """工具注册表：管理工具定义、执行处理函数和 API 格式转换。

    用法::

        registry = ToolRegistry()
        registry.register(
            name="get_weather",
            description="获取指定位置的天气",
            input_schema={...},
            handler=lambda location, unit="celsius": {...},
        )
        tools = registry.to_api_format()
    """

    def __init__(self) -> None:
        self._tools: Dict[str, ToolDefinition] = {}
        self._search_tool_enabled: bool = False
        self._code_execution_enabled: bool = False

    # ------------------------------------------------------------------
    # Registration
    # ------------------------------------------------------------------

    def register(
        self,
        name: str,
        description: str,
        input_schema: Dict[str, Any],
        handler: Callable[..., Any],
        defer_loading: bool = False,
        allowed_callers: Optional[List[str]] = None,
        input_examples: Optional[List[Dict[str, Any]]] = None,
        strict: bool = False,
    ) -> None:
        """注册一个工具。

        Args:
            name: 工具唯一名称。
            description: 工具功能描述，包括返回格式。
            input_schema: JSON Schema 格式的输入参数定义。
            handler: 工具执行函数，接收 ``**kwargs``。
            defer_loading: 设为 True 启用延迟加载（需配合 Tool Search Tool 使用）。
            allowed_callers: 允许调用此工具的上下文列表。
                可选值：``["direct"]``、``["code_execution_20260120"]``。
            input_examples: 工具使用示例列表。
            strict: 设置为 True 启用 Strict Tool Use 模式。

        Raises:
            ValueError: 工具名称已注册时抛出。
        """
        if name in self._tools:
            raise ValueError(f"Tool '{name}' is already registered")
        # 验证 handler 可调用
        if not callable(handler):
            raise ValueError(f"Handler for tool '{name}' must be callable")
        # 验证 input_schema 基本结构
        if not isinstance(input_schema, dict) or input_schema.get("type") != "object":
            raise ValueError(f"input_schema must be a JSON Schema object with type='object'")
        self._tools[name] = ToolDefinition(
            name=name,
            description=description,
            input_schema=input_schema,
            handler=handler,
            defer_loading=defer_loading,
            allowed_callers=allowed_callers,
            input_examples=input_examples,
            strict=strict,
        )

    def unregister(self, name: str) -> None:
        """移除已注册的工具。"""
        self._tools.pop(name, None)

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    def get(self, name: str) -> Optional[ToolDefinition]:
        """按名称获取工具定义。"""
        return self._tools.get(name)

    def list_names(self) -> List[str]:
        """返回所有已注册工具的名称列表。"""
        return list(self._tools.keys())

    def get_deferred_tools(self) -> List[ToolDefinition]:
        """返回所有标记为延迟加载的工具。"""
        return [t for t in self._tools.values() if t.defer_loading]

    def get_immediate_tools(self) -> List[ToolDefinition]:
        """返回所有非延迟加载的工具。"""
        return [t for t in self._tools.values() if not t.defer_loading]

    def get_programmatic_tools(self) -> List[ToolDefinition]:
        """返回允许从代码执行环境调用的工具。"""
        return [t for t in self._tools.values() if t.allowed_callers and "code_execution_20260120" in t.allowed_callers]

    def count(self) -> int:
        """返回已注册工具总数。"""
        return len(self._tools)

    # ------------------------------------------------------------------
    # API format
    # ------------------------------------------------------------------

    def to_api_format(self, include_deferred: bool = True) -> List[Dict[str, Any]]:
        """生成 Anthropic API 兼容的工具列表。

        Args:
            include_deferred: 是否包含延迟加载的工具定义。
                即使不包含，API 仍需要它们来展开 tool_reference。
        """
        result: List[Dict[str, Any]] = []
        for tool in self._tools.values():
            result.append(tool.to_api_format())
        return result

    def to_search_index_format(self) -> List[Dict[str, Any]]:
        """生成用于搜索索引的工具列表（名称、描述、参数）。"""
        result = []
        for tool in self._tools.values():
            if tool.defer_loading:
                result.append({
                    "name": tool.name,
                    "description": tool.description,
                    "input_schema": tool.input_schema,
                })
        return result

    # ------------------------------------------------------------------
    # Execution
    # ------------------------------------------------------------------

    def execute(self, tool_name: str, input_data: Dict[str, Any]) -> Dict[str, Any]:
        """执行指定工具的处理器函数。

        Args:
            tool_name: 要执行的工具名称。
            input_data: 工具参数字典。

        Returns:
            包含 ``success`` 和 ``result`` 或 ``error`` 的字典。

        Raises:
            KeyError: 工具未注册。
        """
        tool = self._tools.get(tool_name)
        if tool is None:
            raise KeyError(f"Tool '{tool_name}' not found in registry")
        try:
            result = tool.handler(**input_data)
            return {"success": True, "result": result}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def execute_many(
        self, calls: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """批量执行多个工具调用。

        Args:
            calls: 工具调用列表，每项含 ``tool_name`` 和 ``input``。

        Returns:
            按输入顺序排列的结果列表。
        """
        results = []
        for call in calls:
            results.append(
                self.execute(call["tool_name"], call["input"])
            )
        return results

    # ------------------------------------------------------------------
    # Search functionality
    # ------------------------------------------------------------------

    def enable_tool_search(self) -> None:
        """启用工具搜索功能（注册内置的 regex 搜索工具）。"""
        self._search_tool_enabled = True

    def enable_code_execution(self) -> None:
        """启用代码执行功能。"""
        self._code_execution_enabled = True

    def is_search_enabled(self) -> bool:
        return self._search_tool_enabled

    def is_code_execution_enabled(self) -> bool:
        return self._code_execution_enabled
```

### 6.3.2 ProgrammaticToolCaller：代码编排工具调用

```python
# programmatic_tool_caller.py
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class CodeExecutionResult:
    """代码执行的结果封装。"""
    stdout: str = ""
    stderr: str = ""
    return_code: int = 0
    container_id: Optional[str] = None
    expires_at: Optional[str] = None


@dataclass
class ProgrammaticToolCall:
    """程序化工具调用记录。"""
    tool_name: str
    input_data: Dict[str, Any]
    caller_tool_id: str
    tool_use_id: str


class ProgrammaticToolCaller:
    """管理 Claude 通过代码执行环境进行程序化工具调用。

    该类模拟了 Anthropic 的代码执行环境行为——工具调用在沙箱中处理，
    只有最终的 stdout 输出返回给模型上下文。

    用法::

        ptc = ProgrammaticToolCaller(registry)
        result = ptc.execute_code('''
            data = query_database("SELECT * FROM orders")
            summary = summarize(data)
            print(json.dumps(summary))
        ''')
    """

    def __init__(self, registry: Any = None):
        """初始化程序化工具调用器。

        Args:
            registry: ToolRegistry 实例，用于解析工具调用。
        """
        self._registry = registry
        self._container_id: Optional[str] = None
        self._pending_calls: List[ProgrammaticToolCall] = []

    # ------------------------------------------------------------------
    # Code execution
    # ------------------------------------------------------------------

    def execute_code(self, code: str) -> CodeExecutionResult:
        """解析并模拟执行编排代码。

        这不是真正的沙箱执行——它通过解析代码中的函数调用来
        识别期望的工具调用，然后将它们记录为待处理调用。

        Args:
            code: Claude 生成的 Python 编排代码。

        Returns:
            包含 stdout、stderr 和 return_code 的 CodeExecutionResult。
        """
        # 解析代码中的工具调用（函数调用模式匹配）
        tool_calls = self._extract_tool_calls(code)

        if not tool_calls:
            return CodeExecutionResult(
                stdout="",
                stderr="No tool calls found in code",
                return_code=0,
            )

        # 在完整的实现中，这些调用将与注册表中的处理函数进行匹配
        return CodeExecutionResult(
            stdout="",
            stderr="",
            return_code=0,
        )

    def _extract_tool_calls(self, code: str) -> List[ProgrammaticToolCall]:
        """从代码中提取工具调用。

        寻找模式如 ``result = await tool_name(...)`` 或 ``tool_name(...)``。

        这是一个简化的解析器；完整的实现会使用 AST 解析。
        """
        import re

        calls = []
        # 匹配 ``await function_name(args)`` 或 ``function_name(args)``
        pattern = r'(?:await\s+)?(\w+)\s*\(\s*(.*?)\s*\)'
        for match in re.finditer(pattern, code):
            func_name = match.group(1)
            call = ProgrammaticToolCall(
                tool_name=func_name,
                input_data={},  # 简化实现
                caller_tool_id="",
                tool_use_id=f"toolu_{len(calls):04d}",
            )
            calls.append(call)
        return calls

    # ------------------------------------------------------------------
    # Tool result handling
    # ------------------------------------------------------------------

    def process_tool_results(self, results: List[Dict[str, Any]]) -> str:
        """处理工具执行结果，生成最终输出。

        将每个工具结果序列化为 JSON 行，模拟代码脚本处理完所有工具调用后
        通过 ``print()`` 输出的内容。

        Args:
            results: 工具执行结果列表，每项含 ``tool_name`` 和 ``result``。

        Returns:
            格式化的最终输出字符串。
        """
        import json

        lines = []
        for result in results:
            lines.append(json.dumps(result, ensure_ascii=False))
        return "\n".join(lines)

    # ------------------------------------------------------------------
    # Container management
    # ------------------------------------------------------------------

    @property
    def container_id(self) -> Optional[str]:
        """当前容器 ID。"""
        return self._container_id

    def set_container(self, container_id: str) -> None:
        """设置要复用的容器 ID。"""
        self._container_id = container_id

    def reset_container(self) -> None:
        """清除容器状态。"""
        self._container_id = None
        self._pending_calls.clear()

    @property
    def has_pending_calls(self) -> bool:
        """是否有待处理的工具调用。"""
        return len(self._pending_calls) > 0
```

### 6.3.3 EmbeddingToolSearch：基于 Embedding 的工具搜索

```python
# tool_search.py
from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple


@dataclass
class ToolSearchEntry:
    """工具搜索索引中的条目。"""
    name: str
    description: str
    input_schema: Dict[str, Any]

    def to_search_text(self) -> str:
        """生成用于搜索的文本表示。

        将工具名称、描述和参数名/描述拼接为一段文本，
        用于生成 embedding 或进行关键词匹配。
        """
        parts = [self.name, self.description]
        props = self.input_schema.get("properties", {})
        for prop_name, prop_def in props.items():
            parts.append(prop_name)
            if isinstance(prop_def, dict):
                desc = prop_def.get("description", "")
                if desc:
                    parts.append(desc)
        return " ".join(parts)


class EmbeddingToolSearch:
    """基于 Embedding 的语义工具搜索。

    支持两种搜索策略：
    1. **TensorFlow/PyTorch 生成的 Embedding**：余弦相似度匹配
    2. **关键词回退**：当无 embedding 模型可用时的 TF-IDF 近似

    用法::

        search = EmbeddingToolSearch()
        search.index_tools(registry.to_search_index_format())
        results = search.search("weather forecast san francisco", top_k=3)
    """

    def __init__(self, embedding_dim: int = 384):
        """初始化搜索器。

        Args:
            embedding_dim: Embedding 向量维度（默认 384，匹配 MiniLM）。
        """
        self._tools: List[ToolSearchEntry] = []
        self._embeddings: Optional[List[List[float]]] = None
        self._embedding_dim = embedding_dim

    # ------------------------------------------------------------------
    # Indexing
    # ------------------------------------------------------------------

    def index_tools(self, tools: List[Dict[str, Any]]) -> None:
        """使用工具定义构建搜索索引。

        Args:
            tools: 工具定义列表，每项含 ``name``、``description``、``input_schema``。
        """
        self._tools = []
        for tool in tools:
            entry = ToolSearchEntry(
                name=tool["name"],
                description=tool.get("description", ""),
                input_schema=tool.get("input_schema", {"type": "object", "properties": {}}),
            )
            self._tools.append(entry)
        # 生成占位 embeddings（实际使用时会替换为真实模型输出）
        self._embeddings = self._compute_embeddings([t.to_search_text() for t in self._tools])

    def _compute_embeddings(self, texts: List[str]) -> List[List[float]]:
        """计算文本的 embedding 向量。

        在生产环境中，会使用真实的 embedding 模型（如 MiniLM、text-embedding-3-small）。
        此处提供关键词频率向量的简化实现，用于演示和测试。
        """
        # 构建全局词汇表
        vocab: Dict[str, int] = {}
        tokenized = []
        for text in texts:
            tokens = text.lower().split()
            tokenized.append(tokens)
            for token in tokens:
                vocab[token] = vocab.get(token, 0) + 1

        # 为每个词汇分配维度索引（使用哈希）
        embeddings = []
        for tokens in tokenized:
            vec = [0.0] * self._embedding_dim
            for token in tokens:
                idx = hash(token) % self._embedding_dim
                vec[idx] += 1.0
            # 归一化
            norm = sum(v * v for v in vec) ** 0.5
            if norm > 0:
                vec = [v / norm for v in vec]
            embeddings.append(vec)

        return embeddings

    # ------------------------------------------------------------------
    # Search
    # ------------------------------------------------------------------

    def search(self, query: str, top_k: int = 5) -> List[Dict[str, Any]]:
        """搜索与查询最相关的工具。

        使用余弦相似度进行语义匹配。

        Args:
            query: 搜索查询（自然语言描述用户需求）。
            top_k: 返回的最相关工具数量。

        Returns:
            按相关性降序排列的搜索结果列表，每项含 ``name``、``description``、
            ``input_schema`` 和 ``score``（0-1 之间的相似度分数）。
        """
        if not self._tools or self._embeddings is None:
            return []

        query_embedding = self._compute_embeddings([query])[0]
        scores: List[Tuple[int, float]] = []

        for i, emb in enumerate(self._embeddings):
            similarity = self._cosine_similarity(query_embedding, emb)
            scores.append((i, similarity))

        # 按相似度降序排序
        scores.sort(key=lambda x: x[1], reverse=True)

        results = []
        for idx, score in scores[:top_k]:
            if score > 0:
                tool = self._tools[idx]
                results.append({
                    "name": tool.name,
                    "description": tool.description,
                    "input_schema": tool.input_schema,
                    "score": round(score, 4),
                })

        return results

    def search_by_regex(self, pattern: str) -> List[Dict[str, Any]]:
        """使用正则表达式搜索工具（模拟 Tool Search Tool 的 regex 模式）。

        Args:
            pattern: Python 正则表达式模式。

        Returns:
            匹配的工具列表。
        """
        import re

        results = []
        for tool in self._tools:
            search_text = tool.to_search_text()
            if re.search(pattern, search_text):
                results.append({
                    "name": tool.name,
                    "description": tool.description,
                    "input_schema": tool.input_schema,
                })
        return results

    # ------------------------------------------------------------------
    # Utilities
    # ------------------------------------------------------------------

    @staticmethod
    def _cosine_similarity(a: List[float], b: List[float]) -> float:
        """计算两个向量的余弦相似度。"""
        if len(a) != len(b):
            raise ValueError("向量维度不匹配")
        dot = sum(x * y for x, y in zip(a, b))
        norm_a = sum(x * x for x in a) ** 0.5
        norm_b = sum(x * x for x in b) ** 0.5
        if norm_a == 0 or norm_b == 0:
            return 0.0
        return dot / (norm_a * norm_b)

    @property
    def tool_count(self) -> int:
        """已索引工具的数量。"""
        return len(self._tools)

    @property
    def embedding_dim(self) -> int:
        """Embedding 向量维度。"""
        return self._embedding_dim
```

---

## 6.4 Node.js 实现

### 6.4.1 ToolRegistry：TypeScript 工具注册与管理

```typescript
// ToolRegistry.ts

export interface JsonSchema {
  type: "object";
  properties: Record<string, Record<string, unknown>>;
  required?: string[];
  additionalProperties?: boolean;
}

export interface ToolDefinition {
  name: string;
  description: string;
  input_schema: JsonSchema;
  handler: (...args: any[]) => any;
  defer_loading?: boolean;
  allowed_callers?: string[];
  input_examples?: Record<string, unknown>[];
  strict?: boolean;
}

export type ToolHandler = (...args: any[]) => any;

export interface ToolCall {
  tool_name: string;
  input: Record<string, unknown>;
}

export interface ToolResult {
  success: boolean;
  result?: unknown;
  error?: string;
}

/**
 * 工具注册表：管理 Anthropic Tool Use 的工具定义、延迟加载策略和执行。
 */
export class ToolRegistry {
  private tools: Map<string, ToolDefinition> = new Map();
  private searchToolEnabled: boolean = false;
  private codeExecutionEnabled: boolean = false;

  // ------------------------------------------------------------------
  // Registration
  // ------------------------------------------------------------------

  register(
    name: string,
    description: string,
    input_schema: JsonSchema,
    handler: ToolHandler,
    options: {
      defer_loading?: boolean;
      allowed_callers?: string[];
      input_examples?: Record<string, unknown>[];
      strict?: boolean;
    } = {},
  ): void {
    if (this.tools.has(name)) {
      throw new Error(`Tool '${name}' is already registered`);
    }
    if (typeof handler !== "function") {
      throw new Error(`Handler for tool '${name}' must be a function`);
    }
    if (!input_schema || input_schema.type !== "object") {
      throw new Error(
        `input_schema must be a JSON Schema object with type='object'`,
      );
    }
    this.tools.set(name, {
      name,
      description,
      input_schema,
      handler,
      defer_loading: options.defer_loading ?? false,
      allowed_callers: options.allowed_callers,
      input_examples: options.input_examples,
      strict: options.strict ?? false,
    });
  }

  unregister(name: string): void {
    this.tools.delete(name);
  }

  // ------------------------------------------------------------------
  // Queries
  // ------------------------------------------------------------------

  get(name: string): ToolDefinition | undefined {
    return this.tools.get(name);
  }

  listNames(): string[] {
    return Array.from(this.tools.keys());
  }

  getDeferredTools(): ToolDefinition[] {
    return Array.from(this.tools.values()).filter((t) => t.defer_loading);
  }

  getImmediateTools(): ToolDefinition[] {
    return Array.from(this.tools.values()).filter((t) => !t.defer_loading);
  }

  getProgrammaticTools(): ToolDefinition[] {
    return Array.from(this.tools.values()).filter(
      (t) =>
        t.allowed_callers &&
        t.allowed_callers.includes("code_execution_20260120"),
    );
  }

  count(): number {
    return this.tools.size;
  }

  // ------------------------------------------------------------------
  // API format
  // ------------------------------------------------------------------

  toApiFormat(): Record<string, unknown>[] {
    const result: Record<string, unknown>[] = [];
    for (const tool of this.tools.values()) {
      const entry: Record<string, unknown> = {
        name: tool.name,
        description: tool.description,
        input_schema: tool.input_schema,
      };
      if (tool.defer_loading) entry["defer_loading"] = true;
      if (tool.allowed_callers) entry["allowed_callers"] = tool.allowed_callers;
      if (tool.input_examples) entry["input_examples"] = tool.input_examples;
      if (tool.strict) entry["strict"] = true;
      result.push(entry);
    }
    return result;
  }

  toSearchIndexFormat(): Record<string, unknown>[] {
    const result: Record<string, unknown>[] = [];
    for (const tool of this.tools.values()) {
      if (tool.defer_loading) {
        result.push({
          name: tool.name,
          description: tool.description,
          input_schema: tool.input_schema,
        });
      }
    }
    return result;
  }

  // ------------------------------------------------------------------
  // Execution
  // ------------------------------------------------------------------

  execute(toolName: string, inputData: Record<string, unknown>): ToolResult {
    const tool = this.tools.get(toolName);
    if (!tool) {
      throw new Error(`Tool '${toolName}' not found in registry`);
    }
    try {
      const result = tool.handler(inputData);
      return { success: true, result };
    } catch (e: unknown) {
      return {
        success: false,
        error: e instanceof Error ? e.message : String(e),
      };
    }
  }

  executeMany(calls: ToolCall[]): ToolResult[] {
    return calls.map((call) => this.execute(call.tool_name, call.input));
  }

  // ------------------------------------------------------------------
  // Feature toggles
  // ------------------------------------------------------------------

  enableToolSearch(): void {
    this.searchToolEnabled = true;
  }

  enableCodeExecution(): void {
    this.codeExecutionEnabled = true;
  }

  isSearchEnabled(): boolean {
    return this.searchToolEnabled;
  }

  isCodeExecutionEnabled(): boolean {
    return this.codeExecutionEnabled;
  }
}
```

### 6.4.2 ProgrammaticToolCaller：代码编排工具调用

```typescript
// ProgrammaticToolCaller.ts

export interface CodeExecutionResult {
  stdout: string;
  stderr: string;
  return_code: number;
}

export interface ProgrammaticToolCallRecord {
  tool_name: string;
  input_data: Record<string, unknown>;
  caller_tool_id: string;
  tool_use_id: string;
}

/**
 * 程序化工具调用器：模拟 Anthropic 的代码执行环境中的工具编排。
 */
export class ProgrammaticToolCaller {
  private containerId: string | null = null;
  private pendingCalls: ProgrammaticToolCallRecord[] = [];

  /**
   * 解析并提取编排代码中的工具调用。
   *
   * @param code - Claude 生成的 Python 编排代码
   * @returns 提取的 CodeExecutionResult
   */
  executeCode(code: string): CodeExecutionResult {
    const toolCalls = this.extractToolCalls(code);

    if (toolCalls.length === 0) {
      return {
        stdout: "",
        stderr: "No tool calls found in code",
        return_code: 0,
      };
    }

    this.pendingCalls = toolCalls;

    return {
      stdout: "",
      stderr: "",
      return_code: 0,
    };
  }

  /**
   * 从代码字符串中提取函数调用模式。
   *
   * 匹配 ``await function_name(args)`` 和 ``function_name(args)`` 模式。
   */
  extractToolCalls(code: string): ProgrammaticToolCallRecord[] {
    const calls: ProgrammaticToolCallRecord[] = [];
    const pattern = /(?:await\s+)?(\w+)\s*\(\s*(.*?)\s*\)/g;
    let match: RegExpExecArray | null;

    while ((match = pattern.exec(code)) !== null) {
      const funcName = match[1]!;
      calls.push({
        tool_name: funcName,
        input_data: {},
        caller_tool_id: "",
        tool_use_id: `toolu_${calls.length.toString().padStart(4, "0")}`,
      });
    }

    return calls;
  }

  /**
   * 处理工具执行结果，生成最终输出。
   */
  processToolResults(results: Array<{ tool_name: string; result: unknown }>): string {
    const lines = results.map((r) => JSON.stringify(r));
    return lines.join("\n");
  }

  // ------------------------------------------------------------------
  // Container management
  // ------------------------------------------------------------------

  setContainer(containerId: string): void {
    this.containerId = containerId;
  }

  resetContainer(): void {
    this.containerId = null;
    this.pendingCalls = [];
  }

  getContainerId(): string | null {
    return this.containerId;
  }

  hasPendingCalls(): boolean {
    return this.pendingCalls.length > 0;
  }
}
```

### 6.4.3 ToolSearch：基于 Embedding 的工具搜索

```typescript
// ToolSearch.ts

interface ToolSearchEntry {
  name: string;
  description: string;
  input_schema: Record<string, unknown>;
}

interface SearchResult {
  name: string;
  description: string;
  input_schema: Record<string, unknown>;
  score: number;
}

/**
 * 基于 Embedding 的语义工具搜索。
 *
 * 支持：
 * 1. 余弦相似度语义搜索
 * 2. 正则表达式精确搜索
 *
 * 用法::
 *
 *   const search = new EmbeddingToolSearch();
 *   search.indexTools([...toolDefinitions]);
 *   const results = search.search("weather forecast", 3);
 */
export class EmbeddingToolSearch {
  private tools: ToolSearchEntry[] = [];
  private embeddings: number[][] | null = null;
  private readonly embeddingDim: number;

  constructor(embeddingDim: number = 384) {
    this.embeddingDim = embeddingDim;
  }

  // ------------------------------------------------------------------
  // Indexing
  // ------------------------------------------------------------------

  indexTools(tools: Array<{ name: string; description: string; input_schema: Record<string, unknown> }>): void {
    this.tools = tools.map((t) => ({
      name: t.name,
      description: t.description ?? "",
      input_schema: t.input_schema ?? { type: "object", properties: {} },
    }));

    const texts = this.tools.map((t) => this.toSearchText(t));
    this.embeddings = this.computeEmbeddings(texts);
  }

  private toSearchText(entry: ToolSearchEntry): string {
    const parts: string[] = [entry.name, entry.description];
    const props = (entry.input_schema as any).properties ?? {};
    for (const [propName, propDef] of Object.entries(props)) {
      parts.push(propName);
      if (typeof propDef === "object" && propDef && "description" in propDef) {
        parts.push((propDef as any).description as string);
      }
    }
    return parts.join(" ");
  }

  private computeEmbeddings(texts: string[]): number[][] {
    // 构建词汇表
    const vocab = new Map<string, number>();
    const tokenized = texts.map((t) => {
      const tokens = t.toLowerCase().split(/\s+/);
      for (const tok of tokens) {
        vocab.set(tok, (vocab.get(tok) ?? 0) + 1);
      }
      return tokens;
    });

    // 生成 embedding 向量（哈希基）
    return tokenized.map((tokens) => {
      const vec = new Array<number>(this.embeddingDim).fill(0);
      for (const token of tokens) {
        const idx = this.hashToken(token) % this.embeddingDim;
        vec[idx] += 1.0;
      }
      // 归一化
      const norm = Math.sqrt(vec.reduce((s, v) => s + v * v, 0));
      if (norm > 0) {
        for (let i = 0; i < vec.length; i++) {
          vec[i] /= norm;
        }
      }
      return vec;
    });
  }

  private hashToken(token: string): number {
    let hash = 0;
    for (let i = 0; i < token.length; i++) {
      const char = token.charCodeAt(i);
      hash = ((hash << 5) - hash + char) | 0;
    }
    return Math.abs(hash);
  }

  // ------------------------------------------------------------------
  // Search
  // ------------------------------------------------------------------

  search(query: string, topK: number = 5): SearchResult[] {
    if (this.tools.length === 0 || !this.embeddings) {
      return [];
    }

    const queryEmbedding = this.computeEmbeddings([query])[0]!;
    const scores: Array<{ index: number; score: number }> = [];

    for (let i = 0; i < this.embeddings.length; i++) {
      const similarity = EmbeddingToolSearch.cosineSimilarity(
        queryEmbedding,
        this.embeddings[i]!,
      );
      scores.push({ index: i, score: similarity });
    }

    scores.sort((a, b) => b.score - a.score);

    return scores.slice(0, topK).map(({ index, score }) => ({
      name: this.tools[index]!.name,
      description: this.tools[index]!.description,
      input_schema: this.tools[index]!.input_schema,
      score: Math.round(score * 10000) / 10000,
    }));
  }

  searchByRegex(pattern: string): Array<{ name: string; description: string; input_schema: Record<string, unknown> }> {
    const regex = new RegExp(pattern);
    return this.tools
      .filter((t) => regex.test(this.toSearchText(t)))
      .map((t) => ({
        name: t.name,
        description: t.description,
        input_schema: t.input_schema,
      }));
  }

  // ------------------------------------------------------------------
  // Utilities
  // ------------------------------------------------------------------

  static cosineSimilarity(a: number[], b: number[]): number {
    if (a.length !== b.length) {
      throw new Error("Vector dimension mismatch");
    }
    let dot = 0;
    let normA = 0;
    let normB = 0;
    for (let i = 0; i < a.length; i++) {
      dot += a[i]! * b[i]!;
      normA += a[i]! * a[i]!;
      normB += b[i]! * b[i]!;
    }
    if (normA === 0 || normB === 0) return 0;
    return dot / (Math.sqrt(normA) * Math.sqrt(normB));
  }

  getToolCount(): number {
    return this.tools.length;
  }

  getEmbeddingDim(): number {
    return this.embeddingDim;
  }
}
```

---

## 6.5 最佳实践

### 6.5.1 工具设计模式

**1. 描述即文档**

工具描述是 Claude 理解何时以及如何使用工具的唯一途径。描述应包含：
- 工具的**功能**：它做什么
- 工具的**适用场景**：何时应该使用它
- **返回格式**：返回值的数据结构和字段含义

```python
# 好的描述
{
    "name": "search_customer_orders",
    "description": "按日期范围、状态或金额搜索客户订单。"
                    "返回订单详情列表，每项包含：id (str)、total (float, USD)、"
                    "status (str: pending/shipped/delivered)、items (list)、"
                    "created_at (str: ISO 8601)"
}

# 不好的描述
{
    "name": "query_db_orders",
    "description": "Execute order query"
}
```

**2. 命名空间化工具名称**

使用 `domain_action` 模式命名工具，使搜索更精准：

- `github_create_pr`, `github_list_issues`, `github_search_code`
- `slack_send_message`, `slack_list_channels`, `slack_search_messages`

**3. 每工具单一职责**

每个工具应只做一件事。如果某个工具的参数组合会导致两种完全不同的行为，请将其拆分为两个独立工具。这不仅让 Claude 更容易选择正确的工具，也让 Tool Search Tool 的匹配更精准。

### 6.5.2 defer_loading 策略

**何时标记为 defer_loading？**

| 工具特征 | 是否延迟 | 原因 |
|---------|---------|------|
| 高频使用（每对话都用） | 否 | 避免不必要的搜索步骤 |
| 仅特定场景使用 | 是 | 节省上下文空间 |
| 工具名称与描述相似于其他工具 | 是 | 减少选择混淆 |
| 工具定义非常大（>500 tokens） | 是 | 按需加载节省最多 |
| 关键/核心工具 | 否 | 始终可用的保证 |

**最佳实践：**
- 保持 3-5 个最常用工具为非延迟
- 在系统提示中告知 Claude 可用工具类别："你可以搜索 Slack、GitHub 和 Jira 的相关工具"
- 监控 Claude 发现哪些工具，据此调整描述和延迟策略
- 对于 MCP 服务器，对整个服务器设置 `default_config: {defer_loading: true}`，仅保留 1-2 个高频工具为非延迟

### 6.5.3 PTC vs 标准 Tool Calling：何时用哪个

**使用 Programmatic Tool Calling 的信号：**

1. **中间结果是噪音**：当你只需要聚合结果而非原始数据时（如预算合规检查只需"谁超支了"，而非 2000+ 条费用明细）
2. **工具调用有 >2 个依赖链**：如需先查 A 再根据 A 的结果查 B 和 C，然后在 B 和 C 之间做条件判断
3. **大量并行操作**：对 50 个端点做健康检查——PTC 一个代码块完成，传统方式 50 次推理
4. **数据处理在模型外更高效**：排序、过滤、聚合、数据转换等逻辑更适合 Python 代码

**使用标准 Tool Calling 的信号：**

1. **单个简单的工具调用**：PTC 的代码执行开销不值得
2. **Claude 需要理解中间结果**：推理依赖每个中间步骤的语义理解
3. **需要用户交互**：标准调用更适合需要用户确认的流程

**混合使用策略：**

你可以在同一应用中同时使用两种方式。关键工具保持标准调用（`allowed_callers: ["direct"]`），数据处理工具切换为 PTC（`allowed_callers: ["code_execution_20260120"]`）。

### 6.5.4 三层功能策略组合

Anthropic 推荐按瓶颈优先级分层使用三项高级特性：

```
第一步：诊断最大瓶颈
  ├── 上下文膨胀 from 工具定义 → Tool Search Tool
  ├── 中间结果污染上下文 → Programmatic Tool Calling
  └── 参数错误/畸形调用 → Tool Use Examples

第二步：叠加互补功能
  Tool Search → 确保找到正确工具
  PTC → 确保高效执行
  Examples → 确保正确调用
```

### 6.5.5 并行调用优化

**强制并行调用：**

```python
system_prompt = """当需要查询多个独立数据时，请一次性发出所有工具调用。
例如：查询三个城市的天气时，同时调用 get_weather（SF）、get_weather（NYC）、
get_weather（LA），不要分三次逐一调用。"""
```

**结果格式验证：**

所有并行调用的结果必须放在**单条 user 消息**中。将结果分散在多条消息中是降低并行调用率的最常见错误。

---

## 6.6 自测题

**题目 1（理论）**：Tool Use 的 `stop_reason` 为 `"tool_use"` 表示什么？Agentic Loop 的退出条件是什么？

**题目 2（理论）**：解释 `tool_choice` 参数中 `auto`、`any`、`none` 和 `{"type": "tool", "name": "X"}` 之间的区别。当设置 `disable_parallel_tool_use: true` 时，`auto` 和 `any` 的行为有何不同？

**题目 3（编码）**：使用 `ToolRegistry` 注册三个工具：`get_weather`（参数：`location`）、`get_time`（参数：`timezone`）、`search_news`（参数：`query`），其中 `search_news` 需要 `defer_loading: true`。编写一个助手函数将注册表的输出转换为 Anthropic API 格式，并包含一个 Regex Tool Search Tool。验证 `get_deferred_tools()` 只返回 `search_news`。

**题目 4（编码）**：使用 `EmbeddingToolSearch` 索引 10 个工具，然后执行查询 `"send message to slack"`，返回 top_k=3 的结果。验证返回结果的 `score` 字段在 0 到 1 之间且按降序排列。

**题目 5（设计）**：你需要构建一个 Agent 来管理数据库运维任务，涉及 3 个 MCP 服务器：GitHub（35 个工具）、Slack（11 个工具）和企业内部数据库（50 个工具）。Agent 常见任务是"分析慢查询日志并将结果通过 Slack 发送给值班工程师"。请设计工具加载策略（哪些工具非延迟、哪些延迟）和 PTC 使用策略（哪些操作应通过 PTC 执行）。解释你的设计选择背后的 Token 节省估算。

---

> **本章小结：** Tool Use 是 Claude 从对话模型升级为 Agent 系统的核心原语。Standard Tool Use 提供了基础的工具调用协议（定义、选择、执行、结果返回），Strict Tool Use 通过语法约束保证类型安全。2025 年的 Advanced Tool Use 三项特性将 Tool Use 推向新高度：Tool Search Tool 实现了按需工具发现（Token 节省高达 95%），Programmatic Tool Calling 通过代码编排实现了上下文隔离和推理次数的大幅减少，Tool Use Examples 提供了超越 Schema 的使用模式教学。掌握这些协议和最佳实践，你就能构建出可靠、高效、可扩展的 Claude Agent 系统。
