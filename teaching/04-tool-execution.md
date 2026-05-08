# 04 - 工具执行与安全 (Tool Execution and Security)

> **本章目标**：深入理解 Claude Code 的工具执行管线 (pipeline)，包括从模型发出 tool_use 到最终返回 tool_result 的完整流程。掌握权限检查、沙箱隔离、Hook 钩子、并发控制等安全机制的设计原理和实现细节。

---

## 核心概念

### 1. 工具执行管线总览

工具执行是一个多阶段流水线：

```
tool_use block → 输入校验 → PreToolUse Hooks → 权限检查 → tool.call() → PostToolUse Hooks → tool_result
```

核心文件：
- `src/services/tools/toolExecution.ts` — 主执行管线
- `src/services/tools/StreamingToolExecutor.ts` — 并发执行调度器
- `src/services/tools/toolHooks.ts` — Hook 执行与权限决策解析

### 2. 沙箱系统 (Sandbox)

沙箱是一个 OS 级别的隔离层，用于限制 Bash 命令的文件系统和网络访问：
- 基于 `@anthropic-ai/sandbox-runtime` 包（bubblewrap on Linux, sandbox-exec on macOS）
- 配置来源于 `settings.json` 中的 `sandbox` 和 `permissions` 字段
- 不是安全边界，而是便利特性——真正的安全控制是权限提示系统

### 3. Bash 安全检查

Bash 工具有额外的安全层：
- **破坏性命令检测** — 识别 `rm -rf`、`git push --force` 等危险操作
- **路径验证** — 确保操作路径在允许的工作目录内
- **分类器 (Classifier)** — 使用 AI 模型判断命令是否安全
- **排除命令** — 用户可配置不需要沙箱的命令

### 4. Hook 系统

Hook 是用户配置的外部命令，在工具执行前后运行：
- **PreToolUse** — 在工具执行前运行，可以允许/拒绝/修改输入
- **PostToolUse** — 在工具成功执行后运行
- **PostToolUseFailure** — 在工具执行失败后运行

---

## 源码导览

### 入口：runToolUse (toolExecution.ts)

```
src/services/tools/toolExecution.ts:337 — runToolUse()
```

这是工具执行的统一入口。它接收一个 `ToolUseBlock`（来自模型的 tool_use content block），执行以下步骤：

1. **工具查找** — `findToolByName()` 在可用工具列表中查找，找不到则尝试别名兼容
2. **Abort 检查** — 如果已经 abort，直接返回取消消息
3. **流式权限检查+调用** — `streamedCheckPermissionsAndCallTool()` 将进度和结果统一为 AsyncIterable

### 核心流程：checkPermissionsAndCallTool (toolExecution.ts:599)

这是整个工具执行的脊梁函数，长约 1100 行，实现了完整的执行管线：

```
输入校验 (Zod schema)
  ↓
工具自定义校验 (tool.validateInput)
  ↓
Bash 分类器预启动 (startSpeculativeClassifierCheck)
  ↓
Backfill 输入字段
  ↓
PreToolUse Hooks (runPreToolUseHooks)
  ↓
权限决策解析 (resolveHookPermissionDecision)
  ↓
权限被拒 → 返回错误消息
权限通过 → 继续
  ↓
tool.call() — 实际执行
  ↓
PostToolUse Hooks (runPostToolUseHooks)
  ↓
返回结果消息
```

**为什么 Bash 分类器要"投机性"地提前启动？**

分类器在输入验证阶段（`toolExecution.ts:746`）就启动，比实际的权限检查提前了很多步。这是因为：

1. **延迟隐藏**：分类是 I/O 密集型操作（需要读文件、运行规则），提前启动可以把计算时间隐藏在工具执行的早期阶段
2. **auto 模式性能**：在 `auto` 模式下，分类器的结果直接影响权限决策（是否需要用户确认），提前算好可以让权限判断几乎零延迟
3. **异步缓存**：`startSpeculativeClassifierCheck` 把 Promise 存入 Map，`consumeSpeculativeClassifierCheck` 在权限检查时消费 — 如果已经算好就直接用，没算好就同步等待

```typescript
// 预启动：fire-and-forget，结果暂存 Map
speculativeChecks.set(command, promise)

// 权限检查时：直接取用，无需等待
const cached = speculativeChecks.get(command)
const result = cached ? await cached : await classifyBashCommand(...)
```

### 并发执行器：StreamingToolExecutor

```
src/services/tools/StreamingToolExecutor.ts:40 — StreamingToolExecutor class
```

模型可以在一个 response 中发出多个 tool_use block。StreamingToolExecutor 管理这些工具的并发执行：

