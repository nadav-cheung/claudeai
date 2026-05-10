# 04 - 添加交互界面

> **本章目标**：学完本章后，你将掌握 Ink 的用法，能够为 Mini-Claude 构建一个带彩色输出、光标定位和实时更新的终端界面。

---

## 1. Ink 简介

### 1.1 什么是 Ink？

Ink 是用 React 语法构建 CLI 界面的库。它让你像写 Web 前端一样写终端 UI。

```typescript
// React（网页）
function Counter() {
  const [count, setCount] = useState(0);
  return <button onClick={() => setCount(count + 1)}>{count}</button>;
}

// Ink（终端）
import { render, Text, Box } from 'ink';

function Counter() {
  const [count, setCount] = useState(0);
  return (
    <Box>
      <Text>计数: {count}</Text>
      <Text onPress={() => setCount(count + 1)}> [增加]</Text>
    </Box>
  );
}

render(<Counter />);
```

### 1.2 Ink vs 普通 CLI

| 方面 | 普通 console | Ink |
|------|-------------|-----|
| 更新方式 | 打印新行 | 原地更新 |
| 光标控制 | 困难 | 声明式 |
| 动画效果 | 很难 | 容易 |
| 组件复用 | 函数 | React 组件 |
| 学习曲线 | 低 | 中 |

---

## 2. 安装 Ink

### 2.1 安装依赖

```bash
npm install ink react
```

### 2.2 项目结构调整

```text
mini-claude/
├── src/
│   ├── index.ts          # commander 入口
│   ├── cli/
│   │   └── repl.tsx      # Ink REPL 界面
│   └── ...
```

---

## 3. Ink 基础组件

### 3.1 Box - 容器

```typescript
import { render, Box, Text } from 'ink';

render(
  <Box flexDirection="column" gap={1}>
    <Text>第一行</Text>
    <Text>第二行</Text>
  </Box>
);
```

**Box 属性**：

| 属性 | 类型 | 说明 |
|------|------|------|
| `flexDirection` | `row \| column` | 排列方向 |
| `gap` | `number` | 元素间距 |
| `padding` | `number` | 内边距 |
| `margin` | `number` | 外边距 |
| `borderStyle` | `single \| double \| round` | 边框样式 |
| `width` | `number` | 固定宽度 |
| `height` | `number` | 固定高度 |

### 3.2 Text - 文本

```typescript
import { render, Text } from 'ink';

// 基础文本
<Text>Hello World</Text>

// 彩色文本
<Text color="green">成功</Text>
<Text color="red" backgroundColor="white">错误</Text>

// 样式
<Text bold>粗体</Text>
<Text italic>斜体</Text>
<Text underline>下划线</Text>

// 可点击（交互）
<Text onPress={() => console.log('clicked')}>点击我</Text>
```

### 3.3 Spacer - 空白

```typescript
<Box>
  <Text>左</Text>
  <Spacer />
  <Text>右</Text>
</Box>
```

---

## 4. 构建消息列表

### 4.1 Message 组件

```typescript
// src/cli/components/Message.tsx
import React from 'react';
import { Text, Box } from 'ink';

interface MessageProps {
  role: 'user' | 'assistant';
  content: string;
  timestamp?: Date;
}

export function Message({ role, content, timestamp }: MessageProps) {
  const isUser = role === 'user';
  const time = timestamp?.toLocaleTimeString() || '';

  return (
    <Box flexDirection="column" marginY={1}>
      <Box>
        <Text color={isUser ? 'cyan' : 'green'}>
          {isUser ? '👤 你' : '🤖 Claude'}
        </Text>
        {time && (
          <Text dimColor> {time}</Text>
        )}
      </Box>
      <Box flexDirection="column" paddingLeft={2}>
        {content.split('\n').map((line, i) => (
          <Text key={i}>{line || ' '}</Text>
        ))}
      </Box>
    </Box>
  );
}
```

### 4.2 MessageList 组件

```typescript
// src/cli/components/MessageList.tsx
import React from 'react';
import { Box } from 'ink';
import { Message } from './Message.js';

interface MessageData {
  role: 'user' | 'assistant';
  content: string;
  timestamp?: Date;
}

interface MessageListProps {
  messages: MessageData[];
}

export function MessageList({ messages }: MessageListProps) {
  if (messages.length === 0) {
    return (
      <Box>
        <Text dimColor>输入消息开始对话...</Text>
      </Box>
    );
  }

  return (
    <Box flexDirection="column">
      {messages.map((msg, index) => (
        <Message
          key={index}
          role={msg.role}
          content={msg.content}
          timestamp={msg.timestamp}
        />
      ))}
    </Box>
  );
}
```

---

## 5. 构建输入框

### 5.1 Input 组件

