# 第 10 章：Memory 与 Citations —— 持久上下文与信息来源追溯

## 10.1 概念全景

### 10.1.1 Memory 与 Citations 在 Agent 架构中的定位

在前几章中，我们探讨了 Claude 如何通过 Messages API 理解用户意图（第 2 章）、如何利用 Tool Use 执行外部操作（第 6 章）、以及如何通过 Streaming 和 Extended Thinking 实现逐步推理（第 5 章）。然而，一个完整的企业级 Agent 还需要解决两个核心难题：

1. **跨会话记忆**：当一个 Agent 会话结束并重启时，如何让 Claude 记住上一次会话中学到的用户偏好、项目约定、领域知识？

2. **信息来源追溯**：当 Claude 基于多个文档、网页或内容块给出答案时，如何让用户验证每个结论的来源？

本章介绍的 **Memory API** 和 **Citations API** 正是 Anthropic 对这两个问题的官方解决方案。

**Memory API** 属于 **Claude Managed Agents**（2026 年 4 月发布，Public Beta）的核心组件。它提供了跨会话持久化存储——Agent 可以在一个会话中写入内容，在另一个会话中读取，甚至通过 **Dreaming（梦境）** 机制在"睡眠"期间自动整理和优化记忆。

**Citations API** 是 Messages API 的扩展功能（从 Claude 3.5 Sonnet 开始支持），让 Claude 在引用文档、PDF 或自定义内容时，自动附加精确的引用位置（字符级、页码级或内容块级）。

两者共同构成了 Anthropic 生态的"信任基础设施"——Memory 让 Claude 保持上下文连续性，Citations 让 Claude 的输出可验证。

### 10.1.2 核心概念速览

| 概念 | 一句话解释 |
|------|-----------|
| Memory Store | 一个工作空间级别的持久化文本存储，Container 内挂载为 `/mnt/memory/{name}` |
| Memory | Store 中的单个文件，由路径寻址，上限 100 KB（约 25K tokens） |
| Memory Version | 每次变更的不可变快照（`memver_...`），保留 30 天，支持审计与回滚 |
| Dreaming | 异步后台任务，读取记忆和会话记录，输出全新的优化记忆，不修改原始 Store |
| Citations | 文本块附带的引用信息，包含 `cited_text`、`document_title` 和精确位置 |
| Citation Types | `char_location`（纯文本/字符）、`page_location`（PDF/页码）、`content_block_location`（自定义内容块） |
| Resources Array | 会话创建时通过 `resources[]` 数组挂载 Memory Store（上限 8 个） |

### 10.1.3 架构全景图

```
┌─────────────────────────────────────────────────────────────────┐
│                    Claude Managed Agent                         │
│                                                                 │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐      │
│  │  Session A   │    │  Session B   │    │  Dream Job   │      │
│  │  (active)    │    │  (active)    │    │  (async)     │      │
│  │              │    │              │    │              │      │
│  │  reads from──┼────┼──reads from──┼────┼──reads from──┤      │
│  │  writes to───┼────┼──writes to───┼────┤              │      │
│  └──────┬───────┘    └──────┬───────┘    └──────┬───────┘      │
│         │                   │                   │               │
│         └───────────────────┼───────────────────┘               │
│                             │                                   │
│                    ┌────────▼────────┐                          │
│                    │  Memory Store   │                          │
│                    │  (read_write)   │                          │
│                    │                 │                          │
│                    │ /preferences/   │                          │
│                    │ /knowledge/     │                          │
│                    │ /errors/        │                          │
│                    └────────┬────────┘                          │
│                             │                                   │
│                    ┌────────▼────────┐                          │
│                    │  Dream Output   │                          │
│                    │  (new store)    │                          │
│                    │  - de-duped     │                          │
│                    │  - updated      │                          │
│                    │  - patterns     │                          │
│                    └─────────────────┘                          │
└─────────────────────────────────────────────────────────────────┘
```

