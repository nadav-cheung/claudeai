# 第 34 章：为什么工具执行是流式的

> 源码验证日期：2026-05-15，基于 commit `0d81bb6`

---

## 决策回顾

Claude Code 的工具执行不是"等模型说完再执行"——而是**预测性工具执行（Speculative Execution）**。模型仍在流式输出时，只读工具就已经开始执行。

源码证据：
- `src/services/tools/StreamingToolExecutor.ts`——~517 行的流式工具执行器
- `StreamingToolExecutor.ts:76`——`addTool()` 在收到 `tool_use` block 时立即添加并尝试执行
- `StreamingToolExecutor.ts:129`——`canExecuteTool()` 并发分区算法
- `src/query.ts:838-845`——模型流式输出期间就开始执行工具

---

## 被否方案

### 方案 A：等模型说完再执行

```typescript
// 被 否 决 的 方 案
// 等模型完整回复后，收集所有 tool_use blocks
const response = await callModel(params)
const toolBlocks = response.content.filter(c => c.type === 'tool_use')

// 然后执行所有工具
for (const block of toolBlocks) {
  await executeTool(block)
}
```

**问题**：
- 模型输出 3 个工具调用需要 5-10 秒——等待期间用户看到空白
- 只读工具（Read、Grep）之间没有依赖——完全可以并行
- 总延迟 = 模型输出时间 + 工具执行时间（串行叠加）

### 方案 B：全部并行执行

```typescript
// 被 否 决 的 方 案
await Promise.all(toolBlocks.map(block => executeTool(block)))
```

**问题**：写操作（Write、Bash `npm install`）并行执行可能导致竞态条件。

### 方案 C：两阶段执行

```typescript
// 被 否 决 的 方 案
// 第一阶段：所有工具并行收集输入
// 第二阶段：所有工具并行执行
```

**问题**：增加了不必要的延迟和复杂度。

---

## 后果分析

### 好处

1. **延迟降低**：模型输出时间 + 只读工具执行时间重叠——用户等待时间显著减少
2. **进度反馈**：工具执行过程中实时显示进度（Bash 命令的实时输出）
3. **并发安全**：`isConcurrencySafe` 分区算法保证写操作串行
4. **兄弟错误级联**：Bash 失败取消并行兄弟——避免无用工作

### 实际性能提升

```
模型同时输出 3 个工具调用：Read("a.ts"), Grep("pattern"), Write("b.ts")

串行执行（方案 A）：
  模型输出: 5s
  Read:     0.1s
  Grep:     0.2s
  Write:    0.1s
  总计:     5.4s

流式执行（实际）：
  模型输出: 5s（Read 和 Grep 在 2s 时就开始执行）
  Read:     0.1s（在模型第 2-2.1s 完成）
  Grep:     0.2s（在模型第 2.5-2.7s 完成）
  Write:    0.1s（等模型说完后独占执行）
  总计:     5.1s（省 0.3s）
```

### 麻烦

1. **复杂度增加**：`StreamingToolExecutor` 需要管理队列、并发控制、进度回调
2. **取消逻辑**：用户中断时需要取消正在执行的并行工具
3. **结果排序**：工具完成顺序不确定——需要正确合并到消息列表

---

## 横向对比

| 工具 | 工具执行策略 | 特点 |
|------|------------|------|
| **Claude Code** | 预测性流式执行 + 并发分区 | 最快，最复杂 |
| **Aider** | 串行执行 | 简单，慢 |
| **Cursor** | 串行执行 + 缓存 | 简单，有缓存优化 |
| **AutoGPT** | 串行执行 | 最简单 |

---

## 你的判断

1. 预测性执行的延迟节省是否值得增加的复杂度？在什么场景下节省最显著？
2. `isConcurrencySafe` 的手动标记是否可能出错？有没有自动检测的方法？
3. 兄弟错误级联只针对 Bash——是否应该扩展到其他工具？

---

**设计原则标签**：可靠执行——graceful recovery + context as scarce resource。流式执行减少了总延迟，并发分区保证了安全性。
