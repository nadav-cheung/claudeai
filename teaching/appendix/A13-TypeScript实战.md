# A13 - TypeScript 实战技巧

> **本附录目标**：为 Java 开发者提供 TypeScript 实战技巧，涵盖从 Java 迁移到 TypeScript 的常见模式、类型系统最佳实践、异步编程、以及如何在实际项目中应用 Claude Code 的架构思想。

---

## 1. 从 Java 到 TypeScript：核心迁移模式

### 1.1 类与接口的对应

Java 的类继承 vs TypeScript 的结构化类型：

```typescript
// TypeScript: 接口是结构契约
interface UserService {
  findById(id: number): Promise<User>;
  findAll(): Promise<User[]>;
}

// 任何实现该结构的类都可以赋值
class InMemoryUserService implements UserService {
  async findById(id: number): Promise<User> { /* ... */ }
  async findAll(): Promise<User[]> { /* ... */ }
}

// 函数参数接受任何结构匹配的对象
function doSomething(service: UserService) {
  // service 必有 findById 和 findAll 方法
}
```

```java
// Java: 必须显式声明 implements
public class InMemoryUserService implements UserService {
    @Override
    public User findById(Long id) { /* ... */ }
    @Override
    public List<User> findAll() { /* ... */ }
}
```

### 1.2 泛型的对应

Java 和 TypeScript 的泛型非常相似：

```typescript
// TypeScript: 泛型约束
function identity<T extends { id: number }>(arg: T): T {
  console.log(arg.id);
  return arg;
}

// TypeScript: 多重约束
function merge<T extends object, U extends object>(a: T, b: U): T & U {
  return { ...a, ...b };
}

// TypeScript: 泛型接口
interface Repository<T, ID> {
  findById(id: ID): Promise<T | null>;
  save(entity: T): Promise<T>;
  delete(id: ID): Promise<void>;
}
```

```java
// Java: 泛型约束
public <T extends HasId> T identity(T arg) {
    System.out.println(arg.getId());
    return arg;
}

// Java: 多重边界
public <T extends A & B> T merge(T a, T b) { /* ... */ }

// Java: 泛型接口
public interface Repository<T, ID> {
    Optional<T> findById(ID id);
    T save(T entity);
    void delete(ID id);
}
```

### 1.3 访问修饰符

```typescript
// TypeScript: 三种访问级别
class Example {
  public name: string;           // 任意位置访问
  protected age: number;        // 类和子类中访问
  private secret: string;       // 仅本类中访问

  // readonly: 初始化后不可修改
  readonly createdAt: Date;

  constructor() {
    this.createdAt = new Date();
  }
}
```

```java
// Java: 四种访问级别
public class Example {
    public String name;          // 任意位置访问
    protected int age;          // 类和子类 + 同包访问
    private String secret;      // 仅本类中访问

    // Java 使用 final
    public final Date createdAt = new Date();
}
```

---

## 2. Zod Schema 实战：替代 Jakarta Validation

### 2.1 基础 schema 定义

```typescript
import { z } from 'zod';

// 基础对象 schema
const UserSchema = z.object({
  id: z.number(),
  name: z.string().min(1).max(100),
  email: z.string().email(),
  age: z.number().int().positive().optional(),
  createdAt: z.date(),
});

// 数组和嵌套
const CompanySchema = z.object({
  name: z.string(),
  users: z.array(UserSchema),
  address: z.object({
    street: z.string(),
    city: z.string(),
    country: z.string(),
  }).optional(),
});

// 联合类型
const StatusSchema = z.enum(['pending', 'active', 'suspended']);
```

### 2.2 运行时验证

```typescript
// 验证并类型推断
const result = UserSchema.safeParse({
  id: 1,
  name: 'Alice',
  email: 'alice@example.com',
});

if (result.success) {
  // result.data 类型为 { id: number; name: string; ... }
  console.log(result.data.name);
} else {
  // 处理验证错误
  console.error(result.error.issues);
}
```

### 2.3 从 schema 生成类型

```typescript
// 从 schema 推断 TypeScript 类型
type User = z.infer<typeof UserSchema>;
type Company = z.infer<typeof CompanySchema>;

// 或手动定义再验证
interface User {
  id: number;
  name: string;
  email: string;
  age?: number;
  createdAt: Date;
}

// 验证输入并转换为类型
function createUser(input: unknown): User {
  return UserSchema.parse(input);  // 抛错如果验证失败
}
```

