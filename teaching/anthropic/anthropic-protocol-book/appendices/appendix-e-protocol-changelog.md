# 附录 E：协议版本变更记录

> Anthropic API 关键功能发布时间线

---

## 2023 年

| 日期 | 事件 | 影响 |
|------|------|------|
| 2023-03-14 | **Claude 首次通过 API 提供服务** | Anthropic 开放第一批商业 API，Claude 1.x 系列上线 |
| 2023-06-01 | **Messages API 正式发布（GA）** | `anthropic-version: 2023-06-01` 成为当前推荐版本。引入 Content Block 类型系统、顶层 `system` 参数、`stop_reason` 机制，确立了不同于 OpenAI 的协议设计哲学 |
| 2023-06-01 | **`x-api-key` 认证方式确立** | 与 Bearer Token 并列成为两种认证方式，`x-api-key` 成为官方 SDK 默认 |
| 2023-Q3 | **Claude 2 发布** | 100K token 上下文窗口，大幅提升推理能力 |
| 2023-Q4 | **分层错误系统完善** | 8 种错误类型（`invalid_request_error` 到 `overloaded_error`）和对应的 HTTP 状态码体系基本成型 |

---

## 2024 年

| 日期 | 事件 | 影响 |
|------|------|------|
| 2024-03-04 | **Claude 3 系列发布（Opus 3, Sonnet 3.5, Haiku 3）** | 引入视觉理解能力（`image` Content Block），多模态支持成为一等公民。Opus 3 在多项基准上达到当时最优 |
| 2024-03-04 | **Tool Use / Function Calling 正式发布** | `tool_use` + `tool_result` Content Blocks 引入。显式工具调用模型成为协议核心，与 OpenAI 的函数调用形成差异化设计 |
| 2024-06-20 | **Claude Sonnet 3.5 发布** | 性能超越 Claude 3 Opus，首次展示"中型模型击败上一代旗舰"的趋势 |
| 2024-08 | **Prompt Caching 发布（Beta）** | 通过 `cache_control: {"type": "ephemeral"}` 标记实现跨请求缓存。写入溢价 25%，读取折扣 90%。需要 `anthropic-beta: prompt-caching-2024-07-31` header |
| 2024-Q3 | **Prompt Caching TTL 延长至 60 分钟** | 部分付费用户通过 feature flag 获得 60 分钟 TTL |
| 2024-10-22 | **Claude Sonnet 3.5 (v2) 发布，Claude Haiku 3.5 发布** | Sonnet 3.5 更新版提升编码能力；Haiku 3.5 带来速度/成本突破 |
| 2024-11-25 | **MCP（Model Context Protocol）首次发布** | Anthropic 主导发布 MCP 开放协议标准，协议版本 `2024-11-05`。定义三层架构（Host-Client-Server）、三大原语（Tools/Resources/Prompts）、JSON-RPC 2.0 传输 |
| 2024-12 | **Batch API 发布** | `POST /v1/messages/batches` 端点，支持高达 100,000 个请求的异步批量处理，提供 50% 价格折扣 |
| 2024-12 | **Citations API 发布** | Messages API 扩展，支持 `char_location`、`page_location`、`content_block_location` 三种引用格式。与 Claude 3.5 Sonnet、3.5 Haiku 配合使用 |

---

## 2025 年

| 日期 | 事件 | 影响 |
|------|------|------|
| 2025-02-19 | **Claude 3.7 Sonnet 发布** | 引入 Extended Thinking（扩展思考）能力，`thinking` Content Block 和签名验证机制 |
| 2025-03-26 | **MCP 规范修订版（`2025-03-26`）** | 重大协议升级：引入 Streamable HTTP 传输（替代旧版 HTTP+SSE）、`Mcp-Session-Id` 会话管理、OAuth 2.1 授权框架 + PKCE 强制。`2024-11-05` 成为已弃用协议版本 |
| 2025-05-14 | **Claude 4 系列发布（Opus 4, Sonnet 4）** | Claude Sonnet 4 (`claude-sonnet-4-20250514`) 和 Claude Opus 4 (`claude-opus-4-20250514`)。Opus 4 在 SWE-bench Verified、Agentic Coding 等基准上达到当时最优 |
| 2025-05 | **Prompt Caching TTL 调整** | 从部分用户的 60 分钟 TTL 调整为默认 5 分钟。符合条件的用户可获得 1 小时 TTL |
| 2025-Q2 | **Prompt Caching GA** | 移除 beta header 要求，缓存功能正式成为 API 标准特性 |
| 2025-08 | **Claude Opus 4.1 发布** | `claude-opus-4-1-20250805`，提升推理和编码能力 |
| 2025-09 | **MCP Registry 预览发布** | 官方 MCP 服务器元数据中心，收录近 2,000 个服务器条目 |
| 2025-09-29 | **Claude Sonnet 4.5 发布** | `claude-sonnet-4-5-20250929`，提升性价比 |
| 2025-10 | **Claude Haiku 4.5 发布** | `claude-haiku-4-5-20251001`，速度最快，近前沿智能水平 |
| 2025-11-01 | **Claude Opus 4.5 发布** | `claude-opus-4-5-20251101` |
| 2025-11-20 | **Advanced Tool Use 三项新特性（Beta）** | Tool Search Tool（按需工具发现）、Programmatic Tool Calling（代码编排工具调用）、Tool Use Examples（工具使用示例标准）。需要 `betas=["advanced-tool-use-2025-11-20"]` |
| 2025-11-25 | **MCP Tasks (SEP-1686) 实验性功能** | 引入异步任务执行（`tasks/get`、`tasks/result`、`tasks/cancel`、`CreateTaskResult`）。Task 状态机：`working` → `input_required` / `completed` / `failed` / `cancelled` |
| 2025-11 | **MCP Tool Annotations 引入** | `tools/list` 返回值中工具新增 `annotations` 字段（如 `readonly`、`destructive`）。Client 被要求将非受信 Server 的 annotations 视为不可信 |
| 2025-Q4 | **Claude Agent SDK 发布** | Python SDK (`claude-agent-sdk`) 和 TypeScript SDK (`@anthropic-ai/claude-agent-sdk`)。提供 `query()` 和 `ClaudeSDKClient` 两个入口，内置 Read/Write/Edit/Bash/Glob/Grep 工具，权限系统和 Hook 机制 |

