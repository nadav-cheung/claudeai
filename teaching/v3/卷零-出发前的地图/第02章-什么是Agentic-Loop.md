# 第 02 章：什么是 Agentic Loop

> 源码验证日期：2026-05-15，基于 commit `0d81bb6`

你刚刚看到了：你输入一句话，AI 回复你。但在这背后，AI 不只是"想了一下就回答"——它可能想了好多轮，每一轮都在读文件、跑命令、检查结果。这个"不断思考→行动→检查→再思考"的过程，就是 Agentic Loop。

---

## 路线图

```mermaid
graph LR
    CH01["第 1 章<br/>你和AI的第一次对话"] --> CH02["📖 第 2 章<br/>什么是 Agentic Loop"]
    CH02 --> V1["卷一：消息的旅程"]

    style CH01 fill:#e1f5fe,stroke:#333
    style CH02 fill:#4CAF50,color:#fff,stroke:#333
    style V1 fill:#f5f5f5,stroke:#999
```

---

## 生活类比：餐厅后厨

想象一家餐厅：

- **服务员**接到顾客的点单，转告给厨师
- **厨师**（AI 模型）看完菜单，决定需要什么食材和工具
- 如果发现缺盐，厨师不会猜——他会打开储物柜（**工具：Read**）确认
- 发现盐罐是空的，厨师让采购员去超市买（**工具：Bash**）
- 买回来后，厨师继续做菜
- 菜做好后，厨师尝一口（**工具：Bash(npm test)**）——太咸了，再调一下
- 最终端上桌

Agentic Loop（代理循环）就是这个流程：**厨师不断思考→行动→检查→再思考**，直到菜做好。

这个过程有两个关键特征：
1. **厨师不是一步到位的**——他可能需要好几轮"发现缺东西→去拿→继续做"的循环
2. **每一轮的行动取决于上一轮的结果**——尝了一口才知道太咸，太咸了才知道要加水

---

## 核心概念：LLM + 工具 + 循环

```mermaid
graph TD
    START["用户输入"] --> THINK["模型思考<br/>需要做什么"]
    THINK --> DECIDE{"需要用工具吗？"}
    DECIDE -->|"是"| TOOL["调用工具<br/>（Read/Bash/Edit...）"]
    TOOL --> RESULT["拿到工具结果"]
    RESULT --> THINK
    DECIDE -->|"否，任务完成"| END["返回最终回复"]

    style START fill:#e1f5fe
    style THINK fill:#fff3e0
    style TOOL fill:#e8f5e9
    style END fill:#f3e5f5
```

三要素：

| 要素 | 角色 | Claude Code 对应 |
|------|------|-----------------|
| **LLM（大语言模型）** | "大脑"——理解指令、决定下一步 | `src/services/api/claude.ts` → Anthropic API |
| **工具（Tools）** | "手脚"——读文件、跑命令、改代码 | `src/Tool.ts`（接口）+ `src/tools/`（实现） |
| **循环（Loop）** | 把"想"和"做"串起来 | `src/query.ts`（`queryLoop()` 函数） |

没有 LLM：有手脚没大脑，不知道做什么。
没有工具：有大脑没手脚，只会说不会做。
没有循环：做一步就停，无法完成多步任务。

---

## 源码中的 Agentic Loop

让我们看看 Claude Code 源码中 Agentic Loop 的入口。这个函数叫 `query()`：

```typescript
// → src/query.ts（简化版）
export async function* query(
  params: QueryParams,
): AsyncGenerator<StreamEvent | Message, Terminal> {
  const terminal = yield* queryLoop(params, consumedCommandUuids)
  return terminal
}
```

两个关键点：

1. **`async function*`**——这是 TypeScript 的 **AsyncGenerator（异步生成器）**。它不是一次性返回结果，而是通过 `yield` 一点点地把中间结果"流"出来。这就是为什么你能在终端看到 Claude 的回复逐字出现。

2. **`queryLoop()`**——真正的循环逻辑在这里面。每一轮循环做的事情就是：发 API 请求 → 拿回复 → 如果有工具调用就执行 → 把结果加到对话中 → 再发 API 请求。

### 循环内部的状态

`queryLoop()` 内部维护了一个 `State` 对象：

```typescript
// → src/query.ts（简化版）
let state: State = {
  messages: params.messages,            // 对话历史
  toolUseContext: params.toolUseContext, // 工具使用上下文
  maxOutputTokensOverride: ...,         // 输出 token 上限
  turnCount: 1,                         // 当前轮次
  // ...
}
```

