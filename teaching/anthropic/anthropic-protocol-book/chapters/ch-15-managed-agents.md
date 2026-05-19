# 第 15 章：Claude Managed Agents

> **本章目标**：掌握 Anthropic 托管式 Agent 运行时——从 Agent/Environment/Session 三要素模型，到 Dreams 记忆整理、Outcomes 结果评估、Multiagent 多智能体编排，再到与第 14 章自建 Agent 的选型决策。完成本章后，你将能够使用 Python/Node.js 客户端创建、管理、监控 Managed Agents 会话，并对核心功能的适用场景建立清醒的判断。

---

## 15.1 概念全景

### 15.1.1 从"自己跑"到"托管跑"

第 14 章我们深入剖析了如何用 Claude Agent SDK 自建 Agent Loop：管理对话历史、编排工具调用、处理中断与恢复——一切代码都在你自己的进程里运行。这条路给了你最大控制权，但也意味着你要对事件循环、会话状态、工具执行沙箱、上下文裁剪（compaction）等基础设施负全责。

Claude Managed Agents 走的是另一条路：**Anthropic 替你托管整个运行时**。2026 年 4 月 8 日，Anthropic 正式发布了 Managed Agents 的公测版（`managed-agents-2026-04-01` beta header）。这是一个托管在 Anthropic 基础设施上的 Agent 执行环境——你定义 Agent 的行为、工具和容器环境，Anthropic 负责将其调度到隔离沙箱中，管理会话生命周期，并提供内置的 Prompt Caching、Compaction 和上下文管理。

本章和第 14 章的关系可以用下面这张决策图概括：

```
你需要什么？
├── 自建 Agent Loop，完全控制运行时
│   └── 第 14 章：Claude Agent SDK
├── 托管运行时，减少基础设施负担
│   └── 第 15 章：Claude Managed Agents
└── 最低级别 API 调用，自己组装一切
    └── 第 1 章：Messages API
```

**核心问题不是"哪个更好"，而是"你想让谁拥有运行时"**。当你选择 Managed Agents，你实际上说：我不想维护 Agent Loop、不想管沙箱、不想操心会话持久化——让 Anthropic 来。

### 15.1.2 Managed Agents 的四大核心概念

Managed Agents 建立在四个最基本的概念之上：

| 概念 | 英文术语 | 描述 |
|------|----------|------|
| **Agent** | Agent | 模型、系统提示词、工具、MCP 服务器、Skills 的版本化配置 |
| **Environment** | Environment | 云容器模板：预装软件包、网络访问策略、挂载文件 |
| **Session** | Session | Agent 在 Environment 中的一个运行实例，执行特定任务并生成输出 |
| **Events** | Events | 应用程序与 Agent 之间交换的消息（用户消息、工具结果、状态更新） |

理解这四个概念的关系是理解 Managed Agents 全部能力的基础：

1. **先创建 Agent** —— 定义模型、system prompt、工具配置。Agent 是版本化的（`version` 字段），每次修改会自增。
2. **再创建 Environment** —— 配置运行环境（预装 Node.js/Python 等）、网络策略。
3. **然后启动 Session** —— 引用 Agent 和 Environment，发送任务。
4. **最后通过 Events 流式交互** —— 发送用户消息，接收 Agent 的工具调用和结果。

---

## 15.2 协议规范

### 15.2.1 Managed Agents 架构全景

#### 托管运行时 vs 自建运行时

