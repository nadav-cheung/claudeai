---
title: "第06章：接入MCP Server"
description: "从配置到连接，从工具发现到实际调用——学习如何将外部 MCP 工具服务器接入 Claude Code。理解 .mcp.json 配置格式、MCPConnectionManager 的连接管理、工具发现与注册的完整流程。"
tags: [MCP, mcp-server, tool-discovery, stdio, sse, http, connection, config, .mcp.json]
date: 2026-05-10
---

# 第06章：接入MCP Server

在卷二的第九章里，我们从协议层面理解了 MCP（Model Context Protocol）——它是一种标准化的工具发现和调用协议。但理解协议和实际接入一个 MCP 服务器是两码事。

这一章，我们从实践角度出发：如何配置一个外部 MCP 服务器，让它连上 Claude Code，让 AI 能够使用它提供的工具。

---

## 目标

完成这一章后，你将能够：

1. 理解 MCP 服务器的配置格式和三种作用域
2. 学会用 `.mcp.json` 和用户配置两种方式添加 MCP 服务器
3. 理解连接管理器 `MCPConnectionManager` 的工作原理
4. 知道工具是如何被发现、注册并暴露给 AI 的
5. 理解企业策略（allowlist/denylist）如何控制 MCP 服务器的可用性

---

## 动手

### 第一步：创建你的第一个 .mcp.json

MCP 服务器的配置入口是项目根目录下的 `.mcp.json` 文件。它的格式非常简单：

```json
{
  "mcpServers": {
    "my-server": {
      "command": "node",
      "args": ["./my-mcp-server.js"]
    }
  }
}
```

这个配置告诉 Claude Code：启动一个名为 `my-server` 的 MCP 服务器，用 `node ./my-mcp-server.js` 命令启动它，通过标准输入/输出（stdio）与之通信。

让我们看 Claude Code 源码中是如何解析这个文件的。配置解析在 `src/services/mcp/config.ts` 中：

```typescript
// 文件：src/services/mcp/config.ts
export function getProjectMcpConfigsFromCwd(): {
  servers: Record<string, ScopedMcpServerConfig>
  errors: ValidationError[]
} {
  const mcpJsonPath = join(getCwd(), '.mcp.json')
  const { config, errors } = parseMcpConfigFromFilePath({
    filePath: mcpJsonPath,
    expandVars: true,
    scope: 'project',
  })
  // ...
}
```

它读取当前目录下的 `.mcp.json`，解析并验证配置，然后返回带有作用域标签的服务器配置。

### 第二步：理解三种通信方式

MCP 服务器有三种通信方式，对应三种配置格式：

**stdio——通过标准输入输出通信。** 最常见的方式，适合本地进程：

```json
{
  "command": "node",
  "args": ["./server.js"],
  "env": { "API_KEY": "xxx" }
}
```

**SSE——通过 Server-Sent Events 通信。** 适合远程 HTTP 服务器：

```json
{
  "type": "sse",
  "url": "https://mcp.example.com/sse"
}
```

**HTTP——通过 Streamable HTTP 通信。** MCP 协议的新传输方式：

```json
{
  "type": "http",
  "url": "https://mcp.example.com/mcp"
}
```

在源码中，这三种方式通过 `type` 字段区分。`type` 省略时默认为 `stdio`：

```typescript
// 文件：src/services/mcp/types.ts
type McpStdioServerConfig = {
  type?: 'stdio'       // 可选，默认为 stdio
  command: string       // 要执行的命令
  args?: string[]       // 命令参数
  env?: Record<string, string>  // 环境变量
}

type McpSSEServerConfig = {
  type: 'sse'
  url: string           // SSE 端点 URL
  headers?: Record<string, string>  // 自定义请求头
}

type McpHTTPServerConfig = {
  type: 'http'
  url: string           // HTTP 端点 URL
  headers?: Record<string, string>
}
```

### 第三步：配置的作用域

MCP 服务器配置有三个作用域，决定了谁能看到这个服务器：