```
Citations 数据流：
User Documents → Claude Messages API → TextBlock + Citations[]
                                         │
                                         ├── char_location: {cited_text, start_char_index, end_char_index}
                                         ├── page_location: {cited_text, start_page_number, end_page_number}
                                         ├── content_block_location: {cited_text, start_block_index, end_block_index}
                                         ├── web_search_result_location: {cited_text, url, title}
                                         └── search_result_location: {cited_text, source, search_result_index}
```

---

## 10.2 协议规范

### 10.2.1 Memory API

Memory API 是 Claude Managed Agents 的一部分，通过 `managed-agents-2026-04-01` beta header 访问。SDK 会自动设置该 header。

#### 10.2.1.1 Memory Store 概念与生命周期

一个 **Memory Store** 是工作空间级别的文本文档集合，针对 Claude 的访问模式进行了优化。每个 Store 的生命周期如下：

```
创建(Create) → 活跃使用(Active) → 归档(Archive) → 删除(Delete)
                    │                    │
                    │                    └── 只读，不可挂载到新会话
                    │                        （不可逆操作）
                    │
                    ├── 挂载到 Session（resources[]）
                    ├── 读写 Memory
                    ├── 创建 Version（审计轨迹）
                    └── Dreaming（生成优化版 Store）
```

**关键约束（Beta 阶段）：**

| 限制项 | 数值 |
|--------|------|
| 每组织 Store 数量 | 1,000 |
| 每 Store Memory 数量 | 2,000 |
| 每 Store 存储容量 | 100 MB |
| 每 Memory 大小上限 | 100 KB（约 25K tokens） |
| 每 Store 版本数量 | 250,000 |
| 每 Session 可挂载 Store | 8 个 |

**Memory Store 字段：**

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | `string` | Store ID（`memstore_...`），用于挂载和 API 调用 |
| `name` | `string` | Store 名称 |
| `description` | `string` | Store 描述，传递给 Agent 以说明内容用途 |
| `created_at` | `timestamp` | 创建时间（RFC 3339） |
| `archived_at` | `timestamp` | 归档时间（仅已归档的 Store） |

#### 10.2.1.2 Memory Store CRUD（REST API）

Memory API 的所有操作均通过 REST 端点完成。下表列出了完整的 CRUD 操作：

| 操作 | HTTP 方法 | 端点 | SDK 方法 | 说明 |
|------|-----------|------|----------|------|
| **创建 Store** | POST | `/v1/memory_stores` | `client.beta.memory_stores.create(name, description)` | 返回 `memstore_...` ID |
| **列举 Store** | GET | `/v1/memory_stores` | `client.beta.memory_stores.list(include_archived)` | 默认不包含已归档 Store |
| **获取 Store** | GET | `/v1/memory_stores/{id}` | `client.beta.memory_stores.retrieve(id)` | 返回完整元数据 |
| **更新 Store** | POST | `/v1/memory_stores/{id}` | `client.beta.memory_stores.update(id, ...)` | 更新 name/description |
| **归档 Store** | POST | `/v1/memory_stores/{id}/archive` | `client.beta.memory_stores.archive(id)` | 单向操作，不可逆 |
| **删除 Store** | DELETE | `/v1/memory_stores/{id}` | `client.beta.memory_stores.delete(id)` | 永久删除 Store + 所有 Memory + Version |

```python
# 创建 Store 示例
store = client.beta.memory_stores.create(
    name="User Preferences",
    description="Per-user preferences and project context.",
)
print(store.id)  # memstore_01Hx...

# 归档 Store（不可逆）
client.beta.memory_stores.archive(store.id)
```

**关于归档：** 归档将 Store 设为只读状态，并阻止其挂载到新会话。已有会话继续可以读取。这是一个**单向操作**——没有"取消归档"功能。

#### 10.2.1.3 Memory CRUD（Store 内的文件操作）

Memory 是 Store 内的文本文件，通过路径（path）寻址。每个 Memory 上限 100 KB。

