# P4 - React 基础速成：构建终端界面

> **本章目标**：学完本章后，你将掌握 React 的核心概念，理解 Claude Code 如何使用 React（Ink）构建终端界面。

---

## 1. React 简介

### 1.1 什么是 React？

React 是 Facebook 开发的 UI 库，用于构建用户界面。它的核心思想是：

**组件化**：把 UI 拆分成独立的、可复用的组件
**声明式**：描述"UI 应该是什么样子"，而不是"如何一步步修改 UI"

### 1.2 React 的核心概念

```jsx
// 命令式（一步一步告诉做什么）
const button = document.createElement('button');
button.textContent = '点击我';
button.addEventListener('click', () => alert('Clicked!'));
document.body.appendChild(button);

// 声明式（描述 UI 应该是什么）
function Button() {
  return <button onClick={() => alert('Clicked!')}>点击我</button>;
}
```

---

## 2. JSX 基础

### 2.1 什么是 JSX？

JSX 是 JavaScript 的语法扩展，允许在 JavaScript 中写 HTML 类似的代码：

```jsx
// JSX 语法
const element = <h1>Hello, World!</h1>;

// 编译后变成
const element = React.createElement('h1', null, 'Hello, World!');
```

### 2.2 在 JSX 中嵌入表达式

```jsx
const name = 'Alice';
const greeting = <p>Hello, {name}!</p>;

// 计算表达式
const a = 5;
const b = 3;
const sum = <p>{a} + {b} = {a + b}</p>;

// 调用函数
function formatName(user) {
  return user.firstName + ' ' + user.lastName;
}

const user = { firstName: 'John', lastName: 'Doe' };
const element = <p>Hello, {formatName(user)}!</p>;
```

### 2.3 JSX 属性

```jsx
// 使用引号指定字符串
const element = <div id="root">Content</div>;

// 使用大括号嵌入表达式
const element = <img src={user.avatarUrl} alt={user.name} />;

// 布尔属性
const element = <input disabled={true} />;
// 简写（disabled 等同于 disabled={true}）
const element = <input disabled />;
```

### 2.4 JSX 样式

```jsx
// 行内样式（需要是对象）
const style = {
  color: 'blue',
  backgroundColor: 'lightgray',
  fontSize: '14px'
};

const element = <p style={style}>Styled text</p>;

// 或者
const element = <p style={{ color: 'blue', marginTop: '10px' }}>Inline style</p>;
```

---

## 3. 组件与 Props

### 3.1 函数组件

组件是返回 JSX 的函数：

```jsx
function Welcome() {
  return <h1>Welcome!</h1>;
}

function App() {
  return (
    <div>
      <Welcome />
      <Welcome />
      <Welcome />
    </div>
  );
}
```

### 3.2 Props

Props 是组件的输入参数：

```jsx
// 定义带 props 的组件
function Welcome(props) {
  return <h1>Hello, {props.name}!</h1>;
}

// 使用组件并传递 props
function App() {
  return (
    <div>
      <Welcome name="Alice" />
      <Welcome name="Bob" />
      <Welcome name="Charlie" />
    </div>
  );
}
```

### 3.3 Props 解构

```jsx
// 使用解构
function Welcome({ name, age }) {
  return (
    <div>
      <h1>Hello, {name}!</h1>
      <p>Age: {age}</p>
    </div>
  );
}

// 带默认值的 props
function Welcome({ name = 'Guest', age = 0 }) {
  return <h1>Hello, {name}!</h1>;
}
```

---

## 4. State 与 Hooks

### 4.1 什么是 State？

State 是组件的内部数据，会影响组件的渲染：

```jsx
import { useState } from 'react';

function Counter() {
  // useState 返回 [当前值, 更新函数]
  const [count, setCount] = useState(0);

  return (
    <div>
      <p>计数: {count}</p>
      <button onClick={() => setCount(count + 1)}>增加</button>
      <button onClick={() => setCount(count - 1)}>减少</button>
      <button onClick={() => setCount(0)}>重置</button>
    </div>
  );
}
```

### 4.2 useState 详细用法

```jsx
// 基础用法
const [value, setValue] = useState(initialValue);

// 函数式更新（基于前一个值）
setCount(prev => prev + 1);

// 多个状态
const [name, setName] = useState('');
const [age, setAge] = useState(0);
const [email, setEmail] = useState('');

// 对象状态（注意要合并）
const [form, setForm] = useState({ name: '', email: '' });

function updateForm(field, value) {
  setForm(prev => ({ ...prev, [field]: value }));
}
```

### 4.3 useEffect

useEffect 用于处理副作用（数据获取、订阅、定时器等）：

```jsx
import { useState, useEffect } from 'react';

function UserProfile({ userId }) {
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    // 组件挂载时执行
    fetchUser(userId)
      .then(user => {
        setUser(user);
        setLoading(false);
      });

    // 可选：返回清理函数（组件卸载时执行）
    return () => {
      console.log('清理...');
    };
  }, [userId]); // 依赖数组：userId 变化时重新执行

  if (loading) return <p>加载中...</p>;
  return <div>{user.name}</div>;
}
```

