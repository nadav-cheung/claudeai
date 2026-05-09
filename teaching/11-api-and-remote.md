---
title: "API 通信与远程"
description: "理解 Claude Code 如何与 Anthropic API 通信、认证流程、远程会话机制，以及 Bridge 模式的工作原理。"
tags: [api, authentication, remote, bridge, websocket]
date: 2026-05-09
---

# 11 - API 通信与远程

> **本章目标**：理解 Claude Code 如何与 Anthropic API 通信、认证流程、远程会话机制，以及 Bridge 模式的工作原理。

---

## 通信架构总览

Claude Code 的通信分为多个层次：

```
Claude Code CLI
  │
  ├── Anthropic API (services/api/)         ← 核心：消息流式传输
  │     ├── claude.ts                       ← 消息 API 调用
  │     ├── client.ts                       ← SDK 客户端
  │     ├── bootstrap.ts                    ← 启动数据获取
  │     └── withRetry.ts                    ← 重试逻辑
  │
  ├── OAuth (services/oauth/)               ← 认证
  │     ├── client.ts                       ← OAuth 客户端
  │     └── types.ts                        ← 认证类型
  │
  ├── Remote Sessions (remote/)             ← 远程会话
  │     └── RemoteSessionManager.ts         ← 会话管理
  │
  ├── Bridge Mode (bridge/)                 ← IDE 集成
  │     ├── bridgeMain.ts                   ← 桥接主逻辑
  │     ├── replBridge.ts                   ← REPL 桥接
  │     └── bridgeMessaging.ts              ← 消息协议
  │
  ├── Direct Connect (server/)              ← 直连模式
  │     ├── createDirectConnectSession.ts   ← 会话创建
  │     └── directConnectManager.ts         ← 连接管理
  │
  └── SSH Sessions (hooks/useSSHSession.ts) ← SSH 远程
```

---

## Anthropic API 调用流程

### 核心文件：`src/services/api/claude.ts`

这是与 Anthropic API 交互的核心模块，负责构建请求并处理流式响应。

**调用流程**：

```
claude.ts → createMessageStream()
  │
  ├── 1. 准备消息
  │     ├── normalizeMessagesForAPI()  ← 标准化消息格式
  │     ├── 构建 system prompt
  │     └── 添加工具定义
  │
  ├── 2. 构建 API 参数
  │     ├── model: 当前模型
  │     ├── messages: 消息列表
  │     ├── tools: 工具 schema
  │     ├── system: 系统 prompt
  │     ├── stream: true (流式)
  │     ├── max_tokens: 模型最大输出
  │     └── betas: 功能标志
  │
  ├── 3. 发送请求
  │     └── Anthropic SDK → streaming response
  │
  └── 4. 处理流式事件
        ├── text 块 → 直接渲染
        ├── tool_use 块 → 工具执行循环
        └── usage 块 → 费用追踪
```

### 消息标准化

```typescript
normalizeMessagesForAPI(messages)
  │
  ├── 过滤系统消息（UI-only 消息不发送到 API）
  ├── 确保 tool_use / tool_result 配对
  ├── 处理图片和附件
  ├── 添加缓存断点（prompt cache）
  └── 返回 API 兼容的消息列表
```

### 工具 Schema 转换

```typescript
toolToAPISchema(tool)
  │
  ├── 将 Zod schema → JSON Schema
  ├── 添加 tool description (来自 tool.prompt())
  └── 返回 Anthropic API 格式的工具定义
```

### Prompt Cache 优化

Claude Code 对 prompt cache 做了大量优化：

```
System Prompt 分层
  ├── 前缀（缓存稳定部分）
  │     ├── 工具描述（按名称排序，保持稳定）
  │     └── 基础系统提示
  └── 后缀（动态部分）
        ├── 用户上下文
        └── CLAUDE.md 内容

缓存断点标记
  └── cache_control: { type: "ephemeral" }
```

---

## 认证系统

### 支持的认证方式