- **TrackedTool** — 每个工具追踪状态：`queued → executing → completed → yielded`
- **并发安全判断** — `isConcurrencySafe()` 决定工具能否并行执行
- **兄弟错误取消** — 当一个 Bash 工具出错时，自动取消其他并行的 Bash 工具（`siblingAbortController`）
- **结果按序返回** — 即使工具并行执行，结果仍按模型发出的顺序 yield

关键设计决策：
```typescript
// 只有 Bash 错误会取消兄弟工具
// Bash 命令通常有隐式依赖链（如 mkdir 失败 → 后续命令无意义）
// Read/WebFetch 等独立工具不会互相影响
if (tool.block.name === BASH_TOOL_NAME) {
  this.hasErrored = true
  this.siblingAbortController.abort('sibling_error')
}
```

### Hook 系统 (toolHooks.ts)

#### PreToolUse Hooks

`runPreToolUseHooks()` 是一个 AsyncGenerator，yield 各种类型的结果：

| yield type | 含义 |
|---|---|
| `message` | Hook 产生的进度/附件消息 |
| `hookPermissionResult` | Hook 的权限决策（allow/deny/ask） |
| `hookUpdatedInput` | Hook 修改了输入但不做权限决策 |
| `preventContinuation` | Hook 要求停止后续执行 |
| `additionalContext` | Hook 提供额外上下文 |
| `stop` | 终止迭代（abort 或错误） |

#### 权限决策解析：resolveHookPermissionDecision

```
src/services/tools/toolHooks.ts:332 — resolveHookPermissionDecision()
```

这个函数是 Hook 与权限系统的桥梁，封装了一个关键不变量：

**Hook 的 `allow` 不能绕过 settings.json 中的 deny/ask 规则**

```
hook allow → 检查是否需要交互 → 检查规则 (checkRuleBasedPermissions) →
  规则 null → 放行
  规则 deny → 覆盖 hook 的 allow
  规则 ask → 弹出对话框
hook deny → 直接拒绝
hook ask → 正常权限流程（带 hook 的消息）
```

---

## 数据流图

### 工具执行完整流程

```
                    Model Response
                         │
                    tool_use block
                         │
                         ▼
                ┌─── runToolUse ───┐
                │                   │
                │  findToolByName   │
                │  (or alias)       │
                │                   │
                └────────┬──────────┘
                         │
                         ▼
          ┌── checkPermissionsAndCallTool ──┐
          │                                  │
          │  1. Zod Schema Validation       │
          │     ↓ fail → InputValidationError│
          │                                  │
          │  2. tool.validateInput()         │
          │     ↓ fail → validation error    │
          │                                  │
          │  3. Bash Classifier (speculative)│
          │     (runs in parallel with hooks)│
          │                                  │
          │  4. PreToolUse Hooks             │
          │     ↓ deny → stop               │
          │     ↓ allow → skip dialog        │
          │     ↓ ask → show dialog          │
          │                                  │
          │  5. Permission Decision          │
          │     canUseTool() / hasPermissions│
          │     ↓ deny → error message       │
          │     ↓ allow → proceed            │
          │                                  │
          │  6. tool.call()                  │
          │     ↓ error → PostToolUseFailure │
          │     ↓ success → PostToolUse      │
          │                                  │
          │  7. PostToolUse Hooks            │
          │     (modify output, add context) │
          │                                  │
          └──────────────┬───────────────────┘
                         │
                         ▼
                   tool_result message
                         │
                         ▼
                    Back to Model
```

### 并发执行流程

```
  Model Response (多个 tool_use)
         │
         ▼
  StreamingToolExecutor.addTool()
         │
    ┌────┼────┐
    ▼    ▼    ▼
  ToolA ToolB ToolC
  (safe)(safe)(unsafe)
    │    │    │
    ▼    ▼    │
  执行  执行  │ ← 等待 unsafe 工具
    │    │    │
    ▼    ▼    ▼
  完成  完成  执行
    │    │    │
    ▼    ▼    ▼
  按顺序 yield 结果
```

---

## 关键代码

### 1. 输入校验的双重防护 (toolExecution.ts:615-733)

```typescript
// 第一层：Zod schema 校验（类型安全）
const parsedInput = tool.inputSchema.safeParse(input)
if (!parsedInput.success) {
  // 返回 InputValidationError
}

// 第二层：工具自定义校验（语义安全）
const isValidCall = await tool.validateInput?.(parsedInput.data, toolUseContext)
if (isValidCall?.result === false) {
  // 返回自定义错误消息
}
```

### 2. 沙箱决策 (shouldUseSandbox.ts)

