# 附录 C：自测题答案

> 本书 17 章全部自测题的参考答案与代码实现

---

## 第 1 章：Anthropic API 基础

### 问题 1（理论）：Anthropic API 错误类型及对应 HTTP 状态码

| HTTP 状态码 | 错误类型 | 典型触发场景 |
|:----------:|---------|------------|
| 400 | `invalid_request_error` | 请求体格式错误、缺少必填字段（如 max_tokens）、参数值不合法 |
| 401 | `authentication_error` | API Key 无效、过期或缺失 |
| 403 | `permission_error` | API Key 无权访问请求的资源或模型 |
| 404 | `not_found_error` | 模型名称错误或资源不存在 |
| 413 | `request_too_large` | 请求体超过大小限制（通常 10MB） |
| 429 | `rate_limit_error` | 超过 RPM/TPM 限制 |
| 500 | `api_error` | Anthropic 内部服务器错误 |
| 529 | `overloaded_error` | Anthropic 服务过载 |

**关键区分**：4xx 错误问题出在客户端——修复请求本身才是正确方案，重试无效。5xx 错误问题出在服务端——这些是暂时的，重试（配合退避策略）是合理的。429 是 4xx 中唯一应该重试的类型。

### 问题 2（理论）：`x-api-key` vs `Bearer` 认证方式区别

**区别：**
- `x-api-key`：自定义 HTTP 头，语义专属于 Anthropic API。不会被遵循 Bearer 规范的其他服务误解析。某些 HTTP 中间件和日志系统默认遮蔽此头内容。
- `Bearer Token`：标准 HTTP Authorization 头，兼容标准 API 网关和 OAuth 中间件。但 Bearer Token 具有通用语义，代理和网关可能在不知情的情况下将其转发到非预期的上游服务。

**选择场景：**
- 直接调用 Anthropic API 且无特殊网关需求 → `x-api-key`（官方 SDK 默认，更安全）
- 使用统一认证层（API Gateway、OAuth 中间件）→ `Bearer`（兼容性更好）

### 问题 3（编码）：多 Key 轮转 Client 类

**Python 参考实现：**

```python
import os
import time
from itertools import cycle


class Client:
    def __init__(self, api_keys: list[str]):
        if not api_keys:
            raise ValueError("至少需要一个 API Key")
        self._keys = api_keys[:]
        self._failed_keys: set[str] = set()
        self._cycle = cycle(range(len(self._keys)))
        self._current_index = 0

    def _next_key_index(self) -> int:
        """获取下一个未标记为失败的 Key 的索引。"""
        available = [i for i in range(len(self._keys))
                     if self._keys[i] not in self._failed_keys]
        if not available:
            raise RuntimeError("所有 API Key 均已失败")
        return available[0]

    def post(self, body: dict) -> dict:
        """发送 API 请求，处理 401 自动切换 Key。"""
        import httpx

        last_error = None
        attempted = set()

        while len(attempted) < len(self._keys):
            idx = self._next_key_index()
            if idx in attempted:
                break
            attempted.add(idx)

            try:
                resp = httpx.post(
                    "https://api.anthropic.com/v1/messages",
                    headers={
                        "x-api-key": self._keys[idx],
                        "anthropic-version": "2023-06-01",
                        "content-type": "application/json",
                    },
                    json=body,
                )
                if resp.status_code == 401:
                    self._failed_keys.add(self._keys[idx])
                    continue
                resp.raise_for_status()
                return resp.json()
            except httpx.HTTPStatusError:
                raise
        raise RuntimeError("所有 API Key 均已失败")


# 测试
client = Client(["key-invalid-1", "key-valid", "key-invalid-2"])
```

**Node.js 参考实现：**

```typescript
class Client {
  private keys: string[];
  private failedKeys: Set<string> = new Set();
  private currentIndex: number = 0;

  constructor(apiKeys: string[]) {
    if (apiKeys.length === 0) {
      throw new Error("至少需要一个 API Key");
    }
    this.keys = [...apiKeys];
  }

  private nextKeyIndex(): number {
    for (let i = 0; i < this.keys.length; i++) {
      const idx = (this.currentIndex + i) % this.keys.length;
      if (!this.failedKeys.has(this.keys[idx]!)) {
        this.currentIndex = (idx + 1) % this.keys.length;
        return idx;
      }
    }
    throw new Error("所有 API Key 均已失败");
  }

  async post(body: Record<string, unknown>): Promise<Record<string, unknown>> {
    const attempted = new Set<number>();
    let lastError: Error | null = null;

    while (attempted.size < this.keys.length) {
      const idx = this.nextKeyIndex();
      if (attempted.has(idx)) break;
      attempted.add(idx);

      try {
        const response = await fetch("https://api.anthropic.com/v1/messages", {
          method: "POST",
          headers: {
            "x-api-key": this.keys[idx]!,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
          },
          body: JSON.stringify(body),
        });

        if (response.status === 401) {
          this.failedKeys.add(this.keys[idx]!);
          continue;
        }
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        return (await response.json()) as Record<string, unknown>;
      } catch (e) {
        lastError = e as Error;
      }
    }
    throw lastError ?? new Error("所有 API Key 均已失败");
  }
}
```

### 问题 4（编码）：带退避的重试策略

**Python 参考实现：**

```python
import time
import random
import httpx


def post_with_retry(self, body: dict, max_retries: int = 3) -> dict:
    """发送请求，仅对 5xx 和 429 进行指数退避重试。"""
    for attempt in range(max_retries + 1):  # N 次重试 = N+1 次总尝试
        try:
            resp = httpx.post(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "x-api-key": self.api_key,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json",
                },
                json=body,
            )

            # 成功：直接返回
            if 200 <= resp.status_code < 300:
                return resp.json()

            # 4xx（除 429 外）：立即失败
            if 400 <= resp.status_code < 500 and resp.status_code != 429:
                raise httpx.HTTPStatusError(
                    f"Client error {resp.status_code}", response=resp
                )

            # 429 或 5xx：计算退避时间
            if attempt == max_retries:
                raise httpx.HTTPStatusError(
                    f"Max retries exceeded: {resp.status_code}", response=resp
                )

            delay = _get_retry_delay(resp, attempt)
            time.sleep(delay)

        except (httpx.TimeoutException, httpx.ConnectError) as e:
            if attempt == max_retries:
                raise
            delay = _get_backoff_delay(attempt)
            time.sleep(delay)

    raise RuntimeError("Unreachable")


def _get_retry_delay(resp, attempt: int) -> float:
    """解析 Retry-After 头，或使用退避计算。"""
    retry_after = resp.headers.get("retry-after")
    if retry_after is not None:
        return max(float(retry_after), _get_backoff_delay(attempt))
    return _get_backoff_delay(attempt)


def _get_backoff_delay(attempt: int) -> float:
    """指数退避 + 全抖动：1s, 2s, 4s。"""
    base = 2 ** attempt  # attempt=0→1, 1→2, 2→4
    return random.uniform(0, base)
```

**Node.js 参考实现：**

```typescript
function getBackoffDelay(attempt: number): number {
  const base = Math.pow(2, attempt); // 0→1, 1→2, 2→4
  return Math.random() * base;
}

async function postWithRetry(
  apiKey: string,
  body: Record<string, unknown>,
  maxRetries: number = 3,
): Promise<Record<string, unknown>> {
  for (let attempt = 0; attempt <= maxRetries; attempt++) {
    const response = await fetch("https://api.anthropic.com/v1/messages", {
      method: "POST",
      headers: {
        "x-api-key": apiKey,
        "anthropic-version": "2023-06-01",
        "content-type": "application/json",
      },
      body: JSON.stringify(body),
    });

    if (response.ok) {
      return (await response.json()) as Record<string, unknown>;
    }

    // 4xx (除 429) 立即失败
    if (response.status >= 400 && response.status < 500 && response.status !== 429) {
      throw new Error(`Client error ${response.status}`);
    }

    if (attempt === maxRetries) {
      throw new Error(`Max retries exceeded: ${response.status}`);
    }

    const retryAfter = response.headers.get("retry-after");
    const delay = retryAfter
      ? Math.max(parseFloat(retryAfter) * 1000, getBackoffDelay(attempt) * 1000)
      : getBackoffDelay(attempt) * 1000;

    await new Promise((resolve) => setTimeout(resolve, delay));
  }

  throw new Error("Unreachable");
}
```

---

## 第 2 章：Messages API 核心协议

### 问题 1（概念）：system 提示的位置差异

**答案：**

Anthropic 使用顶层 `system` 参数而非 `"role": "system"` 消息。主要差异：

1. **结构分离**：`system` 在请求体中独立于 `messages` 数组。语义上明确区分"指令"和"对话"，指令不会混在对话历史中。
2. **只有两种角色**：Messages API 仅支持 `user` 和 `assistant`。`system` 不是第三种角色，而是另一维度的概念（"给模型的元指令"）。
3. **支持数组和缓存**：`system` 可以是 Text Block 数组，支持 `cache_control`。OpenAI 需要在消息数组中使用 system role 才能使用缓存，增加了指令/数据混合的风险。
4. **防止上下文污染**：独立存放的系统提示不会在长对话中被意外截断或修改。

### 问题 2（概念）：找出 Image Block 的错误

**答案：两处错误：**

1. **`source.type` 无效**：仅支持 `"base64"` 和 `"url"`，`"file"` 不是合法的 source type。
2. **本地路径无法被 API 访问**：API 服务器无法访问客户端本地的 `/Users/me/photo.png`。

**正确做法**：将文件读取为字节数据，进行 base64 编码，使用 `source.type: "base64"` 发送。

```json
{
  "type": "image",
  "source": {
    "type": "base64",
    "media_type": "image/png",
    "data": "iVBORw0KGgo..."
  }
}
```

### 问题 3（编码）：多图像分析请求构建器

**Python 参考实现：**