每一轮循环结束，这个状态被更新，然后传入下一轮。这就像厨师一边做菜一边在笔记本上记录进度。

> **设计一瞥**：为什么要用 `async function*`（AsyncGenerator）而不是普通函数？因为 Claude Code 需要**流式输出**。模型回复是逐字到达的，工具执行是异步的。AsyncGenerator 让 UI 层可以在每收到一个中间结果时就立刻显示，而不是等整个循环结束。

---

## 七大组件

Claude Code 由七个主要组件组成，它们像齿轮一样咬合在一起：

```mermaid
graph LR
    subgraph "Claude Code 七大组件"
        E["① 入口<br/>cli.tsx / main.tsx"]
        I["② 消息<br/>processUserInput"]
        Q["③ 查询引擎<br/>query.ts / QueryEngine"]
        P["④ 权限<br/>permissions"]
        T["⑤ 工具执行<br/>StreamingToolExecutor"]
        R["⑥ 渲染<br/>Ink 组件树"]
        S["⑦ 状态与持久化<br/>AppState / sessionStorage"]
    end

    E --> I --> Q
    Q --> P --> T
    T --> Q
    Q --> R
    Q --> S

    style E fill:#e1f5fe
    style I fill:#e8f5e9
    style Q fill:#fff3e0
    style P fill:#fce4ec
    style T fill:#f3e5f5
    style R fill:#e0f2f1
    style S fill:#fff8e1
```

| # | 组件 | 文件 | 做什么 |
|---|------|------|--------|
| ① | 入口 | `cli.tsx` → `main.tsx` | 解析命令行参数，初始化所有模块 |
| ② | 消息 | `processUserInput/` | 捕获用户输入，创建消息对象 |
| ③ | 查询引擎 | `query.ts` + `QueryEngine.ts` | Agentic Loop 的核心 |
| ④ | 权限 | `permissions/` | 检查工具调用是否被允许 |
| ⑤ | 工具执行 | `StreamingToolExecutor.ts` | 执行工具（并发安全、Hook 触发） |
| ⑥ | 渲染 | `ink/` + `components/` | 用 React（Ink）渲染终端输出 |
| ⑦ | 状态与持久化 | `AppStateStore.ts` + `sessionStorage.ts` | 管理会话状态，保存对话 |

### 一次完整的交互

```mermaid
sequenceDiagram
    participant U as 用户
    participant I as ② 消息
    participant Q as ③ 查询引擎
    participant P as ④ 权限
    participant T as ⑤ 工具执行
    participant R as ⑥ 渲染
    participant S as ⑦ 状态

    U->>I: 打字："修复这个 bug"
    I->>Q: createUserMessage("修复这个 bug")
    Q->>Q: queryLoop 开始循环

    loop 每一轮
        Q->>Q: 发送 API 请求
        Q->>Q: 收到流式响应
        Q->>R: yield 中间结果
        alt 需要调用工具
            Q->>P: 检查权限
            P->>T: 权限通过，执行工具
            T->>Q: 返回工具结果
            Q->>S: 更新状态
        else 不需要工具
            Q->>R: 渲染最终回复
        end
    end

    R->>U: 显示完整回复
```

---

## 工具注册：所有工具从哪来

Claude Code 启动时，会把所有可用工具收集到一个列表里：

```typescript
// → src/tools.ts（简化版）
export const getTools = (permissionContext: ToolPermissionContext): Tools => {
  const tools = getAllBaseTools()
    .filter(tool => !specialTools.has(tool.name))
  // ... 加上 MCP 工具、自定义工具等
  return tools
}
```

每个工具都遵循统一的 `Tool` 接口：

```typescript
// → src/Tool.ts（简化版）
interface Tool<Input, Output> {
  name: string                          // 工具名，如 "Bash"
  description: string                   // 描述（模型用来决定何时使用）
  inputSchema: Input                    // Zod schema（定义参数类型）
  isReadOnly(input): boolean            // 是否只读（影响并发策略）
  call(input): Promise<Output>          // 执行工具
}
```

`isReadOnly` 是一个巧妙的设计——只读工具（如 `Read`、`Grep`）可以并行执行，写操作（如 `Write`、`Bash`）必须串行。

---

## 扩展机制一览

除了内置工具，Claude Code 还提供四层扩展机制：