---

## 5. 条件渲染与列表

### 5.1 条件渲染

```jsx
// if 语句
function Greeting({ isLoggedIn }) {
  if (isLoggedIn) {
    return <h1>Welcome back!</h1>;
  }
  return <h1>Please sign in.</h1>;
}

// 三元运算符
function Greeting({ isLoggedIn }) {
  return isLoggedIn ? <h1>Welcome back!</h1> : <h1>Please sign in.</h1>;
}

// && 运算符（适合条件显示某元素）
function Mailbox({ unreadMessages }) {
  return (
    <div>
      <h1>Hello!</h1>
      {unreadMessages.length > 0 && (
        <p>You have {unreadMessages.length} unread messages.</p>
      )}
    </div>
  );
}
```

### 5.2 列表渲染

```jsx
function TodoList({ todos }) {
  return (
    <ul>
      {todos.map(todo => (
        <li key={todo.id}>
          {todo.completed ? <s>{todo.text}</s> : todo.text}
        </li>
      ))}
    </ul>
  );
}

// 或者
function TodoList({ todos }) {
  const todoItems = todos.map(todo => (
    <li key={todo.id}>{todo.text}</li>
  ));

  return <ul>{todoItems}</ul>;
}
```

**注意**：每个列表元素都需要 `key` 属性，帮助 React 高效更新列表。

---

## 6. React 与 Ink

### 6.1 Ink 是什么？

Ink 是 React 的终端版本——用 React 语法构建 CLI 界面：

```jsx
import { render, Text, Box } from 'ink';

// Ink 组件（与 React 类似）
function Counter() {
  const [count, setCount] = useState(0);

  return (
    <Box>
      <Text>计数: {count}</Text>
      <Text> </Text>
      <Text color="green" onPress={() => setCount(count + 1)}>
        [增加]
      </Text>
    </Box>
  );
}

render(<Counter />);
```

### 6.2 Ink 核心组件

| 组件 | 用途 | React 类比 |
|------|------|-----------|
| `<Box>` | 容器，布局 | `<div>` |
| `<Text>` | 文本 | `<span>` |
| `<Static>` | 不重新渲染的静态内容 | 纯展示 |
| `<Spacer>` | 空白 | flex spacer |

### 6.3 Claude Code 的 UI 结构

```jsx
// Claude Code 的 REPL 屏幕简化版
function REPL() {
  const [input, setInput] = useState('');
  const [messages, setMessages] = useState([]);

  return (
    <Box flexDirection="column" height={100}>
      {/* 消息列表 */}
      <Box flexDirection="column" flexGrow={1}>
        {messages.map((msg, i) => (
          <Message key={i} {...msg} />
        ))}
      </Box>

      {/* 输入框 */}
      <Box>
        <Text>{'> '}</Text>
        <TextInput
          value={input}
          onChange={setInput}
          onSubmit={handleSubmit}
        />
      </Box>
    </Box>
  );
}
```

---

## 7. 实战：构建 Ink 待办列表

### 7.1 项目结构

```
ink-todo/
├── src/
│   └── index.tsx
├── package.json
└── tsconfig.json
```

### 7.2 完整代码

```tsx
import React, { useState, useEffect } from 'react';
import { render, Box, Text, Newline } from 'ink';

interface Todo {
  id: number;
  text: string;
  completed: boolean;
}

function App() {
  const [todos, setTodos] = useState<Todo[]>([
    { id: 1, text: '学习 TypeScript', completed: false },
    { id: 2, text: '学习 Node.js', completed: false },
    { id: 3, text: '学习 React', completed: true },
  ]);
  const [input, setInput] = useState('');

  const addTodo = (text: string) => {
    if (!text.trim()) return;
    setTodos(prev => [
      ...prev,
      {
        id: prev.length > 0 ? Math.max(...prev.map(t => t.id)) + 1 : 1,
        text: text.trim(),
        completed: false,
      },
    ]);
    setInput('');
  };

  const toggleTodo = (id: number) => {
    setTodos(prev =>
      prev.map(todo =>
        todo.id === id ? { ...todo, completed: !todo.completed } : todo
      )
    );
  };

  const deleteTodo = (id: number) => {
    setTodos(prev => prev.filter(todo => todo.id !== id));
  };

  return (
    <Box flexDirection="column" padding={1}>
      <Text bold>待办事项</Text>
      <Newline />

      {todos.map(todo => (
        <Box key={todo.id}>
          <Text
            color={todo.completed ? 'gray' : 'white'}
            textDecoration={todo.completed ? 'strikethrough' : 'none'}
          >
            {todo.completed ? '✓' : '○'} {todo.text}
          </Text>
          <Text dimColor> | </Text>
          <Text
            color="red"
            cursor
            onPress={() => deleteTodo(todo.id)}
          >
            删除
          </Text>
        </Box>
      ))}

      <Newline />
      <Box>
        <Text bold color="green">
          > {input}
        </Text>
      </Box>
      <Text dimColor>输入新任务，按 Enter 添加</Text>
    </Box>
  );
}

render(<App />);
```