```python
from message_builder import MessageRequest, Message, TextBlock, ImageBlock


def build_analysis_request(image_paths: list[str], question: str) -> MessageRequest:
    blocks = [TextBlock(text=question)]
    for path in image_paths:
        blocks.append(ImageBlock.from_file(path))

    return MessageRequest(
        model="claude-sonnet-4-20250514",
        messages=[Message(role="user", content=blocks)],
        max_tokens=2048,
        system="你是一个多图像对比分析助手。",
    )


# 测试
req = build_analysis_request(
    ["chart1.png", "chart2.png"],
    "这两个图表的趋势有什么不同？"
)
print(req.to_json(indent=2))
```

**Node.js 参考实现：**

```typescript
import { MessageRequest, Message, TextBlock, ImageBlock } from "./MessageBuilder.js";

function buildAnalysisRequest(imagePaths: string[], question: string): MessageRequest {
  const blocks = [new TextBlock(question)];
  for (const path of imagePaths) {
    blocks.push(ImageBlock.fromFile(path));
  }

  return new MessageRequest({
    model: "claude-sonnet-4-20250514",
    messages: [new Message("user", blocks)],
    maxTokens: 2048,
    system: "你是一个多图像对比分析助手。",
  });
}
```

### 问题 4（编码）：TypeScript 多轮对话请求纠错

**四处错误及修复：**

1. **`role: "system"` 无效**：应使用顶层 `system` 参数
2. **连续 `user` 消息**：改为 user/assistant 交替
3. **`maxTokens: 0` 无效**：`max_tokens` 必须 >= 1
4. **`temperature: 2.0` 超出范围**：必须在 [0.0, 1.0] 之间

**修复后的代码：**

```typescript
const req = new MessageRequest({
  model: "claude-sonnet-4-20250514",
  messages: [
    Message.user("旧金山天气如何？"),
  ],
  maxTokens: 1024,
  system: "你是一个天气助手。",
});
```

---

## 第 3 章：LLM 模型深度剖析

### 问题 1：概念辨析

**a) "Claude Opus 4.7 的单价和 Opus 4.6 相同，所以使用成本也相同。" —— 错误。**

Opus 4.7 使用全新 tokenizer，相同文本可能产生多至 35% 的 token。虽然单价相同（$5/$25 per MTok），但实际消耗的 token 数不同，导致最终美元成本不同。此外，`max_tokens` 设置也可能影响速率限制（OTPM 估算）。

**b) "Prompt caching 的 1 小时缓存在读取 1 次后就开始盈利。" —— 错误。**

1 小时缓存的写入价格为标准输入的 2x（如 Sonnet 4.6：$6.00 vs $3.00）。盈亏平衡计算：
```
write_price / (base_price - read_price) = 6.00 / (3.00 - 0.30) = 6.00 / 2.70 ≈ 2.22
```
需要至少 **3 次**读取才能盈利（1 次写入 + 3 次读取 < 4 次无缓存）。

**c) "Batch API 可以和 prompt caching 叠加使用。" —— 正确。**

Batch API 处理引擎在尽力而为的基础上尝试复用缓存。组合折扣：Batch（-50%）× Cache Read（-90%）= 仅为标准价格的 5%。

**d) "Temperature=0 保证每次输出完全相同。" —— 不完全正确。**

即使 T=0（greedy decoding），由于浮点精度差异和硬件差异（GPU 非确定性），不同运行之间可能存在微小的输出差异。这不是 Anthropic 特有的——所有基于浮点计算的 LLM 都有此特性。

### 问题 2：模型选型 —— AI 英语口语陪练

**a) 模型选择：Haiku 4.5**

理由：
- 延迟要求严格（< 800ms 含网络往返），Haiku 是速度最快的模型
- 任务复杂度中等（英语口语陪练不需要顶级推理）
- 500 万次对话/月，成本极其敏感
- 每轮交互 token 量小（200+100），不需要大上下文窗口

**b) 成本优化策略：**
1. **Prompt Caching**：将 2K token 的教学风格 system prompt 缓存（5 分钟 TTL），每次对话约 10 轮交互中全部命中缓存
2. **模型路由**：简单问候/确认用更低 cost 策略，复杂语法解释路由到 Sonnet 4.6
3. **Batch API**：不适用（实时场景）
4. **输出控制**：设置合理 `max_tokens`（约 150），避免过长回复

**c) 月度成本估算：**

标准模式（每轮 200 input + 100 output = 300 tokens）：
```
月度 API 次数 = 5,000,000 × 10 = 50,000,000 次
input = 50M × 200 / 1M × $1.00 = $10,000
output = 50M × 100 / 1M × $5.00 = $25,000
总成本 = $35,000/月
```

含缓存模式（system prompt 2K tokens 缓存，仅首次写入）：
```
缓存写入 = 2,000/1M × $1.25 × 5M(对话数) = $12,500
缓存读取 = 50M × 2,000/1M × $0.10 = $10,000
其余 input = 50M × 198/1M × $1.00 = $9,900
output = $25,000
总成本 ≈ $57,400/月
```

实际上，缓存方案反而更贵，因为每条请求的非缓存部分（200 tokens 用户输入）占比太小。更好的方案是只缓存教学风格的 system prompt，使用 5 分钟 TTL，单次对话 10 轮内全部命中：
```
缓存写入 = 2,000/1M × $1.25 × 5M = $12,500
缓存读取 = 45M × 2,000/1M × $0.10 = $9,000
其余 = $9,900 + $25,000 = $34,900
总成本 ≈ $56,400/月  -- 仍比无缓存更贵
```

这说明对于 token 消耗极小的场景，Prompt Caching 可能没有经济意义。纯 Haiku 4.5 标准调用每月约 $35,000。

### 问题 3（编码）：模型选择器

**Python 参考实现：**

```python
def select_model_for_scenario(task: dict) -> str:
    """根据任务特征选择最优模型。"""

    # 规则按优先级排序（高优先级在前）

    # 1. 需要 1M 上下文窗口
    if task.get("requires_long_context"):
        return "claude-sonnet-4-6"

    # 2. Agentic 任务
    if task.get("complexity") == "agentic":
        return "claude-opus-4-7"

    # 3. 高复杂度
    if task.get("complexity") == "high":
        if task.get("budget") == "low":
            return "claude-sonnet-4-6"
        else:
            return "claude-opus-4-7"

    # 4. 延迟敏感 或 低预算
    if task.get("latency_sensitive") or task.get("budget") == "low":
        return "claude-haiku-4-5"

    # 5. 默认
    return "claude-sonnet-4-6"


# 测试用例
test_cases = [
    # 长上下文 + 一般复杂度
    ({"requires_long_context": True, "complexity": "medium"}, "claude-sonnet-4-6"),
    # Agentic 任务
    ({"complexity": "agentic"}, "claude-opus-4-7"),
    # 高复杂度 + 低预算
    ({"complexity": "high", "budget": "low"}, "claude-sonnet-4-6"),
    # 高复杂度 + 高预算
    ({"complexity": "high", "budget": "high"}, "claude-opus-4-7"),
    # 延迟敏感
    ({"latency_sensitive": True, "complexity": "low"}, "claude-haiku-4-5"),
    # 低预算默认
    ({"budget": "low"}, "claude-haiku-4-5"),
    # 无特殊条件
    ({}, "claude-sonnet-4-6"),
]

for task, expected in test_cases:
    result = select_model_for_scenario(task)
    assert result == expected, f"{task} → expected {expected}, got {result}"
    print(f"PASS: {task} → {result}")
```

**Node.js 参考实现：**

```typescript
interface Task {
  requires_long_context?: boolean;
  complexity?: "low" | "medium" | "high" | "agentic";
  budget?: "low" | "medium" | "high";
  latency_sensitive?: boolean;
}

function selectModelForScenario(task: Task): string {
  if (task.requires_long_context) return "claude-sonnet-4-6";
  if (task.complexity === "agentic") return "claude-opus-4-7";

  if (task.complexity === "high") {
    return task.budget === "low" ? "claude-sonnet-4-6" : "claude-opus-4-7";
  }

  if (task.latency_sensitive || task.budget === "low") {
    return "claude-haiku-4-5";
  }

  return "claude-sonnet-4-6";
}
```

### 问题 4（编码）：成本计算

**a) 无优化成本：**
```
标准输入 = 10,000 × (30,000 + 5,000) / 1,000,000 × $5.00 = 10,000 × 35,000 / 1M × $5 = $1,750
标准输出 = 10,000 × 500 / 1,000,000 × $25.00 = 10,000 × 0.0005 × $25 = $125
总成本 = $1,875.00
```

**b) Batch API 无缓存成本：**
```
Batch 输入 = $1,750 × 0.5 = $875
Batch 输出 = $125 × 0.5 = $62.50
总成本 = $937.50
节省 = $1,875 - $937.50 = $937.50 (50%)
```

**c) Batch API + 缓存成本：**
```
缓存写入 = 30,000/1M × $10.00 = $0.30 （一次性）
缓存读取 = (10,000 - 1) × 30,000/1M × $0.50 ≈ 9,999 × $0.015 = $149.99
其余输入（Batch）= 10,000 × 5,000/1M × $2.50 = $125
输出（Batch）= $62.50

总成本 = $0.30 + $149.99 + $125 + $62.50 = $337.79
```

**d) 节省百分比：**
- b 方案 vs a 方案：($1,875 - $937.50) / $1,875 = **50.0%**
- c 方案 vs a 方案：($1,875 - $337.79) / $1,875 = **82.0%**
- c 方案 vs b 方案：($937.50 - $337.79) / $937.50 = **64.0%**

---

## 第 4 章：Structured Outputs

### 问题 1（理论）：Constrained Decoding 的 Logit Masking 机制

**Logit Masking 原理：**

在每个自回归解码步骤中，模型计算出所有可能 Token 的 logits（概率分数），然后在 softmax/sampling 之前根据外部约束掩码部分 Token：