```mermaid
graph LR
    H["Hooks<br/>零成本"] --> SK["Skills<br/>低成本"]
    SK --> PL["Plugins<br/>中成本"]
    PL --> MCP["MCP<br/>高成本"]

    style H fill:#e8f5e9
    style SK fill:#fff3e0
    style PL fill:#e1f5fe
    style MCP fill:#f3e5f5
```

| 扩展 | 成本 | 做什么 | 例子 |
|------|------|--------|------|
| **Hooks** | 零 | 工具执行前后自动运行脚本 | 每次 Edit 后自动跑 lint |
| **Skills** | 低 | Markdown 提示模板 | `/deploy` 跑部署流程 |
| **Plugins** | 中 | 打包 Skills + Hooks 分发 | 团队共享开发配置 |
| **MCP** | 高 | 连接外部服务 | 让 Claude 查你的数据库 |

卷二会详细拆解每层扩展机制。

---

## 试试看：模拟一个最简 Agentic Loop

不需要 API key，用纯 Node.js 模拟核心循环：

```javascript
// minimal_loop.js — 最简 agentic loop 模拟
// 运行: node minimal_loop.js

const tools = {
  read_file: (path) => `文件内容: console.log("hello")`,
  run_command: (cmd) => `$ ${cmd}\n输出: 成功`,
};

function simulateBrain(messages) {
  const last = messages[messages.length - 1];

  if (last.role === "user") {
    return {
      role: "assistant",
      content: "让我先看看代码。",
      toolCalls: [{ name: "read_file", args: { path: "index.js" } }],
    };
  }

  if (last.role === "tool_result") {
    return {
      role: "assistant",
      content: "代码看起来没问题，跑一下测试。",
      toolCalls: [{ name: "run_command", args: { cmd: "node index.js" } }],
    };
  }

  return { role: "assistant", content: "测试通过！任务完成。" };
}

function agenticLoop(userInput) {
  console.log(`\n用户: ${userInput}\n`);
  const messages = [{ role: "user", content: userInput }];

  for (let turn = 1; turn <= 5; turn++) {
    console.log(`--- 第 ${turn} 轮 ---`);

    const response = simulateBrain(messages);
    messages.push(response);
    console.log(`  AI: ${response.content}`);

    if (!response.toolCalls?.length) {
      console.log("\n✓ 任务完成");
      return;
    }

    for (const call of response.toolCalls) {
      const result = tools[call.name](call.args.path || call.args.cmd);
      messages.push({ role: "tool_result", content: result });
      console.log(`  工具: ${call.name} → ${result}`);
    }
  }
}

agenticLoop("帮我检查 index.js 有没有问题");
```

运行：

```bash
node minimal_loop.js
```

预期输出：

```
用户: 帮我检查 index.js 有没有问题

--- 第 1 轮 ---
  AI: 让我先看看代码。
  工具: read_file → 文件内容: console.log("hello")
--- 第 2 轮 ---
  AI: 代码看起来没问题，跑一下测试。
  工具: run_command → $ node index.js
输出: 成功
--- 第 3 轮 ---
  AI: 测试通过！任务完成。

✓ 任务完成
```

这个简化版和 Claude Code 的真实 `queryLoop()` 做的是同一件事——只不过真实版本用真正的 AI 模型代替了 `simulateBrain`，用真正的文件系统代替了模拟工具。

> **关键洞察**：Claude Code 的核心就这么简单。复杂的不是循环本身，而是围绕循环构建的工具系统、权限系统、缓存优化、上下文管理等。这些就是后续 50 章要拆解的内容。

---

## 检查点

你现在理解了：

- **Agentic Loop 的三要素**：LLM（大脑）+ 工具（手脚）+ 循环（串联）
- **源码入口**：`src/query.ts` 的 `query()` 和 `queryLoop()`
- **七大组件**：入口→消息→查询引擎→权限→工具执行→渲染→状态
- **工具接口**：每个工具都有 `name`、`inputSchema`、`isReadOnly`、`call()`
- **四层扩展**：Hooks → Skills → Plugins → MCP（成本递增）

**下一站**：从卷一开始，我们将跟随一次 `query()` 调用，从用户按下 Enter 到收到完整回复，一站一站地读源码。第一站：准备工具箱。

---

[上一章：你和 AI 的第一次对话](./第01章-你和AI的第一次对话.md) | [下一卷：消息的旅程](../卷一-消息的旅程/第03章-准备工具箱.md)
