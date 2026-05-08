# 11 - API 通信与远程

> **本章目标**：理解 Claude Code 如何与 Anthropic API 通信、认证流程、远程会话机制，以及 Bridge 模式的工作原理。

---

## 1. 通信架构总览

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

## 2. Anthropic API 调用流程

### 2.1 核心文件：`src/services/api/claude.ts`

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

### 2.2 消息标准化

```typescript
normalizeMessagesForAPI(messages)
  │
  ├── 过滤系统消息（UI-only 消息不发送到 API）
  ├── 确保 tool_use / tool_result 配对
  ├── 处理图片和附件
  ├── 添加缓存断点（prompt cache）
  └── 返回 API 兼容的消息列表
```

### 2.3 工具 Schema 转换

```typescript
toolToAPISchema(tool)
  │
  ├── 将 Zod schema → JSON Schema
  ├── 添加 tool description (来自 tool.prompt())
  └── 返回 Anthropic API 格式的工具定义
```

### 2.4 Prompt Cache 优化

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

## 3. 认证系统

### 3.1 支持的认证方式

| 方式 | 配置 | 用途 |
|------|------|------|
| API Key | `ANTHROPIC_API_KEY` | 直连 API |
| OAuth | 浏览器授权流程 | Claude.ai 订阅用户 |
| Bedrock | `CLAUDE_CODE_USE_BEDROCK` | AWS 用户 |
| Vertex | `CLAUDE_CODE_USE_VERTEX` | GCP 用户 |

### 3.2 OAuth 流程

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

### 3.3 API Key 管理

```
API Key 存储优先级
  ├── 环境变量 ANTHROPIC_API_KEY
  ├── Keychain (macOS) / Credential Manager (Windows)
  └── 配置文件
```

---

## 4. 云服务提供商支持

### 4.1 AWS Bedrock

```
配置
  ├── CLAUDE_CODE_USE_BEDROCK=1
  ├── AWS credentials (环境变量 / ~/.aws/)
  └── 可选：CLAUDE_CODE_USE_BEDROCK_REGION

API 调用
  └── Anthropic SDK 自动路由到 Bedrock endpoint
```

### 4.2 Google Vertex AI

```
配置
  ├── CLAUDE_CODE_USE_VERTEX=1
  ├── GCP credentials (环境变量 / Application Default)
  └── CLAUDE_CODE_USE_VERTEX_PROJECT_ID

API 调用
  └── Anthropic SDK 自动路由到 Vertex endpoint
```

---

## 5. 远程会话

### 5.1 RemoteSessionManager

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

### 5.2 Teleport 功能

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

## 6. Bridge 模式

### 6.1 架构

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

### 6.2 Bridge 消息协议

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

### 6.3 Bridge 生命周期

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

## 7. Direct Connect

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

## 8. SSH 远程会话

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

## 9. API 错误处理与重试

### 9.1 重试策略

文件：`src/services/api/withRetry.ts`

```
重试条件
  ├── 429 (Rate Limit) → 指数退避重试
  ├── 500 (Server Error) → 重试
  ├── 503 (Service Unavailable) → 重试
  └── 其他错误 → 不重试，抛出
```

### 9.2 错误类型

文件：`src/services/api/errors.ts`

| 错误 | 处理方式 |
|------|---------|
| AuthenticationError | 提示重新登录 |
| RateLimitError | 退避重试 |
| QuotaExceededError | 显示配额信息 |
| OverloadedError | 重试 |
| NetworkError | 重试 + 离线提示 |

### 9.3 速率限制

```
速率限制处理
  ├── 读取响应头 X-RateLimit-*
  ├── 计算 remaining / reset 时间
  ├── 显示速率限制状态
  └── 自动退避等待
```

---

## 10. 数据流：完整请求链路

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

## 11. 关键代码

### 11.1 API 调用核心流程

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

### 11.2 消息标准化

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

### 11.3 重试策略

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

### 11.4 OAuth 认证流程

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

### 11.5 API 错误类型

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

## 12. 关键文件索引

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

### 练习 1：API 调用链

**类比 Java**：这类似于 Spring 的 `RestTemplate` 或 `WebClient` 发送 HTTP 请求。

**答案**：

完整 API 调用链路：
```
用户输入 → REPL.tsx → createUserMessage()
  → query.ts → createMessageStream()
  → normalizeMessagesForAPI() → buildSystemPrompt()
  → toolToAPISchema() → Anthropic SDK
  → POST /v1/messages (streaming)
  → 流式响应 → text/tool_use/usage 事件
```

**Java 对比**：
```java
// Spring RestTemplate
restTemplate.postForEntity(url, request, Response.class);
// WebClient (reactive)
webClient.post()
    .bodyValue(request)
    .retrieve()
    .bodyToFlux(Response.class);
```

### 练习 2：OAuth 流程

