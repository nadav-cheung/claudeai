# 第 12 章：MCP 实战构建 —— 从协议到代码

## 12.1 概念全景

### 12.1.1 从规范到工程

第 11 章系统性地剖析了 MCP 协议规范——三层架构、JSON-RPC 2.0 传输、生命周期管理、Tools/Resources/Prompts 三大原语、能力协商机制。但规范本身只是蓝图。将蓝图转化为可运行的服务器、可连接多种语言的客户端、以及可处理异步任务的生产系统，才是工程真正开始的地方。

本章将带你从头构建一个完整的 MCP 生态系统：

1. **MCP Server**：注册工具、暴露资源、提供 Prompt 模板，支持 stdio 和 HTTP 双传输模式
2. **MCP Client**：连接管理、能力协商、工具调用、资源读取、自动重连
3. **MCP Tasks**：基于 SEP-1686 规范的异步任务系统——提交、轮询状态、获取结果、取消
4. **MCP Apps（SEP-1865）概述**：理解 MCP 的交互式 UI 扩展
5. **MCP Registry**：发布与发现 MCP 服务器
6. **MCP Inspector**：调试工具链
7. **跨语言互操作**：Python Server + Node.js Client 协同工作

### 12.1.2 为什么自己实现？

在真正的生产环境中，你应该使用官方 SDK：

```bash
# Python
pip install mcp

# Node.js
npm install @modelcontextprotocol/server @modelcontextprotocol/client
```

官方 SDK（Python 的 `FastMCP`、TypeScript 的 `@modelcontextprotocol/server`）封装了 JSON-RPC 序列化、能力协商、传输层管理等底层细节，让你可以专注于业务逻辑。

但在这一章，我们从零实现核心逻辑，目的有三：

1. **理解协议本质**：亲手编写 JSON-RPC 编解码、能力协商握手、消息路由，比任何文档都更能帮助你理解 MCP 的工作原理
2. **排查问题根基**：当你遇到奇怪的 `-32601 Method not found` 错误或能力不匹配时，理解底层机制让你可以快速定位问题
3. **掌握互操作原理**：理解 Python 和 Node.js 如何通过完全独立的实现来互通——这正是 MCP 协议设计的核心价值

### 12.1.3 本章架构概览

```
┌─────────────────────────────────────────────────┐
│                   MCP Server (Python)             │
│  ┌─────────┐  ┌──────────┐  ┌─────────┐         │
│  │  Tools   │  │ Resources │  │ Prompts  │         │
│  └────┬────┘  └────┬─────┘  └────┬────┘         │
│       └─────────────┼─────────────┘              │
│              ┌──────▼──────┐                     │
│              │ JSON-RPC 2.0 │                    │
│              └──────┬──────┘                     │
│                     │ stdio / HTTP                │
└─────────────────────┼────────────────────────────┘
                      │
    ┌─────────────────▼────────────────────────────┐
    │            MCP Protocol Messages              │
    │   initialize ↔ initialized                    │
    │   tools/list ↔ list  tools/call ↔ result      │
    │   tasks/get ↔ status tasks/result ↔ result    │
    └─────────────────┬────────────────────────────┘
                      │
┌─────────────────────▼────────────────────────────┐
│                MCP Client (Node.js)                │
│  ┌──────────────┐  ┌──────────┐  ┌──────────┐   │
│  │ Cap Negotiation│  │ Reconnect │  │ Retry    │   │
│  └──────┬───────┘  └────┬─────┘  └────┬─────┘   │
│         └───────────────┼─────────────┘          │
│                  ┌──────▼──────┐                  │
│                  │ JSON-RPC 2.0 │                 │
│                  └──────┬──────┘                 │
│                         │ stdio / HTTP             │
└──────────────────────────────────────────────────┘
```

---

## 12.2 协议规范

### 12.2.1 构建 MCP Server

MCP Server 的核心职责是：接收 JSON-RPC 请求，执行相应的操作，返回 JSON-RPC 响应。一个完整的 Server 需要处理三类消息：

| 消息类型 | 方向 | 有无 ID | 用途 |
|---------|------|--------|------|
| Request | Client → Server | 有 | 发起操作，期待响应 |
| Response | Server → Client | 有（匹配 Request） | 返回请求结果 |
| Error | Server → Client | 有（匹配 Request） | 返回错误信息 |
| Notification | Client → Server 或 Server → Client | 无 | 单向通知，无需响应 |

#### 能力声明

Server 启动后，Client 发送的第一个请求永远是 `initialize`。这是 MCP 中最关键的握手过程：

```json
// Client → Server
{
  "jsonrpc": "2.0",
  "id": 1,
  "method": "initialize",
  "params": {
    "protocolVersion": "2025-11-25",
    "capabilities": {
      "roots": { "listChanged": true },
      "sampling": {}
    },
    "clientInfo": {
      "name": "my-mcp-client",
      "version": "1.0.0"
    }
  }
}
```

