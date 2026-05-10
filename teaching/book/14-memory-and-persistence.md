# 14 - 记忆与持久化

> **本章目标**：深入理解 Claude Code 如何保存会话记忆、在不同会话间保持上下文、以及如何实现长期记忆。

---

## 1. 准备工作

### 1.1 阅读源码

**必读**：
- `src/services/memory/` - 记忆服务
- `src/bootstrap/state.ts` - 状态持久化

### 1.2 本章与 Mini-Claude 的关系

| Mini-Claude | Claude Code |
|-------------|-------------|
| 无持久化 | JSON 文件存储 |
| 无会话恢复 | 支持 resume |
| 无学习能力 | 长期记忆 |

---

## 2. 记忆类型

Claude Code 使用多种记忆机制：

```text
┌─────────────────────────────────────────────────────┐
│               Claude Code 记忆系统                     │
├─────────────────────────────────────────────────────┤
│                                                     │
│  1. 工作记忆（Working Memory）                        │
│     └── 当前会话的消息历史                            │
│                                                     │
│  2. 短期记忆（Short-term Memory）                    │
│     └── 最近几次会话的摘要                            │
│                                                     │
│  3. 长期记忆（Long-term Memory）                    │
│     └── 项目知识、用户偏好、学习到的模式               │
│                                                     │
└─────────────────────────────────────────────────────┘
```

---

## 3. 会话持久化

### 3.1 Mini-Claude 的简单存储

```typescript
// Mini-Claude: 简单的 JSON 存储
class SimpleSessionStore {
  private sessions: Map<string, Message[]> = new Map();

  save(sessionId: string, messages: Message[]) {
    const data = JSON.stringify({ messages, timestamp: Date.now() });
    fs.writeFile(`./sessions/${sessionId}.json`, data);
  }

  load(sessionId: string): Message[] | null {
    try {
      const data = fs.readFile(`./sessions/${sessionId}.json`, 'utf-8');
      return JSON.parse(data).messages;
    } catch {
      return null;
    }
  }
}
```

### 3.2 Claude Code 的会话管理

```typescript
// services/memory/sessionStore.ts (简化)
interface Session {
  id: string;
  messages: Message[];
  createdAt: Date;
  updatedAt: Date;
  metadata: {
    projectPath: string;
    model: string;
    cost: number;
  };
}

class SessionStore {
  private basePath: string;

  constructor(basePath: string) {
    this.basePath = basePath;
  }

  async save(session: Session): Promise<void> {
    const path = this.getSessionPath(session.id);
    await fs.mkdir(path, { recursive: true });

    await fs.writeFile(
      path.join('session.json'),
      JSON.stringify(session, null, 2)
    );
  }

  async load(sessionId: string): Promise<Session | null> {
    const path = this.getSessionPath(sessionId);

    try {
      const content = await fs.readFile(path.join('session.json'), 'utf-8');
      return JSON.parse(content);
    } catch {
      return null;
    }
  }

  async list(): Promise<Session[]> {
    const sessions: Session[] = [];
    const dirs = await fs.readdir(this.basePath);

    for (const dir of dirs) {
      const session = await this.load(dir);
      if (session) {
        sessions.push(session);
      }
    }

    return sessions.sort((a, b) =>
      b.updatedAt.getTime() - a.updatedAt.getTime()
    );
  }

  private getSessionPath(sessionId: string): string {
    return path.join(this.basePath, sessionId);
  }
}
```

---

## 4. 会话恢复

### 4.1 Resume 模式

当用户使用 `--resume` 时：

```typescript
// main.tsx (简化)
async function resumeSession(sessionId: string) {
  // 1. 加载会话
  const session = await sessionStore.load(sessionId);

  if (!session) {
    throw new Error(`Session not found: ${sessionId}`);
  }

  // 2. 恢复状态
  state.sessionId.set(sessionId);
  state.messages.set(session.messages);

  // 3. 更新 system prompt（添加会话上下文）
  state.systemPrompt.set(
    buildResumePrompt(session)
  );

  // 4. 启动 REPL
  await replLauncher.launch();
}
```

### 4.2 Resume System Prompt

```typescript
function buildResumePrompt(session: Session): string {
  return `这是恢复的会话。

上次会话时间: ${session.updatedAt}
项目: ${session.metadata.projectPath}

最近的对话摘要:
${summarizeMessages(session.messages.slice(-10))}

请继续帮助用户完成他们的任务。`;
}
```

---

## 5. 项目记忆

### 5.1 项目上下文

Claude Code 为每个项目维护上下文：

