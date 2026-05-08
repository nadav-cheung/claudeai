# 05 - 权限系统 (Permission System)

> **本章目标**：理解 Claude Code 的多层权限架构，包括权限模式 (Permission Mode)、规则系统 (Rule System)、分类器 (Classifier)、权限 UI 组件、以及拒绝追踪 (Denial Tracking) 机制。掌握从模型发出工具调用到最终权限决策的完整链路。

---

## 核心概念

### 1. 权限模式 (Permission Modes)

Claude Code 支持多种权限模式，控制工具调用时是否需要用户确认：

| 模式 | 说明 | 行为 |
|---|---|---|
| `default` | 默认模式 | 每次工具调用都需要用户确认（除非有 allow 规则） |
| `plan` | 计划模式 | 只允许只读操作，禁止文件编辑和命令执行 |
| `acceptEdits` | 接受编辑 | 自动允许文件编辑操作 |
| `auto` | 自动模式 | AI 分类器自动判断命令安全性 |
| `bypassPermissions` | 绕过权限 | 跳过所有权限检查（危险） |
| `dontAsk` | 不再询问 | 类似 auto，使用分类器判断 |

### 2. 规则系统 (Rule System)

权限规则来源按优先级排列：
- `cliArg` — 命令行参数
- `flagSettings` — 标志设置
- `policySettings` — 策略设置（管理员级别）
- `projectSettings` — 项目级 `.claude/settings.json`
- `userSettings` — 用户级 `~/.claude/settings.json`
- `localSettings` — 本地 `settings.local.json`
- `session` — 会话级临时规则（用户选择"仅本次允许"）

### 3. 权限决策流程

```
模型发出 tool_use → 检查规则 → 检查分类器 → (可选) 弹出对话框 → 决策
```

核心文件：
- `src/hooks/useCanUseTool.tsx` — React hook，权限检查的入口
- `src/utils/permissions/permissions.ts` — 权限引擎核心
- `src/utils/permissions/PermissionMode.ts` — 权限模式定义
- `src/utils/permissions/PermissionResult.ts` — 权限结果类型
- `src/utils/permissions/permissionSetup.ts` — 权限初始化

---

## 源码导览

### useCanUseTool Hook (useCanUseTool.tsx)

这是权限系统的入口 hook，返回一个 `CanUseToolFn` 函数。整个权限检查流程如下：

```
useCanUseTool(setToolUseConfirmQueue, setToolPermissionContext)
  │
  ▼
CanUseToolFn(tool, input, toolUseContext, ...)
  │
  ├─ createPermissionContext() — 创建权限上下文
  │
  ├─ hasPermissionsToUseTool() — 非交互式权限检查
  │   │
  │   ├─ 返回 allow → 直接放行
  │   ├─ 返回 deny → 直接拒绝
  │   └─ 返回 ask → 需要交互确认
  │
  └─ ask 分支（需要交互确认）：
      │
      ├─ handleCoordinatorPermission() — 协调器模式自动检查
      │   └─ 返回决策（如果自动检查解决了）
      │
      ├─ handleSwarmWorkerPermission() — swarm worker 权限转发
      │   └─ 返回决策（如果 worker 层解决了）
      │
      ├─ Speculative Classifier — 投机性分类器检查
      │   └─ 2 秒内高置信度匹配 → 自动放行
      │
      └─ handleInteractivePermission() — 显示交互式对话框
```

### 权限引擎：hasPermissionsToUseTool (permissions.ts)

```
src/utils/permissions/permissions.ts
```

这个函数实现了完整的规则匹配和分类器检查：

1. **规则匹配** — `checkRuleBasedPermissions()` 遍历所有来源的 allow/deny 规则
2. **Bash 分类器** — 如果启用 `BASH_CLASSIFIER` feature flag，异步调用 AI 分类器
3. **Auto 模式分类器** — 如果启用 `TRANSCRIPT_CLASSIFIER` feature flag，使用 yolo 分类器
4. **沙箱自动放行** — 如果命令在沙箱中运行且 `autoAllowBashIfSandboxed` 为 true
5. **拒绝追踪** — 连续拒绝超过阈值时回退到提示模式

### 权限模式配置 (PermissionMode.ts)

