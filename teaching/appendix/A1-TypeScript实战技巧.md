# A1 - TypeScript 实战技巧

> **本章目标**：掌握 TypeScript 在 Claude Code 项目中的实战技巧，包括常用模式、类型设计、泛型应用和工程实践。

---

## 1. 类型设计模式

### 1.1 Branded Types（标称类型）

用于区分语义相同但类型不同的值：

```typescript
// 普通 string 无法区分 API key 和普通字符串
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
// fetchWithKey(userId, url); // ✗ 类型错误！
const apiKey = createApiKey('sk-xxx');
fetchWithKey(apiKey, url); // ✓
```

**应用场景**：防止 `toolName` 和 `messageId` 混用、API key 和 token 混用。

### 1.2 Discriminated Unions（可辨识联合）

```typescript
type Success<T> = { type: 'success'; data: T };
type Error = { type: 'error'; message: string; code: number };
type Loading = { type: 'loading' };

type AsyncState<T> = Success<T> | Error | Loading;

// 穷尽检查
function handleState<T>(state: AsyncState<T>): string {
  switch (state.type) {
    case 'success':
      return `Data: ${state.data}`;
    case 'error':
      return `Error ${state.code}: ${state.message}`;
    case 'loading':
      return 'Loading...';
  }
  // TypeScript 会在这里检查是否穷尽所有情况
}
```

### 1.3 Const Assertions（const 断言）

```typescript
// 字面量类型推断
const routes = ['home', 'about', 'contact'] as const;
type Route = typeof routes[number]; // 'home' | 'about' | 'contact'

// 对象字面量的只读推断
const config = {
  apiUrl: 'https://api.anthropic.com',
  timeout: 5000,
  retries: 3,
} as const;

type Config = typeof config;
// {
//   readonly apiUrl: 'https://api.anthropic.com';
//   readonly timeout: 5000;
//   readonly retries: 3;
// }
```

---

## 2. 泛型高级应用

### 2.1 条件类型

```typescript
// 提取数组元素类型
type ElementType<T> = T extends Array<infer U> ? U : T;

// 提取 Promise 返回类型
type Awaited<T> = T extends Promise<infer U> ? U : T;

// 提取函数参数类型
type Parameters<T extends (...args: any) => any> =
  T extends (...args: infer P) => any ? P : never;

// 使用示例
type T1 = ElementType<string[]>; // string
type T2 = Awaited<Promise<number>>; // number
type T3 = Parameters<(x: string, y: number) => void>; // [string, number]
```

### 2.2 映射类型

```typescript
// 可选转必选
type Required<T> = {
  [P in keyof T]-?: T[P];
};

// 只读转可变
type Mutable<T> = {
  -readonly [P in keyof T]: T[P];
};

// 键重映射
type Getters<T> = {
  [P in keyof T as `get${Capitalize<string & P>}`]: () => T[P];
};

interface User {
  name: string;
  age: number;
}

type UserGetters = Getters<User>;
// { getName: () => string; getAge: () => number; }
```

### 2.3 递归类型

```typescript
// 深只读
type DeepReadonly<T> = T extends (infer U)[]
  ? ReadonlyArray<DeepReadonly<U>>
  : T extends object
  ? { readonly [P in keyof T]: DeepReadonly<T[P]> }
  : T;

// JSON 类型
type JSONValue = string | number | boolean | null | JSONValue[] | { [key: string]: JSONValue };

// 树结构
interface TreeNode<T> {
  value: T;
  children: TreeNode<T>[];
}
```

---

## 3. 模块系统

### 3.1 ESM vs CommonJS

```typescript
// ESM (src/utils/api.ts)
export function fetchApi(url: string): Promise<Response> {
  return fetch(url);
}

export const API_BASE = 'https://api.anthropic.com';

// 默认导出
export default class ApiClient {
  // ...
}

// 导入 (ESM)
import ApiClient, { fetchApi, API_BASE } from './utils/api';

// CommonJS 风格
// const { fetchApi } = require('./utils/api');
// module.exports = ApiClient;
```