```typescript
// src/cli/components/Input.tsx
import React, { useState } from 'react';
import { Box, Text } from 'ink';
import { TextInput } from 'ink.TextInput';

interface InputProps {
  onSubmit: (value: string) => void;
  disabled?: boolean;
}

export function Input({ onSubmit, disabled }: InputProps) {
  const [value, setValue] = useState('');

  const handleSubmit = () => {
    if (!value.trim() || disabled) return;
    onSubmit(value);
    setValue('');
  };

  return (
    <Box>
      <Text color="green">{'> '}</Text>
      <TextInput
        value={value}
        onChange={setValue}
        onSubmit={handleSubmit}
        placeholder={disabled ? '等待回复...' : '输入消息...'}
        isDisabled={disabled}
      />
    </Box>
  );
}
```

---

## 6. 完整 REPL 组件

### 6.1 REPL 主组件

```typescript
// src/cli/repl.tsx
import React, { useState, useEffect } from 'react';
import { render, Box, Text } from 'ink';
import { MessageList } from './components/MessageList.js';
import { Input } from './components/Input.js';
import { ChatService } from '../services/chat.js';

interface MessageData {
  role: 'user' | 'assistant';
  content: string;
  timestamp: Date;
}

interface REPLProps {
  apiKey: string;
}

export function REPL({ apiKey }: REPLProps) {
  const [messages, setMessages] = useState<MessageData[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const chatService = new ChatService(apiKey);

  const handleSubmit = async (content: string) => {
    // 添加用户消息
    setMessages((prev) => [
      ...prev,
      { role: 'user', content, timestamp: new Date() },
    ]);
    setIsLoading(true);

    try {
      const response = await chatService.sendMessage(content);
      setMessages((prev) => [
        ...prev,
        { role: 'assistant', content: response, timestamp: new Date() },
      ]);
    } catch (error) {
      setMessages((prev) => [
        ...prev,
        {
          role: 'assistant',
          content: `错误: ${(error as Error).message}`,
          timestamp: new Date(),
        },
      ]);
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <Box flexDirection="column" padding={1}>
      {/* 头部 */}
      <Box borderStyle="round" padding={1} marginBottom={1}>
        <Text bold color="blue">
          Mini-Claude REPL
        </Text>
      </Box>

      {/* 消息列表 */}
      <Box flexGrow={1} flexDirection="column">
        <MessageList messages={messages} />
      </Box>

      {/* 分隔线 */}
      <Box marginY={1}>
        <Text dimColor>{'─'.repeat(50)}</Text>
      </Box>

      {/* 输入框 */}
      <Input onSubmit={handleSubmit} disabled={isLoading} />

      {/* 状态 */}
      {isLoading && (
        <Text dimColor>Claude 正在思考...</Text>
      )}
    </Box>
  );
}
```

### 6.2 启动函数

```typescript
// src/cli/startRepl.ts
import React from 'react';
import { render } from 'ink';
import { REPL } from './repl.js';

export function startRepl(apiKey: string) {
  render(React.createElement(REPL, { apiKey }));
}
```

---

## 7. 集成到 CLI

### 7.1 修改主入口

```typescript
// src/index.ts
import { Command } from 'commander';
import chalk from 'chalk';
import { registry } from './tools/registry.js';
import { getApiKey, setApiKey } from './config.js';
import { startRepl } from './cli/startRepl.js';

const program = new Command();

program
  .name('mini-claude')
  .description('一个简化版的 Claude Code CLI 工具（Ink 界面）')
  .version('1.0.0');

// 设置 API Key
program
  .command('config')
  .description('配置 API Key')
  .action(async () => {
    const { apiKey } = await inquirer.prompt([
      {
        type: 'password',
        name: 'apiKey',
        message: '输入 Anthropic API Key:',
        mask: '*',
      },
    ]);
    await setApiKey(apiKey);
    console.log(chalk.green('✓ API Key 已保存'));
  });

// 交互模式
program
  .command('chat')
  .description('开始对话')
  .action(async () => {
    const apiKey = await getApiKey();
    if (!apiKey) {
      console.error(chalk.red('✗ 请先配置 API Key: mini-claude config'));
      process.exit(1);
    }
    startRepl(apiKey);
  });

// 状态命令
program
  .command('status')
  .description('查看当前状态')
  .action(async () => {
    const apiKey = await getApiKey();
    console.log(chalk.blue('📊 Mini-Claude 状态'));
    console.log(chalk.gray('─'.repeat(40)));
    console.log(`版本: ${chalk.green('1.0.0')}`);
    console.log(`API Key: ${apiKey ? chalk.green('已配置') : chalk.red('未配置')}`);
    console.log(`工具数量: ${chalk.yellow(registry.list().length)}`);
  });

// 无参数时进入交互模式
if (process.argv.length === 2) {
  const apiKey = await getApiKey();
  if (!apiKey) {
    console.error(chalk.red('✗ 请先配置 API Key: mini-claude config'));
    process.exit(1);
  }
  startRepl(apiKey);
} else {
  program.parse();
}
```