| 维度 | Managed Agents | 自建 Agent（SDK） |
|------|----------------|-------------------|
| **Agent Loop** | Anthropic 托管，自动管理 | 开发者手写事件循环 |
| **会话状态** | 服务端持久化，Event Stream 可回溯 | 开发者管理存储 |
| **工具沙箱** | 内置 Bash 命令执行、文件操作、Web Search/Fetch | 需自建沙箱或手动对接 |
| **上下文管理** | 内置 Prompt Caching + Compaction | 开发者实现（参考第 8 章） |
| **模型推理** | 使用标准 Claude 模型 token 计费 | 同 |
| **运行时费用** | $0.08/session-hour（running 状态），毫秒级计量 | 无额外费用 |
| **扩展能力** | MCP 服务器、Agent Skills、自定义工具 | 完全自由 |
| **部署方式** | Anthropic 云基础设施 | 你的服务器/进程 |
| **速率限制** | 创建操作 60 RPM，读取操作 600 RPM | 标准 API 速率限制 |

#### 会话隔离与持久化

每个 Managed Agents Session 在创建时，Anthropic 会为其分配一个**隔离的沙箱容器**。这个容器：

- 拥有独立的文件系统（/mnt/session/ 路径）
- 可以安装和运行软件包（由 Environment 配置指定）
- 支持网络访问（由 Environment 的网络策略控制）
- 会话结束后可以选择保留或销毁

**长运行会话管理**：Session 的生命周期包括以下状态：

```
created → running → idle/running/archived/deleted
              ↑                        ↓
              └──── 用户发送新消息 ←──────┘
```

一个 Session 可以跨多个用户交互：用户发送消息，Agent 开始工作（running），完成后进入 idle，用户可以继续发送新消息。Event History 在服务端完整保存，可以在任何时候通过 API 拉取。

### 15.2.2 核心能力详解

#### 内置 Prompt Caching 与 Compaction

Managed Agents 的内置上下文管理直接对应本书第 8 章介绍的 Prompt Caching 和 Compaction 机制：

- **Prompt Caching**：Agent 的系统提示词、工具定义等重复内容会被自动缓存。在 `span.outcome_evaluation_end` 事件中，你可以看到 `usage.cache_read_input_tokens` 字段，显示缓存命中量。
- **Compaction**：当会话历史增长接近模型上下文窗口限制时，Managed Agents 会自动触发 Compaction——将对话历史压缩为结构化摘要，释放窗口空间。这避免了开发者手动实现第 8 章中的上下文裁剪逻辑。

```
┌──────────────────────────────────────────────────────┐
│              Managed Agents Runtime                  │
│                                                      │
│  ┌───────────┐   ┌────────────┐   ┌──────────────┐  │
│  │ Agent Loop│──▶│Tool Executor│──▶│Event Streamer│  │
│  └───────────┘   └────────────┘   └──────────────┘  │
│        │                │                  │         │
│  ┌─────▼──────┐  ┌──────▼──────┐  ┌───────▼──────┐  │
│  │  Prompt    │  │   Sandbox   │  │   Session    │  │
│  │  Caching   │  │  Container  │  │  Persistence │  │
│  │  (Ch. 8)   │  │             │  │              │  │
│  └────────────┘  └─────────────┘  └──────────────┘  │
│                                                      │
│  ┌────────────┐   ┌─────────────┐  ┌─────────────┐  │
│  │ Compaction │   │   Memory    │  │  Multiagent  │  │
│  │  (Ch. 8)   │   │   Stores    │  │ Orchestration│  │
│  └────────────┘   └─────────────┘  └─────────────┘  │
└──────────────────────────────────────────────────────┘
```

#### Agent 配置（Agent）

Agent 是 Managed Agents 的"大脑"。它定义了谁（模型）、什么性格（system prompt）、能用什么（工具）和知道什么（Skills）。

创建 Agent 的核心参数：

| 字段 | 类型 | 必需 | 说明 |
|------|------|------|------|
| `name` | string | 是 | Agent 名称（1-256 字符） |
| `model` | string \| object | 是 | 模型 ID（如 `claude-opus-4-7`），或 `{id, speed}` 对象 |
| `system` | string | 否 | 系统提示词（最多 100,000 字符） |
| `tools` | array | 否 | 工具配置（最多 50 个），使用 `agent_toolset_20260401` 启用内置工具集 |
| `mcp_servers` | array | 否 | MCP 服务器配置（最多 20 个） |
| `skills` | array | 否 | Agent Skills（最多 64 个） |
| `multiagent` | object | 否 | 多智能体协调器声明（见 15.2.5 节） |
| `description` | string | 否 | Agent 用途描述（最多 2048 字符） |
| `metadata` | object | 否 | 自定义标签（最多 16 个键值对） |

