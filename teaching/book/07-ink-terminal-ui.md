# 07 - 终端 UI 框架

> **本章目标**：深入理解 Claude Code 如何使用 Ink 构建交互式终端界面，包括消息渲染、用户输入处理和状态管理。

---

## 1. 准备工作

### 1.1 阅读源码

**必读**：
- `src/screens/REPL.tsx` - 主界面
- `src/components/App.tsx` - 根组件
- `src/state/AppStateStore.ts` - 状态管理

### 1.2 本章与 Mini-Claude 的关系

| Mini-Claude | Claude Code |
|-------------|-------------|
| `src/cli/repl.tsx` | `src/screens/REPL.tsx` |
| `src/cli/components/Message.tsx` | 消息渲染组件 |
| `src/cli/components/Input.tsx` | 输入处理 |

---

## 2. Claude Code 的 UI 架构

### 2.1 整体结构

```text
┌──────────────────────────────────────────────────────────────┐
│                     App (AppStateStore)                       │
│                    全局状态 Provider                          │
└──────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌──────────────────────────────────────────────────────────────┐
│                      REPL (主界面)                            │
│  ┌──────────────────────────────────────────────────────┐   │
│  │                    Header (头部)                      │   │
│  │  模型选择 | 会话信息 | 设置按钮                        │   │
│  └──────────────────────────────────────────────────────┘   │
│  ┌──────────────────────────────────────────────────────┐   │
│  │                    Messages (消息列表)                 │   │
│  │  ┌────────────────────────────────────────────────┐  │   │
│  │  │  UserMessage (用户消息)                         │  │   │
│  │  │  [可折叠] [复制按钮] [重新生成]                  │  │   │
│  │  └────────────────────────────────────────────────┘  │   │
│  │  ┌────────────────────────────────────────────────┐  │   │
│  │  │  AssistantMessage (AI 消息)                    │  │   │
│  │  │  [打字效果] [代码高亮] [工具调用展示]             │  │   │
│  │  └────────────────────────────────────────────────┘  │   │
│  └──────────────────────────────────────────────────────┘   │
│  ┌──────────────────────────────────────────────────────┐   │
│  │                    Input (输入框)                     │   │
│  │  [文本输入] [发送按钮] [停止按钮]                     │   │
│  └──────────────────────────────────────────────────────┘   │
│  ┌──────────────────────────────────────────────────────┐   │
│  │                    Status (状态栏)                     │   │
│  │  Token 计数 | 费用 | 连接状态                         │   │
│  └──────────────────────────────────────────────────────┘   │
└──────────────────────────────────────────────────────────────┘
```

### 2.2 Claude Code vs Mini-Claude

Claude Code 的 UI 比 Mini-Claude 复杂得多：

| 方面 | Mini-Claude | Claude Code |
|------|-------------|-------------|
| 布局 | 垂直单栏 | 多栏 + 头部 + 状态栏 |
| 消息渲染 | 简单 Text | 组件化 + 折叠 + 代码高亮 |
| 状态管理 | useState | AppStateStore (Context) |
| 输入处理 | TextInput | 自定义光标 + 快捷键 |
| 交互 | 基础 | 工具调用展示 + 停止按钮 |

---

## 3. 消息渲染组件

### 3.1 Claude Code 的消息结构

```typescript
// Claude Code 的消息类型
interface Message {
  id: string;
  role: 'user' | 'assistant';
  content: MessageContent[];
  createdAt: Date;
}

type MessageContent =
  | { type: 'text'; text: string }
  | { type: 'tool_use'; name: string; input: Record<string, unknown> }
  | { type: 'tool_result'; tool_use_id: string; content: string };
```

### 3.2 用户消息组件

```typescript
// Claude Code 的用户消息（简化版）
function UserMessage({ message }: { message: Message }) {
  return (
    <Box flexDirection="column" gap={1}>
      <Box>
        <Text color="cyan" bold>👤 你</Text>
        <Text dimColor> {formatTime(message.createdAt)}</Text>
      </Box>
      <Box paddingLeft={2}>
        {message.content.map((block, i) => (
          <Text key={i}>{block.text}</Text>
        ))}
      </Box>
    </Box>
  );
}
```