### 3.2 路径别名配置

```typescript
// tsconfig.json
{
  "compilerOptions": {
    "baseUrl": ".",
    "paths": {
      "@/*": ["src/*"],
      "@/services/*": ["src/services/*"],
      "@/tools/*": ["src/tools/*"]
    }
  }
}

// 导入
import { ApiService } from '@/services/api';
import { Tool } from '@/tools/base';
```

### 3.3 动态导入

```typescript
// 懒加载模块
const module = await import('./heavy-module.ts');

// 条件导入
async function getFormatter(format: 'json' | 'xml') {
  if (format === 'json') {
    return import('./formatters/json.ts');
  }
  return import('./formatters/xml.ts');
}
```

---

## 4. 错误处理模式

### 4.1 Result 类型

```typescript
type Result<T, E = Error> =
  | { ok: true; value: T }
  | { ok: false; error: E };

function tryCatch<T>(fn: () => T): Result<T> {
  try {
    return { ok: true, value: fn() };
  } catch (error) {
    return { ok: false, error: error as Error };
  }
}

// 使用
const result = tryCatch(() => JSON.parse(input));
if (result.ok) {
  console.log(result.value);
} else {
  console.error(result.error);
}
```

### 4.2 自定义错误类

```typescript
class ToolExecutionError extends Error {
  constructor(
    public toolName: string,
    message: string,
    public cause?: unknown
  ) {
    super(`Tool '${toolName}' failed: ${message}`);
    this.name = 'ToolExecutionError';
  }
}

class PermissionError extends Error {
  constructor(
    public toolName: string,
    public requestedPermission: string
  ) {
    super(`Permission denied for tool '${toolName}': ${requestedPermission}`);
    this.name = 'PermissionError';
  }
}

// 错误层次
class ApiError extends Error {
  constructor(
    message: string,
    public statusCode: number,
    public code: string
  ) {
    super(message);
    this.name = 'ApiError';
  }
}
```

---

## 5. 装饰器模式

### 5.1 方法装饰器

```typescript
function memoize<T extends (...args: any[]) => any>(
  target: any,
  propertyKey: string,
  descriptor: TypedPropertyDescriptor<T>
) {
  const original = descriptor.value!;
  const cache = new Map<string, ReturnType<T>>();

  descriptor.value = function (...args: Parameters<T>): ReturnType<T> {
    const key = JSON.stringify(args);
    if (cache.has(key)) {
      return cache.get(key)!;
    }
    const result = original.apply(this, args);
    cache.set(key, result);
    return result;
  } as T;
}

class Calculator {
  @memoize
  expensiveCompute(n: number): number {
    // 耗时计算
    return n ** 2;
  }
}
```

### 5.2 日志装饰器

```typescript
function log(target: any, propertyKey: string, descriptor: PropertyDescriptor) {
  const original = descriptor.value;

  descriptor.value = function (...args: any[]) {
    console.log(`[${propertyKey}] Called with:`, args);
    const result = original.apply(this, args);
    console.log(`[${propertyKey}] Returned:`, result);
    return result;
  };

  return descriptor;
}

class MyService {
  @log
  fetchData(id: string): Promise<Data> {
    return fetch(`/api/data/${id}`).then(r => r.json());
  }
}
```

---

## 6. 类型守卫与断言

### 6.1 自定义类型守卫

```typescript
interface User {
  type: 'user';
  name: string;
  email: string;
}

interface Admin {
  type: 'admin';
  name: string;
  permissions: string[];
}

type Entity = User | Admin;

// 类型守卫
function isUser(entity: Entity): entity is User {
  return entity.type === 'user';
}

function isAdmin(entity: Entity): entity is Admin {
  return entity.type === 'admin';
}

// 使用
function handleEntity(entity: Entity) {
  if (isUser(entity)) {
    // entity 现在是 User 类型
    console.log(entity.email);
  } else {
    // entity 现在是 Admin 类型
    console.log(entity.permissions);
  }
}
```

