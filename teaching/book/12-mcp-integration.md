# 12 - MCP 协议集成

> **本章目标**：深入理解 Model Context Protocol (MCP) 如何让 Claude Code 动态扩展工具能力。

---

## 1. 准备工作

### 1.1 阅读源码

**必读**：
- `src/services/mcp/` - MCP 服务实现
- `src/tools/MCPTool/` - MCP 工具包装器

### 1.2 本章与 Mini-Claude 的关系

Mini-Claude **没有** MCP 支持 —— 这是 Claude Code 插件生态的基础。

---

## 2. MCP 协议简介

### 2.1 什么是 MCP？

MCP (Model Context Protocol) 是一种让 AI 模型与外部工具和服务交互的标准化协议：

```text
┌─────────────────────────────────────────────────────────────┐
│                        Claude Code                           │
│                                                             │
│  ┌───────────────────────────────────────────────────────┐  │
│  │                    MCP Client                          │  │
│  │  ┌─────────┐  ┌─────────┐  ┌─────────┐               │  │
│  │  │ Server1 │  │ Server2 │  │ Server3 │  ...          │  │
│  │  │ (文件系统) │  │ (Git)   │  │ (数据库) │              │  │
│  │  └─────────┘  └─────────┘  └─────────┘               │  │
│  └───────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
                    │
                    │ MCP 协议
                    ▼
         ┌──────────────────────┐
         │     MCP Server        │
         │  (提供工具/资源)       │
         └──────────────────────┘
```

### 2.2 MCP vs Mini-Claude 的工具系统

| 方面 | Mini-Claude | Claude Code + MCP |
|------|-------------|-------------------|
| 工具来源 | 硬编码 | 动态加载 |
| 扩展方式 | 修改代码 | 配置服务器 |
| 工具数量 | 3 个 | 30+ 基础 + 无限扩展 |
| 类型安全 | 无 | Schema 验证 |

---

## 3. MCP 架构

### 3.1 MCP 服务器

```typescript
// MCP 服务器配置示例
interface MCPServerConfig {
  name: string;           // 服务器名称
  command: string;        // 启动命令
  args?: string[];        // 启动参数
  env?: Record<string, string>;  // 环境变量
  autoConnect?: boolean;  // 自动连接
}

// .claude/mcp.json
{
  "servers": [
    {
      "name": "filesystem",
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-filesystem", "./"]
    },
    {
      "name": "git",
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-github"]
    }
  ]
}
```

### 3.2 MCP 客户端

```typescript
// services/mcp/mcp-client.ts (简化)
export class MCPClient {
  private servers: Map<string, MCPConnection> = new Map();

  async connect(config: MCPServerConfig): Promise<void> {
    // 1. 启动 MCP 服务器进程
    const process = spawn(config.command, config.args, {
      env: { ...process.env, ...config.env },
    });

    // 2. 建立 JSON-RPC 通信
    const connection = new MCPConnection(process);

    // 3. 握手并获取服务器能力
    const capabilities = await connection.initialize();

    // 4. 注册工具
    this.servers.set(config.name, connection);
  }

  // 调用 MCP 工具
  async callTool(serverName: string, toolName: string, args: unknown) {
    const server = this.servers.get(serverName);
    if (!server) {
      throw new Error(`MCP server not found: ${serverName}`);
    }

    return await server.callTool(toolName, args);
  }

  // 列出所有可用工具
  listTools(): Tool[] {
    const tools: Tool[] = [];
    for (const [serverName, server] of this.servers) {
      const serverTools = server.getTools();
      // 为每个工具添加 server 标签
      tools.push(...serverTools.map(t => ({
        ...t,
        name: `${serverName}:${t.name}`, // 命名空间隔离
      })));
    }
    return tools;
  }
}
```

---

## 4. MCP 工具包装

### 4.1 MCPTool

Claude Code 将 MCP 工具包装成本地工具：

```typescript
// tools/MCPTool/ (简化)
export class MCPTool implements Tool {
  name = 'mcp_tool';
  description = '执行 MCP 服务器提供的工具';

  constructor(
    private serverName: string,
    private toolName: string,
    private inputSchema: object
  ) {}

  input_schema = this.inputSchema;

  async execute(args: unknown, context: ToolContext) {
    const result = await mcpClient.callTool(
      this.serverName,
      this.toolName,
      args
    );

    return {
      success: true,
      result: JSON.stringify(result),
    };
  }
}
```

