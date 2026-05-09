---
title: "MCP 集成"
description: "深入理解 Claude Code 如何通过 MCP (Model Context Protocol) 协议连接外部工具服务器，涵盖客户端生命周期、连接类型、工具桥接、Elicitation 交互、OAuth 认证等。"
tags: [mcp, protocol, integration, tools]
date: 2026-05-09
---

# 07 - MCP 集成

> **本章目标**：深入理解 Claude Code 如何通过 MCP (Model Context Protocol) 协议连接外部工具服务器，涵盖客户端生命周期、连接类型（stdio、SSE、Streamable HTTP、WebSocket）、工具/资源/提示发现、MCP 工具桥接、Elicitation 交互、OAuth 认证、企业策略过滤和 Claude.ai 官方注册表。

---

## 目标

- 理解 MCP 协议在 Claude Code 架构中的位置和作用
- 掌握 MCP 客户端的连接、发现、执行、重连完整生命周期
- 了解不同传输类型（stdio / SSE / HTTP / WebSocket）的实现差异
- 理解 MCP 工具如何通过桥接层暴露给 Claude 模型
- 掌握 MCP 认证（OAuth、Claude.ai proxy）、企业策略（allowlist/denylist）机制
- 了解 Elicitation 机制——MCP 服务器如何主动请求用户输入

---

## 核心概念

### MCP 协议概览

MCP (Model Context Protocol) 是一个开放协议，允许 AI 应用通过标准化接口连接外部工具和数据源。Claude Code 作为 MCP 客户端，可以连接多个 MCP 服务器，每个服务器提供三类能力：

1. **Tools（工具）**：可调用的函数，如数据库查询、API 调用、文件操作
2. **Resource（资源）**：可读取的数据对象，如文件内容、数据库记录
3. **Prompts（提示模板）**：预定义的提示词模板

```
Claude Code (MCP Client)
  │
  ├── MCP Server A (stdio)     ← 本地进程通信
  │     ├── tools: query_db, insert_record
  │     └── resources: schema
  │
  ├── MCP Server B (SSE)       ← HTTP 长连接
  │     ├── tools: search_docs
  │     └── prompts: summarize
  │
  └── MCP Server C (HTTP)      ← Streamable HTTP
        └── tools: deploy_app
```

### 服务器连接类型

Claude Code 支持以下传输协议，定义在 `src/services/mcp/types.ts`：

| 类型 | 传输层 | 场景 | 配置键 |
|------|--------|------|--------|
| `stdio` | 标准输入/输出 | 本地进程（如 npx 包） | `command`, `args`, `env` |
| `sse` | Server-Sent Events | HTTP 长轮询 | `url`, `headers` |
| `sse-ide` | SSE (IDE 专用) | IDE 扩展集成 | `url`, `ideName` |
| `http` | Streamable HTTP | 现代 HTTP API | `url`, `headers` |
| `ws` | WebSocket | 双向实时通信 | `url`, `headers` |
| `ws-ide` | WebSocket (IDE) | IDE WebSocket 集成 | `url`, `authToken` |
| `sdk` | SDK 内部传输 | SDK 消费者嵌入 | `name` |
| `claudeai-proxy` | Claude.ai 代理 | 官方注册表服务器 | `url`, `id` |

### 服务器连接状态

```typescript
// src/services/mcp/types.ts
type MCPServerConnection =
  | ConnectedMCPServer    // 已连接：client 可用
  | FailedMCPServer       // 连接失败：携带 error 信息
  | NeedsAuthMCPServer    // 需要认证：需要 OAuth 流程
  | PendingMCPServer      // 等待中：正在重连
  | DisabledMCPServer     // 已禁用：用户手动关闭
```

---

## 源码导览

### MCP 服务架构总览

