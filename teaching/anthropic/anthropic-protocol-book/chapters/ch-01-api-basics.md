# 第 1 章：Anthropic API 基础

> **本章目标**：建立与 Anthropic API 通信所需的所有基础设施。完成本章后，你将拥有一个不依赖官方 SDK、完全可运行的 HTTP 客户端，能够发送消息、处理错误、管理身份验证，并妥善处理速率限制。

---

## 1.1 概念全景

### Anthropic API 在生态系统中的位置

Anthropic API 是访问 Claude 系列大语言模型的 HTTP 接口。与许多开发者熟悉的 OpenAI API 类似，它遵循 RESTful 设计，使用 JSON 作为数据交换格式，通过 HTTPS 传输。但 Anthropic API 在多个关键设计决策上与 OpenAI API 存在显著差异，这些差异反映了 Anthropic 对安全性、可控性和可解释性的不同哲学。

Anthropic 将 Claude 定位为"有用、诚实、无害"的 AI 助手。这一理念直接体现在 API 设计中：

- **Content Blocks 抽象模型**：与 OpenAI 的消息数组不同，Anthropic 引入了结构化的 Content Block 概念。每条消息由多个内容块组成，每个块可以是文本、图像、工具调用或工具结果。这种统一抽象使得多模态交互和工具使用不再是"附加功能"，而是协议的一等公民。

- **显式的工具使用模型**：Anthropic 的 tool_use 不是通过函数调用参数隐式触发的。模型返回一个明确标记为 `tool_use` 的内容块，客户端处理后将结果以 `tool_result` 块返回。这种显式设计让工具调用的每一步都可追踪、可调试。

- **严格的内容类型约束**：每个 Content Block 都有明确的 `type` 字段。API 拒绝接受类型不明确或结构不规范的数据，减少了因输入格式错误导致的意外行为。

- **分层错误系统**：Anthropic 的错误类型系统比 OpenAI 更细粒度。`overloaded_error`（529）明确区分了服务器过载和通用服务器错误，让客户端能够做出更精准的重试决策。

以下是对比表，帮助熟悉 OpenAI API 的开发者快速建立映射：

| 概念 | Anthropic API | OpenAI API |
|------|---------------|------------|
| 消息结构 | Content Blocks 数组 | 扁平 message 对象 |
| 工具调用 | `tool_use` + `tool_result` Content Blocks | `function_call` + `function` role |
| 流式事件 | Server-Sent Events (`content_block_start`, `content_block_delta`, `content_block_stop`) | Server-Sent Events (`choices[0].delta`) |
| 系统提示 | 顶层 `system` 参数（字符串或 Content Block 数组） | `messages` 数组中 `system` role |
| 速率限制头 | `retry-after`, `anthropic-ratelimit-*` 系列头 | `x-ratelimit-*` 系列头 |
| 停止原因 | `end_turn`, `max_tokens`, `stop_sequence`, `tool_use` | `stop`, `length`, `tool_calls`, `content_filter` |
| 流式用法头 | `x-stainless-*` | `x-request-id` |

### 本章学习成果

完成本章的学习和编码练习后，你将能够：

1. 在不依赖 `anthropic` Python SDK 或 `@anthropic-ai/sdk` npm 包的情况下，使用自己编写的 HTTP 客户端调用 Anthropic Messages API。
2. 正确区分并处理 8 种 API 错误类型，针对不同错误采取合适的恢复策略。
3. 实现多 Key 轮转机制，在生产环境中安全地管理 API 密钥。
4. 为客户端添加指数退避重试逻辑，处理速率限制和临时性服务器错误。

本章构建的客户端将是后续所有章节的基础设施。第 2 章的多模态交互、第 5 章的流式处理、第 6 章的工具调用，都将在此基础上扩展。

---

## 1.2 协议规范逐层拆解

### 1.2.1 身份验证（Authentication）

Anthropic API 支持两种身份验证方式：

**方式一：`x-api-key` 头（推荐）**

