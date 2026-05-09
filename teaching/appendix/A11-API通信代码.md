---
title: "A11 - API 通信代码详解"
description: "深入解析 Claude Code 与 Anthropic API 通信的核心代码，包括消息流创建、流式响应处理、认证、重试策略等。"
tags: [code, api, authentication, streaming, retry]
date: 2026-05-09
---

# A11 - API 通信代码详解

> **本文档目标**：深入解析 Claude Code 与 Anthropic API 通信的核心代码，包括消息流创建、流式响应处理、认证、重试策略等。

---

## 1. 消息流创建：createMessageStream()

**文件**：`src/services/api/claude.ts:100-200`

**功能**：创建到 Anthropic API 的流式消息请求。

```typescript
// src/services/api/claude.ts:100
export async function* createMessageStream(
  params: CreateMessageParams
): AsyncGenerator<MessageUpdate, void> {
  const {
    messages,
    systemPrompt,
    tools,
    model,
    maxTokens,
  } = params

  // 1. 标准化消息格式
  const normalizedMessages = normalizeMessagesForAPI(messages)

  // 2. 构建 system prompt
  const system = buildSystemPrompt(systemPrompt, {
    includeTools: tools.length > 0,
    toolDefinitions: tools.map(toolToAPISchema),
  })

  // 3. 构建 API 参数
  const apiParams = {
    model,
    messages: normalizedMessages,
    system,
    tools: tools.map(toolToAPISchema),
    stream: true,
    max_tokens: maxTokens ?? getMaxOutputTokensForModel(model),
    betas: getSdkBetas(),
  }

  // 4. 发送请求
  const response = await anthropic.messages.create(apiParams)

  // 5. 处理流式响应
  for await (const event of response) {
    yield parseStreamEvent(event)
  }
}
```

---

## 2. 消息标准化：normalizeMessagesForAPI()

**文件**：`src/services/api/claude.ts:50-90`

**功能**：将内部消息格式转换为 API 兼容格式。

```typescript
// src/services/api/claude.ts:50
export function normalizeMessagesForAPI(
  messages: Message[]
): APICompatibleMessage[] {
  return messages
    .filter(isAPISendable)  // 过滤 UI-only 消息
    .map(normalizeMessage)
}

function isAPISendable(message: Message): boolean {
  // 不发送以下类型的消息
  if (message.type === 'progress') return false
  if (message.type === 'context_collapse') return false
  if (isCompactBoundaryMessage(message)) return false
  return true
}

function normalizeMessage(message: Message): APICompatibleMessage {
  return {
    role: message.role,
    content: normalizeContent(message.content),
  }
}
```

---

## 3. 流式事件处理

**文件**：`src/services/api/claude.ts:200-300`

**功能**：解析 API 返回的流式事件。

```typescript
// src/services/api/claude.ts:200
export type StreamEvent =
  | { type: 'text'; content: string }
  | { type: 'tool_use'; name: string; input: object; id: string }
  | { type: 'tool_result'; toolUseId: string; content: string }
  | { type: 'usage'; inputTokens: number; outputTokens: number }
  | { type: 'error'; error: string }

export function parseStreamEvent(event: RawStreamEvent): StreamEvent {
  switch (event.type) {
    case 'content_block_delta':
      if (event.delta.type === 'text_delta') {
        return { type: 'text', content: event.delta.text }
      }
      if (event.delta.type === 'input_json_delta') {
        return {
          type: 'tool_use',
          name: event.content_block.name,
          input: JSON.parse(event.delta.partial_json),
          id: event.content_block.id,
        }
      }
      break

    case 'content_block_stop':
      if (event.content_block.type === 'tool_use') {
        return {
          type: 'tool_result',
          toolUseId: event.content_block.id,
          content: '',  // 稍后填充
        }
      }
      break

    case 'message_delta':
      return {
        type: 'usage',
        inputTokens: event.usage.input_tokens,
        outputTokens: event.usage.output_tokens,
      }
  }

  return { type: 'error', error: `Unknown event: ${event.type}` }
}
```

---

## 4. 重试策略：withRetry()

**文件**：`src/services/api/withRetry.ts:30-100`

**功能**：实现指数退避重试逻辑。