### 3.3 AI 消息组件（带工具调用）

```typescript
// Claude Code 的 AI 消息（简化版）
function AssistantMessage({ message }: { message: Message }) {
  return (
    <Box flexDirection="column" gap={1}>
      <Box>
        <Text color="green" bold>🤖 Claude</Text>
      </Box>

      {message.content.map((block, i) => {
        if (block.type === 'text') {
          return <Text key={i}>{block.text}</Text>;
        }

        if (block.type === 'tool_use') {
          return (
            <Box key={i} flexDirection="column" paddingLeft={2}>
              <Text dimColor>🔧 使用工具: {block.name}</Text>
              <Text dimColor>参数: {JSON.stringify(block.input)}</Text>
            </Box>
          );
        }

        return null;
      })}
    </Box>
  );
}
```

---

## 4. 状态管理

### 4.1 AppStateStore

Claude Code 使用 React Context + 自定义 Hook 进行状态管理：

```typescript
// src/state/AppStateStore.ts (简化)
import React, { createContext, useContext } from 'react';
import { signal, computed } from '../lib/signals.js';

interface AppState {
  // 消息
  messages: signal<Message[]>;
  appendMessage: (msg: Message) => void;

  // 输入
  inputValue: signal<string>;
  setInputValue: (v: string) => void;

  // 状态
  isLoading: signal<boolean>;
  isStreaming: signal<boolean>;

  // 计算值
  messageCount: computed<number>;
}

const AppStateContext = createContext<AppState | null>(null);

export function AppStateProvider({ children }: { children: React.ReactNode }) {
  const state: AppState = {
    messages: signal<Message[]>([]),
    inputValue: signal(''),
    isLoading: signal(false),
    isStreaming: signal(false),
    messageCount: computed(() => state.messages.get().length),
    appendMessage: (msg) => {
      state.messages.update(msgs => [...msgs, msg]);
    },
    setInputValue: (v) => state.inputValue.set(v),
  };

  return (
    <AppStateContext.Provider value={state}>
      {children}
    </AppStateContext.Provider>
  );
}

export function useAppState() {
  const ctx = useContext(AppStateContext);
  if (!ctx) throw new Error('useAppState must be used within AppStateProvider');
  return ctx;
}
```

### 4.2 Mini-Claude 的简单状态

```typescript
// Mini-Claude: 直接使用 useState
function REPL() {
  const [messages, setMessages] = useState<MessageData[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [input, setInput] = useState('');

  const handleSubmit = async (content: string) => {
    setMessages(prev => [...prev, { role: 'user', content }]);
    setIsLoading(true);
    // ...
  };

  return (
    // JSX...
  );
}
```

---

## 5. 实战练习

### 5.1 练习：添加消息折叠功能

**目标**：为 Mini-Claude 的消息添加折叠/展开功能

**提示**：
- 使用 Ink 的 `<Box>` 嵌套
- 维护一个 `expanded` state 记录每个消息的展开状态

**答案要点**：
```typescript
function Message({ role, content, timestamp }: MessageProps) {
  const [expanded, setExpanded] = useState(true);

  return (
    <Box flexDirection="column">
      <Text onPress={() => setExpanded(!expanded)}>
        {expanded ? '▼' : '▶'} {role === 'user' ? '👤' : '🤖'}
      </Text>
      {expanded && (
        <Box paddingLeft={2}>
          {content.split('\n').map((line, i) => (
            <Text key={i}>{line}</Text>
          ))}
        </Box>
      )}
    </Box>
  );
}
```

### 5.2 练习：添加停止按钮

**目标**：在 AI 生成回复时显示停止按钮