### 2.4 transform 和预处理

```typescript
const QuerySchema = z.object({
  page: z.coerce.number().int().positive().default(1),
  pageSize: z.coerce.number().int().positive().max(100).default(20),
  sort: z.enum(['asc', 'desc']).optional(),
  filter: z.string().optional(),
  // 预处理：将逗号分隔的字符串转为数组
  tags: z.string().transform(s => s.split(',')).optional(),
});

// URL 查询参数验证
const query = QuerySchema.parse({
  page: '2',           // 自动转为 number
  pageSize: '50',
  tags: 'ai,machine-learning',
});
// { page: 2, pageSize: 50, tags: ['ai', 'machine-learning'] }
```

---

## 3. 异步模式实战

### 3.1 AsyncGenerator 流式处理

```typescript
// 创建异步生成器
async function* fetchPages(url: string): AsyncGenerator<Page> {
  let cursor: string | undefined;

  do {
    const response = await fetch(`${url}?cursor=${cursor || ''}`);
    const data = await response.json();

    yield data.page;

    cursor = data.nextCursor;
  } while (cursor);
}

// 消费生成器
for await (const page of fetchPages('https://api.example.com/data')) {
  console.log(`Processing page ${page.number}`);
  await processPage(page);
}
```

```java
// Java: 响应式流方式
Flux<Page> fetchPages(String url) {
    return Flux.generate(
        () -> new AtomicReference<>(Optional.<String>empty()),
        (state, sink) -> {
            String cursor = state.get().orElse(null);
            Page page = fetchPage(url, cursor);
            if (page.hasNextCursor()) {
                state.set(Optional.of(page.getNextCursor()));
                sink.next(page);
            } else {
                sink.complete();
            }
            return state;
        }
    );
}
```

### 3.2 Promise.all 并发执行

```typescript
// 并发执行多个 Promise
const [users, orders, products] = await Promise.all([
  fetchUsers(),
  fetchOrders(),
  fetchProducts(),
]);

// 带错误处理的并发
const results = await Promise.allSettled([
  fetchUser(1),
  fetchUser(2),
  fetchUser(3),
]);

results.forEach((result, i) => {
  if (result.status === 'fulfilled') {
    console.log(`User ${i + 1}:`, result.value);
  } else {
    console.error(`User ${i + 1} failed:`, result.reason);
  }
});
```

### 3.3 AbortController 取消操作

```typescript
// 创建取消控制器
const controller = new AbortController();

// 3秒后自动取消
const timeout = setTimeout(() => controller.abort(), 3000);

try {
  const result = await fetchData(controller.signal);
  clearTimeout(timeout);
  return result;
} catch (error) {
  if (error.name === 'AbortError') {
    console.log('Request cancelled');
  }
  throw error;
}
```

---

## 4. 模块和导入实战

### 4.1 命名导入 vs 命名空间导入

```typescript
// 推荐：命名导入（更好的 tree-shaking）
import { createSignal, createEffect } from './signal';
import { runToolUse } from './toolExecution';

// 类型导入（编译后移除）
import type { Tool, ToolResult } from './Tool';

// 运行时导入（懒加载）
const getModule = async () => {
  const { heavyModule } = await import('./heavyModule.js');
  heavyModule.doSomething();
};

// re-export
export { createSignal, createEffect } from './signal';
export type { Tool } from './Tool';
```

### 4.2 条件导入（Feature Flag）

```typescript
// Bun 环境：编译时特性开关
import { feature } from 'bun:bundle';

const coordinatorModule = feature('COORDINATOR_MODE')
  ? require('./coordinator/coordinatorMode.js')
  : null;

// 运行时条件导入
if (process.env.NODE_ENV === 'production') {
  import('./productionLogger.js').then(m => m.init());
}
```

### 4.3 循环依赖处理

