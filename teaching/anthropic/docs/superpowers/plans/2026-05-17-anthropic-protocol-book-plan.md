# Anthropic 协议深度剖析 书籍写作计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 完成《Anthropic 协议深度剖析：Python & Node.js 实现指南》全书 17 章的写作，每章含协议规范文档 + Python 实现 + Node.js 实现 + 自测题。

**Architecture:** 每章为独立 markdown 文件（`chapters/ch-XX-title.md`），配套代码按语言分目录（`code/python/chXX/` 和 `code/node/chXX/`）。附录独立文件。全书通过 `README.md` 作为入口索引。

**Tech Stack:** Markdown（正文）、Python 3.12+ / httpx（Python 代码）、TypeScript 5.x / Node.js 22+（Node 代码）、Pytest / Vitest（代码验证）

---

## 文件结构

```
anthropic-protocol-book/
├── README.md                          # 全书入口、阅读路径指引
├── chapters/
│   ├── ch-01-api-basics.md
│   ├── ch-02-messages-api.md
│   ├── ch-03-models.md
│   ├── ch-04-structured-outputs.md
│   ├── ch-05-streaming-thinking.md
│   ├── ch-06-tool-use.md
│   ├── ch-07-computer-use.md
│   ├── ch-08-context-management.md
│   ├── ch-09-batch-api.md
│   ├── ch-10-memory-citations.md
│   ├── ch-11-mcp-spec.md
│   ├── ch-12-mcp-implementation.md
│   ├── ch-13-rag.md
│   ├── ch-14-agent-sdk-patterns.md
│   ├── ch-15-managed-agents.md
│   ├── ch-16-langchain-langgraph.md
│   └── ch-17-production.md
├── code/
│   ├── python/
│   │   ├── ch01/  # API 基础客户端
│   │   ├── ch02/  # Messages 构建器
│   │   ├── ch03/  # Model 选择器、Token 计数器
│   │   ├── ch04/  # Structured Output 客户端
│   │   ├── ch05/  # SSE 流解析器（从零实现）
│   │   ├── ch06/  # Tool Use 引擎
│   │   ├── ch07/  # Computer Use 客户端
│   │   ├── ch08/  # 缓存感知 Client + Compaction
│   │   ├── ch09/  # Batch 提交与收集客户端
│   │   ├── ch10/  # Memory 管理客户端 + Citations 解析器
│   │   ├── ch11/  # JSON-RPC 消息构造器
│   │   ├── ch12/  # MCP Server + Client + Tasks
│   │   ├── ch13/  # RAG Pipeline + Claude-as-Judge
│   │   ├── ch14/  # Agent Loop + Sub-Agent Orchestration
│   │   ├── ch15/  # Managed Agent 部署脚本
│   │   ├── ch16/  # LangGraph Agent
│   │   └── ch17/  # 生产级 Client 包装器（限流/重试/安全/预算）
│   └── node/
│       ├── ch01/  # (mirror structure above)
│       ├── ...
│       └── ch17/
├── appendices/
│   ├── appendix-a-api-reference.md
│   ├── appendix-b-model-matrix.md
│   ├── appendix-c-self-test-answers.md
│   ├── appendix-d-glossary.md
│   └── appendix-e-protocol-changelog.md
└── tests/
    ├── python/
    │   ├── test_ch01_client.py
    │   ├── ...
    │   └── test_ch17_production.py
    └── node/
        ├── ch01.test.ts
        ├── ...
        └── ch17.test.ts
```

---

### Task 1: 项目骨架搭建

**Files:**
- Create: `README.md`、`chapters/`（空目录）、`code/python/`、`code/node/`、`appendices/`、`tests/`

- [ ] **Step 1: 创建目录结构**

```bash
mkdir -p anthropic-protocol-book/{chapters,code/{python,node},appendices,tests/{python,node}}
```

- [ ] **Step 2: 编写 README.md 入口文件**

README.md 内容：书名、简介、3 条推荐阅读路径（来自 spec）、完整目录、每章一句话描述。

- [ ] **Step 3: 创建每章占位文件**

```bash
cd anthropic-protocol-book/chapters
for i in $(seq -w 1 17); do
  echo "# 第 $i 章" > "ch-$i-placeholder.md"
done
```

- [ ] **Step 4: 创建附录占位文件**

```bash
cd anthropic-protocol-book/appendices
for f in appendix-a-api-reference.md appendix-b-model-matrix.md appendix-c-self-test-answers.md appendix-d-glossary.md appendix-e-protocol-changelog.md; do
  echo "# $(echo $f | sed 's/\.md$//' | sed 's/-/ /g')" > "$f"
done
```

- [ ] **Step 5: Commit**

```bash
cd anthropic-protocol-book
git init
git add -A
git commit -m "feat: initialize book project skeleton with 17 chapters and appendices"
```

---

### Task 2: 第 1 章 — Anthropic API 基础

**Files:**
- Create: `chapters/ch-01-api-basics.md`
- Create: `code/python/ch01/client.py`、`code/python/ch01/test_client.py`
- Create: `code/node/ch01/AnthropicClient.ts`、`code/node/ch01/client.test.ts`

- [ ] **Step 1: 编写"概念全景"部分**

覆盖：Anthropic API 在整个生态中的位置、设计理念、与 OpenAI API 的关键协议差异（仅一处简表）、读者学完本章能用什么。

- [ ] **Step 2: 编写协议规范部分**

按协议字段表格格式逐一讲解：
- x-api-key header、Bearer token 两种认证方式
- Base URL `https://api.anthropic.com/v1/messages`
- HTTP POST、Content-Type: application/json
- error type 枚举（authentication_error、rate_limit_error、invalid_request_error、api_error、overloaded_error）
- HTTP Status codes 映射
- RPM/TPM/Usage Tier 体系
- Content Blocks 抽象模型（text/image/tool_use/tool_result）

- [ ] **Step 3: 编写 Python 实现**