| 操作 | SDK 方法 | 说明 |
|------|----------|------|
| **创建** | `client.beta.memory_stores.memories.create(store_id, path, content)` | 不会覆盖已存在文件 |
| **写入(Upsert)** | `client.beta.memory_stores.memories.write(store_id, path, content)` | 创建或覆盖；支持 `precondition: {"type": "not_exists"}` |
| **读取** | `client.beta.memory_stores.memories.retrieve(memory_id, store_id)` | 返回完整内容 + 元数据 |
| **列举** | `client.beta.memory_stores.memories.list(store_id, path_prefix, order_by, depth)` | 支持目录式浏览，通过 `path_prefix` 过滤 |
| **更新** | `client.beta.memory_stores.memories.update(memory_id, store_id, content, path, precondition)` | 可修改内容、路径（重命名）或两者 |
| **删除** | `client.beta.memory_stores.memories.delete(memory_id, store_id)` | 支持 `expected_content_sha256` 条件删除 |

**Memory 对象结构：**

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | `string` | Memory ID（`mem_...`） |
| `memory_store_id` | `string` | 所属 Store ID |
| `path` | `string` | Memory 的路径（如 `/preferences/formatting.md`） |
| `content` | `string` | Memory 的文本内容 |
| `content_sha256` | `string` | 内容的 SHA256 哈希值 |
| `content_size_bytes` | `int64` | 内容字节数 |
| `memory_version_id` | `string` | 当前版本 ID（`memver_...`） |
| `created_at` | `timestamp` | 创建时间 |
| `updated_at` | `timestamp` | 最后更新时间 |
| `type` | `string` | 固定值：`"memory"` |

**种子化（Seeding）：** 可以在任何 Agent 运行之前预填充 Store：

```python
# 预填充参考材料
client.beta.memory_stores.memories.create(
    store.id,
    path="/formatting_standards.md",
    content="All reports use GAAP formatting. Dates are ISO-8601...",
)
```

**路径组织建议：** 将记忆组织为多个小文件，而不是少量大文件。推荐的目录结构：

```
/mnt/memory/user-preferences/
├── formatting.md          # 格式偏好
├── language.md            # 语言偏好
├── project_context.md     # 项目上下文
└── known_errors/
    ├── build_issues.md    # 构建相关问题
    └── api_pitfalls.md    # API 陷阱记录
```

#### 10.2.1.4 Memory 组织与搜索

Memory API 提供了强大的目录式浏览能力。`list` 端点支持以下参数：

| 参数 | 类型 | 说明 |
|------|------|------|
| `path_prefix` | `string` | 按路径前缀过滤（如 `/preferences/` 仅返回该目录下的文件） |
| `order_by` | `string` | 排序字段，如 `"path"` |
| `order` | `string` | `"asc"` 或 `"desc"` |
| `depth` | `int64` | 递归深度限制 |
| `view` | `string` | 控制返回 Memory 或 Memory Prefix |
| `limit` | `int64` | 分页大小 |
| `page` | `string` | 分页游标 |

**路径前缀搜索：** 通过在 `path_prefix` 末尾添加 `/`，可以限定在特定目录范围内：

```python
# 只列出 /preferences/ 目录下的记忆
page = client.beta.memory_stores.memories.list(
    store.id,
    path_prefix="/preferences/",  # 目录级别过滤
    order_by="path",
    depth=2,
)
for item in page.data:
    print(item.type, item.path)
```

返回结果中的 `type` 字段可以是 `"memory"` 或 `"memory_prefix"` ——后者代表一个目录节点。

#### 10.2.1.5 乐观并发控制

对于多 Agent 并发写入同一 Store 的场景，Memory API 提供了乐观并发控制：

```python
# 1. 读取当前状态
mem = client.beta.memory_stores.memories.retrieve(mem_id, memory_store_id=store_id)

# 2. 使用 content_sha256 作为前置条件进行更新
client.beta.memory_stores.memories.update(
    memory_id=mem.id,
    memory_store_id=store.id,
    content="CORRECTED: Always use 2-space indentation.",
    precondition={"type": "content_sha256", "content_sha256": mem.content_sha256},
)
```

如果在你读取和更新之间，其他 Agent 修改了该 Memory，`content_sha256` 将不匹配，API 将拒绝更新。此时应重新读取最新状态并重试。