Agent 是**版本化**的——每次修改（Update）会生成新的 `version`（自增整数）。你可以通过 `versions.list` 查看完整版本历史。Archive 操作会使 Agent 变为只读（新 Session 不可引用，现有 Session 不受影响），且不可逆。

> **注意**：Agent 没有 Delete 操作，只有 Archive。Archive 是永久性的——无法撤销。对生产环境 Agent 执行 Archive 前务必确认。

#### Environment 配置

Environment 是 Agent 运行的"身体"——它决定了 Agent 可以在什么样的容器环境中执行代码、访问网络。

```json
{
  "name": "Python Data Analysis Env",
  "config": {
    "type": "cloud",
    "networking": {
      "type": "unrestricted"
    },
    "packages": {
      "python": ["pandas", "numpy", "matplotlib"],
      "node": ["lodash"]
    }
  }
}
```

Environment 支持 `unrestricted`（允许任意出站网络）和 `limited`（受限）两种网络策略。预装软件包在容器启动时自动安装。Environment 也有 Archive 和 Delete 操作。

#### Session 生命周期管理

Session 是工作执行的核心单元。创建 Session 时需要指定：

```json
{
  "agent": "agent_abc123",
  "environment_id": "env_xyz789",
  "title": "Costco DCF Analysis",
  "resources": [
    {
      "type": "github_repository",
      "url": "https://github.com/owner/repo",
      "authorization_token": "ghp_...",
      "checkout": {"type": "branch", "name": "main"}
    }
  ],
  "vault_ids": ["vlt_abc123"]
}
```

`agent` 字段接受字符串（使用最新版本）或 `{type: "agent", id, version}` 对象。`resources` 支持三种资源类型：
- `file`：文件资源
- `github_repository`：GitHub 仓库（支持 branch 或 commit checkout）
- `memory_store`：持久化记忆存储（仅在创建会话时附加）

Session Event 是通信的核心。三种操作：
1. **SendEvents** (`POST /v1/sessions/{id}/events`)：向会话发送事件（用户消息、工具结果）
2. **ListEvents** (`GET /v1/sessions/{id}/events`)：轮询获取事件历史（分页）
3. **StreamEvents** (`GET /v1/sessions/{id}/events/stream`)：通过 SSE（Server-Sent Events）流式接收事件

#### 内置工具集（Agent Toolset）

使用 `{"type": "agent_toolset_20260401"}` 配置，Agent 获得以下内置能力：

| 工具 | 功能 | 对应本书 |
|------|------|----------|
| **Bash** | 在容器中执行 Shell 命令 | 第 14 章沙箱 |
| **File Read/Write/Edit** | 文件读取、写入、编辑 | — |
| **Glob/Grep** | 文件搜索 | — |
| **Web Search** | 网页搜索 | — |
| **Web Fetch** | 获取 URL 内容 | — |
| **MCP Tools** | 通过 MCP 协议连接外部工具 | 第 9 章 |

#### 速率限制与错误处理

| 操作 | 限制 |
|------|------|
| 创建端点（agents, sessions, environments 等） | 300 RPM（公测期间） |
| 读取端点（retrieve, list, stream 等） | 600 RPM |
| 在线推理 token | 按组织配额 |

错误响应格式与 Messages API 一致（标准 Anthropic API 错误格式）。关键区别：`409 Conflict` 在 Managed Agents 中用于表示资源状态冲突（如向已归档的 Session 发送事件），其 `error.type` 为 `invalid_request_error`——需要同时检查 HTTP 状态码和错误消息来区分。