```typescript
// src/utils/permissions/PermissionMode.ts
const PERMISSION_MODE_CONFIG = {
  default:     { title: 'Default',           color: 'text' },
  plan:        { title: 'Plan Mode',          color: 'planMode', symbol: PAUSE_ICON },
  acceptEdits: { title: 'Accept edits',       color: 'autoAccept' },
  auto:        { title: 'Auto mode',          color: 'warning' },      // ant-only
  bypassPermissions: { title: 'Bypass Permissions', color: 'error' },
  dontAsk:     { title: "Don't Ask",          color: 'error' },
}
```

关键点：
- `auto` 模式是内部(ant)专用，不暴露给外部用户
- `bypassPermissions` 和 `dontAsk` 标记为 `error` 颜色，表示高风险
- `plan` 模式使用暂停图标，表示只读限制

### 权限初始化 (permissionSetup.ts)

```
src/utils/permissions/permissionSetup.ts
```

这个文件负责在会话启动时初始化权限上下文：

1. **加载规则** — `loadAllPermissionRulesFromDisk()` 从所有设置源读取权限规则
2. **确定模式** — 从命令行参数、设置文件、feature flag 确定权限模式
3. **应用规则** — `applyPermissionRulesToPermissionContext()` 将规则应用到权限上下文
4. **Auto 模式设置** — 如果启用了 auto 模式，配置分类器和拒绝追踪

### 权限 UI 组件

```
src/components/permissions/
├── PermissionRequest.tsx        — 权限请求主组件
├── PermissionPrompt.tsx         — 权限提示 UI
├── PermissionDialog.tsx         — 权限对话框
├── PermissionExplanation.tsx    — 权限解释文本
├── PermissionRuleExplanation.tsx — 规则说明
├── BashPermissionRequest/       — Bash 命令权限请求
├── FileEditPermissionRequest/   — 文件编辑权限请求
├── FileWritePermissionRequest/  — 文件写入权限请求
├── SandboxPermissionRequest.tsx — 沙箱权限请求
├── SedEditPermissionRequest/    — sed 编辑权限请求
├── WebFetchPermissionRequest/   — Web 请求权限请求
└── ...
```

每种工具类型有专门的权限请求组件，显示不同的确认信息。例如 Bash 权限请求会显示命令内容，文件编辑权限请求会显示 diff。

---

## 数据流图

### 权限检查完整流程

```
                 Tool Execution
                      │
                      ▼
          ┌─── canUseTool() ───┐
          │                     │
          │  createPermission   │
          │  Context()          │
          │                     │
          └────────┬────────────┘
                   │
                   ▼
      ┌── hasPermissionsToUseTool() ──┐
      │                                │
      │  ┌──────────────────────┐      │
      │  │ 1. checkRuleBased    │      │
      │  │    Permissions()     │      │
      │  │   ├─ deny 规则匹配   │      │
      │  │   │   → return deny  │      │
      │  │   ├─ allow 规则匹配  │      │
      │  │   │   → return allow │      │
      │  │   └─ 无匹配          │      │
      │  │       → continue     │      │
      │  └──────────────────────┘      │
      │                                │
      │  ┌──────────────────────┐      │
      │  │ 2. Bash Classifier   │      │
      │  │   (if BASH_CLASSIFIER│      │
      │  │    feature enabled)  │      │
      │  │   ├─ 高置信度拒绝    │      │
      │  │   │   → return deny  │      │
      │  │   ├─ 高置信度允许    │      │
      │  │   │   → return allow │      │
      │  │   └─ 不确定          │      │
      │  │       → return ask   │      │
      │  └──────────────────────┘      │
      │                                │
      │  ┌──────────────────────┐      │
      │  │ 3. Auto Mode         │      │
      │  │    Classifier        │      │
      │  │   (if TRANSCRIPT_    │      │
      │  │    CLASSIFIER on)    │      │
      │  │   → 使用 yolo 分类器 │      │
      │  └──────────────────────┘      │
      │                                │
      │  ┌──────────────────────┐      │
      │  │ 4. Sandbox Auto-Allow│      │
      │  │   (命令在沙箱中运行) │      │
      │  │   → return allow     │      │
      │  └──────────────────────┘      │
      │                                │
      │  默认 → return ask             │
      └────────────┬───────────────────┘
                   │
           ┌───────┼───────┐
           ▼       ▼       ▼
        allow    deny     ask
           │       │       │
           │       │       ▼
           │       │   ┌────────────────┐
           │       │   │ Interactive    │
           │       │   │ Dialog         │
           │       │   │ ├─ Allow Once  │
           │       │   │ ├─ Allow Always│
           │       │   │ └─ Deny        │
           │       │   └────────────────┘
           │       │       │
           ▼       ▼       ▼
       PermissionDecision
           │
           ▼
       Back to Tool Execution
```

