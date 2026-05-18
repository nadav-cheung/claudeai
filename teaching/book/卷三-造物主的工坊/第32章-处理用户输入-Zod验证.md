# 第 32 章：处理用户输入——Zod 验证

> 源码验证日期：2026-05-15，基于 commit `0d81bb6`

上一章，你创建了自己的第一个工具。它接收输入、做事情、返回结果。但你有没有想过一个问题：如果 AI 传过来的参数不对呢？

比如你的工具期望一个文件路径，AI 传了一个空字符串。或者你期望一个枚举值 `"replace"`，AI 传了一个 `"overwrite"`。再或者你定义了一个可选参数，AI 反而把它填成了 `"undefined"`——注意，是字符串 `"undefined"`，不是真正的 undefined。

这些不是假设。Claude Code 的开发者每天都在处理这些问题。AI 是一个概率模型，它生成的 JSON 参数有时候就是会出格。你的工具需要一道防线，把不合法的输入挡在门外。

这道防线就是 **Zod schema**。

这一章，我们从 Claude Code 源码中的真实工具出发，学习如何用 Zod 设计健壮的输入验证。

---

## 路线图

```mermaid
graph LR
    CH31["第 31 章<br/>创建你的第一个工具"] --> CH32["🔧 第 32 章<br/>处理用户输入"]
    CH32 --> CH33["第 33 章<br/>添加权限规则"]

    style CH32 fill:#4CAF50,color:#fff,stroke:#333
    style CH31 fill:#e8f5e9,stroke:#333
    style CH33 fill:#e1f5fe,stroke:#333
```

---

## Zod 在 Claude Code 里的三重身份

在动手之前，先理解为什么 Claude Code 选择了 Zod 而不是其他方案。打开 `src/Tool.ts`，找到 `Tool` 类型的 `inputSchema` 字段——它是一个 Zod schema。这个 schema 同时做了三件事：

1. **类型推导**——`z.infer<typeof schema>` 自动生成 TypeScript 类型，不需要手写
2. **运行时验证**——`safeParse()` 在工具执行前拦截不合法输入
3. **JSON Schema 生成**——Zod schema 被转换成 Anthropic API 要求的工具参数格式

被否决的方案包括：手写 JSON Schema（类型和 schema 分离，容易不一致）、信任模型输出不验证（运行时错误频发）、io-ts 等其他库（API 不够直观，JSON Schema 生成需额外库）。Zod 是"单一来源"的最佳实践——schema 定义一次，类型、验证、API 文档全部自动生成。

---

## 第一步：最简单的 schema——两个必填字符串

让我们从源码中最简洁的 schema 开始。`FileWriteTool` 是写文件的工具，它的输入只有两个字段：

```typescript
// 文件：src/tools/FileWriteTool/FileWriteTool.ts
const inputSchema = lazySchema(() =>
  z.strictObject({
    file_path: z
      .string()
      .describe(
        'The absolute path to the file to write (must be absolute, not relative)',
      ),
    content: z.string().describe('The content to write to the file'),
  }),
)
```

逐行拆解：

**`z.strictObject`**——定义一个对象，并且**不允许额外字段**。如果 AI 传了 `{ file_path: "...", content: "...", encoding: "utf8" }`，那个多出来的 `encoding` 会被拒绝。为什么？因为工具应该只接收自己能理解的参数。多余字段可能是 AI 的"幻觉"——它以为这个工具支持编码选项，其实不支持。`strictObject` 把这些幻觉挡在门外。

**`z.string()`**——声明这个字段的值必须是字符串。如果 AI 传了 `{ file_path: 123 }`（一个数字），Zod 会报错。

**`.describe('...')`**——这是 Zod 的元数据功能，给字段加一段人类可读的描述。但它的作用不止于此。Claude Code 会把 schema 转换成 JSON Schema 发送给 AI。这段 `.describe()` 里的文字就是 AI 看到的参数说明。AI 读到 "must be absolute, not relative"，就知道该传绝对路径而不是相对路径。**好的 `.describe()` 就是好的 AI 提示词。**

注意看 `file_path` 的描述。它不仅说了"是什么"（文件路径），还特别强调了"不是什么"（不能是相对路径）。这是写工具描述的一个好习惯：**告诉 AI 边界在哪里，比告诉它规则是什么更有效。**

---

## 第二步：可选字段和默认行为

