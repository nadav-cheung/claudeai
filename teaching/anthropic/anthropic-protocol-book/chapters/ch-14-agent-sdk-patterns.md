# 第 14 章：Agent SDK 与 Agent 模式 —— 从单次调用到自主循环

## 14.1 概念全景

### 14.1.1 从 API 调用到 Agent：一个分水岭

在前 13 章中，我们逐层剖析了 Anthropic 协议栈的每个组件——从 Messages API、Tool Use、Streaming/Extended Thinking，到 Context Management、Batch API、Memory/Citations、MCP 协议。所有这些组件的共同特征是：**它们都围绕单次请求-响应模型构建**。你发送一条消息，模型返回一条回复，流程结束。

但当你将这些能力组合在一起时，一个根本性的问题浮现了：

> 如果模型需要连续执行 10 步操作——读取文件、搜索代码、运行测试、修复 bug、再次测试——谁来管理这 10 步之间的状态流转？

这正是 **Agent** 要解决的问题。Agent 不是一个新的 API 端点，而是一种**架构模式**：将单次 LLM 调用嵌入到一个自主的执行循环中，让模型能够观察环境、做出决策、执行动作、接收反馈，并基于反馈调整下一步行动。

### 14.1.2 决策树：你应该用哪种 Agent 方案？

在投入实现之前，先回答三个问题来决定你的架构层级：

```
问题 1：任务的完成路径是否可预先确定？
├── 是 → 问题 2：任务步骤数是否可预测（<5 步）？
│   ├── 是 → 直接用 Messages API + Tool Use（不用 Agent）
│   └── 否 → Prompt Chaining / Routing Workflow
└── 否 → 问题 3：需要多 Agent 协作还是单 Agent 自主循环？
    ├── 单 Agent → Agent Loop（自建）或 Agent SDK
    └── 多 Agent → 选择模式：Supervisor-Worker / Sub-Agent / Debate / Swarm
```

三种方案的本质区别：

| 维度 | 自建 Agent Loop | Claude Agent SDK | Managed Agents |
|------|----------------|-------------------|----------------|
| **控制粒度** | 完全自定义 | SDK 封装循环 + 内置工具 + 权限 | Anthropic 托管执行 |
| **工具执行** | 你实现 executor | 内置 Read/Write/Edit/Bash/Grep/Glob | 声明式配置 |
| **适用场景** | 需要深度定制循环逻辑、不依赖文件系统工具 | 编码助手、文件操作、需要内置 Bash | 云端大规模部署、跨会话 Memory |
| **学习曲线** | 中——需理解循环原理 | 低——`query()` 一行启动 | 中——需理解 Container/Session 模型 |
| **部署位置** | 客户端 | 客户端 | Anthropic 云端 |
| **代表产品** | 自定义 Agent 应用 | Claude Code 底层 | Claude Platform |

**核心理念**（来自 Anthropic 官方指南 *Building Effective Agents*, Dec 2024）：

> "Success isn't about building the most sophisticated system. It's about building the *right* system for your needs. Start with simple prompts, optimize them with comprehensive evaluation, and add multi-step agentic systems only when simpler solutions fall short."

---

## 14.2 Agent Loop 原理：Perceive -> Reason -> Act -> Observe

### 14.2.1 循环的本质

Agent Loop 是 Agent 系统的核心引擎。无论你是自建循环、使用 Agent SDK 还是 Managed Agents，底层的运行逻辑完全相同：

```
┌─────────────────────────────────────────────────────────┐
│                    Agent Loop                            │
│                                                          │
│   ┌──────────┐    ┌──────────┐    ┌──────────┐          │
│   │ PERCEIVE │───>│  REASON  │───>│   ACT    │          │
│   │ 感知环境  │    │ 推理决策  │    │ 执行动作  │          │
│   └──────────┘    └──────────┘    └──────────┘          │
│        ^                                 │               │
│        │                                 │               │
│        └─────────── OBSERVE ◄───────────┘               │
│                   观察结果                               │
│                                                          │
│   终止条件：task_complete OR max_iterations OR error     │
└─────────────────────────────────────────────────────────┘
```

**Perceive（感知）**：将环境状态（用户输入、工具执行结果、中间上下文）组装为 LLM 可理解的 Messages 格式。

