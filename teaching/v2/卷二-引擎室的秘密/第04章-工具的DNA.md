---
title: "第04章：工具的 DNA"
description: "每个工具——不管是读文件、执行命令还是搜索代码——都共享同一套基因。这套基因就是 Tool 类型。本章深入 Tool<Input, Output, P> 泛型的三个类型参数、三个核心方法（prompt / call / checkPermissions），以及 Zod 如何在运行时提供验证和类型安全。"
tags: [tool-interface, generics, zod, type-safety, design-patterns, interface-vs-inheritance]
date: 2026-05-10
---

# 第04章：工具的 DNA

你已经在卷一见过工具了。AI 说"我要读一个文件"，BashTool 跑去执行命令，ReadTool 把文件内容搬回来。每一个工具都是不同的：有的读文件，有的写文件，有的搜索代码，有的访问网页。

但你有没有想过一个问题：Claude Code 里 30 多个工具，它们千差万别，系统是怎么用统一的方式管理它们的？

答案在这四个字母里：**T-o-o-l**。

`Tool` 是一个类型定义，它规定了所有工具必须长什么样、必须能做什么。就像 DNA 决定了所有生物用同一套遗传密码一样，`Tool` 类型决定了所有工具用同一套接口与外界交互。不管你是 BashTool 还是 ReadTool 还是某个你从未听说过的工具，只要它实现了 `Tool`，系统就知道怎么调用它、怎么显示它、怎么检查它的权限。

这一章，我们打开 `Tool` 的 DNA，看看里面的碱基对。

---

## 这是什么

想象一个大型工厂。工厂里有几十种工位：焊接、喷涂、质检、包装。每个工位做的事情完全不同，但它们都遵循同一套标准操作流程：

1. **工作手册**——描述这个工位能做什么、什么时候该启用。
2. **执行任务**——接收原材料（输入），产出成品（输出）。
3. **安全检查**——在执行之前确认操作是允许的。

Claude Code 的 `Tool` 类型就是这个标准操作流程。每个工具都是工厂里的一个工位，千差万别，但都遵循同一套三步流程。

---

## 打开源码

Tool 的核心定义在 `src/Tool.ts` 里。这个文件有将近 800 行，但我们只需要关注几个关键位置：

- 第 362-695 行：`Tool<Input, Output, P>` 类型——这是 DNA 的主体。
- 第 721-726 行：`ToolDef<Input, Output, P>` 类型——这是简化的定义格式。
- 第 757-792 行：`buildTool` 函数——这是工具的工厂方法。

我们一个一个看。

---

## 它怎么工作

### 泛型：三个类型参数

打开 `Tool` 类型的定义，你首先会看到这一行：

```typescript
// 文件：src/Tool.ts，第362行
export type Tool<
  Input extends AnyObject = AnyObject,
  Output = unknown,
  P extends ToolProgressData = ToolProgressData,
> = {
  // ... 几百行定义 ...
}
```

三个尖括号里的东西就是 **泛型参数**。泛型是什么？你可以把它理解为"占位符"。就像表格模板里写着"姓名：\_\_\_"，等填表的时候才写上具体名字。泛型参数就是类型层面的占位符——`Tool` 本身不知道输入是什么形状、输出是什么形状，但具体到某个工具（比如 BashTool），它会说："我的 Input 是命令字符串，我的 Output 是执行结果。"

让我们看看这三个参数分别是什么。

**Input extends AnyObject**——输入的形状。每个工具接收的参数不同：BashTool 接收一个命令字符串，ReadTool 接收一个文件路径，EditTool 接收旧文本和新文本。`Input` 规定了"这个工具的输入长什么样"。`extends AnyObject` 是一个约束，意思是 Input 必须是一个对象——不能是字符串，不能是数字。为什么？因为工具的输入最终来自 AI 的 JSON 输出，而 JSON 对应到 TypeScript 里就是对象。

**Output**——输出的形状。工具执行完返回什么。注意它的默认值是 `unknown`，意思是"我不管你返回什么"。很多工具不需要精确描述自己的输出类型，用默认值就行。

**P extends ToolProgressData**——进度数据的形状。有些工具执行时间很长（比如跑一个测试套件），需要实时报告进度。`P` 规定了进度信息长什么样。

这三个参数组合在一起，就精确描述了一个工具的"数据指纹"。BashTool 的指纹是 `Tool<BashInput, BashOutput, BashProgress>`，ReadTool 的指纹是 `Tool<ReadInput, string, ToolProgressData>`。它们共享同一套行为接口，但数据类型各不相同。