`FileWriteTool` 太简单了——两个必填字段，没有可选余地。让我们看一个有可选字段的例子。`GlobTool` 用来按模式搜索文件：

```typescript
// 文件：src/tools/GlobTool/GlobTool.ts
const inputSchema = lazySchema(() =>
  z.strictObject({
    pattern: z.string().describe('The glob pattern to match files against'),
    path: z
      .string()
      .optional()
      .describe(
        'The directory to search in. If not specified, the current working directory will be used. IMPORTANT: Omit this field to use the default directory. DO NOT enter "undefined" or "null" - simply omit it for the default behavior. Must be a valid directory path if provided.',
      ),
  }),
)
```

`pattern` 是必填的，`path` 是可选的。注意 `.optional()` 的位置——它链在 `z.string()` 后面，意思是"这个字段可以不存在"。

但重点在 `path` 的 `.describe()` 上。这段描述很长，而且包含了一个 `IMPORTANT` 警告。为什么？因为 AI 有一个常见错误：当它不想传某个可选参数时，它不会直接省略这个字段，而是把它设为字符串 `"undefined"` 或 `"null"`。这段描述就是专门防止这个问题的——它明确告诉 AI "DO NOT enter undefined or null, simply omit it"。

这是设计工具 schema 的一条重要经验：**你以为的"可选"对 AI 来说不是理所当然的。你需要用明确的文字告诉它怎么处理可选字段。**

---

## 第三步：枚举——限制可选值

有时候，一个参数只能取几个固定值。比如搜索工具的输出模式只能是"内容"、"文件列表"或"计数"。`GrepTool` 用 `z.enum` 来表达这个约束：

```typescript
// 文件：src/tools/GrepTool/GrepTool.ts
output_mode: z
  .enum(['content', 'files_with_matches', 'count'])
  .optional()
  .describe(
    'Output mode: "content" shows matching lines, "files_with_matches" shows file paths, "count" shows match counts. Defaults to "files_with_matches".',
  ),
```

`z.enum` 接收一个字符串数组，表示这个字段只能取这几个值。如果 AI 传了 `output_mode: "summary"`，Zod 会直接拒绝，并返回一条错误信息告诉 AI 可选值是什么。

再看 `NotebookEditTool` 的例子，它有两个 enum 字段：

```typescript
// 文件：src/tools/NotebookEditTool/NotebookEditTool.ts
cell_type: z
  .enum(['code', 'markdown'])
  .optional()
  .describe(
    'The type of the cell. If not specified, it defaults to the current cell type. If using edit_mode=insert, this is required.',
  ),
edit_mode: z
  .enum(['replace', 'insert', 'delete'])
  .optional()
  .describe(
    'The type of edit to make. Defaults to replace.',
  ),
```

注意 `cell_type` 的描述里有一条额外的规则："如果 edit_mode 是 insert，那 cell_type 是必填的。" 这种跨字段的条件约束 Zod 本身表达不了（它只能验证单个字段的类型），但你可以写在 `.describe()` 里让 AI 知道，然后在 `validateInput()` 里做真正的运行时校验。

---

## 第四步：数组——重复元素

有些工具需要接收一个列表。`TodoWriteTool` 是管理任务清单的工具，它的输入是一个 todo 数组：

```typescript
// 文件：src/tools/TodoWriteTool/TodoWriteTool.ts
const inputSchema = lazySchema(() =>
  z.strictObject({
    todos: TodoListSchema().describe('The updated todo list'),
  }),
)
```

`TodoListSchema` 是一个更复杂的数组 schema（定义在 `src/utils/todo/types.ts`），但从概念上讲就是 `z.array(z.object({...}))`——一个对象数组。

`z.array(某schema)` 表示"一个由符合某 schema 的元素组成的数组"。嵌套的 schema 定义了每个元素的结构。这是处理列表数据的标准方式。

---

## 第五步：lazySchema——为什么要包一层

你可能注意到，所有这些 schema 都被包在一个 `lazySchema()` 里。这个包装器的实现极其简单：

```typescript
// 文件：src/utils/lazySchema.ts
export function lazySchema<T>(factory: () => T): () => T {
  let cached: T | undefined
  return () => (cached ??= factory())
}
```

它做的事情是：把 schema 的创建推迟到第一次被访问的时候，并且缓存结果。为什么要这样做？