**project——项目级。** 配置在项目根目录的 `.mcp.json` 中，只有这个项目的会话能看到。这是最常用的作用域。团队协作时，把 `.mcp.json` 提交到版本控制，整个团队都能用上同样的 MCP 服务器。

**user——用户级。** 配置在用户全局设置中（`~/.claude/settings.json` 的 `mcpServers` 字段），对所有项目生效。适合放个人偏好的工具，比如你自己的 GitHub MCP 服务器。

**local——本地级。** 配置在项目的 `.claude/settings.local.json` 中，对本机当前项目生效，但不提交到版本控制。适合放包含密钥的配置。

源码中的优先级是：`plugin < user < project < local`。也就是说，如果同一个名字的服务器同时出现在多个作用域中，local 的配置会胜出。

```typescript
// 文件：src/services/mcp/config.ts
// 按优先级合并：plugin < user < project < local
const configs = Object.assign(
  {},
  dedupedPluginServers,    // 优先级最低
  userServers,
  approvedProjectServers,
  localServers,            // 优先级最高
)
```

### 第四步：连接是如何建立的

当你配置好 MCP 服务器并启动 Claude Code 后，`MCPConnectionManager` 负责建立连接。它是一个 React Context Provider，包裹在应用的顶层：

```typescript
// 文件：src/services/mcp/MCPConnectionManager.tsx
export function MCPConnectionManager({
  children,
  dynamicMcpConfig,
  isStrictMcpConfig,
}) {
  const { reconnectMcpServer, toggleMcpServer } =
    useManageMCPConnections(dynamicMcpConfig, isStrictMcpConfig)

  return (
    <MCPConnectionContext.Provider value={{ reconnectMcpServer, toggleMcpServer }}>
      {children}
    </MCPConnectionContext.Provider>
  )
}
```

它提供两个核心功能：

- **`reconnectMcpServer(name)`**——重新连接指定的 MCP 服务器（用于配置变更后刷新）
- **`toggleMcpServer(name)`**——启用或禁用指定的 MCP 服务器

实际的连接建立发生在 `src/services/mcp/client.ts` 的 `connectToServer` 函数中。它根据配置的 `type` 创建对应的传输层：

```typescript
// 文件：src/services/mcp/client.ts（简化）
async function connectToServer(name, config) {
  let transport: Transport

  if (config.type === 'sse') {
    transport = new SSEClientTransport(new URL(config.url))
  } else if (config.type === 'http') {
    transport = new StreamableHTTPClientTransport(new URL(config.url))
  } else {
    // 默认 stdio
    transport = new StdioClientTransport({
      command: config.command,
      args: config.args,
      env: { ...process.env, ...config.env },
    })
  }

  const client = new Client({ name: `claude-code-${name}`, version: '1.0' })
  await client.connect(transport)

  return { type: 'connected', client, name, cleanup: () => client.close() }
}
```

对于 stdio 服务器，Claude Code 会启动一个子进程，通过标准输入发送 JSON-RPC 消息，从标准输出读取响应。对于 SSE 和 HTTP 服务器，则通过 HTTP 请求通信。

### 第五步：工具发现——MCP 服务器告诉 Claude Code 它能做什么

连接建立后，Claude Code 会调用 MCP 协议的 `tools/list` 方法，获取服务器提供的工具列表：

```typescript
// 文件：src/services/mcp/client.ts
async function fetchToolsForClient(client) {
  const { tools } = await client.request(
    { method: 'tools/list' },
    ListToolsResultSchema,
  )

  // 把每个 MCP 工具包装成 Claude Code 的 Tool 对象
  return tools.map(toolDef => new MCPTool(client, toolDef))
}
```

每个 MCP 工具会被包装成 `MCPTool` 实例。`MCPTool` 实现了 Claude Code 的 `Tool` 接口，这样 AI 就能像调用内置工具一样调用 MCP 工具。

MCP 工具的名字会被加上前缀 `mcp__serverName__`。比如你的服务器叫 `weather`，它提供一个 `get_forecast` 工具，那么 AI 看到的工具名就是 `mcp__weather__get_forecast`。这个前缀避免了不同服务器之间的名字冲突。