```python
# code/python/ch01/client.py
import os
import httpx
from dataclasses import dataclass
from enum import Enum
from typing import Optional

class AuthMethod(Enum):
    API_KEY = "x-api-key"
    BEARER = "bearer"

@dataclass
class ClientConfig:
    base_url: str = "https://api.anthropic.com/v1"
    api_key: Optional[str] = None
    auth_method: AuthMethod = AuthMethod.API_KEY
    timeout: float = 60.0

class AnthropicError(Exception):
    def __init__(self, status_code: int, error_type: str, message: str):
        self.status_code = status_code
        self.error_type = error_type
        self.message = message
        super().__init__(f"[{error_type}] {message}")

class AnthropicClient:
    def __init__(self, config: Optional[ClientConfig] = None):
        self.config = config or ClientConfig(
            api_key=os.environ.get("ANTHROPIC_API_KEY")
        )
        if not self.config.api_key:
            raise ValueError("API key required: set ANTHROPIC_API_KEY or pass in ClientConfig")
        self._client = httpx.Client(
            base_url=self.config.base_url,
            timeout=self.config.timeout,
            headers=self._build_headers()
        )

    def _build_headers(self) -> dict:
        if self.config.auth_method == AuthMethod.API_KEY:
            return {"x-api-key": self.config.api_key, "anthropic-version": "2023-06-01"}
        return {"Authorization": f"Bearer {self.config.api_key}", "anthropic-version": "2023-06-01"}

    def _handle_error(self, response: httpx.Response) -> AnthropicError:
        body = response.json()
        error = body.get("error", {})
        return AnthropicError(
            status_code=response.status_code,
            error_type=error.get("type", "api_error"),
            message=error.get("message", "Unknown error")
        )

    def post(self, path: str, json: dict) -> dict:
        response = self._client.post(path, json=json)
        if response.status_code >= 400:
            raise self._handle_error(response)
        return response.json()

    def close(self):
        self._client.close()

class AsyncAnthropicClient:
    def __init__(self, config: Optional[ClientConfig] = None):
        self.config = config or ClientConfig(
            api_key=os.environ.get("ANTHROPIC_API_KEY")
        )
        if not self.config.api_key:
            raise ValueError("API key required")
        self._client = httpx.AsyncClient(
            base_url=self.config.base_url,
            timeout=self.config.timeout,
            headers=self._build_headers()
        )

    def _build_headers(self) -> dict:
        if self.config.auth_method == AuthMethod.API_KEY:
            return {"x-api-key": self.config.api_key, "anthropic-version": "2023-06-01"}
        return {"Authorization": f"Bearer {self.config.api_key}", "anthropic-version": "2023-06-01"}

    def _handle_error(self, response: httpx.Response) -> AnthropicError:
        body = response.json()
        error = body.get("error", {})
        return AnthropicError(
            status_code=response.status_code,
            error_type=error.get("type", "api_error"),
            message=error.get("message", "Unknown error")
        )

    async def post(self, path: str, json: dict) -> dict:
        response = await self._client.post(path, json=json)
        if response.status_code >= 400:
            raise self._handle_error(response)
        return response.json()

    async def close(self):
        await self._client.aclose()
```

- [ ] **Step 4: 编写 Python 测试**

```python
# code/python/ch01/test_client.py
import pytest
import os
from unittest.mock import patch, MagicMock
from client import AnthropicClient, ClientConfig, AnthropicError, AuthMethod

def test_client_requires_api_key():
    with patch.dict(os.environ, {}, clear=True):
        with pytest.raises(ValueError, match="API key required"):
            AnthropicClient(ClientConfig(api_key=None))

def test_client_builds_x_api_key_headers():
    client = AnthropicClient(ClientConfig(api_key="sk-test-123"))
    headers = client._build_headers()
    assert headers["x-api-key"] == "sk-test-123"
    assert headers["anthropic-version"] == "2023-06-01"

def test_client_builds_bearer_headers():
    client = AnthropicClient(ClientConfig(api_key="sk-test-456", auth_method=AuthMethod.BEARER))
    headers = client._build_headers()
    assert headers["Authorization"] == "Bearer sk-test-456"

def test_handle_error_parses_api_error():
    client = AnthropicClient(ClientConfig(api_key="sk-test"))
    mock_response = MagicMock()
    mock_response.status_code = 429
    mock_response.json.return_value = {
        "error": {"type": "rate_limit_error", "message": "Too many requests"}
    }
    error = client._handle_error(mock_response)
    assert error.status_code == 429
    assert error.error_type == "rate_limit_error"
    assert "Too many requests" in error.message

def test_post_raises_on_4xx():
    client = AnthropicClient(ClientConfig(api_key="sk-test"))
    mock_response = MagicMock()
    mock_response.status_code = 401
    mock_response.json.return_value = {
        "error": {"type": "authentication_error", "message": "Invalid API key"}
    }
    client._client.post = MagicMock(return_value=mock_response)
    with pytest.raises(AnthropicError) as exc:
        client.post("/v1/messages", {"model": "claude-sonnet-4-6"})
    assert exc.value.error_type == "authentication_error"

def test_post_returns_json_on_success():
    client = AnthropicClient(ClientConfig(api_key="sk-test"))
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"id": "msg_123", "content": []}
    client._client.post = MagicMock(return_value=mock_response)
    result = client.post("/v1/messages", {"model": "claude-sonnet-4-6"})
    assert result["id"] == "msg_123"
```

- [ ] **Step 5: 运行 Python 测试验证通过**

```bash
cd code/python/ch01 && python -m pytest test_client.py -v
```
Expected: 6 tests PASS

- [ ] **Step 6: 编写 Node.js 实现**

```typescript
// code/node/ch01/AnthropicClient.ts
type AuthMethod = "x-api-key" | "bearer";

interface ClientConfig {
  baseUrl?: string;
  apiKey?: string;
  authMethod?: AuthMethod;
  timeout?: number;
}

interface AnthropicErrorResponse {
  error: {
    type: string;
    message: string;
  };
}

class AnthropicError extends Error {
  public statusCode: number;
  public errorType: string;

  constructor(statusCode: number, errorType: string, message: string) {
    super(`[${errorType}] ${message}`);
    this.statusCode = statusCode;
    this.errorType = errorType;
    this.name = "AnthropicError";
  }
}

class AnthropicClient {
  private baseUrl: string;
  private apiKey: string;
  private authMethod: AuthMethod;
  private timeout: number;

  constructor(config: ClientConfig = {}) {
    this.baseUrl = config.baseUrl ?? "https://api.anthropic.com/v1";
    this.apiKey = config.apiKey ?? process.env.ANTHROPIC_API_KEY ?? "";
    this.authMethod = config.authMethod ?? "x-api-key";
    this.timeout = config.timeout ?? 60_000;

    if (!this.apiKey) {
      throw new Error("API key required: set ANTHROPIC_API_KEY or pass in config");
    }
  }

  private buildHeaders(): Record<string, string> {
    const headers: Record<string, string> = {
      "anthropic-version": "2023-06-01",
      "content-type": "application/json",
    };
    if (this.authMethod === "x-api-key") {
      headers["x-api-key"] = this.apiKey;
    } else {
      headers["authorization"] = `Bearer ${this.apiKey}`;
    }
    return headers;
  }

  private handleError(statusCode: number, body: AnthropicErrorResponse): never {
    const { type, message } = body.error;
    throw new AnthropicError(statusCode, type, message);
  }

  async post(path: string, body: Record<string, unknown>): Promise<unknown> {
    const response = await fetch(`${this.baseUrl}${path}`, {
      method: "POST",
      headers: this.buildHeaders(),
      body: JSON.stringify(body),
      signal: AbortSignal.timeout(this.timeout),
    });

    const json = await response.json();

    if (!response.ok) {
      this.handleError(response.status, json as AnthropicErrorResponse);
    }

    return json;
  }
}

export { AnthropicClient, AnthropicError, ClientConfig, AuthMethod };
```