**Reason（推理）**：LLM 基于当前 Messages 进行推理，决定下一步行动。输出可能是：
- `stop_reason: "end_turn"` —— 任务完成，返回最终结果
- `stop_reason: "tool_use"` —— 需要调用工具获取更多信息

**Act（执行）**：如果模型要求工具调用，执行对应的工具函数，捕获结果。

**Observe（观察）**：将工具执行结果注入 Messages 列表（作为 `tool_result` 内容块），形成新的上下文，进入下一轮循环。

### 14.2.2 单次迭代的 Messages 演化

以一个简单的天气查询为例，展示 Agent Loop 中 Messages 的演化过程：

```
迭代 0（初始状态）：
Messages: [
  {role: "user", content: "北京今天天气如何？适合户外运动吗？"}
]

迭代 1（模型请求工具）：
模型响应: stop_reason="tool_use", tool_use={name:"get_weather", input:{location:"北京"}}
Messages: [
  {role: "user", content: "北京今天天气如何？..."},
  {role: "assistant", content: [tool_use_block]},
  {role: "user", content: [tool_result: {weather:"晴", temp:24, wind:"2级"}]}
]

迭代 2（模型给出最终回复）：
模型响应: stop_reason="end_turn", content="北京今天晴天，24°C，微风2级，非常适合户外运动！..."
```

### 14.2.3 循环中的关键工程考量

**1. 最大迭代次数（max_iterations）**

这是 Agent Loop 最重要的安全阀。没有上限的循环可能导致：
- Token 消耗失控（每次迭代都累积上下文）
- 死循环（模型反复调用同一工具而不推进任务）
- 费用爆炸（尤其是使用 Opus 等高价模型）

推荐：对于一般任务，10-15 次迭代足够；复杂编码任务可能需要 25-50 次。

**2. 上下文窗口管理**

每次迭代都会向 Messages 追加 assistant 响应和 tool_result。如果不加控制，长循环会快速填满上下文窗口。策略详见 14.6 节。

**3. 错误恢复**

工具执行可能失败（网络超时、权限不足、输入格式错误）。Agent 需要：
- 将错误信息格式化后注入上下文（而非直接崩溃）
- 让模型自主决定是重试、换策略、还是向用户求助

**4. 终止条件**

除了 `max_iterations`，还应支持：
- `stop_reason == "end_turn"`（模型自主判断任务完成）
- 连续 N 轮无工具调用（模型可能陷入困惑）
- 用户中断信号

---

## 14.3 单 Agent 模式

### 14.3.1 ReAct（Reasoning + Acting）模式

**概念**：ReAct 是 Agent 模式中最基础、最广泛使用的模式。它由 Yao et al. (2022) 提出，核心思想是将推理（Reasoning）和行动（Acting）交织在同一个循环中：

```
Thought → Action → Observation → Thought → Action → Observation → ...
```

每次迭代：
1. **Thought**：模型分析当前状态，用自然语言表达推理过程（"我需要先查询天气，然后根据天气判断..."）
2. **Action**：基于推理，决定调用哪个工具及参数
3. **Observation**：工具返回结果，成为下一轮推理的输入

**适用场景**：
- 需要多步信息检索的任务（先查 A，基于 A 的结果再查 B）
- 需要工具组合使用的任务
- 步骤数不固定、无法预先规划的场景

**ReAct vs 纯 Tool Use**：
纯 Tool Use 只支持单轮或少量固定轮次的工具调用。ReAct 将工具调用嵌入自主推理循环，让模型在每个步骤都能根据最新观察调整策略。

**实现要点**：
- 无需修改系统提示词——Claude 原生支持 `tool_use` 响应类型
- 循环骨架极简：`while True: response = client.messages.create(...); if end_turn: break; if tool_use: execute_tool(); continue`
- 关键挑战是上下文累积管理

### 14.3.2 Reflexion 模式

**概念**：Reflexion 是 ReAct 的增强版，在每次行动-观察之后增加了一个**自我评估和策略调整**阶段。它由 Shinn et al. (2022) 提出，核心思想是让 Agent 从自己的执行轨迹中学习：

```
ReAct Loop → Evaluate Trajectory → Reflect on Failures → Adjust Strategy → Retry
```

Reflexion 的关键区别在于**元认知**——Agent 不仅执行任务，还评估自己的执行质量，并在发现策略偏差时主动调整。

