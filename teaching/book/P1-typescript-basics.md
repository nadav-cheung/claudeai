# P1 - TypeScript 入门：从 JavaScript 到类型安全

> **本章目标**：学完本章后，你将掌握 TypeScript 的核心概念，能够编写类型安全的代码，理解为什么 Claude Code 选择 TypeScript。

---

## 1. 为什么需要 TypeScript？

### 1.1 JavaScript 的问题

JavaScript 是一门**动态类型**语言，这意味着：

```javascript
// JavaScript：灵活但危险
function add(a, b) {
  return a + b;
}

add(1, 2);      // 返回 3 ✓
add("1", "2");  // 返回 "12" ✓（字符串拼接）
add(1, "2");    // 返回 "12" ✓（隐式转换）
add({}, []);     // 返回 "[object Object]" ✓（这有意义吗？）
```

这些"灵活性"在大型项目中是噩梦——你永远不知道函数期待什么类型的参数。

### 1.2 TypeScript 的解决方案

TypeScript 在 JavaScript 基础上添加了**静态类型检查**：

```typescript
// TypeScript：类型安全
function add(a: number, b: number): number {
  return a + b;
}

add(1, 2);      // ✓
add("1", "2");  // ✗ 编译错误！Argument of type 'string' is not assignable to parameter of type 'number'
add(1, "2");    // ✗ 编译错误！
```

**核心优势**：
1. **编译时错误检测** —— 错误在开发时发现，而非运行时
2. **智能提示** —— IDE 知道每个变量的类型，提供准确的自动补全
3. **代码文档** —— 类型本身就是最好的文档
4. **重构安全** —— 修改类型时，编译器告诉你哪些地方需要更新

---

## 2. 基本类型

### 2.1 原始类型

TypeScript 支持与 JavaScript 相同的原始类型：

```typescript
// 字符串
let name: string = "Claude";
let greeting: string = `Hello, ${name}`;

// 数字
let age: number = 25;
let pi: number = 3.14159;

// 布尔值
let isActive: boolean = true;
let isComplete: boolean = false;

// undefined 和 null
let u: undefined = undefined;
let n: null = null;
```

### 2.2 类型推断

TypeScript 具有**智能类型推断**能力——你不必处处标注类型：

```typescript
// TypeScript 会自动推断类型
let name = "Claude";    // 推断为 string
let age = 25;           // 推断为 number
let isActive = true;    // 推断为 boolean

// 后续赋值会检查类型
name = 25;  // ✗ 错误：Type 'number' is not assignable to type 'string'
```

**最佳实践**：优先依赖类型推断，仅在类型不明显时才显式标注。

### 2.3 数组

```typescript
// 两种写法等价
let numbers: number[] = [1, 2, 3, 4, 5];
let numbers2: Array<number> = [1, 2, 3, 4, 5];

// 字符串数组
let names: string[] = ["Alice", "Bob", "Charlie"];

// 混合类型（尽量避免）
let mixed: (string | number)[] = [1, "two", 3];
```

### 2.4 元组（Tuple）

固定长度、固定类型的数组：

```typescript
// 定义一个坐标元组
let coordinate: [number, number] = [40.7128, -74.0060];

// 错误示例
coordinate = [-74.0060, 40.7128];  // ✗ 顺序错误！
coordinate = [40.7128];            // ✗ 长度不对！
coordinate = [40.7128, -74.0060, 1];  // ✗ 长度多了！
```

### 2.5 枚举（Enum）

一组有名字的常量值：

```typescript
// 数字枚举（默认）
enum Direction {
  Up,    // 0
  Down,  // 1
  Left,  // 2
  Right  // 3
}

let move: Direction = Direction.Up;

// 字符串枚举
enum Status {
  Success = "SUCCESS",
  Error = "ERROR",
  Loading = "LOADING"
}

let currentStatus: Status = Status.Loading;
```

---

## 3. 接口（Interface）

接口定义了对象的"形状"（Shape）：

### 3.1 基本用法