### 15.2.3 Dreams：跨 Session 记忆整理

Dreams 是 Managed Agents 最独特的特性之一——让 Claude 像"做梦"一样回顾过去的会话，整理和优化记忆存储。

#### 核心思想

Agent 在多个 Session 中工作时会向 Memory Store 写入信息。随着时间推移，Memory Store 会积累：
- **重复条目**：Agent 多次写入相同的信息
- **矛盾条目**：旧信息被新信息取代，但旧条目仍在
- **过时条目**：曾经适用但不再相关的上下文

**Dreams 解决这个问题**：读取现有 Memory Store 和过去的 Session Transcripts（会话转录），然后生成一个全新的、重组过的 Memory Store——去重、合并、更新，甚至发现新的模式和洞察。

> **关键安全特性**：Dream 永远不会修改或删除输入 Memory Store。它创建一个**全新的输出 Memory Store**。你可以审查结果，满意则使用，不满意则丢弃。

#### API 操作

Dream 是一个异步 Job，创建后需要轮询状态：

```python
dream = client.beta.dreams.create(
    inputs=[
        {"type": "memory_store", "memory_store_id": store_id},
        {"type": "sessions", "session_ids": [session_a, session_b]},
    ],
    model="claude-opus-4-7",
    instructions="Focus on coding-style preferences; ignore one-off debugging notes.",
)
```

Dream 的生命周期：

```
pending → running → completed/failed/canceled
              ↓
         canceled (可主动取消)
```

| `status` | 含义 |
|----------|------|
| `pending` | Dream 已创建并排队 |
| `running` | 正在处理，`usage` 实时更新 |
| `completed` | 成功完成，`outputs[]` 包含新的 Memory Store |
| `failed` | 处理失败，输出 Store 保留部分内容 |
| `canceled` | 已取消，输出 Store 保留部分内容 |

关键限制：
- 每个 Dream 最多 100 个 Session
- `instructions` 最多 4,096 字符
- 支持的模型：`claude-opus-4-7`、`claude-sonnet-4-6`
- 需要额外 Beta Header：`dreaming-2026-04-21`
- 这是一个 **Research Preview** 功能，需单独申请访问

#### 计费

Dreams 按标准 API token 费率计费。`usage` 字段报告确切的 token 消耗。成本与输入 Session 数量和长度大致线性相关。建议先用少量 Session 测试整理质量，再扩展到大规模使用。

### 15.2.4 Outcomes：Agent 结果评估

Outcomes 将 Session 从"对话"提升为"工作"——你定义最终结果应该是什么样子，以及如何衡量质量，Agent 朝着这个目标工作，自我评估并迭代，直到满足标准。

#### Rubric（评估标准）

Outcomes 的核心是 **Rubric**——一个 Markdown 文档，描述逐项的评分标准。例如：

```markdown
# DCF 模型评估标准

## 收入预测
- 使用过去 5 个财年的历史收入数据
- 预测至少 5 年的收入
- 增长率假设被明确声明且合理

## 成本结构
- COGS 和运营费用分别建模
- 利润率与历史趋势一致，或偏差有合理理由

## 输出质量
- 所有数据在一个 .xlsx 文件中，Sheet 标签清晰
- 关键假设在独立的"Assumptions" Sheet 中
- 包含 WACC 和终端增长率的敏感性分析
```

#### 评估流程

当你发送 `user.define_outcome` 事件时，Managed Agents 会自动启动一个 **Grader**（评估器）：

1. Agent 开始工作（与正常 Session 相同）
2. 完成一个工作循环后，Grader 使用**独立的上下文窗口**（不受主 Agent 推理影响）对照 Rubric 评估成果
3. Grader 返回逐项评分：要么确认满足标准，要么指出具体差距
4. Agent 收到反馈后进行下一轮迭代
5. 重复直到满足标准或达到最大迭代次数