### 6.2 断言函数

```typescript
function assertIsDefined<T>(
  value: T,
  message = 'Value is not defined'
): asserts value is NonNullable<T> {
  if (value === undefined || value === null) {
    throw new Error(message);
  }
}

// 使用
function processUser(user: User | null | undefined) {
  assertIsDefined(user, 'User must be defined');
  // 这里的 user 已经被 narrowing 为 User 类型
  console.log(user.name);
}
```

---

## 7. 工具类型速查

```typescript
// 常用工具类型
type Partial<T> = { [P in keyof T]?: T[P] };
type Required<T> = { [P in keyof T]-?: T[P] };
type Readonly<T> = { readonly [P in keyof T]: T[P] };
type Mutable<T> = { -readonly [P in keyof T]: T[P] };

type Pick<T, K extends keyof T> = { [P in K]: T[P] };
type Omit<T, K extends keyof T> = { [P in Exclude<keyof T, K>]: T[P] };

type Record<K extends string, T> = { [P in K]: T };
type Map<T, K extends string> = { [P in K]: T };

type Exclude<T, U> = T extends U ? never : T;
type Extract<T, U> = T extends U ? T : never;

type NonNullable<T> = T extends null | undefined ? never : T;

type ReturnType<T extends (...args: any) => any> =
  T extends (...args: any) => infer R ? R : any;
type Parameters<T extends (...args: any) => any> =
  T extends (...args: infer P) => any ? P : never;
type ConstructorParameters<T extends new (...args: any) => any> =
  T extends new (...args: infer P) => any ? P : never;
type InstanceType<T extends new (...args: any) => any> =
  T extends new (...args: any) => infer R ? R : any;
```

---

## 8. 工程实践

### 8.1 类型合并与扩展

```typescript
// 扩展第三方类型
declare module 'some-package' {
  interface Config {
    customOption?: string;
  }
}

// 扩展全局类型
declare global {
  namespace NodeJS {
    interface ProcessEnv {
      DEBUG: 'true' | 'false';
      LOG_LEVEL: 'debug' | 'info' | 'warn' | 'error';
    }
  }
}
```

### 8.2 类型安全配置

```typescript
// 配置文件类型
interface AppConfig {
  api: {
    baseUrl: string;
    timeout: number;
    retries: number;
  };
  features: {
    darkMode: boolean;
    experimental: boolean;
  };
}

// JSON Schema → TypeScript (使用 ajv 或 zod)
// 或手写 + const 断言
const config = {
  api: {
    baseUrl: 'https://api.anthropic.com',
    timeout: 5000,
    retries: 3,
  },
  features: {
    darkMode: false,
    experimental: true,
  },
} as const satisfies AppConfig;
```

---

## 练习

### 练习 1：实现一个类型安全的 EventEmitter（完整实现）

**要求**：
- 泛型支持事件类型
- 类型安全地触发和监听事件
- 支持 once、off 等常用方法

**答案**：

