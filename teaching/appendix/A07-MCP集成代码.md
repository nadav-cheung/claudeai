---
title: "A07 - MCP 集成代码详解"
description: "深入解析 Claude Code MCP (Model Context Protocol) 集成系统的核心代码，包括 MCP 客户端生命周期、连接管理、工具桥接等。"
tags: [code, mcp, protocol, integration]
date: 2026-05-10
---

# A07 - MCP 集成代码详解

> **本文档目标**：深入解析 Claude Code MCP (Model Context Protocol) 集成系统的核心代码，包括 MCP 客户端生命周期、连接管理、工具桥接等。

> **⚠️ 重要说明**：本文档基于实际源码编写，与旧版文档有重大差异。主要变化：
> - 连接管理从 `mcpCore.ts` 移至 `client.ts`
> - 工具发现函数为 `fetchToolsForClient()` 而非 `discoverMCPTools()`
> - MCPTool 使用 `buildTool()` 工厂模式而非类继承

---

## 1. MCP 连接类型

**文件**：`src/services/mcp/types.ts`

**功能**：定义支持的 MCP 连接类型和传输协议。

```typescript
// src/services/mcp/types.ts
export type MCPServerConnection =
  | ConnectedMCPServer    // 已连接：client 可用
  | FailedMCPServer       // 连接失败：携带 error 信息
  | NeedsAuthMCPServer    // 需要认证：需要 OAuth 流程
  | PendingMCPServer      // 等待中：正在重连
  | DisabledMCPServer     // 已禁用：用户手动关闭
```

---

## 2. MCP 客户端连接管理

**文件**：`src/services/mcp/client.ts`

**功能**：管理 MCP 服务器的生命周期。

### 2.1 连接初始化 (client.ts:595)

```typescript
// src/services/mcp/client.ts:595
export const connectToServer = memoize(
  async (
    name: string,
    serverRef: ScopedMcpServerConfig,
    serverStats?: { totalServers: number; stdioCount: number; sseCount: number }
  ): Promise<MCPServerConnection> => {
    try {
      let transport

      // 根据 serverRef.type 选择传输类型
      if (serverRef.type === 'sse') {
        // SSE (Server-Sent Events) 传输
        const authProvider = new ClaudeAuthProvider(name, serverRef)
        transport = new SSEClientTransport(
          new URL(serverRef.url),
          transportOptions,
        )
      } else if (serverRef.type === 'sse-ide') {
        // IDE 专用 SSE 传输
        transport = new SSEClientTransport(
          new URL(serverRef.url),
          transportOptions,
        )
      } else if (serverRef.type === 'stdio') {
        // Stdio 传输（本地进程）
        transport = new StdioClientTransport({
          command: serverRef.command,
          args: serverRef.args,
          env: serverRef.env,
        })
      }

      // 创建 MCP 客户端
      const client = new MCPClient({
        transport,
        onMessage: handleServerMessage,
        onError: handleServerError,
      })

      // 初始化连接
      await client.initialize()

      // 发现服务器能力
      const capabilities = await client.sendRequest('initialize', {
        protocolVersion: '2024-11-05',
        capabilities: { tools: {}, resources: {}, prompts: {} },
        clientInfo: { name: 'claude-code', version: '2.1.88' },
      })

      return {
        id: generateConnectionId(),
        config: serverRef,
        client,
        capabilities,
        status: 'connected',
        connectedAt: Date.now(),
      }
    } catch (error) {
      return { type: 'failed', error, config: serverRef }
    }
  }
)
```

### 2.2 工具发现 (client.ts:1743)

```typescript
// src/services/mcp/client.ts:1743
export const fetchToolsForClient = memoizeWithLRU(
  async (client: MCPServerConnection): Promise<Tool[]> => {
    if (client.type !== 'connected') return []

    if (!client.capabilities?.tools) {
      return []
    }

    // 发送工具列表请求
    const result = (await client.client.request(
      { method: 'tools/list' },
      ListToolsResultSchema,
    )) as ListToolsResult

    // 转换 MCP 工具为 Claude Code 工具格式
    return result.tools.map((tool): Tool => {
      const fullyQualifiedName = buildMcpToolName(client.name, tool.name)
      return {
        ...MCPTool,
        name: fullyQualifiedName,
        mcpInfo: { serverName: client.name, toolName: tool.name },
        isMcp: true,
        async description() {
          return tool.description ?? ''
        },
        async checkPermissions() {
          return {
            behavior: 'passthrough',
            message: 'MCPTool requires permission.',
          }
        },
        // ... 其他覆盖属性
      }
    })
  }
)
```

---

## 3. MCPTool 工具桥接

