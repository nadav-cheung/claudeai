# A08 - Agent 系统代码详解

> **本文档目标**：深入解析 Claude Code Agent 子代理系统的核心代码，包括 AgentTool.call()、runAgent()、forkSubagent()、团队管理等关键函数的实现。

---

## 1. Agent 工具入口：AgentTool.call()

**文件**：`src/tools/AgentTool/AgentTool.tsx:200-350`

**功能**：处理模型发出的 Agent 工具调用，分发到不同的执行模式。

### 1.1 输入 Schema

```typescript
// src/tools/AgentTool/AgentTool.tsx:100-130
const baseInputSchema = z.object({
  description: z.string(),              // 3-5 词任务描述
  prompt: z.string(),                  // 具体任务指令
  subagent_type: z.string().optional(), // Agent 类型
  model: z.enum(['sonnet', 'opus', 'haiku']).optional(),
  run_in_background: z.boolean().optional(), // 后台执行
})

const multiAgentInputSchema = z.object({
  name: z.string().optional(),          // Agent 名称（可寻址）
  team_name: z.string().optional(),     // 团队名
  mode: permissionModeSchema().optional(), // 权限模式
})

const isolationSchema = z.object({
  isolation: z.enum(['worktree', 'remote']).optional(),
  cwd: z.string().optional(),
})
```

### 1.2 执行模式判断

```typescript
// src/tools/AgentTool/AgentTool.tsx:200-250
async function call(input, context) {
  // 1. 解析 Agent 定义（内置或自定义）
  const agentDefinition = await resolveAgentDefinition(input)

  // 2. 判断执行模式
  const isAsync = input.run_in_background ?? false
  const isTeammate = !!input.team_name
  const isolation = input.isolation

  // 3. 选择执行路径
  if (isTeammate) {
    // 团队模式：创建 InProcessTeammateTask
    return runTeammateAgent(input, context, agentDefinition)
  }

  if (isAsync) {
    // 后台模式：创建 LocalAgentTask
    return runBackgroundAgent(input, context, agentDefinition)
  }

  if (isolation === 'worktree') {
    // Worktree 隔离模式
    return runIsolatedAgent(input, context, agentDefinition)
  }

  // 同步模式：直接执行
  return runSyncAgent(input, context, agentDefinition)
}
```

### 1.3 工具池组装

```typescript
// src/tools/AgentTool/AgentTool.tsx:250-300
async function assembleAgentToolPool(input, context, agentDefinition) {
  // 解析 allowedTools（可能是通配符）
  const allowedTools = parseAllowedTools(input.allowedTools)

  // 过滤 MCP 工具要求
  const filteredAgents = filterAgentsByMcpRequirements(agentDefinition)

  // 从工具注册表组装完整工具池
  const toolPool = assembleToolPool(
    context.permissionContext,
    context.mcpClients
  )

  // 应用 allowedTools 限制
  return filterToolsByAllowList(toolPool, allowedTools)
}
```

---

## 2. Agent 执行循环：runAgent()

**文件**：`src/tools/AgentTool/runAgent.ts:306-400`

**功能**：Agent 的主执行循环，类似于主会话的 query 循环。

