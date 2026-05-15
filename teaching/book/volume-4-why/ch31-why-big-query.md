# 第 31 章：为什么 query.ts 是一个大 AsyncGenerator

> 源码验证日期：2026-05-15，基于 commit `0d81bb6`

---

## 决策回顾

Claude Code 的核心循环是一个 ~1700 行的 `async function* queryLoop()`，包含一个 `while(true)` 循环。它不是状态机，不是事件驱动，不是消息传递——就是一个巨大的 AsyncGenerator 函数。

源码证据：
- `src/query.ts:241`——`queryLoop()` 函数开始
- `src/query.ts:219`——`query()` 用 `yield*` 委托给 `queryLoop()`
- 整个 agentic loop（上下文管理、API 调用、工具执行、错误恢复）在一个函数中

---

## 被否方案

### 方案 A：状态机

```typescript
// 被 否 决 的 方 案
type State = 'idle' | 'calling_api' | 'executing_tools' | 'recovering'

class QueryStateMachine {
  private state: State = 'idle'
  private transitions: Map<State, () => State>

  tick() {
    this.state = this.transitions.get(this.state)()
  }
}
```

**问题**：
- 状态之间的数据传递需要额外管理（context 对象）
- AsyncGenerator 的 `yield` 天然解决了"暂停→恢复"——状态机需要手动实现
- 代码可读性差——控制流分散在多个 transition 函数中

### 方案 B：消息传递 / Actor 模型

```typescript
// 被 否 决 的 方 案
const actor = spawn(async (receive) => {
  while (true) {
    const msg = await receive()
    if (msg.type === 'api_response') { /* ... */ }
    if (msg.type === 'tool_result') { /* ... */ }
  }
})
```

**问题**：增加了一层抽象但没有解决实际问题——Agentic Loop 的核心是线性的（API 调用 → 工具执行 → 下一轮），不是并发的。

### 方案 C：回调 / Promise 链

```typescript
// 被 否 决 的 方 案
function query(params) {
  return callApi(params)
    .then(response => processResponse(response))
    .then(result => executeTools(result))
    .then(toolResults => query({ ...params, toolResults }))
}
```

**问题**：无法 `yield` 中间结果——UI 无法流式更新。

---

## 后果分析

### 好处

1. **控制流直观**：`while(true) { ... yield ... continue ... return }`——一眼看出循环逻辑
2. **流式输出天然支持**：`yield message` 让 UI 在每个事件到达时就渲染
3. **上下文管理简单**：所有状态在闭包中——不需要显式传递
4. **错误恢复集中**：三阶段恢复逻辑在同一函数中——容易理解全貌
5. **依赖注入**：`deps` 参数让测试可以注入 mock——不需要复杂框架

### 麻烦

1. **函数体巨大**：~1700 行的单一函数——阅读需要大量滚动
2. **难以单元测试**：需要模拟整个 AsyncGenerator 消费过程
3. **错误处理复杂**：`try/catch` 和 `yield*` 的交互微妙
4. **`print.ts` 更极端**：5,594 行/单函数 3,167 行/12 层嵌套——生产代码不是完美的

---

## Prompt Cache 经济学如何塑造了核心循环

核心循环的设计受 Prompt Cache 经济学深刻影响：

1. **静态区在前**：system prompt 的静态区（7 个 section）几乎不变 → 稳定命中缓存
2. **动态区在后**：CLAUDE.md、MCP 指令等每轮可能变化 → 放在缓存边界之后
3. **工具列表排序**：`assembleToolPool()` 按名称排序 → 保证顺序一致 → 缓存稳定
4. **Slot Reservation**：8K → 64K 按需升级 → 省 99% 请求上下文

```
缓存命中 → 省 90% 输入成本
整个核心循环的设计都在追求缓存命中率最大化
```

---

## 横向对比

| 工具 | 核心循环设计 | 特点 |
|------|------------|------|
| **Claude Code** | 单函数 AsyncGenerator | 直观、流式天然支持 |
| **LangChain** | 状态机 + 回调 | 灵活但复杂 |
| **AutoGPT** | while 循环 + 函数调用 | 类似但无 yield |
| **CrewAI** | Actor 模型 | 多代理协作 |

---

## 你的判断

1. 1700 行的单函数是否应该拆分？拆分成什么结构？
2. AsyncGenerator 模式在其他语言（Python、Rust）中是否有等价物？
3. 如果 Prompt Cache 不存在，核心循环的设计会怎样不同？

---

**设计原则标签**：可靠执行——context as scarce resource + graceful recovery。单函数 AsyncGenerator 把上下文管理、错误恢复、流式输出统一在一个控制流中。