**Reflexion 的三个阶段**：

1. **执行阶段（Actor）**：标准的 ReAct 循环，产生一个完整的执行轨迹（trajectory）
2. **评估阶段（Evaluator）**：将轨迹交给评估器（可以是同一个模型的另一调用，也可以是启发式规则）分析：
   - 是否达成了任务目标？
   - 哪些步骤有效？哪些步骤冗余？
   - 是否存在更优的执行路径？
3. **反思阶段（Reflexion）**：将评估结果转化为可操作的改进建议，注入下一轮执行：
   - "上次在第 3 步使用了错误的数据源，这次应该从 API 直接获取"
   - "步骤 2 和步骤 3 可以合并，减少一次网络调用"

**适用场景**：
- 开放式的、需要多轮尝试的任务（代码调试、复杂数据分析）
- 初始策略不明确、需要试错的任务
- 对最终结果质量要求极高的场景

**代价**：每次反思都需要额外的 LLM 调用，Token 消耗比纯 ReAct 高 20-50%。

### 14.3.3 Plan-and-Execute 模式

**概念**：Plan-and-Execute 将任务执行分为两个明确分离的阶段——先规划完整计划，再逐步执行和验证。它与 ReAct 的核心区别在于**规划与执行的时间分离**：

```
Phase 1 (Plan):  Task → LLM generates step-by-step plan → Plan validated
Phase 2 (Execute): For each step → Execute → Verify → Next step or halt
```

**与 ReAct 的对比**：

| 维度 | ReAct | Plan-and-Execute |
|------|-------|------------------|
| 规划时机 | 每步即时推理 | 一次性全局规划 |
| 灵活性 | 高——可随时调整 | 低——计划在开始后不易更改 |
| 可预测性 | 低——路径动态变化 | 高——执行路径明确 |
| 适合任务 | 路径不确定的任务 | 步骤明确、可分解的任务 |
| 上下文消耗 | 较低（每步推理较短） | 较高（完整计划占用上下文） |

**实现要点**：
- `plan()` 阶段：提示模型"请先制定完整的执行计划，列出每个步骤的目标、输入、输出和验证标准，但暂不执行任何操作"
- `execute()` 阶段：按计划逐步执行，每一步执行后验证输出是否符合预期
- `verify()` 阶段：用断言或 LLM 检查每步结果

**适用场景**：
- 软件工程多文件修改（先在脑中规划修改哪些文件）
- 复杂数据管道（ETL 各步骤明确）
- 旅行规划（路线、住宿、景点分步确定）

---

## 14.4 多 Agent 模式

### 14.4.1 为什么需要多 Agent？

单 Agent 在处理复杂任务时会遇到根本性瓶颈：

1. **注意力稀释**：单个上下文窗口同时容纳"理解复杂需求"+"拆解任务"+"执行每一步"+"验证结果"会导致每个环节的质量下降
2. **能力边界**：某些子任务需要高度专业化（如安全审计、性能分析），用通用提示词效果不佳
3. **架构刚性**：单 Agent 循环绑定了固定的工具集和策略，无法根据子任务特性动态调整

多 Agent 模式通过**分工与协作**解决这些问题。

### 14.4.2 Supervisor-Worker 模式

**概念**：一个 Supervisor Agent（监督者/协调者）负责全局任务分解和结果整合，多个 Worker Agent（工作者）负责执行具体子任务。

```
                    ┌─────────────┐
                    │  Supervisor  │
                    │  任务分解     │
                    │  结果整合     │
                    └──┬──┬──┬───┘
                       │  │  │
          ┌────────────┘  │  └────────────┐
          ▼               ▼               ▼
    ┌──────────┐   ┌──────────┐   ┌──────────┐
    │ Worker 1 │   │ Worker 2 │   │ Worker 3 │
    │ 代码审查  │   │ 安全检查  │   │ 性能分析  │
    └──────────┘   └──────────┘   └──────────┘
```

**Supervisor 的职责**：
- 接收并理解用户任务
- 将任务分解为可并行/串行的子任务
- 为每个子任务分配合适的 Worker（基于 Worker 的能力描述）
- 收集 Worker 结果，进行去重、冲突解决和综合
- 向用户呈现最终结果

**Worker 的职责**：
- 接收明确的子任务描述（包含输入、预期输出格式、约束条件）
- 在自己的工具集和上下文中独立执行
- 返回结构化结果

