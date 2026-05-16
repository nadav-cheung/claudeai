# 附录 D：命令速查与源码路径

> Claude Code CLI 命令、REPL 内命令、环境变量、核心函数索引与源码路径速查。

---

## D.1 CLI 命令

| 命令 | 说明 |
|------|------|
| `claude` | 启动交互式 REPL |
| `claude --cwd <path>` | 指定工作目录 |
| `claude --verbose` | 详细日志输出 |
| `claude --config <path>` | 指定配置文件 |
| `claude -t <Tool> -- <args>` | 直接调用单个工具 |
| `claude --list-tools` | 列出所有可用工具 |
| `claude --allow-tool <Tool>` | 允许指定工具执行 |
| `claude --mcp` | 启动内置 MCP 服务器 |
| `claude --mcp-config <path>` | 指定 MCP 配置文件 |
| `claude --list-mcp-servers` | 列出已连接的 MCP 服务器 |
| `claude --dangerously-skip-permissions` | 跳过权限检查（危险） |
| `claude --permission-mode <mode>` | 设置权限模式：`prompt` / `bypass` / `fail` / `approve` |
| `claude --export-permissions <path>` | 导出权限配置 |
| `claude --log-file <path>` | 日志输出到文件 |
| `claude --profile` | 启用性能分析 |
| `claude --heap-snapshot` | 启动时生成堆快照 |
| `claude --memory-monitor` | 监控内存使用 |

---

## D.2 REPL 内命令

| 命令 | 说明 |
|------|------|
| `/exit` 或 `/quit` | 退出 REPL |
| `/help` | 查看帮助信息 |
| `/theme dark` | 切换深色主题 |
| `/theme light` | 切换浅色主题 |
| `/clear` | 清除当前对话历史 |
| `/compact` | 压缩上下文以释放 token 空间 |
| `/skills` | 列出所有已注册的 Skill |
| `/review` | 调用代码审查 Skill |
| `/docs` | 调用文档生成 Skill |
| `/refactor` | 调用重构 Skill |
| `/test` | 调用测试生成 Skill |

> 自定义 Skill 以 `/` 前缀调用，如 `/my-skill arg1 arg2`。

---

## D.3 环境变量速查

| 变量 | 说明 | 取值示例 |
|------|------|----------|
| `ANTHROPIC_API_KEY` | Anthropic API 密钥 | `sk-ant-xxx...` |
| `CLAUDE_CODE_CONFIG` | 自定义配置文件路径 | `/etc/claude/config.json` |
| `CLAUDE_CODE_DATA_DIR` | 数据存储目录 | `~/.claude` |
| `LOG_LEVEL` | 日志级别 | `debug` / `info` / `warn` / `error` |
| `DEBUG` | 调试模式开关 | `true` / `false` |
| `NODE_ENV` | 运行环境标识 | `development` / `production` |
| `ENABLE_PROFILING` | 性能分析开关 | `true` / `false` |
| `HTTP_PROXY` | HTTP 代理地址 | `http://proxy:8080` |
| `HTTPS_PROXY` | HTTPS 代理地址 | `http://proxy:8080` |

---

## D.4 权限模式速查

| 模式 | 行为 |
|------|------|
| `prompt` | 每次敏感操作询问用户（默认） |
| `bypass` | 完全跳过权限检查 |
| `fail` | 无权限时直接失败，不提示 |
| `approve` | 自动批准所有请求 |

---

## D.5 核心函数索引

按功能模块分组，列出 Claude Code 源码中最关键的函数及其职责。

### 入口与初始化（卷一 ch03）

| 函数 | 文件 | 一句话描述 |
|------|------|-----------|
| `main()` | `cli.tsx` | CLI 入口调度员，快速路径路由 |
| `main()` | `main.tsx` | 完整 CLI 初始化（认证、Bootstrap、工具组装） |
| `init()` | `init.ts` | 一次性初始化（memoized） |

### 消息处理（卷一 ch04）

| 函数 | 文件 | 一句话描述 |
|------|------|-----------|
| `handlePromptSubmit()` | `handlePromptSubmit.ts` | 处理用户提交 |
| `processUserInput()` | `processUserInput.ts` | 输入模式路由 |
| `processTextPrompt()` | `processTextPrompt.ts` | 文本输入处理 |
| `createUserMessage()` | `messages.ts` | 创建消息对象 |

