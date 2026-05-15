# 附录 B：核心函数速查表

按章节/驿站分组，列出 Claude Code 源码中最关键的函数及其职责。

---

### ① 入口（ch03）

| 函数 | 文件 | 一句话描述 |
|------|------|-----------|
| `main()` | `cli.tsx` | CLI 入口调度员，快速路径路由 |
| `main()` | `main.tsx` | 完整 CLI 初始化（认证、Bootstrap、工具组装） |
| `init()` | `init.ts` | 一次性初始化（memoized） |

---

### ② 消息（ch04）

| 函数 | 文件 | 一句话描述 |
|------|------|-----------|
| `handlePromptSubmit()` | `handlePromptSubmit.ts` | 处理用户提交 |
| `processUserInput()` | `processUserInput.ts` | 输入模式路由 |
| `processTextPrompt()` | `processTextPrompt.ts` | 文本输入处理 |
| `createUserMessage()` | `messages.ts` | 创建消息对象 |

---

### ③ 查询引擎准备（ch05–ch06）

| 函数 | 文件 | 一句话描述 |
|------|------|-----------|
| `getSystemPrompt()` | `prompts.ts` | 组装 system prompt（静态区 + 动态区） |
| `getSystemContext()` | `context.ts` | 获取 Git 状态（memoized） |
| `getUserContext()` | `context.ts` | 加载 CLAUDE.md（memoized） |
| `getMemoryFiles()` | `claudemd.ts` | 遍历加载 CLAUDE.md 文件 |
| `getTools()` | `tools.ts` | 组装工具列表 |
| `assembleToolPool()` | `tools.ts` | 合并内置工具 + MCP 工具 |
| `buildTool()` | `Tool.ts` | 工厂函数，从定义创建可执行工具对象 |

---

### ③ 查询引擎（ch07）

| 函数 | 文件 | 一句话描述 |
|------|------|-----------|
| `query()` | `query.ts` | AsyncGenerator 入口，启动查询流 |
| `queryLoop()` | `query.ts` | while(true) 九步循环——核心心脏 |
| `productionDeps()` | `deps.ts` | 依赖注入，绑定真实 API 调用 |
| `queryModelWithStreaming()` | `claude.ts` | 流式 API 调用，返回 AsyncGenerator |

---

### ④ 权限（ch11）

| 函数 | 文件 | 一句话描述 |
|------|------|-----------|
| `hasPermissionsToUseTool()` | `permissions.ts` | 权限检查主入口 |
| `hasPermissionsToUseToolInner()` | `permissions.ts` | 分层检查实现（白名单 → 规则 → 用户确认） |
| `bashToolHasPermission()` | `bashPermissions.ts` | Bash 命令安全分析 |
| `COMMAND_ALLOWLIST` | `readOnlyValidation.ts` | 只读命令白名单常量 |
| `initialPermissionModeFromCLI()` | `permissionSetup.ts` | 根据 CLI 参数确定初始权限模式 |

---

### ⑤ 工具执行（ch08）

| 函数 | 文件 | 一句话描述 |
|------|------|-----------|
| `addTool()` | `StreamingToolExecutor.ts` | 添加工具到并发执行队列 |
| `canExecuteTool()` | `StreamingToolExecutor.ts` | 判断工具是否满足并发安全条件 |
| `checkPermissionsAndCallTool()` | `toolExecution.ts` | 权限检查 + 执行的 5 步链 |

---

### ⑥ 状态管理（ch09）

| 函数/概念 | 文件 | 一句话描述 |
|----------|------|-----------|
| `State`（type） | `query.ts` | 循环可变状态的类型定义 |
| 三阶段恢复 | `query.ts` | Collapse drain → Reactive Compact → Max Token 升级 |
| `handleStopHooks()` | `query.ts` | 会话结束时的 Stop hook 处理 |

---

### ⑦ 渲染（ch10）

| 函数 | 文件 | 一句话描述 |
|------|------|-----------|
| `render()` | `ink.tsx` | React 树挂载到终端 |
| `onRender()` | `ink.tsx` | 帧渲染管线，计算布局并输出 |
| `handleMessageFromStream()` | `messages.ts` | 流式事件分发到状态更新 |
| `MessageImpl()` | `Message.tsx` | 消息类型分发渲染组件 |
