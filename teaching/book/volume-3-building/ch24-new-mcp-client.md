# 第 24 章：造一个 MCP 客户端

> 源码验证日期：2026-05-15，基于 commit `0d81bb6`

本章接入一个自定义 MCP Server——一个简单的文件搜索服务。

---

## 目标

```
用户：搜索包含 "useQuery" 的所有文件
Claude：[调用 my-search__search_files]
  → MCP Server 返回匹配文件列表
  → 显示结果
```

---

## 方式 1：配置式接入（最常见）

大多数 MCP 服务器只需要配置——不需要写代码：

### 在 settings.json 中配置

```json
// .claude/settings.json
{
  "mcpServers": {
    "my-search": {
      "command": "npx",
      "args": ["-y", "@my-org/mcp-file-search"],
      "env": {
        "SEARCH_ROOT": "/projects/my-app"
      }
    }
  }
}
```

Claude Code 会自动：
1. 启动 MCP Server 进程（stdio 传输）
2. 调用 `tools/list` 获取工具定义
3. 用适配器模式包装为 Claude Code Tool
4. 注册到工具池中

### 验证连接

```bash
claude
> /mcp
# 查看已连接的 MCP 服务器状态
```

---

## 方式 2：SSE 远程服务器

```json
{
  "mcpServers": {
    "my-remote-api": {
      "url": "https://api.example.com/mcp",
      "headers": {
        "Authorization": "Bearer $MY_API_KEY"
      }
    }
  }
}
```

`$MY_API_KEY` 从环境变量插值。

---

## 方式 3：编程式 MCP 服务器（SDK）

使用 Agent SDK 创建进程内 MCP 服务器：

```typescript
// my-mcp-server.ts
import { createSdkMcpServer, tool } from '@anthropic-ai/claude-code'
import { z } from 'zod'

const server = createSdkMcpServer('my-tools')

server.tool(
  tool({
    name: 'search_files',
    description: 'Search files by content pattern',
    inputSchema: z.object({
      pattern: z.string().describe('Search pattern'),
      path: z.string().optional().describe('Directory to search'),
    }),
    run: async ({ pattern, path }) => {
      // 实现搜索逻辑
      const results = await searchFiles(pattern, path)
      return JSON.stringify(results)
    },
  })
)
```

---

## MCP 工具如何变成 Claude Code Tool

回顾第 19 章的适配器模式：

```
MCP Server 启动
  → tools/list 返回工具定义（JSON Schema）
  → client.ts fetchToolsForClient() 转换
    → ...MCPTool 骨骨 + 运行时覆盖
      → Claude Code Tool 对象
        → assembleToolPool() 合并到工具池
          → 发送给 Anthropic API
```

关键映射：

| MCP 属性 | Claude Code Tool 属性 |
|---------|---------------------|
| `name` | `name`（加 `serverName__` 前缀） |
| `inputSchema` | `inputJSONSchema`（保持 JSON Schema） |
| `description` | `description()` + `prompt()` |
| `annotations.readOnlyHint` | `isReadOnly()` + `isConcurrencySafe()` |
| `annotations.destructiveHint` | `isDestructive()` |
| `tools/call` | `call()` |

---

## 调试 MCP 连接

### 常见问题

| 问题 | 原因 | 解决 |
|------|------|------|
| Server 状态 Pending | 进程未启动 | 检查 command 路径 |
| Server 状态 Failed | 连接错误 | 查看 stderr 日志 |
| Server 状态 NeedsAuth | 需要 OAuth | 运行 `/mcp` 认证 |
| 工具不出现 | 被策略过滤 | 检查 deny 规则 |

### 日志方法

```typescript
// 在 src/services/mcp/client.ts 的 fetchToolsForClient 中
console.log('[DEBUG] MCP tools from', serverName, ':',
  tools.map(t => t.name))
```

---

## 检查点

- **配置式接入**：在 settings.json 中添加 `mcpServers` 条目
- **传输类型**：stdio（本地进程）、SSE/HTTP（远程）、SDK（进程内）
- **适配器自动转换**：MCP 工具定义 → Claude Code Tool 对象
- **SDK 方式**：`createSdkMcpServer()` + `tool()` 编程式创建
- **调试**：`/mcp` 命令查看状态，检查连接和工具列表

**下一章**：第 25 章创建自定义输出样式。