Server 必须响应自己的能力和信息：

```json
// Server → Client
{
  "jsonrpc": "2.0",
  "id": 1,
  "result": {
    "protocolVersion": "2025-11-25",
    "capabilities": {
      "tools": { "listChanged": false },
      "resources": { "subscribe": false, "listChanged": false },
      "prompts": { "listChanged": false }
    },
    "serverInfo": {
      "name": "weather-mcp-server",
      "version": "1.0.0"
    }
  }
}
```

**能力协商的关键规则：**

1. Server 声明的能力决定了 Client 可以调用哪些方法。如果 `capabilities.tools` 未声明，Client 不应该调用 `tools/list` 和 `tools/call`
2. `protocolVersion` 使用 `YYYY-MM-DD` 格式，代表规范的发布日期。Client 和 Server 必须协商选择一个双方都支持的版本
3. Client 在收到 `initialize` 响应后，必须发送 `notifications/initialized` 通知来告知 Server 握手完成

#### 工具注册

Tool 是 MCP 最核心的原语。一个 Tool 的定义包含：

- `name`：唯一标识符（1-64 字符，字母数字加连字符/下划线。SEP-986 规范化了命名格式）
- `description`：人类可读的描述，供 LLM 理解工具用途
- `inputSchema`：JSON Schema 定义的输入参数规范

注册流程的本质是为每个 Tool 建立 `(name, schema, handler)` 三元组。当 Client 发送 `tools/call` 请求时，Server 查找对应的 handler，验证参数，执行，返回结果。

```json
// tools/list 返回所有可用工具
{
  "jsonrpc": "2.0",
  "id": 2,
  "method": "tools/list",
  "params": {}
}

// 响应
{
  "jsonrpc": "2.0",
  "id": 2,
  "result": {
    "tools": [
      {
        "name": "get_weather",
        "description": "获取指定城市的实时天气信息",
        "inputSchema": {
          "type": "object",
          "properties": {
            "city": {
              "type": "string",
              "description": "城市名称"
            },
            "units": {
              "type": "string",
              "enum": ["celsius", "fahrenheit"],
              "default": "celsius"
            }
          },
          "required": ["city"]
        }
      }
    ]
  }
}
```

工具调用遵循标准的 Request-Response 模式：

```json
// tools/call
{
  "jsonrpc": "2.0",
  "id": 3,
  "method": "tools/call",
  "params": {
    "name": "get_weather",
    "arguments": {
      "city": "Beijing",
      "units": "celsius"
    }
  }
}

// 响应
{
  "jsonrpc": "2.0",
  "id": 3,
  "result": {
    "content": [
      {
        "type": "text",
        "text": "北京当前气温：22°C，晴，湿度45%"
      }
    ],
    "isError": false
  }
}
```

注意工具调用结果的特殊结构：

- `content` 是数组，每个元素是 `{type, text}` 或 `{type, data, mimeType}` 的内容块
- `isError` 标记工具执行是否出错——设为 `true` 时，LLM 会知道工具执行失败并决定如何向用户解释
- 对于支持 MCP Tasks 的 Server，工具还可能在 `tools/list` 返回中包含 `execution.taskSupport` 字段

#### 资源暴露

Resource 是 MCP 的另一核心原语，代表 Server 可以向 Client 暴露的只读数据。每个 Resource 通过 URI 标识：

```
file:///home/user/docs/report.pdf    # 文件资源
weather://beijing/current           # 自定义协议资源
postgres://db/schema/users          # 数据库资源
```

资源可以是二进制的（如图片、PDF）或文本的（如 JSON、Markdown）。Server 在读取资源时返回对应的 MIME 类型：

```json
// resources/list
{"jsonrpc": "2.0", "id": 4, "method": "resources/list", "params": {}}

// 响应
{
  "jsonrpc": "2.0",
  "id": 4,
  "result": {
    "resources": [
      {
        "uri": "weather://config/supported-cities",
        "name": "支持的城市列表",
        "description": "所有支持天气查询的城市名称",
        "mimeType": "application/json"
      },
      {
        "uri": "weather://beijing/current",
        "name": "北京当前天气",
        "description": "北京实时天气数据（每分钟更新）",
        "mimeType": "application/json"
      }
    ]
  }
}

// resources/read
{
  "jsonrpc": "2.0",
  "id": 5,
  "method": "resources/read",
  "params": {"uri": "weather://config/supported-cities"}
}

// 响应
{
  "jsonrpc": "2.0",
  "id": 5,
  "result": {
    "contents": [
      {
        "uri": "weather://config/supported-cities",
        "mimeType": "application/json",
        "text": "[\"北京\", \"上海\", \"广州\", \"深圳\", \"杭州\", \"成都\"]"
      }
    ]
  }
}
```

