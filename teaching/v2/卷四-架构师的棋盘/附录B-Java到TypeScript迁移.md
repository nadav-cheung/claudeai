---
title: "附录B — Java 到 TypeScript 迁移指南"
description: "面向 Java 开发者的 TypeScript 迁移速查，包含设计模式映射表、核心代码对比、Zod Schema 实战入门与迁移检查清单。"
tags: [typescript, java, migration, patterns, zod]
date: 2026-05-10
---

# 附录B — Java 到 TypeScript 迁移指南

> 本附录面向 Java 开发者，通过设计模式映射、代码对比、Zod 实战与迁移检查清单，帮助快速建立 TypeScript 架构直觉。

---

## B.1 设计模式映射表

TypeScript 与 Java 在架构目标上高度一致，实现路径不同。下表汇总了本书源码中最核心的 8 组映射：

| TypeScript 模式 | Claude Code 实现 | Java 等价 | Spring 等价 |
|---------------|-----------------|----------|------------|
| 工厂模式 | `buildTool()` 填充默认值 | `FactoryBean<T>` | `@Bean` 方法 |
| 胖接口 | `Tool`（30+ 方法） | `Command` + `Renderable` | `HandlerInterceptor` |
| 响应式 | `createSignal()` 15 行 | `Flow.Subscriber` | Reactor `Flux` |
| 异步生成器 | `AsyncGenerator` yield | `CompletableFuture` 链式 | `Mono` / `Flux` |
| 依赖注入 | `getAppState()` | ServiceLocator | `@Autowired` |
| 缓存 | `Map` + LRU | `HashMap` | `@Cacheable` |
| Schema 验证 | Zod | Hibernate Validator | `BindingResult` |
| 权限 | `PermissionMode` 运行时决策 | `SecurityManager` 固定策略 | Spring Security |

**类型系统本质差异：** TypeScript 使用结构化类型（duck typing）——只要对象拥有所需方法就算满足接口；Java 使用标称类型——必须显式声明 `implements`。结构化类型更灵活，标称类型更严格。

---

## B.2 核心代码对比

### 对比 1：工厂模式

**TypeScript `buildTool()`：**

```typescript
export function buildTool<D extends AnyToolDef>(def: D): BuiltTool<D> {
  return {
    ...TOOL_DEFAULTS,          // 填充默认值
    userFacingName: () => def.name,
    ...def,                    // 用户定义覆盖默认值
  } as BuiltTool<D>
}
```

对象字面量展开，无类、无继承，10 行完成工厂模式。

**Java `FactoryBean`：**

```java
@Component
public class ToolFactoryBean implements FactoryBean<Tool> {
    @Override
    public Tool getObject() {
        return switch (type) {
            case MCP -> createMcpTool(config);
            case BUILTIN -> createBuiltinTool(config);
        };
    }
    @Override
    public Class<?> getObjectType() { return Tool.class; }
}
```

需要显式实现接口、注册组件、处理类型信息。

### 对比 2：响应式状态

**TypeScript `createSignal()`：**

```typescript
export function createSignal<Args extends unknown[] = []>(): Signal<Args> {
  const listeners = new Set<(...args: Args) => void>()
  return {
    subscribe(listener) {
      listeners.add(listener)
      return () => { listeners.delete(listener) }  // 返回取消函数
    },
    emit(...args) {
      for (const listener of listeners) listener(...args)
    },
    clear() { listeners.clear() },
  }
}
```

15 行代码，纯事件发布-订阅，无存储状态。

**Java `Flow` API：**

```java
SubmissionPublisher<T> publisher = new SubmissionPublisher<>();
publisher.subscribe(new Flow.Subscriber<T>() {
    public void onSubscribe(Subscription s) { s.request(1); }
    public void onNext(T item)             { /* 处理 */ s.request(1); }
    public void onError(Throwable t)        { t.printStackTrace(); }
    public void onComplete()               { /* 完成 */ }
});
publisher.submit(item);
```

需要 4 个回调方法、手动请求背压。Java 的响应式库（Reactor）有数千行代码——因为需要多线程安全和背压机制，而 CLI 场景是单线程同步交互。

### 对比 3：异步执行

**TypeScript `AsyncGenerator`：**

```typescript
async function* runToolUse(toolUse, context): AsyncGenerator<Update> {
  const tool = findTool(toolUse.name, context.options.tools)
  if (!tool) {
    yield { message: createNotFoundMessage(toolUse) }
    return
  }
  for await (const update of streamedExecute(tool, toolUse)) {
    yield update  // 逐步产出进度
  }
}

// 消费
for await (const update of runToolUse(toolUse, ctx)) {
  displayProgress(update)
}
```