```typescript
// src/tools/BashTool/shouldUseSandbox.ts:130
export function shouldUseSandbox(input: Partial<SandboxInput>): boolean {
  // 1. 沙箱是否全局启用
  if (!SandboxManager.isSandboxingEnabled()) return false

  // 2. 用户是否显式禁用沙箱
  if (input.dangerouslyDisableSandbox && SandboxManager.areUnsandboxedCommandsAllowed())
    return false

  // 3. 命令是否在排除列表中
  if (containsExcludedCommand(input.command)) return false

  return true
}
```

`containsExcludedCommand()` 的匹配逻辑：
- 将复合命令（`&&` 分隔）拆分为子命令
- 对每个子命令进行不动点迭代：去除环境变量前缀 → 去除安全包装器 → 生成所有候选
- 对每个候选匹配 prefix/exact/wildcard 三种规则模式

### 3. 沙箱配置转换 (sandbox-adapter.ts:172)

`convertToSandboxRuntimeConfig()` 将 Claude Code 的设置转换为 sandbox-runtime 的配置：

- **network** — 从 WebFetch 权限规则和 `sandbox.network` 配置提取 allowedDomains/deniedDomains
- **filesystem** — 从 Edit/Read 权限规则和 `sandbox.filesystem` 配置提取 allowWrite/denyWrite/denyRead
- **安全防护** — 始终拒绝写入 `settings.json`、`.claude/skills` 等关键文件
- **Git 裸仓库防护** — 阻止在 cwd 根目录创建伪造的 Git 裸仓库文件（HEAD/objects/refs）

### 4. 错误分类 (toolExecution.ts:150)

`classifyToolError()` 将工具执行错误分类为遥测安全的字符串：

```typescript
export function classifyToolError(error: unknown): string {
  if (error instanceof TelemetrySafeError) return error.telemetryMessage
  if (error instanceof Error) {
    const errnoCode = getErrnoCode(error)  // ENOENT, EACCES 等
    if (typeof errnoCode === 'string') return `Error:${errnoCode}`
    if (error.name && error.name !== 'Error' && error.name.length > 3)
      return error.name  // ShellError, ImageSizeError 等
    return 'Error'
  }
  return 'UnknownError'
}
```

### 5. PostToolUse Hook 的 MCP 工具输出修改 (toolHooks.ts:146)

```typescript
// 如果 hook 返回了 updatedMCPToolOutput，且这是 MCP 工具，则更新输出
if (result.updatedMCPToolOutput && isMcpTool(tool)) {
  toolOutput = result.updatedMCPToolOutput as Output
  yield { updatedMCPToolOutput: toolOutput }
}
```

这使得 PostToolUse Hook 可以在结果返回给模型之前修改 MCP 工具的输出。

---

## 练习

### 练习 1：追踪一次 Bash 工具调用

目标：理解从模型发出 `Bash(command: "ls -la")` 到返回结果的完整路径。

步骤：
1. 从 `runToolUse()` (toolExecution.ts:337) 开始
2. 追踪到 `checkPermissionsAndCallTool()` (toolExecution.ts:599)
3. 找到 Bash 分类器预启动的位置 (约 L740)
4. 找到 `tool.call()` 的调用点 (约 L1207)
5. 查看 BashTool 的 `call()` 方法如何使用沙箱

思考题：为什么 Bash 分类器要"投机性"地提前启动，而不是等权限检查时再启动？（答案见上方"为什么 Bash 分类器要'投机性'地提前启动？"）

### 练习 2：分析并发执行场景

目标：理解 StreamingToolExecutor 的并发控制逻辑。

场景：模型同时发出三个 tool_use：
- `Read(file_path="a.ts")` — isConcurrencySafe = true
- `Bash(command="npm test")` — isConcurrencySafe = false
- `Read(file_path="b.ts")` — isConcurrencySafe = true

步骤：
1. 阅读 `addTool()` 方法，理解 `isConcurrencySafe` 的判断
2. 阅读 `canExecuteTool()` 方法，理解并发条件
3. 阅读 `executeTool()` 中的错误传播逻辑
4. 如果 `npm test` 失败，其他两个工具会怎样？

思考题：为什么只有 Bash 错误会触发兄弟取消，而 Read/Write 错误不会？

### 练习 3：Hook 权限决策的优先级

目标：理解 Hook 和规则系统的交互。

阅读 `resolveHookPermissionDecision()` (toolHooks.ts:332)，回答：

1. 如果 Hook 返回 `allow`，但 settings.json 中有 deny 规则，最终结果是什么？
2. 如果 Hook 返回 `allow` 且提供了 `updatedInput`，`requiresUserInteraction` 的工具有什么特殊行为？
3. 如果 Hook 返回 `ask`，权限对话框会显示什么消息？

---

## 下一篇

[下一章：权限系统 (Permission System) →](05-permission-system.md)