```typescript
// services/memory/projectMemory.ts (简化)
interface ProjectMemory {
  projectPath: string;
  lastActivity: Date;
  summary: string;           // 项目摘要（AI 生成）
  keyFiles: string[];       // 重要文件
  userPreferences: {
    preferredTools: string[];
    autoApprove: boolean;
  };
  learnedPatterns: string[]; // 学习到的模式
}

class ProjectMemoryStore {
  private getMemoryPath(projectPath: string): string {
    return path.join(projectPath, '.claude', 'memory.json');
  }

  async load(projectPath: string): Promise<ProjectMemory> {
    const memoryPath = this.getMemoryPath(projectPath);

    try {
      const content = await fs.readFile(memoryPath, 'utf-8');
      return JSON.parse(content);
    } catch {
      // 返回默认记忆
      return {
        projectPath,
        lastActivity: new Date(),
        summary: '',
        keyFiles: [],
        userPreferences: { preferredTools: [], autoApprove: false },
        learnedPatterns: [],
      };
    }
  }

  async save(memory: ProjectMemory): Promise<void> {
    const memoryPath = this.getMemoryPath(memory.projectPath);
    await fs.mkdir(path.dirname(memoryPath), { recursive: true });
    await fs.writeFile(memoryPath, JSON.stringify(memory, null, 2));
  }
}
```

### 5.2 学习机制

```typescript
// 学习用户偏好
async function learnFromInteraction(
  memory: ProjectMemory,
  interaction: Interaction
): Promise<void> {
  // 分析交互
  if (interaction.toolUsed === 'Bash' &&
      interaction.command.includes('npm test')) {
    // 用户经常运行测试
    memory.learnedPatterns.push('user_runs_tests_often');
  }

  if (interaction.autoApproved) {
    // 用户经常自动批准某工具
    memory.userPreferences.autoApprove = true;
  }

  // 保存更新后的记忆
  await projectMemoryStore.save(memory);
}
```

---

## 6. 记忆检索

### 6.1 语义搜索

Claude Code 可以搜索历史记忆：

```typescript
// 搜索记忆
async function searchMemory(query: string): Promise<MemoryResult[]> {
  const allProjects = await getAllProjectPaths();

  const results: MemoryResult[] = [];

  for (const projectPath of allProjects) {
    const memory = await projectMemoryStore.load(projectPath);

    // 简单关键词匹配
    if (memory.summary.includes(query) ||
        memory.learnedPatterns.some(p => p.includes(query))) {
      results.push({
        project: projectPath,
        relevance: calculateRelevance(memory, query),
        memory,
      });
    }
  }

  // 按相关性排序
  return results.sort((a, b) => b.relevance - a.relevance);
}
```

---

## 7. 实战练习

### 7.1 练习：实现简单的会话保存

**目标**：为 Mini-Claude 添加会话保存功能

**答案要点**：
```typescript
class PersistentSessionStore {
  private storePath = path.join(os.homedir(), '.mini-claude', 'sessions');

  async save(sessionId: string, messages: Message[]): Promise<void> {
    const filePath = path.join(this.storePath, `${sessionId}.json`);
    await fs.mkdir(this.storePath, { recursive: true });

    await fs.writeFile(filePath, JSON.stringify({
      id: sessionId,
      messages,
      savedAt: new Date().toISOString(),
    }, null, 2));
  }

  async load(sessionId: string): Promise<Message[] | null> {
    const filePath = path.join(this.storePath, `${sessionId}.json`);

    try {
      const content = await fs.readFile(filePath, 'utf-8');
      const data = JSON.parse(content);
      return data.messages;
    } catch {
      return null;
    }
  }

  async list(): Promise<string[]> {
    await fs.mkdir(this.storePath, { recursive: true });
    const files = await fs.readdir(this.storePath);
    return files
      .filter(f => f.endsWith('.json'))
      .map(f => f.replace('.json', ''));
  }
}
```

---

## 8. 总结

| 方面 | Mini-Claude | Claude Code |
|------|-------------|-------------|
| 会话保存 | 无 | JSON 文件 |
| 会话恢复 | 无 | --resume |
| 项目记忆 | 无 | 完整 |
| 学习能力 | 无 | 模式学习 |
| 语义搜索 | 无 | 记忆检索 |

---

## 下一篇

👉 [15 - Skills与插件系统](../10-skills-and-plugins.md) —— 深入理解 Skills

`★ Insight ─────────────────────────────────────`
记忆系统的设计体现了**分层存储**的思想：工作记忆（当前会话）→ 短期记忆（最近会话）→ 长期记忆（项目知识）。不同层级的记忆有不同的精度和访问频率。Claude Code 根据任务需要动态地从各层提取信息，这比把所有东西都塞进上下文高效得多。
`─────────────────────────────────────────────────`