同步风格代码，`yield` 逐步产出，`for await` 逐步消费。

**Java `CompletableFuture`：**

```java
CompletableFuture<ToolResult> future = tool.call(input, context)
    .thenApply(result -> processResult(result))
    .thenAccept(finalResult -> displayResult(finalResult))
    .exceptionally(error -> handleError(error));
```

链式回调风格，所有结果一次性返回，无法流式产出中间状态。

---

## B.3 Zod Schema 实战入门

Java 使用 `@NotNull`、`@Size` 等 Jakarta Validation 注解。TypeScript 生态中，Zod 是最主流的运行时验证库——弥补了 TypeScript 类型只在编译时生效的缺口。

**定义 Schema：**

```typescript
import { z } from 'zod';

const UserSchema = z.object({
  id: z.number(),
  name: z.string().min(1).max(100),
  email: z.string().email(),
  age: z.number().int().positive().optional(),
  role: z.enum(['admin', 'user', 'guest']),
});

// 从 Schema 自动推断 TypeScript 类型
type User = z.infer<typeof UserSchema>;
```

**运行时验证：**

```typescript
const result = UserSchema.safeParse(input);
if (result.success) {
  console.log(result.data.name);  // data 类型为 User
} else {
  console.error(result.error.issues);  // 精确的错误信息
}
```

**`transform` 与预处理：**

```typescript
const QuerySchema = z.object({
  page: z.coerce.number().int().positive().default(1),
  tags: z.string().transform(s => s.split(',')).optional(),
});

const query = QuerySchema.parse({ page: '2', tags: 'ai,ml' });
// { page: 2, tags: ['ai', 'ml'] }
```

**Zod vs Jakarta Validation：**

| 方面 | Jakarta Validation | Zod |
|------|-------------------|-----|
| 检查时机 | 运行时 | 运行时 |
| 类型推断 | 无 | `z.infer` 自动生成 TS 类型 |
| Schema 即类型 | 否，需手写 | 是，Schema 定义即类型定义 |
| 嵌套对象 | `@Valid` 递归 | 自然嵌套 |
| 自定义规则 | `ConstraintValidator` | `.refine()` / `.transform()` |

---

## B.4 迁移检查清单

逐项对照，从 Java 思维切换到 TypeScript 思维：

| 方面 | Java 做法 | TypeScript 做法 |
|------|----------|----------------|
| 类型声明 | `List<User>` | `User[]` |
| 空安全 | `Optional<T>` | `T \| undefined` |
| 不可变 | `final` | `readonly` + `as const` |
| 函数式 | Stream API | 内联函数 + 数组方法（`map`、`filter`、`reduce`） |
| 异常 | `try/catch` | `try/catch` + `Result` 类型模式 |
| 泛型约束 | `<T extends Foo>` | `T extends Foo`（语法几乎一致） |
| 访问控制 | `public / private / protected` | 同上 + `readonly` |
| 接口 | `interface Foo` | `interface Foo` + `type Alias = ...`（两者互补） |
| 验证 | Jakarta Validation | Zod schema（运行时 + 类型推断） |
| 依赖注入 | Spring `@Autowired` | 构造函数注入 / `getAppState()` |
| 响应式 | Reactor `Flux` / `Mono` | `AsyncGenerator` / `createSignal()` |
| 异步 | `CompletableFuture` | `async/await` / `Promise` |
| 模块 | `package` + `import` | ES Module `import / export` |

**常见坑与对策：**

| 坑点 | 说明 | 对策 |
|------|------|------|
| `any` 滥用 | 相当于 Java 原始类型，绕过类型检查 | 用 `unknown` 代替，强制类型守卫 |
| 未清理订阅 | Signal/event 监听闭包导致内存泄漏 | `subscribe` 返回取消函数，组件销毁时调用 |
| 隐式 `any` | 函数参数未标注类型时推断为 `any` | 开启 `strict` 模式 + `noImplicitAny` |
| 结构化类型意外匹配 | 只要结构满足就通过，不管意图 | 使用 Branded Types 区分语义 |
| `as` 断言不安全 | `as` 不做运行时检查 | 用 Zod `safeParse` 代替 `as` |

---

## 速查总结

本附录的核心思路：**不要试图在 TypeScript 中写 Java 代码**。TypeScript 有自己的最佳实践：

- 用对象字面量和展开运算符代替工厂类
- 用 `AsyncGenerator` 代替 `CompletableFuture` 链
- 用 `createSignal()` 代替 `Flow.Subscriber`
- 用 Zod 统一运行时验证和类型定义
- 用结构化类型的灵活性减少样板代码，用 Branded Types 防止语义混淆
