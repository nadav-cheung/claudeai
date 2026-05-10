# 16 - API 通信与远程

> **本章目标**：深入理解 Claude Code 如何与 Anthropic API 通信，以及远程会话的工作原理。

---

## 1. 准备工作

### 1.1 阅读源码

**必读**：
- `src/services/api/claude.ts` - API 客户端
- `src/remote/` - 远程会话

### 1.2 本章与 Mini-Claude 的关系

| Mini-Claude | Claude Code |
|-------------|-------------|
| 简单 fetch | 完整 ApiService |
| 无重试 | 自动重试 |
| 无远程 | 远程会话 |

---

## 2. API 通信架构

### 2.1 Claude Code 的 API 层

```text
┌─────────────────────────────────────────────────────┐
│                   Claude Code                        │
│                                                     │
│  ┌───────────────────────────────────────────────┐  │
│  │              ApiService                        │  │
│  │  ┌─────────┐  ┌──────────┐  ┌─────────────┐  │  │
│  │  │请求构建 │  │ 重试逻辑 │  │ 流式处理   │  │  │
│  │  └─────────┘  └──────────┘  └─────────────┘  │  │
│  └───────────────────────────────────────────────┘  │
│                      │                              │
│                      ▼                              │
│  ┌───────────────────────────────────────────────┐  │
│  │              fetch / WebSocket                 │  │
│  └───────────────────────────────────────────────┘  │
│                      │                              │
└──────────────────────│──────────────────────────────┘
                       │
                       ▼
              ┌──────────────────┐
              │  Anthropic API    │
              │  api.anthropic.com │
              └──────────────────┘
```

### 2.2 Mini-Claude 的简单实现

```typescript
// Mini-Claude: 简单的 API 调用
async function callApi(messages: Message[]) {
  const response = await fetch('https://api.anthropic.com/v1/messages', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'x-api-key': API_KEY,
      'anthropic-version': '2023-06-01',
    },
    body: JSON.stringify({
      model: 'claude-3-5-sonnet-20241022',
      messages,
      max_tokens: 1024,
    }),
  });

  return response.json();
}
```

---

## 3. Claude Code 的 ApiService

### 3.1 请求构建

```typescript
// services/api/claude.ts (简化)
export class ApiService {
  private apiKey: string;
  private baseUrl = 'https://api.anthropic.com/v1';

  async createMessage(
    request: CreateMessageRequest
  ): Promise<CreateMessageResponse> {
    // 1. 构建请求
    const payload = {
      model: request.model,
      messages: this.formatMessages(request.messages),
      system: this.formatSystem(request.system),
      tools: this.formatTools(request.tools),
      max_tokens: request.maxTokens || 8192,
      stream: request.stream ?? true,
    };

    // 2. 签名请求（如果有）
    const headers = await this.signRequest(payload);

    // 3. 发送请求
    const response = await this.sendWithRetry(
      `${this.baseUrl}/messages`,
      {
        method: 'POST',
        headers,
        body: JSON.stringify(payload),
      }
    );

    return response.json();
  }

  private async signRequest(payload: object): Promise<Record<string, string>> {
    // 添加认证头
    return {
      'Content-Type': 'application/json',
      'x-api-key': this.apiKey,
      'anthropic-version': '2023-06-01',
      'anthropic-dangerous-direct-browser-access': 'true',
    };
  }
}
```

---

## 4. 重试机制

### 4.1 指数退避

```typescript
// Claude Code 的重试机制
async function sendWithRetry(
  url: string,
  options: RequestInit,
  maxRetries = 3
): Promise<Response> {
  let lastError: Error | null = null;

  for (let attempt = 0; attempt < maxRetries; attempt++) {
    try {
      const response = await fetch(url, options);

      // 成功或客户端错误（不重试）
      if (response.ok || response.status < 500) {
        return response;
      }

      // 服务端错误，重试
      lastError = new Error(`HTTP ${response.status}`);

    } catch (error) {
      lastError = error as Error;
    }

    // 指数退避等待
    if (attempt < maxRetries - 1) {
      const delay = Math.pow(2, attempt) * 1000; // 1s, 2s, 4s
      await sleep(delay);
    }
  }

  throw lastError;
}
```

### 4.2 错误处理

```typescript
// API 错误类型
interface ApiError {
  type: 'rate_limit' | 'authentication' | 'validation' | 'server_error';
  message: string;
  retryAfter?: number;
}

function parseApiError(response: Response): ApiError {
  switch (response.status) {
    case 429:
      return { type: 'rate_limit', message: 'Rate limit exceeded' };
    case 401:
      return { type: 'authentication', message: 'Invalid API key' };
    case 400:
      return { type: 'validation', message: 'Invalid request' };
    default:
      return { type: 'server_error', message: 'Server error' };
  }
}
```