```
1. Schema → 编译为有限状态自动机（FSA）
2. 每个解码步骤：FSA 定义"当前状态下哪些 Token 合法"
3. 非法 Token 的 logit 设为 -inf（概率 = 0）
4. 仅从合法 Token 中采样
```

**为什么比"生成后验证"更高效？**

1. **数学保证**：只要生成正常完成，输出 100% 符合 Schema —— 无需重试、无需正则。
2. **Token 经济**：不消耗 Token 用于重试验证（每次失败重试消耗完整 input + output）。
3. **延迟可预测**：不存在不确定的重试循环导致的尾部延迟。
4. **类型安全**：在 Token 层面保证类型正确（不会出现 `"age": "三十岁"`）。

### 问题 2（理论）：Structured Outputs vs Tool Use 对比

| 维度 | Structured Outputs | Tool Use |
|------|-------------------|----------|
| 输出格式保证 | 数学保证（Logit Masking） | "尽力而为"（训练优化） |
| 交互模式 | 一次性输出 | 对话式（tool_use → tool_result） |
| Token 效率 | 更高（无 tool_use 包装） | 较低（含元数据开销） |

**场景选择：**
- (a) 从客户邮件提取订单号、日期和金额 → **Structured Outputs**（数据提取，需要严格保证，非交互式）
- (b) 构建能查询数据库、发送邮件的 AI 助手 → **Tool Use**（需要与外部系统交互，对话式）
- (c) 将模型输出作为 RESTful API 响应体 → **Structured Outputs**（API 返回值需要严格的 Schema 保证）

### 问题 3（编码）：extract_entities 函数

**Python 参考实现：**

```python
import json
import re
from typing import Any


def extract_entities(client: Any, model: str, text: str) -> dict:
    """从文本中提取人物和地点信息。"""
    schema = {
        "type": "object",
        "properties": {
            "persons": {
                "type": "array",
                "items": {"type": "string"},
                "description": "文本中提到的人物姓名列表"
            },
            "locations": {
                "type": "array",
                "items": {"type": "string"},
                "description": "文本中提到的地点名称列表"
            }
        },
        "required": ["persons", "locations"],
        "additionalProperties": False
    }

    response = client.post(
        model=model,
        max_tokens=1024,
        temperature=0,
        system="你是一个实体提取助手。从文本中提取人物和地点。如果找不到，返回空列表。",
        messages=[
            {"role": "user", "content": text}
        ],
        output_config={
            "format": {"type": "json_schema", "schema": schema},
            "effort": "medium"
        }
    )

    # 提取 JSON（处理模型可能在 JSON 外添加额外文字的情况）
    content = response["content"][0]["text"]

    # 策略 1: 纯 JSON 解析
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        pass

    # 策略 2: 从 markdown fence 中提取
    m = re.search(r'```(?:json)?\s*([\s\S]*?)\s*```', content)
    if m:
        try:
            return json.loads(m.group(1))
        except json.JSONDecodeError:
            pass

    # 策略 3: 找最外层花括号
    m = re.search(r'\{[\s\S]*\}', content)
    if m:
        return json.loads(m.group(0))

    raise ValueError(f"无法从响应中解析 JSON: {content[:200]}...")


# 测试
# result = extract_entities(client, "claude-sonnet-4-6", "张三和李四上周去了北京和上海。")
# print(result)  # {"persons": ["张三", "李四"], "locations": ["北京", "上海"]}
```

**Node.js 参考实现：**

```typescript
async function extractEntities(
  client: { post: (params: any) => Promise<any> },
  model: string,
  text: string,
): Promise<{ persons: string[]; locations: string[] }> {
  const schema = {
    type: "object",
    properties: {
      persons: {
        type: "array",
        items: { type: "string" },
      },
      locations: {
        type: "array",
        items: { type: "string" },
      },
    },
    required: ["persons", "locations"],
    additionalProperties: false,
  };

  const response = await client.post({
    model,
    max_tokens: 1024,
    temperature: 0,
    system: "你是一个实体提取助手。从文本中提取人物和地点。",
    messages: [{ role: "user", content: text }],
    output_config: {
      format: { type: "json_schema", schema },
      effort: "medium",
    },
  });

  const content = response.content[0].text;

  // 多策略 JSON 解析
  try {
    return JSON.parse(content);
  } catch {}

  const fenceMatch = content.match(/```(?:json)?\s*([\s\S]*?)\s*```/);
  if (fenceMatch) {
    try {
      return JSON.parse(fenceMatch[1]!);
    } catch {}
  }

  const braceMatch = content.match(/\{[\s\S]*\}/);
  if (braceMatch) {
    return JSON.parse(braceMatch[0]!);
  }

  throw new Error(`无法解析 JSON: ${content.slice(0, 200)}`);
}
```

### 问题 4（编码）：bulk_extract 方法

**Python 参考实现：**

```python
import concurrent.futures
from typing import Any


class StructuredOutputClient:
    # ... 现有方法 ...

    def bulk_extract(
        self,
        model: str,
        texts: list[str],
        json_schema: dict,
        *,
        max_concurrency: int = 3,
    ) -> list[dict]:
        """批量数据提取，并发执行。"""
        results = [None] * len(texts)

        def _extract_one(idx: int, text: str):
            try:
                return idx, self.extract(
                    text=text,
                    model=model,
                    json_schema=json_schema,
                )
            except Exception as e:
                return idx, {"error": str(e), "text": text[:100]}

        with concurrent.futures.ThreadPoolExecutor(
            max_workers=max_concurrency
        ) as executor:
            futures = [
                executor.submit(_extract_one, i, text)
                for i, text in enumerate(texts)
            ]
            for future in concurrent.futures.as_completed(futures):
                idx, result = future.result()
                results[idx] = result

        return results
```

**Node.js 参考实现：**

```typescript
async function bulkExtract(
  client: StructuredOutputClient,
  model: string,
  texts: string[],
  jsonSchema: Record<string, unknown>,
  maxConcurrency: number = 3,
): Promise<Record<string, unknown>[]> {
  const results: Record<string, unknown>[] = new Array(texts.length);

  async function extractOne(idx: number, text: string): Promise<void> {
    try {
      results[idx] = await client.extract({
        text,
        model,
        json_schema: jsonSchema,
      });
    } catch (e) {
      results[idx] = { error: String(e), text: text.slice(0, 100) };
    }
  }

  // 并发控制：分批执行
  for (let i = 0; i < texts.length; i += maxConcurrency) {
    const batch = texts.slice(i, i + maxConcurrency);
    await Promise.all(
      batch.map((text, j) => extractOne(i + j, text))
    );
  }

  return results;
}
```

---

## 第 5 章：Streaming 与 Extended Thinking

### 题目 1（编码）：SSE 解析器

**Python 参考实现：**

```python
import json
from typing import Optional


class SSEParser:
    """零依赖 SSE 解析器，遵循 WHATWG SSE 标准。"""

    def __init__(self):
        self._buffer = ""

    def feed(self, chunk: str) -> list[dict]:
        """处理新数据块，返回完整的事件列表。"""
        self._buffer += chunk
        events = []

        while True:
            idx = self._buffer.find("\n\n")
            if idx == -1:
                break
            event_text = self._buffer[:idx]
            self._buffer = self._buffer[idx + 2:]
            parsed = self._parse_event(event_text)
            if parsed:
                events.append(parsed)

        return events

    def _parse_event(self, text: str) -> Optional[dict]:
        """解析单个事件文本。"""
        event_type = "message"
        data_lines = []

        for line in text.split("\n"):
            # 注释行
            if line.startswith(":"):
                continue

            if ":" in line:
                field, _, value = line.partition(":")
                value = value.removeprefix(" ")
            else:
                field = line
                value = ""

            if field == "event":
                event_type = value or "message"
            elif field == "data":
                data_lines.append(value)
            # id 和 retry 字段处理省略

        if not data_lines:
            return None

        data = "\n".join(data_lines)
        return {"event": event_type, "data": json.loads(data)}


# 测试
parser = SSEParser()
events = parser.feed(
    'event: message_start\ndata: {"type": "message_start", "message": {"id": "msg_01"}}\n\n'
    'event: content_block_delta\ndata: {"type": "content_block_delta", "index": 0, "delta": {"type": "text_delta", "text": "Hello"}}\n\n'
    'event: ping\ndata: {"type": "ping"}\n\n'
)

assert len(events) == 2  # ping 被忽略
assert events[0]["event"] == "message_start"
assert events[0]["data"]["message"]["id"] == "msg_01"
assert events[1]["event"] == "content_block_delta"
assert events[1]["data"]["delta"]["text"] == "Hello"
```

**Node.js 参考实现：**

```typescript
interface ParsedEvent {
  event: string;
  data: Record<string, unknown>;
}

class SSEParser {
  private buffer = "";

  feed(chunk: string): ParsedEvent[] {
    this.buffer += chunk;
    const events: ParsedEvent[] = [];

    while (true) {
      const idx = this.buffer.indexOf("\n\n");
      if (idx === -1) break;
      const eventText = this.buffer.slice(0, idx);
      this.buffer = this.buffer.slice(idx + 2);
      const parsed = this.parseEvent(eventText);
      if (parsed) events.push(parsed);
    }

    return events;
  }

  private parseEvent(text: string): ParsedEvent | null {
    let eventType = "message";
    const dataLines: string[] = [];

    for (const line of text.split("\n")) {
      if (line.startsWith(":")) continue;

      const colonIdx = line.indexOf(":");
      if (colonIdx >= 0) {
        const field = line.slice(0, colonIdx);
        let value = line.slice(colonIdx + 1);
        if (value.startsWith(" ")) value = value.slice(1);

        if (field === "event") eventType = value || "message";
        else if (field === "data") dataLines.push(value);
      }
    }

    if (dataLines.length === 0) return null;
    return { event: eventType, data: JSON.parse(dataLines.join("\n")) };
  }
}
```

