---
title: "A07 - MCP 集成代码详解"
description: "深入解析 Claude Code MCP (Model Context Protocol) 集成系统的核心代码，包括 MCP 客户端生命周期、连接管理、工具桥接等。"
tags: [code, mcp, protocol, integration]
date: 2026-05-09
---

# A07 - MCP 集成代码详解

> **本文档目标**：深入解析 Claude Code MCP (Model Context Protocol) 集成系统的核心代码，包括 MCP 客户端生命周期、连接管理、工具桥接等。

---

## 1. MCP 连接类型

**文件**：`src/services/mcp/types.ts:30-80`

**功能**：定义支持的 MCP 传输协议类型。

```typescript
// src/services/mcp/types.ts:30
export type TransportType =
  | 'stdio'      // 标准输入/输出（本地进程）
  | 'sse'        // Server-Sent Events
  | 'sse-ide'    // SSE (IDE 专用)
  | 'http'       // Streamable HTTP
  | 'ws'         // WebSocket
  | 'ws-ide'     // WebSocket (IDE)
  | 'local-grpc' // 本地 gRPC

export interface MCPConnectionConfig {
  transport: TransportType
  // stdio 配置
  command?: string           // 可执行命令
  args?: string[]            // 命令参数
  env?: Record<string, string>
  // HTTP/SSE/WS 配置
  url?: string
  headers?: Record<string, string>
  authToken?: string
  // 通用配置
  timeout?: number
  retryCount?: number
}
```

### 1.1 传输类型对比

| 类型 | 适用场景 | 延迟 | 复杂度 |
|------|---------|------|-------|
| `stdio` | 本地 npx 包 | 低 | 低 |
| `sse` | HTTP 长连接 | 中 | 中 |
| `http` | 现代 REST API | 中 | 低 |
| `ws` | 双向实时 | 低 | 高 |

---

## 2. MCP 客户端连接管理

**文件**：`src/services/mcp/mcpCore.ts:50-200`

**功能**：管理 MCP 服务器的生命周期。

### 2.1 连接初始化

```typescript
// src/services/mcp/mcpCore.ts:50
export async function connectToMCPServer(
  config: MCPConnectionConfig
): Promise<MCPServerConnection> {
  const { transport, ...options } = config

  // 创建传输层
  const transportImpl = createTransport(transport, options)

  // 创建 MCP 客户端
  const client = new MCPClient({
    transport: transportImpl,
    onMessage: handleServerMessage,
    onError: handleServerError,
  })

  // 初始化连接
  await client.initialize()

  // 发现服务器能力
  const capabilities = await client.sendRequest('initialize', {
    protocolVersion: '2024-11-05',
    capabilities: {
      tools: {},
      resources: {},
      prompts: {},
    },
    clientInfo: {
      name: 'claude-code',
      version: '2.1.88',
    },
  })

  return {
    id: generateConnectionId(),
    config,
    client,
    capabilities,
    status: 'connected',
    connectedAt: Date.now(),
  }
}
```

### 2.2 工具发现

```typescript
// src/services/mcp/mcpCore.ts:150
export async function discoverMCPTools(
  connection: MCPServerConnection
): Promise<Tool[]> {
  // 发送工具列表请求
  const toolList = await connection.client.sendRequest(
    'tools/list',
    {}
  )

  // 转换为 Claude Code 工具格式
  return toolList.tools.map(tool => ({
    name: `mcp__${connection.id}__${tool.name}`,
    description: tool.description,
    inputSchema: tool.inputSchema,
    isMcp: true,
    mcpInfo: {
      serverName: connection.config.name,
      toolName: tool.name,
    },
    // 包装为 MCP 工具调用
    call: async (args, context) => {
      const result = await connection.client.sendRequest(
        'tools/call',
        {
          name: tool.name,
          arguments: args,
        }
      )
      return {
        success: true,
        data: result.content,
      }
    },
  }))
}
```

---

## 3. MCP 工具桥接

**文件**：`src/tools/MCPTool/MCPTool.ts:50-150`

**功能**：将 MCP 工具桥接为 Claude Code 内部工具。