这是 Anthropic 官方 SDK 使用的方式。将 API Key 直接放入自定义 HTTP 头：

```http
x-api-key: sk-ant-api03-xxxxxxxxxxxxx
```

`x-api-key` 的语义清晰——它只用于 Anthropic API，不会被其他遵循 Bearer 规范的服务误解析。此外，某些 HTTP 中间件和日志系统默认会遮蔽 `x-api-key` 头的内容，降低了密钥泄漏的风险。

**方式二：Bearer Token**

标准的 HTTP Bearer 身份验证：

```http
Authorization: Bearer sk-ant-api03-xxxxxxxxxxxxx
```

这种方式兼容标准的 API 网关和 OAuth 中间件，适合需要统一认证层的架构。但需要注意：Bearer Token 在 HTTP 规范中具有通用语义——某些代理和网关可能在不知情的情况下将其转发到非预期的上游服务。

**方式三：多 Key 轮转**

生产环境中，不应依赖单一 API Key。多 Key 轮转策略可以：

- **突破速率限制**：不同 Key 对应不同的 RPM/TPM 配额，轮转可以聚合多个 Key 的配额。
- **实现平滑切换**：当一个 Key 需要轮换时，新 Key 可以提前加入轮转池，旧 Key 在确认新 Key 可用后再移除。
- **隔离故障**：某个 Key 因欠费或违规被禁用时，其他 Key 继续工作。

多 Key 轮转的具体实现在本章第 1.5 节详细介绍。

### 1.2.2 Base URL 与端点结构

Anthropic API 的基础 URL 为：

```
https://api.anthropic.com/v1/messages
```

所有消息相关的操作都通过这个单一端点完成。与 OpenAI 的 `/v1/chat/completions` 不同，Anthropic 没有为不同功能（对话、补全、编辑）创建不同的端点路径，而是通过 Content Block 的类型系统在同一个端点上支持文本、图像、工具调用等多种交互模式。

**版本控制**：Anthropic 使用 `anthropic-version` 请求头来指定 API 版本，而非将版本号嵌入 URL 路径。当前推荐版本为 `2023-06-01`。

```http
anthropic-version: 2023-06-01
```

这种设计的好处是 URL 保持稳定，客户端可以通过单个头字段控制行为兼容性。

### 1.2.3 请求/响应格式

**请求格式**

所有请求使用 HTTP POST 方法，Content-Type 必须为 `application/json`。一个典型的请求体结构如下：

```json
{
  "model": "claude-sonnet-4-20250514",
  "max_tokens": 1024,
  "system": "You are a helpful assistant.",
  "messages": [
    {
      "role": "user",
      "content": [
        {"type": "text", "text": "Hello, Claude."}
      ]
    }
  ]
}
```

关键设计点：

- `messages` 是消息数组，每个消息有 `role`（`user` 或 `assistant`）和 `content`（Content Block 数组）。
- `content` 始终是数组——即使只有一段纯文本，也必须包装在 Content Block 数组中。
- `system` 是顶层参数，不是 `messages` 数组的一部分。这保证了系统提示不会被对话历史中的其他内容污染。
- `max_tokens` 是必填参数，没有默认值。这是 Anthropic 有意为之的设计——强制开发者显式控制成本上限。

**响应格式**

成功响应（200）的典型结构：

```json
{
  "id": "msg_01Xxxxxxxxxxxxx",
  "type": "message",
  "role": "assistant",
  "content": [
    {"type": "text", "text": "Hello! How can I help you today?"}
  ],
  "model": "claude-sonnet-4-20250514",
  "stop_reason": "end_turn",
  "stop_sequence": null,
  "usage": {
    "input_tokens": 10,
    "output_tokens": 25
  }
}
```

`stop_reason` 的四种可能值：

| stop_reason | 含义 |
|-------------|------|
| `end_turn` | 模型自然结束回复 |
| `max_tokens` | 达到 `max_tokens` 限制 |
| `stop_sequence` | 遇到自定义停止序列 |
| `tool_use` | 模型请求调用工具 |