```python
client.beta.sessions.events.send(
    session_id=session.id,
    events=[{
        "type": "user.define_outcome",
        "description": "Build a DCF model for Costco in .xlsx",
        "rubric": {"type": "text", "content": RUBRIC},
        "max_iterations": 5,
    }],
)
```

#### 评估结果

`span.outcome_evaluation_end` 事件的 `result` 字段：

| Result | 后续行为 |
|--------|----------|
| `satisfied` | Session 转入 `idle`，成果达成 |
| `needs_revision` | Agent 开始新一轮迭代 |
| `max_iterations_reached` | 不再评估，Session 转入 `idle` |
| `failed` | Rubric 与任务描述根本不匹配 |
| `interrupted` | 被 `user.interrupt` 事件打断 |

> **Research Preview**：Outcomes 功能目前也是 Research Preview，需单独申请访问。

### 15.2.5 Multiagent Orchestration：多智能体编排

Multiagent Orchestration 让一个协调 Agent（Coordinator）能够将工作分派给其他 Agent。每个 Agent 在自己的**隔离上下文线程**中运行，使用自己的模型、系统提示词和工具配置。

#### 架构模型

```
                    ┌───────────────────┐
                    │   Coordinator     │
                    │   (Opus 4.7)      │
                    └──────┬────────────┘
            ┌──────────────┼──────────────┐
            │              │              │
            ▼              ▼              ▼
   ┌────────────┐  ┌────────────┐  ┌────────────┐
   │ Security   │  │ Frontend   │  │ Data       │
   │ Reviewer   │  │ Developer  │  │ Analyst    │
   │ (Sonnet)   │  │ (Sonnet)   │  │ (Sonnet)   │
   └────────────┘  └────────────┘  └────────────┘
```

#### 核心特性

1. **隔离上下文**：每个 Agent 有自己的 Event Stream（称为 Session Thread），拥有独立的对话历史和工具访问。
2. **共享文件系统**：所有 Agent 共享同一个容器和文件系统。
3. **持久线程**：Coordinator 可以向之前调用过的子 Agent 发送跟进消息，子 Agent 保留之前的所有历史。
4. **并行执行**：Coordinator 可以同时分派任务给多个子 Agent，然后汇总结果。
5. **事件透传**：子 Agent 的关键事件（如工具权限请求）会被传输到主线程，客户端通过主线程处理。

#### 配置方式

在创建 Coordinator Agent 时声明 `multiagent` 字段：

```json
{
  "multiagent": {
    "agents": [
      {"type": "agent", "id": "agent_security_abc"},
      {"type": "agent", "id": "agent_frontend_xyz"},
      {"type": "self"}
    ]
  }
}
```

- `{"type": "agent", "id": "..."}` 引用已创建的 Agent（默认使用最新版本）
- `{"type": "agent", "id": "...", "version": 3}` 固定特定版本
- `{"type": "self"}` 允许 Coordinator 生成自身的副本

限制：
- Coordinator 只能委托一级深度（depth > 1 被忽略）
- `multiagent.agents` 最多 20 个唯一 Agent
- 支持最多 25 个并发线程
- Coordinator 可以对同一个 Agent 发起多个调用（多个线程）

#### 多智能体事件

主线程（Session-level Event Stream）会接收以下多智能体事件：

| 事件类型 | 说明 |
|----------|------|
| `session.thread_created` | 线程创建，包含 `session_thread_id` 和 `agent_name` |
| `session.thread_status_running` | 线程开始活动 |
| `session.thread_status_idle` | Agent 等待输入，包含 `stop_reason` |
| `session.thread_status_terminated` | 线程被归档或遇到错误 |
| `agent.thread_message_received` | 子 Agent 向 Coordinator 交付结果 |
| `agent.thread_message_sent` | Coordinator 向子 Agent 发送任务 |

#### 适用模式

