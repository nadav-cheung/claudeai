# 第 43 章：为什么用 Zod

> 源码验证日期：2026-05-15，基于 commit `0d81bb6`

前两章讨论了 TypeScript 和 React/Ink 的选择。这两个决定塑造了 Claude Code 的骨架。但骨架要运转，还需要一种机制来处理一个独特的挑战：**AI 返回的数据不可信**。

这不是夸张。AI 模型通过 JSON 格式返回工具调用参数，但这个 JSON 可能不符合你的期望——字段名错了、类型错了、结构嵌套错了、必填字段缺了。你需要一个强壮的校验层。

Claude Code 用 **Zod** 定义所有工具的输入参数 schema。不是手写 JSON Schema，不是手动验证，而是一行 `inputSchema.safeParse(input)` 同时获得类型推导、运行时验证和 JSON Schema 生成。

这一章讨论为什么是这个选择，以及它带来的连锁效应。

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
    style CH43 fill:#4a90d9,stroke:#2c5f8a,color:#fff,stroke-width:3px
    style CH44 fill:#e0e0e0,stroke:#999
    style CH45 fill:#e0e0e0,stroke:#999
    style CH46 fill:#e0e0e0,stroke:#999
    style CH47 fill:#e0e0e0,stroke:#999
    style CH48 fill:#e0e0e0,stroke:#999
    style CH49 fill:#e0e0e0,stroke:#999
    style CH50 fill:#e0e0e0,stroke:#999
    style CH51 fill:#e0e0e0,stroke:#999
    style CH52 fill:#e0e0e0,stroke:#999
```

---

## 现状：Zod 在 Claude Code 里的三重角色

### 角色一：类型推导——编译时的安全保障

打开任何一个工具的定义，你会看到一个统一的模式。以 BashTool 为例：

```typescript
const inputSchema = lazySchema(() => z.strictObject({
  command: z.string().describe('The command to execute'),
  timeout: z.number().optional().describe('Optional timeout in milliseconds'),
  description: z.string().optional().describe('Description of the command'),
}))
```

然后用 `z.infer` 从这个 schema 自动推导 TypeScript 类型：

```typescript
type InputSchema = ReturnType<typeof inputSchema>
```

这意味着 `tool.call()` 的第一个参数不是 `any`，不是 `Record<string, unknown>`，而是这个工具特有的、类型精确的输入。BashTool 的 `call` 方法知道它收到的是 `{ command: string; timeout?: number; description?: string }`，FileReadTool 的 `call` 方法知道它收到的是 `{ file_path: string; offset?: number; limit?: number }`。

在一个有 43 个工具目录的系统里，每个工具的输入格式都不同。如果手动定义类型和手动定义 schema，你需要维护两份定义，而且它们很容易不一致。`z.infer` 消除了这个风险——类型是从 schema 推导出来的，永远同步。

### 角色二：运行时校验——AI 数据的第一道防线

AI 模型通过 Anthropic API 返回工具调用参数。这些参数是 JSON，来自网络，没有编译器帮你检查。模型可能把 `timeout` 传成字符串 `"5000"` 而不是数字 `5000`，可能忘了传必填的 `command` 字段，可能传了根本不存在的字段。

`inputSchema.safeParse(input)` 在 AI 返回参数的第一时间校验。如果 AI 发了格式错误的数据，管线会返回一个精确的错误消息，告诉 AI 哪个字段错了、期望什么类型、实际收到什么。AI 下次可以修正。

```typescript
// safeParse 返回结构化的结果
const result = inputSchema.safeParse(rawInput)
if (!result.success) {
  // result.error 包含精确的错误信息
  return { error: formatZodError(result.error) }
}
```

这种"快速失败、精确反馈"的模式在 AI 编程助手里特别重要。AI 模型不是人类——它不会"感觉"参数不对，它需要明确的错误消息来修正行为。Zod 的错误格式足够精确，AI 可以据此调整。

### 角色三：JSON Schema 生成——与 API 的桥梁

Anthropic API 要求工具参数以 JSON Schema 格式定义。Zod schema 可以直接转换成 JSON Schema：

```typescript
// Zod schema -> JSON Schema -> 发送给 AI 模型
const jsonSchema = zodToJsonSchema(inputSchema)
```

这意味着 Zod schema 是工具输入定义的**单一真相来源**。API 发给模型的工具描述从它生成，管线运行时的校验用它执行，TypeScript 的类型从它推断。**一份定义，三种用途。**

### 惯例：lazySchema + z.strictObject

Claude Code 的工具定义里有一个反复出现的模式：

```typescript
const inputSchema = lazySchema(() => z.strictObject({ ... }))
type InputSchema = ReturnType<typeof inputSchema>

export const MyTool = buildTool({
  get inputSchema(): InputSchema { return inputSchema() },
  // ...
})
```

`lazySchema` 是一个三行的 memoizing 工厂函数：

```typescript
export function lazySchema<T>(factory: () => T): () => T {
  let cached: T | undefined
  return () => (cached ??= factory())
}
```

为什么需要延迟？三个原因：

1. Schema 依赖 feature flags、环境变量——在模块初始化时不可用
2. 未使用的工具（条件禁用）不付出 schema 构建成本
3. 避免循环依赖

`z.strictObject`（而不是 `z.object`）确保不允许额外字段。AI 模型有时会传多余的字段——`strictObject` 会拒绝它们，防止意外数据潜入系统。

---

## 当时还有什么选择

### 选择一：手写 JSON Schema

```typescript
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

**问题**：类型和 schema 分离——修改一处容易忘记修改另一处。在 43 个工具里，这种不同步迟早会导致 bug。

### 选择二：不验证（信任模型输出）

```typescript
async call(args: any) {
  const result = await exec(args.command)
}
```