**答案**：

OAuth PKCE 流程：

| 步骤 | Claude Code | Java Spring |
|------|-----------|-------------|
| 1. 生成 verifier | `code_verifier = randomString()` | `@Bean` generated |
| 2. 生成 challenge | `SHA256(verifier)` | `Spring Security OAuth2` |
| 3. 授权 URL | `buildAuthUrl()` | `AuthorizationRequest` |
| 4. 回调接收 | `localhost:port/callback` | `@GetMapping("/callback")` |
| 5. Token 交换 | `exchangeCodeForToken()` | `AuthorizationCodeTokenResponseClient` |
| 6. Token 刷新 | `checkAndRefreshOAuthTokenIfNeeded()` | `OAuth2AuthorizedClientService` |

### 练习 3：Bridge 消息

**答案**：

Bridge 消息类型：

| 消息类型 | 方向 | Java 类比 |
|---------|------|----------|
| `user_message` | IDE → CLI | HTTP Request |
| `assistant_message` | CLI → IDE | HTTP Response |
| `tool_use` | CLI → IDE | Controller event |
| `tool_result` | IDE → CLI | Service result callback |
| `permission_request` | CLI → IDE | `@PreAuthorize` 拦截 |
| `permission_response` | IDE → CLI | Security context |

### 练习 4：错误处理

**答案**：

重试策略对比：

| 错误类型 | Claude Code | Java Resilience4j |
|---------|------------|-------------------|
| 429 Rate Limit | 指数退避重试 | `@Retryable(maxAttempts)` |
| 500 Server Error | 重试 | `@Retryable` |
| 503 Unavailable | 重试 | `@CircuitBreaker` |
| 其他错误 | 不重试 | `@Retryable` |

---

### 练习 5：Direct Connect vs SSH 远程会话

**目标**：理解 Direct Connect 和 SSH 远程会话的区别。

**场景**：用户在本地 Mac 上，想连接远程 Linux 服务器上的 Claude Code，应该用哪种方式？

**答案**：

| 方面 | Direct Connect | SSH 远程会话 |
|------|---------------|-------------|
| 连接方向 | CLI → 服务器 | 服务器 → CLI |
| 配置 | `cc:// URL` | SSH 配置 |
| 延迟 | 较低 | 取决于网络 |
| 适用场景 | 内网穿透 | 通用 |

**Direct Connect 流程**：
```
本地 Claude Code
    ↓
解析 cc:// URL（包含 serverUrl + authToken）
    ↓
Direct Connect Session 建立
    ↓
远程 Claude Code 作为服务端
```

**SSH 远程会话流程**：
```
用户输入 /connect user@host
    ↓
建立 SSH 连接
    ↓
在远程服务器启动 Claude Code
    ↓
通过 SSH 管道传输数据
```

**Java 对比**：Direct Connect 类似于 RMI 的 stub-skeleton 机制，SSH 远程会话类似于 JMX 的远程管理。

---

## 练习答案速查

| 练习 | 核心答案 |
|------|---------|
| 1 | createMessageStream → normalize → buildSystemPrompt → SDK → streaming |
| 2 | PKCE: verifier → challenge → auth URL → callback → token exchange |
| 3 | Bridge 是 WebSocket/stdin 协议，IDE ↔ CLI 双向消息 |
| 4 | 指数退避重试：429/500/503 可重试，其他不重试 |
| 5 | Direct Connect=CLI→服务器，SSH=服务器→CLI隧道 |

---

## API 通信 vs Java HTTP Client

| 方面 | Claude Code | Java |
|------|------------|------|
| HTTP 客户端 | Anthropic SDK | RestTemplate / WebClient |
| 流式处理 | AsyncGenerator | Flux / Observable |
| 重试策略 | withRetry() | Resilience4j @Retryable |
| 认证 | OAuth + API Key | Spring Security OAuth2 |
| 多云 | Bedrock / Vertex | AWS SDK / GCP SDK |
| 远程会话 | SSH / WebSocket | JMX / RMI |
| IDE 集成 | Bridge 模式 | LSP (Language Server Protocol) |

---

## 关键文件速查

| 功能 | 文件路径 |
|------|---------|
| API 调用 | `src/services/api/claude.ts` |
| OAuth | `src/services/oauth/client.ts` |
| 远程会话 | `src/remote/RemoteSessionManager.ts` |
| Bridge | `src/bridge/bridgeMain.ts` |
| Direct Connect | `src/server/createDirectConnectSession.ts` |
| SSH | `src/hooks/useSSHSession.ts` |
| 错误处理 | `src/services/api/withRetry.ts` |

---

## 下一篇

👉 [12-typescript-vs-java.md](./12-typescript-vs-java.md) — TypeScript 与 Java 架构思想对比，包括类型系统、设计模式、异步编程的全面对比。