| 模式 | 场景 | 说明 |
|------|------|------|
| **并行化** | 同时搜索多个数据源 | 独立子任务并行执行，Coordinator 汇总 |
| **专业化** | 安全检查、文档生成 | 每个 Agent 有领域专注的系统提示词和工具 |
| **升级** | 复杂子任务转交更强大的模型 | OPUS 协调者将复杂子任务转发给 OPUS，简单任务使用 SONNET |

> **Research Preview**：Multiagent Orchestration 同样是 Research Preview 功能。

### 15.2.6 与第 14 章自建 Agent 的对比

| 决策因素 | Managed Agents | Agent SDK（第 14 章） |
|----------|----------------|----------------------|
| **运行时位置** | Anthropic 云 | 你的服务器 |
| **控制粒度** | 粗粒度——Anthropic 管理循环 | 细粒度——你控制每一步 |
| **部署复杂度** | 低——只需 API 调用 | 中高——需管理进程/容器 |
| **调试能力** | 通过 Event Stream 回溯 | 完全可控——可在任意点插入断点 |
| **自定义工具执行** | 通过 Event 处理，需往返通信 | 在你进程中直接执行，零延迟 |
| **成本结构** | Token + $0.08/session-hour | Token 费用 |
| **自动 Compaction** | 内置 | 需手写（参考第 8 章） |
| **跨 Session 记忆** | 内置 Memory Stores + Dreams | 需自行设计存储层 |
| **多 Agent** | 内置 Multiagent | 需自行编排 |

**选型建议**：

- 选择 **Managed Agents**：当你想要一个托管运行时执行长时间、异步的 Agent 任务，且愿意接受 $0.08/session-hour 的运行时费用换取基础设施的零运维。
- 选择 **Agent SDK**：当你需要对 Agent Loop 的每一步进行精确控制，或运行时必须留在你的进程/部署中。
- 选择 **Messages API**：当你连 Agent 框架都不需要，只需要最薄层的模型 API 封装。

### 15.2.7 使用场景与局限性

#### 典型使用场景

1. **数据分析 Agent**：挂载 CSV 文件，让 Agent 在容器中运行 pandas/numpy 分析，生成报告。单次 Session 可能运行数分钟到数十分钟。
2. **代码审查 Agent**：挂载 GitHub 仓库，让 Agent 进行代码审查、生成修复建议。
3. **自动化报告 Agent**：定期启动 Session，Agent 爬取数据、生成 Markdown/PDF 报告，输出到 /mnt/session/outputs/。
4. **多 Agent 研究系统**：Coordinator 分派任务给专门的数据收集、安全审查、文档生成 Agent。

#### 当前局限性

1. **Beta 限制**：产品仍在公测，行为可能在版本间变化。Memory、Multiagent、Outcomes 是 Research Preview，需单独申请访问。
2. **运行时费用**：$0.08/session-hour 虽不高，但对大量短 Session 的场景会增加成本。
3. **自定义工具延迟**：自定义工具需要通过 Event 往返（发送 tool_use，接收 tool_result），有网络延迟。
4. **Agent 不可删除**：只有 Archive（永久只读），没有 Delete 操作。
5. **子 Agent 调用深度**：Multiagent 只支持一级委托，不支持深度树状结构。
6. **速率限制**：创建操作 60 RPM 可能限制高频自动化场景。

---

## 15.3 Python 实现：ManagedAgentClient

我们将在 `code/python/ch15/managed_agent.py` 中实现一个 `ManagedAgentClient` 类，封装 Managed Agents 核心操作。这个客户端遵循项目约定：依赖 `httpx`（不依赖 `anthropic` SDK），支持同步和异步两种模式。

> **说明**：在实际生产环境中，建议使用官方 `anthropic` SDK 的 `client.beta.*` 命名空间来访问 Managed Agents API，它自动处理 Beta Header 和重试。本章实现的客户端主要用于理解和学习协议细节。