---

### 三个核心方法

`Tool` 类型定义了几十个方法，但真正核心的只有三个。

**第一个：prompt()——工作手册。**

```typescript
// 文件：src/Tool.ts，第518行
prompt(options: {
  getToolPermissionContext: () => Promise<ToolPermissionContext>
  tools: Tools
  agents: AgentDefinition[]
  allowedAgentTypes?: string[]
}): Promise<string>
```

`prompt()` 返回一段文字，告诉 AI 这个工具是什么、什么时候该用它、怎么用它。这段文字会被塞进系统提示词里，成为 AI 的"工作手册"。AI 读到这段手册，就知道："哦，有一个叫 Bash 的工具，它接收一个命令字符串，在终端里执行，返回输出结果。当用户让我运行命令的时候，我应该调用这个工具。"

举一个实际的例子。`TaskGetTool`（根据 ID 获取任务详情）的 prompt 是这样的：

```typescript
// 文件：src/tools/TaskGetTool/prompt.ts，第1-24行
export const PROMPT = `Use this tool to retrieve a task by its ID from the task list.

## When to Use This Tool

- When you need the full description and context before starting work on a task
- To understand task dependencies (what it blocks, what blocks it)
- After being assigned a task, to get complete requirements

## Output

Returns full task details:
- **subject**: Task title
- **description**: Detailed requirements and context
- **status**: 'pending', 'in_progress', or 'completed'
- **blocks**: Tasks waiting on this one to complete
- **blockedBy**: Tasks that must complete before this one can start

## Tips

- After fetching a task, verify its blockedBy list is empty before beginning work.
- Use TaskList to see all tasks in summary form.
`
```

注意 `prompt()` 是一个方法，不是静态字符串——工具可以根据当前状态动态生成描述。但在实践中，大多数工具直接返回一段预写好的文本。

**第二个：call()——执行任务。**

```typescript
// 文件：src/Tool.ts，第379行
call(
  args: z.infer<Input>,
  context: ToolUseContext,
  canUseTool: CanUseToolFn,
  parentMessage: AssistantMessage,
  onProgress?: ToolCallProgress<P>,
): Promise<ToolResult<Output>>
```

这是工具的心脏。当 AI 决定使用某个工具时，系统会调用这个工具的 `call()` 方法，传入参数，拿到结果。

参数的含义：

- `args`——AI 提供的输入参数。注意类型是 `z.infer<Input>`，从 Zod schema 推导出来的类型。后面会详细讲。
- `context`——工具执行的上下文，包含当前项目信息、可用命令、MCP 客户端等。
- `canUseTool`——检查工具是否被允许使用的函数。
- `parentMessage`——触发这个工具调用的 AI 消息。
- `onProgress`——可选的进度回调。长时间运行的工具可以实时报告进度。

以 TaskGetTool 为例，它的 `call()` 方法非常简洁：

```typescript
// 文件：src/tools/TaskGetTool/TaskGetTool.ts，第73-97行
async call({ taskId }) {
  const taskListId = getTaskListId()
  const task = await getTask(taskListId, taskId)

  if (!task) {
    return { data: { task: null } }
  }

  return {
    data: {
      task: {
        id: task.id,
        subject: task.subject,
        description: task.description,
        status: task.status,
        blocks: task.blocks,
        blockedBy: task.blockedBy,
      },
    },
  }
},
```

接收一个 taskId，从任务列表里查出来，包装成标准格式返回。就这么简单。

**第三个：checkPermissions()——安全检查。**

```typescript
// 文件：src/Tool.ts，第500行
checkPermissions(
  input: z.infer<Input>,
  context: ToolUseContext,
): Promise<PermissionResult>
```

在 `call()` 被真正执行之前，系统会先调用 `checkPermissions()`。这个方法决定：这个工具这次被调用，是否需要用户授权？如果需要，以什么方式授权？

`PermissionResult` 有几种可能的结果：`allow`（直接放行）、`deny`（直接拒绝）、`ask`（弹出确认对话框让用户决定）。这个三步设计——验证输入、检查权限、执行调用——构成了一个完整的安全管道。

以 FileEditTool 为例：

```typescript
// 文件：src/tools/FileEditTool/FileEditTool.ts，第125行
async checkPermissions(input, context): Promise<PermissionDecision> {
  const appState = context.getAppState()
  return checkWritePermissionForTool(
    FileEditTool,
    input,
    appState.toolPermissionContext,
  )
},
```

