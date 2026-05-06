# 00 - 全局架构总览

> **本章目标**：读完本章后，你将理解 Claude Code CLI 的整体架构、模块关系、核心数据流，以及 1884 个源文件是如何组织成一个完整系统的。

---

## 1. 项目概览

Claude Code 是一个**终端 AI 助手 CLI**，核心能力：
- 在终端中与 Claude 模型对话
- 通过**工具调用**读写文件、执行命令、搜索代码
- 管理 Git 工作流、PR、远程会话
- 支持多 Agent 协作（Team/Swarm）
- 集成 MCP 外部服务

**技术栈**：
| 技术 | 用途 |
|------|------|
| TypeScript | 主语言 |
| React + Ink | 终端 UI 渲染（Ink = React for CLI） |
| Commander.js | CLI 参数解析 |
| Zod | 参数验证 |
| Anthropic SDK | API 调用 |
| MCP SDK | 外部服务集成 |
| Bun | 运行时/构建（`bun:bundle`） |

---

## 2. 目录结构与分层

```
src/
│
├── main.tsx              ← 【入口】CLI 参数解析 + 启动
├── entrypoints/          ← 【入口层】初始化逻辑 (init.ts)
├── bootstrap/            ← 【引导层】全局状态 (state.ts)
│
├── cli/                  ← CLI 底层 I/O（退出处理、远程传输）
├── commands/             ← 斜杠命令实现（/help, /compact 等 60+ 个）
│
├── screens/              ← 屏幕级组件（REPL.tsx 是主屏幕）
├── components/           ← UI 组件库（权限对话框、消息渲染等）
├── ink/                  ← Ink 框架适配层（终端渲染引擎）
├── hooks/                ← React Hooks（权限、设置变更等）
│
├── Tool.ts               ← 【核心接口】工具类型定义
├── tools.ts              ← 【核心注册】工具注册表
├── tools/                ← 【核心实现】30+ 个工具实现
├── services/tools/       ← 【核心调度】工具执行引擎
│
├── services/             ← 服务层
│   ├── api/              ← Anthropic API 通信
│   ├── mcp/              ← MCP 协议客户端
│   ├── compact/          ← 上下文压缩
│   ├── analytics/        ← 遥测与 A/B（GrowthBook）
│   ├── plugins/          ← 插件系统
│   ├── oauth/            ← OAuth 认证
│   └── ...
│
├── state/                ← 应用状态管理（AppState Store）
├── context/              ← React Context（stats, fps, mailbox）
├── constants/            ← 常量与配置
├── types/                ← TypeScript 类型定义
├── utils/                ← 工具函数库
│   ├── permissions/      ← 权限规则引擎
│   ├── settings/         ← 设置管理
│   ├── git/              ← Git 操作封装
│   ├── memory/           ← 记忆系统
│   ├── swarm/            ← 多 Agent 协作
│   └── ...
│
├── skills/               ← 技能系统（bundled skills）
├── plugins/              ← 插件系统入口
├── coordinator/          ← 协调者模式（多 Agent）
├── assistant/            ← KAIROS 助手模式
├── tasks/                ← 后台任务实现
├── query/                ← 查询引擎
├── vim/                  ← Vim 模式支持
├── voice/                ← 语音模式
└── remote/               ← 远程会话
```

---

## 3. 核心架构图