因为工具在模块加载时就被定义了。如果 schema 引用了其他模块的类型（比如 `hunkSchema` 引用了 `gitDiffSchema`，`TodoListSchema` 引用了 todo 类型），而这些模块还没加载完，就会出现循环依赖问题。`lazySchema` 把 schema 的创建延迟到运行时，等所有模块都加载好了再执行。

这不是 Zod 的功能，而是 Claude Code 的工程实践。在你的工具里也建议使用它——养成习惯就好。

---

## 第六步：semanticBoolean 和 semanticNumber——AI 的坏习惯

AI 生成 JSON 时有一些让人头疼的坏习惯。它偶尔会把布尔值写成字符串——`"replace_all": "false"` 而不是 `"replace_all": false`。或者把数字写成字符串——`"head_limit": "30"` 而不是 `"head_limit": 30。

`z.boolean()` 会拒绝字符串 `"false"`，`z.number()` 会拒绝字符串 `"30"`。用 `z.coerce` 可以强制转换，但它太宽松了——`z.coerce.boolean()` 把任何非空字符串都转成 `true`（包括 `"false"`！），`z.coerce.number()` 把空字符串转成 `0`。

Claude Code 的解决方案是两个专门的包装器：`semanticBoolean` 和 `semanticNumber`。

```typescript
// 文件：src/utils/semanticBoolean.ts
export function semanticBoolean<T extends z.ZodType>(
  inner: T = z.boolean() as unknown as T,
) {
  return z.preprocess(
    (v: unknown) => (v === 'true' ? true : v === 'false' ? false : v),
    inner,
  )
}
```

它做的事很简单：在 Zod 验证之前，先把字符串 `"true"` 转成 `true`，把 `"false"` 转成 `false`，其他值原样传给内层的 schema。这样 AI 传 `"false"` 也能通过验证，而不会出现 `z.coerce.boolean()` 那种把 `"false"` 当成 `true` 的荒谬错误。

`semanticNumber` 的思路类似，只接受合法的数字字符串（如 `"30"`、`"-5"`），拒绝非数字字符串。

GrepTool 大量使用了这两个包装器：

```typescript
// 文件：src/tools/GrepTool/GrepTool.ts
'-B': semanticNumber(z.number().optional()).describe(
  'Number of lines to show before each match',
),
'-i': semanticBoolean(z.boolean().optional()).describe(
  'Case insensitive search',
),
```

这是另一个值得学习的工程经验：**不要假设 AI 会严格按照 JSON 类型传参。给它留一点容错空间，但不要无限宽容。**

---

## 第七步：升级你的 TimestampTool

现在，让我们把上一章创建的 TimestampTool 升级一下。给它加上更丰富的输入验证——支持更多格式、加入语言选项：

```typescript
import { z } from 'zod/v4'
import { lazySchema } from '../../utils/lazySchema.js'