它把权限检查委托给了 `checkWritePermissionForTool` 函数——检查当前权限模式、文件路径是否在白名单里、是否需要用户确认。

**三步的执行顺序**是严格固定的：先 `validateInput()`（验证输入参数），再 `checkPermissions()`（检查权限），最后 `call()`（真正执行）。就像机场安检：先查机票，再查登机资格，最后登机。任何一步失败，后续都不会执行。

---

### inputSchema：Zod 的双重身份

在 `Tool` 类型中有一个字段叫 `inputSchema`：

```typescript
// 文件：src/Tool.ts，第394行
readonly inputSchema: Input
```

它的类型是 `Input`，也就是我们的第一个泛型参数。但在实际使用中，这个字段几乎总是被赋值为一个 **Zod schema**。

Zod 是什么？它是一个 TypeScript 的运行时验证库。它做了两件事：

1. **运行时验证**——当 AI 传过来一段 JSON 参数时，Zod 会检查这段 JSON 是否符合预期。如果 AI 传了一个应该是数字的字段但给了一个字符串，Zod 会拦截它。
2. **编译时类型推导**——通过 `z.infer<Schema>` 语法，TypeScript 能从 Zod schema 反推出对应的 TypeScript 类型。你只需要写一次 schema，类型就自动生成了。

这就是 `z.infer<Input>` 在 `call()` 参数中的含义：不是直接写一个 TypeScript 类型，而是从 Zod schema 自动推导出来。

以 TaskGetTool 为例：

```typescript
// 文件：src/tools/TaskGetTool/TaskGetTool.ts，第13-17行
const inputSchema = lazySchema(() =>
  z.strictObject({
    taskId: z.string().describe('The ID of the task to retrieve'),
  }),
)
```

这个 schema 说：输入是一个对象，有且只有一个字段 `taskId`，类型是字符串，描述是"要检索的任务 ID"。Zod 从这个 schema 推导出的类型等价于 `{ taskId: string }`。你不需要手写这个类型——Zod 帮你做了。

`z.strictObject` 和普通的 `z.object` 有什么区别？`strictObject` 不允许出现 schema 里没有定义的额外字段。这对工具输入来说很重要——AI 有时候会"多给"参数，`strictObject` 会把这些多余的参数挡在门外，避免意外行为。

你可能注意到了 `lazySchema` 包裹。这是一个延迟求值的包装器。工具在模块加载时就被定义了，但有些 Zod 类型引用的其他类型可能还没加载好。`lazySchema` 把 schema 的创建推迟到第一次被访问的时候，避免了模块加载的循环依赖问题。

`inputSchema` 还有另一个用途：它会被转换成 JSON Schema 格式，放在 API 请求的工具定义里，告诉 AI 这个工具接收什么参数。AI 看到 JSON Schema，就知道该传什么参数。所以 `inputSchema` 其实服务两个主人：Zod 用它做运行时验证，API 用它告诉 AI 参数格式。

---

### ToolDef 和 buildTool：简化的定义方式

如果你每次写一个工具都要实现 `Tool` 里的所有方法，那会非常繁琐。`Tool` 类型有几十个字段和方法，但大部分工具只需要关心其中几个。

于是有了 `ToolDef` 和 `buildTool`。

`ToolDef` 是 `Tool` 的简化版：

```typescript
// 文件：src/Tool.ts，第721-726行
export type ToolDef<
  Input extends AnyObject = AnyObject,
  Output = unknown,
  P extends ToolProgressData = ToolProgressData,
> = Omit<Tool<Input, Output, P>, DefaultableToolKeys> &
  Partial<Pick<Tool<Input, Output, P>, DefaultableToolKeys>>
```

这段类型体操在说什么？它把 `Tool` 类型拆成两部分：

- **必须实现的部分**——`name`、`inputSchema`、`call()`、`prompt()`、`description()`、`mapToolResultToToolResultBlockParam()`、`renderToolUseMessage()`。
- **可选实现的部分**——`isEnabled()`、`isConcurrencySafe()`、`isReadOnly()`、`isDestructive()`、`checkPermissions()`、`toAutoClassifierInput()`、`userFacingName()`。这些有默认值，你可以覆盖它们，也可以不管。

`buildTool` 函数就是那个帮你"填空"的人：

