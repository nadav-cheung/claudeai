# 第 22 章：造一个新 Tool

> 源码验证日期：2026-05-15，基于 commit `0d81bb6`

本章通过创建一个 GitHub Issue 工具，展示完整的工具开发流程。

---

## 目标

创建一个 `GitHubIssueTool`，让 Claude 能够创建 GitHub Issue：

```
用户：给这个仓库创建一个 issue，标题是"修复登录超时问题"
Claude：[调用 GitHubIssueTool]
  → 创建 GitHub Issue
  → 返回 Issue URL
```

---

## 步骤 1：创建工具目录和 Schema

```bash
mkdir -p src/tools/GitHubIssueTool
```

```typescript
// src/tools/GitHubIssueTool/GitHubIssueTool.ts

import { z } from 'zod/v4'
import { buildTool, type ToolDef } from '../../Tool.js'
import { lazySchema } from '../../utils/lazySchema.js'

// 定义输入 Schema
const inputSchema = lazySchema(() =>
  z.strictObject({
    title: z.string().describe('Issue title'),
    body: z.string().optional().describe('Issue body/description'),
    labels: z.array(z.string()).optional().describe('Labels to apply'),
    assignees: z.array(z.string()).optional().describe('Assignees'),
    repo: z.string().optional().describe('Repository (owner/repo). Defaults to current repo.'),
  })
)

type InputSchema = ReturnType<typeof inputSchema>

// 定义输出类型
type Output = {
  url: string
  number: number
}
```

## 步骤 2：实现 buildTool

```typescript
export const GitHubIssueTool = buildTool({
  name: 'GitHubIssue',
  searchHint: 'create GitHub issues',
  maxResultSizeChars: 10_000,

  // 写操作：不并发安全、非只读
  isConcurrencySafe: () => false,
  isReadOnly: () => false,
  isDestructive: () => false,

  // Schema 作为 getter（配合 lazySchema）
  get inputSchema(): InputSchema { return inputSchema() },

  // 动态描述
  async description(input) {
    return `Create a GitHub issue: ${input.title}`
  },

  // 核心执行逻辑
  async call(args, context) {
    // 确定仓库
    const repo = args.repo ?? await detectCurrentRepo(context)

    // 构建 GitHub API 请求
    const response = await fetch(`https://api.github.com/repos/${repo}/issues`, {
      method: 'POST',
      headers: {
        'Authorization': `Bearer ${await getGitHubToken()}`,
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        title: args.title,
        body: args.body,
        labels: args.labels,
        assignees: args.assignees,
      }),
    })

    if (!response.ok) {
      const error = await response.text()
      return {
        data: { url: '', number: 0 },
        newMessages: [createUserMessage({
          content: `GitHub API error: ${response.status} ${error}`,
          isMeta: true,
        })],
      }
    }

    const issue = await response.json()
    return {
      data: {
        url: issue.html_url,
        number: issue.number,
      },
    }
  },

  // 权限检查——总是需要确认（写操作）
  async checkPermissions(input, context) {
    return { behavior: 'ask' }  // 让用户确认
  },

  // 工具使用提示（系统 prompt 中显示）
  async prompt() {
    return 'Create GitHub issues in repositories. Requires GitHub authentication.'
  },

} satisfies ToolDef<InputSchema, Output>)
```

## 步骤 3：注册工具

```typescript
// src/tools.ts — 在 getAllBaseTools() 中添加

import { GitHubIssueTool } from './tools/GitHubIssueTool/GitHubIssueTool.js'

export function getAllBaseTools(): Tools {
  return [
    // ... 现有工具
    GitHubIssueTool,
    // ...
  ]
}
```

## 步骤 4：测试

```typescript
// src/tools/GitHubIssueTool/GitHubIssueTool.test.ts
import { describe, it, expect, vi } from 'vitest'
import { GitHubIssueTool } from './GitHubIssueTool.js'

describe('GitHubIssueTool', () => {
  it('should have correct name', () => {
    expect(GitHubIssueTool.name).toBe('GitHubIssue')
  })

  it('should not be read-only', () => {
    expect(GitHubIssueTool.isReadOnly({})).toBe(false)
  })

  it('should not be concurrency-safe', () => {
    expect(GitHubIssueTool.isConcurrencySafe({})).toBe(false)
  })

  it('should create an issue', async () => {
    // mock fetch
    const mockFetch = vi.fn().mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({
        html_url: 'https://github.com/owner/repo/issues/42',
        number: 42,
      }),
    })
    vi.stubGlobal('fetch', mockFetch)

    const result = await GitHubIssueTool.call(
      { title: 'Test issue', repo: 'owner/repo' },
      mockContext,
      mockCanUseTool,
      mockParentMessage,
    )

    expect(result.data.url).toBe('https://github.com/owner/repo/issues/42')
    expect(result.data.number).toBe(42)
  })
})
```

## 步骤 5：验证

```bash
# 运行测试
bun test src/tools/GitHubIssueTool/

# 启动 Claude Code，测试工具
claude
> 给这个仓库创建一个 issue，标题是"测试"
# 观察是否出现 GitHubIssue 工具调用和权限提示
```

---

## 关键设计决策

| 决策 | 选择 | 理由 |
|------|------|------|
| `isReadOnly` | `false` | 创建 Issue 是写操作 |
| `isConcurrencySafe` | `false` | 写操作不应并行 |
| `maxResultSizeChars` | `10_000` | Issue URL 很短，不需要持久化到文件 |
| `checkPermissions` | `ask` | 创建 Issue 需要用户确认 |
| `satisfies ToolDef` | 是 | 编译时检查所有必填字段 |

---

## 检查点

- **工具开发流程**：创建目录 → 定义 Schema → 实现 buildTool → 注册 → 测试
- **lazySchema 模式**：延迟 Schema 构建，避免循环依赖
- **satisfies ToolDef**：编译时类型检查
- **注册位置**：`src/tools.ts` 的 `getAllBaseTools()`
- **测试策略**：mock 外部 API、验证输入输出、检查行为标记

**下一章**：第 23 章创建一个 `/metrics` 斜杠命令。