```typescript
// 定义一个用户接口
interface User {
  id: number;
  name: string;
  email: string;
  age?: number;  // 可选属性
  readonly createdAt: Date;  // 只读属性
}

// 创建符合接口的对象
const user: User = {
  id: 1,
  name: "Alice",
  email: "alice@example.com",
  createdAt: new Date()
};

user.createdAt = new Date();  // ✗ 错误：Cannot assign to 'createdAt' because it is a read-only property
```

### 3.2 接口继承

```typescript
interface Animal {
  name: string;
}

interface Dog extends Animal {
  breed: string;
}

const dog: Dog = {
  name: "Buddy",
  breed: "Golden Retriever"
};
```

### 3.3 方法定义

```typescript
interface Calculator {
  add(a: number, b: number): number;
  subtract(a: number, b: number): number;
}

const calc: Calculator = {
  add(a, b) {
    return a + b;
  },
  subtract(a, b) {
    return a - b;
  }
};

console.log(calc.add(5, 3));  // 8
```

---

## 4. 联合类型与交叉类型

### 4.1 联合类型（Union）

一个值可以是多种类型之一：

```typescript
// 允许是 string 或 number
let id: string | number;
id = "user_123";  // ✓
id = 12345;        // ✓
id = true;         // ✗ 错误

// 函数参数使用联合类型
function printId(id: string | number) {
  console.log(`ID: ${id}`);
}

printId("abc");  // ✓
printId(123);    // ✓
```

### 4.2 类型守卫（Type Guard）

在分支中缩小类型范围：

```typescript
function processValue(value: string | number) {
  if (typeof value === "string") {
    // TypeScript 知道这里 value 是 string
    console.log(value.toUpperCase());
  } else {
    // TypeScript 知道这里 value 是 number
    console.log(value.toFixed(2));
  }
}
```

### 4.3 交叉类型（Intersection）

组合多个类型：

```typescript
interface Loggable {
  log(): void;
}

interface Serializable {
  serialize(): string;
}

type LoggableAndSerializable = Loggable & Serializable;

const obj: LoggableAndSerializable = {
  log() {
    console.log("Logging...");
  },
  serialize() {
    return "{ logged: true }";
  }
};
```

---

## 5. 泛型（Generic）

泛型让函数和接口能够工作于多种类型，同时保持类型安全：

### 5.1 泛型函数

```typescript
// 不使用泛型：只能返回一种类型
function firstOfStrings(arr: string[]): string {
  return arr[0];
}

// 使用泛型：适用于任何类型
function firstOf<T>(arr: T[]): T | undefined {
  return arr[0];
}

const str = firstOf(["a", "b", "c"]);  // str 是 string | undefined
const num = firstOf([1, 2, 3]);        // num 是 number | undefined
const bool = firstOf([true, false]);    // bool 是 boolean | undefined
```

### 5.2 泛型接口

```typescript
// 定义一个泛型容器
interface Container<T> {
  value: T;
  getValue(): T;
  setValue(newValue: T): void;
}

const stringContainer: Container<string> = {
  value: "Hello",
  getValue() {
    return this.value;
  },
  setValue(newValue) {
    this.value = newValue;
  }
};

const numberContainer: Container<number> = {
  value: 42,
  getValue() {
    return this.value;
  },
  setValue(newValue) {
    this.value = newValue;
  }
};
```

### 5.3 泛型约束

限制泛型的范围：

```typescript
// 要求 T 必须有 length 属性
interface HasLength {
  length: number;
}

function logLength<T extends HasLength>(arg: T): number {
  return arg.length;
}

logLength("hello");     // ✓ string 有 length
logLength([1, 2, 3]); // ✓ array 有 length
logLength({ length: 10, value: "x" }); // ✓ 有 length 属性
logLength(123);        // ✗ number 没有 length
```

---

## 6. 常用工具类型

TypeScript 内置了很多实用的工具类型：

### 6.1 Partial<T> - 所有属性变为可选

```typescript
interface User {
  id: number;
  name: string;
  email: string;
}

// 更新用户时，只需提供要更新的字段
function updateUser(id: number, updates: Partial<User>) {
  // updates 的所有属性都是可选的
}

updateUser(1, { name: "Bob" });  // ✓ 只更新 name
updateUser(1, {});                // ✓ 允许空对象
```