```
┌─────────────────────────────────────────────────────────┐
│                    用户终端 (Terminal)                      │
└──────────────────────┬──────────────────────────────────┘
                       │ 用户输入
                       ▼
┌──────────────────────────────────────────────────────────┐
│  main.tsx (Commander.js CLI 解析)                         │
│  ├── 启动优化：MDM预读、Keychain预取、性能埋点             │
│  ├── 参数解析：--model, --print, --resume 等              │
│  ├── 认证检查：OAuth / API Key                            │
│  └── 启动模式选择：交互式 / 非交互式 / 远程               │
└──────────────────────┬───────────────────────────────────┘
                       │
          ┌────────────┼─────────────┐
          ▼            ▼             ▼
   ┌──────────┐ ┌──────────┐ ┌──────────────┐
   │ 交互REPL  │ │ 单次查询  │ │ 远程会话     │
   │ REPL.tsx  │ │ query.ts │ │ remote/      │
   └─────┬────┘ └─────┬────┘ └──────┬───────┘
         │            │             │
         ▼            ▼             ▼
┌──────────────────────────────────────────────────────────┐
│               App.tsx (React Context 树)                   │
│  AppStateProvider → StatsProvider → FpsMetricsProvider     │
│  └── MailboxProvider (Agent 间通信)                        │
│      └── VoiceProvider (语音模式)                          │
└──────────────────────┬───────────────────────────────────┘
                       │
                       ▼
┌──────────────────────────────────────────────────────────┐
│              REPL.tsx (主交互循环)                          │
│  ├── PromptInput (用户输入组件)                            │
│  ├── VirtualMessageList (消息列表渲染)                     │
│  ├── PermissionRequest (权限请求对话框)                    │
│  ├── Spinner (加载状态)                                    │
│  └── 命令路由 → commands/                                  │
└──────────────────────┬───────────────────────────────────┘
                       │ 用户消息 / 斜杠命令
                       ▼
┌──────────────────────────────────────────────────────────┐
│             Anthropic API (claude.ts / api/)               │
│  ├── 构建 system prompt（工具描述 + 上下文 + CLAUDE.md）   │
│  ├── 发送消息流                                            │
│  ├── 接收流式响应（文本 + 工具调用）                        │
│  └── 处理 tool_use / tool_result 循环                     │
└──────────────────────┬───────────────────────────────────┘
                       │ tool_use 响应
                       ▼
┌──────────────────────────────────────────────────────────┐
│         工具执行引擎 (services/tools/)                      │
│  ├── toolExecution.ts    ← 权限检查 + 调度入口             │
│  ├── StreamingToolExecutor.ts ← 流式执行器                 │
│  ├── toolHooks.ts        ← 钩子执行 (pre/post)            │
│  └── toolOrchestration.ts ← 编排协调                      │
└──────────────────────┬───────────────────────────────────┘
                       │ 分发到具体工具
          ┌────────────┼────────────┐
          ▼            ▼            ▼
   ┌──────────┐ ┌──────────┐ ┌──────────┐
   │ 内置工具  │ │ MCP 工具  │ │ Agent    │
   │ tools/   │ │ mcp/     │ │ AgentTool│
   └──────────┘ └──────────┘ └──────────┘
```

---

## 4. 核心数据流：一次对话的完整生命周期

### 4.1 用户输入

```
用户在终端输入 → PromptInput 组件捕获
  ├── 普通文本 → createUserMessage() 构建消息
  ├── /command → commands.ts 路由到对应命令处理
  ├── @file    → 附件解析 → AttachmentMessage
  └── !cmd     → 直接 shell 执行
```

关键文件：
- `src/components/PromptInput/PromptInput.tsx` — 输入框组件
- `src/utils/messages.ts` — 消息构建工具
- `src/commands.ts` — 命令路由表

### 4.2 API 调用

```
消息列表 + system prompt + 工具定义
  → Anthropic SDK 流式调用
  → 接收 text 块（直接渲染）
  → 接收 tool_use 块（进入工具执行）
```

关键文件：
- `src/services/api/` — API 通信层
- `src/constants/prompts.ts` — system prompt 模板
- `src/utils/systemPrompt.ts` — system prompt 组装

### 4.3 工具执行

```
API 返回 tool_use 块
  → toolExecution.ts 匹配工具
  → 权限检查 (PermissionRequest)
  → 工具执行 (Tool.execute())
  → 生成 tool_result 消息
  → 再次调用 API（循环直到模型停止调用工具）
```

关键文件：
- `src/services/tools/toolExecution.ts` — 执行入口
- `src/Tool.ts` — 工具接口定义
- `src/hooks/useCanUseTool.ts` — 权限检查 hook

### 4.4 上下文管理

```
消息累积 → token 估算
  ├── 未超限 → 继续对话
  └── 超限 → compact 服务压缩
       ├── 保留最近消息
       ├── 摘要早期消息
       └── 恢复对话继续
```

关键文件：
- `src/services/compact/compact.ts` — 压缩核心
- `src/services/tokenEstimation.ts` — token 估算

---