```typescript
// src/tools/MCPTool/MCPTool.ts:50
export class MCPTool implements Tool {
  readonly name: string
  readonly inputSchema: AnyObject
  isMcp = true

  constructor(
    private serverName: string,
    private toolName: string,
    private mcpClient: MCPServerConnection
  ) {
    this.name = `mcp__${serverName}__${toolName}`
  }

  async call(args, context, canUseTool) {
    // 1. 权限检查
    const permission = await canUseTool(this, args, context)
    if (permission.behavior === 'deny') {
      return { success: false, error: permission.message }
    }

    // 2. 发送 MCP 请求
    const result = await this.mcpClient.sendRequest('tools/call', {
      name: this.toolName,
      arguments: args,
    })

    // 3. 处理结果
    return {
      success: true,
      data: formatMCPToolResult(result),
    }
  }

  async prompt() {
    return `${this.toolName}: MCP tool from ${this.serverName}`
  }
}
```

---

## 4. Elicitation 机制

**文件**：`src/services/mcp/elicitation.ts:50-120`

**功能**：MCP 服务器主动请求用户输入。

```typescript
// src/services/mcp/elicitation.ts:50
export interface ElicitationRequest {
  message: string
  requestedSchema: {
    type: 'string' | 'number' | 'boolean' | 'object'
    properties?: Record<string, any>
    required?: string[]
  }
}

// 处理 elicitation 请求
export async function handleElicitationRequest(
  request: ElicitationRequest,
  context: ToolUseContext
): Promise<any> {
  // 1. 显示交互式对话框
  const response = await context.showElicitationDialog({
    title: 'MCP Request',
    message: request.message,
    schema: request.requestedSchema,
  })

  // 2. 返回用户输入
  return response
}
```

---

## 5. MCP OAuth 认证

**文件**：`src/services/mcp/oauth.ts:50-100`

```typescript
// src/services/mcp/oauth.ts:50
export async function performMCP OAuthFlow(
  serverConfig: MCPConnectionConfig
): Promise<void> {
  // 1. 获取 OAuth 配置
  const oauthConfig = await fetchOAuthConfig(serverConfig.url)

  // 2. 生成 PKCE 挑战
  const { codeVerifier, codeChallenge } = generatePKCEChallenge()

  // 3. 重定向到授权页面
  const authUrl = buildOAuthAuthUrl({
    url: oauthConfig.authorizationUrl,
    clientId: oauthConfig.clientId,
    redirectUri: oauthConfig.redirectUri,
    codeChallenge,
    scope: oauthConfig.scope,
  })

  // 4. 交换 token
  const tokenResponse = await exchangeCodeForToken({
    url: oauthConfig.tokenUrl,
    code: receivedCode,
    codeVerifier,
    clientId: oauthConfig.clientId,
  })

  // 5. 存储 token
  await storeOAuthToken(serverConfig.name, tokenResponse)
}
```

---

---

## 练习

### 练习 1：MCP 协议与工具调用的区别

**问题**：MCP 工具调用和内置工具调用有什么不同？

**答案**：

| 方面 | 内置工具 | MCP 工具 |
|------|---------|---------|
| 实现位置 | Claude Code 内 | 外部进程 |
| 调用方式 | 直接调用 | JSON-RPC over Stdio/HTTP |
| 工具发现 | 编译时确定 | 运行时 discover |
| 生命周期 | 随进程存在 | 可独立管理 |
| 通信协议 | 函数调用 | MCP JSON-RPC |

**MCP 调用流程**：
```
Claude Code → MCPTool.call() → JSON-RPC Request
                                         ↓
                              MCP Server (外部进程)
                                         ↓
                              JSON-RPC Response
                                         ↓
                              MCPTool 返回 ToolResult
```

**Java 对比**：类似于 RMI 或 WebService 调用，但使用标准化的 JSON-RPC 协议。

---

### 练习 2：Stdio vs HTTP 传输

**问题**：MCP 的 StdioTransport 和 HttpTransport 分别适用什么场景？

**答案**：

| 传输方式 | 适用场景 | 优点 | 缺点 |
|---------|---------|------|------|
| **Stdio** | 本地进程 | 低延迟，简单 | 需要进程管理 |
| **HTTP** | 远程服务 | 可网络访问 | 延迟较高 |

**Stdio 传输模型**：
```
Claude Code              MCP Server
     │                       │
     │  ←── stdin ──────────  │
     │  ─── stdout ────────→  │
     │  ─── stderr ────────→  │
```

**HTTP 传输模型**：
```
Claude Code              MCP Server
     │                       │
     │  ──── HTTP POST ────→  │
     │  ←─── HTTP Response ──  │
```

---

### 练习 3：工具发现机制

**问题**：Claude Code 如何发现 MCP 服务器提供的工具？

**答案**：

