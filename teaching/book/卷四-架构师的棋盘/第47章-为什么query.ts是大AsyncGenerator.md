# 第 47 章：为什么 query.ts 是大 AsyncGenerator

> 源码验证日期：2026-05-15，基于 commit `0d81bb6`

你在第 46 章看到上下文压缩如何用三层防线对抗有限窗口。但有一个更基本的问题我们从未触碰：**承载这一切的核心循环，为什么是一个 ~1500 行的 `async function*`？**

打开 `src/query.ts`，你会看到一个叫 `queryLoop` 的函数。它包含一个 `while(true)` 循环，在循环里处理 API 调用、工具执行、上下文管理、错误恢复——几乎整个 Agentic Loop 都在它的函数体里。`query()` 函数只有一行核心逻辑：`yield* queryLoop(...)`，把控制权委托给这个巨型循环。

这不是一个偶然。这是一个深思熟虑的设计选择。函数体巨大，但控制流出奇地清晰。AsyncGenerator 的 `yield` 让每一步都可以暂停和恢复，而 `while(true)` 让循环永不停歇直到任务完成。

这一章讨论这个选择背后的权衡。

---

## 本章路线图

```mermaid
graph LR
    CH41["第41章<br/>为什么是TypeScript"] --> CH42["第42章<br/>为什么是React/Ink"]
    CH42["第42章<br/>为什么是React/Ink"] --> CH43["第43章<br/>为什么用Zod"]
    CH43["第43章<br/>为什么用Zod"] --> CH44["第44章<br/>工具系统的演进"]
    CH44["第44章<br/>工具系统的演进"] --> CH45["第45章<br/>安全与便利"]
    CH45["第45章<br/>安全与便利"] --> CH46["第46章<br/>有限窗口"]
    CH46["第46章<br/>有限窗口"] --> CH47["第47章<br/>大AsyncGenerator"]
    CH47["第47章<br/>大AsyncGenerator"] --> CH48["第48章<br/>Agent架构"]
    CH48["第48章<br/>Agent架构"] --> CH49["第49章<br/>开放协议"]
    CH49["第49章<br/>开放协议"] --> CH50["第50章<br/>性能的故事"]
    CH50["第50章<br/>性能的故事"] --> CH51["第51章<br/>纵深防御"]
    CH51["第51章<br/>纵深防御"] --> CH52["第52章<br/>稳定、历史与未来"]

    style CH41 fill:#e0e0e0,stroke:#999
    style CH42 fill:#e0e0e0,stroke:#999
    style CH43 fill:#e0e0e0,stroke:#999
    style CH44 fill:#e0e0e0,stroke:#999
    style CH45 fill:#e0e0e0,stroke:#999
    style CH46 fill:#e0e0e0,stroke:#999
    style CH47 fill:#4a90d9,stroke:#2c5f8a,color:#fff,stroke-width:3px
    style CH48 fill:#e0e0e0,stroke:#999
    style CH49 fill:#e0e0e0,stroke:#999
    style CH50 fill:#e0e0e0,stroke:#999
    style CH51 fill:#e0e0e0,stroke:#999
    style CH52 fill:#e0e0e0,stroke:#999
```

---

## 现状：一个 AsyncGenerator 的全貌

### queryLoop 的骨架

`queryLoop()` 是 Claude Code 的心脏。它的核心结构可以简化为：

```typescript
async function* queryLoop(params: QueryLoopParams): AsyncGenerator<Message> {
  while (true) {
    // 1. 构建请求
    const request = buildRequest(context)

    // 2. 调用 API（流式）
    for await (const event of callModelStream(request)) {
      yield event  // 每个 token、每个工具调用都 yield 出去
    }

    // 3. 如果有工具调用，执行工具
    if (hasToolCalls(response)) {
      const results = await executeTools(toolCalls)
      continue  // 回到 while(true) 顶部，开始下一轮
    }

    // 4. 没有工具调用，对话结束
    return
  }
}
```

这个骨架看起来简单，但 ~1500 行的函数体里塞满了细节：上下文检查、压缩触发、权限处理、错误恢复、流式进度反馈、中断处理……每一样都是必须的。

`query()` 函数本身几乎是一个空壳：

```typescript
export async function* query(params: QueryParams): AsyncGenerator<Message> {
  // ... 初始化 ...
  yield* queryLoop({ ...params, deps })
}
```

`yield*` 是 AsyncGenerator 的委托语法——它把 `queryLoop` 产生的每一个值都转发给 `query` 的调用者。调用者不需要知道内部有一个 `queryLoop`，它只知道 `query()` 是一个 AsyncGenerator。

### 为什么不用状态机

状态机是最常见的替代方案。把循环的每个阶段定义为一个状态，用 transition 函数驱动状态变化：

```typescript
// 被否决的方案
type State = 'idle' | 'calling_api' | 'executing_tools' | 'recovering'

class QueryStateMachine {
  private state: State = 'idle'
  private transitions: Map<State, () => State>

  tick() {
    this.state = this.transitions.get(this.state)()
  }
}
```