## 5. 关键模块速查表

### 5.1 工具系统

| 工具名 | 文件路径 | 功能 |
|--------|---------|------|
| BashTool | `tools/BashTool/` | Shell 命令执行 |
| FileReadTool | `tools/FileReadTool/` | 读取文件（支持图片/PDF） |
| FileEditTool | `tools/FileEditTool/` | 精确字符串替换编辑 |
| FileWriteTool | `tools/FileWriteTool/` | 创建/覆写文件 |
| GlobTool | `tools/GlobTool/` | 文件模式搜索 |
| GrepTool | `tools/GrepTool/` | 内容搜索 |
| AgentTool | `tools/AgentTool/` | 子 Agent 调度 |
| WebFetchTool | `tools/WebFetchTool/` | 网页抓取 |
| WebSearchTool | `tools/WebSearchTool/` | 网页搜索 |
| MCPTool | `tools/MCPTool/` | MCP 外部工具桥接 |
| TaskCreateTool | `tools/TaskCreateTool/` | 创建任务 |
| SendMessageTool | `tools/SendMessageTool/` | Agent 间通信 |
| SkillTool | `tools/SkillTool/` | 技能调用 |
| EnterPlanModeTool | `tools/EnterPlanModeTool/` | 进入计划模式 |

完整工具注册见 `src/tools.ts` → `getAllBaseTools()` 函数。

### 5.2 斜杠命令

| 命令 | 目录 | 功能 |
|------|------|------|
| /help | `commands/help/` | 帮助信息 |
| /compact | `commands/compact/` | 手动压缩上下文 |
| /config | `commands/config/` | 配置管理 |
| /mcp | `commands/mcp/` | MCP 服务管理 |
| /memory | `commands/memory/` | 记忆管理 |
| /review | `commands/review.js` | PR 审查 |
| /resume | `commands/resume/` | 恢复会话 |
| /login | `commands/login/` | 登录认证 |
| /model | (在 main.tsx 中) | 切换模型 |
| /clear | `commands/clear/` | 清空对话 |

完整命令列表见 `src/commands.ts`。

### 5.3 服务层

| 服务 | 路径 | 功能 |
|------|------|------|
| API 通信 | `services/api/` | 与 Anthropic API 交互 |
| MCP 客户端 | `services/mcp/` | MCP 协议实现 |
| 上下文压缩 | `services/compact/` | 上下文窗口管理 |
| 分析/遥测 | `services/analytics/` | GrowthBook + 事件追踪 |
| OAuth | `services/oauth/` | 认证流程 |
| 插件 | `services/plugins/` | 插件生命周期 |
| LSP | `services/lsp/` | 语言服务协议集成 |
| 记忆 | `services/SessionMemory/` | 会话记忆持久化 |

---

## 6. 全局状态架构

Claude Code 的状态管理分两层：

### 6.1 全局单例状态 (`bootstrap/state.ts`)

```
bootstrap/state.ts
  ├── originalCwd       ← 启动目录
  ├── projectRoot       ← 项目根目录
  ├── sessionId         ← 会话 ID
  ├── mainLoopModel     ← 当前模型
  ├── totalCostUSD      ← 累计费用
  ├── modelUsage        ← 按模型统计用量
  ├── meter/counters    ← OpenTelemetry 指标
  └── ... 其他运行时状态
```

这是一个用 `createSignal()` 实现的**响应式全局状态**，不依赖 React，可以在任何地方访问。

### 6.2 React 状态 (`state/AppStateStore.ts`)

```
AppStateStore
  ├── toolPermissionContext  ← 当前权限上下文
  ├── messages               ← 对话消息列表
  ├── mcp                    ← MCP 连接状态和工具
  ├── autoModeState          ← 自动模式状态
  └── ... UI 相关状态
```

通过 React Context (`AppStateProvider`) 下发到组件树。

---

## 7. 关键设计模式

### 7.1 Feature Flags (`bun:bundle`)

```typescript
// 通过 Bun 的 feature flag 系统控制条件编译
import { feature } from 'bun:bundle'

const coordinatorModeModule = feature('COORDINATOR_MODE')
  ? require('./coordinator/coordinatorMode.js')
  : null
```