### 第六步：试试看——接入一个真实的 MCP 服务器

让我们用一个实际例子来体验。假设你想接入一个提供文件系统操作的 MCP 服务器。首先创建 `.mcp.json`：

```json
{
  "mcpServers": {
    "filesystem": {
      "command": "npx",
      "args": [
        "-y",
        "@modelcontextprotocol/server-filesystem",
        "/Users/you/documents"
      ]
    }
  }
}
```

这个配置使用 `npx` 运行 MCP 官方提供的文件系统服务器，把它限制在 `/Users/you/documents` 目录下。

启动 Claude Code 后，服务器会自动连接。你可以用 `/mcp` 命令查看所有 MCP 服务器的状态：

```
> /mcp

MCP Servers:
  filesystem (connected)
    Tools: read_file, write_file, list_directory, search_files, ...
```

现在 AI 可以使用 `mcp__filesystem__read_file` 等工具来操作你的文档目录了。

### 第七步：环境变量和安全配置

很多 MCP 服务器需要 API 密钥或其他敏感信息。你可以通过 `env` 字段传递环境变量：

```json
{
  "mcpServers": {
    "github": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-github"],
      "env": {
        "GITHUB_PERSONAL_ACCESS_TOKEN": "${GITHUB_TOKEN}"
      }
    }
  }
}
```

注意 `${GITHUB_TOKEN}` 的写法。Claude Code 支持在配置值中使用 `${VAR_NAME}` 格式的环境变量引用。解析逻辑在 `envExpansion.ts` 中：

```typescript
// 文件：src/services/mcp/envExpansion.ts
export function expandEnvVarsInString(input: string): {
  expanded: string
  missingVars: string[]
} {
  // 把 ${VAR_NAME} 替换成 process.env.VAR_NAME 的值
  // 记录哪些变量不存在（missingVars）
}
```

如果引用的环境变量不存在，配置会被标记为有警告，但不会阻止启动。这样你可以在 `.mcp.json` 中写好配置模板，实际值从环境中读取——避免把密钥写进版本控制。

### 第八步：企业策略控制

在企业环境中，管理员可能需要控制哪些 MCP 服务器可以被使用。Claude Code 支持三层策略：

**allowlist（白名单）**——只有白名单中的服务器被允许。空的 allowlist 意味着阻止所有服务器。

**denylist（黑名单）**——黑名单中的服务器被阻止，其他都允许。denylist 优先于 allowlist。

**企业配置（enterprise）**——当存在企业 MCP 配置文件时，其他所有来源（user、project、local）都被忽略，只使用企业配置。

```typescript
// 文件：src/services/mcp/config.ts
function isMcpServerAllowedByPolicy(serverName, config) {
  // 先检查 denylist
  if (isMcpServerDenied(serverName, config)) {
    return false
  }
  // 再检查 allowlist
  const settings = getMcpAllowlistSettings()
  if (!settings.allowedMcpServers) {
    return true  // 没有白名单 = 允许所有
  }
  // 按名字、命令、URL 匹配
  // ...
}
```

策略匹配支持三种维度：按名字匹配、按启动命令匹配（针对 stdio 服务器）、按 URL 匹配（针对远程服务器）。这样管理员可以灵活地按安全需求配置策略。

---

## 遇到问题？

### 问题 1：MCP 服务器连接失败

**症状**：`.mcp.json` 配置正确，但服务器显示为 `disconnected`。

**原因**：最常见的原因是服务器命令执行失败。比如 `npx` 找不到指定的包，或者环境变量没有设置。

**解决方案**：检查以下几点：

1. 手动运行配置中的命令，确认服务器可以启动
2. 检查环境变量是否设置正确（用 `echo $VAR_NAME` 确认）
3. 查看 Claude Code 的调试日志（设置 `CLAUDE_CODE_DEBUG=1`）
4. 用 `/mcp` 命令查看服务器的具体错误信息

### 问题 2：工具名冲突

**症状**：两个不同的 MCP 服务器提供了同名工具，AI 调用时不确定用的是哪个。