资源 URI 的设计建议：

- 使用有意义的命名空间（如 `weather://` 而非 `res://`）
- 支持参数化路径（路径中包含变量部分，通过 Resource Templates 映射，格式如 `weather://{city}/forecast`）
- 对大型资源考虑分块传输

#### Prompt 模板

Prompt 是预定义的对话模板。它们不是直接发送给 LLM 的消息，而是**参数化的提示词生成器**。当 Client 调用 `prompts/get` 时，Server 返回一个包含消息数组的结构，Client 的 Host 可以将其注入到正在进行的对话中：

```json
// prompts/list
{"jsonrpc": "2.0", "id": 6, "method": "prompts/list", "params": {}}

// prompts/get
{
  "jsonrpc": "2.0",
  "id": 7,
  "method": "prompts/get",
  "params": {
    "name": "weather_analysis",
    "arguments": {"city": "北京", "period": "weekly"}
  }
}

// 响应
{
  "jsonrpc": "2.0",
  "id": 7,
  "result": {
    "description": "分析指定城市的天气趋势",
    "messages": [
      {
        "role": "user",
        "content": {
          "type": "text",
          "text": "请分析北京过去一周的天气数据，包括温度趋势、降水情况和空气质量变化。请重点关注极端天气事件。"
        }
      }
    ]
  }
}
```

Prompt 设计最佳实践：

- 描述要具体：让 LLM 和用户都能清楚知道这个 Prompt 做什么
- 参数要显式：不要依赖隐式上下文，所有变量都通过 `arguments` 传入
- 保持模板化：Prompt 是生成器，不是对话历史——不要包含具体的对话内容

### 12.2.2 构建 MCP Client

如果说 Server 是"服务员"——提供服务并响应请求，那么 Client 就是"顾客"——主动发起连接、发现能力、调用服务。

#### 连接管理

MCP Client 通过传输层连接到 Server。当前主流传输方式：

| 传输方式 | 适用场景 | 连接模式 | 典型启动方式 |
|---------|---------|---------|------------|
| **stdio** | 本地进程通信 | Client 作为父进程启动 Server 子进程 | `client.connect_stdio("python", ["mcp_server.py"])` |
| **Streamable HTTP** | 远程服务 | Client 向 Server URL 发起 HTTP 请求 | `client.connect_http("https://mcp.example.com")` |
| **SSE** (被 Streamable HTTP 取代) | 远程服务（遗留） | Server 向 Client 推送事件流 | 不再推荐使用 |

stdio 模式是最简单、最安全的连接方式。Client 通过子进程的标准输入/输出与 Server 通信，每行是一个完整的 JSON-RPC 消息，用换行符分隔：

```
→ {"jsonrpc":"2.0","id":1,"method":"initialize",...}\n
← {"jsonrpc":"2.0","id":1,"result":{...}}\n
→ {"jsonrpc":"2.0","method":"notifications/initialized"}\n
→ {"jsonrpc":"2.0","id":2,"method":"tools/list",...}\n
← {"jsonrpc":"2.0","id":2,"result":{...}}\n
```

HTTP 模式适合远程部署，Server 暴露一个 HTTP 端点，Client 通过 POST 请求发送 JSON-RPC 消息：

```
POST /mcp HTTP/1.1
Content-Type: application/json

{"jsonrpc":"2.0","id":1,"method":"initialize",...}
```

#### 能力协商流程

Client 的初始化流程需要严格遵守以下步骤：

```
1. Client 启动 Server 子进程 或 连接 HTTP 端点
2. Client 发送 initialize 请求（携带 Client 能力）
3. Server 返回 initialize 响应（携带 Server 能力）
4. Client 检查 protocolVersion 兼容性
5. Client 发送 notifications/initialized（握手完成）
6. Client 根据 Server 能力决定后续操作
```

**关键规则：**

- 在收到 `initialized` 通知之前，Server 可以拒绝处理除 `initialize` 之外的任何请求
- Client 必须等待 `initialize` 响应后才能发送后续请求
- 如果协议的 major version 不兼容，Client 应该断开连接并报错

#### 自动重连

生产环境中的 Client 必须具备自动重连能力。Server 可能因为崩溃、重启、网络波动等原因断开连接。一个健壮的 Client 重连策略应该：

1. **检测断连**：通过心跳（定时 `ping` 调用或检查进程存活状态）检测
2. **指数退避**：避免在 Server 重启期间频繁重连导致"惊群效应"
3. **最大重试次数**：防止无限重连循环
4. **状态恢复**：重连后重新初始化，恢复必要的状态