很多模块通过 `feature()` 条件加载，做到**死代码消除**。

### 7.2 懒加载打破循环依赖

```typescript
// tools.ts 中的模式
const getTeamCreateTool = () =>
  require('./tools/TeamCreateTool/TeamCreateTool.js').TeamCreateTool
```

使用 `require()` 函数包装延迟加载，在函数调用时才解析模块，避免循环依赖。

### 7.3 工具接口统一

所有工具实现同一个 `Tool` 接口（定义在 `Tool.ts`），核心方法：
- `name` — 工具名称
- `prompt` — 给模型的工具描述
- `inputSchema` — Zod 定义的参数 schema
- `execute()` — 执行逻辑
- `isEnabled()` — 是否可用
- `validate()` — 参数验证

### 7.4 React Compiler 优化

```typescript
// 源码被 React Compiler 处理，会插入 memo 缓存
const $ = _c(13);  // compiler-runtime 的缓存实例
```

组件函数中会出现 `_c()` 调用和 `$[n]` 缓存，这是 React Compiler 自动插入的优化。

---

## 8. 模块依赖关系总图

```
main.tsx
  ├── entrypoints/init.ts          ← 初始化
  ├── bootstrap/state.ts           ← 全局状态
  ├── commands.ts                  ← 命令注册
  ├── tools.ts                     ← 工具注册
  ├── replLauncher.tsx             ← REPL 启动
  │     ├── components/App.tsx     ← Context 树
  │     └── screens/REPL.tsx       ← 主屏幕
  │           ├── hooks/           ← 业务逻辑 hooks
  │           ├── services/api/    ← API 调用
  │           ├── services/tools/  ← 工具执行
  │           └── services/mcp/    ← MCP 集成
  └── services/                    ← 各种服务初始化
```

---

## 9. 关键代码

### 9.1 全局状态管理

```typescript
// src/bootstrap/state.ts
// 使用 createSignal() 实现的响应式全局状态
import { createSignal } from 'react'

export const state = {
  sessionId: createSignal<string>(''),
  mainLoopModel: createSignal<string>('claude-opus-4-5'),
  totalCostUSD: createSignal<number>(0),
  modelUsage: createSignal<Record<string, number>>({}),
}

// 访问状态
const currentSession = state.sessionId.get()
const cost = state.totalCostUSD.get()
```

### 9.2 工具接口示例

```typescript
// src/Tool.ts
interface Tool<Input, Output> {
  readonly name: string
  readonly inputSchema: z.ZodType<Input>
  prompt(): Promise<string>
  call(args: Input, context: ToolUseContext): Promise<ToolResult<Output>>
  isEnabled(): boolean
  isReadOnly(args: Input): boolean
}
```

### 9.3 React Context 结构

```typescript
// src/components/App.tsx
function App({ children }) {
  return (
    <FpsMetricsProvider>
      <StatsProvider>
        <AppStateProvider>
          <MailboxProvider>
            <VoiceProvider>
              {children}
            </VoiceProvider>
          </MailboxProvider>
        </AppStateProvider>
      </StatsProvider>
    </FpsMetricsProvider>
  )
}
```

### 9.4 特征标志条件加载

```typescript
// 使用 Bun 的 feature flag 系统
import { feature } from 'bun:bundle'

// 条件编译
const coordinatorModule = feature('COORDINATOR_MODE')
  ? require('./coordinator/coordinatorMode.js')
  : null

// 懒加载打破循环依赖
const getTool = () => require('./tools/Tool.js').Tool
```

---

## 练习

1. **找入口**：阅读 `src/main.tsx` 的前 150 行，列出所有 CLI 参数（`--model`, `--print` 等）
2. **追踪工具注册**：打开 `src/tools.ts`，在 `getAllBaseTools()` 中数一数有多少工具是默认启用的
3. **理解状态**：阅读 `src/bootstrap/state.ts` 的 `State` 类型定义，理解有哪些全局状态
4. **追踪一次对话**：从 `src/screens/REPL.tsx` 入手，找到用户消息如何被发送到 API 的调用链

---

## 下一篇

👉 [01-entry-and-bootstrap.md](./01-entry-and-bootstrap.md) — 深入分析入口与启动流程
