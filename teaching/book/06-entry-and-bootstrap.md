# 06 - 入口与启动流程

> **本章目标**：深入理解 Claude Code 如何启动、如何解析命令行参数、如何初始化全局状态。

---

## 1. 准备工作

### 1.1 阅读源码

在继续之前，请先阅读 Claude Code 的启动相关源码：

**必读**：`src/main.tsx`（前 150 行）

**选读**：
- `src/bootstrap/state.ts` - 全局状态
- `src/entrypoints/init.ts` - 初始化逻辑

### 1.2 本章与 Mini-Claude 的关系

| Mini-Claude | Claude Code |
|-------------|-------------|
| `src/index.ts` (Commander 入口) | `src/main.tsx` |
| `src/config.ts` (API Key 存储) | `src/bootstrap/state.ts` |
| `interactiveMode()` | `src/replLauncher.tsx` |

---

## 2. Claude Code 的启动流程

```text
用户执行 mini-claude [args]
        │
        ▼
main.tsx 解析 CLI 参数
        │
        ├── --help / --version ──▶ 打印帮助/版本
        │
        ├── --print ──────────▶ 非交互打印模式
        │
        ├── --resume ─────────▶ 恢复历史会话
        │
        └── 无特殊参数 ────────▶ 启动 REPL
                                │
                                ▼
                         replLauncher.tsx
                                │
                                ▼
                         init.ts (初始化)
                                │
                                ├── 加载配置
                                ├── 初始化状态
                                ├── 注册工具
                                └── 启动 React 渲染
```

---

## 3. main.tsx 核心代码解析

### 3.1 参数解析

```typescript
// src/main.tsx (简化)
import { Command } from 'commander';

const program = new Command();

program
  .name('claude')
  .description('Anthropic Claude Code CLI')
  .version('2.1.88');

// 主要命令
program
  .option('-p, --print', 'Print mode (non-interactive)')
  .option('--resume [session-id]', 'Resume a session')
  .option('--model <model>', 'Select model')
  .option('--add-mcp-server <config>', 'Add MCP server')
  .option('--claude-code-dir <path>', 'Config directory');

// 解析参数
program.parse(process.argv);
```

### 3.2 与 Mini-Claude 对比

**Mini-Claude 的简单路由**：
```typescript
// Mini-Claude: 所有参数在一个 Command 里
program
  .command('chat [message]')
  .command('tool <name>')
  .command('status');

// 无参数时进入交互模式
if (process.argv.length === 2) {
  interactiveMode();
}
```

**Claude Code 的多模式入口**：
```typescript
// Claude Code: 使用选项而非子命令
if (options.print) {
  // 打印模式：读入 stdin，输出到 stdout
  runPrintMode();
} else if (options.resume) {
  // 恢复模式：加载历史会话
  runResumeMode(options.resume);
} else {
  // 交互模式：启动 REPL
  runReplMode();
}
```

---

## 4. 全局状态管理

### 4.1 Claude Code 的 Signal 模式

Claude Code 使用一种响应式状态管理模式：

```typescript
// src/bootstrap/state.ts (简化)
import { createSignal } from './lib/signals.js';

// 全局状态容器
export const state = {
  // 会话标识
  sessionId: createSignal<string>(generateSessionId()),

  // 模型选择
  mainLoopModel: createSignal<string>('claude-3-5-sonnet-20241022'),

  // 使用统计
  totalCostUSD: createSignal<number>(0),
  modelUsage: createSignal<Record<string, number>>({}),

  // 项目信息
  projectRoot: createSignal<string>(process.cwd()),
  originalCwd: createSignal<string>(process.cwd()),
};

// Signal 的用法
const sessionId = state.sessionId.get();    // 读取
state.sessionId.set(newValue);              // 写入

// 监听变化
state.sessionId.subscribe((id) => {
  console.log('Session changed:', id);
});
```

### 4.2 Mini-Claude 的简单配置

```typescript
// Mini-Claude: 简单的文件配置
import * as fs from 'fs/promises';
import * as path from 'path';

const CONFIG_FILE = path.join(os.homedir(), '.mini-claude', 'config.json');

interface Config {
  apiKey?: string;
}

async function loadConfig(): Promise<Config> {
  const content = await fs.readFile(CONFIG_FILE, 'utf-8');
  return JSON.parse(content);
}
```

### 4.3 对比总结

| 方面 | Mini-Claude | Claude Code |
|------|-------------|-------------|
| 状态管理 | JSON 文件 | Signal 响应式 |
| 持久化 | 每次读写文件 | 自动 + 按需 |
| 变化监听 | 无 | 订阅模式 |
| 类型安全 | 基础 | 完整类型 |
| 全局访问 | 模块导出 | Context |

---

## 5. 初始化流程

### 5.1 Claude Code 的懒初始化