```typescript
// 方案1：延迟导入
class ServiceA {
  private serviceB: ServiceB | null = null;

  getServiceB() {
    if (!this.serviceB) {
      this.serviceB = require('./ServiceB').ServiceB;
    }
    return this.serviceB;
  }
}

// 方案2：提取共享接口到独立文件
// shared/interfaces.ts - 无依赖
export interface Repository {
  findAll(): Promise<Item[]>;
}

// service-a.ts - 依赖接口
import { Repository } from '../shared/interfaces';
export class ServiceA {
  constructor(private repo: Repository) {}
}
```

---

## 5. 类型系统高级技巧

### 5.1 条件类型

```typescript
// 根据输入类型决定返回类型
type NonNullable<T> = T extends null | undefined ? never : T;

// 提取数组元素类型
type ElementType<T> = T extends Array<infer E> ? E : never;

// 提取函数返回类型
type ReturnType<T> = T extends (...args: any[]) => infer R ? R : never;

// 根据字段是否存在决定类型
type FieldType<T, K extends keyof T> =
  T[K] extends undefined ? string : T[K];
```

### 5.2 映射类型

```typescript
// 将所有属性变为可选
type Partial<T> = { [P in keyof T]?: T[P] };

// 将所有属性变为只读
type Readonly<T> = { readonly [P in keyof T]: T[P] };

// 选择特定属性
type Pick<T, K extends keyof T> = { [P in K]: T[P] };

// 排除特定类型
type Exclude<T, U> = T extends U ? never : T;

// 实际应用：让特定属性可选
type UpdateUser = Partial<Pick<User, 'name' | 'email'>>;
```

### 5.3 模板字面量类型

```typescript
// 工具名构造
type McpToolName = `mcp__${string}__${string}`;

// 事件名构造
type EventName = `on${Capitalize<string>}`;

// 验证工具名格式
function isMcpToolName(name: string): name is McpToolName {
  return /^mcp__[\w]+__[\w]+$/.test(name);
}
```

---

## 6. 错误处理实战

### 6.1 Result 类型模式

```typescript
// 类似 Rust 的 Result 类型
type Result<T, E = Error> =
  | { success: true; data: T }
  | { success: false; error: E };

async function fetchUser(id: number): Promise<Result<User>> {
  try {
    const user = await db.users.findById(id);
    if (!user) {
      return { success: false, error: new Error('User not found') };
    }
    return { success: true, data: user };
  } catch (error) {
    return { success: false, error: error as Error };
  }
}

// 使用
const result = await fetchUser(1);
if (result.success) {
  console.log(result.data.name);
} else {
  console.error(result.error.message);
}
```

### 6.2 自定义 Error 类

```typescript
// 带错误代码的错误类
class AppError extends Error {
  constructor(
    message: string,
    public code: string,
    public statusCode: number = 500,
    public details?: Record<string, unknown>
  ) {
    super(message);
    this.name = 'AppError';
  }
}

// 使用
class NotFoundError extends AppError {
  constructor(resource: string, id: string) {
    super(
      `${resource} ${id} not found`,
      'NOT_FOUND',
      404,
      { resource, id }
    );
    this.name = 'NotFoundError';
  }
}

// 错误工厂
const errors = {
  notFound: (resource: string, id: string) => new NotFoundError(resource, id),
  unauthorized: () => new AppError('Unauthorized', 'UNAUTHORIZED', 401),
  validation: (details: Record<string, unknown>) =>
    new AppError('Validation failed', 'VALIDATION_ERROR', 400, details),
};
```

---

## 7. 装饰器与元编程

### 7.1 TypeScript 装饰器（实验性）

```typescript
// 启用实验装饰器：tsconfig.json 中设置 "experimentalDecorators": true

// 类装饰器
function logClass(target: Function) {
  console.log(`Class defined: ${target.name}`);
}

// 方法装饰器
function logMethod(
  target: any,
  methodName: string,
  descriptor: PropertyDescriptor
) {
  const original = descriptor.value;
  descriptor.value = function (...args: any[]) {
    console.log(`Calling ${methodName} with`, args);
    const result = original.apply(this, args);
    console.log(`${methodName} returned`, result);
    return result;
  };
}

// 使用
@logClass
class UserService {
  @logMethod
  findById(id: number): User {
    return { id, name: 'User' };
  }
}
```

```java
// Java: 注解方式
@LogClass
public class UserService {
    @LogMethod
    public User findById(Long id) {
        return new User(id, "User");
    }
}
```