状态机有三个致命问题。

第一，**状态之间的数据传递需要额外管理**。每次状态切换时，你需要把当前状态的所有数据打包进一个 context 对象，传给下一个状态。在 AsyncGenerator 里，所有数据都在闭包中——函数本身就是状态的容器。

第二，**`yield` 天然解决了"暂停与恢复"**。AsyncGenerator 每次 `yield` 就暂停，消费者调用 `next()` 就恢复。状态机需要手动实现暂停点——你要自己决定什么时候暂停、暂停时保存什么、恢复时读取什么。

第三，**代码可读性差**。控制流分散在多个 transition 函数中。要理解整个循环的逻辑，你需要在多个函数之间跳转。而 `while(true)` 把所有逻辑放在一个地方——你往下滚动就能看到完整的流程。

### 为什么不用消息传递 / Actor 模型

Actor 模型是另一种常见的并发范式。每个组件是一个 actor，通过消息通信：

```typescript
// 被否决的方案
const actor = spawn(async (receive) => {
  while (true) {
    const msg = await receive()
    if (msg.type === 'api_response') { /* ... */ }
    if (msg.type === 'tool_result') { /* ... */ }
  }
})
```

Agentic loop 的核心流程是线性的：调用 API -> 处理响应 -> 执行工具 -> 回到顶部。Actor 模型增加了一层抽象，但没有解决任何实际问题。它更适合真正并发的场景——多个 agent 同时运行、多个工具并行执行。但对于一个线性的主循环，Actor 模型只是增加了复杂性。

### 为什么不用 Promise 链

```typescript
// 被否决的方案
function query(params) {
  return callApi(params)
    .then(response => processResponse(response))
    .then(result => executeTools(result))
    .then(toolResults => query({ ...params, toolResults }))
}
```

Promise 链最致命的问题是：**无法 yield 中间结果**。AI 的回答是流式的——一个字一个字地出来。用户需要看到每个字出现的过程，而不是等十秒后看到一段完整的文本。Promise 链是"等全部完成再继续"的语义，而 AsyncGenerator 的 `yield` 是"有结果就发出去"的语义。

---

## Prompt Cache 经济学如何塑造了核心循环

核心循环的设计不只是关于控制流的选择。它深受 Prompt Cache 经济学的影响。

### 静态区在前，动态区在后

`queryLoop` 在构建 API 请求时，系统提示的静态区（7 个 section）总是放在最前面。这些 section 几乎不变，因此几乎每次都能命中缓存。

动态区——CLAUDE.md、MCP 工具指令、对话历史——放在静态区之后。它们可能每轮都变化，但因为位置在后面，变化不会影响静态区的缓存命中。

```
缓存结构：
[静态区：系统提示 7 section] ← 缓存命中（90%+ 时间）
[动态区：CLAUDE.md]          ← 可能 miss
[动态区：MCP 指令]           ← 可能 miss
[对话历史]                   ← 压缩后 miss
[用户消息]                   ← 总是新内容
```

### 工具列表的排序一致性

`assembleToolPool()` 按名称排序所有工具。这不是为了美观——它是为了缓存。如果工具的顺序每轮都变化，前缀就变了，缓存就失效了。按名称排序保证了顺序的确定性。

### Slot Reservation 的经济账

工具定义在系统提示中占据 "slot"。初始分配 8K token 的空间，如果工具定义超过 8K，动态升级到 64K。这个设计的经济账是：大多数情况下，内置工具只占 ~6K，8K 的 slot 就够了。只有在连接了大量 MCP 服务器时才需要升级。

```
8K slot → 覆盖 99% 场景 → 省 56K token/请求
升级到 64K → 覆盖剩余 1% → 额外成本可控
```

整个核心循环的设计，从请求构建到消息排序，都在追求缓存命中率最大化。

---

## 后果分析

### 好处

**控制流直观。** `while(true) { ... yield ... continue ... return }`——一眼看出循环逻辑。不需要理解状态机的 transition 表、Actor 的消息协议、Promise 链的嵌套。控制流是线性的、可预测的。

**流式输出天然支持。** `yield message` 让 UI 在每个事件到达时就渲染。不需要额外的回调、事件发射器、或轮询机制。AsyncGenerator 的消费端用 `for await...of` 就能拿到每个事件。

**上下文管理简单。** 所有状态在闭包中——不需要显式的 context 对象传递。变量在函数作用域内自然可见，不需要跨状态传递。

**错误恢复集中。** `queryLoop` 的三阶段恢复逻辑（重试 API 调用 -> 重新渲染系统提示 -> 创建新对话）在同一个函数中。你不需要在多个状态之间协调恢复逻辑。

**依赖注入让测试可行。** `deps` 参数让测试可以注入 mock 的 API 调用、工具执行、权限检查——不需要复杂的测试框架。

### 麻烦

**函数体巨大。** ~1500 行的单一函数是客观事实。阅读需要大量滚动，理解需要记住函数顶部的变量定义。