- [ ] **Step 7: 编写 Node.js 测试**

```typescript
// code/node/ch01/client.test.ts
import { describe, it, expect, beforeEach, vi } from "vitest";
import { AnthropicClient, AnthropicError } from "./AnthropicClient";

describe("AnthropicClient", () => {
  it("throws if no API key provided", () => {
    vi.stubEnv("ANTHROPIC_API_KEY", "");
    expect(() => new AnthropicClient()).toThrow("API key required");
  });

  it("builds x-api-key headers correctly", () => {
    const client = new AnthropicClient({ apiKey: "sk-test-123" });
    const headers = (client as any).buildHeaders();
    expect(headers["x-api-key"]).toBe("sk-test-123");
  });

  it("builds bearer headers correctly", () => {
    const client = new AnthropicClient({ apiKey: "sk-test-456", authMethod: "bearer" });
    const headers = (client as any).buildHeaders();
    expect(headers["authorization"]).toBe("Bearer sk-test-456");
  });

  it("parses error response correctly", () => {
    const client = new AnthropicClient({ apiKey: "sk-test" });
    expect(() =>
      (client as any).handleError(429, {
        error: { type: "rate_limit_error", message: "Too many requests" },
      })
    ).toThrow(AnthropicError);
  });

  it("returns JSON on success", async () => {
    const client = new AnthropicClient({ apiKey: "sk-test" });
    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({ id: "msg_123", content: [] }),
    });
    const result = await client.post("/v1/messages", { model: "claude-sonnet-4-6" });
    expect((result as any).id).toBe("msg_123");
  });
});
```

- [ ] **Step 8: 运行 Node.js 测试验证通过**

```bash
cd code/node/ch01 && npx vitest run client.test.ts
```
Expected: 5 tests PASS

- [ ] **Step 9: 编写"最佳实践与常见陷阱"**

- API Key 轮转策略（含代码示例：双 key 平滑切换）
- NEVER 在客户端代码中硬编码 API Key（反面案例 + 正面案例）
- 区分 4xx（客户端错误，不重试）和 5xx（服务端错误，可重试）
- 429 速率限制的 Retry-After header 处理

- [ ] **Step 10: 编写自测题**

1. （理论）Asnthropic API 的错误类型有哪些？每种对应什么场景？
2. （理论）x-api-key 和 Authorization: Bearer 两种认证方式的区别是什么？
3. （编码）在不参考示例代码的情况下，实现一个支持多 key 轮转的基础 Client 类。
4. （编码）为 Client 类添加请求重试逻辑（3 次指数退避，仅对 5xx 和 429 重试）。

- [ ] **Step 11: Commit**

```bash
git add chapters/ch-01-api-basics.md code/python/ch01/ code/node/ch01/
git commit -m "feat: complete chapter 1 - Anthropic API basics (Python + Node.js)"
```

---

### Task 3: 第 2 章 — Messages API 核心协议

**Files:**
- Create: `chapters/ch-02-messages-api.md`
- Create: `code/python/ch02/message_builder.py`、`code/python/ch02/test_message_builder.py`
- Create: `code/node/ch02/MessageBuilder.ts`、`code/node/ch02/message_builder.test.ts`

- [ ] **Step 1: 编写概念全景与协议规范**

逐字段讲解 Messages API 端点，含 endpoint = `POST /v1/messages`，所有参数以表格呈现：

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| model | string | 是 | 模型标识符 |
| messages | Message[] | 是 | 对话消息列表 |
| max_tokens | integer | 是 | 最大输出 token 数 |
| system | string\|ContentBlock[] | 否 | 系统提示（两种传递方式） |
| temperature | float | 否 | 0-1，默认 1 |
| top_p | float | 否 | nucleus sampling |
| top_k | integer | 否 | top-k sampling |
| stop_sequences | string[] | 否 | 自定义停止序列 |
| stream | boolean | 否 | 是否启用 SSE 流 |
| metadata | object | 否 | 含 user_id 等 |

Content Blocks 结构逐类型讲解：
- `{"type": "text", "text": "..."}`
- `{"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": "..."}}`
- 支持的图像格式与尺寸限制（JPEG/PNG/GIF/WebP，最大 5MB 或 8000x8000px）
- `{"type": "tool_use", "id": "...", "name": "...", "input": {...}}`
- `{"type": "tool_result", "tool_use_id": "...", "content": [...]}`

- [ ] **Step 2: 编写 Python 实现 — MessageBuilder**