```typescript
// src/services/api/withRetry.ts:30
export async function withRetry<T>(
  fn: () => Promise<T>,
  options: RetryOptions = {}
): Promise<T> {
  const {
    maxRetries = 3,
    initialDelayMs = 1000,
    maxDelayMs = 30000,
    backoffMultiplier = 2,
    shouldRetry = defaultShouldRetry,
  } = options

  let lastError: Error
  let delay = initialDelayMs

  for (let attempt = 0; attempt <= maxRetries; attempt++) {
    try {
      return await fn()
    } catch (error) {
      lastError = error as Error

      // 检查是否应该重试
      if (attempt === maxRetries || !shouldRetry(error)) {
        throw error
      }

      // 检查是否是速率限制
      if (isRateLimitError(error)) {
        const retryAfter = getRetryAfterHeader(error)
        if (retryAfter) {
          delay = Math.min(retryAfter * 1000, maxDelayMs)
        }
      }

      // 等待后重试
      await sleep(delay)
      delay = Math.min(delay * backoffMultiplier, maxDelayMs)
    }
  }

  throw lastError!
}

// 默认重试条件
function defaultShouldRetry(error: unknown): boolean {
  if (error instanceof RateLimitError) return true
  if (error instanceof ServerError && error.status >= 500) return true
  if (error instanceof NetworkError) return true
  return false
}
```

---

## 5. OAuth 认证流程

**文件**：`src/services/oauth/client.ts:50-150`

**功能**：完整的 OAuth 2.0 + PKCE 认证流程。

```typescript
// src/services/oauth/client.ts:50
export async function authenticateWithOAuth(): Promise<OAuthTokens> {
  // 1. 生成 PKCE 参数
  const codeVerifier = generateRandomString(64)
  const codeChallenge = await sha256Hash(codeVerifier)

  // 2. 启动本地回调服务器
  const callbackPort = await findAvailablePort(3100, 3200)
  const callbackUrl = `http://localhost:${callbackPort}/callback`

  // 3. 构建授权 URL
  const authUrl = new URL(`${AUTH_BASE_URL}/authorize`)
  authUrl.searchParams.set('client_id', OAUTH_CLIENT_ID)
  authUrl.searchParams.set('redirect_uri', callbackUrl)
  authUrl.searchParams.set('response_type', 'code')
  authUrl.searchParams.set('code_challenge', codeChallenge)
  authUrl.searchParams.set('code_challenge_method', 'S256')
  authUrl.searchParams.set('scope', 'claude.ai')

  // 4. 打开浏览器授权
  await openBrowser(authUrl.toString())

  // 5. 等待回调
  const callback = await waitForOAuthCallback(callbackPort)

  // 6. 交换 token
  const tokenResponse = await fetch(`${AUTH_BASE_URL}/token`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      grant_type: 'authorization_code',
      code: callback.code,
      redirect_uri: callbackUrl,
      code_verifier: codeVerifier,
      client_id: OAUTH_CLIENT_ID,
    }),
  })

  // 7. 存储 token
  await storeOAuthTokens(tokenResponse)

  return tokenResponse
}
```

---

## 6. API 错误处理

**文件**：`src/services/api/errors.ts:30-80`

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
  constructor(
    public retryAfterMs?: number
  ) {
    super('Rate limit exceeded', 429, 'RATE_LIMIT')
  }
}

export class AuthenticationError extends APIError {
  constructor() {
    super('Authentication failed', 401, 'AUTH_ERROR')
  }
}

export class QuotaExceededError extends APIError {
  constructor(public quotaType: 'tokens' | 'requests') {
    super(`Quota exceeded: ${quotaType}`, 403, 'QUOTA_EXCEEDED')
  }
}

export class PromptTooLongError extends APIError {
  constructor(public maxTokens: number) {
    super('Prompt too long', 400, 'PROMPT_TOO_LONG')
  }
}
```

---

---

## 练习

### 练习 1：消息标准化

**问题**：Claude Code 的内部消息格式和 API 格式有什么不同？为什么需要转换？

**答案**：

**格式差异**：
```typescript
// Claude Code 内部格式
interface Message {
  id: string
  role: 'user' | 'assistant'
  content: ContentBlock[]
  type?: 'api-round' | 'compact-boundary'
}

// API 格式
interface APIMessage {
  role: 'user' | 'assistant'
  content: string | ContentBlock[]
}
```

**转换原因**：
1. API 有固定的字段要求
2. 内部有额外元数据（id, type 等）
3. content 格式不同

```typescript
// 转换函数
function normalizeMessagesForAPI(messages: Message[]): APIMessage[] {
  return messages
    .filter(m => m.role === 'user' || m.role === 'assistant')
    .map(m => ({
      role: m.role,
      content: m.content  // 可能是 string 或 ContentBlock[]
    }))
}
```

---

### 练习 2：流式事件解析

**问题**：`parseStreamEvent()` 如何解析 SSE 格式的流式响应？

**答案**：

**SSE 格式**：
```
event: content_block_delta
data: {"type":"content_block_delta","index":0,"delta":{"type":"text_delta","text":"Hello"}}

event: message_stop
data: {"type":"message_stop"}
```

**解析逻辑**：
```typescript
function parseStreamEvent(lines: string[]): StreamEvent | null {
  let event: string | undefined
  let data: string

  for (const line of lines) {
    if (line.startsWith('event:')) {
      event = line.slice(6).trim()
    } else if (line.startsWith('data:')) {
      data = line.slice(5).trim()
    }
  }

  if (!data) return null

  const parsed = JSON.parse(data)

  return {
    type: event || parsed.type,
    data: parsed
  }
}
```