**难以单元测试。** 测试一个 AsyncGenerator 需要模拟整个消费过程——`next()` 调用序列、`yield` 值验证、错误处理路径覆盖。这比测试一个纯函数复杂得多。

**`try/catch` 和 `yield` 的交互微妙。** 在 AsyncGenerator 中，`yield` 出现在 `try` 块内时，JavaScript 运行时会保持 `try` 块活跃直到 `next()` 被再次调用。如果消费者在 `next()` 调用之间抛出错误，这个错误会传播回 `yield` 点。这种行为不是所有开发者都熟悉的。

**print.ts 更极端。** 如果你觉得 1500 行已经很多了，`print.ts` 有 5,594 行，其中单函数 3,167 行，嵌套 12 层。生产代码不是教科书——它反映了真实的工程压力。

---

## 横向对比

| 工具 | 核心循环设计 | 流式支持 | 特点 |
|------|------------|---------|------|
| **Claude Code** | 单函数 AsyncGenerator | 天然 yield | 直观、流式天然支持 |
| **LangChain** | 状态机 + 回调 | 回调函数 | 灵活但复杂 |
| **AutoGPT** | while 循环 + 函数调用 | 无 yield | 类似但无暂停点 |
| **CrewAI** | Actor 模型 | 消息传递 | 多代理协作 |

LangChain 的状态机模型更灵活——你可以定义任意的状态转换图，支持分支和并行。但 Claude Code 的 Agentic Loop 本质上是线性的：API -> 工具 -> API -> 工具 -> 结束。线性流程用状态机表达是杀鸡用牛刀。

CrewAI 的 Actor 模型适合多代理场景——多个 agent 同时运行、互相通信。但 Claude Code 的主循环是单 agent 的，Actor 模型的通信开销在这里没有收益。

---

## 如果重新设计

### 拆分为子 Generator

1500 行不需要全在一个函数里。可以把循环体内的不同阶段拆分为独立的子 Generator：

```typescript
async function* queryLoop(params) {
  while (true) {
    const response = yield* handleApiCall(params)
    if (hasToolCalls(response)) {
      yield* handleToolExecution(toolCalls)
      continue
    }
    return
  }
}
```

`yield*` 委托让子 Generator 的事件可以透明地传递给外层。每个子 Generator 可以独立测试，也更容易理解。这个重构不需要改变外部接口——`query()` 的调用者不会注意到变化。

### 引入结构化的消息类型

当前 `yield` 出去的消息类型是松散的。一个更严格的设计是定义一个 discriminated union：

```typescript
type QueryEvent =
  | { type: 'api_start' }
  | { type: 'api_token', text: string }
  | { type: 'tool_start', name: string }
  | { type: 'tool_result', output: string }
  | { type: 'loop_end' }
```

这让消费端可以用 exhaustive check 确保每种事件都被处理。当前的实现更松散——有些事件是字符串，有些是对象，消费端需要做类型检查。

### 用更小的模型做循环控制

当前循环的每一步都使用同一个大模型。但有些步骤不需要大模型的创造力——比如判断是否需要压缩、决定是否继续循环。这些决策可以用一个更小、更快的模型来完成，降低延迟和成本。

---

## 试试看

### 练习一：追踪 yield 的消费者

在 `query.ts` 中找到 `queryLoop` 的 `yield` 语句，然后在 `print.ts` 或其他消费端找到 `for await...of` 循环。追踪一个 yield 出去的消息经过了哪些处理步骤才到达终端渲染。

### 练习二：添加一个新的事件类型

在 `queryLoop` 中添加一个新的 yield 点——比如在每次 API 调用开始时 yield 一个 `{ type: 'api_call_start', timestamp: Date.now() }` 事件。然后在消费端处理这个事件，显示一个时间戳。

### 练习三：对比 print.ts 的复杂度

打开 `print.ts`，找到那个 3,167 行的单函数。对比 `queryLoop` 的 1500 行——哪一个更难理解？为什么？思考什么样的重构可以让这两个函数都更可读。

---

## 检查点

- **核心循环是 `async function* queryLoop()`**：~1500 行，包含 `while(true)` 循环
- **被否决的方案**：状态机（数据传递复杂）、Actor 模型（不必要的抽象）、Promise 链（无法 yield）
- **AsyncGenerator 的优势**：控制流直观、流式天然支持、闭包保存状态、依赖注入便于测试
- **Prompt Cache 塑造了循环**：静态区在前、工具按名称排序、Slot Reservation 经济账
- **代价**：函数体巨大、难以单元测试、`yield` 与 `try/catch` 交互微妙
- **横向对比**：比 LangChain 简单、比 AutoGPT 可暂停、比 CrewAI 直接

---

> **导航**
>
> 上一章：[第 46 章：有限窗口的智慧](./第46章-有限窗口的智慧.md)
>
> 下一章：[第 48 章：Agent 架构的取舍](./第48章-Agent架构的取舍.md)