```
src/services/mcp/
├── client.ts              ← 核心客户端：连接、发现、执行
├── types.ts               ← 类型定义：配置 schema、连接状态
├── config.ts              ← 配置管理：加载、合并、策略过滤
├── auth.ts                ← OAuth 认证：流程、令牌管理
├── claudeai.ts            ← Claude.ai 注册表：拉取官方服务器
├── elicitationHandler.ts  ← Elicitation：服务器请求用户输入
├── mcpStringUtils.ts      ← 工具名构建：mcp__server__tool 格式
├── normalization.ts       ← 名称规范化
├── envExpansion.ts        ← 环境变量展开
├── headersHelper.ts       ← 动态 headers 辅助
├── SdkControlTransport.ts ← SDK 传输层
├── InProcessTransport.ts  ← 进程内传输（Chrome/Computer Use）
└── utils.ts               ← 工具函数

src/tools/MCPTool/
├── MCPTool.ts             ← MCP 工具桥接模板
├── prompt.ts              ← 工具 prompt
├── UI.tsx                 ← 渲染 UI
└── classifyForCollapse.ts ← 工具分类（折叠显示）

src/tools/ListMcpResourcesTool/  ← 列出 MCP 资源
src/tools/ReadMcpResourceTool/   ← 读取 MCP 资源

src/components/mcp/
├── index.ts               ← 组件导出
├── MCPListPanel.tsx       ← MCP 服务器列表面板
├── MCPSettings.tsx        ← MCP 设置面板
├── MCPToolListView.tsx    ← 工具列表视图
├── MCPToolDetailView.tsx  ← 工具详情视图
├── ElicitationDialog.tsx  ← Elicitation 对话框
├── MCPReconnect.tsx       ← 重连 UI
├── CapabilitiesSection.tsx ← 能力展示
├── MCPStdioServerMenu.tsx  ← stdio 服务器菜单
├── MCPRemoteServerMenu.tsx ← 远程服务器菜单
└── MCPAgentServerMenu.tsx  ← Agent 服务器菜单
```

### 配置加载流程

`src/services/mcp/config.ts` 中的 `getClaudeCodeMcpConfigs()` 是配置加载的核心入口：

```
启动时调用 getClaudeCodeMcpConfigs()
  │
  ├── 1. getMcpConfigsByScope('enterprise')
  │     └── 读取 managed-mcp.json（企业策略）
  │         └── 如果存在企业配置 → 排他模式，忽略其他配置
  │
  ├── 2. getMcpConfigsByScope('user')
  │     └── 读取 ~/.claude/settings.json 的 mcpServers
  │
  ├── 3. getMcpConfigsByScope('project')
  │     └── 从根目录到 CWD 遍历 .mcp.json
  │         └── 近 CWD 的配置覆盖父目录
  │         └── 仅包含已批准（approved）的项目服务器
  │
  ├── 4. getMcpConfigsByScope('local')
  │     └── 读取 .claude/settings.local.json
  │
  ├── 5. loadAllPluginsCacheOnly()
  │     └── 加载插件提供的 MCP 服务器
  │
  ├── 6. dedupPluginMcpServers()
  │     └── 基于 signature（command/url）去重
  │         └── 手动配置优先于插件
  │
  └── 7. isMcpServerAllowedByPolicy()
        └── 企业策略过滤（allowlist/denylist）
            └── 支持名称、命令、URL 三种匹配模式
```

### 服务器连接流程

`src/services/mcp/client.ts` 中的 `connectToServer()` 是连接的核心：

```typescript
// connectToServer 是 memoized 的，同一配置不会重复连接
export const connectToServer = memoize(
  async (name, serverRef, serverStats): Promise<MCPServerConnection> => {
    // 1. 根据 config.type 创建对应的 Transport
    switch (serverRef.type) {
      case 'sse':    // SSEClientTransport
      case 'http':   // StreamableHTTPClientTransport
      case 'ws':     // WebSocketTransport
      case 'stdio':  // StdioClientTransport
      case 'sse-ide': // SSEClientTransport (无 auth)
      case 'ws-ide':  // WebSocketTransport (IDE token)
      case 'claudeai-proxy': // StreamableHTTPClientTransport + OAuth
    }

    // 2. 创建 MCP Client 并连接
    const client = new Client({ name: 'claude-code', version: '...' })
    await client.connect(transport)

    // 3. 发现工具和资源
    const tools = await client.request({ method: 'tools/list' }, ...)
    const resources = await client.request({ method: 'resources/list' }, ...)

    // 4. 注册 Elicitation 处理器
    registerElicitationHandler(client, name, setAppState)

    // 5. 返回连接结果
    return { type: 'connected', client, name, capabilities, ... }
  }
)
```