**Anthropic 官方定位**（来自 *Building Effective Agents*）：
> "In the orchestrator-workers workflow, a central LLM dynamically breaks down tasks, delegates them to worker LLMs, and synthesizes their results. This workflow is well-suited for complex tasks where you can't predict the subtasks needed."

**适用场景**：
- 代码审查系统（Supervisor 接收 PR，Worker 分别检查代码质量、安全、性能）
- 多数据源综合分析（Worker 各自查询不同数据源，Supervisor 汇总）
- CI/CD 流水线中的质量门禁

### 14.4.3 Sub-Agent Orchestration 模式

**概念**：Sub-Agent Orchestration 与 Supervisor-Worker 的最大区别在于**主 Agent 不预先规划子任务**，而是**在执行过程中动态决定何时以及如何委托给子 Agent**。这是 Anthropic Agent SDK 原生支持的模式。

```
主 Agent（动态决策）：
  "我需要审查这个代码库" 
  → 调用 Agent 工具："code-reviewer"，输入 "检查 /src/auth.py 的安全漏洞"
  → 子 Agent 独立运行，返回审查结果
  → 主 Agent 根据结果决定："发现 XSS 风险，让 security-fixer 修复"
  → 调用 Agent 工具："security-fixer"，输入 "修复 XSS 风险..."
  → 子 Agent 修复后返回
  → 主 Agent 综合所有结果，生成最终报告
```

**与 Supervisor-Worker 的关键区别**：

| 维度 | Supervisor-Worker | Sub-Agent Orchestration |
|------|-------------------|------------------------|
| 子任务分配时机 | 预先规划 | 运行时动态决策 |
| 子任务依赖 | Supervisor 知道全局 | 主 Agent 逐步发现 |
| 适合场景 | 结构化的并行任务 | 探索性的、路径不确定的任务 |
| Agent SDK 支持 | 需自行实现协调逻辑 | 原生 `AgentDefinition` + `agents` 参数 |

**Anthropic Agent SDK 中的子 Agent 定义**：
```python
# 定义子 Agent
agents = {
    "code-reviewer": AgentDefinition(
        description="代码质量与安全审查专家",
        prompt="分析代码质量，检查安全漏洞，给出改进建议",
        tools=["Read", "Glob", "Grep"]
    ),
    "test-runner": AgentDefinition(
        description="运行测试并分析失败原因",
        prompt="运行项目的测试套件，分析失败用例的根因",
        tools=["Bash"]
    )
}
```

**适用场景**：
- 代码库探索与修复（既需要审查也需要修复和测试）
- 研究型任务（需要多轮查询、分析、交叉验证）
- 复杂的客户支持（需要查询知识库、调用内部 API、生成回复）

### 14.4.4 Multi-Agent Debate 模式

**概念**：多个 Agent 从不同角度/角色分析同一问题，通过讨论达成共识或呈现多元观点。每个 Agent 拥有独立的上下文窗口和推理链，避免了单一视角的偏见。

```
                  ┌────────────┐
                  │   用户问题   │
                  └─────┬──────┘
                        │
        ┌───────────────┼───────────────┐
        ▼               ▼               ▼
  ┌──────────┐   ┌──────────┐   ┌──────────┐
  │ Agent A  │   │ Agent B  │   │ Agent C  │
  │ 乐观视角  │   │ 悲观视角  │   │ 中立视角  │
  │ "可行"    │   │ "有风险"  │   │ "需要数据" │
  └────┬─────┘   └────┬─────┘   └────┬─────┘
       │               │               │
       └───────────────┼───────────────┘
                       ▼
               ┌────────────┐
               │  Moderator  │
               │ 汇总/评判   │
               └────────────┘
```

**核心机制**：
1. **角色定义**：每个 Agent 被赋予不同的系统提示词，代表不同的视角（乐观/悲观/中立，或技术/商业/用户）
2. **独立推理**：每个 Agent 在隔离的上下文中独立推理
3. **交叉辩论**：Agent 之间可以"看到"彼此的观点（通过 Moderator 汇总传递）
4. **收敛或分歧**：Moderator 可以促使 Agent 达成共识，或保留分歧，呈现多元观点

