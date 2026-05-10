# 13 - Agent 与多 Agent 协作

> **本章目标**：深入理解 Claude Code 的 Agent 模式——一个可以调用其他 Agent 的 Agent，以及多 Agent 协作模式。

---

## 1. 准备工作

### 1.1 阅读源码

**必读**：
- `src/tools/AgentTool/` - Agent 工具实现
- `src/coordinator/` - 多 Agent 协调器

### 1.2 本章与 Mini-Claude 的关系

Mini-Claude **没有** Agent 功能 —— 这是 Claude Code 的高级特性。

---

## 2. 什么是 Agent？

### 2.1 Agent 的定义

在 Claude Code 中，**Agent** 是一个可以：
1. 接收任务描述
2. 使用工具完成任务
3. 创建子 Agent 协作

```text
Agent 模式
┌─────────────────────────────────────────────────────┐
│                                                     │
│   用户 ──▶ Agent ──┬──▶ 工具执行                     │
│                   │                                 │
│                   └──▶ 子Agent ──▶ 工具执行          │
│                                    │               │
│                                    └──▶ 工具执行    │
│                                                     │
└─────────────────────────────────────────────────────┘
```

### 2.2 为什么需要 Agent？

当任务太复杂时，一个 Agent 可能无法完成：

```text
任务：重构整个项目
        │
        ├── 子任务1：分析代码结构 → Agent A
        ├── 子任务2：修改测试 → Agent B
        ├── 子任务3：更新文档 → Agent C
        └── 子任务4：验证修改 → Agent D
```

---

## 3. AgentTool 实现

### 3.1 AgentTool 接口

```typescript
// tools/AgentTool/ (简化)
export class AgentTool implements Tool {
  name = 'Agent';
  description = '创建一个子Agent来执行任务';

  input_schema = {
    type: 'object',
    properties: {
      prompt: {
        type: 'string',
        description: '给子Agent的任务描述',
      },
      agent: {
        type: 'string',
        enum: ['default', 'coding', 'review'],
        description: 'Agent类型',
      },
    },
    required: ['prompt'],
  };

  async execute(args: { prompt: string; agent?: string }, context: ToolContext) {
    // 创建一个新的 Agent 实例
    const subAgent = await createAgent({
      prompt: args.prompt,
      type: args.agent || 'default',
      parentContext: context,
    });

    // 执行任务
    const result = await subAgent.run();

    return {
      success: true,
      result: result.summary,
    };
  }
}
```

### 3.2 Agent 创建

```typescript
// coordinator/agentFactory.ts (简化)
async function createAgent(options: AgentOptions): Promise<Agent> {
  // 1. 继承父 Agent 的上下文
  const context = inheritContext(options.parentContext);

  // 2. 添加任务特定的 System Prompt
  context.addSystemMessage(options.prompt);

  // 3. 限制工具权限（子 Agent 可能权限更小）
  context.restrictTools(options.restrictedTools || []);

  // 4. 创建 Agent 实例
  return new Agent(context);
}

class Agent {
  private context: AgentContext;

  constructor(context: AgentContext) {
    this.context = context;
  }

  async run(): Promise<AgentResult> {
    while (!this.context.isComplete()) {
      // 思考下一步
      const action = await this.context.think();

      if (action.type === 'tool') {
        // 执行工具
        await this.context.executeTool(action.tool, action.args);
      } else if (action.type === 'message') {
        // 发送消息给父 Agent
        return { summary: action.content };
      }
    }
  }
}
```

---

## 4. 多 Agent 协作模式

### 4.1 串行模式

```
Agent A → Agent B → Agent C
   │          │          │
 完成task1  完成task2  完成task3
```

### 4.2 并行模式

```
       ┌→ Agent B →┐
Agent A ┤           ├→ Agent D
       └→ Agent C →┘
```

### 4.3 层次模式

```
        Agent A (Manager)
       /      |      \
  Agent B  Agent C  Agent D
  (设计)   (实现)   (测试)
```

---

## 5. Claude Code 的协调器模式

### 5.1 Coordinator

