---
title: 附录D — 核心源码路径
description: Claude Code 核心源码文件路径映射与关键数据结构速查
tags: [附录, 源码路径, 数据结构, 架构]
date: 2026-05-10
---

# 附录D — 核心源码路径

> 本附录提供 Claude Code 源码的文件路径映射与核心数据结构速查。各章节已内联展示接口签名，此处仅做路径索引与类型速查。

---

## 1. 文件路径映射

### 工具系统

| 功能 | 源码路径 |
|------|----------|
| 工具泛型接口 | `src/Tool.ts` |
| 工具注册表 | `src/tools.ts` |
| 工具执行引擎 | `src/services/tools/toolExecution.ts` |

### 权限系统

| 功能 | 源码路径 |
|------|----------|
| 权限模式与规则引擎 | `src/utils/permissions/permissions.ts` |
| 拒绝追踪器 | `src/utils/permissions/denialTracking.ts` |

### 上下文与会话

| 功能 | 源码路径 |
|------|----------|
| 消息状态管理 | `src/state/messages.ts` |
| 上下文压缩策略 | `src/services/compact/strategies.ts` |
| 会话创建与恢复 | `src/state/sessions.ts` |

### API 通信

| 功能 | 源码路径 |
|------|----------|
| 消息流（Streaming） | `src/services/api/claude.ts` |
| 重试逻辑 | `src/services/api/withRetry.ts` |
| OAuth PKCE 认证 | `src/services/oauth/client.ts` |

### MCP 协议

| 功能 | 源码路径 |
|------|----------|
| MCP 连接管理 | `src/services/mcp/connection.ts` |

### Agent 系统

| 功能 | 源码路径 |
|------|----------|
| Agent 任务类型定义 | `src/services/agents/types.ts` |

### Skills 与 Plugin

| 功能 | 源码路径 |
|------|----------|
| Skill 目录加载 | `src/skills/loadSkillsDir.ts` |
| 内置 Skill 注册 | `src/skills/bundledSkills.ts` |
| Plugin 生命周期操作 | `src/services/plugins/pluginOperations.ts` |
| Plugin Hook 加载 | `src/utils/plugins/loadPluginHooks.ts` |

---

## 2. 核心数据结构速查

### ContentBlock

AI 回复中每个内容块的联合类型：

```typescript
type ContentBlock =
  | { type: 'text'; text: string }
  | { type: 'tool_use'; id: string; name: string; input: Record<string, unknown> }
  | { type: 'tool_result'; tool_use_id: string; content: string }
```

### ToolCall

一次工具调用的完整描述：

```typescript
interface ToolCall {
  id: string;
  type: 'tool_use';
  name: string;
  input: Record<string, unknown>;
}
```

### Usage

单次 API 调用的 token 用量统计：

```typescript
interface Usage {
  inputTokens: number;
  outputTokens: number;
  totalTokens: number;
}
```

### PermissionMode

权限检查的行为模式枚举：

```typescript
enum PermissionMode {
  BYPASS = 'bypass',   // 完全跳过
  FAIL = 'fail',       // 无权限直接失败
  PROMPT = 'prompt',   // 询问用户
  APPROVE = 'approve', // 自动批准
}
```

### CompactionStrategyType

上下文压缩策略选项：

```typescript
enum CompactionStrategyType {
  FULL = 'full',
  MICRO = 'micro',
  SESSION_MEMORY = 'session_memory',
}
```

---

`★ Insight ─────────────────────────────────────`
源码路径随版本迭代可能变动。当路径失效时，以模块名（如 `toolExecution`、`denialTracking`）为关键词全局搜索即可定位。
`─────────────────────────────────────────────────`