#### 10.2.1.6 Memory Version 审计轨迹

每次 Memory 变更都会创建一个不可变的 **Memory Version**（`memver_...`），构成完整的审计轨迹。

**Version 生命周期：**

```
Memory 写入 ──→ Version 创建（memver_...）──→ 保留 30 天 ──→ 自动清理
                                                       │
                                        ┌──────────────┘
                                        │
                                  Redact（内容擦除）
                                  保留 who/what/when 元数据
```

| Version 操作 | SDK 方法 | 说明 |
|---|---|---|
| **列举版本** | `memory_versions.list(store_id, memory_id, operation, session_id, created_at_gte/lte)` | 按 Memory、操作类型、会话、时间范围过滤 |
| **获取版本** | `memory_versions.retrieve(version_id, store_id)` | 返回完整内容体 |
| **擦除版本** | `memory_versions.redact(version_id, store_id)` | 清除内容但保留审计元数据 |

**版本对象结构：**

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | `string` | Version ID（`memver_...`） |
| `memory_id` | `string` | 所属 Memory ID |
| `memory_store_id` | `string` | 所属 Store ID |
| `content` | `string` | 该版本的内容快照 |
| `operation` | `string` | 操作类型：`"create"`, `"update"`, `"delete"` |
| `session_id` | `string` | 执行操作的会话 ID |
| `created_at` | `timestamp` | 版本创建时间 |

**回滚机制：** 没有专用的"恢复"端点。要回滚，获取所需版本，然后用其内容写回：

```python
# 获取历史版本
version = client.beta.memory_stores.memory_versions.retrieve(
    version_id, memory_store_id=store.id
)

# 写回以"恢复"
client.beta.memory_stores.memories.update(
    memory_id=mem.id,
    memory_store_id=store.id,
    content=version.content,
)
```

**Redact（合规擦除）：** 当需要移除敏感信息（密钥泄露、PII、用户删除请求）但必须保留审计记录时，使用 Redact：

```python
client.beta.memory_stores.memory_versions.redact(
    version_id, memory_store_id=store.id
)
```

注意：如果目标 Version 是当前 Memory 的 HEAD，不能直接 Redact。需要先写入新版本（或删除 Memory），然后再 Redact 旧版本。

#### 10.2.1.7 Session 与 Memory 的交互模式

**挂载 Memory Store 到 Session：**

Memory Store 只能**在会话创建时**通过 `resources[]` 数组挂载，不能在会话运行中添加或移除：

```python
session = client.beta.sessions.create(
    agent=agent.id,
    environment_id=environment.id,
    resources=[
        {
            "type": "memory_store",
            "memory_store_id": store.id,
            "access": "read_write",  # 默认为 read_write
            "instructions": "User preferences and project context. Check before starting any task.",
        }
    ],
)
```

| 参数 | 说明 |
|------|------|
| `type` | 固定值：`"memory_store"` |
| `memory_store_id` | Store ID（`memstore_...`） |
| `access` | `"read_write"`（默认）或 `"read_only"` |
| `instructions` | 可选，上限 4,096 字符，本次会话特定的使用指导 |

**容器内挂载：** 每个挂载的 Store 在 Container 中作为 `/mnt/memory/` 下的目录出现。Agent 使用标准的 Agent Toolset 读写它。系统提示中会自动添加每个挂载点的说明（路径、访问模式、Store 描述和 instructions）。

**安全考量：**

> 如果 Agent 处理不可信输入（用户提供的提示、抓取的网页内容、第三方工具输出），成功的提示注入可能将恶意内容写入 Store。后续会话会将这些内容视为可信记忆读取。对于参考资料、共享查询等场景，使用 `read_only` 访问模式。

**多 Store 使用场景：**

1. **共享参考资料**：一个只读 Store 挂载到多个会话（标准、约定、领域知识），与每个会话自己的读写 Store 分开
2. **映射产品结构**：每个终端用户、团队或项目一个 Store，共享同一 Agent 配置
3. **不同生命周期**：某些 Store 的生命周期超过单次会话，或需要独立归档

#### 10.2.1.8 "Dreaming" 记忆整合机制