**文件**：`src/tools/MCPTool/MCPTool.ts`

**功能**：将 MCP 工具桥接为 Claude Code 内部工具。

### 3.1 MCPTool 模板 (MCPTool.ts:27)

```typescript
// src/tools/MCPTool/MCPTool.ts:27
export const MCPTool = buildTool({
  isMcp: true,
  name: 'mcp',  // 会被 fetchToolsForClient 覆盖
  maxResultSizeChars: 100_000,

  async description() {
    return DESCRIPTION  // 来自 prompt.ts
  },

  async call() {
    // 实际实现在 client.ts 中被覆盖
    return { data: '' }
  },

  async checkPermissions(): Promise<PermissionResult> {
    return {
      behavior: 'passthrough',
      message: 'MCPTool requires permission.',
    }
  },

  renderToolUseMessage,      // UI.tsx
  renderToolResultMessage,    // UI.tsx
})
```

### 3.2 工具名称构建 (client.ts:1730)

```typescript
// src/services/mcp/client.ts:1730
function buildMcpToolName(
  serverName: string,
  toolName: string
): string {
  return `mcp__${serverName}__${toolName}`
}
```

---

## 4. Elicitation 机制

**文件**：`src/services/mcp/elicitationHandler.ts`

**功能**：MCP 服务器主动请求用户输入。

```typescript
// src/services/mcp/elicitationHandler.ts
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

**文件**：`src/services/mcp/auth.ts`

```typescript
// src/services/mcp/auth.ts
// ClaudeAuthProvider 实现 OAuth 2.0 + PKCE 流程
export class ClaudeAuthProvider {
  async tokens(): Promise<TokenResponse | null> {
    // 获取存储的 OAuth token
  }

  async refreshToken(): Promise<void> {
    // 刷新过期的 token
  }
}
```

---

## 6. 传输层实现

**文件**：`src/services/mcp/InProcessTransport.ts`

```typescript
// src/services/mcp/InProcessTransport.ts:57
export function createLinkedTransportPair(): [Transport, Transport] {
  // 创建一对 linked transports，用于进程内通信
}
```

---

## 练习

### 练习 1：MCP 工具调用流程

**问题**：描述 MCP 工具从发现到调用的完整流程。

**答案**：

```text
连接 MCP 服务器 → fetchToolsForClient() → 获取工具列表
    ↓
构建 MCPTool 实例（name, description, call 被覆盖）
    ↓
模型发出 tool_use { name: "mcp__server__tool" }
    ↓
runToolUse() → 找到 MCPTool → 调用覆盖的 call()
    ↓
通过 MCP JSON-RPC 发送请求到外部服务器
    ↓
返回结果
```

---

### 练习 2：连接类型选择

**问题**：Claude Code 如何根据 serverRef.type 选择传输类型？

**答案**：

| type | 传输类 | 适用场景 |
|------|--------|---------|
| `sse` | SSEClientTransport | 远程 MCP 服务器 |
| `sse-ide` | SSEClientTransport | IDE 插件 |
| `stdio` | StdioClientTransport | 本地 npx 包 |

---

### 练习 3：工具名称解析

**问题**：`mcp__serverName__toolName` 格式的作用是什么？

**答案**：
1. 区分不同 MCP 服务器的同名工具
2. 在权限检查时通过 `mcpInfo` 识别服务器来源
3. 支持 MCP 工具覆盖内置工具（skip-prefix 模式）

---

## 练习答案速查

| 练习 | 核心答案 |
|------|---------|
| 练习 1 | 连接 → fetchToolsForClient → 构建 MCPTool → tool_use → JSON-RPC |
| 练习 2 | 根据 serverRef.type 选择 SSE/Stdio 传输 |
| 练习 3 | 区分服务器来源，支持工具覆盖 |

---

## 关键源码文件索引

| 文件 | 关键函数 | 说明 |
|------|---------|------|
| `src/services/mcp/client.ts` | `connectToServer()` | 连接初始化 |
| `src/services/mcp/client.ts` | `fetchToolsForClient()` | 工具发现 |
| `src/services/mcp/client.ts` | `getMcpToolsCommandsAndResources()` | 获取工具和资源 |
| `src/tools/MCPTool/MCPTool.ts` | `MCPTool` 模板 | 工具桥接模板 |
| `src/services/mcp/elicitationHandler.ts` | `handleElicitationRequest()` | Elicitation 处理 |
| `src/services/mcp/auth.ts` | `ClaudeAuthProvider` | OAuth 认证 |

---

## 附录导航

👈 [A06-压缩系统代码.md](./A06-压缩系统代码.md) | [A08-Agent代码.md](./A08-Agent代码.md) 👉