---

## 8. 测试

### 8.1 编译

```bash
npm run build
```

### 8.2 运行

```bash
mini-claude chat
```

你会看到一个彩色的界面：
```
┌──────────────────────────────────────────┐
│ Mini-Claude REPL                         │
└──────────────────────────────────────────┘

输入消息开始对话...

──────────────────────────────────────────────────
> _
```

---

## 9. 与 Claude Code 对比

| 方面 | Mini-Claude | Claude Code |
|------|-------------|------------|
| UI 框架 | Ink | Ink（相同） |
| 布局 | 简单垂直布局 | 复杂多栏布局 |
| 消息渲染 | 基础 Text | 自定义组件 |
| 键盘处理 | TextInput | 自定义光标管理 |
| 快捷键 | 无 | Ctrl+C, Ctrl+L 等 |
| 工具执行 | 普通输出 | 原地更新状态 |
| 打字效果 | 无 | 逐字显示 |

**Claude Code 的额外功能**：
- 完整的键盘快捷键支持
- 工具执行状态的实时更新
- 多栏布局（消息、工具、状态）
- 终端大小自适应
- 复制粘贴支持

---

## 8. 练习

### 练习 1：添加 loading 动画

**目标**：为长时间操作添加 loading 动画

**提示**：
- 使用 `<Text>` 的闪烁效果
- 使用 `useState` 控制动画状态

**答案要点**：
```jsx
function LoadingSpinner({ text = '加载中' }) {
  const [frame, setFrame] = useState(0);
  const frames = ['⠋', '⠙', '⠹', '⠸', '⠼', '⠴', '⠦', '⠧'];

  useEffect(() => {
    const interval = setInterval(() => {
      setFrame(f => (f + 1) % frames.length);
    }, 80);
    return () => clearInterval(interval);
  }, []);

  return <Text>{frames[frame]} {text}</Text>;
}
```

### 练习 2：实现进度条

**目标**：用 Ink 组件显示文件复制进度

**提示**：
- 使用 `<Box>` 的 `width` 和 `height` 属性
- 根据百分比计算填充宽度

**答案要点**：
```jsx
function ProgressBar({ percent }: { percent: number }) {
  const width = 30;
  const filled = Math.floor((percent / 100) * width);
  const empty = width - filled;

  return (
    <Box>
      <Text> [{'|'.repeat(filled)}{' '.repeat(empty)}] </Text>
      <Text>{percent}%</Text>
    </Box>
  );
}
```

### 练习 3：实现分页显示

**目标**：为长列表添加分页功能

**提示**：
- 使用 `useState` 保存当前页码
- 每页显示固定数量的项目
- 添加上一页/下一页按钮

**答案要点**：
```jsx
function PaginatedList({ items, pageSize = 10 }) {
  const [page, setPage] = useState(0);
  const start = page * pageSize;
  const visibleItems = items.slice(start, start + pageSize);
  const totalPages = Math.ceil(items.length / pageSize);

  return (
    <Box>
      {visibleItems.map(item => (
        <Text key={item.id}>{item.name}</Text>
      ))}
      <Box flexDirection="row">
        <Text>第 {page + 1}/{totalPages} 页</Text>
        <Text onPress={() => setPage(p => Math.max(0, p - 1))}> ◀ </Text>
        <Text onPress={() => setPage(p => Math.min(totalPages - 1, p + 1))}> ▶ </Text>
      </Box>
    </Box>
  );
}
```

---

## 总结

| 概念 | 理解了吗？ |
|------|----------|
| Ink 基础组件 | ✓ |
| Box 布局 | ✓ |
| Text 样式 | ✓ |
| State 管理 | ✓ |
| REPL 组件设计 | ✓ |

---

## 阶段总结

恭喜你完成了入门篇！你现在拥有一个功能完备的"迷你 Claude Code"：

```
mini-claude chat                    # 对话
mini-claude tools                   # 查看工具
mini-claude tool read --param file_path=./package.json  # 使用工具
mini-claude config                  # 配置
```

---

## 下一篇

👉 [05 - 全局架构总览](./teaching/05-architecture.md) —— 理解 Claude Code 完整架构

`★ Insight ─────────────────────────────────────`
Ink 把终端变成了一个"声明式画布"。你描述 UI 应该是什么样子（垂直排列、彩色文本），Ink 负责处理光标定位、清屏、重绘等底层细节。这和 React 的思想一模一样——你只关心"是什么"，不关心"怎么做"。
`─────────────────────────────────────────────────`