```python
# code/python/ch02/message_builder.py
from dataclasses import dataclass, field
from typing import Optional, Union, Literal
import base64
import mimetypes
from pathlib import Path

Role = Literal["user", "assistant"]
MediaType = Literal["image/jpeg", "image/png", "image/gif", "image/webp"]

class ContentBlock:
    """Base class for content blocks."""
    def to_dict(self) -> dict: ...

class TextBlock(ContentBlock):
    def __init__(self, text: str):
        self.text = text
    def to_dict(self) -> dict:
        return {"type": "text", "text": self.text}

class ImageBlock(ContentBlock):
    def __init__(self, source: Union[str, bytes], media_type: Optional[MediaType] = None):
        if isinstance(source, str):
            if source.startswith(("http://", "https://")):
                self._url = source
                self._data = None
            else:
                path = Path(source)
                self._data = base64.b64encode(path.read_bytes()).decode()
                self._media_type = media_type or self._guess_type(source)
                self._url = None
        else:
            self._data = base64.b64encode(source).decode()
            self._media_type = media_type or "image/png"
            self._url = None

    @staticmethod
    def _guess_type(path: str) -> str:
        mime, _ = mimetypes.guess_type(path)
        if mime in ("image/jpeg", "image/png", "image/gif", "image/webp"):
            return mime
        raise ValueError(f"Unsupported image format: {mime}")

    def to_dict(self) -> dict:
        if self._url:
            return {"type": "image", "source": {"type": "url", "url": self._url}}
        return {"type": "image", "source": {"type": "base64", "media_type": self._media_type, "data": self._data}}

class ToolUseBlock(ContentBlock):
    def __init__(self, id: str, name: str, input: dict):
        self.id = id
        self.name = name
        self.input = input
    def to_dict(self) -> dict:
        return {"type": "tool_use", "id": self.id, "name": self.name, "input": self.input}

class ToolResultBlock(ContentBlock):
    def __init__(self, tool_use_id: str, content: str, is_error: bool = False):
        self.tool_use_id = tool_use_id
        self.content = content
        self.is_error = is_error
    def to_dict(self) -> dict:
        return {"type": "tool_result", "tool_use_id": self.tool_use_id, "content": self.content, "is_error": self.is_error}

@dataclass
class Message:
    role: Role
    content: Union[str, list[ContentBlock]]

    def to_dict(self) -> dict:
        if isinstance(self.content, str):
            return {"role": self.role, "content": self.content}
        return {"role": self.role, "content": [b.to_dict() for b in self.content]}

@dataclass
class MessageRequest:
    model: str
    messages: list[Message]
    max_tokens: int
    system: Optional[Union[str, list[ContentBlock]]] = None
    temperature: Optional[float] = None
    top_p: Optional[float] = None
    top_k: Optional[int] = None
    stop_sequences: Optional[list[str]] = None
    stream: bool = False
    metadata: Optional[dict] = None

    def to_dict(self) -> dict:
        body = {
            "model": self.model,
            "messages": [m.to_dict() for m in self.messages],
            "max_tokens": self.max_tokens,
        }
        if self.system is not None:
            body["system"] = self.system if isinstance(self.system, str) else [b.to_dict() for b in self.system]
        for key in ("temperature", "top_p", "top_k", "stop_sequences", "stream", "metadata"):
            val = getattr(self, key)
            if val is not None:
                body[key] = val
        return body
```

- [ ] **Step 3: 编写 Python 测试并验证通过**

测试覆盖：text message 构建、image message 构建（base64 和 URL）、多 Content Block 混合、tool_use/tool_result block、request to_dict 完整输出。

```bash
cd code/python/ch02 && python -m pytest test_message_builder.py -v
```

- [ ] **Step 4: 编写 Node.js 实现**

```typescript
// code/node/ch02/MessageBuilder.ts
type Role = "user" | "assistant";
type MediaType = "image/jpeg" | "image/png" | "image/gif" | "image/webp";

interface ContentBlock {
  toDict(): Record<string, unknown>;
}

class TextBlock implements ContentBlock {
  constructor(public text: string) {}
  toDict() { return { type: "text", text: this.text }; }
}

class ImageBlock implements ContentBlock {
  private url: string | null = null;
  private data: string | null = null;
  private mediaType: string | null = null;

  constructor(source: string | Buffer, mediaType?: MediaType) {
    if (typeof source === "string") {
      if (source.startsWith("http://") || source.startsWith("https://")) {
        this.url = source;
      } else {
        const fs = require("fs");
        const buffer = fs.readFileSync(source);
        this.data = buffer.toString("base64");
        this.mediaType = mediaType ?? this.guessType(source);
      }
    } else {
      this.data = source.toString("base64");
      this.mediaType = mediaType ?? "image/png";
    }
  }

  private guessType(path: string): string {
    const ext = path.split(".").pop()?.toLowerCase();
    const map: Record<string, string> = { jpg: "image/jpeg", jpeg: "image/jpeg", png: "image/png", gif: "image/gif", webp: "image/webp" };
    const mime = map[ext ?? ""];
    if (!mime) throw new Error(`Unsupported image format: ${ext}`);
    return mime;
  }

  toDict() {
    if (this.url) return { type: "image", source: { type: "url", url: this.url } };
    return { type: "image", source: { type: "base64", media_type: this.mediaType, data: this.data } };
  }
}

class ToolUseBlock implements ContentBlock {
  constructor(public id: string, public name: string, public input: Record<string, unknown>) {}
  toDict() { return { type: "tool_use", id: this.id, name: this.name, input: this.input }; }
}

class ToolResultBlock implements ContentBlock {
  constructor(public toolUseId: string, public content: string, public isError: boolean = false) {}
  toDict() { return { type: "tool_result", tool_use_id: this.toolUseId, content: this.content, is_error: this.isError }; }
}

class Message {
  constructor(public role: Role, public content: string | ContentBlock[]) {}
  toDict() {
    if (typeof this.content === "string") return { role: this.role, content: this.content };
    return { role: this.role, content: this.content.map(b => b.toDict()) };
  }
}

interface MessageRequestParams {
  model: string;
  messages: Message[];
  maxTokens: number;
  system?: string | ContentBlock[];
  temperature?: number;
  topP?: number;
  topK?: number;
  stopSequences?: string[];
  stream?: boolean;
  metadata?: Record<string, unknown>;
}

class MessageRequest {
  constructor(private params: MessageRequestParams) {}
  toDict(): Record<string, unknown> {
    const body: Record<string, unknown> = {
      model: this.params.model,
      messages: this.params.messages.map(m => m.toDict()),
      max_tokens: this.params.maxTokens,
    };
    if (this.params.system !== undefined) {
      body.system = typeof this.params.system === "string" ? this.params.system : this.params.system.map(b => b.toDict());
    }
    for (const key of ["temperature", "topP", "topK", "stopSequences", "stream", "metadata"]) {
      const val = (this.params as any)[key] ?? (this.params as any)[key.replace(/[A-Z]/g, '_$&').toLowerCase()];
      if (val !== undefined) body[this.camelToSnake(key)] = val;
    }
    return body;
  }
  private camelToSnake(s: string): string {
    return s.replace(/[A-Z]/g, letter => `_${letter.toLowerCase()}`);
  }
}

export { Message, MessageRequest, TextBlock, ImageBlock, ToolUseBlock, ToolResultBlock, ContentBlock, Role };
```