```typescript
// ============================================================
// 类型安全的 EventEmitter 实现
// ============================================================

type EventMap = Record<string, unknown>;

class TypedEventEmitter<T extends EventMap> {
  // 私有 listeners Map：key 是事件名，value 是处理函数 Set
  private listeners = new Map<keyof T, Set<Function>>();

  // ============================================================
  // on: 注册事件监听器
  // ============================================================
  on<K extends keyof T>(event: K, handler: (data: T[K]) => void): this {
    if (!this.listeners.has(event)) {
      this.listeners.set(event, new Set());
    }
    this.listeners.get(event)!.add(handler);
    return this;  // 支持链式调用
  }

  // ============================================================
  // once: 注册只触发一次的事件监听器
  // ============================================================
  once<K extends keyof T>(event: K, handler: (data: T[K]) => void): this {
    const wrappedHandler = (data: T[K]) => {
      handler(data);
      this.off(event, wrappedHandler);  // 触发后自动移除
    };
    return this.on(event, wrappedHandler);
  }

  // ============================================================
  // off: 移除事件监听器
  // ============================================================
  off<K extends keyof T>(event: K, handler: (data: T[K]) => void): this {
    const handlers = this.listeners.get(event);
    if (handlers) {
      handlers.delete(handler);
      if (handlers.size === 0) {
        this.listeners.delete(event);
      }
    }
    return this;
  }

  // ============================================================
  // emit: 触发事件
  // ============================================================
  emit<K extends keyof T>(event: K, data: T[K]): boolean {
    const handlers = this.listeners.get(event);
    if (!handlers || handlers.size === 0) {
      return false;
    }
    handlers.forEach(h => h(data));
    return true;
  }

  // ============================================================
  // removeAllListeners: 清除所有监听器
  // ============================================================
  removeAllListeners<K extends keyof T>(event?: K): this {
    if (event) {
      this.listeners.delete(event);
    } else {
      this.listeners.clear();
    }
    return this;
  }

  // ============================================================
  // listenerCount: 获取监听器数量
  // ============================================================
  listenerCount<K extends keyof T>(event: K): number {
    return this.listeners.get(event)?.size ?? 0;
  }
}

// ============================================================
// 使用示例
// ============================================================

// 定义事件类型接口
interface Events {
  message: { text: string; user: string };
  connected: void;
  error: { code: number; message: string };
  progress: { percent: number };
}

const emitter = new TypedEventEmitter<Events>();

// message 事件：data 类型自动推断为 { text: string; user: string }
emitter.on('message', (data) => {
  console.log(`${data.user}: ${data.text}`);
});

// connected 事件：data 类型是 void
emitter.on('connected', () => {
  console.log('Connected!');
});

// error 事件：data 类型是 { code: number; message: string }
emitter.on('error', (data) => {
  console.error(`Error ${data.code}: ${data.message}`);
});

// once 示例：只触发一次
emitter.once('progress', (data) => {
  console.log(`Initial progress: ${data.percent}%`);
});

// 触发事件
emitter.emit('message', { text: 'Hello!', user: 'alice' });
emitter.emit('connected');
emitter.emit('error', { code: 404, message: 'Not found' });

// 链式调用
emitter
  .on('message', (d) => console.log('Also received:', d))
  .once('connected', () => console.log('First connection!'));

// ============================================================
// 类型安全验证
// ============================================================
// 下面这些都会导致 TypeScript 编译错误：

// emitter.emit('message', { text: 'hi' });  // ❌ 缺少 user 字段
// emitter.emit('unknown', {});               // ❌ unknown 不在 Events 中
// emitter.on('error', (code) => {});        // ❌ error data 是对象不是 number
```

### 练习 2：实现 DeepPartial 和更多工具类型（完整实现）

**要求**：递归地将所有属性变为可选，并实现更多工具类型

**答案**：