### 12.2.3 MCP Tasks（SEP-1686）

MCP Tasks 是在 `2025-11-25` 规范版本中引入的实验性功能（在扩展机制正式化后由 SEP-2663 重新定义为 Extensions Track 扩展）。它为 MCP 添加了异步任务执行能力——"提交后稍后获取结果"模式。

#### 为什么需要 Tasks？

传统的 MCP 工具调用是同步的：Client 发送 `tools/call`，等待 Server 处理完成，获取结果。这对于毫秒级到秒级的操作非常合适。但以下场景打破了这一模式：

- **长时间计算**：一个数据分析工具可能需要处理数 TB 的数据，耗时数分钟甚至数小时
- **外部工作流**：CI/CD 触发、模型训练任务提交——你不知道什么时候完成
- **人工审核**：某些工具需要人工审批，可能数小时后才能有结果
- **批量处理**：批量邮件发送、批量数据转换——需要追踪每个子任务的进度

#### 核心概念

Tasks 定义了 Requestor（请求方）和 Receiver（接收方）两个角色。注意：**Client 和 Server 都可以是 Requestor 或 Receiver**——这是一个对称的设计。例如：

- Client 请求 Server 执行耗时工具 → Client 是 Requestor，Server 是 Receiver
- Server 请求 Client 进行 LLM Sampling → Server 是 Requestor，Client 是 Receiver

Task 有明确的状态机：

```
                        ┌──────────┐
             ┌─────→    │ cancelled │  (终态)
             │          └──────────┘
             │               ↑
┌─────────┐  │          ┌────┴─────┐
│ working  ├──┼─────→    │ completed │  (终态)
└────┬────┘  │          └──────────┘
     │       │               ↑
     │  ┌────┴──────┐   ┌────┴─────┐
     └──┤input_required├──→│  failed   │  (终态)
        └────────────┘   └──────────┘
```

各状态含义：

| 状态 | 含义 | Requestor 应执行的操作 |
|------|------|---------------------|
| `working` | 任务正在处理中 | 通过 `tasks/get` 轮询状态 |
| `input_required` | Receiver 需要 Requestor 提供更多输入 | 调用 `tasks/result` 获取输入请求 |
| `completed` | 任务成功完成 | 调用 `tasks/result` 获取最终结果 |
| `failed` | 任务执行失败 | 调用 `tasks/result` 获取错误信息 |
| `cancelled` | 任务被取消 | 终端状态，不再变化 |

#### 创建任务

通过在请求的 `params` 中添加 `task` 字段来将普通请求增强为 Task 请求：

```json
{
  "jsonrpc": "2.0",
  "id": 10,
  "method": "tools/call",
  "params": {
    "name": "analyze_large_dataset",
    "arguments": {"dataset_id": "ds_2025_q4", "metrics": ["revenue", "churn"]},
    "task": {
      "ttl": 3600000
    }
  }
}
```

- `ttl`（Time-To-Live，毫秒）：请求的任务生命周期，超时后 Receiver 可能删除任务
- Server 返回的不是工具结果，而是 `CreateTaskResult`：

```json
{
  "jsonrpc": "2.0",
  "id": 10,
  "result": {
    "task": {
      "taskId": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
      "status": "working",
      "statusMessage": "Beginning data analysis...",
      "createdAt": "2025-11-25T10:30:00Z",
      "lastUpdatedAt": "2025-11-25T10:30:00Z",
      "ttl": 3600000,
      "pollInterval": 5000
    }
  }
}
```

#### 轮询状态

Requestor 通过 `tasks/get` 定期检查任务状态：

```json
// 请求
{
  "jsonrpc": "2.0",
  "id": 11,
  "method": "tasks/get",
  "params": {"taskId": "a1b2c3d4-e5f6-7890-abcd-ef1234567890"}
}

// 响应（仍在运行）
{
  "jsonrpc": "2.0",
  "id": 11,
  "result": {
    "taskId": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
    "status": "working",
    "statusMessage": "Processing chunk 42 of 200...",
    "createdAt": "2025-11-25T10:30:00Z",
    "lastUpdatedAt": "2025-11-25T10:35:00Z",
    "ttl": 3600000,
    "pollInterval": 5000
  }
}
```

Requestor 应该遵守 `pollInterval` 的建议值，避免过于频繁的轮询。

#### 获取结果

一旦任务进入终态（`completed`、`failed` 或 `cancelled`），通过 `tasks/result` 获取最终结果：