```typescript
// 连接时自动发现
async function discoverMCPTools(client: MCPClient) {
  // 1. 发送 list_tools 请求
  const response = await client.sendRequest({
    method: 'tools/list',
    params: {}
  })

  // 2. 解析返回的工具列表
  const tools = response.tools.map(mcpTool => ({
    name: mcpTool.name,
    description: mcpTool.description,
    inputSchema: mcpTool.inputSchema,
  }))

  // 3. 转换为 MCPTool 实例
  return tools.map(tool => new MCPTool(tool))
}
```

**发现时机**：
1. MCP 服务器连接时（`initialize` 阶段）
2. 服务器主动通知（`notifications/tools/list_changed`）

---

### 练习 4：Elicitation 请求

**问题**：什么是 Elicitation？为什么需要它？

**答案**：

**Elicitation**：MCP 服务器主动请求用户输入的机制

**使用场景**：
```typescript
// MCP 服务器需要用户选择或输入
interface ElicitationRequest {
  message: "请选择文件编码"
  requestedSchema: {
    type: "string"
    enum: ["UTF-8", "GBK", "ISO-8859-1"]
  }
}
```

**处理流程**：
```
MCP Server → elicitation request
    ↓
Claude Code 显示对话框
    ↓
用户选择/输入
    ↓
返回响应给 MCP Server
```

**Java 对比**：类似于 Swing 的 `JOptionPane.showInputDialog()`。

---

### 练习 5：MCP OAuth 流程

**问题**：MCP OAuth 认证使用 PKCE 的原因是什么？

**答案**：

**PKCE (Proof Key for Code Exchange)** 作用：

1. **防止授权码拦截**：公共客户端无法保存 client_secret
2. **代码交换验证**：通过 code_verifier 确保是同一客户端

```typescript
// PKCE 流程
const { codeVerifier, codeChallenge } = generatePKCEChallenge()

// 1. 授权请求包含 code_challenge
GET /authorize?code_challenge=xxx&code_challenge_method=S256

// 2. 交换 token 时提供 code_verifier
POST /token
{
  code: "xxx",
  code_verifier: "yyy"  // 服务器验证 S256(code_verifier) === code_challenge
}
```

**Java 对比**：类似于 OAuth 2.0 的 Authorization Code Flow with PKCE。

---

## 练习答案速查

| 练习 | 核心答案 |
|------|---------|
| 1 | MCP=外部进程+JSON-RPC，内置=直接调用 |
| 2 | Stdio=本地低延迟，HTTP=远程访问 |
| 3 | 连接时发送 list_tools 请求，自动发现 |
| 4 | 服务器请求用户输入，显示对话框 |
| 5 | PKCE 防止授权码拦截，验证客户端身份 |

---

## 附录：MCP 协议消息类型

| 消息类型 | 方向 | 说明 |
|---------|------|------|
| `initialize` | C→S | 初始化连接 |
| `initialized` | S→C | 初始化完成 |
| `tools/list` | C→S | 查询工具列表 |
| `tools/call` | C→S | 调用工具 |
| `tools/list_changed` | S→C | 工具列表变更 |
| `elicitation` | S→C | 请求用户输入 |

---

## 7. 关键源码文件索引

| 文件 | 关键函数/类 | 说明 |
|------|-----------|------|
| `src/services/mcp/types.ts` | `MCPConnectionConfig` | 连接配置类型 |
| `src/services/mcp/mcpCore.ts` | `connectToMCPServer()` | 连接初始化 |
| `src/services/mcp/mcpCore.ts` | `discoverMCPTools()` | 工具发现 |
| `src/services/mcp/transport/` | `createTransport()` | 传输层工厂 |
| `src/services/mcp/transport/stdio.ts` | `StdioTransport` | stdio 传输 |
| `src/services/mcp/transport/http.ts` | `HttpTransport` | HTTP 传输 |
| `src/tools/MCPTool/MCPTool.ts` | `MCPTool` | MCP 工具桥接类 |
| `src/services/mcp/elicitation.ts` | `handleElicitationRequest()` | Elicitation 处理 |
| `src/services/mcp/oauth.ts` | `performMCP OAuthFlow()` | OAuth 认证 |
| `src/services/mcp/policyFilter.ts` | `filterByPolicy()` | 企业策略过滤 |

---

## 附录导航

👈 [A06-压缩系统代码.md](./A06-压缩系统代码.md) | [A08-Agent代码.md](./A08-Agent代码.md) 👉