### 题目 2（编码）：思考签名验证

**Python 参考实现：**

```python
from typing import Any


def prepare_assistant_message(blocks: list[dict[str, Any]]) -> dict[str, Any]:
    """构造可安全传递回 API 的 assistant 消息对象。

    Args:
        blocks: 原始内容块列表（thinking block + text/tool_use block）

    Returns:
        符合 API 格式的 assistant 消息对象
    """
    thinking_blocks = []
    non_thinking_blocks = []
    has_error = False

    for block in blocks:
        block_type = block.get("type")

        if block_type == "thinking":
            signature = block.get("signature")
            if not signature:
                raise ValueError(f"thinking 块缺少签名: {block}")
            thinking_blocks.append({
                "type": "thinking",
                "thinking": block["thinking"],
                "signature": signature,
            })

        elif block_type == "redacted_thinking":
            # 回退处理：保留完整数据
            if "data" not in block:
                raise ValueError("redacted_thinking 块缺少 data 字段")
            thinking_blocks.append(block)

        elif block_type in ("text", "tool_use"):
            non_thinking_blocks.append(block)

        else:
            raise ValueError(f"未知的块类型: {block_type}")

    # 验证顺序：thinking 必须在 text/tool_use 之前
    # 构造最终 content 数组
    content = thinking_blocks + non_thinking_blocks

    return {
        "role": "assistant",
        "content": content,
    }


# 测试
blocks = [
    {"type": "thinking", "thinking": "Let me analyze...", "signature": "EqQBCg..."},
    {"type": "text", "text": "Based on my analysis..."},
]
msg = prepare_assistant_message(blocks)
assert msg["role"] == "assistant"
assert msg["content"][0]["type"] == "thinking"
assert msg["content"][0]["signature"] == "EqQBCg..."
assert msg["content"][1]["type"] == "text"
```

### 题目 3（设计）：流式中断与恢复

**1. 第二条消息的 API 请求构造：**

需要包含：
- 原始 System Prompt（不变）
- 原始 User 消息（用户的第一条消息）
- 已生成的 Assistant 回复（截至被中断时的完整内容块列表）
- 新的 User 消息（用户的第二条输入）

```json
[
  {"role": "user", "content": "北京天气？"},
  {"role": "assistant", "content": [
    {"type": "text", "text": "[中途截断的回复内容]"}
  ]},
  {"role": "user", "content": "上海呢？"}
]
```

**2. 已生成但未显示的思考 tokens 是否应包含？**

**应该包含**。原因：
- 思考 tokens 是模型推理的一部分，模型在后续推理中"记得"自己思考过什么
- 如果不包含思考历史，模型的上下文连贯性会受损
- 但如果使用了工具调用，上一个 assistant 消息中的思考块必须完整返回，否则签名验证会失败

**3. Extended Thinking 在工具调用后被中断的处理：**

这涉及思考块（thinking）+ 工具调用块（tool_use）的完整性需求：
- 如果要继续对话：需保留完整的 thinking + tool_use 内容块，并添加 tool_result 作为下一条 user 消息
- 如果重新开始：将 thinking + tool_use 保留在历史中，但不添加 tool_result（模型会从该状态继续）
- 如果丢弃：将所有 assistant 内容从历史中移除，问题简化为初始状态

### 题目 4（分析）：不完整事件序列分析

**1. 在协议层面是否合法？**

**不合法**。事件序列在 `content_block_start` (index=1, tool_use) 之后有 `content_block_delta` (input_json_delta)，但缺少 `content_block_stop` (index=1) 就出现了 `error` 事件。协议要求每个内容块由 `content_block_start` → 一系列 `content_block_delta` → `content_block_stop` 构成。该序列中的 tool_use 块未完成就被 `error` 事件中断。

此外，`error` 事件可能在任何位置出现（这是协议允许的），它之后的任何内容都应被忽略。

**2. 收到 error 事件后的处理：**
- 立即停止处理流（不再等待更多事件）
- 已完整接收的部分（thinking 块 index=0，已通过 content_block_stop 确认完成）可以保留
- 记录错误信息用于诊断
- 根据 error.type 决定重试策略：
  - `overloaded_error` → 退避后重试
  - 其他类型 → 根据类型判断

**3. 第四轮对话的构造：**

需要保留的上下文：
```json
[
  {前两轮的完整 user/assistant 交换},
  {
    "role": "user",
    "content": "旧金山的天气如何？"  // 第三轮用户输入
  },
  {
    "role": "assistant",
    "content": [
      {"type": "thinking", "thinking": "Let me check the weather...", "signature": "abc123..."}
    ]
    // 注意：tool_use 块未完成（无 content_block_stop），因此不应包含在历史中
  },
  {
    "role": "user",
    "content": "那明天呢？"  // 第四轮
  }
]
```

关键是：只能包含已通过 `content_block_stop` 确认完成的块（即 thinking 块 index=0），未完成的 tool_use 块不应出现在历史中。

---

## 第 6 章：工具调用与函数执行

### 题目 1（理论）：stop_reason 与 Agentic Loop

**`stop_reason: "tool_use"` 表示：**
Claude 已生成一个或多个 `tool_use` 内容块，正在等待客户端执行这些工具并返回 `tool_result`。这是 Agentic Loop 的"等待执行"状态。

**Agentic Loop 的退出条件：**
1. **自然退出**：`stop_reason == "end_turn"`（模型判断任务完成）
2. **迭代上限**：达到 `max_iterations`（如 10-25 次）
3. **连续无工具调用**：连续 N 轮 stop_reason 都不再是 `tool_use`
4. **用户中断**：外部取消信号
5. **致命错误**：工具执行全部失败且模型无法继续

### 题目 2（理论）：tool_choice 参数差异

| 配置 | 行为 | disable_parallel_tool_use=true 时的行为 |
|------|------|--------------------------------------|
| `{"type": "auto"}` | 模型自行判断是否使用工具、使用哪个、是否并行 | 最多使用一个工具 |
| `{"type": "any"}` | 模型必须使用至少一个工具，自行选择使用哪个 | 恰好使用一个工具 |
| `{"type": "tool", "name": "X"}` | 模型必须使用工具 X | 可进一步设置 `disable_parallel_tool_use: true` |

**关键差异**：`auto` 时模型可以完全不使用工具；`any` 强制至少使用一个；`{"type": "tool", "name": "X"}` 强制使用特定工具。

### 题目 3（编码）：ToolRegistry 使用

**Python 参考实现：**

```python
from tool_registry import ToolRegistry


registry = ToolRegistry()

# 注册工具
registry.register(
    name="get_weather",
    description="获取指定位置的当前天气信息",
    input_schema={
        "type": "object",
        "properties": {
            "location": {"type": "string", "description": "城市名称"}
        },
        "required": ["location"]
    },
    handler=lambda location: f"{location}: 22°C, 晴",
)

registry.register(
    name="get_time",
    description="获取指定时区的当前时间",
    input_schema={
        "type": "object",
        "properties": {
            "timezone": {"type": "string", "description": "时区名称，如 Asia/Shanghai"}
        },
        "required": ["timezone"]
    },
    handler=lambda timezone: f"2026-05-17T10:30:00 {timezone}",
)

registry.register(
    name="search_news",
    description="搜索最新新闻",
    input_schema={
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "搜索关键词"}
        },
        "required": ["query"]
    },
    handler=lambda query: f"关于'{query}'的搜索结果: ...",
    defer_loading=True,
)

# 启用 Tool Search
registry.enable_tool_search()

# 验证 API 格式
tools = registry.to_api_format()
print(f"注册了 {len(tools)} 个工具")

# 验证延迟加载
deferred = registry.get_deferred_tools()
assert len(deferred) == 1
assert deferred[0].name == "search_news"

# 验证即时加载
immediate = registry.get_immediate_tools()
assert len(immediate) == 2
assert {t.name for t in immediate} == {"get_weather", "get_time"}

print("全部验证通过")
```

### 题目 4（编码）：EmbeddingToolSearch

**Python 参考实现：**

```python
from tool_search import EmbeddingToolSearch


# 创建搜索器
search = EmbeddingToolSearch()

# 索引 10 个模拟工具
tools = [
    {"name": "slack_send_message", "description": "Send a message to a Slack channel",
     "input_schema": {"type": "object", "properties": {"channel": {"type": "string"}, "text": {"type": "string"}}}},
    {"name": "github_create_issue", "description": "Create a GitHub issue in a repository",
     "input_schema": {"type": "object", "properties": {"repo": {"type": "string"}, "title": {"type": "string"}}}},
    {"name": "get_weather", "description": "Get current weather for a location",
     "input_schema": {"type": "object", "properties": {"location": {"type": "string"}}}},
    {"name": "search_database", "description": "Search the database for records",
     "input_schema": {"type": "object", "properties": {"query": {"type": "string"}}}},
    {"name": "send_email", "description": "Send an email to a recipient",
     "input_schema": {"type": "object", "properties": {"to": {"type": "string"}, "body": {"type": "string"}}}},
    {"name": "slack_list_channels", "description": "List all channels in a Slack workspace",
     "input_schema": {"type": "object", "properties": {}}},
    {"name": "github_list_prs", "description": "List pull requests in a GitHub repository",
     "input_schema": {"type": "object", "properties": {"repo": {"type": "string"}}}},
    {"name": "read_file", "description": "Read a file from disk",
     "input_schema": {"type": "object", "properties": {"path": {"type": "string"}}}},
    {"name": "slack_search_messages", "description": "Search messages in Slack",
     "input_schema": {"type": "object", "properties": {"query": {"type": "string"}}}},
    {"name": "run_shell", "description": "Execute a shell command",
     "input_schema": {"type": "object", "properties": {"command": {"type": "string"}}}},
]

search.index_tools(tools)
print(f"已索引 {search.tool_count} 个工具")

# 搜索
results = search.search("send message to slack", top_k=3)
print(f"\n搜索 'send message to slack' 的结果:")
for r in results:
    print(f"  {r['name']}: score={r['score']}")
    assert 0 <= r['score'] <= 1.0, f"score {r['score']} out of range"

# 验证分数降序
scores = [r["score"] for r in results]
for i in range(len(scores) - 1):
    assert scores[i] >= scores[i + 1], f"scores not in descending order at index {i}"

print("\n全部验证通过：分数在 [0,1] 范围内且降序排列")
```