```json
// 请求
{
  "jsonrpc": "2.0",
  "id": 12,
  "method": "tasks/result",
  "params": {"taskId": "a1b2c3d4-e5f6-7890-abcd-ef1234567890"}
}

// 响应（成功）
{
  "jsonrpc": "2.0",
  "id": 12,
  "result": {
    "content": [
      {"type": "text", "text": "分析完成。2025 Q4 营收增长 12.3%，客户流失率降至 4.1%。"}
    ],
    "isError": false,
    "_meta": {
      "io.modelcontextprotocol/related-task": {
        "taskId": "a1b2c3d4-e5f6-7890-abcd-ef1234567890"
      }
    }
  }
}
```

`tasks/result` 对非终态任务会**阻塞**直到任务完成。Client 可以并行使用 `tasks/get`（非阻塞轮询）和 `tasks/result`（阻塞等待）。

#### 工具级别的 Task 控制

在 `tools/list` 的返回中，每个工具可以通过 `execution.taskSupport` 声明其对 Task 的支持级别：

| 值 | 含义 |
|---|------|
| `"required"` | 该工具**必须**通过 Task 方式调用，不支持同步调用 |
| `"optional"` | 该工具**可以**通过 Task 方式调用，也可以同步调用 |
| `"forbidden"` 或不声明 | 该工具**不支持** Task 方式调用 |

#### Tasks 与 Batch API 的对比

虽然两者都支持异步处理模式，但有本质区别：

| 维度 | MCP Tasks | Anthropic Batch API |
|------|----------|---------------------|
| 层面 | 协议层（通用模式） | API 层（特定提供商） |
| 发起方 | 任何 Requestor（Client 或 Server） | Client 发起 |
| 任务类型 | 任意 MCP 请求（工具调用、Sampling 等） | Messages API 请求 |
| 状态追踪 | `tasks/get` 实时轮询 | `GET /v1/messages/batches/{id}` |
| 成本 | N/A（非计费协议特性） | 50% 折扣 |
| 并发控制 | `pollInterval` 和 `ttl` | 批次级别（RPM 限制） |

简言之：Tasks 是一个**通用的异步请求协议模式**，Batch API 是一个**特定提供商的批量推理经济模型**。

#### 通知机制

除了主动轮询，Receiver 还可以通过 `notifications/tasks/status` 通知 Requestor 状态变更：

```json
{
  "jsonrpc": "2.0",
  "method": "notifications/tasks/status",
  "params": {
    "taskId": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
    "status": "completed",
    "createdAt": "2025-11-25T10:30:00Z",
    "lastUpdatedAt": "2025-11-25T10:50:00Z",
    "ttl": 3600000
  }
}
```

但 Requestor 绝不能依赖通知——通知是**可选**的，Server 可以选择不发送。Requestor 应该始终保持主动轮询。

### 12.2.4 MCP Apps（SEP-1865）概述

MCP Apps（SEP-1865, Extensions Track, Final 状态）是 MCP 的一个重要扩展，标准化了 Server 向 Host 交付交互式用户界面的方式。它解决了纯文本/结构化数据无法满足的 UI 需求场景——例如数据可视化仪表盘、表单填写、富媒体播放。

#### 核心设计

1. **UI Resources（`ui://` 协议）**：Server 通过声明 `ui://` URI scheme 的资源来暴露 UI 模板。这些资源在 Server 的 `resources/list` 中可被发现，Host 可以预取模板以提高性能。

2. **Tool-UI 关联**：工具通过元数据引用 UI 资源，形成 "工具调用 → 获取数据 → 渲染 UI" 的工作流。例如天气查询工具返回数据后，Host 渲染预报图表。

3. **双向通信**：UI 内容运行在 sandboxed iframe 中，通过标准 MCP JSON-RPC 与 Host 通信。这意味着 UI 可以发起工具调用、读取资源、请求 Sampling——所有这些都经过 Host 的审计和安全控制。

4. **安全模型**：
   - 所有 UI 内容在 sandboxed iframe 中运行
   - UI 发起的所有操作都经过 Host 的日志记录和审计
   - Host 可以要求用户显式批准 UI 发起的工具调用
   - 预声明的模板允许 Host 在渲染前审查内容

5. **初始内容类型**：`text/html;profile=mcp-app`——HTML 是通用且成熟的 UI 格式，sandbox 机制已被广泛理解

MCP Apps 的核心推理是：**复用 MCP 的 JSON-RPC 基础设施**而非发明新的 UI 协议，降低了实现和维护成本。

### 12.2.5 MCP Registry

MCP Registry 是官方的 MCP 服务器元数据中心仓库，于 2025 年 9 月以预览版发布，截至 2025 年 11 月已收录近 2,000 个服务器条目。

#### Registry 的核心价值

Registry 解决的是 MCP 生态的"发现"问题：用户如何找到可用的 MCP Server？Client 如何自动发现和配置 Server？