| 方式 | 配置 | 用途 |
|------|------|------|
| API Key | `ANTHROPIC_API_KEY` | 直连 API |
| OAuth | 浏览器授权流程 | Claude.ai 订阅用户 |
| Bedrock | `CLAUDE_CODE_USE_BEDROCK` | AWS 用户 |
| Vertex | `CLAUDE_CODE_USE_VERTEX` | GCP 用户 |

### OAuth 流程

文件：`src/services/oauth/client.ts`

```
OAuth 认证流程
  │
  ├── 1. 生成 PKCE 挑战
  │     ├── code_verifier (随机字符串)
  │     └── code_challenge (SHA256 哈希)
  │
  ├── 2. 打开浏览器授权页面
  │     └── buildAuthUrl() → 授权 URL
  │
  ├── 3. 本地 HTTP 服务器监听回调
  │     └── localhost:{port}/callback
  │
  ├── 4. 接收授权码
  │     └── code 参数
  │
  ├── 5. 交换 token
  │     ├── authorization_code → access_token
  │     └── refresh_token → 持久化
  │
  └── 6. Token 自动刷新
        └── checkAndRefreshOAuthTokenIfNeeded()
```

### API Key 管理

```
API Key 存储优先级
  ├── 环境变量 ANTHROPIC_API_KEY
  ├── Keychain (macOS) / Credential Manager (Windows)
  └── 配置文件
```

---

## 云服务提供商支持

### AWS Bedrock

```
配置
  ├── CLAUDE_CODE_USE_BEDROCK=1
  ├── AWS credentials (环境变量 / ~/.aws/)
  └── 可选：CLAUDE_CODE_USE_BEDROCK_REGION

API 调用
  └── Anthropic SDK 自动路由到 Bedrock endpoint
```

### Google Vertex AI

```
配置
  ├── CLAUDE_CODE_USE_VERTEX=1
  ├── GCP credentials (环境变量 / Application Default)
  └── CLAUDE_CODE_USE_VERTEX_PROJECT_ID

API 调用
  └── Anthropic SDK 自动路由到 Vertex endpoint
```

---

## 远程会话

### RemoteSessionManager

文件：`src/remote/RemoteSessionManager.ts`

远程会话允许用户将本地 CLI 连接到远程运行的 Claude Code 实例：

```
本地 CLI ─── SSH/网络 ─── 远程 Claude Code 实例
  │                            │
  │ ──发送用户输入──→           │
  │                            │ ──调用 API──→ Anthropic
  │                            │ ←──响应────
  │ ←──渲染输出──              │
```

### Teleport 功能

Teleport 允许将本地会话"传送"到远程机器：

```
Teleport 流程
  ├── 1. 验证 Git 状态（未提交更改）
  ├── 2. 上传会话数据到远程
  ├── 3. 在远程恢复会话
  ├── 4. 检出对应的 Git 分支
  └── 5. 继续 CLI 交互
```

---

## Bridge 模式

### 架构

Bridge 模式用于 IDE 集成（VS Code、JetBrains 等），让 IDE 作为前端，CLI 作为后端：

```
IDE (前端)
  │ WebSocket / stdin-stdout
  ▼
Bridge (bridge/)
  │
  ├── replBridge.ts         ← REPL 桥接
  ├── bridgeMessaging.ts    ← 消息协议
  ├── bridgePermissionCallbacks.ts ← 权限回调
  │
  ▼
Claude Code CLI (后端)
  │
  ▼
Anthropic API
```

### Bridge 消息协议

```
消息类型
  ├── user_message     ← 用户从 IDE 发送的消息
  ├── assistant_message ← Claude 的回复
  ├── tool_use         ← 工具调用事件
  ├── tool_result      ← 工具结果
  ├── permission_request ← 权限请求
  ├── permission_response ← 用户权限响应
  └── status_update    ← 状态更新
```

### Bridge 生命周期