```typescript
// coordinator/coordinator.ts (简化)
export class Coordinator {
  private agents: Map<string, Agent> = new Map();

  // 创建团队
  async createTeam(task: string): Promise<void> {
    // 主 Agent（经理）
    const manager = await this.createAgent({
      role: 'manager',
      prompt: `管理任务: ${task}`,
      canDelegate: true,  // 可以分配子任务
    });

    // 专家 Agents
    const coder = await this.createAgent({
      role: 'coder',
      prompt: '负责代码编写',
      tools: ['Read', 'Write', 'Bash'],
    });

    const reviewer = await this.createAgent({
      role: 'reviewer',
      prompt: '负责代码审查',
      tools: ['Read', 'Grep'],
    });

    this.agents.set('manager', manager);
    this.agents.set('coder', coder);
    this.agents.set('reviewer', reviewer);
  }

  // 协调执行
  async coordinate(): Promise<void> {
    const manager = this.agents.get('manager')!;

    while (!manager.isComplete()) {
      const action = await manager.decide();

      if (action.type === 'delegate') {
        const agent = this.agents.get(action.agent);
        if (agent) {
          await agent.execute(action.task);
        }
      }
    }
  }
}
```

---

## 6. 消息传递

### 6.1 Agent 间通信

当子 Agent 需要与父 Agent 通信时：

```typescript
// Agent 消息传递
interface AgentMessage {
  from: string;
  to: string;
  type: 'result' | 'error' | 'ask';
  content: string;
}

class Agent {
  private inbox: AgentMessage[] = [];

  async receive(message: AgentMessage): Promise<void> {
    this.inbox.push(message);
  }

  async send(to: string, type: AgentMessage['type'], content: string): Promise<void> {
    const message: AgentMessage = {
      from: this.id,
      to,
      type,
      content,
    };

    // 通过协调器发送
    await coordinator.route(message);
  }
}
```

---

## 7. Mini-Claude 的简单实现

### 7.1 基础任务队列

```typescript
// Mini-Claude: 简单的任务队列
class SimpleTaskQueue {
  private tasks: string[] = [];
  private results: Map<string, string> = new Map();

  addTask(task: string) {
    this.tasks.push(task);
  }

  async processAll() {
    const results = [];

    for (const task of this.tasks) {
      const result = await this.processTask(task);
      results.push(result);
    }

    return results;
  }

  private async processTask(task: string): Promise<string> {
    // 简单处理
    return `Processed: ${task}`;
  }
}
```

---

## 9. 练习

### 练习 1：实现简单的任务队列

**目标**：为 Mini-Claude 添加任务队列支持

**提示**：
- 使用数组存储任务
- 按顺序处理任务

**答案要点**：
```typescript
class TaskQueue {
  private queue: Task[] = [];
  private processing = false;

  async add(task: Task) {
    this.queue.push(task);
    if (!this.processing) {
      await this.process();
    }
  }

  private async process() {
    this.processing = true;
    while (this.queue.length > 0) {
      const task = this.queue.shift()!;
      await this.execute(task);
    }
    this.processing = false;
  }

  private async execute(task: Task) {
    console.log(`执行任务: ${task.name}`);
    // 处理逻辑
  }
}
```

### 练习 2：实现 Agent 结果聚合

**目标**：收集多个 Agent 的结果并汇总

**提示**：
- 使用 `Promise.all()` 并行执行
- 聚合结果数组

**答案要点**：
```typescript
async function aggregateAgentResults(agents: Agent[]): Promise<string> {
  const results = await Promise.all(
    agents.map(agent => agent.execute())
  );

  return results
    .map((r, i) => `Agent ${i + 1}: ${r}`)
    .join('\n');
}
```

### 练习 3：分析 Claude Code Agent 代码结构

**目标**：在源码中找到 Agent 相关的关键文件

**步骤**：
1. 运行 `grep -r "class Agent" src/`
2. 查看 `src/tools/AgentTool/`
3. 追踪 `runAgent()` 调用链

**答案要点**：
- `AgentTool.tsx` - Agent 工具入口
- `runAgent.ts` - Agent 执行循环
- `forkSubagent.ts` - 子 Agent 创建

---

## 8. 总结

| 方面 | Mini-Claude | Claude Code |
|------|-------------|-------------|
| Agent 模式 | 无 | 完整 |
| 子 Agent | 无 | 支持 |
| 工具限制 | 全部可用 | 可配置 |
| 多 Agent 协调 | 无 | 协调器模式 |
| 消息传递 | 无 | 结构化消息 |

---

## 下一篇

👉 [14 - 记忆与持久化](../09-memory-and-persistence.md) —— 深入理解会话如何保存

`★ Insight ─────────────────────────────────────`
Agent 模式的核心是**分而治之**——把复杂任务拆分成简单任务，交给专门的 Agent 处理。关键设计点包括：Agent 间的通信机制、工具权限的限制（子 Agent 不应该有父 Agent 的全部权限）、以及如何协调多个 Agent 的工作。
`─────────────────────────────────────────────────`