```
┌──────────────┐     ┌──────────────────┐     ┌─────────────────┐
│ Server 开发者  │──→ │   MCP Registry    │──→ │  下游聚合器       │
│ (发布元数据)   │     │ (中央元数据仓库)    │     │ (市场、应用商店)   │
└──────────────┘     └──────────────────┘     └────────┬────────┘
                                                        │
                                                  ┌─────▼─────┐
                                                  │ Host 应用  │
                                                  │ (最终消费)  │
                                                  └───────────┘
```

**关键设计原则：**

1. **Registry 只存元数据，不存代码**：实际代码托管在 npm、PyPI、Docker Hub 等包注册表中。Registry 的 `server.json` 包含指向这些包注册表的引用。

2. **命名空间认证**：Server 名称采用反向 DNS 格式（如 `io.github.username/server-name`），通过 GitHub 账户验证或域名验证确保命名空间的真实性。这提供了信任和责任机制。

3. **公开服务优先**：Registry 只支持公开可访问的 Server。私有 Server（仅限企业内部网络或私有包注册表的）需要自建私有 Registry。

4. **消费模式**：Registry 主要被下游聚合器（如 MCP 市场）通过 REST API 消费。Host 应用不应该直接消费 Registry。

#### REST API

```
# 列出所有 Server
GET https://registry.modelcontextprotocol.io/v0.1/servers

# 搜索 Server
GET https://registry.modelcontextprotocol.io/v0.1/servers?search=weather

# 获取单个 Server 详情
GET https://registry.modelcontextprotocol.io/v0.1/servers/{qualifiedName}

# 发布 Server（需要认证）
POST https://registry.modelcontextprotocol.io/v0.1/servers
```

#### server.json 结构

```json
{
  "name": "io.github.user/weather-mcp",
  "description": "Real-time weather data and forecasts",
  "packageType": "npm",
  "packageName": "@user/weather-mcp",
  "command": "npx",
  "args": ["-y", "@user/weather-mcp"],
  "env": {},
  "capabilities": {
    "tools": true,
    "resources": true
  },
  "version": "1.0.0",
  "homepage": "https://github.com/user/weather-mcp"
}
```

### 12.2.6 调试与 MCP Inspector

MCP Inspector 是官方提供的调试工具，通过 npm 分发：

```bash
npx -y @modelcontextprotocol/inspector
```

启动后，Inspector 会在浏览器中打开一个交互界面，你可以：

- **连接到 MCP Server**：输入 Server 命令（如 `python mcp_server.py`）或 HTTP URL
- **探索能力**：查看 Server 宣告的 Tools、Resources 和 Prompts
- **测试工具调用**：手动构造参数、发送 `tools/call` 请求、观察响应
- **查看资源内容**：浏览和读取 Server 暴露的资源
- **追踪 JSON-RPC 消息**：实时查看所有 Request/Response/Notification 的完整 JSON-RPC 内容

Inspector 对于开发的帮助：

- **快速验证**：写完工具后，不需要写 Client 代码，在 Inspector 中直接调用测试
- **协议级调试**：看到完整 JSON-RPC 交互过程，定位协议错误
- **能力测试**：验证 Server 是否正确声明了能力、`tools/list` 返回的 schema 是否符合预期

### 12.2.7 跨语言互操作测试

MCP 的核心价值之一是**语言无关的互操作性**。一个 Python Server 应该能无缝服务于 JavaScript/TypeScript Client，反之亦然。这是因为 MCP 的通信建立在纯文本 JSON-RPC 之上，与实现语言完全解耦。

**互操作测试**验证以下场景：

1. Python MCP Server + Node.js MCP Client（通过 stdio）
2. 工具注册与发现：Client `tools/list` 能看到所有 Python Server 注册的工具
3. 工具调用与结果：Client `tools/call` 能正确获取 Python Server 的执行结果
4. 资源读取：Client `resources/read` 能正确获取 Python Server 暴露的资源
5. 能力协商：双方正确完成 `initialize` 握手
6. Tasks 流程：Task 创建、轮询、结果获取的完整生命周期

这一测试是本章的"毕业考试"——只有当 Python Server 和 Node.js Client 完全互通时，你才真正掌握了 MCP 的构建。

---

## 12.3 Python 实现

### 12.3.1 MCPServer

#### 设计要点

`MCPServer` 类是 MCP 服务器端的核心实现，负责：

- 注册和管理 Tools、Resources、Prompts
- 实现 JSON-RPC 2.0 消息的序列化/反序列化
- 处理 `initialize` 握手和能力协商
- 支持 stdio 和 HTTP 两种传输模式
- 管理活跃的 MCP Tasks

#### 核心设计决策

**1. 基于 `asyncio` 的异步架构**

MCP Server 可能是 I/O 密集型的（数据库查询、API 调用、文件操作），同步实现会阻塞整个服务。使用 `asyncio` 确保并发能力：