```
bridgeMain.ts
  │
  ├── 初始化
  │     ├── bridgeConfig.ts → 读取配置
  │     ├── createSession.ts → 创建会话
  │     └── 初始化 REPL
  │
  ├── 运行
  │     ├── 接收 IDE 消息
  │     ├── 转发到 CLI
  │     ├── 接收 CLI 事件
  │     └── 转发到 IDE
  │
  └── 清理
        ├── sessionRunner.ts → 停止会话
        └── 清理资源
```

---

## Direct Connect

文件：`src/server/`

Direct Connect 允许通过 URL 直接连接到 Claude Code：

```
claude cc://session-id?auth=token
  │
  ▼
createDirectConnectSession.ts
  │
  ├── 1. 解析 cc:// URL
  │     └── parseConnectUrl() → session info
  │
  ├── 2. 验证认证
  │     └── authToken 验证
  │
  ├── 3. 创建连接
  │     └── DirectConnectManager
  │
  └── 4. 启动 REPL
        └── 连接到远程会话
```

---

## SSH 远程会话

文件：`src/hooks/useSSHSession.ts`, `src/ssh/`

SSH 模式允许通过 SSH 连接到远程机器上运行的 Claude Code：

```
本地 Claude Code CLI
  │ SSH 连接
  ▼
远程机器
  │ 自动部署/启动 Claude Code
  ▼
远程 Claude Code CLI
  │
  ▼
Anthropic API
```

SSH 会话支持：
- 自动在远程部署 CLI
- 权限模式同步
- 输入/输出转发
- 文件同步

---

## API 错误处理与重试

### 重试策略

文件：`src/services/api/withRetry.ts`

```
重试条件
  ├── 429 (Rate Limit) → 指数退避重试
  ├── 500 (Server Error) → 重试
  ├── 503 (Service Unavailable) → 重试
  └── 其他错误 → 不重试，抛出
```

### 错误类型

文件：`src/services/api/errors.ts`

| 错误 | 处理方式 |
|------|---------|
| AuthenticationError | 提示重新登录 |
| RateLimitError | 退避重试 |
| QuotaExceededError | 显示配额信息 |
| OverloadedError | 重试 |
| NetworkError | 重试 + 离线提示 |

### 速率限制

```
速率限制处理
  ├── 读取响应头 X-RateLimit-*
  ├── 计算 remaining / reset 时间
  ├── 显示速率限制状态
  └── 自动退避等待
```

---

## 数据流：完整请求链路

```
用户输入 "帮我修复 bug"
  │
  ▼
REPL.tsx → PromptInput
  │ createUserMessage()
  ▼
query.ts / QueryEngine.ts
  │ 构建完整请求
  ▼
claude.ts → createMessageStream()
  │
  ├── normalizeMessagesForAPI(messages)
  ├── buildSystemPrompt()
  ├── toolToAPISchema(tools)
  │
  ▼
Anthropic SDK
  │ POST /v1/messages (streaming)
  ▼
Anthropic API Server
  │
  ├── 返回 text 事件 → 渲染到终端
  ├── 返回 tool_use 事件 → 工具执行
  └── 返回 usage 事件 → 费用计算
```

---

## 关键代码

### API 调用核心流程

```typescript
// src/services/api/claude.ts:100
export async function* createMessageStream(params: CreateMessageParams) {
  // 1. 标准化消息
  const normalizedMessages = normalizeMessagesForAPI(params.messages)

  // 2. 构建 system prompt
  const system = buildSystemPrompt(params.systemPrompt, {
    includeTools: params.tools.length > 0,
    toolDefinitions: params.tools.map(toolToAPISchema),
  })

  // 3. 发送 API 请求
  const response = await anthropic.messages.create({
    model: params.model,
    messages: normalizedMessages,
    system,
    tools: params.tools.map(toolToAPISchema),
    stream: true,
    max_tokens: params.maxTokens ?? getMaxOutputTokensForModel(params.model),
  })

  // 4. 处理流式响应
  for await (const event of response) {
    yield parseStreamEvent(event)
  }
}
```

### 消息标准化

