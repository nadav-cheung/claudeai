# 快速入门：Java开发者视角的Claude Code学习路径

> **本指南目标**：帮助Java开发者用已有的知识快速理解Claude Code的核心概念。通过类比Spring/Hibernate/MyBatis等熟悉的技术，让你在30分钟内建立整体架构直觉。

---

## 学习路径图

```
用户输入 → 命令解析 → 工具执行 → API调用 → 输出
    │           │            │           │
    ↓           ↓            ↓           ↓
 Prompt    Commander.js   runToolUse  messages
 Input     斜杠命令      权限检查    create

类比：DispatcherServlet → @Controller → TransactionTemplate → RestTemplate
```

---

## 1. 核心组件对照

| Claude Code | Java Spring | 说明 |
|-------------|-------------|------|
| `main.tsx` | `DispatcherServlet` | 请求入口，参数解析 |
| `commands/` | `@Controller` + `@RequestMapping` | 斜杠命令（/help, /compact） |
| `tools/` | `@Service` + `@Repository` | 工具实现（文件读写、搜索） |
| `toolExecution.ts` | `TransactionTemplate` | 事务管理，权限控制 |
| `services/api/claude.ts` | `RestTemplate`/`WebClient` | 外部API调用 |
| `bootstrap/state.ts` | `ApplicationContext` | 全局单例Bean |

---

## 2. 工具系统：策略模式

**Java策略模式**：
```java
public interface PaymentStrategy {
    PayResult pay(PaymentRequest request);
}
```

**Claude Code等效实现**：
```typescript
interface Tool {
  name: string;
  call(input: unknown, context: ToolUseContext): Promise<ToolResult>;
}

const tools = {
  'Read': { call: async (input) => readFile(input.path) },
  'Write': { call: async (input) => writeFile(input.path, input.content) },
};
```

**关键差异**：TypeScript的`Tool`接口更"胖"——除了`call`还有`description`、`inputSchema`等30+方法。这让工具自描述，但实现复杂度更高。

---

## 3. 权限系统：类比Spring Security

**Spring Security流程**：
```
请求 → FilterChain → AccessDecisionManager → 目标方法
```

**Claude Code权限流程**：
```
工具调用 → checkPermissions() → PermissionRule解析 → 用户确认/自动通过
```

**配置对比**：

| 方面 | Spring Security | Claude Code |
|------|----------------|-------------|
| 匹配方式 | Ant路径 + SpEL | Glob模式 |
| 条件 | `.hasRole()`, `.hasAuthority()` | `allow`, `disallow`, `require-approval` |

---

## 4. 状态管理：Signal vs Bean

**Spring Bean**：
```java
@Component
@Scope("singleton")  // 默认单例
public class UserService { }
```

**Claude Code Signal**：
```typescript
export const state = {
  sessionId: createSignal<string>(''),
  currentModel: createSignal<string>('claude-opus-4-7'),
};

const sessionId = state.sessionId.get();
state.sessionId.set('new-session-id');
```

| 方面 | Spring Bean | Claude Code Signal |
|------|-------------|-------------------|
| 创建 | `@Bean`/`@Component` | `createSignal(initialValue)` |
| 变更通知 | 依赖注入 + AOP | 订阅者模式 |

---

## 5. API调用：RestTemplate vs AsyncGenerator

**Java同步调用**：
```java
ResponseEntity<MessageResponse> response = restTemplate.exchange(
    "https://api.anthropic.com/v1/messages",
    HttpMethod.POST, entity, MessageResponse.class);
```

**TypeScript流式调用**：
```typescript
export async function* createMessageStream(request: CreateMessageRequest) {
  const response = await api.messages.create({ stream: true, ... });
  for await (const event of response) {
    yield event;
  }
}
```

| 方面 | RestTemplate | TypeScript AsyncGenerator |
|------|-------------|--------------------------|
| 响应方式 | 同步等待全部返回 | 流式逐块返回 |
| 取消 | 难（线程中断） | `AbortController` |

---

## 6. 上下文压缩：类比Hibernate一级缓存

**Hibernate L1缓存**：同一Session内，同一ID的实体只查询一次。