**问题**：模型可能生成无效输入（缺少必填字段、错误类型），导致运行时错误在深层代码中爆炸，而不是在校验边界被拦截。

### 选择三：io-ts / tRPC / 其他验证库

```typescript
import * as t from 'io-ts'
const InputType = t.type({ command: t.string, timeout: t.union([t.number, t.undefined]) })
```

**问题**：io-ts 的 API 不如 Zod 直观，JSON Schema 生成需要额外库。Zod 在类型推导、运行时校验、JSON Schema 生成三个方面的整合度更高。

### 选择四：Pydantic（如果选了 Python）

Pydantic 是 Python 生态里 Zod 的等价物——同样提供类型推导和运行时校验。如果 Claude Code 用 Python，Pydantic 会是自然的选择。但既然选了 TypeScript（第 41 章），Pydactic 就不在选项里了。

---

## 为什么选了 Zod

### 理由一：单一来源原则

Zod schema 是类型、验证、API 定义的唯一来源。修改一处自动同步。在 43 个工具的代码库里，这种"单一来源"的保证不是奢侈品，而是防止不同步 bug 的唯一可靠方式。

### 理由二：`.describe()` 方法服务于 AI

每个字段自带描述——模型看到工具文档。这对于 AI 编程助手特别重要：AI 模型需要知道每个参数的语义，才能正确生成工具调用。

```typescript
command: z.string().describe('The bash command to execute')
```

这个 `describe` 不只是给人类看的注释——它被转换成 JSON Schema 的 `description` 字段，直接发送给 AI 模型，指导它如何使用这个工具。

### 理由三：友好的错误消息

`safeParse()` 返回结构化错误，比手动检查信息更丰富。Zod 的错误格式包含路径、期望类型、实际值——AI 模型可以据此精确修正。

### 理由四：`satisfies` 操作符的配合

Claude Code 用 TypeScript 的 `satisfies` 操作符配合 Zod，在定义点检查而不丢失字面量类型信息：

```typescript
export const GlobTool = buildTool({
  name: 'Glob',
  isConcurrencySafe: () => true,
  async call(args) { /* ... */ },
} satisfies ToolDef<InputSchema, Output>)
```

`satisfies ToolDef<InputSchema, Output>` 确保工具实现匹配 schema，编译时检查所有必填字段是否存在。这是一种"类型驱动的开发"——编译器在开发阶段就帮你发现遗漏。

---

## Zod 的代价

选择 Zod 不是没有后果的：

1. **Zod 版本锁定**：Claude Code 用 Zod v4——生态不如 v3 成熟
2. **`lazySchema` 的模板代码**：所有工具都需要三行的延迟包装
3. **MCP 工具的例外**：MCP 工具用 `inputJSONSchema`（原始 JSON Schema），绕过了 Zod——这是一个设计不一致的地方
4. **`strictObject` 的严格性**：不允许额外字段——有时过于限制

横向对比：

| 工具 | 输入验证方案 | 特点 |
|------|------------|------|
| **Claude Code** | Zod v4 + lazySchema | 类型推导 + 验证 + JSON Schema 三合一 |
| **LangChain** | Pydantic（Python） | 类似理念，Python 生态的 Zod |
| **OpenAI Function Calling** | 手写 JSON Schema | 无类型推导，无运行时验证 |
| **AutoGPT** | 无验证 | 信任模型输出，运行时错误多 |

---

## 如果重新设计

### lazySchema 的模板代码能否消除？

每个工具都需要三行的 `lazySchema` 包装。这是可以接受的模板代码，但如果工具数量继续增长（当前 43 个），有没有更优雅的方式？Bun 的 `import type` 或者装饰器模式可能是一种替代。

### MCP 工具绕过 Zod 是设计缺陷吗？

MCP 工具使用原始 JSON Schema 而不是 Zod，这打破了"单一来源"的原则。MCP 协议应该支持 Zod schema 吗？或者至少在 MCP 工具加载时，把 JSON Schema 转换成 Zod schema 来统一验证管线？

### 更轻量的替代方案？

在大规模校验场景下（比如同时处理几十个工具调用的参数），Zod 的运行时开销有多大？有没有更轻量的替代方案？Valibot（Zod 的轻量替代品）可能是一个值得考虑的方向——它支持 tree-shaking，只打包你用到的校验功能。

---

## 试试看

### 练习一：构造一个校验失败的场景

在 BashTool 的 `inputSchema` 中找到 `command` 字段，然后用代码尝试传入一个非字符串的 `command`。观察 `safeParse` 返回的错误格式。

### 练习二：追踪 JSON Schema 的生成路径

从工具的 `inputSchema` 开始，追踪 Zod schema 是如何被转换成 JSON Schema，最终发送给 Anthropic API 的。找到 `tools` 参数的构造位置。

### 练习三：对比 strictObject 和 object

把某个工具的 `z.strictObject` 改成 `z.object`，然后让 AI 传入一个额外的字段。观察行为差异。

---

## 检查点

- **Zod 的三重角色**：类型推导（编译时）、运行时校验（运行时）、JSON Schema 生成（API 桥梁）
- **lazySchema + z.strictObject 是项目惯例**：延迟初始化 + 不允许额外字段
- **单一来源原则**：一份 Zod schema 定义，三种用途，永远同步
- **`.describe()` 服务于 AI**：字段描述直接指导模型的工具使用
- **satisfies 操作符**：编译时检查工具实现是否匹配 schema
- **代价**：Zod v4 生态不成熟、模板代码、MCP 工具绕过 Zod

---

> **导航**
>
> 上一章：[第 42 章：为什么是 React/Ink](./第42章-为什么是React-Ink.md)
>
> 下一章：[第 44 章：工具系统的演进](./第44章-工具系统的演进.md)
