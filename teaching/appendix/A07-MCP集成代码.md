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

## 6. 关键源码文件索引

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