### 7.2 反射元数据

```typescript
import 'reflect-metadata';

const METADATA_KEY = Symbol('required');

// 属性装饰器
function required(target: any, propertyKey: string | symbol) {
  Reflect.defineMetadata(METADATA_KEY, true, target, propertyKey);
}

// 验证函数
function validate(target: any): boolean {
  for (const key of Object.keys(target)) {
    if (Reflect.getMetadata(METADATA_KEY, target, key)) {
      if (target[key] === undefined) {
        console.error(`${String(key)} is required`);
        return false;
      }
    }
  }
  return true;
}

class CreateUserRequest {
  @required name: string;
  @required email: string;
  age?: number;
}
```

---

## 8. 实战案例：构建一个 CLI 工具

### 8.1 项目结构

```
my-cli/
├── src/
│   ├── main.ts           # 入口
│   ├── commands/         # 命令实现
│   │   ├── index.ts
│   │   └── greet.ts
│   ├── services/         # 业务逻辑
│   │   └── userService.ts
│   ├── types/            # 类型定义
│   │   └── user.ts
│   └── utils/            # 工具函数
│       └── logger.ts
├── package.json
└── tsconfig.json
```

### 8.2 命令行参数解析

```typescript
import { Command } from 'commander';

// 定义命令
const program = new Command();

program
  .name('my-cli')
  .description('A sample CLI tool')
  .version('1.0.0');

program
  .command('greet')
  .description('Greet a user')
  .option('-n, --name <name>', 'User name', 'World')
  .option('-t, --type <type>', 'Greeting type', 'formal')
  .action((options) => {
    const greeting = generateGreeting(options.name, options.type);
    console.log(greeting);
  });

program.parse();
```

### 8.3 完整示例

```typescript
// src/main.ts
import { Command } from 'commander';
import { greetCommand } from './commands/greet.js';
import { UserService } from './services/userService.js';
import { logger } from './utils/logger.js';

// 初始化
const program = new Command();

// 全局选项
program
  .option('-v, --verbose', 'Enable verbose logging')
  .hook('preAction', (thisCommand) => {
    if (thisCommand.opts().verbose) {
      logger.setLevel('debug');
    }
  });

// 注册子命令
program.addCommand(greetCommand);

// 主命令
program
  .action(() => {
    program.help();
  });

program.parse();
```

```typescript
// src/commands/greet.ts
import { Command } from 'commander';

export const greetCommand = new Command('greet')
  .description('Send a greeting')
  .option('-n, --name <name>', 'Name to greet', 'World')
  .option('-u, --uppercase', 'Uppercase output', false)
  .action(async (options) => {
    const message = `Hello, ${options.name}!`;
    console.log(options.uppercase ? message.toUpperCase() : message);
  });
```

---

## 9. 测试实战

### 9.1 Vitest 配置

```typescript
// vitest.config.ts
import { defineConfig } from 'vitest/config';

export default defineConfig({
  test: {
    globals: true,
    environment: 'node',
    include: ['src/**/*.test.ts'],
    coverage: {
      provider: 'v8',
      reporter: ['text', 'json', 'html'],
    },
  },
});
```

### 9.2 单元测试

```typescript
// src/utils/signal.test.ts
import { describe, it, expect, vi } from 'vitest';
import { createSignal } from './signal';

describe('Signal', () => {
  it('should return initial value', () => {
    const signal = createSignal(42);
    expect(signal.get()).toBe(42);
  });

  it('should notify subscribers on update', () => {
    const signal = createSignal(0);
    const subscriber = vi.fn();

    signal.subscribe(subscriber);
    signal.set(10);

    expect(subscriber).toHaveBeenCalledWith(10);
  });

  it('should unsubscribe on cleanup', () => {
    const signal = createSignal(0);
    const subscriber = vi.fn();

    const unsubscribe = signal.subscribe(subscriber);
    unsubscribe();

    signal.set(20);

    expect(subscriber).not.toHaveBeenCalled();
  });
});
```

### 9.3 Mock 外部依赖