**适用场景**：
- 高风险决策辅助（投资分析、架构选择）
- 内容审核（多视角判断内容是否违规，降低误杀率）
- 创意评估（多视角评价提案的优缺点）

**工程挑战**：
- Token 消耗是单 Agent 的 N 倍（N 为参与 Agent 数）
- 协调延迟（需要等待最慢的 Agent 完成）
- 收敛机制设计（如何定义"共识"？投票？加权？）

### 14.4.5 Swarm 模式

**概念**：大量轻量级 Agent 通过简单的局部交互规则产生涌现性的全局行为。Swarm 模式受到自然界群体智能（蚁群、蜂群）的启发，不依赖中心化协调。

```
每个 Agent 的行为循环：
1. 感知局部环境（有限的上下文窗口）
2. 根据简单规则做决策
3. 执行动作（调用工具）
4. 释放信息素（写入共享记忆空间）
5. 其他 Agent 通过信息素间接协调
```

**核心特征**：
- **去中心化**：没有 Supervisor 或 Moderator
- **简单规则**：每个 Agent 的行为逻辑很简单
- **涌现行为**：复杂的全局行为从局部交互中"涌现"
- **信息素通信**：通过共享的 Memory Store 间接通信

**适用场景（前沿/实验性）**：
- Web 爬虫集群（多个 Agent 各自抓取不同页面，共享已访问 URL）
- 并行测试生成（多个 Agent 各自产生测试用例，覆盖不同边界条件）
- 大规模数据标注（多个 Agent 各自标注一批数据，通过共识机制验证）

**当前局限**：
- Claude API 的单请求延迟使得大规模并发成本高
- 缺乏成熟的信息素/共识机制框架
- 涌现行为难以预测和调试

---

## 14.5 Anthropic Agent SDK 详解

### 14.5.1 SDK 的定位与分层

Claude Agent SDK 是 Anthropic 官方提供的 Agent 构建工具包，于 2025 年底发布，2026 年初进入成熟期。它的定位是**填补 Claude API（单次请求-响应）与 Claude Code（完整 CLI 应用）之间的空白**：

```
Claude API ──────────> Agent SDK ──────────> Claude Code / Managed Agents
(底层原子接口)        (可编程 Agent 引擎)     (完整产品/托管服务)
```

SDK 提供两种语言支持：
- **Python SDK**：`pip install claude-agent-sdk`
- **TypeScript SDK**：`npm install @anthropic-ai/claude-agent-sdk`

### 14.5.2 SDK 的两个入口

**简单场景：`query()`**

```python
from claude_agent_sdk import query, ClaudeAgentOptions, ResultMessage

async for message in query(
    prompt="分析这个项目的认证模块，找出所有潜在的安全漏洞",
    options=ClaudeAgentOptions(
        allowed_tools=["Read", "Glob", "Grep"],
        cwd="/path/to/project"
    )
):
    if isinstance(message, ResultMessage):
        print(message.result)
```

`query()` 封装了完整的 Agent Loop：它会自动处理工具调用的执行和上下文注入，你只需消费异步消息流。

**复杂场景：`ClaudeSDKClient`**

```python
from claude_agent_sdk import ClaudeSDKClient, ClaudeAgentOptions

async with ClaudeSDKClient(options=options) as client:
    await client.query("你的任务")
    async for msg in client.receive_response():
        # 处理中间消息、权限请求、Hook 事件
        match msg:
            case PermissionRequest():
                decision = await your_custom_auth(msg)
                await client.respond_permission(decision)
            case StopEvent():
                break
```

**选择规则**：
- 绝大多数场景用 `query()` —— 代码量少 80%，覆盖 90% 的用例
- 需要自定义权限逻辑、Hook 拦截、Session 恢复时用 `ClaudeSDKClient`

### 14.5.3 工具体系

SDK 的工具分为两类：

**客户端工具（Client-side Tools）**——SDK 在你的进程中执行：
- `Read`：读取文件
- `Write`：写入文件
- `Edit`：编辑文件（基于 search/replace）
- `Bash`：执行 Shell 命令
- `Glob`：文件模式匹配
- `Grep`：文本搜索
- 自定义工具（通过 MCP 协议接入）

**服务端工具（Server-side Tools）**——Anthropic 云端托管执行：
- `WebSearch`：网页搜索
- `WebFetch`：网页内容抓取
- `CodeExecution`：云端代码沙箱执行
- `ComputerUse`：计算机操作（Beta）