const inputSchema = lazySchema(() =>
  z.strictObject({
    format: z
      .enum(['iso', 'unix', 'locale', 'rfc2822'])
      .optional()
      .describe(
        'Output format. "iso" for ISO 8601 (default), "unix" for Unix timestamp, ' +
        '"locale" for human-readable local time, "rfc2822" for email date format.',
      ),
    timezone: z
      .string()
      .optional()
      .describe(
        'IANA timezone identifier (e.g., "Asia/Shanghai", "America/New_York"). ' +
        'Only used with "locale" format. IMPORTANT: Omit this field for system default timezone. ' +
        'DO NOT enter "undefined" or "null".',
      ),
  }),
)
```

这个 schema 做了什么？

1. **`format`** 用 `z.enum` 限制为四种值，用 `.optional()` 表示可省略（默认 iso）
2. **`timezone`** 是可选字符串，只在 `locale` 格式下有意义。描述中明确告诉 AI 省略的方法

然后在 `call()` 里做跨字段的验证：

```typescript
async call(input) {
  const format = input.format ?? 'iso'

  // 跨字段验证：timezone 只对 locale 格式有意义
  if (input.timezone && format !== 'locale') {
    return {
      data: {
        timestamp: new Date().toISOString(),
        format,
        warning: 'timezone parameter is ignored for non-locale formats',
      },
    }
  }

  let timestamp: string
  switch (format) {
    case 'unix':
      timestamp = String(Math.floor(Date.now() / 1000))
      break
    case 'locale':
      const options: Intl.DateTimeFormatOptions = {}
      if (input.timezone) options.timeZone = input.timezone
      timestamp = new Date().toLocaleString('zh-CN', options)
      break
    case 'rfc2822':
      timestamp = new Date().toUTCString()
      break
    case 'iso':
    default:
      timestamp = new Date().toISOString()
      break
  }

  return { data: { timestamp, format } }
}
```

---

## 验证错误如何被 AI 看到

当 AI 传了不合法的参数时，Zod 的验证错误会变成一条错误信息返回给 AI。比如 AI 传了：

```json
{ "format": "rfc3339", "timezone": "Mars/Opportunity" }
```

Zod 会生成类似这样的错误：

- `format`: 不合法的枚举值。可选值为 'iso' | 'unix' | 'locale' | 'rfc2822'

AI 读到这条错误，会在下一轮自动修正参数重新调用。这就是为什么 `.describe()` 里的描述如此重要——好的描述让 AI 一次就传对参数，减少来回次数。

---

## 常见错误

| 常见错误 | 检查方法 |
|----------|----------|
| AI 总是传多余字段 | 使用 `z.strictObject`（严格），不要用 `z.object`（宽松） |
| AI 把可选字段设成 `"undefined"` | 在 `.describe()` 里加 `IMPORTANT: Omit this field...` 警告 |
| AI 传了 `"true"` 字符串而非布尔值 | 用 `semanticBoolean` 包装器容忍这种常见错误 |
| enum 的值需要动态变化 | 退回 `z.string()` 加 `validateInput()` 手动校验 |
| schema 引起循环依赖 | 用 `lazySchema()` 延迟创建 |
| AI 传了 `"30"` 字符串而非数字 | 用 `semanticNumber` 包装器 |

---

## 试试看

1. **给 TimestampTool 的 `format` 字段添加一个 `relative` 选项**（如 "3 小时前"）。你需要修改 `z.enum` 和 `call()` 的 switch 语句。测试一下 AI 传了 `"relativ"` 拼写错误时 Zod 的报错信息。
2. **设计一个文件搜索工具的 schema**。要求：`pattern`（必填字符串）、`path`（可选字符串）、`max_results`（可选正整数，默认 50）、`case_sensitive`（可选布尔，默认 false）。用 `semanticBoolean` 和 `semanticNumber` 处理 AI 的类型错误。
3. **阅读 `src/tools/GrepTool/GrepTool.ts` 的完整 schema**——它是 Claude Code 中最复杂的 schema 之一。找出所有你学过的模式：`strictObject`、`enum`、`optional`、`semanticBoolean`、`semanticNumber`。

---

## 检查点

- **`z.strictObject`** 是 Claude Code 的默认选择——拒绝多余字段，防止 AI 的"幻觉"参数
- **`.describe()`** 不只是给人看的注释，它是给 AI 的使用指南。好的描述能减少 AI 传错参数的概率
- **`.optional()`** 标记可选字段，但要在描述里明确告诉 AI 怎么处理省略
- **`z.enum`** 限制参数为固定值，是防止 AI "发明"选项的最佳方式
- **`semanticBoolean` 和 `semanticNumber`** 处理 AI 偶尔的类型错误——宽容但不放纵
- **`lazySchema`** 延迟 schema 创建，避免模块加载时的循环依赖
- **验证错误** 是 Zod 和 AI 之间的对话——AI 传错参数时会看到错误信息并自动修正

记住，输入验证不是一堵墙——它是一个对话。Zod 拦住了不合法的参数，告诉 AI 哪里错了，AI 在下一轮自动修正。好的 schema 设计让这个对话尽量短。

---

## 验证——你的 Zod schema 做对了吗？

1. **编译检查**：`tsc --noEmit` 确认 schema 类型推断正确，`z.infer<typeof schema>` 输出的类型与 `call()` 期望的参数类型一致
2. **合法输入测试**：用 `schema.safeParse(validInput)` 确认合法参数通过，返回 `{ success: true }`
3. **非法输入测试**：用 `schema.safeParse(invalidInput)` 确认多余字段被拒绝（`strictObject`）、错误类型被拦截、缺少必填字段返回明确错误
4. **AI 对话测试**：启动 Claude Code，故意让 AI 调用你的工具并传错参数——观察 AI 是否能看到 Zod 错误并自动修正

---

[上一章：创建你的第一个工具](./第31章-创建你的第一个工具.md) | [下一章：添加权限规则](./第33章-添加权限规则.md)
