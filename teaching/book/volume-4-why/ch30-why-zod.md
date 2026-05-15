# 第 30 章：为什么用 Zod 验证工具输入

> 源码验证日期：2026-05-15，基于 commit `0d81bb6`

---

## 决策回顾

Claude Code 用 **Zod** 定义所有工具的输入参数 schema。不是手写 JSON Schema，不是手动验证，而是一行 `inputSchema.safeParse(input)` 同时获得类型推导、运行时验证和 JSON Schema 生成。

源码证据：
- `src/Tool.ts:362`——`Tool` 类型的 `inputSchema` 字段
- `src/tools/BashTool/BashTool.tsx:227`——`lazySchema(() => z.strictObject({...}))`
- 每个工具都用 `lazySchema + z.strictObject` 模式

三个关键能力的统一：
1. **类型推导**：`z.infer<typeof schema>` 自动生成 TypeScript 类型
2. **运行时验证**：`safeParse()` 在工具执行前验证输入
3. **JSON Schema 生成**：Zod schema 转换为 Anthropic API 要求的工具参数格式

---

## 被否方案

### 方案 A：手写 JSON Schema

```typescript
// 被 否 决 的 方 案
const inputSchema = {
  type: 'object',
  properties: {
    command: { type: 'string', description: 'The command to execute' },
    timeout: { type: 'number', description: 'Optional timeout' },
  },
  required: ['command'],
}

// 问题 1：没有类型推导——需要手写 TypeScript 类型
type Input = { command: string; timeout?: number }  // 重复定义
// 问题 2：运行时验证需要手动实现
// 问题 3：描述字符串需要手动管理
```

**问题**：类型和 schema 分离——修改一处容易忘记修改另一处。

### 方案 B：不验证（信任模型输出）

```typescript
// 被 否 决 的 方 案
async call(args: any) {
  // 直接使用 args，不验证
  const result = await exec(args.command)
}
```

**问题**：模型可能生成无效输入（缺少必填字段、错误类型），导致运行时错误。

### 方案 C：io-ts / tRPC / 其他验证库

```typescript
// 被 否 决 的 方 案
import * as t from 'io-ts'
const InputType = t.type({ command: t.string, timeout: t.union([t.number, t.undefined]) })
```

**问题**：io-ts 的 API 不如 Zod 直观，JSON Schema 生成需要额外库。

---

## 后果分析

### 好处

1. **单一来源**：Zod schema 是类型、验证、API 定义的唯一来源——修改一处自动同步
2. **编译时安全**：`satisfies ToolDef<InputSchema, Output>` 确保工具实现匹配 schema
3. **友好的错误消息**：`safeParse()` 返回结构化错误，比手动检查信息更丰富
4. **JSON Schema 自动生成**：Zod → JSON Schema 转换直接用于 Anthropic API 的 `tools` 参数
5. **`.describe()` 方法**：每个字段自带描述——模型看到工具文档

### 麻烦

1. **Zod 版本锁定**：Claude Code 用 Zod v4——生态不如 v3 成熟
2. **`lazySchema` 模式**：所有工具都需要三行的延迟包装——模板代码
3. **MCP 工具的例外**：MCP 工具用 `inputJSONSchema`（原始 JSON Schema），绕过了 Zod
4. **`strictObject` 的严格性**：不允许额外字段——有时过于限制

---

## 横向对比

| 工具 | 输入验证方案 | 特点 |
|------|------------|------|
| **Claude Code** | Zod v4 + lazySchema | 类型推导 + 验证 + JSON Schema 三合一 |
| **LangChain** | Pydantic（Python） | 类似理念，Python 生态的 Zod |
| **OpenAI Function Calling** | 手写 JSON Schema | 无类型推导，无运行时验证 |
| **AutoGPT** | 无验证 | 信任模型输出，运行时错误多 |

---

## 你的判断

1. `lazySchema` 的三行模板代码是否可以消除？Bun 的 `import type` 能否替代？
2. MCP 工具绕过 Zod 是否是个设计缺陷？MCP 协议应该支持 Zod schema 吗？
3. 如果未来 Zod v4 的 JSON Schema 生成有 bug，回退到 v3 的成本有多大？

---

**设计原则标签**：可靠执行——graceful recovery。Zod 验证在工具执行前捕获无效输入，防止运行时错误传播到更深的层级。