### 14.5.4 权限系统

Agent 的自主性意味着风险。SDK 通过四级权限模式控制：

| 模式 | 行为 | 适用场景 |
|------|------|---------|
| `"default"` | 危险操作弹出确认 | 交互式开发 |
| `"plan"` | 只规划，不执行任何操作 | 任务预览/审核 |
| `"acceptEdits"` | 自动批准文件编辑 | 受信任的沙箱环境 |
| `"bypassPermissions"` | 跳过所有检查 | 完全自动化（慎用） |

### 14.5.5 Hook 机制

SDK 提供了完整的 Hook 生命周期，允许你在 Agent 的每个关键节点插入自定义逻辑：

```python
options = ClaudeAgentOptions(
    hooks={
        "PreToolUse": [HookMatcher(matcher="Bash", hooks=[audit_bash_command])],
        "PostToolUse": [HookMatcher(matcher="Edit|Write", hooks=[log_file_change])],
        "PostToolUseFailure": [HookMatcher(matcher="*", hooks=[alert_on_failure])],
        "Stop": [HookMatcher(matcher="*", hooks=[collect_metrics])],
    }
)
```

可拦截的生命周期事件：
- `PreToolUse` / `PostToolUse` / `PostToolUseFailure`
- `UserPromptSubmit`
- `Stop` / `SubagentStop`
- `PermissionRequest`

### 14.5.6 Session 管理

Agent SDK 原生支持跨请求的 Session 持久化：

```python
# 首次请求：捕获 session_id
session_id = None
async for msg in query(prompt="读取认证模块", options=ClaudeAgentOptions(...)):
    if isinstance(msg, SystemMessage) and msg.subtype == "init":
        session_id = msg.data["session_id"]

# 后续请求：恢复 Session，模型记得之前的上下文
async for msg in query(
    prompt="找到所有调用认证模块的地方",
    options=ClaudeAgentOptions(resume=session_id)
):
    ...
```

### 14.5.7 子 Agent 的原生支持

SDK 通过 `agents` 参数提供原生的子 Agent 定义和调度：

```python
options = ClaudeAgentOptions(
    allowed_tools=["Read", "Glob", "Grep", "Agent"],
    agents={
        "code-reviewer": AgentDefinition(
            description="代码质量与安全审查专家",
            prompt="分析代码的架构质量、安全隐患、性能瓶颈",
            tools=["Read", "Glob", "Grep"]
        ),
        "test-writer": AgentDefinition(
            description="单元测试编写专家",
            prompt="为给定的代码模块编写全面的单元测试",
            tools=["Read", "Write", "Edit", "Bash"]
        )
    }
)
```

主 Agent 通过 `"Agent"` 工具动态委托任务给子 Agent，两者共享 `allowed_tools` 白名单。

---

## 14.6 上下文窗口管理策略

Agent 循环的最大工程挑战是**上下文窗口的渐进式膨胀**。每轮迭代都会向 Messages 追加新的内容，如果不加控制，即便 200K tokens 的窗口也会在 50-100 轮迭代后被填满。

### 14.6.1 上下文消耗模型

一次典型的 Agent 迭代消耗：
- System Prompt：2-5K tokens（取决于工具定义数量）
- User Message：0.5-2K tokens
- Assistant Response（含 tool_use）：1-3K tokens
- Tool Result：1-10K tokens（高度可变，读文件可能一次消耗数十K）

单轮迭代平均消耗 5-15K tokens。在 200K 上下文中，从空开始约可运行 13-40 轮。

### 14.6.2 策略一：Prompt Caching

将 System Prompt 和工具定义标记为可缓存，可节省 90% 的重复输入成本：

```python
system_prompt = [
    {"type": "text", "text": "...", "cache_control": {"type": "ephemeral"}}
]
tools = [
    {"name": "get_weather", ..., "cache_control": {"type": "ephemeral"}}
]
```

### 14.6.3 策略二：上下文窗口预留与截断

```python
class ContextBudget:
    def __init__(self, max_tokens: int = 180000, reserve: int = 20000):
        self.max_tokens = max_tokens
        self.reserve = reserve  # 为最终回复预留
        self.used = 0

    def can_add(self, tokens: int) -> bool:
        return self.used + tokens <= self.max_tokens - self.reserve

    def add(self, tokens: int):
        self.used += tokens
```