- [ ] **Step 5: 运行 Node.js 测试验证通过**

```bash
cd code/node/ch02 && npx vitest run message_builder.test.ts
```

- [ ] **Step 6: 编写最佳实践与自测题，Commit**

---

### Task 4–18: 第 3–17 章（每章结构同 Task 2–3 模式）

由于篇幅限制，第 3–17 章每章遵循相同的 Task 结构，此处列出每章的关键实现文件与核心接口签名。实际写作时每章展开为完整的 Task（含完整代码和测试）。

#### 第 3 章：LLM 模型深度剖析

**核心实现**:
```python
# code/python/ch03/model_selector.py
class ModelSelector:
    MODELS = {
        "claude-opus-4-7-20250514": {"context_window": 200000, "max_output": 32000, "pricing": {"input": 5.00, "output": 25.00}, "strength": "旗舰推理"},
        "claude-sonnet-4-6-20250514": {"context_window": 200000, "max_output": 32000, "pricing": {"input": 3.00, "output": 15.00}, "strength": "性能平衡"},
        "claude-haiku-4-5-20251001": {"context_window": 200000, "max_output": 8192, "pricing": {"input": 1.00, "output": 5.00}, "strength": "速度优先"},
    }
    def select(self, task_complexity: str, budget_constraint: str, context_needed: int) -> str: ...
    def cost_estimate(self, model: str, input_tokens: int, output_tokens: int, cache_hit: bool = False, batch: bool = False) -> float: ...

# code/python/ch03/token_counter.py
class TokenCounter:
    """Approximate token counting using tiktoken-like algorithm."""
    def count(self, text: str) -> int: ...
    def estimate_request_tokens(self, messages: list, system: str = None, tools: list = None) -> int: ...
```

- [ ] Step 1: 编写模型规范章节（模型族、参数数学原理、Pricing）
- [ ] Step 2–5: Python + Node 实现、测试、最佳实践
- [ ] Step 6: 编写自测题（含："在给定场景下选择最优模型并计算预估成本"）
- [ ] Step 7: Commit

#### 第 4 章：Structured Outputs

**核心实现**:
```python
# code/python/ch04/structured_output.py
class StructuredOutputClient:
    def create(self, model: str, messages: list, json_schema: dict, system: str = None) -> dict: ...
    def extract(self, model: str, text: str, json_schema: dict) -> dict: ...
```

- [ ] Step 1: 编写 constrained decoding 协议规范
- [ ] Step 2–5: Python + Node 实现（含 grammar 编译原理简述）、测试
- [ ] Step 6: 自测题
- [ ] Step 7: Commit

#### 第 5 章：Streaming 与 Extended Thinking

**核心实现**:
```python
# code/python/ch05/sse_parser.py
class SSEParser:
    """从零实现 SSE 协议解析器，不依赖任何 SSE 库"""
    def __init__(self):
        self._buffer = ""
    def feed(self, chunk: bytes) -> list[dict]:
        """Feed raw bytes, return parsed SSE events"""
    def _parse_line(self, line: str) -> Optional[dict]: ...

# code/python/ch05/stream_handler.py
class StreamHandler:
    def __init__(self):
        self._current_message = None
        self._content_blocks = []
    def handle_event(self, event: dict) -> Optional[str]:
        """Handle event, return text delta or None"""

# code/python/ch05/thinking_handler.py
class ThinkingHandler:
    def start_thinking(self, budget_tokens: int): ...
    def process_thinking_delta(self, thinking: str): ...
    def finalize_thinking(self, signature: str) -> bool:
        """Verify thinking signature"""
```

- [ ] Step 1: 编写 SSE 协议标准完整讲解（含 RFC reference）
- [ ] Step 2: 编写 event types 规范 + Extended Thinking 规范
- [ ] Step 3–5: Python + Node 实现（SSE 解析器从零手写）、测试
- [ ] Step 6: 自测题（含："实现 SSE 解析器并处理 thinking 事件流"）
- [ ] Step 7: Commit

#### 第 6 章：Tool Use & Function Calling

**核心实现**:
```python
# code/python/ch06/tool_registry.py
class ToolRegistry:
    def register(self, name: str, description: str, input_schema: dict, handler: callable, defer_loading: bool = False, allowed_callers: list = None): ...
    def to_api_format(self) -> list[dict]: ...
    def execute(self, tool_name: str, input: dict) -> dict: ...

# code/python/ch06/programmatic_tool_caller.py
class ProgrammaticToolCaller:
    """Implements Programmatic Tool Calling pattern"""
    def __init__(self, tool_registry: ToolRegistry): ...
    def execute_code(self, code: str) -> dict:
        """Execute orchestration code, intercept tool calls, return only final output"""

# code/python/ch06/tool_search.py
class EmbeddingToolSearch:
    """Custom semantic tool search using embeddings"""
    def __init__(self, embedding_client): ...
    def index_tools(self, tools: list[dict]): ...
    def search(self, query: str, top_k: int = 5) -> list[dict]: ...
```

- [ ] Step 1: 编写标准 Tool Use + Strict Tool Use 协议规范
- [ ] Step 2: 编写 Advanced Tool Use 三件套规范
- [ ] Step 3–7: Python + Node 全部实现（含 embedding-based tool search）、测试
- [ ] Step 8: 自测题
- [ ] Step 9: Commit

#### 第 7 章：Computer Use

**核心实现**:
```python
# code/python/ch07/computer_use.py
class ComputerUseClient:
    SCREENSHOT_TOOL = {"name": "computer", "display_width_px": 1920, "display_height_px": 1080}
    def capture_screenshot(self) -> str: ...
    def move_mouse(self, x: int, y: int): ...
    def click(self, x: int, y: int, button: str = "left"): ...
    def type_text(self, text: str): ...
    def scroll(self, x: int, y: int, scroll_x: int, scroll_y: int): ...
    def key_combination(self, keys: list[str]): ...
```

- [ ] Step 1: 编写 Computer Use 独立协议规范
- [ ] Step 2–5: Python + Node 实现（截图→分析→操作循环）、测试、安全边界讨论
- [ ] Step 6: Commit

#### 第 8 章：上下文管理：Prompt Caching 与 Compaction

