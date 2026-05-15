# 第 32 章：为什么权限系统是分层的

> 源码验证日期：2026-05-15，基于 commit `0d81bb6`

---

## 决策回顾

Claude Code 的权限系统不是简单的 `allow/deny` 布尔值——而是 8 种规则来源、7 种权限模式、12 步分层检查管线。

源码证据：
- `src/utils/permissions/permissions.ts:1158`——`hasPermissionsToUseToolInner()` 12 步管线
- `src/types/permissions.ts:54-63`——8 种 `PermissionRuleSource`
- `src/tools/BashTool/bashPermissions.ts:1663`——Bash 的 AST 解析 + 10 步安全检查

---

## 被否方案

### 方案 A：单一布尔权限

```typescript
// 被 否 决 的 方 案
if (mode === 'bypass') return 'allow'
if (tool.name === 'Bash') return 'deny'
return 'ask'
```

**问题**：无法表达"允许 `npm install` 但不允许 `npm publish`"这样的细粒度控制。

### 方案 B：纯 RBAC（基于角色的访问控制）

```typescript
// 被 否 决 的 方 案
if (user.role === 'admin') return 'allow'
if (user.role === 'developer') return 'ask'
```

**问题**：Claude Code 是单用户应用——不需要多角色。权限粒度在工具+输入级别，不在角色级别。

### 方案 C：外部策略服务器

```typescript
// 被 否 决 的 方 案
const decision = await fetch('https://policy-server.local/check', { body: toolInput })
```

**问题**：每次工具调用增加网络延迟——影响用户体验。

---

## 后果分析

### 好处

1. **细粒度控制**：`Bash(npm install:*)` 允许安装但拒绝发布
2. **deny 优先于 allow**：安全关键检查（`.git/`、shell 配置）即使 bypass 模式也必须提示
3. **多种来源**：企业策略、用户设置、项目设置、CLI 参数、会话——灵活组合
4. **渐进式信任**：default → acceptEdits → auto——用户逐步放手
5. **Bash 深度分析**：AST 解析 + 语义检查 + 沙盒 + 分类器——多层防御

### 麻烦

1. **复杂度高**：12 步管线，开发者难以预测结果
2. **调试困难**：工具被 deny 但不知道是哪条规则——需要 PermissionDecisionReason
3. **性能开销**：auto 模式的 AI 分类器每次调用 Opus 模型
4. **Bash 解析的边界**：`too-complex` 命令回退到 `ask`——复杂命令无法精确控制

---

## 横向对比

| 工具 | 权限模型 | 特点 |
|------|---------|------|
| **Claude Code** | 分层规则引擎 + 7 种模式 | 细粒度、多来源、deny 优先 |
| **Aider** | 基本无权限控制 | 信任用户 |
| **Cursor** | 简单 allow/deny | GUI 选择 |
| **GitHub Copilot CLI** | 无权限控制 | 只读建议 |

---

## 你的判断

1. 7 种权限模式是否应该简化为 3-4 种？哪些可以合并？
2. auto 模式的 AI 分类器是否值得隐藏的 Opus 调用成本？
3. 权限永不跨会话恢复的设计——用户体验 vs 安全的平衡是否合适？

---

**设计原则标签**：人类决策权——deny-first + graduated trust + externalized policy。分层规则引擎让权限决策可审计、可覆盖、可恢复。