### 1.2.4 Content Blocks 概念

Content Block 是 Anthropic API 最核心的抽象。在 Anthropic 的世界里，消息不是一个字符串，而是一个有序的内容块列表。每个内容块有明确的类型和结构。

**请求中的 Content Block 类型：**

| 类型 | 用途 | 结构示例 |
|------|------|---------|
| `text` | 纯文本内容 | `{"type": "text", "text": "..."}` |
| `image` | Base64 编码的图像 | `{"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": "..."}}` |
| `tool_use` | 助手发出的工具调用请求 | `{"type": "tool_use", "id": "toolu_...", "name": "...", "input": {...}}` |
| `tool_result` | 用户返回的工具执行结果 | `{"type": "tool_result", "tool_use_id": "toolu_...", "content": "..."}` |

**响应中的 Content Block 类型：**

响应中的 Content Block 除了上述类型外，还可能包含 `thinking` 类型（扩展思考内容）和 `redacted_thinking` 类型（因安全原因被隐藏的思考内容）。

**为什么使用 Content Block 模型？**

这种设计解决了扁平消息模型中的几个固有问题：

1. **多模态混合**：一条消息可以同时包含文本和图像，且顺序由开发者精确控制。
2. **工具调用状态追踪**：`tool_use` 和 `tool_result` 通过 `tool_use_id` 配对，形成完整的调用链。每一步都是显式的、可审计的。
3. **流式增量更新**：流式响应按 Content Block 组织事件（`content_block_start`、`content_block_delta`、`content_block_stop`），客户端可以精确知道当前正在接收哪个块的哪一部分。

### 1.2.5 错误码系统

Anthropic API 使用标准 HTTP 状态码配合结构化的错误响应体。错误响应体格式如下：

```json
{
  "type": "error",
  "error": {
    "type": "authentication_error",
    "message": "invalid x-api-key"
  }
}
```

**错误响应体字段说明：**

| 字段 | 类型 | 必填 | 描述 |
|------|------|------|------|
| `type` | `string` | 是 | 固定值 `"error"` |
| `error` | `object` | 是 | 错误详情对象 |
| `error.type` | `string` | 是 | 错误类型，见下表 |
| `error.message` | `string` | 是 | 人类可读的错误描述 |

**完整的错误类型分类：**

| HTTP 状态码 | 错误类型 | 触发场景 | 重试策略 |
|------------|---------|---------|---------|
| 400 | `invalid_request_error` | 请求体格式错误、缺少必填字段、参数值不合法 | 不重试——修复请求后重发 |
| 401 | `authentication_error` | API Key 无效、过期或缺失 | 不重试——检查 Key 是否正确 |
| 403 | `permission_error` | API Key 无权访问请求的资源或模型 | 不重试——检查权限配置 |
| 404 | `not_found_error` | 请求的资源不存在（如模型名称错误） | 不重试——检查资源标识符 |
| 413 | `request_too_large` | 请求体超过大小限制（Messages: 32MB, Batch: 256MB） | 不重试——压缩或分割请求 |
| 429 | `rate_limit_error` | 超过 RPM/TPM 限制 | 重试——使用 `Retry-After` + 指数退避 |
| 500 | `api_error` | Anthropic 内部服务器错误 | 重试——指数退避 |
| 529 | `overloaded_error` | Anthropic 服务过载 | 重试——使用 `Retry-After` + 更长退避 |

**4xx vs 5xx 的根本区别：**

- **4xx 错误**：问题出在客户端。无论重试多少次，结果都不会改变。修复请求本身才是正确的解决方案。
- **5xx 错误**：问题出在服务端。这些错误通常是暂时的，重试（配合适当的退避策略）是合理的恢复手段。

### 1.2.6 速率限制（Rate Limits）

Anthropic 使用多层速率限制体系：

**RPM（Requests Per Minute）**

每分钟允许的 API 请求数量。当超过 RPM 限制时，API 返回 429 状态码，响应头包含：