**连接超时和批处理**：
- 本地服务器（stdio）批处理大小：3（`MCP_SERVER_CONNECTION_BATCH_SIZE`）
- 远程服务器批处理大小：20（`MCP_REMOTE_SERVER_CONNECTION_BATCH_SIZE`）
- 单个工具调用超时：~27.8 小时（`DEFAULT_MCP_TOOL_TIMEOUT_MS = 100_000_000`）
- 单个请求超时：60 秒（`MCP_REQUEST_TIMEOUT_MS = 60_000`）
- 连接超时：30 秒（`MCP_TIMEOUT` 环境变量，默认 30000ms）

---

## 数据流图

### MCP 工具调用完整流程

```
Claude 模型返回 tool_use: { name: "mcp__serverA__query", input: {...} }
  │
  ▼
工具执行引擎 (toolExecution.ts)
  │ 匹配工具名 "mcp__serverA__query" → MCPTool 实例
  ▼
MCPTool.call(input, context)
  │
  ├── 1. 从 mcpClients 中找到 serverA 的 ConnectedMCPServer
  │
  ├── 2. ensureConnectedClient(serverA)
  │     └── 如果连接断开 → 自动重连
  │
  ├── 3. 处理输入中的图片内容
  │     └── 识别 image MIME 类型 → 转换为 Base64ImageSource
  │
  ├── 4. client.request({ method: 'tools/call', params: { name, arguments } })
  │     └── 超时由 getMcpToolTimeoutMs() 控制
  │
  ├── 5. 处理返回结果
  │     ├── 文本内容 → 直接使用
  │     ├── 图片内容 → 缩小/下采样 → 返回给模型
  │     └── 二进制 blob → 持久化到磁盘 → 返回路径
  │
  ├── 6. 截断检查
  │     └── getContentSizeEstimate() → 超过限制则截断
  │
  └── 7. 返回 ToolResult
        └── mapToolResultToToolResultBlockParam() → tool_result 消息
```

### 配置优先级

```
优先级从低到高：
  Claude.ai 连接器 < 插件服务器 < 用户配置 < 项目配置(.mcp.json) < 本地配置 < 企业配置
                                                        ↑
                                              企业配置存在时，排他控制
```

---

## 关键代码

### MCPTool 桥接模板

`src/tools/MCPTool/MCPTool.ts` 是所有 MCP 工具的模板。它本身不执行任何操作——所有方法都在 `client.ts` 中被覆盖：

```typescript
// src/tools/MCPTool/MCPTool.ts
export const MCPTool = buildTool({
  isMcp: true,
  name: 'mcp',              // 被 client.ts 覆盖为 mcp__server__tool
  async description() { return DESCRIPTION },  // 被 client.ts 覆盖
  async call() { return { data: '' } },         // 被 client.ts 覆盖

  // 这些渲染方法不被覆盖，所有 MCP 工具共享
  renderToolUseMessage,
  renderToolUseProgressMessage,
  renderToolResultMessage,
})
```

在 `client.ts` 中，每个 MCP 工具被创建为 MCPTool 的变体：

```typescript
// client.ts 中的 createToolOverride()
function createToolOverride(serverName, toolDef) {
  return {
    ...MCPTool,
    name: buildMcpToolName(serverName, toolDef.name),
    //  "mcp__serverName__toolName" 格式
    async description() { return toolDef.description },
    async call(input, context) {
      // 实际调用 MCP 服务器的 tools/call
    },
  }
}
```

### 工具名规范化

MCP 工具名格式为 `mcp__<server>__<tool>`，在 `mcpStringUtils.ts` 中构建：

