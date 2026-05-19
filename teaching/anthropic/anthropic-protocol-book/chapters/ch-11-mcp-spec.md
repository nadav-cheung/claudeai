# 第 11 章：MCP 协议规范 —— 连接 LLM 与外部世界的开放标准

## 11.1 概念全景

### 11.1.1 什么是 MCP？

**Model Context Protocol（MCP）** 是由 Anthropic 主导发布的开放协议标准，旨在为 LLM 应用与外部数据源、工具和服务之间建立统一的交互接口。MCP 于 2024 年 11 月首次发布（`2024-11-05`），2025 年 3 月发布重大修订版（`2025-03-26`，引入 Streamable HTTP 传输），2025 年 11 月发布最新版本（`2025-11-25`，引入 Tasks、Tool Annotations 等）。本章以 `2025-03-26` 为基础讲解协议核心概念，第 12 章实现使用 `2025-11-25`。读者在实际开发中应参考 modelcontextprotocol.io 获取最新协议版本。

在 MCP 出现之前，每当你想要让 LLM 访问一个新的数据源（如数据库、文件系统、第三方 API），你都需要编写专门适配该数据源的胶水代码。这种**N x M 的集成的复杂性**——N 个 AI 应用对接 M 个数据源——导致了大量重复工作。MCP 通过标准化的协议层将复杂度从 **N x M 降为 N + M**：

```
Without MCP:  Each AI app → custom code → each data source  (N × M integrations)
With MCP:      AI apps → MCP Client → MCP Protocol → MCP Server → data sources  (N + M integrations)
```

### 11.1.2 MCP 与 LSP 的类比

MCP 的设计从 **Language Server Protocol（LSP）** 中汲取了核心灵感。LSP 标准化了 IDE 如何添加编程语言支持——以前每个编辑器需要单独实现每种语言的语法高亮、自动补全、诊断等功能（M 个编辑器 x N 种语言），而 LSP 将复杂度降低为 M+N。MCP 以同样的理念标准化了 AI 应用如何接入外部上下文和工具。

| 维度 | LSP | MCP |
|------|-----|-----|
| 解决的问题 | 编辑器 x 语言 集成 | AI 应用 x 数据源/工具 集成 |
| 通信协议 | JSON-RPC 2.0 (自定义方法) | JSON-RPC 2.0 (标准化方法) |
| 服务端 | Language Server | MCP Server |
| 客户端 | IDE / Editor | LLM 应用 (Host + Client) |
| 核心原语 | 补全、诊断、悬停、跳转定义 | Tools、Resources、Prompts |
| 传输层 | STDIO / TCP / Pipe | STDIO / Streamable HTTP |

MCP 并非 LSP 的超集或替代品——两者解决不同层面的问题。LSP 聚焦于编程语言的智能支持，MCP 聚焦于 LLM 的上下文和工具集成。但它们在架构哲学上高度一致：**一个开放的、语言无关的、以能力协商为基础的协议标准**。

### 11.1.3 三层架构：Host -> Client -> Server

MCP 定义了清晰的三层架构：

```
┌─────────────────────────────────────────┐
│              Host (LLM 应用)              │
│   ┌──────────┐  ┌──────────┐            │
│   │ Client 1  │  │ Client 2  │  ...      │
│   └────┬─────┘  └────┬─────┘            │
└────────┼──────────────┼─────────────────┘
         │              │
    ┌────▼─────┐   ┌────▼─────┐
    │ Server 1 │   │ Server 2 │
    │(Files)   │   │(Database)│
    └──────────┘   └──────────┘
```

**Host（宿主应用）**
Host 是整个 MCP 生态的"容器"和"协调者"。它是用户直接交互的 LLM 应用（如 Claude Desktop、VS Code 插件、你自建的聊天界面）。Host 的职责包括：

- 创建并管理多个 MCP Client 实例
- 控制 Client 的连接权限和生命周期
- 执行安全策略（用户同意确认、数据访问控制）
- 协调 AI/LLM 推理与工具调用的集成
- 聚合跨多个 Client 的上下文信息

**Client（客户端）**
每个 Client 由 Host 创建，与一个特定的 MCP Server 维持**一对一的隔离状态会话**。Client 的职责包括：

- 建立并维护与 Server 的有状态会话
- 处理协议协商和能力交换
- 双向路由协议消息
- 管理资源订阅和变更通知
- 在 Server 之间维护安全边界

每个 Client 只能"看到"自己连接的 Server——**Server 之间完全隔离**，不能互相查看或"窥探"彼此的上下文。这个设计确保了最小权限原则和信任边界。

**Server（服务端）**
Server 提供专门的上下文和能力：

- 通过 MCP 原语暴露 **Resources（资源）**、**Tools（工具）** 和 **Prompts（提示模板）**
- 独立运行，职责聚焦
- 通过 Client 接口请求 LLM 采样
- 必须遵守安全约束
- 可以是本地进程或远程服务

### 11.1.4 协议栈分层

MCP 的协议栈分为**数据层**和**传输层**：

```
┌──────────────────────────────────────┐
│         Server Features              │
│  ┌─────────┐ ┌──────────┐ ┌───────┐ │
│  │  Tools   │ │ Resources │ │Prompts│ │
│  └─────────┘ └──────────┘ └───────┘ │
├──────────────────────────────────────┤
│         Client Features              │
│  ┌──────┐ ┌───────┐ ┌──────────┐    │
│  │ Roots │ │Sampling│ │Elicitation│   │
│  └──────┘ └───────┘ └──────────┘    │
├──────────────────────────────────────┤
│       Lifecycle Management           │
│   initialize ⟶ initialized ⟶ ...    │
├──────────────────────────────────────┤
│       JSON-RPC 2.0 Base Protocol     │
│   Request / Response / Error / Notif  │
├──────────────────────────────────────┤
│          Transport Layer             │
│   ┌────────┐ ┌─────────────────┐     │
│   │ STDIO  │ │ Streamable HTTP │     │
│   └────────┘ └─────────────────┘     │
└──────────────────────────────────────┘
```

**数据层**（JSON-RPC 2.0 及以上）定义了消息的语义——什么样的请求调用什么方法、返回什么结果。它与传输无关：同样的数据层程序可以在本地 STDIO 进程或远程 HTTP 服务上运行。

**传输层**负责消息的实际传递：字节如何从一个进程到达另一个进程。MCP 当前定义了两种标准传输：STDIO（用于本地进程间通信）和 Streamable HTTP（用于远程服务通信）。

---

## 11.2 协议规范

### 11.2.1 JSON-RPC 2.0 基础