```typescript
// src/tools/AgentTool/runAgent.ts:306-370
export async function* runAgent({
  agentDefinition,
  promptMessages,
  toolUseContext,
  canUseTool,
  isAsync,
  availableTools,
  forkContextMessages,
}: RunAgentParams): AsyncGenerator<Message, void> {

  // 1. 解析模型和权限
  const resolvedAgentModel = getAgentModel(agentDefinition, toolUseContext)
  const agentId = createAgentId()

  // 2. Fork 上下文处理（如果启用）
  const contextMessages = forkContextMessages
    ? filterIncompleteToolCalls(forkContextMessages)
    : []
  const initialMessages = [...contextMessages, ...promptMessages]

  // 3. 优化上下文（只读 Agent 省略 CLAUDE.md）
  const shouldOmitClaudeMd = agentDefinition.omitClaudeMd && !override?.userContext

  // 4. 初始化 Agent 专属 MCP 服务器
  const { clients, tools, cleanup } = await initializeAgentMcpServers(
    agentDefinition,
    toolUseContext.options.mcpClients
  )

  // 5. 创建子代理上下文
  const agentContext = createSubagentContext(toolUseContext, {
    options: { tools: availableTools },
    agentId,
    agentType: agentDefinition.agentType,
    abortController: isAsync ? new AbortController() : toolUseContext.abortController,
  })

  // 6. 执行主循环
  try {
    for await (const message of query({
      messages: initialMessages,
      systemPrompt: buildAgentSystemPrompt(agentDefinition, agentContext),
      canUseTool,
      toolUseContext: agentContext,
      model: resolvedAgentModel,
    })) {
      // 转发 API 指标
      if (message.type === 'stream_event') {
        toolUseContext.pushApiMetricsEntry?.(message.ttftMs)
        continue
      }

      // 记录 transcript
      if (isRecordableMessage(message)) {
        await recordSidechainTranscript([message], agentId)
        yield message
      }
    }
  } finally {
    // 清理资源
    await cleanup()
    clearSessionHooks(toolUseContext.setAppState, agentId)
    killShellTasksForAgent(agentId)
  }
}
```

---

## 3. Fork 机制：buildForkedMessages()

**文件**：`src/tools/AgentTool/forkSubagent.ts:466-500`

**功能**：在 Fork 模式下，克隆主会话的消息作为上下文前缀，共享 prompt cache。

```typescript
// src/tools/AgentTool/forkSubagent.ts:466
export function buildForkedMessages(
  parentMessages: Message[],      // 主会话消息历史
  promptMessages: Message[],       // Agent 的新 prompt
): Message[] {
  // 1. 过滤不完整的 tool_use（等待用户确认的）
  const filteredParent = filterIncompleteToolCalls(parentMessages)

  // 2. 拼接：主会话上下文 + Agent 新 prompt
  return [...filteredParent, ...promptMessages]
}

// 过滤不完整的 tool_call
function filterIncompleteToolCalls(messages: Message[]): Message[] {
  return messages.map(msg => {
    if (msg.role !== 'assistant') return msg

    // 移除 content 中正在等待 tool_use 结果的项
    const filteredContent = msg.content?.filter(block => {
      if (block.type !== 'tool_use') return true
      // 检查是否有对应的 tool_result
      return hasToolResultForToolUse(block.id, messages)
    })

    return { ...msg, content: filteredContent }
  })
}
```

**Fork vs 独立模式的区别**：

| 特性 | Fork 模式 | 独立模式 |
|------|----------|---------|
| 上下文 | 克隆主会话消息 | 仅 prompt |
| Prompt Cache | 共享主会话缓存 | 独立缓存 |
| 工具权限 | 继承主会话 | 可独立配置 |
| 适用场景 | Explore、Plan | 通用 Agent |

---

## 4. 团队创建：TeamCreateTool

**文件**：`src/tools/TeamCreateTool/TeamCreateTool.ts:50-150`

**功能**：创建多 Agent 协作团队。

```typescript
// src/tools/TeamCreateTool/TeamCreateTool.ts:50-100
async function call(input, context) {
  const { team_name, description, agent_type } = input

  // 1. 生成唯一团队名
  const uniqueTeamName = await generateUniqueTeamName(team_name)

  // 2. 创建团队目录
  const teamDir = `~/.claude/teams/${uniqueTeamName}/`
  await fs.mkdir(teamDir, { recursive: true })

  // 3. 写入团队配置文件
  const teamFile: TeamFile = {
    name: uniqueTeamName,
    description,
    createdAt: Date.now(),
    leadAgentId: `team-lead@${uniqueTeamName}`,
    leadSessionId: context.sessionId,
    members: [{
      agentId: `team-lead@${uniqueTeamName}`,
      name: 'team-lead',
      joinedAt: Date.now(),
      tmuxPaneId: generateTmuxPaneId(),
      cwd: process.cwd(),
    }]
  }
  await writeTeamFile(uniqueTeamName, teamFile)

  // 4. 注册会话清理
  registerTeamForSessionCleanup(uniqueTeamName)

  // 5. 创建任务目录
  await fs.mkdir(`~/.claude/tasks/${uniqueTeamName}/`, { recursive: true })

  return {
    success: true,
    result: {
      teamName: uniqueTeamName,
      message: `Team '${uniqueTeamName}' created successfully`
    }
  }
}
```