---

## 5. 流式响应处理

### 5.1 SSE 事件解析

```typescript
// Claude Code 的流式处理
async function* streamResponse(
  response: Response
): AsyncGenerator<StreamEvent> {
  const reader = response.body?.getReader();
  if (!reader) throw new Error('No response body');

  const decoder = new TextDecoder();
  let buffer = '';

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;

    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split('\n');
    buffer = lines.pop() || '';

    for (const line of lines) {
      if (line.startsWith('data: ')) {
        const data = line.slice(6);
        if (data === '[DONE]') return;
        yield JSON.parse(data);
      }
    }
  }
}
```

### 5.2 流式事件类型

```typescript
// 流式事件
type StreamEvent =
  | { type: 'message_start'; message: Message }
  | { type: 'content_block_start'; index: number; block: ContentBlock }
  | { type: 'content_block_delta'; index: number; delta: Delta }
  | { type: 'content_block_stop'; index: number }
  | { type: 'message_delta'; delta: Delta; usage: Usage }
  | { type: 'message_stop' };

// 处理事件
async function handleStream(events: AsyncGenerator<StreamEvent>) {
  for await (const event of events) {
    switch (event.type) {
      case 'content_block_delta':
        if (event.delta.type === 'text_delta') {
          process.stdout.write(event.delta.text);
        }
        break;

      case 'message_delta':
        updateTokenUsage(event.usage);
        break;
    }
  }
}
```

---

## 6. 远程会话

### 6.1 远程会话架构

```
本地 Claude Code              远程服务器
      │                           │
      │  ──── WebSocket ──────▶  │
      │                           │
      │  加密通信                  │  解密
      │                           ▼
      │                      ┌────────────┐
      │                      │ 会话处理    │
      │                      │  (在服务器) │
      │                      └────────────┘
      │                           │
      │  ◀──── 渲染更新 ────────  │
      │                           │
```

### 6.2 远程会话流程

```typescript
// remote/session.ts (简化)
class RemoteSession {
  private ws: WebSocket;
  private localState: AppState;

  async connect(sessionId: string, token: string): Promise<void> {
    // 1. 建立 WebSocket 连接
    this.ws = new WebSocket(`wss://remote.claude.ai/sessions/${sessionId}`);

    // 2. 认证
    this.ws.send(JSON.stringify({ token }));

    // 3. 同步状态
    this.ws.onmessage = (event) => {
      const update = JSON.parse(event.data);
      this.applyRemoteUpdate(update);
    };
  }

  // 发送本地更新到远程
  sendUpdate(update: StateUpdate): void {
    this.ws.send(JSON.stringify({
      type: 'state_update',
      payload: encrypt(update),
    }));
  }
}
```

---

## 7. 实战练习

### 7.1 练习：实现简单的请求重试

**目标**：为 Mini-Claude 添加重试机制

**答案要点**：
```typescript
async function callWithRetry(
  request: Request,
  maxRetries = 3
): Promise<Response> {
  for (let i = 0; i < maxRetries; i++) {
    try {
      const response = await fetch(request);

      // 4xx 错误不重试
      if (response.status >= 400 && response.status < 500) {
        return response;
      }

      // 5xx 错误重试
      if (response.status >= 500) {
        const delay = Math.pow(2, i) * 1000;
        await sleep(delay);
        continue;
      }

      return response;

    } catch (error) {
      if (i === maxRetries - 1) throw error;
      await sleep(Math.pow(2, i) * 1000);
    }
  }

  throw new Error('Max retries exceeded');
}
```

---

## 8. 总结

| 方面 | Mini-Claude | Claude Code |
|------|-------------|-------------|
| API 调用 | fetch 直接调用 | 封装服务 |
| 重试机制 | 无 | 指数退避 |
| 流式处理 | 基础 | 完整 SSE |
| 错误分类 | 无 | 细粒度 |
| 远程会话 | 无 | WebSocket |

---

## 书籍三阶段总结

恭喜你完成了深入篇！现在你已经：

1. **理解架构** - 从 Mini-Claude 到 Claude Code
2. **掌握核心模块** - 工具系统、权限、上下文、MCP
3. **理解高级特性** - Agent、记忆、Skills

---

## 下一篇

👉 [17 - 如何阅读大型项目源码](17-how-to-read-source.md) —— 开启实战篇

`★ Insight ─────────────────────────────────────`
API 通信层虽然看起来是"底层"，但它直接影响用户体验——重试机制让网络不稳定时更稳定，流式处理让响应更快。Claude Code 在这层的投入（重试、流式、错误分类）保证了在各种网络环境下的可靠性。Mini-Claude 的简单实现适合原型，在生产环境需要类似 Claude Code 的健壮处理。
`─────────────────────────────────────────────────`