完整的实现文件见 `code/python/ch15/managed_agent.py`。核心接口如下：

```python
class ManagedAgentClient:
    """Anthropic Managed Agents API 客户端"""

    def create_agent(self, config: dict) -> str: ...
    def start_session(self, agent_id: str, task: str) -> str: ...
    def get_session_status(self, session_id: str) -> dict: ...
    def get_session_result(self, session_id: str) -> dict: ...
    def cancel_session(self, session_id: str): ...
    def list_sessions(self, agent_id: str) -> list[dict]: ...
```

API 设计要点：
- 所有 Managed Agents 端点使用 `https://api.anthropic.com/v1/` 基础路径
- 需要 `anthropic-version: 2023-06-01` 和 `anthropic-beta: managed-agents-2026-04-01` 头
- Sessions 使用 `managed-agents-2026-04-01` beta header
- Dreams 额外需要 `dreaming-2026-04-21` beta header
- 完整的测试套件见 `code/python/ch15/test_managed_agent.py`

---

## 15.4 Node.js 实现：ManagedAgentClient

TypeScript 实现与 Python 版本保持接口一致，遵循项目 TypeScript 约定（严格模式、零 `any` 使用、Node.js 22+ 原生 `fetch`）。

完整实现见 `code/node/ch15/ManagedAgentClient.ts`。测试文件见 `code/node/ch15/managed_agent.test.ts`。

```typescript
export class ManagedAgentClient {
  constructor(config: ManagedAgentConfig) {}
  async createAgent(config: AgentConfig): Promise<string>;
  async startSession(agentId: string, task: string): Promise<string>;
  async getSessionStatus(sessionId: string): Promise<SessionStatus>;
  async getSessionResult(sessionId: string): Promise<SessionResult>;
  async cancelSession(sessionId: string): Promise<void>;
  async listSessions(agentId: string): Promise<SessionSummary[]>;
}
```

---

## 15.5 最佳实践

### 15.5.1 Session 生命周期管理

1. **始终处理超时和取消**：当不再需要结果时立即调用 `cancel_session`，避免产生不必要的运行时费用。
2. **归档而非"等待"**：`running` 状态的 Session 按小时计费。工作完成后 Session 会自动进入 `idle` 状态，但不会自动归档。如果不再需要交互，主动归档以释放资源。
3. **轮询策略**：使用指数退避轮询 Session 状态（建议 1s-5s-10s-30s），而非固定间隔。当 `status` 变为非 `running`/非 `pending` 时停止轮询。
4. **保留 Session ID 用于审计**：Session 的 Event History 是完整的审计日志，在问题回溯时非常有用。

### 15.5.2 错误恢复

| 错误类型 | 恢复策略 |
|----------|----------|
| `rate_limit_error` (429) | 指数退避重试，上限 5 次 |
| `api_error` (500) / `overloaded_error` (529) | 退避重试，上限 3 次 |
| `authentication_error` (401) | 不要重试——检查 API Key |
| `not_found_error` (404) | 检查资源 ID 是否正确 |
| `invalid_request_error` (400/409) | 检查请求参数，409 检查资源状态 |

**关键模式**：区分"操作失败"和"Session 内工作失败"。`get_session_status` 返回的 `status != "completed"` 不一定是错误——Agent 可能仍在工作。检查 Event Stream 中的错误事件来确定实际问题。

### 15.5.3 成本优化

1. **选择合适的模型**：简单任务使用 `claude-sonnet-4-6` 的 `fast` 速度模式；复杂任务使用 `claude-opus-4-7`。
2. **限制迭代次数**：Outcomes 的 `max_iterations` 不要设置过高（默认 3，最大 20）。每次迭代都会消耗 token。
3. **重用 Agent 和 Environment**：Agent 和 Environment 是一次性创建的版本化资源，跨 Session 复用。
4. **及时清理**：不用的 Memory Stores、Files、Sessions 及时归档/删除。
5. **Dream 测试策略**：先用少量 Session 测试 Dream 的整理质量，确认满意后再大规模运行。Dream 成本与输入 Session 数量和长度大致线性相关。