```typescript
// 使用 vi.mock() 模拟模块
vi.mock('./api/client', () => ({
  fetchUser: vi.fn().mockResolvedValue({ id: 1, name: 'Test User' }),
}));

// 模拟定时器
vi.useFakeTimers();

it('should debounce calls', async () => {
  const fn = vi.fn();
  const debouncedFn = debounce(fn, 100);

  debouncedFn();
  debouncedFn();
  debouncedFn();

  expect(fn).not.toHaveBeenCalled();

  vi.advanceTimersByTime(100);

  expect(fn).toHaveBeenCalledTimes(1);
});
```

---

## 10. 性能优化

### 10.1 懒计算与缓存

```typescript
// 简单 memoize
function memoize<T extends (...args: any[]) => any>(fn: T): T {
  const cache = new Map<string, ReturnType<T>>();

  return ((...args: any[]) => {
    const key = JSON.stringify(args);
    if (cache.has(key)) {
      return cache.get(key);
    }
    const result = fn(...args);
    cache.set(key, result);
    return result;
  }) as T;
}

// 使用
const expensiveOperation = memoize((n: number) => {
  console.log('Computing...');
  return n * 2;
});

expensiveOperation(5);  // Computing... 10
expensiveOperation(5);  // 直接返回缓存 10
```

### 10.2 大数据流处理

```typescript
// 分批处理大数组
async function processInBatches<T, R>(
  items: T[],
  batchSize: number,
  processor: (batch: T[]) => Promise<R[]>
): Promise<R[]> {
  const results: R[] = [];

  for (let i = 0; i < items.length; i += batchSize) {
    const batch = items.slice(i, i + batchSize);
    const batchResults = await processor(batch);
    results.push(...batchResults);
  }

  return results;
}

// 使用
const users = await getAllUsers();
const processed = await processInBatches(users, 100, (batch) =>
  Promise.all(batch.map(u => transformUser(u)))
);
```

### 10.3 避免内存泄漏

```typescript
// 清理订阅
class Component {
  private subscriptions: (() => void)[] = [];

  mount() {
    // 收集清理函数
    const unsub1 = signal.subscribe(handler);
    const unsub2 = anotherSignal.subscribe(handler2);

    this.subscriptions.push(unsub1, unsub2);
  }

  unmount() {
    // 清理所有订阅
    this.subscriptions.forEach(unsub => unsub());
    this.subscriptions = [];
  }
}
```

---

## 总结：Java 开发者的 TypeScript 迁移检查清单

| 方面 | Java 做法 | TypeScript 做法 |
|------|----------|----------------|
| 类型声明 | `List<User>` | `User[]` |
| 空安全 | `Optional<T>` | `T \| undefined` |
| 不可变 | `final` | `readonly` + `as const` |
| 函数式 | Stream API | 内联函数 + 数组方法 |
| 异常 | `try/catch` | `try/catch` + `Result` 类型 |
| 泛型约束 | `<T extends Foo>` | `T extends Foo` |
| 访问控制 | `public/private/protected` | 同上 + `readonly` |
| 接口 | `interface Foo` | `interface Foo` + `type Alias = ...` |
| 验证 | Jakarta Validation | Zod schema |
| 依赖注入 | Spring `@Bean` | 构造函数注入 / `getAppState()` |

**★ 设计思想 ─────────────────────────────────────**
TypeScript 的类型系统比 Java 更灵活，但需要开发者自律——`any` 类型就像 Java 的原始类型，需要谨慎使用。好的 TypeScript 实践是：用 `unknown` 代替 `any`，用 `interface` 代替结构契约，用 `z.infer` 从 schema 推断类型。这些实践在 Claude Code 的源码中都有体现。
─────────────────────────────────────────────────

---

## 练习

### 练习 1：类型推断 vs 显式类型

**问题**：为什么 Claude Code 大量使用类型推断而不是显式类型标注？

**答案**：

**推断优势**：
1. **减少样板代码**：不需要处处写 `: string`
2. **DRY 原则**：类型定义一处，多处推断
3. **重构友好**：改一处类型，全局生效

```typescript
// 显式标注（Java 风格）
const users: Map<string, User> = new Map<string, User>()

// 类型推断（TypeScript 风格）
const users = new Map<string, User>()  // 推断出 Map<string, User>
```

**何时用显式标注**：
- 公共 API 的参数和返回值
- 需要文档化的关键类型
- 编译器无法推断时

---