```python
async def run_stdio(self):
    """通过标准输入/输出运行 MCP Server。"""
    loop = asyncio.get_event_loop()
    reader = asyncio.StreamReader()
    protocol = asyncio.StreamReaderProtocol(reader)
    await loop.connect_read_pipe(lambda: protocol, sys.stdin)
    # 从 stdin 逐行读取 JSON-RPC 消息...

async def run_http(self, host: str, port: int):
    """通过 HTTP 运行 MCP Server。"""
    # 使用 aiohttp 或任何异步 HTTP 框架
```

**2. 工具调用使用 `isError` 标志**

MCP 规范要求工具返回 `{content: [...], isError: boolean}` 格式。`isError` 为 `true` 时，LLM 会知道工具执行失败并据此调整行为。我们的 Server 实现优雅处理 handler 异常：

```python
async def _handle_tools_call(self, params: dict) -> dict:
    tool_name = params["name"]
    arguments = params.get("arguments", {})
    handler = self._tools.get(tool_name)

    if not handler:
        return {"content": [{"type": "text", "text": f"Unknown tool: {tool_name}"}], "isError": True}

    try:
        result = await handler(arguments) if asyncio.iscoroutinefunction(handler) else handler(arguments)
        return {"content": [{"type": "text", "text": str(result)}], "isError": False}
    except Exception as exc:
        return {"content": [{"type": "text", "text": str(exc)}], "isError": True}
```

### 12.3.2 MCPClient

`MCPClient` 负责：

- 启动 Server 子进程（stdio 模式）或连接 HTTP 端点
- 管理 JSON-RPC 请求 ID 的递增
- 能力协商（`initialize` 握手）
- 自动重连（指数退避）
- 提供便捷方法（`list_tools`、`call_tool`、`list_resources`、`read_resource`）

### 12.3.3 MCPTask（Tasks 实现）

`MCPTask` 类封装了 MCP Tasks 的全部生命周期操作：

- `submit_task`：通过 `tools/call` 发送带 `task` 参数的请求
- `get_task_status`：通过 `tasks/get` 轮询任务状态
- `get_task_result`：通过 `tasks/result` 获取最终结果
- `list_tasks`：通过 `tasks/list` 列出全部任务
- `cancel_task`：通过 `tasks/cancel` 取消任务

---

## 12.4 Node.js 实现

Node.js 端实现完全镜像 Python 的结构，但利用 TypeScript 的类型系统提供更强的编译期保证。

### 12.4.1 MCPServer（TypeScript）

核心接口定义：

```typescript
interface ToolDefinition {
  name: string;
  description: string;
  inputSchema: Record<string, unknown>;
  handler: (args: Record<string, unknown>) => Promise<ToolResult>;
}

interface ToolResult {
  content: ContentBlock[];
  isError: boolean;
}

interface ContentBlock {
  type: "text" | "image" | "resource";
  text?: string;
  data?: string;
  mimeType?: string;
}
```

### 12.4.2 MCPClient（TypeScript）

Node.js 的 stdio 通信使用原生 `child_process.spawn`，通过 child process 的 `stdin`/`stdout` 进行 JSON-RPC 行协议通信。

### 12.4.3 MCPTasks（TypeScript）

与 Python 版本完全对称的 Task 生命周期管理。

---

## 12.5 最佳实践

### 12.5.1 Server 设计模式

**1. 工具粒度：宁细勿粗**

```python
# 不好：一个工具做太多事
def manage_everything(action, target, params): ...

# 好：每个工具聚焦一个职责
def create_user(name, email): ...
def delete_user(user_id): ...
def search_users(query): ...
```

粗粒度工具会让 LLM 难以理解和使用。细粒度工具更容易组合，也更容易测试。

**2. Schema 描述要详细**

LLM 依赖 `inputSchema` 中的 `description` 字段来理解工具用途。越详细的描述，LLM 调用越准确：

```python
{
    "name": "get_stock_price",
    "description": "获取指定股票代码的当前价格。"
                   "返回最新成交价、涨跌幅和成交量。数据来源于交易所实时行情。",
    "inputSchema": {
        "type": "object",
        "properties": {
            "symbol": {
                "type": "string",
                "description": "股票代码，如 AAPL（苹果）、TSLA（特斯拉）。不区分大小写。"
            }
        },
        "required": ["symbol"]
    }
}
```

**3. 错误处理：用 `isError` 而非异常**

工具 handler 中捕获的异常应该转换为 `{isError: true}` 的返回，而不是让异常传播到 JSON-RPC 层。这样 LLM 可以读取错误信息并决定如何应对：