```typescript
// 文件：src/Tool.ts，第757-792行
const TOOL_DEFAULTS = {
  isEnabled: () => true,
  isConcurrencySafe: (_input?: unknown) => false,
  isReadOnly: (_input?: unknown) => false,
  isDestructive: (_input?: unknown) => false,
  checkPermissions: (
    input: { [key: string]: unknown },
    _ctx?: ToolUseContext,
  ): Promise<PermissionResult> =>
    Promise.resolve({ behavior: 'allow', updatedInput: input }),
  toAutoClassifierInput: (_input?: unknown) => '',
  userFacingName: (_input?: unknown) => '',
}

export function buildTool<D extends AnyToolDef>(def: D): BuiltTool<D> {
  return {
    ...TOOL_DEFAULTS,
    userFacingName: () => def.name,
    ...def,
  } as BuiltTool<D>
}
```

注意执行顺序：先展开 `TOOL_DEFAULTS`（填上所有默认值），再设置 `userFacingName` 默认为工具名，最后展开你传入的 `def`（你的自定义实现会覆盖同名的默认值）。这是一个经典的"默认值 + 用户覆盖"模式。

看看默认值的设计哲学：

- `isEnabled` 默认 `true`——大部分工具都是启用的，只有少数需要根据配置开关。
- `isConcurrencySafe` 默认 `false`——**假设不安全**。这是"fail-closed"（失败时关闭）的思路：如果你不确定一个工具能否并发执行，那就假设它不能。
- `isReadOnly` 默认 `false`——**假设是写操作**。同样是 fail-closed：不确定就当成会修改文件来处理。
- `checkPermissions` 默认放行——这不是安全漏洞，因为通用的权限系统在更上层已经检查过了。工具特定的 `checkPermissions` 只是提供额外的精细控制。

这种设计让你写一个新工具的门槛非常低。最简情况下，你只需要提供 `name`、`inputSchema`、`call()`、`prompt()`、`description()` 和几个渲染方法，其他全部使用默认值。

---

### 为什么是接口，不是继承

如果你熟悉面向对象编程，你可能会问：为什么不定义一个 `BaseTool` 抽象类，让所有工具继承它？这样默认值可以直接放在基类里，不用搞 `buildTool` 这种函数。

这是一个经典的设计选择：**接口组合 vs 类继承**。

Claude Code 选择接口（`type`）有三个原因。

**第一，TypeScript 的类型是结构化的。** 在 Java 里，一个类必须显式声明 `implements Tool`。在 TypeScript 里，只要对象的形状匹配 `Tool` 类型，它就自动满足。这让 `buildTool` 的展开语法能够自然工作。

**第二，组合比继承更灵活。** 类继承是线性的——一个类只能有一个父类。`buildTool` 的方式是组合：默认值和自定义定义合并在一起。将来需要混入额外能力（"可缓存"、"可重试"），组合可以轻松做到。

**第三，工具的多样性不适合继承树。** 有些工具只读，有些可写。有些需要权限检查，有些不需要。如果用继承，你需要各种排列组合的中间类（`ReadOnlyTool`、`WritableToolWithPermission`……）。接口没有这个问题——每个方法独立可选，默认值填补空缺。

---

## 对比：如果用 Java

如果用 Java 来实现同样的设计，你会怎么写？

最接近的类比是 Java 的泛型接口。比如 `Callable<V>`——它只定义了一个方法 `V call()`，任何类只要实现这个方法就可以被线程池执行。`Tool<Input, Output, P>` 的思路是一样的：定义一个最小化的接口，让实现者自由发挥。

但 Java 和 TypeScript 在这里有一个重要区别。Java 的接口方法不能有默认实现（Java 8 引入了 `default` 方法，但使用起来比 TypeScript 的展开语法笨重得多）。所以 Java 版本通常会这样设计：

```java
// Java 版本的 Tool 接口
public interface Tool<I, O> {
    String prompt(ToolContext ctx);
    O call(I input, ToolContext ctx) throws ToolException;
    PermissionResult checkPermissions(I input, ToolContext ctx);
    default boolean isEnabled() { return true; }
    default boolean isReadOnly(I input) { return false; }
}
```

这可以工作，但有两个问题。第一，`default` 方法不能引用 `this` 以外的状态——你想让 `userFacingName` 默认返回工具名？不行，接口不知道工具名是什么。第二，Java 的泛型有类型擦除——`Tool<BashInput, BashOutput>` 和 `Tool<ReadInput, String>` 在运行时是同一个类型 `Tool`，你无法在运行时检查类型参数。