当预算不足时，采取以下措施之一：
- **滑动窗口**：保留最近的 N 轮对话，丢弃最早的消息对（保留 System 和第一条 User）
- **摘要压缩**：调用轻量模型（如 Haiku）将历史对话压缩为摘要
- **重置并保存状态**：将当前状态持久化，重新开始一个 Session

### 14.6.4 策略三：工具输出裁剪

工具的原始输出常常远大于 LLM 所需的实际信息。例如，`grep` 可能返回 500 行匹配结果，但 Agent 只需要前 20 行来判断模式：

```python
def trim_tool_output(output: str, max_chars: int = 8000) -> str:
    if len(output) <= max_chars:
        return output
    half = max_chars // 2
    return output[:half] + f"\n... (截断 {len(output) - max_chars} 字符) ...\n" + output[-half:]
```

### 14.6.5 策略四：Compaction

在第 8 章中详细讨论的 Compaction 机制同样适用于 Agent 循环。当上下文逼近窗口上限时：

1. 生成历史对话的结构化摘要
2. 保留 System Prompt、原始 Task Description、最近 N 轮对话
3. 用摘要替换中间的对话历史

---

## 14.7 错误恢复与 Agent 韧性

### 14.7.1 常见 Agent 失败模式

| 失败类型 | 表现 | 根因 |
|---------|------|------|
| 工具循环 | 反复调用同一工具，不推进任务 | 模型未理解工具输出或策略僵化 |
| 中途迷失 | 执行大量步骤后偏离原始目标 | 长上下文中的注意力衰减 |
| 过早终止 | 任务未完成就声明完成 | 模型过于乐观或验证不足 |
| 幻觉工具参数 | 传入不存在的参数 | 工具定义不清晰或模型训练数据干扰 |
| 资源耗尽 | 上下文窗口满或迭代次数超限 | 任务复杂度超出 Agent 能力边界 |

### 14.7.2 韧性设计原则

**1. 优雅降级（Graceful Degradation）**

工具执行失败时，不要崩溃——将错误格式化为信息丰富的 tool_result：

```python
try:
    result = execute_tool(tool_name, tool_input)
    return {"success": True, "result": result}
except Exception as e:
    return {
        "success": False,
        "error": str(e),
        "error_type": type(e).__name__,
        "suggestion": "请检查输入参数是否正确，或尝试其他方法"
    }
```

**2. 看门狗（Watchdog）**

监控 Agent 行为，干预异常模式：
- 连续 3 轮调用同一工具且输入几乎相同 → 注入提醒："你似乎陷入了循环，请尝试不同的方法"
- 最近 5 轮无实质性进展 → 建议："当前策略似乎未取得进展，是否考虑重新评估任务？"

**3. 检查点（Checkpoint）**

每 N 轮保存完整的 Messages 状态，支持从失败点恢复而非从头开始。

**4. 人机交互（Human-in-the-Loop）**

对于高风险操作，暂停 Agent 并请求人工确认。

### 14.7.3 迭代次数控制

```python
class IterationLimit:
    def __init__(self, soft_limit: int = 10, hard_limit: int = 25):
        self.soft_limit = soft_limit
        self.hard_limit = hard_limit
        self.count = 0

    def check(self) -> str:
        """返回 'continue', 'warn', 'stop'"""
        self.count += 1
        if self.count <= self.soft_limit:
            return "continue"
        elif self.count <= self.hard_limit:
            return "warn"  # 向 Agent 发送警告，但允许继续
        else:
            return "stop"  # 强制终止
```

---

## 14.8 最佳实践

### 14.8.1 何时使用哪种模式

```
任务特征                                推荐模式
─────────────────────────────────────────────────────
可预定义步骤、路径固定               → Prompt Chaining / Workflow
步骤不确定、需要探索                 → ReAct Agent Loop
需要从失败中学习、多轮优化           → Reflexion
步骤多但可预先规划、需可预测性       → Plan-and-Execute
子任务独立可并行                     → Supervisor-Worker
子任务依赖需动态发现                 → Sub-Agent Orchestration
高风险决策、需多视角                 → Multi-Agent Debate
大规模并行简单任务                   → Swarm
```

### 14.8.2 成本-质量权衡