### 练习 2：Zod schema vs TypeScript interface

**问题**：为什么 Claude Code 使用 Zod 进行验证而不是只用 TypeScript 类型？

**答案**：

| 方面 | TypeScript 类型 | Zod Schema |
|------|----------------|-------------|
| 运行时检查 | ❌ 编译时 | ✅ 运行时 |
| 验证规则 | ❌ 无 | ✅ 可定义 |
| 自文档化 | ❌ 无 | ✅ 有 |
| 从 schema 推断类型 | ❌ 需手动 | ✅ `z.infer<typeof schema>` |

```typescript
// TypeScript：只检查编译时
function processInput(input: { name: string; age: number }) { ... }

// Zod：运行时也检查
const UserSchema = z.object({
  name: z.string().min(1),
  age: z.number().positive(),
})

function processInput(input: z.infer<typeof UserSchema>) {
  // 编译时 + 运行时检查
}
```

---

### 练习 3：AsyncGenerator 的使用场景

**问题**：Claude Code 的 `createMessageStream()` 返回 AsyncGenerator 而不是 Promise，有什么优势？

**答案**：

**Promise vs AsyncGenerator**：
```typescript
// Promise：返回全部结果
async function fetchAll(): Promise<string[]> {
  return await api.getMessages()
}

// AsyncGenerator：流式返回
async function* streamMessages(): AsyncGenerator<string> {
  for await (const chunk of api.streamMessages()) {
    yield chunk  // 逐步产出
  }
}
```

**优势**：
1. **内存效率**：不需要等待全部完成
2. **低延迟**：首个结果即可处理
3. **背压控制**：消费者决定处理节奏

---

### 练习 4：解决循环依赖

**问题**：如果模块 A 导入 B，B 又导入 A，有哪些解决方案？

**答案**：

**方案对比**：

| 方案 | 优点 | 缺点 |
|------|------|------|
| 合并模块 | 简单 | 单一职责被破坏 |
| 接口提取 | 干净 | 需要多一个文件 |
| 延迟导入 | 动态 | 运行时开销 |

```typescript
// 方案 2：提取接口
// types.ts - 无依赖
export interface UserService { findUser(id: string): Promise<User> }

// service-a.ts
import { UserService } from './types'
import { UserServiceB } from './service-b'

export class ServiceA implements UserService { ... }

// service-b.ts - 只依赖接口
import type { UserService } from './types'  // type import 避免实际导入
```

---

### 练习 5：Signal vs Promise

**问题**：Claude Code 使用 Signal 而不是 Promise 进行状态管理，为什么？

**答案**：

| 方面 | Promise | Signal |
|------|---------|--------|
| 用途 | 异步计算结果 | 响应式状态 |
| 推送 | 单次 | 多次 |
| 订阅 | 一次 | 持续 |
| 适用场景 | API 调用 | UI 状态 |

```typescript
// Promise：一次性结果
const userPromise = fetchUser(id)
userPromise.then(user => ...)  // 调用一次

// Signal：持续状态
const sessionId = state.sessionId
sessionId.get()                    // 读取当前值
sessionId.set('new-session')      // 更新值
sessionId.subscribe(id => ...)     // 订阅变化
```

**Java 对比**：Signal 类似于 RxJava 的 `BehaviorSubject`，Promise 类似于 `CompletableFuture`。

---

## 练习答案速查

| 练习 | 核心答案 |
|------|---------|
| 1 | 推断减少样板，公共API用显式标注 |
| 2 | Zod有运行时检查，TypeScript只有编译时 |
| 3 | AsyncGenerator流式返回，内存效率高 |
| 4 | 提取接口到独立文件，type import |
| 5 | Signal=响应式状态多次推送，Promise=单次结果 |

---

## 附录：TypeScript 实用工具类型

| 工具类型 | 用途 |
|---------|------|
| `Partial<T>` | 所有属性可选 |
| `Required<T>` | 所有属性必需 |
| `Readonly<T>` | 所有属性只读 |
| `Pick<T, K>` | 选择特定属性 |
| `Omit<T, K>` | 排除特定属性 |
| `z.infer<typeof schema>` | 从Zod推断类型 |

---

## 附录导航

👈 [A11-API通信代码.md](./A11-API通信代码.md)
