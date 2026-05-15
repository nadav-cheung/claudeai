# 第 16 章：权限系统——分层规则引擎

> 源码验证日期：2026-05-15，基于 commit `0d81bb6`

---

本章是第 11 章的展开版。第 11 章聚焦最常见的 3 种权限模式，本章覆盖全部 7 种权限模式和安全纵深防御体系。

---

## 源码入口

```
src/types/permissions.ts                    — 权限类型定义
src/utils/permissions/permissions.ts        — 主检查逻辑
src/utils/permissions/permissionSetup.ts    — 模式初始化和切换
src/utils/permissions/PermissionMode.ts     — 模式配置
src/utils/permissions/permissionExplainer.ts — 风险评估
src/utils/permissions/PermissionUpdate.ts   — 规则持久化
src/utils/permissions/permissionsLoader.ts  — 规则加载
src/utils/permissions/classifierDecision.ts — auto 模式决策
src/utils/permissions/denialTracking.ts     — 拒绝追踪
src/tools/BashTool/bashPermissions.ts       — Bash 专用权限
src/tools/BashTool/readOnlyValidation.ts    — 只读命令检测
```

---

## 逐行阅读

### 16.1 全部 7 种权限模式

| 模式 | 外部可用? | 行为 | 启用方式 |
|------|----------|------|---------|
| `default` | 是 | 未被规则覆盖的每个工具调用都需要用户确认 | 默认模式 |
| `plan` | 是 | 计划模式：工具只读（除非 auto 模式叠加） | `/plan` 命令 |
| `acceptEdits` | 是 | 自动接受工作目录内的文件读写 | `--permission-mode acceptEdits` |
| `bypassPermissions` | 是 | 跳过所有权限检查（除安全关键） | `--dangerously-skip-permissions` |
| `dontAsk` | 是 | 静默拒绝任何需要提示的请求 | 内部/SDK 用 |
| `auto` | Ant 内部 | AI 分类器自动决定允许/拒绝 | 功能标志 |

```typescript
// → src/utils/permissions/PermissionMode.ts:42-91（简化版）
const PERMISSION_MODE_CONFIG = {
  default: { title: 'Default', symbol: '!', color: 'yellow' },
  plan: { title: 'Plan', symbol: '?', color: 'blue' },
  acceptEdits: { title: 'Auto-accept Edits', symbol: '✓', color: 'green' },
  bypassPermissions: { title: 'Bypass Permissions', symbol: '⚡', color: 'red' },
  dontAsk: { title: 'Dont Ask', symbol: '✗', color: 'gray' },
  auto: { title: 'Auto (YOLO)', symbol: '→', color: 'cyan' },
}
```

### 16.2 模式转换

模式不是静态的——用户可以在会话中切换：

```typescript
// → src/utils/permissions/permissionSetup.ts:597（简化版）
function transitionPermissionMode(from, to) {
  // plan 模式进入：剥离危险规则
  if (to === 'plan') {
    strippedDangerousRules = extractDangerousRules(currentRules)
    return { mode: 'plan', strippedDangerousRules }
  }

  // plan 模式退出：恢复危险规则
  if (from === 'plan' && to === 'default') {
    restoreDangerousRules(strippedDangerousRules)
  }

  // auto 模式激活：需要 GrowthBook 功能标志
  if (to === 'auto' && !isAutoModeAllowed()) {
    throw new Error('Auto mode not available')
  }
}
```

plan 模式进入时会临时剥离危险权限规则（如 `Bash(npm publish:*)`），退出时恢复。

### 16.3 分层规则检查的完整流程

第 11 章展示了简化的管线。这里是完整版本：

```typescript
// → src/utils/permissions/permissions.ts:1158（完整步骤）

// Step 1: 规则检查（模式无关）
// 1a. 工具级 deny
// 1b. 工具级 ask
// 1c. 工具自定义 checkPermissions()
// 1d. 工具返回 deny
// 1e. 需要用户交互的工具
// 1f. 内容级 ask 规则（bypass-immune）
// 1g. 安全路径检查（bypass-immune）
//     - .git/, .claude/, .vscode/
//     - shell 配置文件（.bashrc, .zshrc 等）
//     - 即使 bypass 模式也必须提示

// Step 2: 模式决策
// 2a. bypass 模式：允许所有通过 Step 1 的
// 2b. 工具级 allow 规则

// Step 3: 回退
// 3a. passthrough → ask
// 3b. dontAsk 模式：ask → deny
// 3c. auto 模式：ask → AI 分类器
//     - acceptEdits 快速路径
//     - 安全工具白名单
//     - 完整 Opus 分类器
// 3d. default 模式：显示权限提示
```

