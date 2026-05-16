v# 附录 A：TypeScript 速成

> 浓缩 TypeScript 核心知识：基础类型、接口、泛型、联合/交叉类型、async/await，以及 Branded Types、Discriminated Unions、TypedEventEmitter、DeepPartial 等高级模式。配合本书源码阅读使用。

---

## A.1 基础类型与接口

TypeScript 在 JavaScript 基础上添加静态类型检查。核心优势：编译时错误检测、IDE 智能提示、类型即文档。

**原始类型与类型推断：**

```typescript
let name: string = "Claude";
let age = 25;           // 推断为 number
let isActive = true;    // 推断为 boolean
```

优先依赖类型推断，仅在类型不明显时显式标注。

**接口定义对象形状：**

```typescript
interface User {
  id: number;
  name: string;
  email?: string;           // 可选属性
  readonly createdAt: Date;  // 只读属性
}
```

**常用工具类型速查：**

| 工具类型 | 作用 |
|---------|------|
| `Partial<T>` | 所有属性变可选 |
| `Required<T>` | 所有属性变必需 |
| `Readonly<T>` | 所有属性变只读 |
| `Pick<T, K>` | 选取部分属性 |
| `Omit<T, K>` | 排除部分属性 |
| `Record<K, V>` | 键值对映射类型 |
| `Exclude<A, B>` | 从联合类型 A 中排除 B |
| `Extract<A, B>` | 从联合类型 A 中提取 B |
| `ReturnType<F>` | 提取函数返回类型 |
| `Parameters<F>` | 提取函数参数类型元组 |

---

## A.2 联合类型与交叉类型

**联合类型（Union）** — 值可以是多种类型之一：

```typescript
let id: string | number;
id = "user_123";  // OK
id = 12345;       // OK
```

配合类型守卫（Type Guard）缩小类型范围：

```typescript
function processValue(value: string | number) {
  if (typeof value === "string") {
    console.log(value.toUpperCase());  // value 是 string
  } else {
    console.log(value.toFixed(2));     // value 是 number
  }
}
```

**交叉类型（Intersection）** — 组合多个类型：

```typescript
interface Loggable { log(): void }
interface Serializable { serialize(): string }

type LoggableAndSerializable = Loggable & Serializable;
// 同时拥有 log() 和 serialize() 方法
```

---

## A.3 泛型

泛型让函数和接口工作于多种类型，同时保持类型安全。

**泛型函数与泛型约束：**

```typescript
function firstOf<T>(arr: T[]): T | undefined {
  return arr[0];
}

const str = firstOf(["a", "b", "c"]);  // string | undefined
const num = firstOf([1, 2, 3]);        // number | undefined

// 泛型约束：要求 T 必须有 length 属性
interface HasLength { length: number }

function logLength<T extends HasLength>(arg: T): number {
  return arg.length;
}

logLength("hello");     // OK
logLength([1, 2, 3]);   // OK
logLength(123);         // 编译错误：number 没有 length
```

**条件类型与映射类型：**

```typescript
// 条件类型：提取 Promise 内部的值类型
type Unwrapped<T> = T extends Promise<infer U> ? U : T;
type T1 = Unwrapped<Promise<number>>;  // number
type T2 = Unwrapped<string>;           // string

// 映射类型：为所有属性生成 getter
type Getters<T> = {
  [P in keyof T as `get${Capitalize<string & P>}`]: () => T[P];
};
```

---

## A.4 async/await 与异步编程

`async/await` 是 Promise 的同步写法，是 TypeScript 异步编程的主流方式。

**基本用法：**

```typescript
async function getUser(id: number): Promise<User> {
  try {
    const response = await fetch(`/api/users/${id}`);
    return await response.json();
  } catch (error) {
    console.error("Failed:", error);
    throw error;
  }
}
```

**并行执行：**

```typescript
const [users, orders] = await Promise.all([
  fetchUsers(),
  fetchOrders(),
]);
```

**AsyncGenerator 流式处理（本书核心模式）：**

```typescript
async function* fetchPages(url: string): AsyncGenerator<Page> {
  let cursor: string | undefined;
  do {
    const response = await fetch(`${url}?cursor=${cursor || ''}`);
    const data = await response.json();
    yield data.page;
    cursor = data.nextCursor;
  } while (cursor);
}

// 消费
for await (const page of fetchPages('/api/data')) {
  await processPage(page);
}
```

**yield* 委托 — 将子生成器的产出透传给外层：**

```typescript
async function* parent(): AsyncGenerator<string> {
  yield "start";
  yield* child();   // child 的每个 yield 都直接传给 parent 的消费者
  yield "end";
}
```

---

## A.5 高级模式：Branded Types

用于区分语义相同但不应混用的类型（如 `toolName` vs `messageId`）：