```http
retry-after: 30
```

**TPM（Tokens Per Minute）**

每分钟允许处理的 Token 总数（输入 Token + 输出 Token）。TPM 限制与具体模型绑定，不同模型有不同的 TPM 配额。

**Usage Tier 系统**

Anthropic 根据用户的消费历史和使用量自动划分 Tier 等级。更高的 Tier 享有更高的 RPM/TPM 限制。Tier 从 1 到 5 逐级提升：

| Tier | 月消费门槛 | 典型 RPM 限制 | 适用场景 |
|------|-----------|-------------|---------|
| 1 | 初始（$0） | 较低 | 开发与测试 |
| 2 | $50+ | 中等 | 个人项目 |
| 3 | $200+ | 较高 | 小团队产品 |
| 4 | $500+ | 高 | 商业应用 |
| 5 | $1,000+ | 最高 | 大规模生产 |

**速率限制响应头**

当接近或超过限制时，Anthropic 返回以下响应头：

| 响应头 | 描述 |
|--------|------|
| `retry-after` | 建议等待的秒数（429 时） |
| `anthropic-ratelimit-requests-limit` | RPM 上限 |
| `anthropic-ratelimit-requests-remaining` | 当前窗口剩余请求数 |
| `anthropic-ratelimit-requests-reset` | RPM 计数器重置时间（ISO 8601） |
| `anthropic-ratelimit-tokens-limit` | TPM 上限 |
| `anthropic-ratelimit-tokens-remaining` | 当前窗口剩余 Token 数 |
| `anthropic-ratelimit-tokens-reset` | TPM 计数器重置时间（ISO 8601） |

### 1.2.7 API Key 安全

API Key 安全不是可选的——它是整个系统安全的基础。以下是分层防御策略：

**第一层：环境变量**

永远不要将 API Key 硬编码在源代码中。使用环境变量隔离敏感信息：

```bash
export ANTHROPIC_API_KEY="sk-ant-api03-xxxxxxxxxxxxx"
```

环境变量的好处：
- 不会意外提交到版本控制系统（前提是 `.env` 文件在 `.gitignore` 中）
- 可以在不同环境（开发、测试、生产）中使用不同的 Key
- 容器化和 CI/CD 系统原生支持环境变量注入

**第二层：Secret Manager**

对于生产环境，使用云平台的密钥管理服务：

- **AWS**: Secrets Manager 或 Parameter Store
- **GCP**: Secret Manager
- **Azure**: Key Vault
- **HashiCorp Vault**: 跨平台密钥管理

Secret Manager 提供：
- 密钥加密存储
- 审计日志（谁、何时访问了密钥）
- 自动轮换
- 精细的访问控制（IAM 策略）

**第三层：Key 轮换**

定期轮换 API Key 是最佳实践。具体轮换策略见第 1.5 节。

---

## 1.3 Python 实现

本节实现的完整代码文件位于 `code/python/ch01/client.py` 和 `code/python/ch01/test_client.py`。

### 设计决策

在编写代码之前，我们明确几个设计决策：

1. **使用 httpx**：httpx 是 Python 生态中优秀的 HTTP 客户端，支持 HTTP/2、连接池、超时控制，并提供了近乎一致的同步和异步 API。

2. **AuthMethod 枚举**：支持 `x-api-key` 和 `Bearer` 两种认证方式，通过枚举类型区分，避免字符串拼写错误。

3. **AnthropicError 异常类**：所有 API 错误通过统一的异常类型抛出，携带 `status_code` 和 `error_type`，方便上层区分处理策略。

4. **ClientConfig 配置类**：使用 dataclass 集中管理所有配置参数，避免构造函数参数爆炸。

5. **同步和异步双模**：`AnthropicClient` 处理同步调用，`AsyncAnthropicClient` 处理异步调用，两者共享相同的错误处理和请求构建逻辑。

---

## 1.4 Node.js 实现