```typescript
// ============================================================
// DeepPartial: 递归地将所有属性变为可选
// ============================================================
type DeepPartial<T> = T extends object
  ? { [P in keyof T]?: DeepPartial<T[P]> }
  : T;

// ============================================================
// DeepRequired: 递归地将所有属性变为必需
// ============================================================
type DeepRequired<T> = T extends object
  ? { [P in keyof T]-?: DeepRequired<T[P]> }
  : T;

// ============================================================
// DeepReadonly: 递归地将所有属性变为只读
// ============================================================
type DeepReadonly<T> = T extends object
  ? { readonly [P in keyof T]: DeepReadonly<T[P]> }
  : T;

// ============================================================
// DeepMutable: 递归地移除只读
// ============================================================
type DeepMutable<T> = T extends object
  ? { -readonly [P in keyof T]: DeepMutable<T[P]> }
  : T;

// ============================================================
// 使用示例
// ============================================================
interface Config {
  api: {
    url: string;
    timeout: number;
    retries: number;
  };
  features: {
    darkMode: boolean;
    notifications: {
      enabled: boolean;
      sound: boolean;
    };
  };
}

type PartialConfig = DeepPartial<Config>;
// {
//   api?: {
//     url?: string;
//     timeout?: number;
//     retries?: number;
//   };
//   features?: {
//     darkMode?: boolean;
//     notifications?: {
//       enabled?: boolean;
//       sound?: boolean;
//     };
//   };
// }

// ============================================================
// 实际应用场景
// ============================================================

// 场景 1: 用户配置更新（只更新部分字段）
function updateConfig(updates: DeepPartial<Config>): Config {
  const current: Config = {
    api: { url: 'https://api.example.com', timeout: 5000, retries: 3 },
    features: { darkMode: false, notifications: { enabled: true, sound: true } },
  };

  // 深度合并
  return deepMerge(current, updates);
}

function deepMerge<T extends object>(target: T, source: DeepPartial<T>): T {
  const result = { ...target };
  for (const key in source) {
    const sourceValue = (source as any)[key];
    const targetValue = (target as any)[key];
    if (
      typeof sourceValue === 'object' &&
      sourceValue !== null &&
      !Array.isArray(sourceValue) &&
      typeof targetValue === 'object' &&
      targetValue !== null &&
      !Array.isArray(targetValue)
    ) {
      (result as any)[key] = deepMerge(targetValue, sourceValue);
    } else if (sourceValue !== undefined) {
      (result as any)[key] = sourceValue;
    }
  }
  return result;
}

// 场景 2: 测试数据生成
const testConfig: DeepPartial<Config> = {
  api: { url: 'http://localhost:3000' },  // 只设置 URL，其他都是可选的
};

// ============================================================
// 其他常用工具类型
// ============================================================

// PickByValue: 根据值类型挑选属性
type PickByValue<T, Value> = {
  [K in keyof T as T[K] extends Value ? K : never]: T[K]
};

// OmitByValue: 根据值类型排除属性
type OmitByValue<T, Value> = {
  [K in keyof T as T[K] extends Value ? never : K]: T[K]
};

// RequiredKeys: 获取必需的属性名
type RequiredKeys<T> = {
  [K in keyof T]-?: undefined extends T[K] ? never : K
}[keyof T];

// OptionalKeys: 获取可选的属性名
type OptionalKeys<T> = {
  [K in keyof T]-?: undefined extends T[K] ? K : never
}[keyof T];

// 使用示例
interface User {
  id: string;        // 必需
  name: string;      // 必需
  email?: string;    // 可选
  age?: number;      // 可选
}

type RequiredUserKeys = RequiredKeys<User>;      // "id" | "name"
type OptionalUserKeys = OptionalKeys<User>;      // "email" | "age"

type StringOnlyProps = PickByValue<User, string>;  // { id: string; name: string; email?: string }
type NonStringProps = OmitByValue<User, string>;  // { age?: number }
```

---

## 总结

| 模式 | 用途 |
|------|------|
| Branded Types | 区分语义相同的不同类型 |
| Discriminated Unions | 状态机、结果类型 |
| Const Assertions | 字面量只读 |
| 条件类型 | 类型运算、提取 |
| 映射类型 | 类型转换 |
| Result 类型 | 错误处理 |
| 装饰器 | 横切关注点 |

`★ Insight ─────────────────────────────────────`
TypeScript 的类型系统是图灵完备的——理论上可以做任何类型运算。但实战中应该追求**类型可读性**而非类型技巧。好的类型设计让代码自文档化，IDE 能提供准确提示，重构时编译器能捕获所有破坏性变更。
`─────────────────────────────────────────────────`
