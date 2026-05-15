# 第 23 章：造一个斜杠命令

> 源码验证日期：2026-05-15，基于 commit `0d81bb6`

本章创建一个 `/metrics` 命令，展示会话用量统计。

---

## 目标

```
用户：/metrics
Claude：显示当前会话统计：
  - Token 使用量：输入 45,230 / 输出 12,450
  - API 调用次数：8
  - 工具调用次数：12（Read 5, Edit 3, Bash 2, Grep 2）
  - 会话持续时间：15m 32s
  - 估算成本：$0.42
```

---

## 步骤 1：创建命令目录

```bash
mkdir -p src/commands/metrics
```

## 步骤 2：选择命令类型

这个命令需要显示实时统计——选择 `local` 类型（非交互式本地命令）。

## 步骤 3：实现命令定义

```typescript
// src/commands/metrics/index.ts（命令注册）

import type { Command } from '../../types/command.js'

const metricsCommand = {
  type: 'local',
  name: 'metrics',
  description: 'Show current session usage metrics',
  isEnabled: () => true,
  load: () => import('./metrics.js'),
} satisfies Command

export default metricsCommand
```

## 步骤 4：实现命令逻辑

```typescript
// src/commands/metrics/metrics.ts（命令实现）

import type { LocalCommandResult } from '../../types/command.js'
import { getSessionId, getTotalCostUSD } from '../../bootstrap/state.js'

export async function call(args, context): Promise<LocalCommandResult> {
  const cost = getTotalCostUSD()
  const sessionId = getSessionId()

  // 从 context 中获取统计信息
  const stats = context.stats ?? {}

  const lines = [
    '=== Session Metrics ===',
    `Session ID: ${sessionId}`,
    `Duration: ${formatDuration(stats.duration)}`,
    `Cost: $${cost.toFixed(4)}`,
    '',
    'Token Usage:',
    `  Input:  ${(stats.inputTokens ?? 0).toLocaleString()}`,
    `  Output: ${(stats.outputTokens ?? 0).toLocaleString()}`,
    '',
    'Tool Calls:',
    ...Object.entries(stats.toolCalls ?? {})
      .map(([name, count]) => `  ${name}: ${count}`)
      .sort((a, b) => b[1] - a[1]),
  ]

  return {
    type: 'text',
    text: lines.join('\n'),
  }
}

function formatDuration(ms: number): string {
  const minutes = Math.floor(ms / 60000)
  const seconds = Math.floor((ms % 60000) / 1000)
  return `${minutes}m ${seconds}s`
}
```

## 步骤 5：注册命令

```typescript
// src/commands.ts — 在导入区域添加
import metricsCommand from './commands/metrics/index.js'

// 在 COMMANDS() 数组中添加
const COMMANDS = memoize(() => [
  // ... 现有命令
  metricsCommand,
])
```

## 步骤 6：测试

```typescript
// src/commands/metrics/metrics.test.ts
import { describe, it, expect } from 'vitest'
import { call } from './metrics.js'

describe('/metrics', () => {
  it('should return text result', async () => {
    const result = await call([], {
      stats: {
        duration: 932000,
        inputTokens: 45230,
        outputTokens: 12450,
        toolCalls: { Read: 5, Edit: 3, Bash: 2 },
      },
    })
    expect(result.type).toBe('text')
    expect(result.text).toContain('Session Metrics')
    expect(result.text).toContain('Read: 5')
  })
})
```

## 替代方案：Prompt 类型命令

如果命令需要模型参与（如 `/metrics-report` 生成详细报告）：

```typescript
const metricsReportCommand = {
  type: 'prompt',
  name: 'metrics-report',
  description: 'Generate a detailed usage report with analysis',
  getPromptForCommand(args, context) {
    return `Analyze the current session metrics and provide recommendations.
Cost: $${getTotalCostUSD().toFixed(4)}
Session ID: ${getSessionId()}
Provide tips on reducing token usage and cost.`
  },
} satisfies Command
```

---

## 命令类型选择指南

| 场景 | 类型 | 理由 |
|------|------|------|
| 显示信息、执行本地操作 | `local` | 不需要模型 |
| 交互式 UI（选择、表单） | `local-jsx` | 需要 Ink 组件 |
| 需要模型分析/生成 | `prompt` | 展开为提示词 |
| 需要工具调用 | `prompt` + `allowedTools` | 模型执行操作 |

---

## 检查点

- **命令开发流程**：创建目录 → 选择类型 → 实现定义 + 逻辑 → 注册 → 测试
- **三种命令类型**：local（本地）、local-jsx（交互式）、prompt（提示词）
- **命令注册**：`src/commands.ts` 的 `COMMANDS()` 数组
- **`satisfies Command`**：编译时检查必填字段
- **LocalCommandResult**：`text` / `compact` / `skip` 三种返回类型

**下一章**：第 24 章接入自定义 MCP Server。