---

### 练习 3：重试策略

**问题**：哪些 API 错误需要重试？重试策略是什么？

**答案**：

**可重试错误**：
| 错误类型 | 重试 | 原因 |
|---------|------|------|
| `RateLimitError` (429) | ✅ | 服务端限流 |
| `ServerError` (5xx) | ✅ | 服务端问题 |
| `NetworkError` | ✅ | 网络问题 |
| `AuthenticationError` (401) | ❌ | 认证失败 |
| `QuotaExceeded` (403) | ❌ | 配额用尽 |

**重试策略**：
```typescript
async function withRetry<T>(
  fn: () => Promise<T>,
  maxRetries = 3
): Promise<T> {
  for (let i = 0; i < maxRetries; i++) {
    try {
      return await fn()
    } catch (error) {
      if (!isRetryable(error)) throw error

      const delay = calculateBackoff(i)  // 指数退避
      await sleep(delay)
    }
  }
  throw new Error('Max retries exceeded')
}
```

---

### 练习 4：OAuth PKCE 流程

**问题**：Claude Code 的 OAuth 认证为什么使用 PKCE？流程是怎样的？

**答案**：

**PKCE 作用**：防止授权码被拦截

**完整流程**：
```
1. 客户端生成 code_verifier（随机字符串）
2. 计算 code_challenge = SHA256(code_verifier)
3. 打开浏览器，跳转到授权页面（含 code_challenge）
4. 用户授权，浏览器重定向到 localhost 回调
5. 客户端收到 code
6. 用 code + code_verifier 换取 token
7. 服务器验证 code_challenge
```

**关键代码**：
```typescript
const codeVerifier = generateRandomString(64)
const codeChallenge = await sha256Hash(codeVerifier)  // S256

// 换取 token
const token = await fetch('/token', {
  body: { code, code_verifier: codeVerifier }
})
```

---

### 练习 5：错误类型层次

**问题**：API 错误的类层次结构是什么？

**答案**：

```
Error
  └── APIError (基类)
        ├── RateLimitError (429)
        ├── AuthenticationError (401)
        ├── QuotaExceededError (403)
        └── PromptTooLongError (400)
```

**使用场景**：
```typescript
try {
  await createMessageStream(request)
} catch (error) {
  if (error instanceof RateLimitError) {
    // 显示 "请求过于频繁，请稍后重试"
  } else if (error instanceof AuthenticationError) {
    // 跳转登录
  } else if (error instanceof QuotaExceededError) {
    // 显示配额不足
  }
}
```

---

## 练习答案速查

| 练习 | 核心答案 |
|------|---------|
| 1 | 内部格式有额外字段，API格式需标准化 |
| 2 | 解析 event: 和 data: 行，JSON.parse data |
| 3 | 5xx/429/网络错误重试，4xx 不重试 |
| 4 | PKCE 防止授权码拦截，code_verifier 验证 |
| 5 | APIError 基类 → RateLimit/Auth/Quota/PromptTooLong |

---

## 附录：API 响应码速查

| 状态码 | 含义 | 处理 |
|--------|------|------|
| 200 | 成功 | 解析响应 |
| 400 | 请求错误 | 检查参数 |
| 401 | 认证失败 | 刷新 token |
| 403 | 权限/配额 | 提示用户 |
| 429 | 限流 | 等待重试 |
| 500+ | 服务器错误 | 等待重试 |

---

## 8. 关键源码文件索引

| 文件 | 关键函数 | 说明 |
|------|---------|------|
| `src/services/api/claude.ts` | `createMessageStream()` | 消息流创建 |
| `src/services/api/claude.ts` | `normalizeMessagesForAPI()` | 消息标准化 |
| `src/services/api/claude.ts` | `parseStreamEvent()` | 流式事件解析 |
| `src/services/api/client.ts` | `createAnthropicClient()` | 客户端初始化 |
| `src/services/api/withRetry.ts` | `withRetry()` | 重试逻辑 |
| `src/services/api/errors.ts` | `APIError` 等 | 错误类型定义 |
| `src/services/oauth/client.ts` | `authenticateWithOAuth()` | OAuth 认证 |
| `src/services/oauth/client.ts` | `refreshOAuthToken()` | Token 刷新 |
| `src/utils/auth.ts` | `getAPIKey()` | API Key 获取 |
| `src/utils/auth.ts` | `getAuthToken()` | Auth Token 获取 |

---

## 附录导航

👈 [A10-插件系统代码.md](./A10-插件系统代码.md) | [A13-TypeScript实战.md](./A13-TypeScript实战.md) 👉