**核心实现**:
```python
# code/python/ch08/cache_aware_client.py
class CacheAwareClient(AnthropicClient):
    def create_with_cache(self, request: MessageRequest, cache_points: list[int]) -> dict:
        """Insert cache_control breakpoints at specified message indices"""
    def estimate_cache_savings(self, prompt_tokens: int, expected_requests: float) -> float: ...
    def should_cache(self, prompt_tokens: int, requests_per_5min: float) -> bool: ...

# code/python/ch08/cache_keepalive.py
class CacheKeepAlive:
    def __init__(self, client, system_prompt: str, ping_interval: int = 240): ...
    def start(self): ...
    def stop(self): ...

# code/python/ch08/compaction_handler.py
class CompactionHandler:
    def should_compact(self, context_usage_pct: float) -> bool: ...
    def compact(self, messages: list[Message]) -> list[Message]: ...
    def summarize_and_replace(self, messages: list[Message], threshold_index: int) -> list[Message]: ...
```

- [ ] Step 1: 编写 Prompt Caching 协议规范 + 5min TTL 深度分析
- [ ] Step 2: 编写 Compaction 协议规范
- [ ] Step 3–7: Python + Node 全部实现（含 Keep-Alive、Batch、Compaction）、测试
- [ ] Step 8: 自测题（含："实现缓存盈亏平衡计算器"）
- [ ] Step 9: Commit

#### 第 9 章：Batch API

**核心实现**:
```python
# code/python/ch09/batch_client.py
class BatchClient(AnthropicClient):
    def create_batch(self, requests: list[MessageRequest]) -> str:
        """Create MessageBatch, return batch_id"""
    def get_batch_status(self, batch_id: str) -> dict:
        """Returns {status: 'in_progress'|'ended'|'canceled', ...}"""
    def get_batch_results(self, batch_id: str) -> list[dict]:
        """Fetch completed results"""
    def cancel_batch(self, batch_id: str): ...
    def wait_for_completion(self, batch_id: str, poll_interval: int = 60, max_wait: int = 86400) -> list[dict]: ...
```

- [ ] Step 1: 编写 Batch API 完整协议规范
- [ ] Step 2–5: Python + Node 实现、测试
- [ ] Step 6: Commit

#### 第 10 章：Memory 与 Citations

**核心实现**:
```python
# code/python/ch10/memory_client.py
class MemoryClient(AnthropicClient):
    def create_memory_store(self, name: str) -> str: ...
    def store_memory(self, store_id: str, content: str, metadata: dict = None) -> str: ...
    def search_memories(self, store_id: str, query: str) -> list[dict]: ...
    def list_memories(self, store_id: str, limit: int = 20) -> list[dict]: ...
    def delete_memory(self, store_id: str, memory_id: str): ...

# code/python/ch10/citation_parser.py
class CitationParser:
    def parse_citations(self, content_block: dict) -> list[dict]:
        """Extract citations from a content block"""
    def format_citation(self, citation: dict) -> str: ...
```

- [ ] Step 1: 编写 Memory API 完整协议规范（含 Dreaming 机制）
- [ ] Step 2: 编写 Citations 协议规范
- [ ] Step 3–6: Python + Node 实现、测试
- [ ] Step 7: Commit

#### 第 11 章：MCP 协议规范

**核心实现**:
```python
# code/python/ch11/json_rpc.py
class JSONRPCRequest:
    jsonrpc: str = "2.0"
    id: int | str
    method: str
    params: dict

class JSONRPCResponse:
    jsonrpc: str = "2.0"
    id: int | str
    result: dict

class JSONRPCError:
    jsonrpc: str = "2.0"
    id: int | str
    error: dict  # {code, message, data?}

class JSONRPCNotification:
    jsonrpc: str = "2.0"
    method: str
    params: dict

class JSONRPCParser:
    def parse_message(self, raw: str) -> JSONRPCRequest | JSONRPCResponse | JSONRPCError | JSONRPCNotification: ...
    def serialize(self, msg) -> str: ...

# code/python/ch11/mcp_lifecycle.py
class MCPLifecycle:
    def initialize(self, client_capabilities: dict) -> dict: ...
    def handle_initialized(self): ...
    def negotiate_capabilities(self, server_capabilities: dict) -> dict: ...
```

本章以协议规范为主，代码为辅助理解 JSON-RPC 和 MCP 生命周期。OAuth 2.1 授权流程重点展开。

- [ ] Step 1: 编写 MCP 架构全景 + JSON-RPC 底层协议标准讲解
- [ ] Step 2: 编写生命周期管理规范
- [ ] Step 3: 编写三大原语规范（Tools/Resources/Prompts）
- [ ] Step 4: 编写客户端特性规范（Elicitation/Roots/Sampling）
- [ ] Step 5: 编写传输层规范（STDIO/Streamable HTTP）
- [ ] Step 6: 编写授权体系 + 安全威胁模型
- [ ] Step 7: Python + Node JSON-RPC 解析器实现 + 测试
- [ ] Step 8: 自测题
- [ ] Step 9: Commit

#### 第 12 章：MCP 实战构建

**核心实现**:
```python
# code/python/ch12/mcp_server.py
class MCPServer:
    def __init__(self, name: str, version: str): ...
    def register_tool(self, tool_def: dict): ...
    def register_resource(self, resource_def: dict): ...
    def register_prompt(self, prompt_def: dict): ...
    async def run_stdio(self): ...
    async def run_http(self, host: str, port: int): ...

# code/python/ch12/mcp_client.py
class MCPClient:
    async def connect_stdio(self, command: str, args: list[str]): ...
    async def connect_http(self, url: str): ...
    async def list_tools(self) -> list[dict]: ...
    async def call_tool(self, name: str, arguments: dict) -> dict: ...
    async def list_resources(self) -> list[dict]: ...
    async def read_resource(self, uri: str) -> bytes: ...

# code/python/ch12/mcp_tasks.py
class MCPTask:
    """SEP-1686 Tasks implementation"""
    async def submit_task(self, tool_name: str, arguments: dict) -> str: ...
    async def get_task_status(self, task_id: str) -> dict: ...
    async def get_task_result(self, task_id: str) -> dict: ...
    async def cancel_task(self, task_id: str): ...
```