本节实现的完整代码文件位于 `code/node/ch01/AnthropicClient.ts` 和 `code/node/ch01/client.test.ts`。

Node.js 实现与 Python 版本在功能上完全等价，但充分利用了 TypeScript 的类型系统和 Node.js 22 的原生 `fetch` API。

### 设计决策

1. **使用原生 fetch**：Node.js 22 原生支持的全局 `fetch` 消除了对 `node-fetch` 或 `axios` 的依赖，减少外部依赖数。

2. **TypeScript 严格模式**：所有类型在编译时检查，杜绝 `any` 的使用。

3. **Result 类型模式**：`success` 响应和 `error` 响应通过判别联合类型（Discriminated Union）精确建模。

---

## 1.5 最佳实践与常见陷阱

### 1.5.1 API Key 轮换策略

生产环境中，API Key 不应该像密码一样"设置后就忘记"。以下是推荐的平滑轮换流程：

**双 Key 平滑切换模式**

核心思想：在新 Key 生效前，保持旧 Key 可用，确保零停机切换。

```python
import os
import time
from itertools import cycle

class DualKeyRotator:
    """双 Key 平滑轮换器。

    始终保持两个 Key 可用：一个 primary，一个 secondary。
    切换时先添加新 Key，验证可用后再移除旧 Key。
    """

    def __init__(self):
        primary = os.environ["ANTHROPIC_API_KEY"]
        secondary = os.environ.get("ANTHROPIC_API_KEY_SECONDARY")
        self._keys = [primary]
        if secondary:
            self._keys.append(secondary)
        self._cycle = cycle(self._keys)
        self._failed_keys: set[str] = set()

    def next_key(self) -> str:
        """获取下一个可用 Key，自动跳过已标记为失败的 Key。"""
        for _ in range(len(self._keys)):
            key = next(self._cycle)
            if key not in self._failed_keys:
                return key
        raise RuntimeError("All API keys have failed")

    def mark_failed(self, key: str) -> None:
        """标记 Key 为不可用（收到 401 时调用）。"""
        self._failed_keys.add(key)

    def add_key(self, key: str) -> None:
        """添加新 Key 到轮转池。"""
        if key not in self._keys:
            self._keys.append(key)
            self._cycle = cycle(self._keys)

    def remove_key(self, key: str) -> None:
        """从轮转池中移除 Key。"""
        self._keys = [k for k in self._keys if k != key]
        self._failed_keys.discard(key)
        self._cycle = cycle(self._keys)

    def _verify_key(self, key: str, client: "AnthropicClient") -> bool:
        """验证 Key 是否可用——发送一个轻量请求。"""
        try:
            client.post(
                messages=[{"role": "user", "content": [{"type": "text", "text": "ping"}]}],
                model="claude-sonnet-4-20250514",
                max_tokens=1,
                api_key=key,
            )
            return True
        except Exception:
            return False
```

轮换流程：

1. 在 Anthropic Console 生成新 Key。
2. 将新 Key 设为 `ANTHROPIC_API_KEY_SECONDARY` 环境变量。
3. 部署后，客户端自动将新 Key 加入轮转池。
4. 观察一段时间（如 1 小时），确认新 Key 稳定工作。
5. 移除旧 Key 环境变量，再次部署。

### 1.5.2 反模式：硬编码 API Key

**错误示范**（永远不要这样做）：

```python
# 反模式：API Key 硬编码在源码中
client = AnthropicClient(api_key="sk-ant-api03-xxxxxxxxxxxxx")
```

为什么这是灾难性的：
- `git push` 后 Key 永久暴露在仓库历史中。
- 即使后续提交删除了 Key，Git 历史仍可被任何人检索。
- 自动化扫描工具（如 GitHub Secret Scanning）会标记你的仓库。
- 如果仓库被设置为公开，Key 可能在几分钟内被滥用。

**正确做法**：

```python
import os

# 从环境变量读取，代码本身不包含敏感信息
api_key = os.environ["ANTHROPIC_API_KEY"]
client = AnthropicClient(api_key=api_key)
```