```typescript
// src/services/mcp/mcpStringUtils.ts
export function buildMcpToolName(serverName: string, toolName: string): string {
  const normalizedServer = normalizeNameForMCP(serverName)
  const normalizedTool = normalizeNameForMCP(toolName)
  return `mcp__${normalizedServer}__${normalizedTool}`
}
```

### 资源工具

`ListMcpResourcesTool` 和 `ReadMcpResourceTool` 是两个内置工具，允许模型发现和读取 MCP 服务器提供的资源：

```typescript
// src/tools/ListMcpResourcesTool/ListMcpResourcesTool.ts
// 输入：可选的 server 名称过滤
// 输出：资源列表 [{ uri, name, mimeType, description, server }]

// src/tools/ReadMcpResourceTool/ReadMcpResourceTool.ts
// 输入：server 名称 + resource URI
// 输出：资源内容（文本或持久化的二进制 blob 路径）
```

资源读取的一个关键细节：二进制内容（blob）不会被直接返回给模型，而是持久化到磁盘，返回文件路径：

```typescript
// ReadMcpResourceTool 中的 blob 处理
if ('blob' in c && typeof c.blob === 'string') {
  const persisted = await persistBinaryContent(
    Buffer.from(c.blob, 'base64'),
    c.mimeType,
    persistId,
  )
  return { uri, mimeType, blobSavedTo: persisted.filepath }
}
```

### Elicitation 机制

Elicitation 允许 MCP 服务器主动请求用户输入，这是 MCP 协议的一个重要交互模式：

```typescript
// src/services/mcp/elicitationHandler.ts
export type ElicitationRequestEvent = {
  serverName: string
  requestId: string | number
  params: ElicitRequestParams
  signal: AbortSignal
  respond: (response: ElicitResult) => void
  waitingState?: ElicitationWaitingState   // URL 模式的等待 UI
  onWaitingDismiss?: (action) => void       // 用户关闭等待 UI
}
```

支持两种模式：
- **form 模式**：服务器发送表单 schema，CLI 渲染为对话框
- **url 模式**：服务器发送 URL，CLI 在浏览器中打开，等待回调

### OAuth 认证流程

`src/services/mcp/auth.ts` 实现了完整的 OAuth 2.0 流程：

```
1. discoverAuthorizationServerMetadata(url)
   └── 获取 OAuth 服务器元数据

2. registerClient(metadata)
   └── 动态客户端注册（RFC 7591）

3. authorize(metadata, clientInfo)
   └── 启动本地 HTTP 服务器接收回调
   └── 打开浏览器进行用户授权

4. callback(code)
   └── 交换 authorization code 获取 tokens

5. saveTokens(tokens)
   └── 存储到安全存储（macOS Keychain / 文件）

6. refreshTokens(refreshToken)
   └── 使用 refresh_token 刷新访问令牌
```

**Claude.ai 代理认证**（`createClaudeAiProxyFetch`）：
- 使用 Claude.ai 的 OAuth token 进行认证
- 401 时自动重试一次（token 可能过期）
- 支持 token 刷新的锁竞争处理

### 企业策略过滤

`src/services/mcp/config.ts` 提供了多层策略控制：

```typescript
// denylist 优先于 allowlist
function isMcpServerAllowedByPolicy(name, config): boolean {
  // 1. 检查 denylist
  if (isMcpServerDenied(name, config)) return false

  // 2. 检查 allowlist
  const settings = getMcpAllowlistSettings()
  if (!settings.allowedMcpServers) return true  // 无限制

  // 3. 匹配模式：名称 / 命令数组 / URL 通配符
  // URL 支持 * 通配符，如 "https://*.example.com/*"
}
```

**去重机制**（`dedupPluginMcpServers` / `dedupClaudeAiMcpServers`）：
- 基于"签名"（signature）去重：stdio 命令数组 / URL
- 手动配置优先于插件，插件之间先加载优先
- CCR 代理 URL 会自动 unwrap 后比较

### Claude.ai 注册表

`src/services/mcp/claudeai.ts` 从 Claude.ai 平台拉取组织配置的 MCP 服务器：