### 规则匹配优先级

```
高优先级
  │
  ├─ cliArg (命令行参数)
  ├─ flagSettings (标志设置)
  ├─ policySettings (管理员策略)
  ├─ projectSettings (.claude/settings.json)
  ├─ userSettings (~/.claude/settings.json)
  ├─ localSettings (settings.local.json)
  │
  └─ session (会话临时规则)
低优先级

deny 规则优先于 allow 规则
同名工具的规则，高优先级源覆盖低优先级源
```

---

## 关键代码

### 1. 权限结果类型 (PermissionResult.ts)

```typescript
// src/utils/permissions/PermissionResult.ts
// 类型实际定义在 src/types/permissions.ts

type PermissionResult = {
  behavior: 'allow' | 'deny' | 'ask'
  message?: string
  updatedInput?: Record<string, unknown>
  decisionReason?: PermissionDecisionReason
  // ...
}

type PermissionDecisionReason =
  | { type: 'rule', rule: { source: string, ... } }
  | { type: 'classifier', classifier: 'bash_allow' | 'auto-mode', ... }
  | { type: 'hook', hookName: string, ... }
  | { type: 'mode' }
  | { type: 'sandboxOverride' }
  | { type: 'other' }
  // ...
```

`decisionReason` 是遥测和调试的关键——它记录了决策是如何做出的。

### 2. useCanUseTool 的分类器投机检查 (useCanUseTool.tsx:126-158)

```typescript
// 投机性分类器检查：给分类器 2 秒时间
const speculativePromise = peekSpeculativeClassifierCheck(command)
if (speculativePromise) {
  const raceResult = await Promise.race([
    speculativePromise.then(r => ({ type: 'result', result: r })),
    new Promise(res => setTimeout(res, 2000, { type: 'timeout' })),
  ])

  if (raceResult.type === 'result' &&
      raceResult.result.matches &&
      raceResult.result.confidence === 'high') {
    // 高置信度匹配 → 自动放行，跳过对话框
    resolve(ctx.buildAllow(input, { decisionReason: ... }))
    return
  }
}
// 超时或低置信度 → 显示对话框
handleInteractivePermission(...)
```

这体现了"grace period"设计：给分类器一个短暂窗口来做出快速决策，避免弹出不必要的对话框。

### 3. 拒绝追踪 (denialTracking.ts)

```typescript
// src/utils/permissions/denialTracking.ts
export const DENIAL_LIMITS = {
  maxConsecutive: 3,   // 连续拒绝 3 次
  maxTotal: 20,        // 总共拒绝 20 次
}

export function shouldFallbackToPrompting(state: DenialTrackingState): boolean {
  return (
    state.consecutiveDenials >= DENIAL_LIMITS.maxConsecutive ||
    state.totalDenials >= DENIAL_LIMITS.maxTotal
  )
}
```

当分类器连续拒绝 3 次或总共拒绝 20 次后，自动回退到提示模式——这防止了分类器在不确定情况下无限拒绝。

### 4. Auto 模式状态 (autoModeState.ts)

```typescript
// src/utils/permissions/autoModeState.ts
let autoModeActive = false
let autoModeFlagCli = false
let autoModeCircuitBroken = false  // 熔断器

export function setAutoModeCircuitBroken(broken: boolean): void {
  autoModeCircuitBroken = broken
}
```

Auto 模式有一个"熔断器"机制：当远程配置（GrowthBook）将 `tengu_auto_mode_config.enabled` 设为 `disabled` 时，`autoModeCircuitBroken` 被设为 true，阻止 SDK 或显式请求重新进入 auto 模式。

### 5. Bash 分类器 (bashClassifier.ts)

```typescript
// src/utils/permissions/bashClassifier.ts (stub — 外部构建的占位文件)
// 实际实现使用 AI 模型分类 Bash 命令

export type ClassifierResult = {
  matches: boolean          // 是否匹配规则
  matchedDescription?: string  // 匹配的规则描述
  confidence: 'high' | 'medium' | 'low'  // 置信度
  reason: string            // 分类原因
}

export async function classifyBashCommand(
  command: string,     // 要分类的命令
  cwd: string,         // 当前工作目录
  descriptions: string[],  // prompt 规则描述列表
  behavior: ClassifierBehavior,  // deny/ask/allow
  signal: AbortSignal,
  isNonInteractiveSession: boolean,
): Promise<ClassifierResult>
```