### 6.2 Required<T> - 所有属性变为必需

```typescript
interface Config {
  host?: string;
  port?: number;
}

function initService(config: Required<Config>) {
  // host 和 port 都是必需的
}
```

### 6.3 Pick<T, K> - 选取部分属性

```typescript
interface User {
  id: number;
  name: string;
  email: string;
  password: string;
}

// 只暴露 id 和 name
type PublicUser = Pick<User, "id" | "name">;

const user: PublicUser = {
  id: 1,
  name: "Alice"
  // email 和 password 不可访问
};
```

### 6.4 Omit<T, K> - 排除部分属性

```typescript
interface User {
  id: number;
  name: string;
  email: string;
  password: string;
}

// 排除敏感字段
type SafeUser = Omit<User, "password">;

const user: SafeUser = {
  id: 1,
  name: "Alice",
  email: "alice@example.com"
  // password 不可访问
};
```

### 6.5 Record<K, V> - 创建键值对类型

```typescript
// 字符串到数字的映射
type ScoreMap = Record<string, number>;

const scores: ScoreMap = {
  Alice: 95,
  Bob: 87,
  Charlie: 92
};

// 枚举作为键
enum Status {
  Active = "ACTIVE",
  Inactive = "INACTIVE"
}

type StatusConfig = Record<Status, { label: string; color: string }>;

const config: StatusConfig = {
  [Status.Active]: { label: "活跃", color: "green" },
  [Status.Inactive]: { label: "不活跃", color: "gray" }
};
```

---

## 7. 异步编程：Promise 与 async/await

### 7.1 Promise 基础

Promise 代表一个异步操作的最终结果：

```typescript
// 创建 Promise
function fetchUser(id: number): Promise<User> {
  return new Promise((resolve, reject) => {
    setTimeout(() => {
      if (id > 0) {
        resolve({ id, name: "Alice", email: "alice@example.com" });
      } else {
        reject(new Error("Invalid user ID"));
      }
    }, 1000);
  });
}

// 使用 Promise
fetchUser(1)
  .then(user => {
    console.log(`User: ${user.name}`);
  })
  .catch(error => {
    console.error(`Error: ${error.message}`);
  });
```

### 7.2 async/await 语法

async/await 是 Promise 的同步写法：

```typescript
async function getUser(id: number): Promise<User> {
  try {
    const response = await fetch(`https://api.example.com/users/${id}`);
    const user = await response.json();
    return user;
  } catch (error) {
    console.error("Failed to fetch user:", error);
    throw error;
  }
}

// 调用 async 函数
async function main() {
  const user = await getUser(1);
  console.log(`User: ${user.name}`);
}
```

### 7.3 并行执行

```typescript
async function fetchAllUsers(ids: number[]): Promise<User[]> {
  // 同时发起所有请求（并行）
  const promises = ids.map(id => fetchUser(id));
  return Promise.all(promises);
}

// 使用
const users = await fetchAllUsers([1, 2, 3]);
```

---

## 8. 模块系统：import 与 export

### 8.1 导出

```typescript
// 导出变量
export const PI = 3.14159;

// 导出函数
export function add(a: number, b: number): number {
  return a + b;
}

// 导出接口
export interface User {
  id: number;
  name: string;
}

// 默认导出（每个文件只能有一个）
export default class App {
  run() {
    console.log("App is running");
  }
}
```

### 8.2 导入

```typescript
// 导入命名导出
import { add, PI, User } from "./math";

// 导入默认导出
import App from "./app";

// 导入时重命名
import { add as sum } from "./math";

// 导入所有导出
import * as math from "./math";
console.log(math.PI);
```

---

## 9. 类型守卫与类型断言

### 9.1 类型断言

告诉 TypeScript 某个值的具体类型：

```typescript
// 假设你知道这个值是字符串
function processValue(value: unknown) {
  const str = value as string;
  console.log(str.toUpperCase());
}