```typescript
// src/services/api/claude.ts:50
export function normalizeMessagesForAPI(messages: Message[]): NormalizedMessage[] {
  return messages
    .filter(isAPISendable)  // 过滤 UI-only 消息
    .map(normalizeMessage)
}

// 过滤掉的消息类型
function isAPISendable(message: Message): boolean {
  if (message.type === 'progress') return false
  if (message.type === 'context_collapse') return false
  if (isCompactBoundaryMessage(message)) return false
  return true
}
```

### 重试策略

```typescript
// src/services/api/withRetry.ts:30
export async function withRetry<T>(
  fn: () => Promise<T>,
  options: RetryOptions = {}
): Promise<T> {
  const { maxRetries = 3, initialDelayMs = 1000, backoffMultiplier = 2 } = options

  for (let attempt = 0; attempt <= maxRetries; attempt++) {
    try {
      return await fn()
    } catch (error) {
      if (attempt === maxRetries || !shouldRetry(error)) {
        throw error
      }
      const delay = initialDelayMs * Math.pow(backoffMultiplier, attempt)
      await sleep(delay)
    }
  }
  throw new Error('Should not reach here')
}
```

### OAuth 认证流程

```typescript
// src/services/oauth/client.ts:50
export async function authenticateWithOAuth(): Promise<OAuthTokens> {
  // 1. 生成 PKCE 参数
  const { codeVerifier, codeChallenge } = await generatePKCEChallenge()

  // 2. 启动本地回调服务器
  const callbackPort = await findAvailablePort(3100, 3200)

  // 3. 打开浏览器授权
  await openBrowser(buildAuthUrl({ codeChallenge, callbackPort }))

  // 4. 等待回调并交换 token
  const callback = await waitForOAuthCallback(callbackPort)
  return await exchangeCodeForToken(callback.code, codeVerifier)
}
```

### API 错误类型

```typescript
// src/services/api/errors.ts:30
export class APIError extends Error {
  constructor(
    message: string,
    public status: number,
    public code?: string
  ) {
    super(message)
    this.name = 'APIError'
  }
}

export class RateLimitError extends APIError {
  constructor(public retryAfterMs?: number) {
    super('Rate limit exceeded', 429, 'RATE_LIMIT')
  }
}

export class AuthenticationError extends APIError {
  constructor() {
    super('Authentication failed', 401, 'AUTH_ERROR')
  }
}

export class PromptTooLongError extends APIError {
  constructor(public maxTokens: number) {
    super('Prompt too long', 400, 'PROMPT_TOO_LONG')
  }
}
```

---

## 关键文件索引

| 文件 | 作用 |
|------|------|
| `src/services/api/claude.ts` | 核心 API 调用 |
| `src/services/api/client.ts` | SDK 客户端初始化 |
| `src/services/api/bootstrap.ts` | 启动数据获取 |
| `src/services/api/withRetry.ts` | 重试逻辑 |
| `src/services/api/errors.ts` | 错误定义 |
| `src/services/oauth/client.ts` | OAuth 客户端 |
| `src/remote/RemoteSessionManager.ts` | 远程会话管理 |
| `src/bridge/bridgeMain.ts` | Bridge 主逻辑 |
| `src/bridge/replBridge.ts` | REPL 桥接 |
| `src/bridge/bridgeMessaging.ts` | 消息协议 |
| `src/server/createDirectConnectSession.ts` | Direct Connect |
| `src/hooks/useSSHSession.ts` | SSH 会话 |
| `src/utils/auth.ts` | 认证工具 |

---

## 练习

1. **API 调用链**：从 `src/services/api/claude.ts` 入手，追踪一个完整的 API 请求是如何构建和发送的
2. **OAuth 流程**：阅读 `src/services/oauth/client.ts`，理解 PKCE 流程和 token 刷新机制
3. **Bridge 消息**：阅读 `src/bridge/bridgeMessaging.ts`，理解 IDE 和 CLI 之间的消息格式
4. **错误处理**：阅读 `src/services/api/withRetry.ts`，理解重试策略的实现