如果环境变量不存在，`os.environ["ANTHROPIC_API_KEY"]` 会抛出 `KeyError` 并提供清晰的错误信息——这比静默地使用一个空字符串或占位符安全得多。

### 1.5.3 区分 4xx 和 5xx 的重试策略

这是一个常见的混淆点。通用规则：

| 错误类别 | 含义 | 重试？ | 原因 |
|---------|------|--------|------|
| 4xx（除 429） | 客户端错误 | 否 | 同样请求会得到同样错误 |
| 429 | 速率限制 | 是 | 等待后配额恢复 |
| 5xx | 服务端错误 | 是 | 临时故障，重试可能成功 |

**4xx 重试为什么是错的？**

想象一个 401 错误：你的 API Key 是无效的。无论重试多少次，这个 Key 都不会突然变有效。重试只是在浪费你的配额（有些 API 仍会对 401 请求计数）、浪费服务器资源，并延迟你的应用发现真正的问题。

**429 的特殊处理**

429 错误是 4xx 中唯一应该重试的。处理 429 时，优先使用响应中的 `Retry-After` 头：

```python
def _get_retry_delay(self, response) -> float:
    retry_after = response.headers.get("retry-after")
    if retry_after is not None:
        return float(retry_after)
    # 如果服务端没有提供 Retry-After，使用默认退避
    return 2.0  # 初始退避 2 秒
```

`Retry-After` 的值是服务端根据当前负载动态计算的，比客户端自己猜测的退避时间更准确。

### 1.5.4 连接池与连接复用

使用 httpx 时，正确的做法是创建一个客户端实例并复用，而不是为每个请求创建新实例。`AnthropicClient` 的设计已经内置了这一最佳实践——`self._client` 在构造函数中创建，整个生命周期中复用。

连接复用减少了 TCP 握手和 TLS 协商的开销，在高频调用场景下可以显著降低延迟。

---

## 1.6 自测题

### 问题 1（理论）

列出 Anthropic API 的所有错误类型及其对应的 HTTP 状态码，并说明每种错误类型的典型触发场景。

### 问题 2（理论）

Anthropic API 支持 `x-api-key` 和 `Bearer` 两种身份验证方式。解释两者的区别，并说明在什么场景下你会选择哪一种。

### 问题 3（编码）

不参考本章的示例代码，实现一个 `Client` 类，支持多 Key 轮转。要求：

- 构造函数接收一个 API Key 列表
- 每次请求使用下一个 Key（轮询）
- 当某个 Key 返回 401 错误时，自动将其标记为不可用，切换到下一个 Key
- 如果所有 Key 都不可用，抛出异常

```python
# 预期接口
class Client:
    def __init__(self, api_keys: list[str]):
        ...

    def post(self, body: dict) -> dict:
        ...
```

### 问题 4（编码）

为第 1.5.3 节中的重试策略添加具体实现。要求：

- 仅对 5xx 和 429 错误进行重试
- 最多重试 3 次
- 使用指数退避（1s, 2s, 4s）
- 对于 429 错误，如果响应包含 `Retry-After` 头，优先使用其值
- 4xx 错误（除 429 外）立即失败，不重试

```python
# 预期接口
def post_with_retry(self, body: dict, max_retries: int = 3) -> dict:
    ...
```

---

## 本章小结

本章完成了与 Anthropic API 通信所需的所有基础设施：

1. **概念层**：理解了 Anthropic API 的设计哲学——Content Block 抽象模型、显式工具使用、分层错误系统。
2. **协议层**：掌握了身份验证、请求格式、错误码体系和速率限制机制的完整细节。
3. **实现层**：构建了 Python 和 Node.js 双语言的可运行客户端，支持同步/异步调用、完整的错误处理和类型安全。
4. **实践层**：学习了 Key 轮换、重试策略和安全最佳实践。

第 2 章将在此基础上实现流式响应（Server-Sent Events）处理，让 Claude 的回复逐 Token 实时呈现。