### 查询引擎（卷一 ch05-ch07）

| 函数 | 文件 | 一句话描述 |
|------|------|-----------|
| `getSystemPrompt()` | `prompts.ts` | 组装 system prompt（静态区 + 动态区） |
| `getSystemContext()` | `context.ts` | 获取 Git 状态（memoized） |
| `getUserContext()` | `context.ts` | 加载 CLAUDE.md（memoized） |
| `getMemoryFiles()` | `claudemd.ts` | 遍历加载 CLAUDE.md 文件 |
| `getTools()` | `tools.ts` | 组装工具列表 |
| `assembleToolPool()` | `tools.ts` | 合并内置工具 + MCP 工具 |
| `buildTool()` | `Tool.ts` | 工厂函数，从定义创建可执行工具对象 |
| `query()` | `query.ts` | AsyncGenerator 入口，启动查询流 |
| `queryLoop()` | `query.ts` | while(true) 九步循环——核心心脏 |
| `productionDeps()` | `deps.ts` | 依赖注入，绑定真实 API 调用 |
| `queryModelWithStreaming()` | `claude.ts` | 流式 API 调用，返回 AsyncGenerator |

### 权限系统（卷二 ch11）

| 函数 | 文件 | 一句话描述 |
|------|------|-----------|
| `hasPermissionsToUseTool()` | `permissions.ts` | 权限检查主入口 |
| `hasPermissionsToUseToolInner()` | `permissions.ts` | 分层检查实现（白名单 → 规则 → 用户确认） |
| `bashToolHasPermission()` | `bashPermissions.ts` | Bash 命令安全分析 |
| `COMMAND_ALLOWLIST` | `readOnlyValidation.ts` | 只读命令白名单常量 |
| `initialPermissionModeFromCLI()` | `permissionSetup.ts` | 根据 CLI 参数确定初始权限模式 |

### 工具执行（卷二 ch08）

| 函数 | 文件 | 一句话描述 |
|------|------|-----------|
| `addTool()` | `StreamingToolExecutor.ts` | 添加工具到并发执行队列 |
| `canExecuteTool()` | `StreamingToolExecutor.ts` | 判断工具是否满足并发安全条件 |
| `checkPermissionsAndCallTool()` | `toolExecution.ts` | 权限检查 + 执行的 5 步链 |

### 状态管理（卷二 ch09）

| 函数/概念 | 文件 | 一句话描述 |
|----------|------|-----------|
| `State`（type） | `query.ts` | 循环可变状态的类型定义 |
| 三阶段恢复 | `query.ts` | Collapse drain → Reactive Compact → Max Token 升级 |
| `handleStopHooks()` | `query.ts` | 会话结束时的 Stop hook 处理 |

### 渲染系统（卷三 ch10）

| 函数 | 文件 | 一句话描述 |
|------|------|-----------|
| `render()` | `ink.tsx` | React 树挂载到终端 |
| `onRender()` | `ink.tsx` | 帧渲染管线，计算布局并输出 |
| `handleMessageFromStream()` | `messages.ts` | 流式事件分发到状态更新 |
| `MessageImpl()` | `Message.tsx` | 消息类型分发渲染组件 |

---

## D.6 核心源码路径

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
| Bash 命令安全分析 | `src/utils/permissions/bashPermissions.ts` |
| 只读命令白名单 | `src/utils/permissions/readOnlyValidation.ts` |
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

### 渲染与 TUI

| 功能 | 源码路径 |
|------|----------|
| Ink 入口 | `src/ink.tsx` |
| 消息组件 | `src/Message.tsx` |
| 布局引擎（Yoga） | Ink 内部依赖 |

---

## D.7 核心数据结构速查

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

> CLI 参数覆盖环境变量，环境变量覆盖配置文件。当调试异常行为时，优先检查这三层优先级是否冲突。
>
> 源码路径随版本迭代可能变动。当路径失效时，以模块名（如 `toolExecution`、`denialTracking`）为关键词全局搜索即可定位。