分类器使用 prompt 规则描述（如 "prompt: running npm test commands"）来判断命令是否匹配。这是"分类器权限系统"的核心——用户描述允许/拒绝的命令类型，AI 判断具体命令是否匹配。

### 6. 权限上下文创建 (PermissionContext.ts)

```
src/hooks/toolPermission/PermissionContext.ts
```

`createPermissionContext()` 创建一个上下文对象，封装了：
- `resolveIfAborted()` — 检查请求是否已被取消
- `logDecision()` — 记录权限决策到遥测
- `buildAllow()` — 构建 allow 决策结果
- `cancelAndAbort()` — 取消并中止请求
- `messageId` — 用于日志关联的消息 ID

---

## 练习

### 练习 1：理解权限模式的转换

**类比 Java**：权限模式转换类似于 Spring Security 的 `SecurityFilterChain` 动态切换。

**答案**：

1. **`default` → `plan` 模式**
   - `applyPermissionRulesToPermissionContext()` 设置只读规则
   - 所有写操作（Edit/Write/Bash）被标记为 deny
   - 模型只能执行只读操作

2. **`plan` 模式退出恢复**
   - 从会话状态中读取之前的权限模式
   - 恢复到 `default` 或用户之前设置的模式

3. **`auto` 模式激活条件**
   - SDK 消费者显式请求 `auto` 模式
   - `tengu_auto_mode_config.enabled` 不为 `disabled`
   - 熔断器 `autoModeCircuitBroken` 为 false

### 练习 2：追踪 deny 规则生效路径

**类比 Java**：规则匹配类似于 Spring Security 的 `AccessDecisionVoter` 投票。

**答案**：

1. **规则加载路径**：`loadAllPermissionRulesFromDisk()` → 解析 JSON → 生成 PermissionRule → 按优先级排序

2. **deny 优先于 allow**：deny 规则匹配 → 直接拒绝，allow 规则不被检查

**Java 对比**：
```java
// Spring Security 投票器
public int vote(Authentication auth, Object target, Collection<ConfigAttribute> attrs) {
    for (ConfigAttribute attr : attrs) {
        if ("ROLE_ADMIN".equals(attr.getAttribute())) return ACCESS_GRANTED;
        if ("ROLE_DENY".equals(attr.getAttribute())) return ACCESS_DENIED;  // deny 优先
    }
    return ACCESS_ABSTAIN;
}
```

### 练习 3：分类器权限系统分析

**答案**：

| 方面 | Prompt 描述 | 直接匹配 |
|------|------------|---------|
| 灵活性 | 高（自然语言） | 低（精确匹配） |
| 泛化 | AI 可推断类似命令 | 无推断能力 |
| 误报率 | 可能误判 | 精确但死板 |
| 性能 | 需 AI 调用 | 快速正则 |

**优点**：用户可用"删除文件的命令"描述一类危险操作，AI 理解 `rm -rf`、`git push --force` 等。

**缺点**：依赖 AI 理解能力，可能误判；需额外 AI 调用开销。

### 练习 4：权限 UI 组件分析

**答案**：

1. **`ToolUseConfirm` 字段**：`toolName`, `input`, `toolUseId`, `inputDescription`

2. **Allow Once vs Always**：
   - `Allow Once`：session 临时规则
   - `Allow Always`：持久化到 settings.json

3. **`acceptFeedback`**：记录用户反馈，用于改进分类器

---

## 练习答案速查

| 练习 | 核心答案 |
|------|---------|
| 1 | plan 只读限制，auto 通过 GrowthBook + 熔断器激活 |
| 2 | deny 优先于 allow（安全不变量） |
| 3 | prompt 灵活但有 AI 依赖开销 |
| 4 | Once=session 临时，Always=持久化 |

---

## 权限系统 vs Java Spring Security

| 方面 | Claude Code | Spring Security |
|------|-------------|----------------|
| 规则定义 | JSON + glob 模式 | `hasRole()`, `permitAll()` |
| 匹配方式 | glob/wildcard | Ant 路径 + SpEL |
| 决策者 | 规则 + 分类器 + 用户 | AccessDecisionManager |
| 权限模式 | default/plan/auto/bypass | 无等价物 |
| 熔断器 | autoModeCircuitBroken | CircuitBreaker |

---

## 下一篇

👉 [06-context-and-compact.md](./06-context-and-compact.md) — 上下文管理与压缩