**原因**：MCP 工具名有 `mcp__serverName__` 前缀，所以即使两个服务器提供了同名工具（比如都叫 `search`），它们的完整名字不会冲突（`mcp__server1__search` vs `mcp__server2__search`）。

**解决方案**：名字冲突在工具层面不会发生。但如果你担心 AI 选错服务器，可以在权限规则中配置 deny 规则来禁用不需要的那个：`mcp__server1__search` → deny。

### 问题 3：项目级服务器需要手动批准

**症状**：配置了 `.mcp.json`，但服务器没有被连接。

**原因**：出于安全考虑，项目级的 MCP 服务器需要用户首次手动批准。这是一个防止恶意仓库在你不知情的情况下启动进程的安全措施。

**解决方案**：第一次使用时，Claude Code 会弹出确认对话框，询问你是否信任这个服务器。批准后，配置会被记录在 `.claude/settings.local.json` 的 `approvedMcpServers` 中，后续不再询问。

### 问题 4：Windows 上的 npx 问题

**症状**：在 Windows 上配置 `"command": "npx"` 的服务器无法启动。

**原因**：Windows 上 `npx` 是一个批处理脚本，需要通过 `cmd /c` 来执行。

**解决方案**：修改配置格式：

```json
{
  "command": "cmd",
  "args": ["/c", "npx", "-y", "@modelcontextprotocol/server-filesystem"]
}
```

源码中有一个专门的检查来警告这个问题：

```typescript
// 文件：src/services/mcp/config.ts
if (getPlatform() === 'windows' && (command === 'npx' || ...)) {
  errors.push({
    message: "Windows requires 'cmd /c' wrapper to execute npx",
    suggestion: 'Change command to "cmd" with args ["/c", "npx", ...]',
  })
}
```

---

## 验证

让我们通过几个操作来验证你的 MCP 服务器是否正确接入。

**测试 1：配置验证。** 创建一个 `.mcp.json` 文件，配置一个 stdio 类型的 MCP 服务器。确认文件格式正确（可以用 `cat .mcp.json` 检查 JSON 语法）。

**测试 2：连接状态。** 启动 Claude Code，运行 `/mcp` 命令。你的服务器应该显示为 `connected`，并列出它提供的工具。

**测试 3：工具可用性。** 在对话中让 AI 使用 MCP 工具。比如 "列出 mcp__my-server 下的所有工具"。AI 应该能看到并调用这些工具。

**测试 4：环境变量展开。** 在配置中使用 `${VAR_NAME}` 引用一个环境变量。确认它被正确展开（查看调试日志），而不是被当作字面字符串。

**测试 5：权限规则。** 尝试为 MCP 工具配置权限规则：

- `mcp__my-server` → deny（整个服务器被禁用）
- `mcp__my-server__*` → deny（同上，通配符形式）

确认规则生效后，AI 不再能调用该服务器的工具。

如果这五个测试都通过了，你的 MCP 服务器接入就成功了。

---

## 回顾

这一章，我们从实践角度学习了 MCP 服务器的接入：

1. **`.mcp.json`**——项目级配置文件，定义服务器名称、命令和参数
2. **三种通信方式**——stdio（本地进程）、SSE（HTTP 长连接）、HTTP（Streamable HTTP）
3. **三个作用域**——project、user、local，优先级递增
4. **连接管理器**——`MCPConnectionManager` 负责建立和维护连接
5. **工具发现**——通过 `tools/list` 获取工具列表，包装为 `MCPTool`
6. **环境变量**——用 `${VAR_NAME}` 安全引用敏感配置
7. **企业策略**——allowlist/denylist 控制服务器的可用性

记住，MCP 的核心思想是**工具即服务**。你不需要把所有功能都写进 Claude Code 里，只需接入一个 MCP 服务器，AI 就能使用它提供的所有工具。

下一章，我们进入更高级的话题——如何让多个 Agent 协同工作。

---

[上一章：添加权限规则](./第05章-添加权限规则.md) | [下一章：构建多Agent协作](./第07章-构建多Agent协作.md)