MCP 的基石是 **JSON-RPC 2.0** 协议（[jsonrpc.org](https://www.jsonrpc.org/specification)），这是一种轻量级、传输无关的远程过程调用协议。理解 JSON-RPC 是理解 MCP 的前提——本章将完整教授 JSON-RPC 2.0 标准，然后介绍 MCP 在此基础上增加的特定约束。

#### 11.2.1.1 请求 (Request)

请求从客户端发往服务端（或反过来），用于发起一次操作调用。

```
{
  "jsonrpc": "2.0",
  "id": 1,
  "method": "subtract",
  "params": {"minuend": 42, "subtrahend": 23}
}
```

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `jsonrpc` | `string` | **是** | 必须严格等于 `"2.0"`。任何其他值（包括 `"1.0"`、`"2.1"`等）均非法 |
| `id` | `string \| number` | **是** | 请求的唯一标识符。**MCP 约束：`id` 不能为 `null`**（这与基础 JSON-RPC 不同——标准 JSON-RPC 允许 null id 表示通知，但 MCP 使用无 id 字段表示通知） |
| `method` | `string` | **是** | 要调用的方法名。MCP 的方法命名遵循 `domain/action` 模式，如 `tools/list`、`sampling/createMessage` |
| `params` | `object \| array` | 否 | 方法参数。可以是有名对象或位置数组。省略等价于空参数 |

**关键约束**：

1. `id` 在同一个会话中**不得重复使用**——每个请求的 id 在该方向上必须唯一
2. `id` 的类型（string 或 number）可以混合使用，但建议保持一致性
3. 仅支持对象和数组类型的 `params`（不支持基础类型作为 params 顶层值）

#### 11.2.1.2 成功响应 (Response)

响应是对请求的回复，包含操作的结果或错误。

```
{
  "jsonrpc": "2.0",
  "id": 1,
  "result": 19
}
```

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `jsonrpc` | `string` | **是** | 必须等于 `"2.0"` |
| `id` | `string \| number` | **是** | 必须与对应请求的 `id` 完全一致。这是 JSON-RPC 消息关联的核心机制 |
| `result` | `any` | 条件 | 操作成功时设置。可以是任何 JSON 值（包括 `null`） |

**关键约束**：

1. `result` 和 `error` **互斥**——一条消息中**不能同时包含**两者
2. 成功响应中 `result` **必须存在**（即使其值为 `null`）

#### 11.2.1.3 错误响应 (Error)

当操作失败时，响应消息包含 `error` 对象而非 `result`。

```
{
  "jsonrpc": "2.0",
  "id": 1,
  "error": {
    "code": -32601,
    "message": "Method not found",
    "data": "The method 'subtrac' does not exist"
  }
}
```

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `error.code` | `integer` | **是** | 数字错误码。负数表示 JSON-RPC 标准保留错误，正数表示实现自定义错误 |
| `error.message` | `string` | **是** | 单行人类可读的错误描述 |
| `error.data` | `any` | 否 | 附加的错误信息（如详细的验证错误列表、堆栈跟踪等） |

**标准 JSON-RPC 2.0 错误码**：

| 错误码 | 含义 | 触发条件 |
|--------|------|---------|
| `-32700` | Parse error | 服务端收到无效 JSON |
| `-32600` | Invalid Request | JSON 不是有效的请求对象 |
| `-32601` | Method not found | 方法不存在或不可用 |
| `-32602` | Invalid params | 方法参数无效 |
| `-32603` | Internal error | 服务端内部 JSON-RPC 错误 |
| `-32000 ~ -32099` | Server error | 保留给实现自定义的服务端错误 |

MCP 为这些标准错误赋予了特定语义。例如：
- `tools/call` 中未知的工具名返回 `-32602`（Invalid params）
- `resources/read` 中资源未找到返回 `-32002`（特定服务端错误）

#### 11.2.1.4 通知 (Notification)

通知是**单向消息**——接收方**不得**发送响应。

```
{
  "jsonrpc": "2.0",
  "method": "notifications/initialized",
  "params": {}
}
```

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `jsonrpc` | `string` | **是** | 必须等于 `"2.0"` |
| `method` | `string` | **是** | 通知的方法名 |
| `params` | `object` | 否 | 通知参数 |

**关键约束**：

1. 通知**不得**包含 `id` 字段——这是它与 Request 的本质区别
2. 接收方不得对通知做出任何响应（包括错误）
3. 通知发送后即"发射后不管"（fire and forget）

MCP 大量使用通知来传递状态变化：`notifications/initialized`、`notifications/tools/list_changed`、`notifications/resources/updated`、`notifications/progress`、`notifications/cancelled` 等。

#### 11.2.1.5 消息 ID 关联机制

JSON-RPC 的**消息关联**通过 `id` 字段实现——这是协议设计的核心。每一条响应（成功或错误）都必须原样回显对应请求的 `id`：

```
Client → Server:  {"jsonrpc":"2.0","id":"abc","method":"ping"}
Server → Client:  {"jsonrpc":"2.0","id":"abc","result":{}}
```

这使得客户端可以在单个连接上**并行发出多个请求**，然后通过 `id` 将响应与原请求一一对应。这种设计比 HTTP/1.1 的"一个请求一个响应"模式更高效。

**MCP 特别约束**：一个已使用的 `id` 在同一方向上的会话中**不得重复**。这意味着一旦你发出一个 `id=1` 的请求并收到了响应，你不能再发另一个 `id=1` 的请求。

#### 11.2.1.6 批量请求 (Batch)

JSON-RPC 2.0 支持将多个请求和通知打包为一个 JSON 数组：

```json
[
  {"jsonrpc": "2.0", "id": 1, "method": "tools/list"},
  {"jsonrpc": "2.0", "id": 2, "method": "resources/list"},
  {"jsonrpc": "2.0", "method": "notifications/cancelled", "params": {"requestId": 99}}
]
```

对批量请求的响应也是一个 JSON 数组，其中的每个元素对应批量中的一条请求（通知没有对应的响应元素）：

```json
[
  {"jsonrpc": "2.0", "id": 1, "result": {"tools": [...]}},
  {"jsonrpc": "2.0", "id": 2, "result": {"resources": [...]}}
]
```

**MCP 对批量的规定**：

- 所有 MCP 实现**必须支持接收**批量请求
- 实现**可以**但不强制要求支持发送批量请求
- `initialize` 请求**不得**出现在批量数组中——因为初始化完成前不能发送其他消息
- 批量中的各条消息是**独立处理**的，某条失败不影响其他条

### 11.2.2 生命周期管理

MCP 定义了严格的**三阶段连接生命周期**：初始化（Initialization）、运行（Operation）、关闭（Shutdown）。

```
Client                         Server
  │                              │
  │──── initialize request ────→│  ① 初始化阶段
  │←── initialize response ────│     能力协商 + 版本确认
  │──── initialized notif. ───→│
  │                              │
  │══════ 运行阶段 (Operation) ═══│  ② 正常运行
  │ ←→ tools/list, tools/call   │
  │ ←→ resources/read, prompts  │
  │ ←→ sampling, notifications  │
  │                              │
  │──── 关闭 STDIN / HTTP DELETE ──→│  ③ 关闭阶段
  │                              │
```

#### 11.2.2.1 初始化请求 (initialize)

初始化必须是 Client 和 Server 之间的**第一次交互**。Client **必须**最先发出 `initialize` 请求：

```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "method": "initialize",
  "params": {
    "protocolVersion": "2025-03-26",
    "capabilities": {
      "roots": {
        "listChanged": true
      },
      "sampling": {}
    },
    "clientInfo": {
      "name": "ExampleClient",
      "version": "1.0.0"
    }
  }
}
```

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `protocolVersion` | `string` | **是** | Client 支持的协议版本。**应该**是最新版本（如 `"2025-03-26"`） |
| `capabilities` | `object` | **是** | Client 声明的能力集。空对象 `{}` 表示无特殊能力 |
| `capabilities.roots` | `object` | 否 | 声明 Client 可以提供文件系统根目录列表 |
| `capabilities.sampling` | `object` | 否 | 声明 Client 支持 LLM 采样功能 |
| `capabilities.experimental` | `object` | 否 | 非标准的实验性功能 |
| `clientInfo` | `object` | **是** | 实现的标识信息 |
| `clientInfo.name` | `string` | **是** | 实现名称 |
| `clientInfo.version` | `string` | **是** | 实现版本号 |

**关键约束**：

1. `initialize` 请求**不得**出现在批量数组中
2. Client 在收到 `initialize` 响应前**不应**发送除 `ping` 以外的任何其他请求
3. Server 在收到 `initialized` 通知前**不应**发送除 `ping` 和 `logging` 以外的任何请求

#### 11.2.2.2 初始化响应 (Initialize Result)

Server **必须**以自身的能力和信息响应：

```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "result": {
    "protocolVersion": "2025-03-26",
    "capabilities": {
      "logging": {},
      "prompts": {
        "listChanged": true
      },
      "resources": {
        "subscribe": true,
        "listChanged": true
      },
      "tools": {
        "listChanged": true
      }
    },
    "serverInfo": {
      "name": "ExampleServer",
      "version": "1.0.0"
    },
    "instructions": "这是一个文件系统 MCP Server，提供对项目文件的访问..."
  }
}
```

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `protocolVersion` | `string` | **是** | Server 接受的协议版本（见版本协商） |
| `capabilities` | `object` | **是** | Server 的能力集 |
| `serverInfo.name` | `string` | **是** | 实现名称 |
| `serverInfo.version` | `string` | **是** | 实现版本号 |
| `instructions` | `string` | 否 | 给 Client 的使用说明（可由 Host 展示给用户） |

**Server 能力声明**：

| 能力 | 说明 | 子能力 |
|------|------|--------|
| `prompts` | 提供 Prompt 模板 | `listChanged` |
| `resources` | 提供可读资源 | `subscribe`, `listChanged` |
| `tools` | 提供可调用工具 | `listChanged` |
| `logging` | 发送结构化日志 | — |
| `completions` | 支持参数自动补全 | — |
| `experimental` | 实验性功能 | 自定义 |

#### 11.2.2.3 版本协商

在 `initialize` 请求中，Client **必须**发送它支持的协议版本（应该是最新版本）。

- 如果 Server 支持请求的版本，它**必须**以相同版本号响应
- 如果 Server **不支持**请求的版本，它**必须**以另一个它支持的版本号响应（应该是它支持的最新版本）
- 如果 Client 不支持 Server 响应中的版本，它**应该**断开连接

示例——版本不匹配：

```json
// Client 请求
{"jsonrpc": "2.0", "id": 1, "method": "initialize",
 "params": {"protocolVersion": "2025-03-26", ...}}

// Server 仅支持旧版本
{"jsonrpc": "2.0", "id": 1,
 "error": {"code": -32602, "message": "Unsupported protocol version",
           "data": {"supported": ["2024-11-05"], "requested": "2025-03-26"}}}
```

#### 11.2.2.4 initialized 通知

成功初始化后，Client **必须**发送 `initialized` 通知（注意是**通知**，不是请求）：

```json
{
  "jsonrpc": "2.0",
  "method": "notifications/initialized"
}
```

这条通知标志着 Client 准备就绪，可以开始正常的协议操作。Server 收到此通知后，即可自由发送请求和通知。

#### 11.2.2.5 连接终止

MCP 没有定义专门的"关闭"消息——由底层传输机制负责：

**STDIO 传输的关闭流程**：

1. Client 关闭子进程的 STDIN 流
2. Client 等待 Server 进程退出，若超时则发送 `SIGTERM`
3. 若 `SIGTERM` 后仍未退出，发送 `SIGKILL`

Server 也可以主动关闭：关闭其 STDOUT 流并退出进程。

**Streamable HTTP 的关闭流程**：

- Client 发送 `HTTP DELETE` 到 MCP endpoint（附带 `Mcp-Session-Id`）
- 或者直接关闭 HTTP 连接

#### 11.2.2.6 超时和错误恢复

实现**应该**为所有发出的请求设置超时：

- 超时后发送方**应该**发送取消通知 `notifications/cancelled` 并停止等待
- SDK 和中间件**应该**允许按请求配置超时
- 收到 `notifications/progress` 可以重置超时时钟（因为确认有进度），但仍应强制执行**最大超时上限**

实现必须准备好处理以下错误场景：

| 错误场景 | 处理方式 |
|---------|---------|
| 协议版本不匹配 | Client 断开连接 |
| 能力协商失败 | 依赖方停止使用该功能 |
| 请求超时 | 发送取消通知 |
| 连接断开（STDIO） | 重启 Server 进程 |
| 会话过期（HTTP） | 收到 404 后重新初始化 |

### 11.2.3 Ping 保活机制

MCP 提供了一个可选的 ping 机制用于连接健康检查。Client 或 Server 均可发起：

```json
// Ping 请求
{"jsonrpc": "2.0", "id": "ping-1", "method": "ping"}

// Ping 响应
{"jsonrpc": "2.0", "id": "ping-1", "result": {}}
```

实现**应该**定期发送 ping 以检测连接健康状态。如果多次 ping 失败，实现**可以**触发连接重建。

### 11.2.4 三大原语详解

MCP Server 通过三种核心原语（Primitives）向外暴露能力。这三种原语的本质区别在于**控制权的归属**：

| 原语 | 控制方 | 控制方式 | 典型用途 |
|------|--------|---------|---------|
| **Prompts（提示模板）** | 用户控制 (User-controlled) | 用户主动选择 | 斜杠命令、菜单选项、预置对话 |
| **Resources（资源）** | 应用控制 (Application-controlled) | Host 决定何时附加 | 文件内容、数据库 Schema、Git 历史 |
| **Tools（工具）** | 模型控制 (Model-controlled) | LLM 自主发现和调用 | 查询 API、写入文件、执行计算 |

这种分层设计使得不同类型的上下文以最自然的方式被使用：用户知道何时需要一个特定的 Prompt 模板；应用知道何时需要附加某些资源；而模型最适合判断何时需要使用一个工具。

#### 11.2.4.1 Tools（工具）

Tools 是 MCP 中**最强大也最容易产生安全风险**的原语。每个 Tool 由唯一的名称标识，包含描述其功能的元数据和 JSON Schema 格式的输入参数定义。

**能力声明**：

```json
{
  "capabilities": {
    "tools": {
      "listChanged": true
    }
  }
}
```

**1. 列出工具 — `tools/list`**

```json
// Request
{"jsonrpc": "2.0", "id": 1, "method": "tools/list",
 "params": {"cursor": "optional-cursor-value"}}

// Response
{
  "jsonrpc": "2.0", "id": 1,
  "result": {
    "tools": [
      {
        "name": "get_weather",
        "description": "获取指定位置的当前天气信息",
        "inputSchema": {
          "type": "object",
          "properties": {
            "location": {
              "type": "string",
              "description": "城市名称或邮政编码"
            }
          },
          "required": ["location"]
        }
      }
    ],
    "nextCursor": "next-page-cursor"
  }
}
```

Tool 的定义结构：

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `name` | `string` | **是** | 工具的唯一标识符 |
| `description` | `string` | 否(但强烈建议) | 人类可读的功能描述，直接影响模型的调用准确率 |
| `inputSchema` | `object` | **是** | JSON Schema 格式的参数定义。必须是 `type: "object"` |
| `annotations` | `object` | 否 | 工具行为注解（如 readonly、destructive 等） |

**安全注记**：Client **必须**将来自非受信 Server 的 tool annotations 视为不可信。

**2. 调用工具 — `tools/call`**

```json
// Request
{"jsonrpc": "2.0", "id": 2, "method": "tools/call",
 "params": {"name": "get_weather", "arguments": {"location": "New York"}}}

// Response (成功)
{
  "jsonrpc": "2.0", "id": 2,
  "result": {
    "content": [
      {"type": "text", "text": "纽约当前天气：\n温度：22°C\n天气：晴"}
    ],
    "isError": false
  }
}
```

工具返回的 `content` 数组支持多种内容类型：

| 内容类型 | 使用场景 | 关键字段 |
|---------|---------|---------|
| `text` | 文本结果 | `text: string` |
| `image` | 图像结果 | `data: string` (base64), `mimeType: string` |
| `audio` | 音频结果 | `data: string` (base64), `mimeType: string` |
| `resource` | 嵌入资源 | `resource: {uri, mimeType, text/blob}` |

**3. Tools 的两种错误报告方式**

MCP 区分了两种级别的工具错误：

**协议级错误**（工具调用本身失败——如工具不存在、参数无效）：

```json
{"jsonrpc": "2.0", "id": 3,
 "error": {"code": -32602, "message": "Unknown tool: invalid_tool_name"}}
```

**工具执行错误**（工具被正确调用但执行过程出错——如 API 调用失败）：

```json
{"jsonrpc": "2.0", "id": 4,
 "result": {"content": [{"type": "text", "text": "获取天气失败：API 频率限制已超出"}],
            "isError": true}}
```

`isError: true` 向 LLM 表明操作未成功，但这不是协议级错误——JSON-RPC 本身成功传递了消息。

**Tools 安全要求**：

1. Server **必须**验证所有工具输入
2. Server **必须**实现适当的访问控制
3. Server **必须**对工具调用进行频率限制
4. Server **必须**清理工具输出以防注入
5. Client **应该**在敏感操作前向用户请求确认
6. Client **应该**在调用前向用户展示工具输入（防止恶意数据外泄）
7. Client **应该**为工具调用实现超时

#### 11.2.4.2 Resources（资源）

Resources 允许 Server 向 LLM 提供数据作为上下文。每个资源由一个 URI 唯一标识（遵循 [RFC 3986](https://datatracker.ietf.org/doc/html/rfc3986)）。

**能力声明**：

```json
{
  "capabilities": {
    "resources": {
      "subscribe": true,     // 支持资源变更订阅
      "listChanged": true    // 支持资源列表变更通知
    }
  }
}
```

**1. 列出资源 — `resources/list`**

```json
// Request
{"jsonrpc": "2.0", "id": 1, "method": "resources/list",
 "params": {"cursor": "optional-cursor-value"}}

// Response
{
  "jsonrpc": "2.0", "id": 1,
  "result": {
    "resources": [
      {
        "uri": "file:///project/src/main.rs",
        "name": "main.rs",
        "description": "主程序入口点",
        "mimeType": "text/x-rust"
      }
    ],
    "nextCursor": "next-page-cursor"
  }
}
```

资源定义字段：

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `uri` | `string` | **是** | 资源的唯一标识符（RFC 3986 URI） |
| `name` | `string` | **是** | 人类可读的名称 |
| `description` | `string` | 否 | 可选描述 |
| `mimeType` | `string` | 否 | MIME 类型（如 `text/plain`, `image/png`） |
| `size` | `number` | 否 | 可选的文件大小（字节） |

**2. 读取资源 — `resources/read`**

```json
// Request
{"jsonrpc": "2.0", "id": 2, "method": "resources/read",
 "params": {"uri": "file:///project/src/main.rs"}}

// Response
{
  "jsonrpc": "2.0", "id": 2,
  "result": {
    "contents": [
      {
        "uri": "file:///project/src/main.rs",
        "mimeType": "text/x-rust",
        "text": "fn main() {\n    println!(\"Hello world!\");\n}"
      }
    ]
  }
}
```

资源内容分两种：

**文本内容**：

```json
{"uri": "file:///example.txt", "mimeType": "text/plain", "text": "资源内容文本"}
```

**二进制内容**：

```json
{"uri": "file:///example.png", "mimeType": "image/png", "blob": "base64-encoded-data"}
```

**3. 资源模板 — `resources/templates/list`**

Resource Templates 允许 Server 暴露参数化的资源（使用 [RFC 6570](https://datatracker.ietf.org/doc/html/rfc6570) URI 模板）：

```json
// Response
{
  "resourceTemplates": [
    {
      "uriTemplate": "file:///{path}",
      "name": "项目文件",
      "description": "访问项目目录中的文件",
      "mimeType": "application/octet-stream"
    }
  ]
}
```

URI 模板中的变量（如 `{path}`）可以通过 [Completion API](/specification/2025-03-26/server/utilities/completion) 进行自动补全。

**4. 资源订阅 — `resources/subscribe`**

当 Server 声明了 `subscribe` 能力后，Client 可以订阅特定资源的变更通知：

```json
// Subscribe
{"jsonrpc": "2.0", "id": 4, "method": "resources/subscribe",
 "params": {"uri": "file:///project/src/main.rs"}}

// Update notification (Server → Client)
{"jsonrpc": "2.0",
 "method": "notifications/resources/updated",
 "params": {"uri": "file:///project/src/main.rs"}}
```

**标准 URI 方案**：

| 方案 | 用途 | 说明 |
|------|------|------|
| `https://` | 可通过 Web 直接访问的资源 | 仅当 Client 能自行获取时使用 |
| `file://` | 类文件系统的资源 | 不必映射到实际物理文件系统 |
| `git://` | Git 版本控制集成 | — |
| 自定义 | 任何自定义方案 | 实现可自由定义额外方案 |

#### 11.2.4.3 Prompts（提示模板）

Prompts 是**用户控制**的交互模板，为 LLM 提供结构化的消息和指令。用户可以像使用斜杠命令一样发现和调用它们。

**能力声明**：

```json
{"capabilities": {"prompts": {"listChanged": true}}}
```

**1. 列出提示 — `prompts/list`**

```json
// Response
{
  "prompts": [
    {
      "name": "code_review",
      "description": "让 LLM 分析代码质量并提出改进建议",
      "arguments": [
        {
          "name": "code",
          "description": "要审查的代码",
          "required": true
        }
      ]
    }
  ],
  "nextCursor": "next-page-cursor"
}
```

**2. 获取提示 — `prompts/get`**

```json
// Request
{"jsonrpc": "2.0", "id": 2, "method": "prompts/get",
 "params": {"name": "code_review", "arguments": {"code": "def hello():\n    print('world')"}}}

// Response
{
  "jsonrpc": "2.0", "id": 2,
  "result": {
    "description": "代码审查提示",
    "messages": [
      {
        "role": "user",
        "content": {
          "type": "text",
          "text": "请审查以下 Python 代码：\ndef hello():\n    print('world')"
        }
      }
    ]
  }
}
```

Prompt 消息支持的内容类型与 Tools 完全一致：`text`、`image`、`audio` 和 `resource`（嵌入式资源）。`role` 可以是 `"user"` 或 `"assistant"`，用于构建对话式的提示模板。

### 11.2.5 Client 特性

MCP 不仅定义了 Server 能做什么，也定义了 Client 能向 Server 提供什么能力。这些"反向能力"使得 Server 可以利用 Host 的资源。

#### 11.2.5.1 Roots（根目录）

Roots 定义了 Server 可以在文件系统中操作的**边界**。Server 可以向 Client 请求根目录列表，并在列表变化时收到通知。

**能力声明**：

```json
{"capabilities": {"roots": {"listChanged": true}}}
```

**获取根目录 — `roots/list`**（由 Server 发出）：

```json
// Request (Server → Client)
{"jsonrpc": "2.0", "id": 1, "method": "roots/list"}

// Response (Client → Server)
{
  "jsonrpc": "2.0", "id": 1,
  "result": {
    "roots": [
      {"uri": "file:///home/user/projects/myproject", "name": "My Project"}
    ]
  }
}
```

每个 Root 包含：
- `uri`：必须为 `file://` URI
- `name`：可选的人类可读名称

**安全注意事项**：

1. Client **必须**只暴露有适当权限的根目录
2. Client **必须**验证所有根目录 URI 以防止路径穿越
3. Server **应该**在所有操作中遵守根目录边界

#### 11.2.5.2 Sampling（LLM 采样）

Sampling 是 MCP 最强大的 Client 特性——它允许 **Server 请求 Client 进行 LLM 推理**。这使得 Server 可以实现"递归"的 Agent 行为，而无需持有自己的 API 密钥。

**能力声明**：

```json
{"capabilities": {"sampling": {}}}
```

**创建消息 — `sampling/createMessage`**（由 Server 发出）：

```json
// Request
{
  "jsonrpc": "2.0", "id": 1, "method": "sampling/createMessage",
  "params": {
    "messages": [
      {"role": "user", "content": {"type": "text", "text": "法国的首都是哪里？"}}
    ],
    "modelPreferences": {
      "hints": [{"name": "claude-3-sonnet"}],
      "intelligencePriority": 0.8,
      "speedPriority": 0.5
    },
    "systemPrompt": "你是一个乐于助人的助手。",
    "maxTokens": 100
  }
}

// Response
{
  "jsonrpc": "2.0", "id": 1,
  "result": {
    "role": "assistant",
    "content": {"type": "text", "text": "法国的首都是巴黎。"},
    "model": "claude-3-sonnet-20240307",
    "stopReason": "endTurn"
  }
}
```

**模型偏好系统**：由于 Server 和 Client 可能使用不同的 AI 提供商，MCP 使用一个巧妙的**抽象能力优先级+模型提示**系统：

| 参数 | 类型 | 范围 | 说明 |
|------|------|------|------|
| `costPriority` | `number` | 0-1 | 成本优先级，越高越倾向便宜模型 |
| `speedPriority` | `number` | 0-1 | 速度优先级，越高越倾向快模型 |
| `intelligencePriority` | `number` | 0-1 | 智能优先级，越高越倾向强模型 |
| `hints` | `array` | — | 模型名称提示（子串匹配），按优先级排序 |

Server 不指定具体模型名，而是描述**需要什么特性的模型**。Client 根据自己的可用模型列表做出最终选择。这种"能力抽象"设计使得 MCP 可以在完全不同的模型生态系统中工作。

**Sampling 安全要求**：

1. Client **应该**实现用户审批控制——用户必须明确批准每次 LLM 采样请求
2. 用户应该能看到并编辑 Server 请求的 prompt
3. 生成的响应在返回给 Server 之前应该经过用户审查
4. 协议有意限制 Server 对 prompt 和响应的可见性

#### 11.2.5.3 进度追踪 (Progress)

对于长时间运行的操作，MCP 支持通过通知传递进度更新。请求方在 `_meta.progressToken` 中提供进度令牌：

```json
// 发送请求时携带 progressToken
{"jsonrpc": "2.0", "id": 1, "method": "long_operation",
 "params": {"_meta": {"progressToken": "abc123"}}}

// 接收方周期性发送进度通知
{"jsonrpc": "2.0", "method": "notifications/progress",
 "params": {"progressToken": "abc123", "progress": 50, "total": 100,
            "message": "正在处理第 50/100 条数据..."}}
```

- `progress` 值必须递增
- `total` 在未知时可以省略
- 进度值可以为浮点数

#### 11.2.5.4 请求取消 (Cancellation)

任何一方都可以通过取消通知终止正在进行的请求：

```json
{"jsonrpc": "2.0",
 "method": "notifications/cancelled",
 "params": {"requestId": "123", "reason": "用户请求取消"}}
```

- 取消通知只能指向**同一方向上**正在进行的请求
- `initialize` 请求**不得**被客户端取消
- 接收方**应该**停止处理、释放资源、不发送响应
- 由于网络延迟，取消通知可能到达时请求已经完成——双方**必须**妥善处理这种竞态条件

### 11.2.6 传输层

MCP 协议的传输层负责 JSON-RPC 消息的实际传递。当前规范定义了两种标准传输方式。所有 JSON-RPC 消息**必须**使用 UTF-8 编码。

#### 11.2.6.1 STDIO 传输

STDIO 传输适用于**本地进程间通信**——Client 将 MCP Server 作为子进程启动，通过标准输入/输出进行通信。

```
Client Process                    Server Process (child)
     │                                     │
     │──── JSON-RPC messages ────→ stdin   │
     │                                     │
     │←─── JSON-RPC messages ──── stdout   │
     │                                     │
     │←─── 日志 (可选) ───────── stderr    │
```

**消息帧格式**：

- 每条 JSON-RPC 消息独占一行（以换行符 `\n` 分隔）
- 消息**内部不得包含嵌入的换行符**——所有 JSON 必须是紧凑的单行格式
- 可以为单条请求、响应、通知或批量数组

**关键约束**：

| 约束 | 说明 |
|------|------|
| Server **不得**向 stdout 写入任何非 MCP 消息的内容 | 日志必须通过 stderr 输出 |
| Client **不得**向 Server 的 stdin 写入任何非 MCP 消息的内容 | 包括 `\n` 在内没有其他通信 |
| Server **可以**向 stderr 写入 UTF-8 字符串作为日志 | Client **可以**捕获、转发或忽略 |
| 消息以换行符分隔 | `\n` 是唯一的消息帧边界 |

**STDIO 的优势与局限**：

| 优势 | 局限 |
|------|------|
| 零网络配置 | 仅限本地进程 |
| 无需认证（环境变量获取凭据） | 无多客户端支持 |
| 最低延迟（无网络往返） | 进程管理由 Client 负责 |
| 实现最简单 | 无连接恢复机制 |

#### 11.2.6.2 Streamable HTTP 传输

Streamable HTTP 传输是 2025-03-26 版本引入的新标准，**替代了**旧版（2024-11-05）的 HTTP+SSE 传输。它支持 Server 作为独立 HTTP 进程运行，可以处理多个 Client 连接，支持可选的 SSE 流式传输。

Server **必须**提供一个统一的 **MCP Endpoint**（单一 URL，同时支持 GET 和 POST 方法，如 `https://example.com/mcp`）。

**发送消息（Client → Server）**：

每次 Client 向 Server 发送 JSON-RPC 消息都通过一个独立的 HTTP POST 请求：

1. Client **必须**使用 HTTP POST 发送 JSON-RPC 消息
2. Client **必须**包含 `Accept` 头，列出 `application/json` 和 `text/event-stream`
3. POST body 可以为：单条请求/通知/响应，或批量数组
4. 如果输入**全是响应或通知**（无线程期待响应）：
   - Server 接受则返回 HTTP 202 Accepted（无 body）
   - Server 拒绝则返回 HTTP 400
5. 如果输入**包含任何请求**：
   - Server 可以返回 `Content-Type: application/json`（单次 JSON 响应）
   - 或者返回 `Content-Type: text/event-stream`（启动 SSE 流）
   - Client **必须**支持这两种情况

**监听消息（Server → Client 主动推送）**：

1. Client **可以**发送 HTTP GET 到 MCP Endpoint 以打开 SSE 流
2. Client **必须**包含 `Accept: text/event-stream`
3. Server 可以返回 SSE 流或 405 Method Not Allowed
4. 在此 SSE 流上，Server **可以**发送 JSON-RPC 请求和通知
5. 这些消息**应该**与任何正在进行的 Client 请求无关

**会话管理**：

Streamable HTTP 支持有状态会话：

1. Server 可以在初始化响应中通过 `Mcp-Session-Id` 头分配会话 ID
   - 会话 ID **应该**是全局唯一且加密安全的（UUID、JWT、哈希）
   - 会话 ID **必须**只包含可见 ASCII 字符（0x21-0x7E）
2. Client 在后续所有 HTTP 请求中**必须**附带 `Mcp-Session-Id` 头
3. Server 可以随时终止会话，此后对该会话 ID 的请求返回 HTTP 404
4. Client 收到 404 后**必须**重新初始化（不带会话 ID）
5. 不再需要的会话，Client **应该**发送 HTTP DELETE 到 MCP Endpoint

**SSE 流的可恢复性和重投递**：

为支持断线恢复和消息重投递：

1. Server **可以**在 SSE 事件上附加 `id` 字段（按 SSE 标准）
2. Client 重连时，在 HTTP GET 中包含 `Last-Event-ID` 头
3. Server **可以**使用此 ID 重投递断开期间的消息

**Streamable HTTP 安全要求**：

1. Server **必须**验证所有入站连接的 `Origin` 头以防止 DNS 重绑定攻击
2. 本地运行时应绑定到 `127.0.0.1` 而非 `0.0.0.0`
3. Server **应该**对所有连接实施认证

#### 11.2.6.3 传输选择指南

| 场景 | 推荐传输 | 原因 |
|------|---------|------|
| 本地开发工具 (IDE 插件) | STDIO | 零配置、低延迟、无需网络 |
| 本地 Claude Desktop 集成 | STDIO | 标准配置方式 |
| 远程/云托管服务 | Streamable HTTP | 支持多客户端、远程访问 |
| SaaS 集成 | Streamable HTTP | 需要 OAuth 认证 |
| 微服务间通信 | Streamable HTTP | 标准化 HTTP 基础设施 |
| 需要服务端推送 | Streamable HTTP + SSE | 支持双向异步通信 |

#### 11.2.6.4 向后兼容

**Server 要支持旧版客户端**：
- 同时托管旧版 HTTP+SSE 的 SSE endpoint 和 POST endpoint
- 与新版的统一 MCP Endpoint 并存

**Client 要支持旧版 Server**：
1. 尝试 POST `InitializeRequest` 到 Server URL（带新版 Accept 头）
   - 成功 → 使用新版 Streamable HTTP
   - HTTP 4xx 失败 → 降级为旧版流程（GET 打开 SSE，等待 `endpoint` 事件）

### 11.2.7 授权与认证

MCP 提供了 HTTP 传输层的授权框架。**授权是可选的**。本节内容**仅适用于 HTTP 传输**；STDIO 传输应通过环境变量获取凭据。

#### 11.2.7.1 OAuth 2.1 完整流程

MCP 的授权基于 OAuth 2.1 IETF 草案，并强制实施 PKCE（Proof Key for Code Exchange）。

**核心要求**：

1. MCP Auth 实现**必须**实现 OAuth 2.1（支持保密客户端和公开客户端）
2. **应该**支持 RFC 7591 动态客户端注册（Dynamic Client Registration / DCR）
3. Client **必须**实现 RFC 8414 授权服务器元数据发现
4. Server **应该**实现 RFC 8414

**PKCE 是强制性的**——所有客户端（包括保密客户端）都必须使用 PKCE 防止授权码拦截攻击。

**Authorization Code Grant 完整流程**：

```
┌──────────┐     ┌──────────┐     ┌──────────┐
│ Browser  │     │  Client  │     │  Server  │
└────┬─────┘     └────┬─────┘     └────┬─────┘
     │                 │                │
     │                 │── MCP Request ─→│  ① Client 尝试未认证请求
     │                 │←── 401 ────────│  ② Server 返回 401
     │                 │                │
     │                 │ 生成 PKCE:     │
     │                 │ code_verifier  │
     │                 │ code_challenge │
     │                 │                │
     │← 打开浏览器 ────│                │  ③ Client 打开浏览器
     │  (auth URL +    │                │
     │   code_challenge)                │
     │                 │                │
     │── GET /authorize ──────────────→│  ④ 用户登录并授权
     │←── 302 callback?code=xxx ──────│  ⑤ 重定向带回授权码
     │                 │                │
     │── callback ────→│                │  ⑥ 浏览器回调 Client
     │  (auth code)    │                │
     │                 │                │
     │                 │── POST /token ─→│  ⑦ Token 请求
     │                 │  code +         │     (含 code_verifier)
     │                 │  code_verifier  │
     │                 │←── access_token │  ⑧ 返回令牌
     │                 │   + refresh_token
     │                 │                │
     │                 │── MCP Request ─→│  ⑨ 带 token 的正常请求
     │                 │  Authorization: │
     │                 │  Bearer <token> │
```

#### 11.2.7.2 元数据发现

Client **必须**首先尝试通过 RFC 8414 元数据发现获取授权端点：

```
GET /.well-known/oauth-authorization-server
```

Client **应该**在发现请求中包含 `MCP-Protocol-Version` 头。

**授权基础 URL 确定规则**：从 MCP Server URL 中去除 path 部分。例如 MCP Server 在 `https://api.example.com/v1/mcp`，则：
- 授权基础 URL 为 `https://api.example.com`
- 元数据端点必在 `https://api.example.com/.well-known/oauth-authorization-server`

**不支持元数据发现时的默认端点**：

| 端点 | 默认路径 |
|------|---------|
| Authorization Endpoint | `/authorize` |
| Token Endpoint | `/token` |
| Registration Endpoint | `/register` |

#### 11.2.7.3 动态客户端注册 (DCR)

Client 和 Server **应该**支持 RFC 7591 DCR，使 Client 无需用户手动操作即可获取 OAuth client ID。这对 MCP 至关重要：Client 无法预先知道所有可能的 Server，手动注册会阻碍用户体验。

不支持 DCR 的 Server 需要提供替代方式获取 client ID：
1. 在 Client 中硬编码特定 Server 的 client ID
2. 或提供 UI 让用户手动输入注册信息

#### 11.2.7.4 Grant Types 选择

| Grant Type | 适用场景 | 说明 |
|-----------|---------|------|
| Authorization Code + PKCE | 用户授权（Agent 代表用户操作） | 有浏览器参与，最安全的用户授权方式 |
| Client Credentials | 应用间授权（Agent 作为服务调用） | 无需用户参与，client_id + client_secret |

#### 11.2.7.5 Token 使用

**访问令牌**必须通过 HTTP Authorization 头传递：

```http
Authorization: Bearer eyJhbGciOiJIUzI1NiIs...
```

- 每次 HTTP 请求**必须**包含授权头（即使在同一会话中）
- Token **不得**放在 URI 查询字符串中
- 无效或过期 Token **必须**收到 HTTP 401 响应

**Refresh Token 轮换**：

1. 每次使用 refresh token 后 Server **应该**发放新的 refresh token
2. 旧的 refresh token 应立即失效
3. 如果检测到已失效的 refresh token 被使用（可能是 token 被盗），Server **应该**撤销所有关联的 token

#### 11.2.7.6 Bearer Token 与 API Key

除了完整的 OAuth 2.1 流程，更简单的场景可以使用：

**Bearer Token**：与 OAuth 2.1 的 Access Token 使用方式相同，通过 `Authorization: Bearer <token>` 头传递。适用于开发环境下不需要完整 OAuth 流程的简单认证。

**API Key**：虽然不是 MCP 规范明确定义的方式，但许多实现使用自定义 Header（如 `X-API-Key`）传递 API 密钥。这种方式最简单，但安全级别最低（无过期、无轮换、无作用域控制）。仅建议在内部网络或开发环境中使用。

#### 11.2.7.7 第三方授权流

MCP Server **可以**支持通过第三方授权服务器的委托授权。在此流程中：

1. MCP Client 启动与 MCP Server 的标准 OAuth 流程
2. MCP Server 将用户重定向到第三方授权服务器
3. 用户授权第三方服务器
4. MCP Server 将第三方 token 绑定到自己发放的 MCP token
5. MCP Server 完成与 MCP Client 的 OAuth 流程

Server 实现此流程时**必须**：
- 维护第三方 token 和 MCP token 的安全映射
- 在兑现 MCP token 前验证第三方 token 状态
- 处理第三方 token 过期和续期

### 11.2.8 安全威胁模型

MCP 的强大能力——任意数据访问和代码执行路径——伴随着重大安全责任。

#### 11.2.8.1 OAuth 代理攻击面

**One-Click Account Takeover 攻击**：这是一个需要高度重视的威胁场景。攻击链如下：

1. 用户被诱导连接到一个恶意的 MCP Server
2. 该 Server 返回 401，启动 OAuth 流程
3. 用户在浏览器中看到熟悉的授权页面
4. 用户点击"授权"，以为是在给已知应用授权
5. 但实际上，恶意 Server 的 client_id 替代了合法应用
6. 攻击者获得代表用户的 access token
7. 攻击者可以以用户身份调用所有后续 API

**防御措施**：

- Client **必须**清楚地展示正在授权给哪个 Server/应用
- Client **应该**验证 redirect URI（只允许 localhost 或 HTTPS）
- 用户**应该**仔细检查授权页面上的详细信息
- 实现 OAuth 2.1 的**推送授权请求**（PAR / RFC 9126）可以进一步减少攻击面

#### 11.2.8.2 Tool 调用权限模型

Tool 调用遵循**最小权限**原则：

| 安全措施 | 实现要求 |
|---------|---------|
| 用户同意 | 任何 Tool 调用前必须经过用户明确同意 |
| 输入可见性 | Host **应该**在调用前向用户展示工具输入（防止数据外泄） |
| 输出验证 | Host **应该**在将结果传递给 LLM 前验证工具输出 |
| 频率限制 | Server **必须**对 Tool 调用实施频率限制 |
| 输入验证 | Server **必须**验证所有工具输入参数 |
| Trust Boundary | Tool annotations 默认不可信（除非来自受信 Server） |
| 超时保护 | Client **应该**为每个 Tool 调用设置超时 |

**人机回环（Human-in-the-Loop）应该是默认行为**，而不应是例外。这适用于：
- Tool 调用（执行前确认）
- LLM Sampling 请求（用户审查 prompt 和响应）
- 资源访问（用户同意哪些 Server 能访问哪些文件）

#### 11.2.8.3 传输层安全对比

| 安全机制 | 适用场景 | 安全级别 | 说明 |
|---------|---------|---------|------|
| **STDIO** | 本地进程 | 高（操作系统进程隔离） | 不经过网络，凭据通过环境变量传递。父子进程间信任由操作系统保证 |
| **mTLS** | 内部服务间 | 最高 | 双向证书认证，零信任架构推荐 |
| **Bearer Token (OAuth 2.1)** | 用户授权场景 | 高 | 完整的授权流程，支持 PKCE、作用域控制、Token 轮换 |
| **API Key** | 简单/内部场景 | 低 | 无过期控制，无作用域隔离。仅适合开发/内部网络 |

#### 11.2.8.4 核心安全原则

MCP 协议层面无法强制执行这些原则，但所有实现者**应该**遵守：

1. **用户同意和控制**：用户必须明确同意并理解所有数据访问和操作
2. **数据隐私**：Host 在向 Server 暴露用户数据前必须获取明确同意
3. **Tool 安全**：Tools 代表任意代码执行，必须以适当的谨慎对待
4. **LLM Sampling 控制**：用户必须明确批准所有 LLM 采样请求
5. **Server 隔离**：每个 Server 连接之间保持严格的隔离——Server 不能"看到"其他 Server 或完整对话历史

---

## 11.3 Python 实现

本章的实现聚焦于 JSON-RPC 2.0 消息解析器——这是 MCP 协议栈的基石。完整的 MCP Server/Client 实现超出了本章范围（详见第 14 章），但这里的 JSON-RPC 解析器是所有 MCP 实现的必备组件。

### 11.3.1 消息类型定义

`code/python/ch11/json_rpc.py` 定义了四种消息类型的 dataclass：

```python
@dataclass
class JSONRPCRequest:
    id: Union[int, str]
    method: str
    params: Optional[Dict[str, Any]] = None
    jsonrpc: str = "2.0"

@dataclass
class JSONRPCResponse:
    id: Union[int, str]
    result: Any = None
    jsonrpc: str = "2.0"

@dataclass
class JSONRPCError:
    id: Union[int, str]
    code: int
    message: str
    data: Optional[Any] = None
    jsonrpc: str = "2.0"

@dataclass
class JSONRPCNotification:
    method: str
    params: Optional[Dict[str, Any]] = None
    jsonrpc: str = "2.0"
```

### 11.3.2 解析器核心逻辑

`JSONRPCParser` 类的 `parse_message()` 方法实现了基于规则的消息分类：

1. 验证 JSON 解析成功
2. 验证顶层是 JSON 对象（非数组/标量）
3. 验证 `jsonrpc` 字段为 `"2.0"`
4. 按优先级规则判断消息类型：
   - 无 `id` + 有 `method` → Notification
   - 有 `id` + 有 `result` + 有 `error` → 立即拒绝
   - 有 `id` + 有 `method` + 无 `result` + 无 `error` → Request
   - 有 `id` + 有 `error` → Error
   - 有 `id` + 有 `result` + 无 `error` → Response

`serialize()` 方法执行反向操作——将类型化消息对象序列化回紧凑的 JSON 字符串。

**关键验证点**：

- `id` 不能为 `null`（MCP 特有约束）
- `id` 必须是 `string` 或 `int` 类型
- `error.code` 必须是整数
- `error` 对象必须包含 `code` 和 `message`
- 一条消息不能同时包含 `result` 和 `error`

### 11.3.3 运行测试

```bash
cd code/python/ch11
python -m pytest test_json_rpc.py -v
# 42 passed
```

---

## 11.4 Node.js 实现

### 11.4.1 类型定义

`code/node/ch11/JSONRPC.ts` 使用 TypeScript 接口定义消息类型：

```typescript
export interface JSONRPCRequest {
  readonly jsonrpc: "2.0";
  readonly id: string | number;
  readonly method: string;
  readonly params?: Record<string, unknown>;
}

export interface JSONRPCResponse {
  readonly jsonrpc: "2.0";
  readonly id: string | number;
  readonly result: unknown;
}

export interface JSONRPCError {
  readonly jsonrpc: "2.0";
  readonly id: string | number;
  readonly error: {
    readonly code: number;
    readonly message: string;
    readonly data?: unknown;
  };
}

export interface JSONRPCNotification {
  readonly jsonrpc: "2.0";
  readonly method: string;
  readonly params?: Record<string, unknown>;
}

export type JSONRPCMessage =
  | JSONRPCRequest
  | JSONRPCResponse
  | JSONRPCError
  | JSONRPCNotification;
```

TypeScript 的 `Union` 类型和私有类型守卫（`_isRequest`、`_isResponse` 等）使得 `serialize` 方法可以通过类型缩小安全地访问不同类型的字段。

### 11.4.2 工厂函数

```typescript
makeRequest(id, method, params?) → JSONRPCRequest
makeResponse(id, result) → JSONRPCResponse
makeError(id, code, message, data?) → JSONRPCError
makeNotification(method, params?) → JSONRPCNotification
```

### 11.4.3 运行测试

```bash
cd code/node
npx vitest run ch11/json_rpc.test.ts
# 40 passed
```

---

## 11.5 最佳实践

### 11.5.1 能力协商模式

正确的 MCP 实现应该遵循以下能力协商模式：

```
1. Client 发送 initialize，声明自己支持的所有能力
2. Server 响应 initialize，声明自己支持的所有能力
3. 双方取交集 —— 只使用双方都声明支持的能力
4. 在访问任何能力前，先检查对方的能力声明
5. 如果能力缺失，优雅降级而非崩溃
```

**实战示例**：

```python
# Client 端检查 Server 能力
def can_use_sampling(capabilities: dict) -> bool:
    return "sampling" in capabilities

def can_call_tools(capabilities: dict) -> bool:
    return "tools" in capabilities

# 在实际调用前检查
if can_use_sampling(server_caps):
    await client.send_sampling_request(...)
else:
    log.warning("Server does not support sampling, skipping...")
```

### 11.5.2 传输选择决策树

```
是否需要远程访问？
├── 否（本地开发/IDE 插件）
│   → 使用 STDIO 传输
│   → 通过环境变量传递配置
│   → 无需认证层
│
└── 是（远程服务/SaaS）
    → 使用 Streamable HTTP
    ├── 是否需要用户授权？
    │   ├── 是 → OAuth 2.1 + PKCE + DCR
    │   └── 否 → Bearer Token 或 API Key
    └── 是否需要 Server 主动推送？
        ├── 是 → 启用 SSE 流（GET endpoint）
        └── 否 → 仅使用 POST endpoint
```

### 11.5.3 安全加固清单

- [ ] 所有 HTTP 连接使用 TLS（仅 HTTPS）
- [ ] Streamable HTTP Server 验证 `Origin` 头
- [ ] 本地 Server 绑定到 `127.0.0.1` 而非 `0.0.0.0`
- [ ] OAuth 2.1 强制 PKCE（所有客户端）
- [ ] 实现 Refresh Token 轮换
- [ ] Tool 调用前始终经过用户确认
- [ ] 合理设置 Token 过期时间（Access Token 建议 5-15 分钟）
- [ ] 所有请求设置超时（防止连接悬挂）
- [ ] 实现请求频率限制（防止滥用）
- [ ] 日志中屏蔽敏感信息（Token、用户数据）
- [ ] Server 输出进行清理（防止注入）

### 11.5.4 JSON-RPC 错误处理模式

```python
def create_mcp_error(request_id, message_type: str, detail: str):
    """Factory for standard MCP error responses."""
    error_map = {
        "method_not_found": (-32601, "Method not found"),
        "invalid_params": (-32602, "Invalid params"),
        "internal": (-32603, "Internal error"),
        "resource_not_found": (-32002, "Resource not found"),
    }
    code, msg = error_map.get(message_type, (-32603, detail))
    return JSONRPCError(id=request_id, code=code, message=msg, data=detail)
```

---

## 11.6 自测题

1. **概念题**：JSON-RPC 2.0 的请求、响应、通知在结构上有何区别？MCP 对 JSON-RPC 增加了哪些特定约束？（至少列出 3 条）

2. **协议理解题**：在 MCP 的初始化阶段，Client 发送 `initialize` 请求声明协议版本为 `"2025-03-26"`，但 Server 仅支持 `"2024-11-05"`。Server 应该如何响应？Client 收到此响应后又应该如何行动？

3. **比较题**：MCP 的三大原语（Tools、Resources、Prompts）分别由谁控制调用？各自适用于什么场景？为什么需要区分这三种控制模式？

4. **编程题**：实现一个 JSON-RPC 2.0 消息解析器（可以是简化版）。要求：
   - 能区分 Request、Response、Error、Notification 四种消息类型
   - 对不符合规范的消息抛出明确的错误
   - 支持将解析后的消息重新序列化为 JSON 字符串
   - 编写至少 5 个测试用例覆盖边界情况

   提示：可以从本章的 `code/python/ch11/json_rpc.py` 获取参考实现，但鼓励自己独立完成后再对比。

5. **安全分析题**：假设你正在开发一个 MCP Host 应用，用户通过你的应用连接到第三方 MCP Server。请列出至少 5 项你必须在 Host 端实现的安全措施，并说明每项措施防御的具体威胁。

---

## 本章小结

- MCP 是一个开放的、基于 JSON-RPC 2.0 的协议，标准化了 LLM 应用与外部数据源/工具之间的通信
- 三层架构（Host-Client-Server）提供了清晰的关注点分离和安全边界
- JSON-RPC 2.0 定义了四种消息类型：Request（请求）、Response（成功响应）、Error（错误响应）、Notification（单向通知）
- 生命周期分为初始化（能力协商）、运行（协议操作）和关闭三阶段
- 三大原语按控制权区分：Prompts（用户控制）、Resources（应用控制）、Tools（模型控制）
- 两种标准传输：STDIO（本地，零配置）和 Streamable HTTP（远程，支持 SSE 和多客户端）
- 授权基于 OAuth 2.1，强制 PKCE，支持 DCR 和元数据发现
- 安全是 MCP 的头等关注——特别是 Tool 调用权限、用户同意、传输安全
- 完整的 JSON-RPC 解析器实现（Python + TypeScript）是所有 MCP 组件的基础