### 4.1 团队文件格式

```typescript
// src/utils/swarm/teamHelpers.ts
type TeamFile = {
  name: string
  description?: string
  createdAt: number
  leadAgentId: string          // "team-lead@team-name"
  leadSessionId?: string
  hiddenPaneIds?: string[]
  members: Array<{
    agentId: string           // "researcher@my-team"
    name: string              // "researcher"
    agentType?: string
    tmuxPaneId: string
    cwd: string
    worktreePath?: string
    sessionId?: string
    subscriptions: string[]   // 订阅的频道
    isActive?: boolean
    mode?: PermissionMode
  }>
}
```

---

## 5. 消息传递：SendMessageTool

**文件**：`src/tools/SendMessageTool/SendMessageTool.ts:100-200`

**功能**：Agent 之间传递消息，支持直接寻址和广播。

```typescript
// src/tools/SendMessageTool/SendMessageTool.ts:100-150
async function call(input, context) {
  const { to, message } = input

  // 1. 解析目标地址
  const address = parseAddress(to)
  //    "researcher"      → teammate 名
  //    "*"               → 广播
  //    "uds:<path>"      → UDS 本地对等
  //    "bridge:<session>" → Remote Control

  // 2. 查找目标 Agent
  const targetAgent = await findAgentByAddress(address)

  // 3. 结构化消息（如果是协议消息）
  const structuredMessage = structureProtocolMessage(message)
  //    shutdown_request / shutdown_response
  //    plan_approval_response
  //    其他自由文本

  // 4. 投递消息
  if (address.type === 'teammate') {
    // 写入队友邮箱
    await writeToMailbox(targetAgent.agentId, structuredMessage)
  } else if (address.type === 'broadcast') {
    // 广播：遍历所有成员
    const teamMembers = await getTeamMembers(address.teamName)
    for (const member of teamMembers) {
      await writeToMailbox(member.agentId, structuredMessage)
    }
  }

  return {
    success: true,
    result: { delivered: true, recipients: address.type === 'broadcast' ? 'all' : to }
  }
}
```

### 5.1 Mailbox 机制

```typescript
// src/utils/mailbox.ts
type Mailbox = {
  messages: ProtocolMessage[]
  unreadCount: number
  lastReadTimestamp: number
}

// 写入邮箱
async function writeToMailbox(agentId: string, message: ProtocolMessage): Promise<void> {
  const mailboxPath = getMailboxPath(agentId)
  const mailbox = await readMailbox(mailboxPath)
  mailbox.messages.push(message)
  mailbox.unreadCount++
  await writeMailbox(mailboxPath, mailbox)
}
```

---

## 6. 关键源码文件索引

| 文件 | 关键函数/类 | 说明 |
|------|-----------|------|
| `src/tools/AgentTool/AgentTool.tsx` | `AgentTool.call()` | Agent 工具入口 |
| `src/tools/AgentTool/runAgent.ts` | `runAgent()` | Agent 执行循环 |
| `src/tools/AgentTool/forkSubagent.ts` | `buildForkedMessages()` | Fork 上下文构建 |
| `src/tools/AgentTool/builtInAgents.ts` | `builtInAgents` | 内置 Agent 定义 |
| `src/tools/TeamCreateTool/TeamCreateTool.ts` | `TeamCreateTool.call()` | 团队创建 |
| `src/tools/SendMessageTool/SendMessageTool.ts` | `SendMessageTool.call()` | 消息传递 |
| `src/utils/swarm/teamHelpers.ts` | `readTeamFile()`, `writeTeamFile()` | 团队文件管理 |
| `src/utils/mailbox.ts` | `writeToMailbox()`, `readMailbox()` | 邮箱机制 |
| `src/tasks/LocalAgentTask/LocalAgentTask.tsx` | `LocalAgentTask` | 本地后台任务 |
| `src/tasks/InProcessTeammateTask/InProcessTeammateTask.tsx` | `InProcessTeammateTask` | 进程内队友任务 |