**答案要点**：
```typescript
function Input({ onSubmit, disabled }) {
  const [isGenerating, setIsGenerating] = useState(false);

  return (
    <Box>
      {isGenerating ? (
        <Text color="red" onPress={() => stopGeneration()}>[停止]</Text>
      ) : (
        <Text color="green">{'> '}</Text>
      )}
      <TextInput
        onChange={setInput}
        onSubmit={handleSubmit}
        isDisabled={disabled}
      />
    </Box>
  );
}
```

---

## 6. 与我们的小项目对比

### 6.1 UI 组件对比

| 方面 | Mini-Claude (Chapter 04) | Claude Code |
|------|-------------------------|-------------|
| 消息显示 | `<Text>` 简单渲染 | 完整 `Message.tsx` 组件树 |
| 布局方式 | 单栏或简单分栏 | 多栏布局（侧边栏 + 主消息区） |
| 输入框 | 基础 `<TextInput>` | 带历史记录、自动补全 |
| 状态管理 | 组件内 `useState` | Context + Signal 混合 |
| 滚动处理 | 无 | 虚拟滚动支持 |
| Markdown 渲染 | 无 | 完整 Markdown 解析 |

### 6.2 架构模式对比

```
Mini-Claude REPL 架构:
┌─────────────────────────────────────┐
│         render(<REPL />)            │
├─────────────────────────────────────┤
│ - useState 管理输入                  │
│ - 直接调用 chatService.send()        │
│ - 简单消息列表                       │
└─────────────────────────────────────┘

Claude Code REPL 架构:
┌─────────────────────────────────────┐
│      screens/REPL.tsx               │
├─────────────────────────────────────┤
│  ┌──────────┐    ┌──────────────┐ │
│  │ Sidebar  │    │ MessageList   │ │
│  │ (状态)   │    │ (虚拟滚动)    │ │
│  └──────────┘    └──────────────┘ │
│  ┌─────────────────────────────────┐│
│  │     <PromptInput />             ││
│  │  (自动补全 + 历史)               ││
│  └─────────────────────────────────┘│
├─────────────────────────────────────┤
│    AppStateStore (Signal)           │
│    Context (React)                  │
└─────────────────────────────────────┘
```

### 6.3 关键差异总结

| 差异点 | Mini-Claude | Claude Code | 为什么重要 |
|--------|-------------|-------------|------------|
| 消息渲染 | 简单文本 | 组件树 + Markdown | 支持代码高亮、链接等 |
| 状态架构 | 局部状态 | 全局 Store | 多组件共享状态 |
| 布局复杂度 | 单栏 | 多栏 + 侧边栏 | 功能分区更清晰 |
| 输入处理 | 直接发送 | 预处理 + 补全 | 用户体验更好 |
| 滚动性能 | 无优化 | 虚拟滚动 | 大会话不卡顿 |

### 6.4 扩展练习

**问题**：如何在 Mini-Claude 中添加消息时间戳？

**提示**：
1. 在消息对象中添加 `timestamp` 字段
2. 创建一个 `<Timestamp>` 组件格式化时间
3. 在消息渲染时传入时间戳

**答案要点**：
```tsx
// 消息类型扩展
interface Message {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  timestamp: Date;
}

// 时间戳组件
const Timestamp = ({ date }: { date: Date }) => (
  <Text dimColor>{formatTime(date)}</Text>
);

// 使用
<MessageItem message={msg}>
  <Timestamp date={msg.timestamp} />
</MessageItem>
```

---

## 7. 总结

| 概念 | 理解 |
|------|------|
| Ink 组件系统 | ✓ |
| 消息渲染架构 | ✓ |
| 状态管理 (Context + Signal) | ✓ |
| 多栏布局 | ✓ |

---

## 下一篇

👉 [08 - 工具系统](../03-tool-system.md) —— 深入理解 30+ 工具的注册与执行

`★ Insight ─────────────────────────────────────`
Ink 的核心是**声明式布局**——你描述 UI 的结构（垂直排列、哪些放左边、哪些放右边），Ink 负责处理终端的底层细节（光标定位、清屏、重绘）。当你习惯了这种思维方式，你会发现构建 CLI 界面和构建网页一样直观。
`─────────────────────────────────────────────────`