```typescript
type ApiKey = string & { readonly __brand: 'ApiKey' };
type UserId = string & { readonly __brand: 'UserId' };

function createApiKey(key: string): ApiKey {
  return key as ApiKey;
}

function createUserId(id: string): UserId {
  return id as UserId;
}

function fetchWithKey(key: ApiKey, url: string): Promise<Response> {
  return fetch(url, { headers: { 'x-api-key': key } });
}

const userId = createUserId('user-123');
// fetchWithKey(userId, url);  // 编译错误！不能混用
const apiKey = createApiKey('sk-xxx');
fetchWithKey(apiKey, url);     // OK
```

---

## A.6 高级模式：Discriminated Unions

通过公共字段（通常是 `type`）区分联合类型成员，配合 `switch` 实现穷尽检查：

```typescript
type Success<T> = { type: 'success'; data: T };
type Failure = { type: 'error'; message: string; code: number };
type Loading = { type: 'loading' };

type AsyncState<T> = Success<T> | Failure | Loading;

function handleState<T>(state: AsyncState<T>): string {
  switch (state.type) {
    case 'success':  return `Data: ${state.data}`;
    case 'error':    return `Error ${state.code}: ${state.message}`;
    case 'loading':  return 'Loading...';
  }
  // TypeScript 自动检查是否穷尽所有分支
}
```

本书源码中 `ContentBlock` 类型就是 Discriminated Union 的典型应用：

```typescript
type ContentBlock =
  | { type: 'text'; text: string }
  | { type: 'tool_use'; id: string; name: string; input: Record<string, unknown> }
  | { type: 'tool_result'; tool_use_id: string; content: string }
```

---

## A.7 高级模式：TypedEventEmitter

类型安全的事件发射器，确保事件名与回调参数类型一一对应：

```typescript
type EventMap = Record<string, unknown>;

class TypedEventEmitter<T extends EventMap> {
  private listeners = new Map<keyof T, Set<Function>>();

  on<K extends keyof T>(event: K, handler: (data: T[K]) => void): this {
    if (!this.listeners.has(event)) {
      this.listeners.set(event, new Set());
    }
    this.listeners.get(event)!.add(handler);
    return this;
  }

  off<K extends keyof T>(event: K, handler: (data: T[K]) => void): this {
    this.listeners.get(event)?.delete(handler);
    return this;
  }

  emit<K extends keyof T>(event: K, data: T[K]): boolean {
    const handlers = this.listeners.get(event);
    if (!handlers || handlers.size === 0) return false;
    handlers.forEach(h => h(data));
    return true;
  }
}

// 使用示例
interface Events {
  message: { text: string; user: string };
  error: { code: number; message: string };
}

const emitter = new TypedEventEmitter<Events>();

emitter.on('message', (data) => {
  console.log(`${data.user}: ${data.text}`);  // data 自动推断
});

emitter.emit('message', { text: 'Hello', user: 'alice' });  // OK
// emitter.emit('message', { text: 'hi' });  // 编译错误：缺少 user
```

---

## A.8 高级模式：DeepPartial 系列

递归地将嵌套对象的所有属性变为可选，适用于配置更新、测试数据生成等场景：

```typescript
type DeepPartial<T> = T extends object
  ? { [P in keyof T]?: DeepPartial<T[P]> }
  : T;

type DeepReadonly<T> = T extends object
  ? { readonly [P in keyof T]: DeepReadonly<T[P]> }
  : T;

type DeepRequired<T> = T extends object
  ? { [P in keyof T]-?: DeepRequired<T[P]> }
  : T;
```

**实际应用 — 部分更新：**

```typescript
interface Config {
  api: { url: string; timeout: number; retries: number };
  features: { darkMode: boolean; notifications: { enabled: boolean } };
}

function updateConfig(updates: DeepPartial<Config>): void {
  // 只需提供要更新的字段，嵌套层级也只需部分提供
}

updateConfig({
  api: { url: 'http://localhost:3000' }  // 只改 url，其余保持不变
});
```

---

## 速查总结

| 概念 | 关键词 | 本书应用场景 |
|------|--------|-------------|
| 接口与工具类型 | `interface`、`Partial`、`Pick`、`Omit`、`Record` | Tool 定义、消息类型、配置对象 |
| 联合与交叉 | `A \| B`、`A & B`、类型守卫 | ContentBlock、权限模式 |
| 泛型 | `<T>`、`extends` 约束、条件类型、映射类型 | `buildTool<D>()`、`TypedEventEmitter<T>` |
| 异步编程 | `async/await`、`Promise.all`、`AsyncGenerator` | `query()` 流式响应、工具执行 |
| Branded Types | `string & { __brand }` | 区分 toolName / messageId 等语义类型 |
| Discriminated Unions | 公共 `type` 字段 + `switch` 穷尽检查 | 消息分发、工具结果类型 |
| TypedEventEmitter | 泛型 `EventMap` | 组件间事件通信 |
| DeepPartial | 递归可选 | 嵌套配置的部分更新 |