---

## 2026 年

| 日期 | 事件 | 影响 |
|------|------|------|
| 2026-01 | **Structured Outputs 正式发布** | 通过 `output_config` 参数启用 Constrained Decoding。支持 JSON Schema Draft 2020-12 子集，`effort` 参数（low/medium/high/xhigh/max）控制约束精度。从 Claude 3.5 Sonnet 开始原生支持 |
| 2026-01 | **Computer Use 进入 Beta** | `computer_use` 工具让 Claude 可以操作计算机界面（鼠标点击、键盘输入、屏幕截图） |
| **2026-02-05** | **Claude Opus 4.6 发布** | 1M token 上下文窗口。MRCR v2 得分 78.3%（1M tokens 下最高）。使用无日期格式模型 ID（`claude-opus-4-6`）。与 Opus 4.7 同价 |
| 2026-Q1 | **Prompt Cache TTL 最终确定** | 5 分钟（默认）/ 1 小时（限定用户）。双 TTL 机制稳定运行 |
| 2026-Q1 | **Claude Opus 4.7 发布** | 引入全新 tokenizer（相同文本 token 数多至 35%），Adaptive Thinking（自适应思考模式），128k tokens 最大输出 |
| **2026-04-23** | **Managed Agents Public Beta 发布 + Memory API** | Claude Managed Agents 进入 Public Beta。Memory API（`/v1/memory_stores`）提供跨会话持久化存储、乐观并发控制（`content_sha256`）、30 天版本审计轨迹。`managed-agents-2026-04-01` beta header |
| 2026-Q2 | **Claude Sonnet 4.6 发布** | 1M token 上下文窗口，64k 最大输出。使用无日期格式模型 ID（`claude-sonnet-4-6`）。Extended Thinking 支持。性价比最佳平衡点 |
| **2026-05-01** | **MCP SEP-1865 (MCP Apps) Final** | 标准化 Server 向 Host 交付交互式 UI 的方式。`ui://` 协议 + sandboxed iframe + 双向 JSON-RPC 通信 |
| **2026-05-06** | **Code with Claude 开发者大会** | 15+ 项更新发布。Dreaming Research Preview，Outcomes，Multiagent Orchestration |
| **2026-05-07** | **Dreaming（梦境）Research Preview** | Agent 异步后台任务，读取 Memory Store + 最多 100 个会话记录，输出全新优化 Store。不可变输入，不修改原始 Store。需要 `managed-agents-2026-04-01` + `dreaming-2026-04-21` beta header |
| **2026-05-07** | **Outcomes 与 Multiagent 功能** | Multiagent Orchestration 允许单会话中多 Agent 协作。Outcomes 提供 Agent 执行结果的结构化评估 |
| 2026-05-14 | **Claude Sonnet 4 系列最终定价确认** | Sonnet 4 标准输入 $3/MTok，标准输出 $15/MTok。Cache write $3.75/MTok，Cache read $0.30/MTok。Batch 输入 $1.50/MTok |
| 2026-06-15 | **Claude Opus 4 / Sonnet 4（20250514版）计划退役** | 旧版 `claude-opus-4-20250514` 和 `claude-sonnet-4-20250514` 计划停用，建议迁移至 Opus 4.7 / Sonnet 4.6 |

---

## 废弃与迁移记录

| 旧版 | 替代方案 | 退役日期 | 备注 |
|------|---------|---------|------|
| Claude Opus 4 (`claude-opus-4-20250514`) | Opus 4.7 | 2026-06-15 | 旧版 tokenizer，200K ctx，高定价 |
| Claude Sonnet 4 (`claude-sonnet-4-20250514`) | Sonnet 4.6 | 2026-06-15 | 200K ctx；4.6 有 1M ctx + 更多能力 |
| `response_format` 参数 | `output_config` 参数 | 逐步弃用中 | 旧 Schema 结构，无 `effort` 支持 |
| MCP `2024-11-05` 协议版本 | `2025-03-26` | 2025-Q2 起不再推荐 | 旧版 HTTP+SSE 传输被 Streamable HTTP 替代 |
| Prompt Caching 60 分钟 TTL | 1 小时 TTL（限定用户） | 2025-Q2 | 普通用户缩至 5 分钟，付费用户可申请 1 小时 |
