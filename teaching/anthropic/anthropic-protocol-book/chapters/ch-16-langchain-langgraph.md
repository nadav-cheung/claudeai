# 第 16 章：LangChain & LangGraph —— Anthropic Claude 的 Agent 工程平台

> **本章目标**：掌握在 LangChain 生态中集成 Anthropic Claude 的完整方法。完成本章后，你将能够使用 LangChain 的 ChatAnthropic 封装调用 Claude，使用 LangGraph 构建有状态的 Agent 工作流，并利用 LangSmith 进行可观测性监控和评估。同时，你将深入理解框架与原生 SDK 的取舍边界。

---

## 16.1 概念全景

### LangChain 在 Agent 开发中的定位

LangChain 是目前最流行的 LLM 应用开发框架之一，截至 2025 年拥有超过 100,000 GitHub stars。它的核心定位是**降低 LLM 应用开发的门槛**——提供一套标准化的抽象层，让开发者不必从头处理提示模板、对话记忆、工具绑定、流式输出等重复性工程问题。

然而，LangChain 并非银弹。理解"什么时候该用框架，什么时候该用原生 SDK"是每个严肃的 Agent 开发者必须回答的问题。

**LangChain 的三大核心价值**：

1. **抽象统一**：无论底层是 Claude、GPT、Gemini 还是开源模型，上层代码几乎相同。这个"一次编写，多模型运行"的能力在需要灵活切换模型供应商的场景中价值巨大。

2. **组件生态**：提示模板（PromptTemplate）、对话记忆（Memory）、检索器（Retriever）、文档加载器（Document Loader）等组件开箱即用，避免重复造轮子。

3. **工作流编排（LangGraph）**：对于需要多步骤推理、条件分支、人机协同的复杂 Agent，LangGraph 提供的状态图模型是目前最成熟的解决方案之一。

**LangChain 的代价**：

1. **抽象泄漏**：高度封装意味着排错困难。当 `ChatAnthropic` 内部某次重试失败或流式连接中断时，错误堆栈可能穿越五六层抽象，定位根因比直接使用 `anthropic` SDK 困难得多。

2. **版本演进快**：LangChain 的 API 仍在快速变化中（v0.1 → v0.2 → v0.3 → v1.0），升级可能带来较大的迁移成本。

3. **性能层损耗**：每个抽象层都增加若干函数调用和对象分配。对于高吞吐、低延迟的应用，这些开销不可忽略。

**决策框架**：

| 场景 | 推荐方案 |
|------|----------|
| 简单问答 / 单轮翻译 | 原生 Anthropic SDK |
| 多轮对话 + 记忆管理 | LangChain ChatAnthropic + Memory |
| 工具调用 Agent | LangChain ChatAnthropic + bind_tools |
| 复杂多步骤工作流 | LangGraph StateGraph |
| 需要跨模型供应商 | LangChain（抽象层价值最大） |
| 高吞吐生产服务 | 原生 SDK + 自定义编排 |
| 原型验证 / 快速实验 | LangChain 全栈 |
| 需要可观测性 | LangSmith（可与原生 SDK 配合） |

**本章学习成果**：

完成本章后，你将能够：

1. 使用 `ChatAnthropic` 封装调用 Claude，理解其与原生 SDK 的差异。
2. 在 LangChain 中绑定工具、构建提示模板、管理对话记忆。
3. 使用 LangGraph 的 `StateGraph` 构建 Tool-Use Agent 工作流，集成检查点（Checkpointing）和人机协同（Human-in-the-Loop）。
4. 使用 LangSmith 进行 trace、评估和实验管理。
5. 在 Python 和 TypeScript/Node.js 两种语言中完成以上全部操作。

---

## 16.2 协议规范与集成详解

### 16.2.1 LangChain 架构与设计哲学

LangChain 的架构可以理解为三个层次：