### 题目 5（设计）：Agent 工具加载与 PTC 策略

**工具加载策略：**

| 工具集 | 工具数 | 加载策略 | 原因 |
|--------|:--:|---------|------|
| 内部数据库（高频） | 50 | 保留 3-5 个核心工具为非延迟（如 `query_slow_log`、`check_db_health`、`get_query_plan`），其余 45 个标记 `defer_loading: true` | 数据库运维是核心任务，但不需要 50 个工具全部立即可用 |
| GitHub（中频） | 35 | 整个 MCP server 设 `default_config: {defer_loading: true}`，保留 `github_search_code` 为非延迟 | 代码搜索是主要用例，其他（创建 PR/Issue）按需加载 |
| Slack（结果通道） | 11 | 保留 `slack_send_message` 为非延迟，其余延迟 | 主要向值班工程师发消息，其他管理操作按需 |

**Token 估算：**

传统方式（全部加载）：约 70K tokens（35+11+50 ≈ 96 个工具）
分层策略：约 5-8 个非延迟工具（~5K tokens）+ Tool Search Tool（~500 tokens）= **~5.5K tokens**
Token 节省：约 **92%**

**PTC 策略：**

对于"分析慢查询日志"任务：
1. **使用 PTC 的操作**：
   - 查询慢查询日志（可能返回数千行）→ PTC 处理数据，仅返回聚合统计
   - 分析查询模式、分组、排序 → Python 在 PTC 沙箱中处理
2. **使用标准 Tool Calling 的操作**：
   - 最终的 `slack_send_message`（将分析结果发送给工程师）→ 标准调用即可

PTC 标记：内部数据库的分析类工具设 `allowed_callers: ["code_execution_20260120"]`，避免原始日志数据污染 Claude 的上下文窗口。

---

## 第 8 章：上下文管理

### 题 1：5 分钟 TTL 对客户端架构的影响

**三种应对策略：**

1. **Keep-Alive Ping 模式**：每隔 240 秒发送轻量级请求（仅含 System Prompt），触发缓存读/写以重置 TTL 计时器。成本极低（每次约 $0.0045），但需要后台定时器管理。

2. **批处理请求**：将独立请求在 5 分钟窗口内批量发送，最大化缓存共享。例如：不逐一发送消息，而是将多个 `user` 消息合并到一个 `messages` 数组中。

3. **不依赖缓存命中**：架构不假设缓存一定命中。设计优雅降级——缓存命中时获得成本优势，未命中时按标准价格计费。避免因缓存过期导致的架构性问题。

### 题 2：cache_control 标记限制

**最多 4 个** cache_control 标记。

**Claude Code 为何只放一个消息级标记？**

因为 API 服务端的 KV 缓存页管理器只保留最后一个 `cache_control` 位置的本地注意力 KV 页。放置多个标记会浪费缓存空间，且后续的标记永远不会被恢复。最有效的策略是：在前缀的最后一个可缓存位置放置一个标记，确保此前所有内容都被缓存。

### 题 3：分层缓存策略

**设计：**

```
System Prompt 块 1: 核心指令 (8K tokens)
  → cache_control: {type: "ephemeral", scope: "global"}
System Prompt 块 2: 用户特定上下文 (4K tokens)
  → cache_control: {type: "ephemeral"}  (组织级隔离)
```

**成本计算（每用户 30 轮）：**

无缓存：每用户 30 × 12,000/1M × $3.00 = $1.08/用户 × 10,000 = $10,800/月

有缓存（全局 8K + 用户 4K）：
- 首次写入每个用户：8K/1M × $3.75 + 4K/1M × $3.75 = $0.045
- 后续 29 轮每用户：8K/1M × $0.30 + 4K/1M × $0.30 = $0.0036 × 29 = $0.1044
- 总计每用户：$0.1494
- 10,000 用户：$1,494/月
- **节省：86.2%**

### 题 4（编码）：缓存盈亏计算器

**Python 参考实现：**

```python
def cache_breakeven_analysis(
    write_price_per_mtok: float,
    read_price_per_mtok: float,
    base_price_per_mtok: float,
    cacheable_tokens: int,
) -> dict:
    """计算 Prompt Caching 的盈亏平衡点和节省比例。"""
    mtok = cacheable_tokens / 1_000_000

    # 盈亏平衡点：write + N*read <= N*base
    # write_price <= N*(base_price - read_price)
    # N >= write_price / (base_price - read_price)
    breakeven_n = write_price_per_mtok / (base_price_per_mtok - read_price_per_mtok)

    # 在各 N 值下的成本比较
    scenarios = [5, 10, 50, 100]
    results = {}

    for n in scenarios:
        no_cache = n * base_price_per_mtok * mtok
        with_cache = write_price_per_mtok * mtok + (n - 1) * read_price_per_mtok * mtok
        savings_pct = ((no_cache - with_cache) / no_cache) * 100 if no_cache > 0 else 0
        results[n] = {
            "no_cache_cost": round(no_cache, 4),
            "with_cache_cost": round(with_cache, 4),
            "savings_pct": round(savings_pct, 1),
        }

    return {
        "breakeven_reads": round(breakeven_n, 2),
        "breakeven_reads_int": int(breakeven_n) + 1 if breakeven_n % 1 > 0 else int(breakeven_n),
        "scenarios": results,
        "breakeven_in_5min": breakeven_n <= 5,  # 假设 5 分钟内能完成 N 次读取
    }


# 示例
result = cache_breakeven_analysis(3.75, 0.30, 3.00, 100_000)
print(f"盈亏平衡点: {result['breakeven_reads']} 次读取 (取整: {result['breakeven_reads_int']})")
for n, data in result["scenarios"].items():
    print(f"  N={n:3d}: 无缓存=${data['no_cache_cost']:.4f}, 缓存=${data['with_cache_cost']:.4f}, 节省={data['savings_pct']}%")
```

**Node.js 参考实现：**

```typescript
interface BreakevenResult {
  breakevenReads: number;
  breakevenReadsInt: number;
  scenarios: Record<number, { noCacheCost: number; withCacheCost: number; savingsPct: number }>;
  breakevenIn5min: boolean;
}

function cacheBreakevenAnalysis(
  writePricePerMtok: number,
  readPricePerMtok: number,
  basePricePerMtok: number,
  cacheableTokens: number,
): BreakevenResult {
  const mtok = cacheableTokens / 1_000_000;
  const breakevenN = writePricePerMtok / (basePricePerMtok - readPricePerMtok);
  const scenarios = [5, 10, 50, 100];
  const results: Record<number, any> = {};

  for (const n of scenarios) {
    const noCache = n * basePricePerMtok * mtok;
    const withCache = writePricePerMtok * mtok + (n - 1) * readPricePerMtok * mtok;
    const savingsPct = noCache > 0 ? ((noCache - withCache) / noCache) * 100 : 0;
    results[n] = {
      noCacheCost: Math.round(noCache * 10000) / 10000,
      withCacheCost: Math.round(withCache * 10000) / 10000,
      savingsPct: Math.round(savingsPct * 10) / 10,
    };
  }

  return {
    breakevenReads: Math.round(breakevenN * 100) / 100,
    breakevenReadsInt: Math.ceil(breakevenN),
    scenarios: results,
    breakevenIn5min: breakevenN <= 5,
  };
}
```

---

## 第 9 章：Batch API

### 题目 1（理论）：MessageBatch 状态

| 状态 | 含义 | 转换条件 |
|------|------|---------|
| `in_progress` | 批次处理中 | 创建批次后自动进入 |
| `ended` | 所有请求处理完毕 | 批次中每个请求均完成（成功/失败/过期/取消） |
| `canceled` | 用户手动取消 | 调用 cancel 端点 |
| `expired` | 24 小时 SLA 到期 | 系统在 24 小时后自动标记 |

给定场景：500 succeeded + 3 errored + 2 canceled = 505 个请求已处理（全部完成）。

`processing_status` = **`ended`**（所有请求都已处理，没有待处理的请求）

`request_counts`：
- `processing`: 0
- `succeeded`: 500
- `errored`: 3
- `canceled`: 2
- `expired`: 0

### 题目 2（理论）：Batch API 计费规则

| Result Type | 是否计费 | 说明 |
|------------|:--:|------|
| `succeeded` | **是** | 按批次价格计费（标准价格的 50%） |
| `errored` | **否** | 请求未成功处理 |
| `canceled` | **否** | 批次取消，请求未发送给模型 |
| `expired` | **否** | 24 小时到期，请求未发送给模型 |

**费用计算（Claude Haiku 3.5, 100 输入 + 30 输出）：**
```
成功的 950 个请求：
  input: 950 × 100 / 1,000,000 × $0.40 = $0.038
  output: 950 × 30 / 1,000,000 × $2.00 = $0.057
其余 50 个 errored/expired：不计费

总费用 = $0.038 + $0.057 = $0.095
```

### 题目 3（编码）：retry_failed_requests

**Python 参考实现：**