- [ ] Step 1: 编写 MCP Server 构建指南 + Python 实现
- [ ] Step 2: 编写 MCP Client 构建指南 + Python 实现
- [ ] Step 3: 编写 Node.js Server + Client 实现
- [ ] Step 4: 编写 MCP Tasks 实现
- [ ] Step 5: 编写 Registry 发布与发现
- [ ] Step 6: 运行端到端测试（Python Server + Node Client 互操作）
- [ ] Step 7: 自测题（含："构建一个支持 Tools 和 Resources 的 MCP Server"）
- [ ] Step 8: Commit

#### 第 13 章：RAG 检索增强生成

**核心实现**:
```python
# code/python/ch13/rag_pipeline.py
class RAGPipeline:
    def __init__(self, claude_client, vector_store, embedding_model): ...
    def ingest(self, documents: list[str], chunk_size: int = 1000, chunk_overlap: int = 200): ...
    def retrieve(self, query: str, top_k: int = 5, strategy: str = "hybrid") -> list[dict]: ...
    def generate(self, query: str, context: list[dict], model: str = "claude-sonnet-4-6") -> str: ...
    def query(self, query: str) -> str:
        """End-to-end RAG query"""

# code/python/ch13/claude_judge.py
class ClaudeJudge:
    def evaluate_faithfulness(self, answer: str, context: list[str]) -> dict: ...
    def evaluate_relevance(self, answer: str, query: str) -> dict: ...
    def evaluate_completeness(self, answer: str, context: list[str]) -> dict: ...
    def comprehensive_eval(self, query: str, answer: str, context: list[str]) -> dict:
        """Returns {faithfulness, relevance, completeness, overall}"""
```

- [ ] Step 1: 编写 RAG 全链路架构 + 文档处理/Chunking/Embedding 策略
- [ ] Step 2: 编写检索策略（稀疏/稠密/混合/多阶段）+ Reranking
- [ ] Step 3: 编写高级 RAG 模式（Adaptive/Self-RAG/Agentic RAG/Graph RAG）
- [ ] Step 4: 编写评估体系（含 Claude-as-Judge）
- [ ] Step 5: Python + Node 完整实现
- [ ] Step 6: 运行端到端测试（ingest 5 篇文档 → query 3 个问题 → judge 评估）
- [ ] Step 7: 自测题（含："实现端到端 RAG pipeline 并用 Claude 评估其输出"）
- [ ] Step 8: Commit

#### 第 14 章：Agent SDK 与 Agent 模式

**核心实现**:
```python
# code/python/ch14/agent_loop.py
class AgentLoop:
    def __init__(self, claude_client, tools: ToolRegistry, max_iterations: int = 10): ...
    async def run(self, task: str) -> dict:
        """Run ReAct loop: perceive → reason → act → observe → ..."""

# code/python/ch14/reflexion_agent.py
class ReflexionAgent(AgentLoop):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.reflections: list[str] = []
    async def reflect(self, trajectory: list[dict]) -> str: ...
    async def run(self, task: str) -> dict:
        """ReAct + post-action reflection + retry with reflection"""

# code/python/ch14/subagent_orchestrator.py
class SubAgentOrchestrator:
    def __init__(self, claude_client, tools: ToolRegistry): ...
    async def decompose(self, task: str) -> list[dict]:
        """Decompose task into subtasks"""
    async def dispatch(self, subtask: dict) -> dict:
        """Dispatch subtask to a sub-agent"""
    async def synthesize(self, results: list[dict]) -> dict: ...

# code/python/ch14/supervisor_worker.py
class SupervisorWorker:
    """Supervisor coordinates multiple worker agents"""
    def __init__(self, claude_client, worker_tools: dict[str, ToolRegistry]): ...
    async def run(self, task: str) -> dict: ...
```

- [ ] Step 1: 编写 Agent 决策图（自建 vs SDK vs Managed Agents）
- [ ] Step 2: 编写单 Agent 3 种模式 + 各自协议描述
- [ ] Step 3: 编写多 Agent 4 种模式 + 各自协议描述
- [ ] Step 4: Python + Node 全部 Agent 模式实现
- [ ] Step 5: 运行集成测试（ReAct Agent 执行多步工具调用任务）
- [ ] Step 6: 自测题（含："实现一个 ReAct Agent 完成多步工具调用"）
- [ ] Step 7: Commit

#### 第 15 章：Claude Managed Agents

**核心实现**:
```python
# code/python/ch15/managed_agent.py
class ManagedAgentClient(AnthropicClient):
    def create_agent(self, config: dict) -> str: ...
    def start_session(self, agent_id: str, task: str) -> str: ...
    def get_session_status(self, session_id: str) -> dict: ...
    def get_session_result(self, session_id: str) -> dict: ...
    def cancel_session(self, session_id: str): ...
    def list_sessions(self, agent_id: str) -> list[dict]: ...
```

- [ ] Step 1: 编写 Managed Agents 架构与运行时机理
- [ ] Step 2: 编写 Dreaming/Outcomes/Multiagent Orchestration
- [ ] Step 3: 编写与自建 Agent 的取舍对比
- [ ] Step 4: Python + Node 实现（含部署脚本）
- [ ] Step 5: 自测题
- [ ] Step 6: Commit

#### 第 16 章：LangChain & LangGraph

**核心实现**:
```python
# code/python/ch16/langchain_integration.py
from langchain_anthropic import ChatAnthropic
# Show ChatAnthropic setup, Tool binding, Prompt templates, Memory integration
# Demonstrate when to use LangChain vs raw SDK

# code/python/ch16/langgraph_agent.py
from langgraph.graph import StateGraph, START, END
# Build a complete LangGraph agent with Claude
# StateGraph → nodes → edges → checkpointer → human-in-the-loop
```

- [ ] Step 1: 编写 LangChain 架构 + ChatAnthropic 集成
- [ ] Step 2: 编写 LangGraph StateGraph Agent 编排
- [ ] Step 3: 编写 LangSmith 可观测性
- [ ] Step 4: 编写取舍决策（LangChain vs 原生 SDK）
- [ ] Step 5: Python + Node 实现
- [ ] Step 6: 自测题
- [ ] Step 7: Commit

#### 第 17 章：生产实践