### 16.4 安全路径检查：bypass-immune

某些路径即使 bypass 模式也必须提示：

```typescript
// → src/utils/permissions/permissions.ts:1256（简化版）
// 以下路径的修改需要用户确认，即使 --dangerously-skip-permissions
// .git/       — Git 仓库元数据
// .claude/    — Claude Code 配置
// .vscode/    — IDE 配置
// .bashrc, .zshrc, .profile 等 — Shell 配置
// SSH 配置文件
```

这些是安全关键路径——恶意工具调用修改它们可能导致持久性后门。

### 16.5 PermissionDecisionReason：追踪决策原因

```typescript
// → src/types/permissions.ts:271-324（简化版）
type PermissionDecisionReason =
  | { type: 'rule', source: PermissionRuleSource, rule: string }
  | { type: 'mode', mode: PermissionMode }
  | { type: 'permissionPromptTool' }
  | { type: 'hook', hookName: string }
  | { type: 'asyncAgent' }
  | { type: 'sandboxOverride' }
  | { type: 'classifier', confidence: number }
  | { type: 'workingDir' }
  | { type: 'safetyCheck', path: string }
  | { type: 'other', detail: string }
```

每个权限决策都附带原因——这对调试和遥测非常重要。你可以在 UI 中看到"这条规则来自 projectSettings"或"被 AI 分类器允许"。

### 16.6 Auto 模式的三级快速路径

```typescript
// → src/utils/permissions/permissions.ts:522（简化版）
if (mode === 'auto' && decision.behavior === 'ask') {
  // 快速路径 1：acceptEdits 兼容
  // 如果 acceptEdits 模式下会允许，直接允许（不调用 AI）
  if (wouldBeAllowedInAcceptEdits(tool, input, context)) {
    return { behavior: 'allow', reason: { type: 'classifier', confidence: 1.0 } }
  }

  // 快速路径 2：安全工具白名单
  // → src/utils/permissions/classifierDecision.ts:56
  // Read, Grep, Glob, LSP, ToolSearch, ListMcpResources, ReadMcpResource,
  // TodoWrite, TaskCreate/Get/Update/List/Stop/Output, AskUserQuestion,
  // EnterPlanMode, ExitPlanMode, TeamCreate, TeamDelete, SendMessage, Sleep
  if (SAFE_YOLO_ALLOWLISTED_TOOLS.includes(tool.name)) {
    return { behavior: 'allow' }
  }

  // 快速路径 3：完整 AI 分类器
  // 调用 Opus 模型评估完整对话上下文 + 工具输入
  const classification = await classifyYoloAction({
    transcript: messages,
    action: { toolName: tool.name, input },
    claudeMd: getCachedClaudeMdContent(),
  })
  return classification.decision
}
```

大多数工具调用走快速路径 1 或 2——只有写操作（Bash、Write、Edit）才需要调用 AI 分类器。

### 16.7 拒绝追踪：防止分类器退化

```typescript
// → src/utils/permissions/denialTracking.ts（简化版）
const limits = {
  maxConsecutive: 3,   // 连续拒绝上限
  maxTotal: 20,        // 总拒绝上限
}

// 如果超过上限，auto 模式退回到手动提示
// 防止分类器持续做出错误决策
```

### 16.8 权限提示：建议和风险评估

当权限系统决定 `ask`（提示用户）时，UI 显示：

1. **工具描述**：工具在做什么
2. **风险评估**：LOW / MEDIUM / HIGH（由 `permissionExplainer.ts` 生成）
3. **建议操作**：用户可以点击的快捷按钮

```typescript
// → src/utils/permissions/permissionExplainer.ts（简化版）
// 调用模型生成风险评估
// 输入：工具名 + 输入 + 对话上下文
// 输出：{ risk: 'LOW' | 'MEDIUM' | 'HIGH', explanation: string }
```

建议操作：