**Claude Code上下文压缩**：当messages超过200K tokens时，AI生成摘要替换原始内容。

| 方面 | Hibernate L1 Cache | Claude Code Compact |
|------|-------------------|-------------------|
| 触发条件 | `session.get()` 同一ID | messages超200K tokens |
| 粒度 | 实体级别 | 对话轮次级别 |
| 压缩方式 | 不变，直接缓存实体 | AI生成摘要替换 |

---

## 7. 设计模式对照

| Java 模式 | Claude Code 实现 |
|-----------|------------------|
| 工厂模式 | `buildTool()` |
| 策略模式 | `Tool` 接口 |
| 模板方法 | `runAgent()` |
| 观察者模式 | `Signal` 订阅 |
| 责任链模式 | `Hook` 链 |

---

## 8. 快速实验清单

### 实验1：追踪完整对话
```bash
CLAUDE_DEBUG=1 claude
# 观察：消息构建 → API调用 → 工具执行
```

### 实验2：理解工具执行
在 `tools/FileReadTool/` 中添加日志，观察调用流程。

### 实验3：理解权限流程
```bash
cat ~/.claude/settings.json | jq '.permissions'
```

---

## 9. 下一步学习

| 你的目标 | 推荐章节 |
|---------|---------|
| 理解工具系统设计 | 第3章：工具系统 |
| 深入权限机制 | 第5章：权限系统 |
| 理解上下文压缩 | 第6章：上下文管理与压缩 |
| 学习MCP集成 | 第7章：MCP协议集成 |
| 理解Agent协作 | 第8章：Agent与多Agent协作 |

---

## 10. 常见问题FAQ

**Q: 为什么TypeScript选择`buildTool()`工厂而不是继承？**

A: 工厂模式更灵活。Java的继承是编译时绑定，而TypeScript的对象字面量可以在运行时组合。

**Q: Signal和Spring Bean有什么区别？**

A: Signal是发布-订阅模式，Bean是依赖注入。Signal适合响应式UI更新，Bean适合服务间协作。

**Q: 上下文压缩会丢失信息吗？**

A: 会，但Claude Code设计了多层保护：
1. Microcompact保留最新消息不做压缩
2. 工具调用结果只保留摘要
3. 关键信息（如CLAUDE.md指令）永不压缩

---

`★ Insight ─────────────────────────────────────`
Java开发者学习Claude Code的关键，是理解TypeScript的"对象字面量 + 接口组合"模式替代了Java的"类继承 + 注解"。TypeScript的灵活性来自结构化类型和鸭式辨型，Java的安全性来自显式声明和编译时检查。这不是优劣之分，而是不同语言设计哲学的体现。
`─────────────────────────────────────────────────`

---

## 附录：完整概念对照表

### 核心组件

| Java 组件 | Claude Code 组件 |
|-----------|-----------------|
| `DispatcherServlet` | `main.tsx` |
| `@Controller` | `commands/` |
| `@Service` | `tools/` |
| `@Repository` | `toolExecution.ts` |
| `ApplicationContext` | `bootstrap/state.ts` |
| `Bean` | `Signal` |
| `Filter` | `Hook` |

### 生态系统

| Java 生态 | Claude Code 生态 |
|-----------|-----------------|
| Spring Boot | Claude Code CLI |
| Spring Security | 权限系统 |
| HikariCP | API 预连接 |
| MyBatis | 会话存储 |
| JUnit 5 | Vitest |
| Maven/Gradle | Bun |
| YAML 配置 | JSON 配置 |

### 推荐学习顺序

```
1. 入门
   └── quick-start.md（本文件）
   └── 00-overview.md（全局架构）

2. 核心流程
   └── 01-entry-and-bootstrap.md（启动）
   └── 03-tool-system.md（工具）
   └── 04-tool-execution.md（执行）

3. 安全与协作
   └── 05-permission-system.md（权限）
   └── 08-agent-and-team.md（Agent）

4. 深入主题
   └── 06-context-and-compact.md（压缩）
   └── 09-memory-and-persistence.md（记忆）
   └── 10-skills-and-plugins.md（插件）

5. 实战
   └── A01-A13（代码详解）
   └── 12-typescript-vs-java.md（语言对比）
```