**Dreaming** 于 2026 年 5 月 6 日作为 Research Preview 发布，是 Claude Managed Agents 最具创新性的功能。它让 Agent 在"睡眠"期间（会话间隙）异步处理记忆。

**核心原理：**

Dreaming 是一个异步后台作业，读取一个 Memory Store 和多达 100 个过往会话记录，然后输出一个**全新的、经过优化的 Memory Store**，而不修改原有的 Store。

**Dreaming 执行三项核心任务：**

1. **合并重复与清除噪音**：将冗余条目合并为一条简洁记录
2. **替换过时内容**：用最新信息替换已失效的内容
3. **跨会话模式发现**：识别重复出现的错误、最佳工作流、多个 Agent 间的共享偏好

**API 调用：**

需要 `managed-agents-2026-04-01` 和 `dreaming-2026-04-21` 两个 beta header：

```bash
curl -s https://api.anthropic.com/v1/dreams \
  -H "x-api-key: $ANTHROPIC_API_KEY" \
  -H "anthropic-version: 2023-06-01" \
  -H "anthropic-beta: managed-agents-2026-04-01,dreaming-2026-04-21" \
  -H "content-type: application/json" \
  -d '{
    "inputs": [
      {"type": "memory_store", "memory_store_id": "'$STORE'"},
      {"type": "sessions", "session_ids": ["'$SESSION_A'", "'$SESSION_B'"]}
    ],
    "model": "claude-opus-4-7",
    "instructions": "Focus on durable coding preferences; drop one-off debugging notes."
  }'
```

| 参数 | 说明 |
|------|------|
| `inputs` | 输入源：`memory_store` 类型（必需）和 `sessions` 类型（可选，上限 100 个会话） |
| `model` | 用于 Dreaming 的模型（`claude-opus-4-7` 或 `claude-sonnet-4-6`） |
| `instructions` | 可选，上限 4,096 字符，指导 Dreaming 关注的重点 |

**安全保障设计：**

- **不可变输入**：Dreaming 永远不会修改原始 Store，始终输出到新 Store
- **审查后应用**：开发者可以在变更生效前审查结果，或配置自动批准
- **实时流式**：Dream 暴露 `session_id` 和事件流，可以实时观察（或取消）

**适用时机：**

- 经过多轮用户交互后，自动提取关键偏好
- 跨会话发现团队的编码规范
- 每晚定期运行，保持记忆库的精简和准确
- 在有大量会话历史的 Agent 中定期"清理"记忆

---

### 10.2.2 Citations API

Citations API 是 Messages API 的内置功能，支持 Claude 3.5 Sonnet、Claude 3.5 Haiku 和 Claude Sonnet 4.6 等模型。

#### 10.2.2.1 Citations 协议概览

Citations API 的核心思想很简单：当你向 Claude 提供文档（纯文本、PDF 或自定义内容块），并请求它基于这些文档回答问题时，Claude 不仅给出答案，还**精确标注每个结论的来源**。

这与基于 prompt 的引用技术（让模型自己输出引用文本）有本质区别：

| 维度 | Citations API | Prompt 式引用 |
|------|--------------|--------------|
| Token 效率 | 不增加输出 token（结构化返回） | 需要在输出中重复原文 |
| 幻觉防护 | 不会引用未提供的文档或位置 | 可能编造不存在的引用 |
| 召回率与精度 | 测试中表现更高 | 较低 |
| 集成复杂度 | 需解析 `citations` 字段 | 纯文本处理 |

#### 10.2.2.2 Document 类型与对应的 Citation 格式

Citations API 支持三种文档类型，每种产生不同格式的 Citation：

**文档类型对照表：**

| 文档类型 | `source.type` | 分块方式 | Citation 格式 | 位置字段 |
|----------|---------------|----------|---------------|----------|
| 纯文本 | `"text"` | 自动按句子分块 | `char_location` | `start_char_index` / `end_char_index` |
| PDF | `"base64"` (base64编码) | 自动按句子分块 | `page_location` | `start_page_number` / `end_page_number` |
| 自定义内容 | `"content"` | 用户自定义分块 | `content_block_location` | `start_block_index` / `end_block_index` |