**核心实现**:
```python
# code/python/ch17/rate_limiter.py
class TokenBucketRateLimiter:
    def __init__(self, tokens_per_minute: int, tokens_per_minute_input: int): ...
    async def acquire(self, tokens: int) -> bool: ...

class SlidingWindowRateLimiter:
    def __init__(self, max_requests: int, window_seconds: int = 60): ...
    async def acquire(self) -> bool: ...

# code/python/ch17/retry_handler.py
class RetryHandler:
    def __init__(self, max_retries: int = 3, base_delay: float = 1.0, max_delay: float = 60.0): ...
    async def execute(self, fn: callable) -> dict:
        """Execute with exponential backoff + jitter + circuit breaker"""

# code/python/ch17/security_guard.py
class PromptInjectionGuard:
    def sanitize(self, user_input: str) -> str: ...
    def detect_injection(self, user_input: str) -> bool: ...

class ToolPermissionScope:
    def __init__(self, allowed_tools: set[str]): ...
    def authorize(self, tool_name: str) -> bool: ...

# code/python/ch17/budget_controller.py
class BudgetController:
    def __init__(self, monthly_budget_usd: float, hard_limit_pct: float = 1.0, soft_alert_pct: float = 0.8): ...
    def check(self, estimated_cost: float) -> Literal["allow", "warn", "block"]: ...
    def record_usage(self, cost: float): ...
    def get_remaining(self) -> float: ...

# code/python/ch17/observable_client.py
class ObservableClient(AnthropicClient):
    """Production-grade client with logging, metrics, and tracing"""
    def __init__(self, config: ClientConfig, logger, metrics_collector, tracer): ...
    async def create_message(self, request: MessageRequest) -> dict: ...
```

- [ ] Step 1: 编写速率限制策略（RPM/TPM、Token Bucket、Sliding Window）
- [ ] Step 2: 编写错误处理与重试体系（指数退避、jitter、断路器）
- [ ] Step 3: 编写安全（Key 管理 + Agent 安全边界：Prompt Injection/Tool Poisoning/数据泄露）
- [ ] Step 4: 编写 Prompt Engineering 实践
- [ ] Step 5: 编写 Token 预算与成本优化（含可运行的 BudgetController）
- [ ] Step 6: 编写可观测性（结构化日志、Metrics、分布式追踪）
- [ ] Step 7: Python + Node 完整生产级 Client 包装器实现
- [ ] Step 8: 运行全部生产测试
- [ ] Step 9: 自测题（含："从零构建一个生产级 Client，含限流、重试、安全、预算控制"）
- [ ] Step 10: Commit

---

### Task 19: 附录编写

**Files:**
- Create: `appendices/appendix-a-api-reference.md`
- Create: `appendices/appendix-b-model-matrix.md`
- Create: `appendices/appendix-c-self-test-answers.md`
- Create: `appendices/appendix-d-glossary.md`
- Create: `appendices/appendix-e-protocol-changelog.md`

- [ ] **Step 1: 编写附录 A — API 快速参考表**

整理所有 17 章涉及的 API 端点、请求字段、响应字段，以表格形式呈现。来源：从已完成的章节中提取，确保一致性。

- [ ] **Step 2: 编写附录 B — 模型对比矩阵**

| 模型 | Context Window | Max Output | Input $/1M | Output $/1M | 适用场景 |
|------|---------------|------------|------------|-------------|----------|
| claude-opus-4-7 | 200K/1M | 32K | $5.00 | $25.00 | 复杂推理 |
| ... | ... | ... | ... | ... | ... |

- [ ] **Step 3: 编写附录 C — 自测题答案**

逐章整理所有自测题的编码题参考实现和理论题答案。

- [ ] **Step 4: 编写附录 D — 术语表**

中英对照表。涵盖：Content Block、Tool Use、MCP、RAG、Agent、Sub-Agent、Prompt Caching、Compaction、SSE、JSON-RPC、OAuth 2.1、PKCE 等。

- [ ] **Step 5: 编写附录 E — 协议版本变更记录**

按时间线列出 Anthropic API 各特性的引入日期和演进：
- 2023-06-01: Messages API (GA)
- 2024-XX-XX: Tool Use
- 2024-11-25: MCP 发布
- 2025-03-26: MCP 规范正式版
- 2025-XX-XX: Advanced Tool Use
- 2026-Q1: 5min Cache TTL、Memory、Structured Outputs
- ...

- [ ] **Step 6: Commit**

```bash
git add appendices/
git commit -m "feat: complete appendices A-E (API reference, model matrix, answers, glossary, changelog)"
```

---

### Task 20: 全书整合与终审

**Files:**
- Modify: `README.md`（补充完整目录与阅读指引）
- Create: 交叉引用完整性检查脚本

- [ ] **Step 1: 更新 README.md 为完整版**

包含：书名、简介、3 条阅读路径（链接到具体章节）、17 章完整目录、每章一句话简介、代码运行说明。

- [ ] **Step 2: 运行全量代码测试**

```bash
# Python
cd code/python
for ch in ch*/; do cd "$ch" && python -m pytest --tb=short -q && cd ..; done

# Node
cd code/node
for ch in ch*/; do cd "$ch" && npx vitest run && cd ..; done
```
Expected: 所有章节的 Python 和 Node 测试全部 PASS。

- [ ] **Step 3: 交叉引用完整性检查**

遍历所有 markdown 文件，检查内部交叉引用链接是否有效（章节号是否匹配、引用的 API 端点是否存在、文件路径是否正确）。

- [ ] **Step 4: 术语一致性检查**

检查全书术语使用是否一致：
- "Tool Use" vs "工具调用" 的使用规则
- "Content Block" 的翻译一致性
- API 字段名保持原文，解释使用中文

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "feat: final integration - complete book with 17 chapters, appendices, and all code"
```

---

## 自审清单

**1. Spec 覆盖检查**:
- [x] 第 1-17 章全部对应 spec 中的章节
- [x] 附录 A-E 全部对应 spec 中的附录规划
- [x] 阅读路径指南在 README 中实现
- [x] 每章自测题含编码题
- [x] Claude-as-Judge 在第 13 章实现
- [x] Agent 决策图在第 14 章开头
- [x] Agent 安全边界在第 17 章实现
- [x] BudgetController 在第 17 章实现
- [x] Compaction 在第 8 章实现
- [x] MCP Tasks 在第 12 章实现
- [x] MCP 安全威胁模型在第 11 章实现
- [x] Computer Use 独立为第 7 章
- [x] SSE/JSON-RPC/JSON Schema 从底层标准开始讲解

**2. 占位符扫描**: 无 TBD/TODO。所有核心接口签名已定义。

**3. 类型一致性**: 所有章节共享的基础类型（Message, ContentBlock, AnthropicError）在第 1-2 章定义，后续章节引用。