```python
from batch_client import BatchClient, MessageRequest


def retry_failed_requests(
    client: BatchClient,
    original_requests: list[MessageRequest],
    batch_id: str,
) -> tuple[str, int]:
    """重试批次中因临时错误而失败的请求。"""
    # 获取结果
    results = client.get_batch_results(batch_id)

    # 筛选可重试的失败请求
    retryable_errors = {"overloaded_error", "internal_error", "api_error"}
    failed_ids = set()

    for r in results:
        if r.result_type == "errored":
            error_type = r.error.get("type", "")
            if error_type in retryable_errors:
                failed_ids.add(r.custom_id)

    # 从原始请求中找到对应的请求
    retry_requests = [
        req for req in original_requests
        if req.custom_id in failed_ids
    ]

    if not retry_requests:
        return ("", 0)

    # 创建新批次
    new_batch_id = client.create_batch(retry_requests)
    return (new_batch_id, len(retry_requests))


# 测试示例
# new_id, count = retry_failed_requests(client, requests, "msgbatch_01ABC...")
# print(f"创建重试批次 {new_id}，包含 {count} 个请求")
```

### 题目 4（编码）：estimate_batch_savings

**Python 参考实现：**

```python
# 定价表（每百万 token）
PRICING = {
    "claude-opus-4-7":       {"input": 5.00,  "output": 25.00},
    "claude-sonnet-4-6":     {"input": 3.00,  "output": 15.00},
    "claude-haiku-4-5":      {"input": 1.00,  "output": 5.00},
    "claude-haiku-3-5":      {"input": 0.80,  "output": 4.00},
}


def estimate_batch_savings(
    n: int,
    input_tokens: int,
    output_tokens: int,
    model: str,
) -> dict:
    """估算批次处理的成本节约。"""
    if model not in PRICING:
        raise ValueError(f"未知模型: {model}。支持的模型: {list(PRICING.keys())}")

    prices = PRICING[model]
    in_price = prices["input"]
    out_price = prices["output"]

    # 实时成本
    realtime_input = n * input_tokens / 1_000_000 * in_price
    realtime_output = n * output_tokens / 1_000_000 * out_price
    realtime_total = realtime_input + realtime_output

    # Batch 成本（50% 折扣）
    batch_input = n * input_tokens / 1_000_000 * (in_price * 0.5)
    batch_output = n * output_tokens / 1_000_000 * (out_price * 0.5)
    batch_total = batch_input + batch_output

    # 节约
    savings = realtime_total - batch_total
    savings_pct = round((savings / realtime_total) * 100, 1) if realtime_total > 0 else 0

    return {
        "model": model,
        "requests": n,
        "realtime_cost": round(realtime_total, 2),
        "batch_cost": round(batch_total, 2),
        "savings": round(savings, 2),
        "savings_pct": savings_pct,
    }


# 测试
for test in [
    (1000, 100, 50, "claude-haiku-4-5"),
    (10000, 5000, 1000, "claude-sonnet-4-6"),
    (100, 2000, 500, "claude-opus-4-7"),
]:
    result = estimate_batch_savings(*test)
    print(f"{result['model']}: 实时 ${result['realtime_cost']} → Batch ${result['batch_cost']} "
          f"节省 {result['savings_pct']}%")
```

---

## 第 10 章：Memory 与 Citations

### Q1：Memory Store 架构理解

**错误项：C**

"Memory Store 可以在会话运行中动态添加或移除" —— **错误**。

Memory Store 只能**在会话创建时**通过 `resources[]` 数组挂载，不能在会话运行中添加或移除。A、B、D 均正确：A（挂载为 `/mnt/memory/{name}`）、B（最多 8 个）、D（归档不可逆）。

### Q2：Citations 类型匹配

```
1. 纯文本文档 → c. char_location
2. PDF 文档    → b. page_location
3. 自定义内容  → a. content_block_location
```

### Q3：Dreaming 机制分析

**正确项：C**

"Dreaming 可以分析多达 100 个过往会话记录来发现模式" —— **正确**。

A 错误（Dreaming 不修改原始 Store，输出到新 Store）；B 错误（Dreaming 是异步后台任务，非实时同步）；D 错误（Dreaming 是 Research Preview，需要 `dreaming-2026-04-21` beta header）。

### Q4（编程）：Memory 去重

**Python 参考实现：**

```python
def deduplicate_memories(memories: list[dict]) -> list[str]:
    """识别内容重复的 Memory，返回建议删除的 memory_id 列表（保留最早的）。

    Args:
        memories: 包含 'id', 'path', 'content_sha256', 'created_at' 的字典列表

    Returns:
        建议删除的 memory_id 列表
    """
    # 按 content_sha256 分组
    sha_groups: dict[str, list[dict]] = {}
    for mem in memories:
        sha = mem["content_sha256"]
        sha_groups.setdefault(sha, []).append(mem)

    duplicates = []
    for sha, group in sha_groups.items():
        if len(group) > 1:
            # 按 created_at 排序，保留最早的
            group.sort(key=lambda m: m["created_at"])
            # 标记后续的为重复
            for dup in group[1:]:
                duplicates.append(dup["id"])

    return duplicates


# 测试
memories = [
    {"id": "mem_01", "path": "/prefs/a.md", "content_sha256": "abc123", "created_at": "2026-05-01"},
    {"id": "mem_02", "path": "/prefs/b.md", "content_sha256": "abc123", "created_at": "2026-05-02"},  # 重复!
    {"id": "mem_03", "path": "/prefs/c.md", "content_sha256": "def456", "created_at": "2026-05-01"},
    {"id": "mem_04", "path": "/prefs/d.md", "content_sha256": "abc123", "created_at": "2026-05-03"},  # 重复!
]

dups = deduplicate_memories(memories)
print(f"建议删除: {dups}")  # ['mem_02', 'mem_04'] -- mem_01 是最早的，保留
assert "mem_02" in dups
assert "mem_04" in dups
assert "mem_01" not in dups
assert "mem_03" not in dups
```

---

## 第 11 章：MCP 协议规范

### 题 1（概念）：JSON-RPC 2.0 消息类型与 MCP 约束

**四种消息类型的结构区别：**

| 类型 | id | method | result | error |
|------|:--:|:--:|:--:|:--:|
| Request | 有 | 有 | 无 | 无 |
| Response | 有（匹配请求） | 无 | 有 | 无 |
| Error | 有（匹配请求） | 无 | 无 | 有 |
| Notification | 无 | 有 | 无 | 无 |

**MCP 对 JSON-RPC 的特定约束（至少 3 条）：**

1. **`id` 不能为 `null`**：基础 JSON-RPC 允许 null id 表示通知，但 MCP 使用无 id 字段表示通知。
2. **`id` 在会话中不得重复**：同一方向上的每个请求 id 必须唯一。
3. **`initialize` 请求不得出现在批量数组中**：初始化完成前不能发送其他消息。
4. **仅支持对象和数组类型的 `params`**：不支持基础类型作为 params 顶层值。
5. **`result` 和 `error` 互斥**：一条消息中不能同时包含两者。

### 题 2（协议理解）：版本协商

**Server 的响应：**
```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "error": {
    "code": -32602,
    "message": "Unsupported protocol version",
    "data": {
      "supported": ["2024-11-05"],
      "requested": "2025-03-26"
    }
  }
}
```

**Client 收到后的行动：**
如果 Client 也支持 `2024-11-05`，它可以：
1. 使用 `2024-11-05` 重新发送 `initialize` 请求
2. 使用旧版本的 HTTP+SSE 传输（而非 Streamable HTTP）

如果 Client 不支持旧版本，它**应该断开连接**并报告错误。

### 题 3（比较）：MCP 三大原语

| 原语 | 控制方 | 场景 | 为什么区分 |
|------|--------|------|-----------|
| **Prompts** | 用户控制 | 斜杠命令、菜单选项、预置对话 | 用户知道何时需要一个特定的 Prompt 模板 |
| **Resources** | 应用控制 | 文件内容、数据库 Schema、Git 历史 | Host 知道何时需要附加某些资源 |
| **Tools** | 模型控制 | 查询 API、写入文件、执行计算 | LLM 最适合判断何时需要使用一个工具 |

**区分原因**：不同类型的上下文以最自然的方式被使用。如果所有交互都通过 Tools（模型控制），用户将失去对 Prompt 模板的主动选择权；如果所有交互都通过 Resources（应用控制），LLM 将失去自主发现和使用工具的能力。分层设计确保了每种类型的内容都能被最合适的决策者调用。

### 题 4（编码）：JSON-RPC 2.0 消息解析器

**参考本章的 `code/python/ch11/json_rpc.py`**。关键实现逻辑：

1. 验证 `jsonrpc == "2.0"`
2. 检查 `id` 存在性：有 id + 有 method + 无 result + 无 error → Request
3. 有 id + 有 result + 无 error → Response
4. 有 id + 有 error → Error
5. 无 id + 有 method → Notification
6. 同时有 result 和 error → 拒绝
7. id 为 null → 拒绝（MCP 约束）

### 题 5（安全分析）：MCP Host 安全措施

| 安全措施 | 防御威胁 |
|---------|---------|
| 1. **用户同意控制**：每次 Tool 调用前必须经过用户明确同意 | 恶意 Server 在用户不知情的情况下执行危险操作（文件删除、数据泄露） |
| 2. **工具输入可见性**：调用前向用户展示完整输入参数 | 恶意 Server 诱使 LLM 在工具参数中嵌入用户数据外泄 |
| 3. **Server 隔离**：每个 Server 连接之间严格隔离，不能互相访问 | 恶意 Server 通过侧信道窥探其他 Server 或查看完整对话历史 |
| 4. **LLM Sampling 审批**：用户必须明确批准所有 LLM 采样请求 | 恶意 Server 通过 Sampling 将用户上下文发送给第三方模型 |
| 5. **Input 清洗 + 输出验证**：对 Server 返回内容进行验证和过滤 | Tool Poisoning：恶意 Server 返回包含注入指令的结果 |
| 6. **Origin 验证 + 本地绑定**：HTTP Server 验证 Origin 头并绑定 127.0.0.1 | DNS 重绑定攻击、跨域请求伪造 |
| 7. **频率限制**：对 Tool 调用和资源访问实施速率限制 | 恶意或失控的 Server 发起拒绝服务攻击 |