---

## 8. 常见问题

### Q1: 为什么不直接用 DOM 而用 React？

React 的优势：
- **声明式**：描述 UI 而不是操作 UI
- **组件化**：复用和组合
- **虚拟 DOM**：高效的批量更新
- **生态**：丰富的组件库

### Q2: key 属性为什么重要？

key 帮助 React 识别哪些元素改变了：

```jsx
// 错误：没有 key
todos.map(todo => <TodoItem todo={todo} />);

// 正确：使用唯一 ID 作为 key
todos.map(todo => <TodoItem key={todo.id} todo={todo} />);

// 可以：使用索引作为 key（仅当列表不会变化时）
todos.map((todo, index) => <TodoItem key={index} todo={todo} />);
```

### Q3: useEffect 的依赖数组是做什么的？

依赖数组告诉 React 什么时候重新执行 effect：

```jsx
useEffect(() => {
  // 每次 count 变化时执行
}, [count]);

useEffect(() => {
  // 只在组件挂载时执行一次
}, []);

useEffect(() => {
  // 每次渲染都执行（避免使用）
});
```

---

## 9. 练习

### 练习 1：实现计数器组件

**目标**：创建一个带 + / - 按钮的计数器

**提示**：
- 使用 `useState` 保存计数
- 使用 `useEffect` 在计数变化时保存到 localStorage

**答案要点**：
```jsx
function Counter() {
  const [count, setCount] = useState(0);

  useEffect(() => {
    localStorage.setItem('count', count.toString());
  }, [count]);

  return (
    <Box>
      <Text>计数: {count}</Text>
      <Box flexDirection="row">
        <Text onPress={() => setCount(c => c - 1)}> - </Text>
        <Text onPress={() => setCount(c => c + 1)}> + </Text>
      </Box>
    </Box>
  );
}
```

### 练习 2：实现 TodoList 组件

**目标**：渲染一个 todo 列表，支持添加和删除

**提示**：
- 使用 `useState` 保存 todo 数组
- 使用 `filter` 删除 todo

**答案要点**：
```jsx
function TodoList() {
  const [todos, setTodos] = useState([]);
  const [input, setInput] = useState('');

  const addTodo = () => {
    if (!input.trim()) return;
    setTodos([...todos, { id: Date.now(), text: input, done: false }]);
    setInput('');
  };

  const toggleTodo = (id) => {
    setTodos(todos.map(t =>
      t.id === id ? { ...t, done: !t.done } : t
    ));
  };

  return (
    <Box>
      <TextInput value={input} onChange={setInput} />
      <Button onPress={addTodo}>添加</Button>
      {todos.map(todo => (
        <Box key={todo.id}>
          <Text
            onPress={() => toggleTodo(todo.id)}
            style={todo.done ? { textDecoration: 'line-through' } : {}}
          >
            {todo.text}
          </Text>
        </Box>
      ))}
    </Box>
  );
}
```

### 练习 3：实现自定义 Hook

**目标**：创建一个 `useDebounce` Hook

**提示**：
- 使用 `useState` 保存防抖后的值
- 使用 `useEffect` + `setTimeout` 实现延迟

**答案要点**：
```jsx
function useDebounce(value, delay = 500) {
  const [debouncedValue, setDebouncedValue] = useState(value);

  useEffect(() => {
    const timer = setTimeout(() => {
      setDebouncedValue(value);
    }, delay);

    return () => clearTimeout(timer);
  }, [value, delay]);

  return debouncedValue;
}

// 使用
function SearchComponent() {
  const [query, setQuery] = useState('');
  const debouncedQuery = useDebounce(query, 300);

  useEffect(() => {
    if (debouncedQuery) {
      // 执行搜索
      console.log('搜索:', debouncedQuery);
    }
  }, [debouncedQuery]);

  return <TextInput value={query} onChange={setQuery} />;
}
```

---

## 总结

| 概念 | 用途 |
|------|------|
| JSX | 在 JavaScript 中写 UI |
| 组件 | 可复用的 UI 片段 |
| Props | 组件的输入参数 |
| useState | 组件内部状态 |
| useEffect | 副作用处理 |
| 条件/列表渲染 | 动态 UI |

---

## 下一篇

👉 [01 - 构建你的第一个CLI工具](01-构建你的第一个CLI工具.md) —— 开始构建迷你 Claude Code

`★ Insight ─────────────────────────────────────`
React 的核心是**组件 = 函数**，**Props = 输入**，**State = 内存**。UI 是 props 和 state 的函数——当它们变化时，React 自动更新 UI。这比手动操作 DOM 安全得多：你只需要描述"要什么"，React 负责"怎么做"。Ink 把这个思想带到终端，让 CLI 界面也可以用 React 开发。
`─────────────────────────────────────────────────`
