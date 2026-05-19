# 附录 D：术语表（中英对照）

> 覆盖本书全部 17 章的关键术语，按英文首字母排序。

---

| English | 中文 | 章节 | 说明 |
|:--------|:-----|:-----|:-----|
| **Adaptive Thinking** | 自适应思考 | 第3、5章 | Extended Thinking 的模式之一（`type: "adaptive"`），模型根据问题复杂度自行决定思考深度，而非预设固定 budget_tokens |
| **Agent** | 智能体 | 第14章 | 将 LLM 嵌入自主执行循环的架构模式，能够观察环境、做出决策、执行动作、接收反馈并调整下一步行动 |
| **Agent Loop** | 智能体循环 | 第14章 | Agent 的核心执行引擎：Perceive（感知）→ Reason（推理）→ Act（执行）→ Observe（观察）→ 循环 |
| **Agent SDK** | 智能体开发工具包 | 第14章 | Anthropic 官方的 Agent 构建库（`claude-agent-sdk` / `@anthropic-ai/claude-agent-sdk`），提供 query()、内置工具、权限系统和 Hook 机制 |
| **API Key** | API 密钥 | 第1章 | 访问 Anthropic API 的凭证（`sk-ant-api03-...`），通过 `x-api-key` 或 `Authorization: Bearer` 传递 |
| **anthropic-version** | API 版本头 | 第1、2章 | HTTP 请求头，指定 API 版本（当前推荐 `2023-06-01`），URL 保持稳定，客户端通过头字段控制兼容性 |
| **Batch API** | 批量 API | 第9章 | 异步批量处理端点（`POST /v1/messages/batches`），50% 折扣，24 小时内完成，最高 100,000 请求/批次 |
| **BPE (Byte-Pair Encoding)** | 字节对编码 | 第3章 | Claude tokenizer 的核心算法，通过统计字符/字节对频率构建词汇表，用于文本到 token 的转换 |
| **budget_tokens** | 思考预算 | 第5章 | Extended Thinking 参数，控制思考深度。最小 1,024 tokens。`max_tokens` 必须大于 `budget_tokens` |
| **cache_control** | 缓存控制标记 | 第8章 | 请求内容块上的标记（`{"type": "ephemeral"}`），标记缓存断点位置。支持 `scope`、`ttl` 参数 |
| **cache_edits** | 缓存编辑 | 第8章 | Compaction 的 Cached Microcompact 路径中使用的 API，在不破坏缓存前缀一致性的前提下删除工具结果内容 |
| **CCU (Claude Credit Unit)** | Claude 信用单位 | 第3章 | Anthropic 在 AWS Marketplace 上的计价单位。1 CCU = $0.01 USD，仅适用于 Claude Platform on AWS |
| **Circuit Breaker** | 熔断器 | 第17章 | 容错模式：CLOSED（正常）→ OPEN（拒绝请求）→ HALF_OPEN（探测恢复）。防止级联故障 |
| **Citations** | 引文标注 | 第10章 | Messages API 扩展，Claude 引用文档时自动附加精确位置（字符级/页码级/内容块级） |
| **Compaction** | 上下文压缩 | 第8章 | 将长对话的早期消息替换为结构化摘要，回收上下文窗口空间。支持自动触发（75-92% 使用率）和手动触发 |
| **Computer Use** | 计算机操作 | 第3、14章 | Beta 功能，让 Claude 通过 `computer_use` 工具操作计算机界面（鼠标、键盘、截图） |
| **Constrained Decoding** | 约束解码 | 第4章 | 在 Token 生成层面实施约束（Logit Masking），保证输出 100% 符合 JSON Schema，区别于"生成后验证" |
| **Content Block** | 内容块 | 第1、2章 | Anthropic API 的核心抽象。消息由类型化的内容块数组组成。类型包括：`text`、`image`、`tool_use`、`tool_result`、`thinking` |
| **content_block_start / _delta / _stop** | 内容块开始/增量/结束 | 第5章 | 流式响应的三种核心事件类型，每个内容块通过这三类事件逐步传输完整数据 |
| **Context Window** | 上下文窗口 | 第3、8章 | 模型在一次请求中能"看到"的总 token 数上限。当前最高 1M tokens（Opus 4.7/Sonnet 4.6） |
| **custom_id** | 自定义ID | 第9章 | Batch API 请求的客户端定义唯一标识符，用于将结果映射回原始请求 |
| **DCR (Dynamic Client Registration)** | 动态客户端注册 | 第11、12章 | RFC 7591，MCP 授权中可选的客户端自动注册机制，无需用户手动获取 client_id |
| **defer_loading** | 延迟加载 | 第6章 | 工具定义标记（`defer_loading: true`），配合 Tool Search Tool 实现按需动态发现工具 |
| **Dreaming** | 梦境 | 第10章 | 2026-05 Research Preview，Agent 异步后台任务，读取 Memory Store 和会话记录，输出全新优化 Store |
| **effort** | 约束执行等级 | 第4章 | Structured Outputs 的 `output_config.effort` 参数：`low`/`medium`/`high`/`xhigh`/`max` |
| **Exponential Backoff** | 指数退避 | 第17章 | 重试策略：等待时间 = base × factor^attempt。配合 Full Jitter 消除惊群效应 |
| **Extended Thinking** | 扩展思考 | 第5章 | 让 Claude 先生成思考块（thinking block）记录内部推理过程，再给出最终答案。签名验证保证真实性 |
| **Few-Shot Prompting** | 少样本提示 | 第17章 | 在 System Prompt 中提供 2-5 个高质量示例以提升输出一致性 |
| **Full Jitter** | 全抖动 | 第17章 | 指数退避的随机化增强：`delay = random(0, base × factor^attempt)`，消除分布式系统中的惊群效应 |
| **Hallucination** | 幻觉 | 第4、10章 | 模型编造不存在的事实或引用。Citations API 和 Structured Outputs 可有效降低幻觉 |
| **Hook** | 钩子 | 第14章 | Agent SDK 的生命周期拦截机制：PreToolUse、PostToolUse、Stop、PermissionRequest 等 |
| **input_schema** | 输入模式 | 第6章 | 工具定义的 JSON Schema 格式输入参数规范（`type: "object"`，含 `properties` 和 `required`） |
| **isError** | 错误标记 | 第6、12章 | Tool Result 中的布尔字段（`isError: true`），告知 LLM 工具执行失败以便调整行为 |
| **ITPM (Input Tokens Per Minute)** | 每分钟输入 token 限制 | 第17章 | 速率限制的三个维度之一，与 RPM、OTPM 为 AND 关系 |
| **JSON-RPC 2.0** | JSON 远程过程调用 2.0 | 第11章 | MCP 协议的基础传输协议。四种消息类型：Request (有id+method)、Response (有id+result)、Error (有id+error)、Notification (无id+有method) |
| **JSON Schema** | JSON 模式 | 第4章 | JSON 数据结构的声明式描述语言（Draft 2020-12）。Anthropic Structured Outputs 和 Strict Tool Use 使用其子集 |
| **JSONL** | JSON 行格式 | 第9章 | Batch API 结果格式：每行一个完整的 JSON 对象，用换行符分隔，支持流式读取 |
| **Keep-Alive** | 保活机制 | 第8章 | 通过定时发送轻量请求（~240s间隔）维持 Prompt Caching 的 TTL 计时器，防止 5 分钟缓存过期 |
| **LangChain** | LangChain 框架 | 第14章 | 第三方 LLM 应用开发框架，提供 Chains、Agents、Tools 抽象层。Anthropic 推荐优先使用原生 Agent SDK |
| **LangGraph** | LangGraph 框架 | 第14章 | LangChain 的图状态机扩展，支持将 Agent 工作流建模为有向图（状态节点 + 条件边） |
| **Logit Masking** | Logit 掩码 | 第4章 | Constrained Decoding 的核心机制：将非法 Token 的 logit 设为 -inf，确保模型只从合法候选集中采样 |
| **LSP (Language Server Protocol)** | 语言服务协议 | 第11章 | IDE 与语言服务器之间的标准协议。MCP 的设计灵感来源——同样将 N×M 复杂度降为 N+M |
| **Managed Agents** | 托管智能体 | 第10章 | Anthropic 云端托管的 Agent 执行环境（2026-04 Public Beta），包含 Memory、Dreaming、Session API |
| **max_tokens** | 最大 token 限制 | 第2章 | 必填参数，生成的最大 token 数。模型可能在此之前自然停止。Structured Outputs 中建议设为预期输出的 2-3 倍 |
| **MCP (Model Context Protocol)** | 模型上下文协议 | 第11、12章 | Anthropic 主导的开放协议标准，标准化 LLM 与外部数据源/工具之间的通信。基于 JSON-RPC 2.0 |
| **MCP Apps (SEP-1865)** | MCP 交互式应用 | 第12章 | MCP 扩展，标准化 Server 向 Host 交付 UI 的方式（`ui://` 协议 + sandboxed iframe） |
| **MCP Registry** | MCP 注册表 | 第12章 | 官方 MCP 服务器元数据中心，收录近 2,000 个条目，支持搜索和自动发现 |
| **MCP Tasks (SEP-1686)** | MCP 异步任务 | 第12章 | MCP 的异步任务执行功能：状态机（working→completed/failed/cancelled），`tasks/get`、`tasks/result` 端点 |
| **Memory** | 记忆 | 第10章 | Memory Store 中的单个文本文件，由路径寻址，上限 100 KB（约 25K tokens） |
| **Memory Store** | 记忆存储 | 第10章 | 工作空间级别的持久化文本存储，Container 内挂载为 `/mnt/memory/{name}`，支持读写/只读挂载 |
| **Memory Version** | 记忆版本 | 第10章 | 每次 Memory 变更的不可变快照（`memver_...`），保留 30 天，支持审计与 Redact（合规擦除） |
| **message_start / _delta / _stop** | 消息开始/增量/结束 | 第5章 | 流式响应的生命周事件。message_start 携带 Message 元数据，message_delta 包含 stop_reason 和 usage，message_stop 表示流结束 |
| **Messages API** | 消息 API | 第1、2章 | Anthropic 的核心 API 端点（`POST /v1/messages`），所有对话交互通过这一个端点完成 |
| **Multi-Agent Debate** | 多智能体辩论 | 第14章 | 多个 Agent 从不同视角分析同一问题，通过 Moderator 汇总/评判，达成共识或呈现多元观点 |
| **OAuth 2.1** | 开放授权 2.1 | 第11章 | MCP HTTP 传输的授权框架，强制 PKCE，支持 Authorization Code Grant 和 Client Credentials Grant |
| **OTPM (Output Tokens Per Minute)** | 每分钟输出 token 限制 | 第17章 | 速率限制维度之一，控制输出 token 的消耗速率 |
| **output_config** | 输出配置 | 第4章 | Structured Outputs 的顶层参数，包含 `format`（Schema 定义）和 `effort`（执行等级） |
| **PKCE** | 代码交换证明密钥 | 第11章 | OAuth 2.1 强制安全机制（Proof Key for Code Exchange），防止授权码拦截攻击。MCP 中所有客户端必须使用 |
| **Plan-and-Execute** | 先规划后执行 | 第14章 | 单 Agent 模式：先制定完整计划，再逐步执行和验证。适合步骤明确、可分解的任务 |
| **Programmatic Tool Calling (PTC)** | 程序化工具调用 | 第6章 | Advanced Tool Use 功能。Claude 通过编写 Python 代码编排工具调用，实现上下文隔离和推理次数减少 |
| **Prompt Caching** | 提示缓存 | 第8章 | 跨请求缓存前缀处理结果。写入溢价 25%，读取折扣 90%。默认 TTL 5 分钟。盈亏平衡点约 2 次读取 |
| **Prompt Chaining** | 提示链 | 第14章 | 将复杂任务拆分为多个连续的 API 调用，每步的输出作为下一步的输入 |
| **Prompt Injection** | 提示注入 | 第17章 | 攻击者通过用户输入覆盖或绕过系统指令。分层防御：输入清洗、模式检测、指令隔离、最小权限 |
| **ReAct** | 推理+行动模式 | 第14章 | Reasoning + Acting 的 Agent 循环模式。Thought → Action → Observation 交替进行 |
| **Redact** | 合规擦除 | 第10章 | Memory Version 的内容擦除操作，清除敏感信息但保留 who/what/when 审计元数据 |
| **Reflexion** | 自我反思模式 | 第14章 | ReAct 的增强版，增加自我评估和策略调整阶段（Actor → Evaluator → Reflexion → Retry） |
| **Resources** | 资源原语 | 第11、12章 | MCP 三大原语之一。应用控制的、通过 URI 标识的只读数据暴露（文件内容、数据库 Schema 等） |
| **RPM (Requests Per Minute)** | 每分钟请求限制 | 第17章 | 速率限制的核心维度，控制 API 请求频率 |
| **Retry-After** | 重试等待头 | 第1、17章 | HTTP 响应头，指示客户端应等待的秒数（429 时）。优先于客户端自行计算的退避时间 |
| **Sampling** | LLM 采样 | 第11章 | MCP Client 特性，允许 Server 请求 Client 进行 LLM 推理（`sampling/createMessage`），支持模型偏好提示 |
| **Server-Sent Events (SSE)** | 服务端推送事件 | 第5章 | HTTP 标准扩展（`text/event-stream`），Anthropic 流式响应的底层传输协议。四种标准字段：data、event、id、retry |
| **Service Tier** | 服务层级 | 第2章 | `service_tier` 参数，`auto` 优先使用预留容量，`standard_only` 仅使用标准容量 |
| **Signature** | 签名 | 第5章 | Extended Thinking 中思考块的加密散列，由 Anthropic 私钥签名。API 验证签名以确认思考内容未被篡改 |
| **stop_reason** | 停止原因 | 第2章 | 响应字段，标识模型停止生成的原因：`end_turn`、`max_tokens`、`stop_sequence`、`tool_use`、`pause_turn`、`refusal` |
| **stop_sequences** | 停止序列 | 第2章 | 自定义字符串数组，模型生成到这些文本时立即停止 |
| **Streamable HTTP** | 可流式 HTTP | 第11章 | MCP 2025-03-26 引入的新传输标准，替代旧版 HTTP+SSE。统一 MCP Endpoint（同时支持 GET 和 POST） |
| **Structured Outputs** | 结构化输出 | 第4章 | 通过 Constrained Decoding 保证模型输出符合 JSON Schema。使用 `output_config` 参数启用 |
| **Sub-Agent** | 子智能体 | 第14章 | 在主 Agent 执行过程中动态委托的子 Agent，拥有独立的 System Prompt 和工具集 |
| **Supervisor-Worker** | 监督-工作者模式 | 第14章 | 多 Agent 模式：Supervisor 负责任务分解和结果整合，Worker 负责执行具体子任务 |
| **Swarm** | 群体智能模式 | 第14章 | 去中心化的多 Agent 模式，通过简单局部规则和信息素通信产生涌现性的全局行为 |
| **system (参数)** | 系统提示参数 | 第2章 | 顶层请求参数，传递系统级指令。支持字符串或 Text Block 数组（含 cache_control）。与消息数组在结构上分离 |
| **temperature** | 温度参数 | 第2、3章 | 控制输出随机性：T=0 最确定（代码/数学），T=1.0 最富创造性（创意写作）。数学定义：logits/T |
| **Thinking Block** | 思考块 | 第5章 | Extended Thinking 的输出块（`type: "thinking"`），包含内部推理过程和加密签名 |
| **Token Bucket** | 令牌桶 | 第17章 | 速率限制算法：令牌以 capacity/60 的速率连续补充，每次请求消耗令牌，支持三个维度原子操作 |
| **Token Counter** | Token 计数器 | 第3章 | 估算文本 token 数的工具。英文约 4 字符/token，中文约 1.5-2 字符/token |
| **Tool Choice** | 工具选择参数 | 第6章 | `tool_choice` 参数：`auto`（自动）、`any`（必须使用）、`tool`（指定工具）、`none`（不使用） |
| **Tool Poisoning** | 工具投毒 | 第17章 | 恶意构造的工具返回结果被 LLM 误解读为指令。防御：结果验证、敏感数据过滤、沙箱执行 |
| **Tool Result** | 工具结果块 | 第6章 | user 角色消息中的内容块（`type: "tool_result"`），将工具执行结果传回模型。通过 `tool_use_id` 与 Tool Use 配对 |
| **Tool Search Tool** | 工具搜索工具 | 第6章 | Advanced Tool Use 功能。按需动态发现工具，支持 Regex 和 BM25 两种搜索变体。Token 节省可达 95% |
| **Tool Use** | 工具调用 | 第6章 | Anthropic 的函数调用机制。模型返回 `tool_use` Content Block，客户端执行后将 `tool_result` 返回 |
| **Top-k** | 前K采样 | 第2、3章 | 仅保留概率最高的 K 个 token 进行采样。k=1 为贪心解码 |
| **Top-p (Nucleus Sampling)** | 核采样 | 第2、3章 | 从累积概率达到阈值 p 的 token 中采样。p=0.9 覆盖 90% 概率质量 |
| **TPM (Tokens Per Minute)** | 每分钟 token 限制 | 第1、17章 | token 维度的速率限制，分为 ITPM 和 OTPM |
| **Tree of Thoughts (ToT)** | 思维树 | 第5章 | 推理框架：在每个决策点探索多个分支，评估后选择最佳路径。与 Extended Thinking 结合可产生协同效应 |
| **TTL (Time-To-Live)** | 存活时间 | 第8章 | 缓存的存活时间。Prompt Caching：5 分钟（默认）或 1 小时（限定用户）。Memory Version：30 天 |
| **Usage Tier** | 使用层级 | 第1、17章 | Anthropic 根据消费历史自动划分的 Tier 等级（1-5），更高 Tier 享有更宽松的 RPM/TPM 限制 |
| **XML Prompt Structure** | XML 提示结构 | 第17章 | Claude 4 系列推荐使用的结构化提示格式（`<role>`、`<constraints>`、`<format>`、`<security>`），同时也是 Prompt Injection 防御的基础 |