**每种 Citation 类型的完整字段：**

```
BetaCitationCharLocation:
  - cited_text: string       # 被引用的原文
  - document_index: int64    # 文档在列表中的索引
  - document_title: string   # 文档标题
  - start_char_index: int64  # 起始字符位置
  - end_char_index: int64    # 结束字符位置
  - file_id: string          # 文件标识符
  - type: "char_location"    # 固定值

BetaCitationPageLocation:
  - cited_text: string       # 被引用的原文
  - document_index: int64    # 文档索引
  - document_title: string   # 文档标题
  - start_page_number: int64 # 起始页码（1-indexed）
  - end_page_number: int64   # 结束页码
  - file_id: string          # 文件标识符
  - type: "page_location"    # 固定值

BetaCitationContentBlockLocation:
  - cited_text: string       # 被引用的原文
  - document_index: int64    # 文档索引
  - document_title: string   # 文档标题
  - start_block_index: int64 # 起始内容块索引
  - end_block_index: int64   # 结束内容块索引
  - file_id: string          # 文件标识符
  - type: "content_block_location"  # 固定值
```

**额外 Citation 类型（用于搜索类结果）：**

```
BetaCitationsWebSearchResultLocation:
  - cited_text: string       # 被引用的文本
  - encrypted_index: string  # 加密的搜索结果索引
  - title: string            # 网页标题
  - url: string              # 网页 URL
  - type: "web_search_result_location"

BetaCitationSearchResultLocation:
  - cited_text: string       # 被引用的文本
  - search_result_index: int64  # 搜索结果索引
  - source: string           # 搜索来源
  - start_block_index: int64 # 起始块索引
  - end_block_index: int64   # 结束块索引
  - title: string            # 结果标题
  - type: "search_result_location"
```

#### 10.2.2.3 Citations Content Block Delta 规范

在流式响应中，Citation 数据通过 `content_block_delta` 事件传递。Delta 类型为 `"citations_delta"`：

```json
{
  "type": "content_block_delta",
  "index": 0,
  "delta": {
    "type": "citations_delta",
    "citation": {
      "type": "char_location",
      "cited_text": "Once your order ships, you'll receive an email...",
      "document_index": 0,
      "document_title": "Order Tracking Information",
      "start_char_index": 0,
      "end_char_index": 120
    }
  }
}
```

在非流式响应中，Citation 作为 `TextBlock` 的 `citations` 数组直接返回：

```json
{
  "type": "text",
  "text": "You'll receive an email with your tracking number...",
  "citations": [
    {
      "type": "char_location",
      "cited_text": "Once your order ships, you'll receive an email...",
      "document_title": "Order Tracking Information"
    }
  ]
}
```

#### 10.2.2.4 请求格式

要启用 Citations，在文档定义中设置 `"citations": {"enabled": true}`：

**纯文本文档：**

```python
documents = [
    {
        "type": "document",
        "source": {
            "type": "text",
            "media_type": "text/plain",
            "data": "Document body text here..."
        },
        "title": "Document Title",
        "citations": {"enabled": True},
    }
]

response = client.messages.create(
    model="claude-sonnet-4-6",
    max_tokens=1024,
    messages=[
        {"role": "user", "content": documents},
        {"role": "user", "content": [{"type": "text", "text": "What does the document say?"}]},
    ],
)
```

**PDF 文档：**

```python
import base64

with open("document.pdf", "rb") as f:
    pdf_data = base64.b64encode(f.read()).decode()

documents = [
    {
        "type": "document",
        "source": {
            "type": "base64",
            "media_type": "application/pdf",
            "data": pdf_data,
        },
        "title": "My PDF Document",
        "citations": {"enabled": True},
    }
]
```

**自定义内容文档：**

```python
documents = [
    {
        "type": "document",
        "source": {
            "type": "content",
            "content": [
                {"type": "text", "text": "Chunk 1: ..."},
                {"type": "text", "text": "Chunk 2: ..."},
            ],
        },
        "title": "Structured Content",
        "citations": {"enabled": True},
    }
]
```