// 非空断言（确定值不为 null/undefined）
function getLength(str: string | null): number {
  return str!.length;  // 告诉 TS str 一定有值
}
```

### 9.2 自定义类型守卫

```typescript
interface Cat {
  meow(): void;
}

interface Dog {
  bark(): void;
}

function isCat(animal: Cat | Dog): animal is Cat {
  return (animal as Cat).meow !== undefined;
}

function makeSound(animal: Cat | Dog) {
  if (isCat(animal)) {
    animal.meow();
  } else {
    animal.bark();
  }
}
```

---

## 10. 实战练习

### 练习 1：实现一个类型安全的工具库

创建一个 `stringUtils.ts`，实现以下函数：

```typescript
// 1. 重复字符串
function repeat(str: string, times: number): string

// 2. 截断字符串
function truncate(str: string, maxLength: number, suffix?: string): string

// 3. 提取首字母
function getInitials(name: string): string
```

**答案**：

```typescript
function repeat(str: string, times: number): string {
  return str.repeat(times);
}

function truncate(str: string, maxLength: number, suffix: string = "..."): string {
  if (str.length <= maxLength) return str;
  return str.slice(0, maxLength - suffix.length) + suffix;
}

function getInitials(name: string): string {
  return name
    .split(" ")
    .map(part => part[0])
    .join("")
    .toUpperCase();
}

// 测试
console.log(repeat("ha", 3));           // "hahaha"
console.log(truncate("Hello World", 8));    // "Hello..."
console.log(getInitials("John Doe"));       // "JD"
```

### 练习 2：实现一个简单的结果类型

```typescript
// 实现一个 Result 类型，用于表示操作成功或失败

type Result<T, E = Error> =
  | { success: true; value: T }
  | { success: false; error: E };

function divide(a: number, b: number): Result<number, string> {
  if (b === 0) {
    return { success: false, error: "Division by zero" };
  }
  return { success: true, value: a / b };
}

// 使用
const result = divide(10, 2);
if (result.success) {
  console.log(`Result: ${result.value}`);  // 5
} else {
  console.error(`Error: ${result.error}`);
}
```

---

## 11. 常见错误与解决方案

### 错误 1：`Object is possibly 'null'`

```typescript
// 问题
function getName(user?: { name: string }) {
  return user.name.toUpperCase();  // ✗ user 可能为 null
}

// 解决
function getName(user?: { name: string }) {
  if (!user) return "Anonymous";
  return user.name.toUpperCase();
}
```

### 错误 2：`Argument of type 'X' is not assignable to parameter of type 'Y'`

通常是类型不匹配。检查：
1. 是否传递了正确的类型
2. 是否需要类型断言
3. 是否需要使用联合类型

### 错误 3：`Property 'X' does not exist on type 'Y'`

通常是：
1. 对象类型没有定义该属性
2. 拼写错误
3. 需要使用索引签名 `Record<string, unknown>`

---

## 总结

本章学习了 TypeScript 的核心概念：

| 概念 | 用途 |
|------|------|
| 基本类型 | string, number, boolean, null, undefined |
| 接口 | 定义对象的形状 |
| 联合类型 | 值可以是多种类型之一 |
| 泛型 | 创建可复用的类型安全组件 |
| 工具类型 | Partial, Pick, Omit, Record 等 |
| async/await | 异步编程语法糖 |
| import/export | 模块化代码组织 |

**关键理解**：TypeScript 的类型系统是在编译时工作的，它不会影响运行时的性能。它的目的是让你在开发时发现错误，而不是在用户使用时。

---

## 下一篇

👉 [P2 - Node.js 与 Bun 入门](P2-nodejs-bun.md) —— 学会使用 JavaScript 运行时

`★ Insight ─────────────────────────────────────`
TypeScript 的"类型"不是束缚，而是**合同**。当你定义一个函数接受 `User` 类型时，你在使用者和实现者之间签订了一份合同："我保证给你一个包含 id、name、email 属性的对象"。TypeScript 会确保没有人违反这份合同。这在大型项目中比文档更可靠——代码变了，类型检查自动跟上。
`─────────────────────────────────────────────────`