```typescript
// → src/utils/permissions/PermissionUpdate.ts:349（简化版）
// Bash 命令建议：
//   - 精确允许：Bash(npm install)
//   - 前缀允许：Bash(npm install:*)
// 文件访问建议：
//   - 路径模式：Read(//path/**)
```

### 16.9 规则加载：8 种来源

```typescript
// → src/utils/permissions/permissionsLoader.ts（简化版）
function loadAllPermissionRulesFromDisk(): PermissionRules {
  // 按优先级从高到低：
  // 1. policySettings   — 企业管理（不可覆盖）
  // 2. flagSettings     — 功能标志覆盖
  // 3. userSettings     — ~/.claude/settings.json
  // 4. projectSettings  — .claude/settings.json
  // 5. localSettings    — .claude/settings.local.json
  // 6. cliArg           — --allowedTools / --disallowedTools
  // 7. command          — 程序化规则
  // 8. session          — 内存中，当前会话

  // 当 allowManagedPermissionRulesOnly 启用时，
  // 只有 policySettings 规则生效
}
```

### 16.10 Bash 规则匹配：三种模式

```typescript
// → src/tools/BashTool/bashPermissions.ts:778（简化版）
// Bash 规则有三种匹配模式：

// 1. 精确匹配：Bash(npm install)
//    命令字符串完全相等

// 2. 前缀匹配：Bash(npm:*)
//    命令以 "npm " 开头

// 3. 通配符匹配：Bash(npm run *)
//    glob 风格的通配符

// 安全特性：
// - stripSafeWrappers(): 在匹配前剥离 timeout/nice/nohup 包装
// - stripAllLeadingEnvVars(): 对 deny/ask 规则剥离环境变量
// - 复合命令守卫：前缀/通配符规则不匹配复合命令（&&/||/;）
```

### 16.11 权限永不跨会话恢复

这个安全属性值得再次强调：

- session 级别的权限规则存在内存中
- `resume` 恢复对话时不恢复 session 规则
- 用户需要重新确认工具调用
- 这是防止权限泄漏的核心设计

---

## 调试实践

| 位置 | 看什么 |
|------|--------|
| `permissions.ts:473` | `hasPermissionsToUseTool`——主入口 |
| `permissions.ts:1158` | `hasPermissionsToUseToolInner`——完整 12 步 |
| `PermissionMode.ts:42` | 模式配置 |
| `permissionSetup.ts:597` | 模式转换 |
| `classifierDecision.ts:56` | 安全工具白名单 |
| `permissionsLoader.ts` | 8 种规则来源加载 |
| `denialTracking.ts` | 拒绝追踪和退化 |

---

## 试一试

### 修改 1：追踪权限决策完整路径

```typescript
// 在 hasPermissionsToUseToolInner 的每个步骤加：
console.log('[DEBUG] Step 1a:', tool.name, 'deny:', !!denyRule)
console.log('[DEBUG] Step 1c:', tool.name, 'toolResult:', toolResult.behavior)
// ... 等等
```

发送一个需要权限的工具调用，观察走了哪条路径。

### 修改 2：测试不同权限模式

```bash
claude --permission-mode acceptEdits    # 自动接受编辑
claude --dangerously-skip-permissions   # 跳过权限（需要确认）
claude                                  # 默认模式
```

观察不同模式下同一个工具调用（如 `Write`）的行为差异。

---

## 检查点

- **7 种权限模式**：default、plan、acceptEdits、bypassPermissions、dontAsk、auto（+ 内部扩展）
- **模式转换**：plan 进入/退出时剥离/恢复危险规则
- **分层检查 12 步**：规则优先（deny > ask > allow）→ 模式决策 → 回退处理
- **安全路径检查**：.git/、.claude/、shell 配置文件——bypass-immune
- **PermissionDecisionReason**：10 种决策原因标签，支持调试和遥测
- **Auto 模式三级快速路径**：acceptEdits 兼容 → 安全工具白名单 → Opus 分类器
- **拒绝追踪**：连续 3 次或总计 20 次拒绝后退回手动提示
- **8 种规则来源**：policySettings（不可覆盖）> ... > session（仅内存）
- **Bash 规则匹配**：精确、前缀、通配符三种模式
- **跨会话安全**：权限永不跨会话恢复

**下一站**：第 17 章追踪 Hook 系统——27 个 Hook 事件、4 种执行类型、工具调用的拦截与修改。