```
┌──────────────────────────────────────────────────┐
│                  应用层（你的代码）                  │
├──────────────────────────────────────────────────┤
│   LangGraph（Agent 编排）   │   LangServe（部署）   │
├──────────────────────────────────────────────────┤
│   langchain（Chain / Agent / Memory / Retrieval）  │
├──────────────────────────────────────────────────┤
│   langchain-core（Runnable / LCEL / 消息抽象）      │
├──────────────────────────────────────────────────┤
│   langchain-anthropic（ChatAnthropic 模型适配）     │
├──────────────────────────────────────────────────┤
│   anthropic SDK（HTTP 通信层）                      │
└──────────────────────────────────────────────────┘
```

**核心设计原则**：

- **Runnable 协议**：LangChain 中几乎所有组件都实现了 `Runnable` 接口（`invoke`、`stream`、`batch`），这使得组件可以像乐高积木一样通过 `|` 管道操作符（LCEL——LangChain Expression Language）自由组合。

- **消息抽象**：`langchain-core` 提供了一套与具体模型无关的消息类型——`HumanMessage`、`AIMessage`、`SystemMessage`、`ToolMessage`。这套抽象的威力在于：你可以在 Claude 和 GPT 之间切换模型，而无需修改消息构建代码。

- **回调系统**：通过 `callbacks` 参数，可以在 LLM 调用的每个生命周期节点（`on_llm_start`、`on_llm_end`、`on_llm_error` 等）注入自定义逻辑。LangSmith 的 tracing 功能正是基于这个回调系统实现的。

### 16.2.2 ChatAnthropic：Claude 的 LangChain 封装

`ChatAnthropic` 是 LangChain 生态中 Anthropic Claude 的标准入口。它位于独立的 `langchain-anthropic` 包中，底层依赖 `anthropic` Python/Node SDK。

**类参数全表**：

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `model` | `str` | 必填 | 模型名称，如 `"claude-sonnet-4-20250514"` |
| `temperature` | `float` | `None` | 采样温度，0-1 之间。Claude 建议 0.3-0.7 |
| `max_tokens` | `int` | `1024` | 最大输出 token 数 |
| `max_tokens_to_sample` | `int` | 已弃用 | 请使用 `max_tokens` |
| `timeout` | `float` | `None` | HTTP 请求超时（秒）。`None` 表示无限制 |
| `max_retries` | `int` | `2` | 失败重试次数 |
| `streaming` | `bool` | `False` | 是否启用流式输出 |
| `stop_sequences` | `List[str]` | `None` | 停止序列列表 |
| `top_p` | `float` | `None` | Nucleus 采样参数 |
| `top_k` | `int` | `None` | Top-K 采样参数 |
| `default_headers` | `Dict` | `None` | 额外的 HTTP 头 |
| `api_key` | `str` | 环境变量 | Anthropic API Key。若不提供，则从 `ANTHROPIC_API_KEY` 环境变量读取 |
| `base_url` | `str` | `None` | 自定义 API 端点（用于代理或私有部署） |
| `anthropic_api_key` | `str` | 已弃用 | 请使用 `api_key` |
| `anthropic_api_url` | `str` | 已弃用 | 请使用 `base_url` |

**模型选择指南**：

| 模型 | 上下文窗口 | 特点 | 适用场景 |
|------|-----------|------|----------|
| `claude-sonnet-4-20250514` | 200K | 速度与质量的最佳平衡 | 大多数生产场景 |
| `claude-haiku-4-5-20251001` | 200K | 速度最快，成本最低 | 高吞吐简单任务 |
| `claude-opus-4-20250514` | 200K | 最强推理能力 | 复杂分析、代码生成 |
| `claude-3-5-sonnet-latest` | 200K | 上一代标杆 | 兼容性需求 |