```typescript
// src/entrypoints/init.ts (简化)
import { state } from '../bootstrap/state.js';
import { loadConfig } from './config.js';

// 懒初始化单例
let initialized = false;
let initPromise: Promise<void> | null = null;

export async function ensureInitialized(): Promise<void> {
  if (initialized) return;

  // 防止重复初始化
  if (initPromise) return initPromise;

  initPromise = doInit();
  await initPromise;
  initialized = true;
}

async function doInit(): Promise<void> {
  // 1. 加载用户配置
  const config = await loadConfig();

  // 2. 设置 API Key
  if (config.apiKey) {
    state.apiKey.set(config.apiKey);
  }

  // 3. 初始化项目根目录
  state.projectRoot.set(findProjectRoot(process.cwd()));

  // 4. 加载 Feature Flags
  await loadFeatureFlags();

  // 5. 注册 MCP 服务器
  await registerMcpServers(config.mcpServers);
}
```

### 5.2 Mini-Claude 的直接初始化

```typescript
// Mini-Claude: 在入口直接初始化
async function main() {
  const apiKey = await getApiKey();
  if (!apiKey) {
    console.error('请先配置 API Key');
    process.exit(1);
  }

  const chatService = new ChatService(apiKey);
  await interactiveMode(chatService);
}
```

---

## 6. 实战练习

### 6.1 练习：追踪启动流程

**目标**：理解 Claude Code 如何从命令行参数到启动 REPL

**步骤**：
1. 阅读 `src/main.tsx` 的前 100 行
2. 找出所有 CLI 选项
3. 追踪 `--print` 模式的代码路径
4. 追踪默认（无参数）模式的代码路径

**答案要点**：
- `--print` 模式调用 `runPrintMode()`
- 默认模式调用 `replLauncher.tsx` 中的函数
- 初始化通过 `entrypoints/init.ts` 的 `ensureInitialized()`

### 6.2 练习：添加新 CLI 选项

**目标**：为 Mini-Claude 添加 `--model` 选项

**答案**：
```typescript
// 添加选项
program
  .option('-m, --model <model>', '选择 AI 模型', 'claude-3-5-sonnet-20241022')
  .action((options) => {
    console.log(`使用模型: ${options.model}`);
  });
```

---

## 7. 与我们的小项目对比

### 7.1 入口点对比

| 方面 | Mini-Claude (Chapter 01) | Claude Code |
|------|-------------------------|-------------|
| 入口文件 | `src/index.ts` 单文件 | `src/main.tsx` + `entrypoints/init.ts` |
| 参数解析 | Commander 直接解析 | Commander → 路由 → 多模式 |
| 初始化时机 | main() 中直接初始化 | 懒初始化 `ensureInitialized()` |
| 状态管理 | 局部变量 | Signal 全局响应式状态 |
| 配置管理 | 无持久化 | JSON 配置文件 + 环境变量 |

### 7.2 架构模式对比

```
Mini-Claude 入口架构:
┌─────────────────┐
│  src/index.ts   │
│  (单文件入口)    │
├─────────────────┤
│ - 直接解析 args  │
│ - 直接初始化     │
│ - 直接调用服务   │
└─────────────────┘

Claude Code 入口架构:
┌─────────────────────────────────────┐
│          src/main.tsx               │
│   (Commander 解析 + 路由分发)        │
├─────────────────────────────────────┤
│         entrypoints/init.ts         │
│   (懒初始化 + Feature Flags)         │
├─────────────────────────────────────┤
│        bootstrap/state.ts            │
│   (Signal 响应式全局状态)             │
└─────────────────────────────────────┘
```

### 7.3 关键差异总结

| 差异点 | Mini-Claude | Claude Code | 为什么重要 |
|--------|-------------|-------------|------------|
| 初始化模式 | eager (立即) | lazy (惰性) | 大型项目初始化慢，懒加载提升启动速度 |
| 状态管理 | 模块变量 | Signal 响应式 | Signal 支持订阅和自动更新 |
| 配置存储 | 无 | JSON + 环境变量 | 持久化配置便于用户定制 |
| Feature Flags | 无 | 有 | 支持灰度发布和 A/B 测试 |

### 7.4 扩展练习

**问题**：如果你要在 Mini-Claude 中添加懒初始化模式，应该怎么改？

**提示**：
1. 把初始化逻辑从 `main()` 移到单独的 `ensureInitialized()` 函数
2. 使用一个 `initialized` 标志避免重复初始化
3. 使用 Promise 缓存防止并发初始化

**答案要点**：
```typescript
let initialized = false;
let initPromise: Promise<void> | null = null;

export async function ensureInitialized(): Promise<void> {
  if (initialized) return;
  if (initPromise) return initPromise;
  initPromise = doInit();
  await initPromise;
  initialized = true;
}
```

---

## 8. 总结

| 概念 | 理解 |
|------|------|
| CLI 参数解析 | ✓ |
| Signal 响应式状态 | ✓ |
| 懒初始化模式 | ✓ |
| 多模式入口 | ✓ |

---

## 下一篇

👉 [07 - 终端 UI 框架](./teaching/02-ink-terminal-ui.md) —— Ink 如何渲染消息

`★ Insight ─────────────────────────────────────`
Claude Code 的启动流程展示了几个重要模式：**1) 懒初始化**：只在需要时初始化，避免启动慢。**2) Signal 模式**：比 React Context 更轻量的响应式状态。**3) 多模式入口**：同一 CLI 可以是打印模式、恢复模式或交互模式，理解这点有助于设计灵活的 CLI 工具。
`─────────────────────────────────────────────────`