```typescript
export const fetchClaudeAIMcpConfigsIfEligible = memoize(async () => {
  // 1. 检查 OAuth token 可用性
  // 2. 调用 Claude.ai API 获取 MCP 服务器列表
  // 3. 转换为 McpClaudeAIProxyServerConfig（type: 'claudeai-proxy'）
  // 4. 通过代理 URL 路由请求
})
```

---

## 练习

### 练习 1：连接类型对比

**类比 Java**：这类似于 JDBC 的驱动类型——不同数据库有不同驱动，MCP 的传输类型类似于此。

**答案**：

| 传输类型 | 创建方式 | 特点 |
|---------|---------|------|
| stdio | `StdioClientTransport` | 子进程，本地通信 |
| sse | `SSEClientTransport` | HTTP 长连接，服务器推送 |
| http | `StreamableHTTPClientTransport` | 现代 HTTP，支持流式 |
| ws | `WebSocketTransport` | 双向实时通信 |

### 练习 2：配置优先级

**答案**：

| 优先级 | 来源 | 说明 |
|--------|------|------|
| 1（最低） | claudeai | Claude.ai 注册表 |
| 2 | 插件 | 插件提供的服务器 |
| 3 | 用户 | ~/.claude/settings.json |
| 4 | 项目 | .mcp.json |
| 5 | 本地 | settings.local.json |
| 6（最高） | 企业 | managed-mcp.json（排他） |

**企业排他**：存在企业配置时，忽略其他配置，确保企业安全策略不被绕过。

**项目 approved**：项目服务器需要显式批准才能使用，防止恶意 .mcp.json 注入。

### 练习 3：工具桥接

**答案**：

**为什么需要规范化？**
- MCP 服务器名称可能包含特殊字符（空格、连字符等）
- 工具名需要符合 Claude Code 的命名规范
- 避免命名冲突

**normalizeNameForMCP()**：
- 替换特殊字符为下划线
- 确保跨服务器工具名唯一

### 练习 4：Elicitation 模式

**答案**：

| 模式 | 流程 | 类比 |
|------|------|------|
| form | 服务器发送 schema → CLI 渲染对话框 → 用户填写 → 提交 | 表单提交 |
| url | 服务器发送 URL → CLI 打开浏览器 → 用户授权 → 回调 | OAuth 授权码流程 |

**completed 通知**：用户提交表单或授权完成后，`respond()` 被调用，解除工具执行等待状态。

### 练习 5：认证重试

**答案**：

**为什么捕获 `sentToken`？**

并发 401 场景：
```
时刻T1: 请求A 发送 token X，收到 401
时刻T2: 请求B 发送 token Y，收到 401
时刻T3: 刷新 token X → token Z
时刻T4: 重试请求A，使用 token Z
```

如果在重试时重新读取 token，可能读到新的 token（如 token Z），而不是请求 A 原来发送的 token X，导致重试失败。

**解决方案**：捕获 `sentToken`，重试时使用相同 token。

---

## MCP vs JDBC

| 方面 | MCP | JDBC |
|------|------|------|
| 协议 | JSON-RPC over stdio/HTTP/WS | SQL over TCP |
| 发现 | `tools/list` 动态发现 | `DatabaseMetaData` |
| 调用 | `tools/call` | `Statement.execute()` |
| 资源 | `resources/list` | `ResultSet` |
| 认证 | OAuth 2.0 | 数据库用户名/密码 |
| 驱动 | MCP SDK | JDBC Driver |

---

## 练习答案速查

| 练习 | 核心答案 |
|------|---------|
| 1 | stdio=进程，sse=HTTP长连接，http=流式HTTP，ws=双向 |
| 2 | 企业排他，项目需approved |
| 3 | 规范化避免冲突，确保命名合规 |
| 4 | form=对话框，url=浏览器授权 |
| 5 | 捕获sentToken避免并发竞态 |

---

## 下一篇

[第08章-Agent与多Agent协作.md](./第08章-Agent与多Agent协作.md) — Agent 与多 Agent 协作