| 模式 | 相对成本 | 质量提升 | 适用门槛 |
|------|---------|---------|---------|
| Messages API + Tool Use | 1x | 基准 | 低 |
| ReAct | 2-5x | +20-40% | 低 |
| Reflexion | 3-8x | +30-60% | 中 |
| Plan-and-Execute | 2-4x | +15-30% | 低 |
| Supervisor-Worker | 3-6x | +25-50% | 中 |
| Sub-Agent Orchestration | 3-6x | +25-50% | 高 |
| Multi-Agent Debate | 5-10x | +30-50% | 高 |

### 14.8.3 工程设计清单

实施 Agent 系统前，确认以下事项：

- [ ] **简单方案真的不够吗？** 先尝试用 Messages API + Tool Use 完成 80% 的场景
- [ ] **定义了明确的迭代上限**：软限制 10 轮 + 硬限制 25 轮
- [ ] **上下文预算已规划**：部署了至少一种上下文管理策略
- [ ] **错误处理已完善**：所有工具调用都有 try/except，错误信息对模型友好
- [ ] **监控已就位**：记录每轮迭代的 token 消耗、工具调用详情、执行时长
- [ ] **测试了边界情况**：空工具结果、超长工具输出、工具全部不可用的降级行为
- [ ] **人工审核机制已建立**：对于高风险操作（删除文件、数据库写入）有人工确认环节

### 14.8.4 常见反模式

1. **过度工程化**：用一个完整的 Agent 循环解决简单的文本分类问题
2. **无限制循环**：没有 max_iterations，导致 token 费用失控
3. **工具定义过大**：在 System Prompt 中塞入 50+ 工具定义，稀释了模型注意力
4. **忽略工具输出格式**：工具返回非结构化的、对模型不友好的原始数据
5. **过早终止**：依赖 `stop_reason == "end_turn"` 作为唯一终止条件，没有超时/超次保护

---

## 14.9 自测题

### 基础题

1. **Agent Loop 的核心四个阶段是什么？请用一句话描述每个阶段的职责。**

2. **ReAct 和 Plan-and-Execute 模式的核心区别是什么？各适合什么场景？**

### 编码题

3. **实现一个最小 ReAct Loop**：编写一个函数 `react_loop(task: str, tools: dict, max_iterations: int = 10)`，使用 Anthropic Messages API + Tool Use 实现完整的 Thought -> Action -> Observation 循环。要求处理 `end_turn` 和 `tool_use` 两种 stop_reason，并在达到 max_iterations 时优雅终止。

4. **实现一个 Sub-Agent Orchestrator**：编写一个类 `SubAgentOrchestrator`，支持注册多个子 Agent（每个有独立的 system prompt 和工具集），主 Agent 可以动态调用子 Agent 处理子任务，并收集和综合子 Agent 的返回结果。

### 设计题

5. **上下文窗口管理设计**：假设你的 Agent 运行在一个 200K tokens 的上下文窗口中，每次工具调用平均产生 3K tokens 的 tool_result。你需要支持最多 50 轮迭代。描述你的上下文管理策略，包括何时触发 Compaction、如何选择保留和丢弃哪些消息、以及如何验证策略的有效性。

---

## 14.10 本章小结

本章从 Agent 的基本概念出发，系统性地覆盖了从单 Agent 到多 Agent 的完整模式谱系：

- **Agent Loop** 是这一切的基础——`Perceive → Reason → Act → Observe` 四个阶段构成了自主 Agent 的执行引擎
- **单 Agent 模式**：ReAct（基础循环）、Reflexion（增加自我反思）、Plan-and-Execute（先规划后执行）
- **多 Agent 模式**：Supervisor-Worker（中心化协调）、Sub-Agent Orchestration（动态委托）、Multi-Agent Debate（多视角辩论）、Swarm（涌现行为）
- **Anthropic Agent SDK** 提供了开箱即用的 Agent 基础设施，内置工具、权限、Hook、Session 管理和子 Agent 支持
- **上下文管理**和**错误恢复**是生产级 Agent 系统的必要条件
- **简单优先**：在评估是否需要 Agent 时，始终从最简单的方案开始

Agent 不是魔术——它只是将 LLM 的基础能力（推理、工具使用）封装在一个结构化的执行循环中。理解这个循环的每一环，你就能构建出既强大又可控的 Agent 系统。