#### 10.2.2.5 Context 字段：不可引用的元信息

`context` 字段允许你提供文档的额外信息——Claude 可以使用它来生成回答，但**不能引用**它。典型用途：

- 文档元数据（发布日期、作者）
- 上下文检索信息
- 使用说明或警告

```python
document = {
    "type": "document",
    "source": {"type": "text", "media_type": "text/plain", "data": "Loyalty program details..."},
    "title": "Loyalty Program",
    "context": "WARNING: This article has not been updated in 12 months. Content may be out of date.",
    "citations": {"enabled": True},
}
```

#### 10.2.2.6 Citation 可视化

Citation 数据可以在前端以多种方式呈现：

1. **学术风格编号**：在文本末尾附加 `[1]`, `[2]` 标记，底部列出参考文献
2. **悬停提示**：鼠标悬停在引用文本上时高亮显示来源
3. **侧边面板**：在回答旁边显示源文档面板，实时同步滚动
4. **PDF 高亮**：使用 PyMuPDF 等库在 PDF 的引用位置添加高亮注释

---

## 10.3 Python 实现

### 10.3.1 MemoryClient

```python
# code/python/ch10/memory_client.py
```

`MemoryClient` 封装了 Memory API 的核心操作，提供同步和简化的接口。它处理：

- Memory Store 的创建与管理（create、list、archive、delete）
- Memory 的 CRUD 操作（store、retrieve、list、delete）
- Memory Version 的审计与回滚
- Dreaming 作业的启动与结果检索

详见 `code/python/ch10/memory_client.py`。

### 10.3.2 CitationParser

```python
# code/python/ch10/citation_parser.py
```

`CitationParser` 将 Citations API 的结构化响应转换为可读的引用格式：

- 从 Content Block 中提取所有 Citation
- 支持 `char_location`、`page_location`、`content_block_location` 三种格式
- 去重并编号引用
- 生成学术风格的引用列表
- 支持 Markdown 和纯文本输出

详见 `code/python/ch10/citation_parser.py`。

---

## 10.4 Node.js 实现

### 10.4.1 MemoryClient

```typescript
// code/node/ch10/MemoryClient.ts
```

TypeScript 版 `MemoryClient` 提供强类型的 Memory API 封装，与 Python 版本保持功能对等。

详见 `code/node/ch10/MemoryClient.ts`。

### 10.4.2 CitationParser

```typescript
// code/node/ch10/CitationParser.ts
```

TypeScript 版 `CitationParser`，提供完整的 Citation 类型定义和解析逻辑。

详见 `code/node/ch10/CitationParser.ts`。

---

## 10.5 最佳实践

### 10.5.1 Memory 组织策略

**1. 小而专注的文件 > 大而全的文件**

Memory 上限为 100 KB，但建议将记忆拆分为多个专门的小文件：

```
# 好
/preferences/formatting.md       (3 KB)
/preferences/language.md         (1 KB)
/context/project_a.md            (15 KB)
/errors/api_timeout_solutions.md (8 KB)

# 差
/everything.md                   (80 KB)
```

原因：Claude 可以更有针对性地读取相关文件，减少上下文窗口的浪费。

**2. 目录结构反映访问模式**

- `/preferences/` -- 用户级别偏好，高频访问
- `/context/` -- 项目和团队级别的上下文
- `/errors/` -- 常见错误和解决方案
- `/knowledge/` -- 领域知识、标准文档
- `/archive/` -- 已过时但保留供参考的内容

**3. 使用只读 Store 共享不变内容**

将公司编码规范、API 文档、领域知识放在只读 Store 中，挂载到所有相关会话。这可以防止因 Agent 误操作而修改关键参考内容。

**4. 利用 Dreaming 做定期整理**

设置定期（如每日）Dreaming 作业，自动清理冗余、合并重复、更新过时信息。Dreaming 始终输出到新 Store，所以不会有破坏原有数据的风险。

### 10.5.2 Citation 信任验证

**1. 始终展示引用来源**