---

## 第 12 章：MCP 实战构建

### 问题 1（能力协商）

**Server 响应中仅声明了 `tools` 能力**（未声明 `resources` 和 `prompts`）。因此：

- `resources/list` → Server 会返回 JSON-RPC 错误（`-32601 Method not found`），因为该方法是 `resources` 能力的一部分
- `prompts/list` → 同样返回 `-32601 Method not found`

Client 的正确行为：在 `initialize` 响应后，检查 `capabilities` 对象，只调用已声明能力对应的方法。如果 Client 依赖 `resources` 或 `prompts` 功能，应报告能力缺失并优雅降级。

### 问题 2（Task 状态机）

**Python 参考实现：**

```python
import time


async def simulate_task_lifecycle(
    client,
    tool_name: str,
    arguments: dict,
    max_wait: float = 60.0,
) -> dict:
    """提交 Task 并轮询直到完成、失败或超时。"""
    # 1. 提交 Task
    task_response = await client.submit_task(tool_name, arguments)
    task_id = task_response["task"]["taskId"]
    poll_interval = task_response["task"].get("pollInterval", 5000) / 1000.0
    elapsed = 0.0

    # 2. 轮询
    while elapsed < max_wait:
        status = await client.get_task_status(task_id)
        state = status["status"]

        if state == "completed":
            result = await client.get_task_result(task_id)
            return {"success": True, "result": result}
        elif state == "failed":
            return {
                "success": False,
                "error": status.get("statusMessage", "Task failed")
            }
        elif state == "cancelled":
            return {"success": False, "error": "Task was cancelled"}

        await asyncio.sleep(poll_interval)
        elapsed += poll_interval

    return {"success": False, "error": "timeout"}
```

### 问题 3（跨语言互操作）

**Node.js 参考实现：**

```typescript
import { MCPClient } from "./MCPClient.js";
import { spawn } from "child_process";
import { strict as assert } from "assert";

async function testCrossLanguage() {
  // 1. 连接 Python Server
  const client = new MCPClient();
  const serverProcess = spawn("python", ["mcp_server.py"]);
  await client.connectStdio(serverProcess);

  // 2. 初始化
  await client.initialize({
    protocolVersion: "2025-03-26",
    capabilities: {},
    clientInfo: { name: "node-test-client", version: "1.0.0" },
  });

  // 3. 列出工具
  const tools = await client.listTools();
  const toolNames = tools.tools.map((t: any) => t.name);
  assert(toolNames.includes("echo"), "echo 工具未注册");
  assert(toolNames.includes("add"), "add 工具未注册");
  assert(toolNames.includes("get_server_info"), "get_server_info 工具未注册");

  // 4. 测试 echo
  const echoResult = await client.callTool("echo", { message: "hello from node" });
  const echoText = echoResult.content[0].text;
  assert.equal(echoText, "hello from node");

  // 5. 测试 add
  const addResult = await client.callTool("add", { a: 40, b: 2 });
  const addValue = parseInt(addResult.content[0].text);
  assert.equal(addValue, 42);

  // 6. 测试 get_server_info
  const infoResult = await client.callTool("get_server_info", {});
  const info = JSON.parse(infoResult.content[0].text);
  assert.equal(info.language, "python");

  console.log("全部跨语言测试通过!");

  // 清理
  await client.close();
  serverProcess.kill();
}

testCrossLanguage().catch(console.error);
```

### 问题 4（设计）：Tools vs Resources 划分

**划分方案：**

| 能力 | 方式 | 理由 |
|------|------|------|
| 列出指定目录中的文件 | **Tool** | 需要参数化（路径），LLM 需要自主决定何时探索目录结构 |
| 读取指定文件的内容 | **Resource** | 简单的数据获取，不需要 LLM 决策，参数（路径）可通过 URI 表达 |
| 搜索包含特定关键词的文件 | **Tool** | 需要复杂参数（关键词、文件类型、路径范围），LLM 需要根据任务构造合适的搜索查询 |

**设计理由：**
- Tool 适合需要 LLM 构造参数和评估结果后决定下一步的场景（"我该搜索哪个目录？"）
- Resource 适合"已知道路径，只需要读取数据"的场景。URI 可以直接引用文件（`file:///project/src/main.rs`），Resource Templates 支持参数化（`file:///{path}`）
- 这种划分让 LLM 的能力得到充分利用（通过 Tools 做探索和决策），同时 Host 可以通过 Resources 高效地批量附加上下文

---

## 第 14 章：Agent SDK 与 Agent 模式

### 题目 1：Agent Loop 的四个阶段

| 阶段 | 职责 |
|------|------|
| **Perceive（感知）** | 将环境状态（用户输入、工具执行结果、中间上下文）组装为 LLM 可理解的 Messages 格式 |
| **Reason（推理）** | LLM 基于当前 Messages 进行推理，决定下一步行动（end_turn 或 tool_use） |
| **Act（执行）** | 如果模型要求工具调用，执行对应的工具函数，捕获结果 |
| **Observe（观察）** | 将工具执行结果注入 Messages 列表，形成新上下文，进入下一轮循环 |

### 题目 2：ReAct vs Plan-and-Execute

| 维度 | ReAct | Plan-and-Execute |
|------|-------|------------------|
| 规划时机 | 每步即时推理 | 一次性全局规划 |
| 灵活性 | 高——可随时调整 | 低——计划在开始后不易更改 |
| 可预测性 | 低——路径动态变化 | 高——执行路径明确 |
| 适合场景 | 路径不确定的任务（探索性研究、调试） | 步骤明确、可分解的任务（ETL、多文件修改） |

### 题目 3（编码）：最小 ReAct Loop

**Python 参考实现：**

```python
def react_loop(task: str, tools: dict, max_iterations: int = 10) -> str:
    """最小 ReAct Agent 循环。

    Args:
        task: 用户任务描述
        tools: 工具字典 {name: handler}
        max_iterations: 最大迭代次数

    Returns:
        Claude 的最终回复文本
    """
    import httpx

    api_key = os.environ["ANTHROPIC_API_KEY"]

    tool_definitions = [
        {
            "name": name,
            "description": handler.__doc__ or f"Execute {name}",
            "input_schema": {
                "type": "object",
                "properties": {"input": {"type": "string"}},
                "required": ["input"]
            }
        }
        for name, handler in tools.items()
    ]

    messages = [{"role": "user", "content": task}]

    for iteration in range(max_iterations):
        response = httpx.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json={
                "model": "claude-sonnet-4-6",
                "max_tokens": 4096,
                "messages": messages,
                "tools": tool_definitions,
            },
        ).json()

        stop_reason = response.get("stop_reason")

        # 自然结束
        if stop_reason == "end_turn":
            for block in response.get("content", []):
                if block["type"] == "text":
                    return block["text"]
            return str(response["content"])

        # 工具调用
        if stop_reason == "tool_use":
            # 添加 assistant 消息
            messages.append({
                "role": "assistant",
                "content": response["content"]
            })

            # 执行工具
            tool_results = []
            for block in response["content"]:
                if block["type"] == "tool_use":
                    tool_name = block["name"]
                    tool_input = block["input"]
                    try:
                        handler = tools[tool_name]
                        result = str(handler(tool_input))
                    except Exception as e:
                        result = f"Error: {e}"
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": block["id"],
                        "content": result,
                    })

            # 添加 tool_result 消息
            messages.append({
                "role": "user",
                "content": tool_results
            })
            continue

        # 其他 stop_reason
        return f"Loop ended with stop_reason: {stop_reason}"

    return f"Reached max iterations ({max_iterations})"
```

### 题目 4（编码）：Sub-Agent Orchestrator

**Python 参考实现：**

```python
from dataclasses import dataclass, field
from typing import Any


@dataclass
class SubAgentDefinition:
    name: str
    description: str
    system_prompt: str
    tools: list[str]


class SubAgentOrchestrator:
    """管理子 Agent 的注册、调用和结果综合。"""

    def __init__(self, main_system_prompt: str, main_tools: list[str]):
        self.main_system_prompt = main_system_prompt
        self.main_tools = main_tools
        self._sub_agents: dict[str, SubAgentDefinition] = {}

    def register_sub_agent(self, definition: SubAgentDefinition):
        self._sub_agents[definition.name] = definition

    def list_sub_agents(self) -> list[dict]:
        return [
            {"name": a.name, "description": a.description}
            for a in self._sub_agents.values()
        ]

    def execute_sub_agent(
        self, name: str, task: str, context: dict = None
    ) -> dict[str, Any]:
        """执行指定的子 Agent 并返回结果。"""
        agent = self._sub_agents.get(name)
        if not agent:
            return {"error": f"Sub-agent '{name}' not found"}

        # 构造子 Agent 的 Messages
        messages = [{"role": "user", "content": task}]

        # 实际执行（简化版）
        import httpx
        api_key = os.environ["ANTHROPIC_API_KEY"]

        tool_defs = [
            {"name": t, "description": f"Tool: {t}",
             "input_schema": {"type": "object", "properties": {}, "required": []}}
            for t in agent.tools
        ]

        response = httpx.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json={
                "model": "claude-sonnet-4-6",
                "max_tokens": 4096,
                "system": agent.system_prompt,
                "messages": messages,
                "tools": tool_defs if tool_defs else None,
            },
        )

        result = response.json()
        return {
            "agent": name,
            "content": result.get("content", []),
            "stop_reason": result.get("stop_reason"),
        }

    def synthesize(self, sub_results: list[dict]) -> str:
        """综合多个子 Agent 的结果。"""
        # 简化版：拼接所有结果
        parts = []
        for r in sub_results:
            if "error" in r:
                parts.append(f"[{r['agent']}] Error: {r['error']}")
            else:
                text = " ".join(
                    b.get("text", "") for b in r.get("content", [])
                    if b.get("type") == "text"
                )
                parts.append(f"[{r['agent']}] {text}")
        return "\n\n".join(parts)
```