---

## 按章节索引

| 章节 | 核心术语 |
|------|---------|
| 第1章 API 基础 | API Key, anthropic-version, Content Block, Authentication, Error Types, Rate Limits, Usage Tier |
| 第2章 Messages API | Messages API, Content Block, Text Block, Image Block, Tool Use Block, Tool Result Block, system, temperature, top_p, top_k, stop_reason, stop_sequences, max_tokens |
| 第3章 LLM 模型 | BPE, Tokenizer, Context Window, CCU, Prompt Caching 定价, Batch API 折扣, Token 估算 |
| 第4章 Structured Outputs | Constrained Decoding, Logit Masking, JSON Schema, output_config, effort |
| 第5章 Streaming & Thinking | SSE, content_block_start/delta/stop, message_start/delta/stop, Extended Thinking, thinking block, signature, budget_tokens, Adaptive Thinking, Tree of Thoughts |
| 第6章 Tool Use | Tool Use, tool_choice, strict, defer_loading, Tool Search Tool, Programmatic Tool Calling, Tool Use Examples |
| 第8章 Context Management | Prompt Caching, cache_control, cache_edits, Compaction, TTL, Keep-Alive, Summarization |
| 第9章 Batch API | MessageBatch, custom_id, processing_status, request_counts, JSONL, 50% 折扣 |
| 第10章 Memory & Citations | Memory Store, Memory, Memory Version, Dreaming, Citations, char_location, page_location, content_block_location, Redact |
| 第11章 MCP 协议规范 | MCP, JSON-RPC 2.0, Host-Client-Server, Tools/Resources/Prompts, STDIO, Streamable HTTP, OAuth 2.1, PKCE, DCR, Sampling |
| 第12章 MCP 实战 | MCP Server/Client, MCP Tasks, SEP-1686, SEP-1865, MCP Apps, MCP Registry, MCP Inspector |
| 第14章 Agent SDK | Agent Loop, ReAct, Reflexion, Plan-and-Execute, Supervisor-Worker, Sub-Agent, Multi-Agent Debate, Swarm, Agent SDK, Hook |
| 第17章 生产实践 | Token Bucket, Sliding Window, Exponential Backoff, Full Jitter, Circuit Breaker, Prompt Injection, Tool Poisoning, BudgetController, Idempotency Key |