即使用户没有明确要求，也应该在 UI 中展示引用信息。这是建立信任的关键。

**2. 验证引用一致性**

在将 Citation 展示给用户之前，验证 `cited_text` 确实存在于源文档中：

```python
# 验证引用
def verify_citation(citation, source_chunks):
    cited = citation["cited_text"].strip()
    for chunk in source_chunks:
        if cited in chunk:
            return True
    return False
```

**3. 引用去重**

同一个引用可能出现在多个 Content Block 中。在呈现给用户时应该去重。

**4. PDF 引用的页码处理**

页码是 1-indexed。当需要高亮 PDF 页面时，记得转换为 0-indexed。

### 10.5.3 Memory vs Cache

| 维度 | Memory API | 缓存 |
|------|-----------|------|
| 目的 | 跨会话持久化上下文 | 降低延迟和成本 |
| 内容 | 用户偏好、知识、经验 | API 响应 |
| 更新频率 | 低频，由 Agent 写入 | 高频，由系统管理 |
| 生命周期 | 持续到显式删除 | TTL 过期或 LRU 淘汰 |
| 写入者 | Agent（通过 Tool Use） | 系统（自动） |
| 读取者 | Agent（通过 Tool Use） | 系统（自动） |

Memory 不是缓存。不要用它存储可以轻松重新计算的数据或临时 API 响应。把它想象成 Agent 的"长期记忆"——存储那些跨会话有价值的信息。

---

## 10.6 自测题

### Q1. Memory Store 架构理解

以下关于 Memory Store 的描述，哪一项是**错误**的？

A. Memory Store 在容器内挂载为 `/mnt/memory/{name}` 目录
B. 一个 Session 最多可以挂载 8 个 Memory Store
C. Memory Store 可以在会话运行中动态添加或移除
D. 归档 Memory Store 是单向操作，不可撤销

### Q2. Citations 类型匹配

将左边的文档类型与右边正确的 Citation 格式配对：

1. 纯文本文档
2. PDF 文档
3. 自定义内容文档

a. `content_block_location`
b. `page_location`
c. `char_location`

### Q3. Dreaming 机制分析

以下关于 Dreaming 的描述，哪一项是**正确**的？

A. Dreaming 直接修改原始 Memory Store 以提高效率
B. Dreaming 是实时同步的，会在每个 Session 结束后立即执行
C. Dreaming 可以分析多达 100 个过往会话记录来发现模式
D. Dreaming 是 Public Beta 功能，不需要单独申请访问

### Q4. 编程题：实现 Memory 去重

给定一个 Memory Store 的记忆列表（包含 `path`、`content` 和 `content_sha256`），编写一个函数 `deduplicate_memories`，识别内容完全相同的记忆（通过 `content_sha256` 判断），返回一个建议删除的 `memory_id` 列表（保留最早的版本，标记重复的供删除）。

```python
def deduplicate_memories(memories: list[dict]) -> list[str]:
    """
    Args:
        memories: List of dicts with keys: id, path, content_sha256, created_at
    
    Returns:
        List of memory IDs that are duplicates (keep the oldest)
    """
    # 你的实现
    pass
```

---

## 10.7 小结

Memory 和 Citations 共同构成了 Anthropic 生态的"信任基础设施"：

- **Memory API** 让 Agent 拥有了超越单次会话的持久记忆，通过 Dreaming 实现记忆的自动优化与演进
- **Memory Version** 提供了完整的审计轨迹，支持回滚与合规擦除
- **Citations API** 让 Claude 的每一个回答都具备可追溯的来源，三种文档类型覆盖了纯文本、PDF 和自定义内容块
- **乐观并发控制**（`content_sha256`）确保了多 Agent 环境下的数据一致性
- **只读挂载** 和 **Redact** 提供了安全与合规层面的保障

这两个 API 当前都处于活跃开发中：Memory API 是 Managed Agents Public Beta 的一部分（2026 年 4 月），Dreaming 处于 Research Preview（2026 年 5 月），Citations API 已随 Messages API 稳定提供。建议持续关注官方文档以获取最新的参数变化和限制调整。