### 题目 5（设计）：上下文窗口管理

**策略设计：**

1. **分层缓存策略**：
   - System Prompt（~3K tokens）标记 `cache_control` —— 每次命中，节省 90%
   - 工具定义（~2K tokens）紧随其后

2. **监控机制**：
   - 每轮迭代后计算 `input_tokens` 累计
   - 当 `used_tokens > context_window × 0.75` 时触发 Compaction

3. **Compaction 触发与执行**：
   ```
   触发条件：used_tokens > 150K (75% of 200K)
   保留：System Prompt + 最近的 5 轮完整对话 + 原始 Task Description
   压缩：对第 6-45 轮的对话历史进行摘要（保留目标、决策、状态）
   丢弃：完全冗余的工具输出（如成功状态确认）
   ```

4. **工具输出裁剪**：
   - 每次 `tool_result` 超过 8K 字符时，自动裁剪为头尾各 4K
   - 在裁剪点插入 `... (截断 N 字符) ...`

5. **验证策略有效性**：
   - 记录每次 Compaction 前后的 token 总数
   - 监控 Agent 的"任务完成率"（Compaction 前 vs 后）
   - 如果 Compaction 后任务完成率显著下降，增加保留轮数或降低压缩激进程度

---

## 第 17 章：生产实践

### 题 1：Token Bucket vs Sliding Window

| 维度 | Token Bucket | Sliding Window |
|------|-------------|----------------|
| 算法 | 令牌以固定速率连续补充，请求消耗令牌 | 记录每个请求时间戳，淘汰窗口外的旧记录 |
| 优势 | 连续补充，平滑；O(1) 操作；与 Anthropic 服务端一致 | 精确的窗口内计数，严格保证不超限 |
| 劣势 | 短时间突发可能超限 | 内存开销 O(窗口内请求数)；无"容量可用"概念 |
| 适用场景 | **客户端主动限流**（行为可预测）；高吞吐场景（>1000 RPM） | **网关层限流**（精确控制）；精确的突发控制 |

### 题 2：熔断器状态机

**三种状态：**
- **CLOSED**（关闭）：正常状态，允许所有请求通过。连续失败计数。
- **OPEN**（打开）：拒绝所有请求，立即返回错误（不接触远程服务）。持续 `reset_timeout` 秒（建议 30s）。
- **HALF_OPEN**（半开）：允许有限探测请求通过，测试服务是否恢复。

**转换条件：**
- CLOSED → OPEN：连续失败次数 >= `failure_threshold`（建议 5 次）
- OPEN → HALF_OPEN：经过 `reset_timeout`（建议 30s）
- HALF_OPEN → CLOSED：探测请求成功 >= `success_threshold`（建议 2 次）
- HALF_OPEN → OPEN：探测请求失败 → 重新进入 OPEN 状态

**为什么需要 HALF_OPEN？**

如果没有 HALF_OPEN，熔断器从 OPEN 直接回到 CLOSED 会导致"立即恢复到全负载"——如果服务只是暂时恢复、随即又过载，请求会再次失败，形成振荡。HALF_OPEN 通过有限探测来验证服务是否**真正**恢复，避免了振荡。

### 题 3：分层防注入策略

| 层次 | 措施 | 解决的问题 |
|------|------|-----------|
| **第 1 层：输入清洗** | 移除 null 字节和控制字符（`\x00-\x1f`）；规范化 Unicode | 基础的格式攻击、编码混淆 |
| **第 2 层：模式检测** | 正则表达式检测已知注入模式（"ignore previous instructions"、"you are now DAN"、XML 标签注入等） | 常见攻击模式的快速阻断 |
| **第 3 层：指令隔离** | 将用户输入包裹在 `<user_input>` 标签中，System Prompt 中声明标签内内容为不可信数据 | 核心防御层——结构化分离指令和数据，即使模式检测被绕过，模型仍能将用户输入视为数据 |
| **第 4 层：最小权限** | 工具调用权限限定在任务必需的最小集合 | 即使注入成功，攻击者也无法利用超出范围的能力 |

### 题 4（编码）：Token Bucket Rate Limiter

**Python 参考实现：**

```python
import time
import threading


class TokenBucketRateLimiter:
    """三维度令牌桶限流器（RPM + ITPM + OTPM），原子消耗。"""

    def __init__(self, capacity_rpm: int, capacity_itpm: int, capacity_otpm: int):
        self._capacity = {
            "rpm": capacity_rpm,
            "itpm": capacity_itpm,
            "otpm": capacity_otpm,
        }
        self._tokens = dict(self._capacity)
        self._last_refill = time.monotonic()
        self._lock = threading.Lock()

    def _refill(self):
        now = time.monotonic()
        elapsed = now - self._last_refill
        for key, cap in self._capacity.items():
            refill_rate = cap / 60.0
            self._tokens[key] = min(cap, self._tokens[key] + elapsed * refill_rate)
        self._last_refill = now

    def consume(self, requests: int = 0, input_tokens: int = 0, output_tokens: int = 0) -> bool:
        """原子消耗：三个维度都有足够容量时才消耗。"""
        with self._lock:
            self._refill()
            needed = {
                "rpm": requests,
                "itpm": input_tokens,
                "otpm": output_tokens,
            }
            # 先检查
            for key, need in needed.items():
                if self._tokens[key] < need:
                    return False
            # 原子消耗
            for key, need in needed.items():
                self._tokens[key] -= need
            return True

    def available(self) -> tuple:
        """返回三个维度的可用容量。"""
        with self._lock:
            self._refill()
            return (
                int(self._tokens["rpm"]),
                int(self._tokens["itpm"]),
                int(self._tokens["otpm"]),
            )

    def time_until_available(self, requests: int = 0, input_tokens: int = 0) -> float:
        """估算等待时间（秒）。"""
        with self._lock:
            self._refill()
            wait_times = []
            needed = {"rpm": requests, "itpm": input_tokens}
            for key, need in needed.items():
                if need > 0 and self._tokens[key] < need:
                    deficit = need - self._tokens[key]
                    rate = self._capacity[key] / 60.0
                    wait_times.append(deficit / rate)
            return max(wait_times) if wait_times else 0
```

### 题 5（编码）：BudgetController

**Python 参考实现：**

```python
from dataclasses import dataclass, field
from enum import Enum, auto
import time


class BudgetDecision(Enum):
    ALLOW = auto()
    WARN = auto()
    BLOCK = auto()
    DOWNGRADE = auto()


@dataclass
class BudgetConfig:
    hard_limit: float = 500.0         # 月度预算
    warn_threshold: float = 0.75      # 告警线
    auto_downgrade: bool = True       # 自动降级


class BudgetController:
    """支持硬限制、软告警和自动模型降级的预算控制器。"""

    DOWNGRADE_CHAIN = {
        "claude-opus-4-7": "claude-sonnet-4-6",
        "claude-sonnet-4-6": "claude-haiku-4-5",
    }

    PRICE_TABLE = {
        "claude-opus-4-7":  {"input": 5.00,  "output": 25.00},
        "claude-sonnet-4-6": {"input": 3.00,  "output": 15.00},
        "claude-haiku-4-5":  {"input": 1.00,  "output": 5.00},
    }

    def __init__(self, config: BudgetConfig):
        self.config = config
        self._spent: float = 0.0
        self._model_spending: dict[str, float] = {}
        self._events: list[dict] = []

    @property
    def spent(self) -> float:
        return self._spent

    @property
    def remaining(self) -> float:
        return max(0, self.config.hard_limit - self._spent)

    @property
    def utilization_pct(self) -> float:
        return (self._spent / self.config.hard_limit) * 100

    def check(self, model: str, input_tokens: int = 0, output_tokens: int = 0) -> tuple:
        """调用前的预算检查。返回 (decision, recommended_model)。"""
        prices = self.PRICE_TABLE.get(model, {"input": 3.0, "output": 15.0})
        projected_cost = (
            input_tokens / 1_000_000 * prices["input"]
            + output_tokens / 1_000_000 * prices["output"]
        )

        # 硬限制
        if self._spent + projected_cost >= self.config.hard_limit:
            return (BudgetDecision.BLOCK, model)

        # 超过告警线
        if self._spent >= self.config.hard_limit * self.config.warn_threshold:
            if self.config.auto_downgrade and model in self.DOWNGRADE_CHAIN:
                downgraded = self.DOWNGRADE_CHAIN[model]
                return (BudgetDecision.DOWNGRADE, downgraded)
            return (BudgetDecision.WARN, model)

        return (BudgetDecision.ALLOW, model)

    def record(self, model: str, input_tokens: int = 0, output_tokens: int = 0):
        """根据实际 token 消耗更新预算。"""
        prices = self.PRICE_TABLE.get(model, {"input": 3.0, "output": 15.0})
        cost = (
            input_tokens / 1_000_000 * prices["input"]
            + output_tokens / 1_000_000 * prices["output"]
        )
        self._spent += cost
        self._model_spending[model] = self._model_spending.get(model, 0) + cost
        self._events.append({
            "timestamp": time.time(),
            "model": model,
            "cost": cost,
            "spent": self._spent,
        })

    def get_summary(self) -> dict:
        return {
            "spent": round(self._spent, 2),
            "remaining": round(self.remaining, 2),
            "utilization_pct": round(self.utilization_pct, 1),
            "limit": self.config.hard_limit,
        }

    def get_model_breakdown(self) -> dict:
        return {
            model: round(cost, 2)
            for model, cost in self._model_spending.items()
        }
```

---

*以上涵盖了本书 17 章中全部有自测题章节的参考答案。部分章节（第 7、13、15、16 章为占位章节）无独立自测题。每题提供了理论和编码两种形式的完整解答。*