**版本兼容性提示**：LangChain 的 `ChatAnthropic` 封装与 Anthropic API 版本之间没有硬绑定关系。`ChatAnthropic` 通过底层 `anthropic` SDK 发送请求，SDK 会自动处理 API 版本头的设置。因此，只要 `langchain-anthropic` 包版本不是极端陈旧，通常无需担心 API 版本兼容性。建议访问 [langchain.com](https://langchain.com) 查阅最新的 `langchain-anthropic` 文档获取最新的模型支持列表。

**与原生 SDK 的关键差异**：

1. **调用方式**：`ChatAnthropic` 遵循 LangChain 的 `invoke` / `ainvoke` / `stream` / `astream` 模式，而非原生 SDK 的 `messages.create()`。

2. **消息格式**：输入接受 LangChain 的 `HumanMessage` / `AIMessage` / `SystemMessage` 对象，而非原生 dict。输出返回 `AIMessage` 对象。

3. **Tool Use**：通过 `bind_tools()` 绑定工具，模型返回的 `AIMessage.tool_calls` 是 LangChain 的标准化格式，而非 Anthropic 原生的 `tool_use` Content Block。这种差异在混合使用 LangChain 工具和 Anthropic 原生工具（如 `text_editor`、`web_fetch`）时需要特别注意。

4. **重试行为**：`ChatAnthropic` 内部有独立的指数退避重试机制（`max_retries` 控制），这与原生 SDK 的重试逻辑叠加时可能导致 double-retry 问题。建议：使用 `ChatAnthropic` 时将原生 SDK 的重试设为 0。

### 16.2.3 工具绑定：bind_tools() 与 StructuredTool

在 LangChain 中绑定工具有两种主流方式：

**方式一：使用 `bind_tools()` 绑定函数式工具**

```python
from langchain_anthropic import ChatAnthropic

model = ChatAnthropic(model="claude-sonnet-4-20250514")
model_with_tools = model.bind_tools(
    [
        {
            "name": "get_weather",
            "description": "Get the current weather in a given location",
            "input_schema": {
                "type": "object",
                "properties": {
                    "location": {
                        "type": "string",
                        "description": "The city and state, e.g. San Francisco, CA"
                    }
                },
                "required": ["location"]
            }
        }
    ]
)
```

**方式二：使用 `StructuredTool` 定义工具**

```python
from langchain_core.tools import StructuredTool

def get_weather(location: str) -> str:
    """Get the current weather in a given location."""
    return f"The weather in {location} is sunny, 72°F."

weather_tool = StructuredTool.from_function(
    func=get_weather,
    name="get_weather",
    description="Get the current weather in a given location"
)

model_with_tools = model.bind_tools([weather_tool])
```

**Anthropic 原生工具支持**：`ChatAnthropic` 也支持 Anthropic 专有的内置工具类型，如：

- `text_editor_20250728`：Claude 的文本编辑器工具，支持 `str_replace_based_edit_tool`
- `web_fetch_20250910`：Claude 的网页抓取工具
- `memory_20250818`：Claude 的记忆工具

这些工具只能通过原生 Anthropic API 的格式定义，在 LangChain 中需要以字典形式传递给 `bind_tools()`。

**工具调用流程对比**：

```
LangChain 流程:
  bind_tools() → invoke() → AIMessage.tool_calls → Tool.invoke() → ToolMessage → 再次 invoke()

Anthropic 原生流程:
  messages.create(tools=[...]) → tool_use Content Block → tool_result Content Block → messages.create()
```

关键差异在于：LangChain 将 Anthropic 的 `tool_use` / `tool_result` Content Blocks 自动转换为 `AIMessage.tool_calls` / `ToolMessage`，使得工具调用的处理代码在模型间是统一的。但代价是丢失了 Anthropic 原生格式中的一些字段（如 `tool_use` 的 `id` 值在 LangChain 中变成了新的 UUID）。

### 16.2.4 提示模板系统

LangChain 的提示模板系统分为两个层次：

**基础 PromptTemplate**：适用于纯文本补全场景（不推荐用于 Claude，因为 Claude 原生支持 Chat 模型）。

**ChatPromptTemplate**：专为 Chat 模型设计，支持消息角色。这是与 Claude 交互的标准方式。

| 组件 | 用途 | 示例 |
|------|------|------|
| `SystemMessagePromptTemplate` | 系统提示模板 | 设定助手的行为和角色 |
| `HumanMessagePromptTemplate` | 用户消息模板 | 用户输入 |
| `AIMessagePromptTemplate` | AI 消息模板 | 历史对话中的 AI 回复 |
| `MessagesPlaceholder` | 消息占位符 | 动态插入历史消息列表或工具消息列表 |

**MessagesPlaceholder 的关键作用**：

`MessagesPlaceholder` 是构建 Agent 时最重要的组件之一。它允许你在提示模板中预留一个位置，运行时动态插入一组消息（例如对话历史或工具调用结果）。没有它，你将无法构建支持多轮工具调用的 Agent。

```python
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder

prompt = ChatPromptTemplate.from_messages([
    ("system", "You are a helpful assistant."),
    MessagesPlaceholder(variable_name="history"),  # 动态对话历史
    ("human", "{input}"),
    MessagesPlaceholder(variable_name="agent_scratchpad"),  # 工具调用中间结果
])
```

### 16.2.5 记忆集成

LangChain 提供了多种记忆（Memory）实现。记忆的核心价值是在多轮对话中保持上下文，避免每次都传递完整的对话历史。

| 记忆类型 | 策略 | 适用场景 | Claude 适配 |
|----------|------|----------|------------|
| `ConversationBufferMemory` | 存储全部历史 | 短对话 | 直接可用，无特殊要求 |
| `ConversationBufferWindowMemory` | 滑动窗口，保留最近 N 轮 | 中等长度对话 | 直接可用 |
| `ConversationSummaryMemory` | 用 LLM 摘要历史 | 长对话 | 摘要模型可与主模型不同 |
| `ConversationSummaryBufferMemory` | 摘要 + 窗口混合 | 长对话（推荐） | 摘要模型建议用 Haiku 节省成本 |
| `ConversationTokenBufferMemory` | Token 数量限制 | 精确控制 token 消耗 | 利用 Claude 的 tokenizer |

**使用建议**：

对于 Claude 来说，200K 上下文窗口使得大多数场景下 `ConversationBufferMemory`（全量存储）是完全可行的。只有在对话极长（超过 100 轮）或需要严格控制 token 消耗时，才建议使用摘要型记忆。过早引入摘要反而会丢失细节信息。

### 16.2.6 LangGraph：Agent 编排引擎

LangGraph 是 LangChain 生态系统中的 Agent 编排层，核心思想是将 Agent 的行为建模为**有向图（StateGraph）**，其中：

- **状态（State）**：在图的节点间流转的数据结构，通常是 `TypedDict` 或 Pydantic 模型
- **节点（Node）**：图中的执行单元，接收状态并返回部分状态更新
- **边（Edge）**：连接节点，决定执行流
- **条件边（Conditional Edge）**：根据当前状态动态选择下一个节点

#### StateGraph 的核心概念

**1. 状态定义**

```python
from typing import Annotated, TypedDict
from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages

class AgentState(TypedDict):
    messages: Annotated[list[BaseMessage], add_messages]
    # add_messages 是一个 reducer：新消息追加到列表，而非替换
```

`add_messages` 是 LangGraph 中最常用的 reducer。它定义了状态合并策略：对于 `messages` 字段，新消息会被追加到现有列表末尾（而不是覆盖）。同名消息 ID 的更新会替换旧消息。

**2. 节点定义**

节点是一个接收状态、返回状态更新的函数：

```python
def call_model(state: AgentState) -> dict:
    response = model.invoke(state["messages"])
    return {"messages": [response]}
```

**3. 条件边**

条件边通过一个路由函数决定下一个节点：

```python
def should_continue(state: AgentState) -> Literal["tools", "__end__"]:
    last_message = state["messages"][-1]
    if hasattr(last_message, "tool_calls") and last_message.tool_calls:
        return "tools"
    return "__end__"
```

#### 标准的 ReAct Agent 模式

LangGraph 最经典的 Agent 模式是 ReAct（Reasoning + Acting）循环：

```
        ┌──────────┐
START →│call_model │ ←──────┐
        └─────┬────┘        │
              │             │
         tool_calls?        │
         ┌───┴───┐         │
         │ YES   │ NO      │
         ▼       ▼         │
    ┌───────┐  END         │
    │ tools  │─────────────┘
    └───────┘
```

这个循环的本质是：模型要么给出最终回答（结束），要么发起工具调用（执行工具后返回模型）。

#### Checkpointing 与持久化

Checkpointing 是 LangGraph 区别于简单 Agent 框架的核心特性。它在图的每个节点执行后自动保存状态快照，支持：

- **断点续传**：Agent 在执行过程中崩溃或超时后，可以从上次检查点恢复
- **时间旅行**：回退到任意历史检查点，重新执行
- **分支探索**：从某个检查点分叉（fork），并行探索不同的执行路径
- **人机协同基础**：中断（interrupt）必须在 checkpointer 支持下工作

支持的 Checkpointer 后端：

| 后端 | 特点 | 适用场景 |
|------|------|----------|
| `InMemorySaver` | 内存存储，进程重启丢失 | 开发调试、原型验证 |
| `SqliteSaver` | 本地 SQLite 持久化 | 单机部署 |
| `PostgresSaver` | PostgreSQL 持久化 | 生产环境 |
| `RedisSaver` | Redis 存储 | 高性能分布式 |

```python
from langgraph.checkpoint.memory import InMemorySaver

checkpointer = InMemorySaver()
agent = builder.compile(checkpointer=checkpointer)

config = {"configurable": {"thread_id": "conversation-1"}}
agent.invoke({"messages": [HumanMessage(content="Hello")]}, config)
# 后续调用使用相同的 thread_id 可恢复对话上下文
```

#### Human-in-the-Loop（HITL）模式

LangGraph 提供两种人机协同方式：

**1. `interrupt()` —— 动态中断**

在节点函数中调用 `interrupt()`，暂停执行并等待外部输入。这是最灵活的方式。

```python
from langgraph.types import interrupt

def review_node(state: AgentState) -> dict:
    # 向人类展示当前计划，等待批准
    approval = interrupt({
        "message": "Please review the plan",
        "plan": state.get("plan"),
    })
    if approval == "approved":
        return {"status": "executing"}
    return {"status": "revising"}
```

**2. `breakpoints` —— 静态断点**

在编译图时指定在特定节点之前或之后暂停：

```python
agent = builder.compile(
    checkpointer=checkpointer,
    interrupt_before=["tools"],  # 每次工具调用前暂停
)
```

**HITL 适用场景**：

- 敏感操作确认（付款、删除数据、发送邮件）
- 复杂决策审核（生成的代码/计划需要人工审查）
- 错误恢复（Agent 出错后人工介入指导后续步骤）

### 16.2.7 LangSmith：可观测性与评估平台

LangSmith 是 LangChain 生态的 DevOps 平台，提供 LLM 应用的可观测性、实验管理和评估能力。

#### 核心功能对比

| 功能 | 说明 | 是否依赖 LangChain |
|------|------|-------------------|
| **Tracing** | 自动记录 LLM 调用的输入、输出、延迟、token 消耗 | 否（通过回调或 OpenTelemetry 支持任意 SDK） |
| **Metrics** | 聚合延迟、错误率、token 消耗等指标 | 否 |
| **Evaluation** | 定义评估器（evaluator），在数据集上运行评估实验 | 否（但便利函数依赖 LangChain） |
| **Dataset** | 管理测试用例（输入-期望输出对） | 否 |
| **Experiment** | 对比不同模型/参数/提示的评估结果 | 否 |
| **Hub** | 社区共享的提示模板仓库 | 是 |

**与原生 Anthropic SDK 的配合**：

LangSmith 的 tracing 功能不需要 LangChain。你可以通过 `@traceable` 装饰器或 `wrap_openai` 风格的工具直接追踪原生 SDK 调用：

```python
from langsmith import traceable
from anthropic import Anthropic

client = Anthropic()

@traceable(name="claude-call")
def ask_claude(prompt: str) -> str:
    response = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=1024,
        messages=[{"role": "user", "content": prompt}],
    )
    return response.content[0].text
```

#### 评估器（Evaluator）类型

| 类型 | 说明 |
|------|------|
| `correctness` | 基于参考答案或 LLM-as-Judge 评估正确性 |
| `groundedness` | 评估回答是否基于提供的上下文 |
| `relevance` | 评估回答与问题的相关性 |
| `concision` | 评估回答是否简洁 |
| `custom` | 自定义 Python/JS 函数评估器 |

### 16.2.8 决策指南：框架 vs 原生 SDK vs 混合

```
需要多模型切换？
├── 是 → LangChain ChatAnthropic（抽象层价值最大化）
└── 否 → 继续判断

需要多步骤 Agent 工作流？
├── 是 → 继续判断
│   ├── 简单线性流程 → 原生 SDK + 自定义编排
│   └── 复杂分支 / 需 HITL / 需持久化 → LangGraph
└── 否 → 原生 Anthropic SDK

需要可观测性？
├── 是 → LangSmith（独立于 LangChain，可配合原生 SDK）
└── 否 → 日志系统 + 手动埋点
```

**混合架构推荐**：在实际生产系统中，最常见的模式是**混合架构**——核心 LLM 调用使用原生 Anthropic SDK（性能和可控性最优），编排层使用 LangGraph（状态管理和持久化成熟），可观测性使用 LangSmith（trace 和评估体系完善）。

**版本兼容性**：本章代码基于 langchain-anthropic >= 0.3.0、langgraph >= 0.2.0、langsmith >= 0.2.0。这些包的 API 仍在快速演进，具体的最新 API 请务必查阅 [langchain.com](https://langchain.com) 官方文档。

---

## 16.3 最佳实践

### 16.3.1 框架 vs 原生 SDK 的取舍清单

**使用 LangChain / LangGraph 的充分理由**：

1. **团队需要跨模型灵活性**：如果你需要在 Claude、GPT、Gemini 之间自由切换，LangChain 的消息抽象和统一接口价值巨大。

2. **复杂工作流超出简单循环**：当 Agent 需要条件分支、并行执行、子图嵌套、人机协同、断点续传——LangGraph 是经过实战检验的选择。

3. **需要开箱即用的记忆、检索、文档加载**：自己实现这些组件需要大量时间，LangChain 的成熟度降低了"重复造轮子"的风险。

4. **原型验证阶段**：LangChain 让你从 idea 到可运行原型的速度最快。

**使用原生 Anthropic SDK 的充分理由**：

1. **性能和延迟是最关键指标**：每一层抽象都有性能开销。对于高吞吐场景，原生 SDK 是最小开销的选择。

2. **需要细粒度控制**：你想精确控制重试策略、定制 Content Block 结构、或者使用 Anthropic 的 beta 功能（如 extended thinking 的 budget_tokens 精确调节）。

3. **团队对 LangChain 缺乏深度理解**：LangChain 的排错曲线陡峭。如果团队没有 LangChain 专家，引入框架可能弊大于利。

4. **简单应用不需要框架**：一个 50 行的原生 SDK 脚本就能完成的工作，不要引入 5 个额外的依赖包。

### 16.3.2 常见陷阱与规避

1. **Double-retry 问题**：`ChatAnthropic` 的 `max_retries` 和底层 `anthropic` SDK 的重试可能叠加。解决：将 `ChatAnthropic` 的重试设为实际需要的值，或在 `anthropic` SDK 层面将 `max_retries` 设为 0。

2. **Tool Call ID 不一致**：在 LangChain 中手动处理 `tool_calls` 时，`AIMessage.tool_calls` 的 `id` 字段可能与 Anthropic 原生的 `tool_use.id` 不同。构建 `ToolMessage` 时必须使用 `AIMessage.tool_calls` 返回的 `id`，否则模型会报错。

3. **MessagesPlaceholder 缺失**：忘记在 ChatPromptTemplate 中添加 `MessagesPlaceholder` 是构建 Agent 时最常见的问题。工具调用的中间结果（`function` / `tool` role 消息）必须通过 `agent_scratchpad` 占位符插入。

4. **Checkpointer 遗忘**：使用 `interrupt()` 或需要跨调用保持状态时，忘记 `compile(checkpointer=...)` 会导致运行时错误或状态丢失。

5. **LangChain 版本与 Claude 模型名称不匹配**：LangChain 的 `ChatAnthropic` 内部会验证模型名称。使用最新模型时，需要确保 `langchain-anthropic` 版本足够新。

6. **Anthropic 原生工具格式混用**：`text_editor`、`web_fetch`、`memory` 等 Anthropic 原生工具必须使用 Anthropic 的格式定义（`{"type": "text_editor_20250728", ...}`），不能使用 LangChain 的 `StructuredTool` 包装。同时，工具执行和 `tool_result` 的构建也需要按 Anthropic 的规范进行。

### 16.3.3 生产部署建议

1. **使用 LangGraph 作为编排层，ChatAnthropic 作为调用层**：这是当前最成熟的生产架构模式。

2. **Checkpointer 选择 PostgreSQL**：生产环境中，`PostgresSaver` 提供 ACID 保证和持久化，优于 `InMemorySaver` 和 `SqliteSaver`。

3. **启用 LangSmith 但不依赖它**：LangSmith 是"附加价值"而非"硬依赖"。所有核心功能应该在 LangSmith 不可用时仍能运行。

4. **配置合理的 timeout**：Claude 的某些复杂推理可能耗时较长（尤其是 Opus + extended thinking）。`ChatAnthropic` 的默认 timeout 为 `None`（无限等待），生产环境应设置合理的值（如 120 秒）。

---

## 16.4 自测题

**Q1（简答）**：LangChain 的 `ChatAnthropic` 与原生 `anthropic` SDK 在处理 Tool Use 时有三个关键差异。请列出并简要说明。

**Q2（简答）**：LangGraph 的 `interrupt()` 和 `breakpoints` 有什么区别？分别适用于什么场景？

**Q3（简答）**：在生产环境中使用 LangChain + Anthropic Claude 时，至少需要配置哪三个关键参数来保证稳定性和可恢复性？说明每个参数的作用。

**Q4（编程）**：使用 LangGraph 实现一个完整的 Tool-Use Agent。要求：
- 状态为 `AgentState`（包含 `messages` 字段）
- 至少绑定两个工具（例如计算器 `calculator` 和搜索 `search` ）
- 使用 `SqliteSaver` 作为 checkpointer
- 在工具调用前设置 `interrupt_before="tools"` 实现 HITL
- 编写测试验证：模型可以选择正确的工具、人类可以批准或拒绝工具调用

参考答案位于 `code/python/ch16/` 和 `code/node/ch16/`。

---

## 16.5 代码实现

完整实现位于以下文件：

| 文件 | 内容 |
|------|------|
| `code/python/ch16/langchain_integration.py` | ChatAnthropic、Tool binding、Prompt templates、Memory |
| `code/python/ch16/langgraph_agent.py` | StateGraph Agent + Checkpointer + HITL |
| `code/python/ch16/test_langchain.py` | 完整 pytest 测试 |
| `code/node/ch16/LangChainIntegration.ts` | TypeScript ChatAnthropic 集成 |
| `code/node/ch16/LangGraphAgent.ts` | TypeScript StateGraph Agent |
| `code/node/ch16/langchain.test.ts` | 完整 vitest 测试 |

---

> **版本提示**：本章涉及的 LangChain 生态包的 API 仍在演进中。对于生产使用，请查阅 [LangChain 官方文档](https://docs.langchain.com) 和 [LangGraph 文档](https://langchain-ai.github.io/langgraph/) 获取最新 API 参考。