```python
def stock_price_handler(args):
    try:
        price = fetch_price(args["symbol"])
        return {"content": [{"type": "text", "text": f"${price:.2f}"}], "isError": False}
    except SymbolNotFoundError:
        return {"content": [{"type": "text", "text": "股票代码无效，请检查后重试。"}], "isError": True}
```

### 12.5.2 重连策略

**指数退避算法：**

```
第 1 次重连：等待 1 秒
第 2 次重连：等待 2 秒
第 3 次重连：等待 4 秒
第 4 次重连：等待 8 秒
...
最多重试 5 次，最大等待间隔 30 秒
```

实现中的关键点：

1. 重连前必须重置所有内部状态（pending requests、消息缓冲区）
2. 重连成功后自动发送 `initialize` 重新进行能力协商
3. 对于幂等性操作（如 `tools/list`），可以在重连后自动重新执行

### 12.5.3 传输模式选择

| 场景 | 推荐传输 | 理由 |
|------|---------|------|
| 本地开发 | stdio | 简单、安全、无网络配置 |
| 单机部署 | stdio | 零网络开销，进程隔离 |
| 远程服务 | Streamable HTTP | 跨网络、支持负载均衡 |
| 容器化部署 | Streamable HTTP | Service Mesh 兼容、健康检查方便 |
| 高并发服务 | Streamable HTTP | 连接池、keep-alive、水平扩展 |

### 12.5.4 调试工作流

推荐的 MCP 开发调试流程：

```
1. 编写 Server → 2. Inspector 手动测试 → 3. 单元测试 → 4. 集成测试 → 5. 跨语言互操作测试
```

每一步的具体方法：

1. **编写 Server**：先定义工具 schema，再实现 handler，最后注册到 Server
2. **Inspector 测试**：`npx -y @modelcontextprotocol/inspector`，连接 Server，手动调用工具，检查返回结果
3. **单元测试**：测试 handler 逻辑（独立于 MCP 协议层）、测试 JSON-RPC 编解码
4. **集成测试**：启动 Server，通过 Client 连接，测试完整的 Request-Response 循环
5. **跨语言互操作测试**：Python Server + Node.js Client（或反过来），验证完全互操作

常见调试技巧：

- 在 Server 的每个 JSON-RPC handler 中添加 debug 日志，记录请求方法和参数
- 使用 `jq` 格式化 JSON-RPC 消息以便阅读
- 检查 `initialize` 响应的 `capabilities` 是否包含了你的 Client 需要的方法
- 如果 Client 调用 `tools/call` 失败，首先检查 `tools/list` 返回的工具名是否完全匹配

---

## 12.6 自测题

### 问题 1：能力协商（概念题）

Client 发送 `initialize` 请求后收到了以下 Server 响应：

```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "result": {
    "protocolVersion": "2025-03-26",
    "capabilities": {
      "tools": { "listChanged": false }
    },
    "serverInfo": {
      "name": "minimal-server",
      "version": "1.0.0"
    }
  }
}
```

Client 随后尝试调用 `resources/list` 和 `prompts/list`。会发生什么？为什么？

### 问题 2：Task 状态机（编码题）

编写一个 Python 函数 `simulate_task_lifecycle(client, tool_name, arguments)`，它：
1. 通过 `submit_task` 提交一个 Task
2. 以不超过 `pollInterval` 的频率轮询状态，直到任务完成或失败
3. 如果任务失败，返回 `{"success": False, "error": status_message}`
4. 如果任务完成，返回 `{"success": True, "result": result}`
5. 如果轮询超过 60 秒，返回 `{"success": False, "error": "timeout"}`

### 问题 3：跨语言互操作（编码题）

你有一个用 Python 编写的 MCP Server（通过 stdio 运行），Server 注册了以下工具：

- `echo(message: str) -> str`：返回相同的消息
- `add(a: int, b: int) -> int`：返回两数之和
- `get_server_info() -> dict`：返回 `{"language": "python", "version": "1.0.0"}`

请编写一个 Node.js 测试脚本，验证：
1. 能成功连接到 Python Server
2. 能正确列出注册的工具
3. 调用 `echo("hello from node")` 并验证返回结果
4. 调用 `add(40, 2)` 并验证返回 `42`
5. 调用 `get_server_info()` 并验证 `language` 字段为 `"python"`

### 问题 4：设计题

你正在设计一个 MCP Server，它需要为 LLM 提供文件系统访问。你需要暴露以下能力：
- 列出指定目录中的文件
- 读取指定文件的内容
- 搜索包含特定关键词的文件

请设计 Tools 和 Resources 的划分方案。哪些应该作为 Tool 暴露？哪些应该作为 Resource？为什么？

（提示：考虑 LLM 和人类用户分别会如何使用每种接口类型。Tools 适合需要 LLM 决策和参数构造的场景，Resources 适合简单的数据暴露。）