### 15.5.4 Memory Store 最佳实践

1. **结构化为多个小文件**：每个 Memory 上限 100 KB（约 25k tokens）。避免单个大文件，优先组织为 `/preferences/`, `/conventions/`, `/context/` 等目录结构。
2. **使用 read_only 保护数据**：对参考材料、共享查询表等不需要 Agent 修改的 Memory Store 使用 `read_only` 访问模式。
3. **防范 Prompt Injection**：如果 Agent 处理不受信任的输入（用户提示词、网页内容、第三方工具输出），使用 `read_only` 防止恶意内容写入 Memory Store。
4. **定期 Dream**：随着 Session 积累，定期运行 Dream 清理重复和过时内容。

### 15.5.5 Multiagent 设计原则

1. **明确角色边界**：每个子 Agent 的系统提示词应清晰定义其职责范围。
2. **Coordination 开销**：多 Agent 协作会产生协调开销（Coordinator 需要理解、分派和汇总），不适合过于简单的任务。
3. **并行化前提**：子任务之间应真正独立，避免隐藏的数据依赖。
4. **合理选择子 Agent 模型**：简单子任务使用 `sonnet`，复杂子任务或需要深度推理的场景使用 `opus`。

---

## 15.6 本章小结

本章从托管运行时 vs 自建运行时的决策出发，深入拆解了 Claude Managed Agents 的完整架构：

- **四大核心概念**：Agent（谁）、Environment（在哪）、Session（做什么）、Events（怎么通信）
- **内置能力**：Prompt Caching、Compaction、Session 持久化——直接连接第 8 章的理论与实践
- **Dreams**：跨 Session 记忆整理——去重、合并、发现新模式
- **Outcomes**：带评估标准的迭代工作——Agent 自我评估直到达标
- **Multiagent Orchestration**：一个 Coordinator 协调多个专业 Agent，并行执行
- **选型决策**：Managed Agents vs Agent SDK vs Messages API——核心问题是"运行时谁来管"

Managed Agents 代表了 Anthropic 对 Agent 基础设施的愿景：你不应该把精力花在构建 Agent Loop 和沙箱上——你应该专注于定义 Agent 能做什么，剩下的交给平台。

但要记住：**托管不等于万能**。当你的需求需要精细的循环控制、零延迟的工具执行、或运行时必须在自己的基础设施上时，第 14 章的自建 Agent 仍然是正确的选择。

---

## 15.7 自测题

### Q1（概念题）
Managed Agents 的四大核心概念是什么？请说明每个概念的作用以及它们之间的关系。

### Q2（对比分析题）
在以下场景中，应该选择 Managed Agents 还是第 14 章的 Agent SDK？请说明理由。
- (a) 需要精确控制 Agent Loop 的每一步，包括自定义的运行时检查点
- (b) 要构建一个数据分析 Agent，每天自动运行，在容器中运行 pandas 分析 CSV 文件
- (c) 延迟极其敏感的应用，自定义工具的每次往返都不能超过 10ms

### Q3（架构设计题）
你需要设计一个多 Agent 代码审查系统：一个 Coordinator 协调三个子 Agent（安全检查、性能分析、代码风格审查）。请写出 Coordinator Agent 的 `multiagent` 配置，并说明 Coordinator 如何汇总三个子 Agent 的结果。

### Q4（编码题）
使用本章实现的 `ManagedAgentClient`，编写一个函数 `run_agent_with_retry(agent_id: str, task: str, max_wait_seconds: int = 600) -> dict`，它启动一个 Session，轮询等待完成（最多 `max_wait_seconds` 秒），返回最终结果。如果超时或失败，应自动取消 Session 并抛出异常。