如果你熟悉 Spring 框架，还有一个更贴切的类比：`HandlerInterceptor`。它定义了 `preHandle()`、`postHandle()`、`afterCompletion()`，围绕每个请求形成拦截链。Claude Code 的 `validateInput()` -> `checkPermissions()` -> `call()` 也是类似的链式结构，只不过围绕工具调用而不是 HTTP 请求。`preHandle` 对应 `checkPermissions`，handler 对应 `call()`，`postHandle` 对应结果渲染。但 Spring 通过类继承实现，Claude Code 只需要传一个对象给 `buildTool`——更轻量。

---

## 你能改什么

### 入门级：阅读和理解

如果你刚接触这个代码库，以下是一些安全的起点：

**阅读 prompt() 输出。** 打开任意一个工具目录下的 `prompt.ts` 文件（比如 `src/tools/TaskGetTool/prompt.ts`），读一读那个工具的工作手册。你会看到每个工具怎么向 AI 解释自己。这是一个理解工具行为的好方法——`prompt()` 里写的，就是 AI 看到的。如果你发现 AI 在某个工具上表现不好，先去看 `prompt()` 里的描述是否清晰。

**理解 inputSchema。** 找几个工具，看看它们的 `inputSchema` 定义。你会发现有些工具的 schema 很简单（一两个字段），有些很复杂（十几个字段，嵌套对象，条件验证）。对比简单和复杂的工具，你能感受到 Zod schema 的表达力。

**追踪 call() 的执行。** 在一个简单的工具（比如 TaskGetTool）的 `call()` 方法里打一个 `console.log`，然后触发这个工具，看看日志输出。这能帮你理解从 AI 发出调用请求到 `call()` 被执行的完整链路。

### 中级：修改现有工具

**优化 prompt() 的描述。** 如果你发现 AI 对某个工具的使用不够好（比如经常传错参数、在不该用的时候用了、在该用的时候没用），修改那个工具的 `prompt()` 是最直接的方式。`prompt()` 是纯文本，改错了也不会导致系统崩溃。

**调整权限策略。** 如果你想让某个工具在特定条件下自动放行（或自动拒绝），修改它的 `checkPermissions()` 方法。注意：权限相关的修改需要特别小心，因为安全是 fail-closed 的——宁可多问一次用户，也不要漏放一个危险操作。

### 危险区域

**修改 Tool 类型本身。** `Tool` 类型是整个工具系统的基石。改动它的某个方法签名，会影响所有 30 多个工具。如果你要在 `Tool` 里加一个新方法，你必须确保：所有现有工具要么实现了这个方法，要么它有一个合理的默认值。`buildTool` 里的 `TOOL_DEFAULTS` 也需要同步更新。这是一个"牵一发而动全身"的操作。

**修改泛型参数。** `Tool<Input, Output, P>` 的三个类型参数被整个代码库引用。改变任何一个参数的约束（比如修改 `extends AnyObject`），可能导致级联的编译错误。这不是不能做，但需要全局搜索和逐个修复。

**修改 buildTool 的默认值。** `TOOL_DEFAULTS` 里的默认值被所有未显式覆盖的工具依赖。把 `isReadOnly` 的默认值从 `false` 改成 `true`，会让所有没有显式声明自己可写的工具突然变成"只读"——这可能不是你想要的效果。默认值的改变需要非常慎重地评估影响范围。

---

## 回顾

这一章，我们拆开了 `Tool` 类型的 DNA：

1. **三个泛型参数** `Input`、`Output`、`P` 规定了工具的数据指纹——输入什么、输出什么、进度报告什么。
2. **三个核心方法** 构成了工具的生命周期：`prompt()` 告诉 AI 怎么用这个工具，`checkPermissions()` 在执行前做安全检查，`call()` 真正执行任务。
3. **inputSchema** 用 Zod 做了两件事：运行时验证 AI 传来的参数，编译时推导出 TypeScript 类型。一份定义，两份收益。
4. **ToolDef + buildTool** 提供了一个简化的定义方式——你只需要写核心逻辑，默认值由 `buildTool` 填充。
5. **选择接口而不是继承**，因为 TypeScript 的结构化类型系统和组合模式比类继承更适合这里的需求。

你看到了工具的 DNA——那个统一的接口。但接口只是图纸，真正的工具在哪里？下一章，我们看看那 30 多个工具是怎么被注册和管理起来的。

---

[上一章：React 在终端里奔跑](./第03章-React在终端里奔跑.md) | [下一章：30 个工具的故事](./第05章-30个工具的故事.md)