### 4.2 动态工具注册

```typescript
// 当 MCP 服务器连接时，动态注册工具
async function onServerConnect(server: MCPConnection) {
  const tools = server.getTools();

  for (const tool of tools) {
    // 注册到全局工具注册表
    registry.register(new MCPTool(server.name, tool.name, tool.inputSchema));
  }
}
```

---

## 5. MCP 资源系统

### 5.1 什么是 MCP 资源？

MCP 不仅提供工具，还提供**资源**（类似文件系统的文件）：

```typescript
// MCP 资源示例
interface MCPResource {
  uri: string;           // 资源标识符
  name: string;         // 资源名称
  mimeType: string;     // MIME 类型
  content: string | Buffer;  // 资源内容
}

// 资源示例
// file:///project/package.json
// git://current-branch
// database://schema/users
```

### 5.2 资源读取

```typescript
// ListMcpResourcesTool
export class ListMcpResourcesTool implements Tool {
  name = 'list_mcp_resources';

  async execute(args: unknown, context: ToolContext) {
    const resources = await mcpClient.listResources();

    return {
      success: true,
      result: resources
        .map(r => `${r.uri}: ${r.name}`)
        .join('\n'),
    };
  }
}

// ReadMcpResourceTool
export class ReadMcpResourceTool implements Tool {
  name = 'read_mcp_resource';

  async execute(args: { uri: string }, context: ToolContext) {
    const content = await mcpClient.readResource(args.uri);

    return {
      success: true,
      result: content,
    };
  }
}
```

---

## 6. Mini-Claude 的简单扩展

### 6.1 插件式工具注册

虽然 Mini-Claude 没有 MCP，但可以设计一个简单的插件系统：

```typescript
// Mini-Claude 插件接口
interface MiniClaudePlugin {
  name: string;
  tools: Tool[];
  init?: () => Promise<void>;
}

// 插件注册表
class PluginRegistry {
  private plugins: Map<string, MiniClaudePlugin> = new Map();

  register(plugin: MiniClaudePlugin) {
    this.plugins.set(plugin.name, plugin);

    // 注册插件提供的工具
    for (const tool of plugin.tools) {
      registry.register(tool);
    }

    // 调用初始化
    if (plugin.init) {
      plugin.init();
    }
  }

  listPlugins(): MiniClaudePlugin[] {
    return Array.from(this.plugins.values());
  }
}
```

### 6.2 插件示例

```typescript
// 一个简单的文件系统插件
const fileSystemPlugin: MiniClaudePlugin = {
  name: 'filesystem',
  tools: [
    new FileReadTool(),
    new FileWriteTool(),
  ],
};

// 注册插件
pluginRegistry.register(fileSystemPlugin);
```

---

## 7. 实战练习

### 7.1 练习：实现 MCP 模拟

**目标**：为 Mini-Claude 设计一个简化版的 MCP 协议

**答案要点**：
```typescript
// 简化的 MCP 模拟
interface MockMCPServer {
  name: string;
  tools: Tool[];
}

// 服务器注册表
const servers: MockMCPServer[] = [];

// 添加服务器
function addServer(server: MockMCPServer) {
  servers.push(server);
  // 注册工具
  for (const tool of server.tools) {
    registry.register(tool);
  }
}

// 初始化所有服务器
async function initializeMCP() {
  // 用户可以配置服务器
  addServer({
    name: 'filesystem',
    tools: [new FileReadTool(), new FileWriteTool()],
  });
}
```

---

## 8. 总结

| 方面 | Mini-Claude | Claude Code + MCP |
|------|-------------|-------------------|
| 工具扩展 | 修改代码 | 配置服务器 |
| 协议标准 | 无 | MCP 标准 |
| 工具来源 | 硬编码 | 动态加载 |
| 资源访问 | 无 | MCP 资源 |
| 命名空间 | 无 | 服务器隔离 |

---

## 下一篇

👉 [13 - Agent与多Agent协作](../08-agent-and-team.md) —— 深入理解 Agent 模式

`★ Insight ─────────────────────────────────────`
MCP 的核心价值是**解耦**——工具提供者不需要知道 Claude Code 的存在，只需要实现 MCP 协议即可。这就像 USB 接口：不管是什么设备，只要支持 USB，就能插上电脑用。Claude Code 通过 MCP 实现了"即插即用"的工具扩展生态。
`─────────────────────────────────────────────────`
