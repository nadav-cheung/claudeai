# 03 - 接入 AI API

> **本章目标**：学完本章后，你将理解 AI API 的调用方式，能够为 Mini-Claude 集成 Claude API，实现真正的 AI 对话。

---

## 1. Anthropic API 简介

### 1.1 什么是 API？

API（Application Programming Interface）是软件之间对话的接口。就像：
- 点餐：顾客 → 服务员 → 厨房 → 服务员 → 顾客
- API：你的程序 → API 服务器 → AI 模型 → API 服务器 → 你的程序

### 1.2 Claude API 的核心概念

```typescript
// API 调用基本结构
const response = await fetch('https://api.anthropic.com/v1/messages', {
  method: 'POST',
  headers: {
    'Content-Type': 'application/json',
    'x-api-key': 'your-api-key',
    'anthropic-version': '2023-06-01',
  },
  body: JSON.stringify({
    model: 'claude-3-5-sonnet-20241022',
    max_tokens: 1024,
    messages: [
      { role: 'user', content: 'Hello, Claude!' }
    ]
  })
});
```

### 1.3 API 的关键参数

| 参数 | 作用 |
|------|------|
| `model` | 选择 AI 模型 |
| `messages` | 对话历史 |
| `max_tokens` | 最大回复长度 |
| `system` | 系统提示词 |
| `tools` | 可用工具列表 |

---

## 2. 创建 API 服务层

### 2.1 项目结构

```bash
mkdir -p src/services
```

### 2.2 API 客户端

```typescript
// src/services/api.ts
const ANTHROPIC_API_URL = 'https://api.anthropic.com/v1/messages';

export interface Message {
  role: 'user' | 'assistant';
  content: string;
}

export interface ApiOptions {
  apiKey: string;
  model?: string;
  maxTokens?: number;
  messages: Message[];
  system?: string;
}

export async function callClaudeApi(options: ApiOptions) {
  const {
    apiKey,
    model = 'claude-3-5-sonnet-20241022',
    maxTokens = 1024,
    messages,
    system,
  } = options;

  const response = await fetch(ANTHROPIC_API_URL, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'x-api-key': apiKey,
      'anthropic-version': '2023-06-01',
    },
    body: JSON.stringify({
      model,
      max_tokens: maxTokens,
      messages,
      system,
    }),
  });

  if (!response.ok) {
    const error = await response.text();
    throw new Error(`API 调用失败: ${response.status} - ${error}`);
  }

  const data = await response.json();
  return data;
}
```

### 2.3 工具调用响应格式

当 AI 需要调用工具时，API 返回的类型：

```typescript
export interface ToolUse {
  type: 'tool_use';
  id: string;
  name: string;
  input: Record<string, unknown>;
}

export interface ApiResponse {
  type: 'message' | 'error';
  content: Array<{
    type: 'text' | 'tool_use' | 'tool_result';
    text?: string;
    id?: string;
    name?: string;
    input?: Record<string, unknown>;
    tool_use_id?: string;
    content?: string;
  }>;
  stop_reason: 'end_turn' | 'max_tokens' | 'stop_sequence';
}
```

---

## 3. 实现流式响应

### 3.1 什么是流式响应？

普通响应：等 AI **完全生成**后才返回
流式响应：**边生成边返回**，一个字一个字地显示

```typescript
// 流式响应处理
async function* streamClaudeApi(options: ApiOptions) {
  const response = await fetch(ANTHROPIC_API_URL, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'x-api-key': options.apiKey,
      'anthropic-version': '2023-06-01',
      'anthropic-dangerous-direct-browser-access': 'true', // 重要！
    },
    body: JSON.stringify({
      model: options.model,
      max_tokens: options.maxTokens,
      messages: options.messages,
      system: options.system,
      stream: true, // 启用流式
    }),
  });

  if (!response.ok) {
    throw new Error(`API 调用失败: ${response.status}`);
  }

  const reader = response.body?.getReader();
  if (!reader) {
    throw new Error('无法获取响应流');
  }

  const decoder = new TextDecoder();
  let buffer = '';

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;

    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split('\n');
    buffer = lines.pop() || '';

    for (const line of lines) {
      if (line.startsWith('data: ')) {
        const data = line.slice(6);
        if (data === '[DONE]') {
          return;
        }
        yield JSON.parse(data);
      }
    }
  }
}
```

### 3.2 解析流式事件

```typescript
// 流式事件类型
interface StreamEvent {
  type: 'message_start' | 'content_block_start' | 'content_block_delta' | 'message_delta';
  index?: number;
  content_block?: { type: string };
  delta?: { type: string; text?: string };
}

// 使用流式响应
async function chatWithStreaming(apiKey: string, message: string) {
  console.log(chalk.gray('\n🤖 Claude: '));

  let fullResponse = '';

  for await (const event of streamClaudeApi({
    apiKey,
    messages: [{ role: 'user', content: message }],
  })) {
    if (event.type === 'content_block_delta' && event.delta?.text) {
      const text = event.delta.text;
      process.stdout.write(text);
      fullResponse += text;
    }
  }

  console.log('\n');
  return fullResponse;
}
```

---

## 4. 集成到 CLI

### 4.1 创建 ChatService

```typescript
// src/services/chat.ts
import chalk from 'chalk';
import { callClaudeApi, Message } from './api.js';
import { registry, Tool } from '../tools/registry.js';

export interface ChatOptions {
  apiKey: string;
  messages: Message[];
  system?: string;
}

export class ChatService {
  private apiKey: string;
  private tools: Tool[];

  constructor(apiKey: string) {
    this.apiKey = apiKey;
    this.tools = registry.list();
  }

  // 将工具转换为 API 格式
  private formatTools() {
    return this.tools.map((tool) => ({
      name: tool.name,
      description: tool.description,
      input_schema: {
        type: 'object',
        properties: tool.parameters.reduce((acc, param) => {
          acc[param.name] = {
            type: param.type,
            description: param.description,
          };
          return acc;
        }, {} as Record<string, unknown>),
        required: tool.parameters.filter((p) => p.required).map((p) => p.name),
      },
    }));
  }

  // 发送消息并处理响应
  async sendMessage(content: string): Promise<string> {
    const messages: Message[] = [{ role: 'user', content }];

    while (true) {
      const response = await callClaudeApi({
        apiKey: this.apiKey,
        messages,
        system: '你是一个有用的 AI 助手。',
        maxTokens: 1024,
      });

      // 处理响应内容
      for (const block of response.content) {
        if (block.type === 'text') {
          console.log(chalk.green(`\n🤖 Claude: ${block.text}`));
          messages.push({ role: 'assistant', content: block.text });
          return block.text;
        }

        if (block.type === 'tool_use') {
          const toolName = block.name;
          const toolInput = block.input;
          const toolUseId = block.id;

          console.log(chalk.blue(`\n🔧 使用工具: ${toolName}`));
          console.log(chalk.gray(`参数: ${JSON.stringify(toolInput)}`));

          // 执行工具
          const tool = registry.get(toolName);
          if (!tool) {
            console.error(chalk.red(`✗ 未知工具: ${toolName}`));
            messages.push({
              role: 'assistant',
              content: '',
            });
            continue;
          }

          const result = await tool.execute(toolInput);

          // 将工具结果返回给 AI
          messages.push({
            role: 'assistant',
            content: '',
          });

          // 添加工具结果（简化版，实际需要用 tool_result 类型）
          const toolResultContent = result.success
            ? result.result || '执行成功'
            : result.error || '执行失败';

          messages.push({
            role: 'user',
            content: `[Tool ${toolName} result]: ${toolResultContent}`,
          });
        }
      }
    }
  }
}
```

### 4.2 修改交互模式

```typescript
// src/interactive.ts
import inquirer from 'inquirer';
import chalk from 'chalk';
import { registry } from './tools/registry.js';
import { ChatService } from './services/chat.js';

export async function interactiveMode(apiKey: string) {
  const chatService = new ChatService(apiKey);

  console.log(chalk.blue('╔══════════════════════════════════════╗'));
  console.log(chalk.blue('║   Mini-Claude CLI (AI Powered!)       ║'));
  console.log(chalk.blue('╚══════════════════════════════════════╝'));
  console.log(chalk.gray('命令列表:'));
  console.log(chalk.gray('  tools - 查看所有工具'));
  console.log(chalk.gray('  exit  - 退出程序'));
  console.log();

  let conversationHistory = '';

  while (true) {
    const { input } = await inquirer.prompt([
      {
        type: 'input',
        name: 'input',
        message: chalk.green('你: '),
      },
    ]);

    if (input.toLowerCase() === 'exit') {
      console.log(chalk.yellow('\n👋 再见！'));
      break;
    }

    if (input.toLowerCase() === 'tools') {
      listTools();
      continue;
    }

    try {
      console.log(chalk.gray('─'.repeat(40)));
      await chatService.sendMessage(input);
      console.log();
    } catch (error) {
      console.error(chalk.red(`\n✗ 错误: ${(error as Error).message}`));
      console.log();
    }
  }
}

function listTools() {
  const tools = registry.list();
  console.log(chalk.blue('\n📦 可用工具:'));
  console.log(chalk.gray('─'.repeat(50)));
  tools.forEach((tool) => {
    console.log(`  ${chalk.green(tool.name)} - ${tool.description}`);
  });
  console.log();
}
```

### 4.3 添加 API Key 配置

```typescript
// src/config.ts
import * as fs from 'fs/promises';
import * as path from 'path';
import * as os from 'os';

const CONFIG_DIR = path.join(os.homedir(), '.mini-claude');
const CONFIG_FILE = path.join(CONFIG_DIR, 'config.json');

export interface Config {
  apiKey?: string;
}

export async function loadConfig(): Promise<Config> {
  try {
    const content = await fs.readFile(CONFIG_FILE, 'utf-8');
    return JSON.parse(content);
  } catch {
    return {};
  }
}

export async function saveConfig(config: Config): Promise<void> {
  await fs.mkdir(CONFIG_DIR, { recursive: true });
  await fs.writeFile(CONFIG_FILE, JSON.stringify(config, null, 2), 'utf-8');
}

export async function getApiKey(): Promise<string | null> {
  const config = await loadConfig();
  return config.apiKey || null;
}

export async function setApiKey(apiKey: string): Promise<void> {
  const config = await loadConfig();
  config.apiKey = apiKey;
  await saveConfig(config);
}
```

### 4.4 修改主入口

```typescript
// src/index.ts
import { Command } from 'commander';
import chalk from 'chalk';
import { registry } from './tools/registry.js';
import { interactiveMode } from './interactive.js';
import { getApiKey, setApiKey } from './config.js';

const program = new Command();

program
  .name('mini-claude')
  .description('一个简化版的 Claude Code CLI 工具（AI 驱动）')
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

// 工具列表命令
program
  .command('tools')
  .description('列出所有可用工具')
  .action(() => {
    listTools();
  });

// 交互模式
program
  .command('chat [message]')
  .description('开始对话（无参数时进入交互模式）')
  .action(async (message) => {
    const apiKey = await getApiKey();
    if (!apiKey) {
      console.error(chalk.red('✗ 请先配置 API Key: mini-claude config'));
      return;
    }

    if (message) {
      // 单条消息模式
      const chatService = new ChatService(apiKey);
      await chatService.sendMessage(message);
    } else {
      // 交互模式
      await interactiveMode(apiKey);
    }
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
  await interactiveMode(apiKey);
} else {
  program.parse();
}
```

---

## 5. 完整使用流程

### 5.1 首次设置

```bash
# 1. 编译
npm run build

# 2. 配置 API Key
mini-claude config

# 3. 查看状态
mini-claude status
```

### 5.2 对话示例

```bash
# 单条消息
mini-claude chat "解释什么是 TypeScript"

# 交互模式
mini-claude chat
# 然后输入你的问题
```

---

## 6. 与 Claude Code 对比

| 方面 | Mini-Claude | Claude Code |
|------|-------------|------------|
| API 调用 | fetch 原始调用 | 封装好的 ApiService |
| 流式输出 | 基础实现 | 完整 SSE 处理 |
| 工具结果 | 手动拼接 | 专门的 tool_result 类型 |
| 上下文 | 简单 messages 数组 | 完整的上下文管理 |
| 重试机制 | 无 | 自动重试 + 指数退避 |
| 费用追踪 | 无 | 完整的使用统计 |

**Claude Code 的额外功能**：
- 完整的上下文窗口管理
- 自动上下文压缩
- 流式输出的实时渲染
- 工具执行的详细日志
- A/B 测试集成

---

## 7. 常见问题

### Q1: API Key 从哪获取？

访问 [Anthropic Console](https://console.anthropic.com/) 创建 API Key。

### Q2: 流式响应不工作？

确保请求头包含：
```typescript
'anthropic-dangerous-direct-browser-access': 'true'
```

### Q3: 超出 token 限制？

减小 `maxTokens` 值，或实现上下文压缩。

---

## 8. 练习

### 练习 1：添加模型选择

**目标**：让用户选择使用哪个 Claude 模型

**提示**：
- 在 config 中添加 `model` 选项
- API 调用时传递选择的模型
- 支持 `claude-3-5-sonnet-20241022` 等模型

**答案要点**：
```typescript
// 添加模型选项
const models = [
  'claude-3-5-sonnet-20241022',
  'claude-3-opus-4-20251114',
  'claude-3-haiku-4-20250307',
];

// 在 API 调用时使用
const response = await fetch('https://api.anthropic.com/v1/messages', {
  // ...
  body: JSON.stringify({
    model: config.model || 'claude-3-5-sonnet-20241022',
    messages,
    max_tokens: 1024,
  }),
});
```

### 练习 2：实现历史记录

**目标**：保存对话历史，支持 `mini-claude history` 命令

**提示**：
- 使用文件系统保存历史到 `~/.mini-claude/history.json`
- 每次对话后保存用户消息和 AI 回复
- `history` 命令显示最近 10 条对话

**答案要点**：
```typescript
async function saveToHistory(userMsg: string, aiMsg: string) {
  const historyPath = path.join(os.homedir(), '.mini-claude', 'history.json');
  const history = await fs.readFile(historyPath, 'utf-8').catch(() => '[]');
  const entries = JSON.parse(history);
  entries.push({ user: userMsg, ai: aiMsg, time: Date.now() });
  await fs.writeFile(historyPath, JSON.stringify(entries, null, 2));
}

async function showHistory() {
  const historyPath = path.join(os.homedir(), '.mini-claude', 'history.json');
  const history = await fs.readFile(historyPath, 'utf-8').catch(() => '[]');
  const entries = JSON.parse(history);
  entries.slice(-10).forEach((e, i) => {
    console.log(`\n[${i + 1}] 你: ${e.user}`);
    console.log(`AI: ${e.ai}`);
  });
}
```

### 练习 3：添加速率限制处理

**目标**：处理 API 速率限制错误

**提示**：
- 当收到 429 状态码时，等待后重试
- 显示友好的错误信息

**答案要点**：
```typescript
async function callWithRetry(url: string, options: RequestInit, maxRetries = 3) {
  for (let i = 0; i < maxRetries; i++) {
    const response = await fetch(url, options);

    if (response.status === 429) {
      const retryAfter = response.headers.get('retry-after') || '5';
      console.log(chalk.yellow(`速率限制，等待 ${retryAfter} 秒...`));
      await new Promise(r => setTimeout(r, parseInt(retryAfter) * 1000));
      continue;
    }

    return response;
  }
  throw new Error('请求失败，已达到最大重试次数');
}
```

---

## 总结

| 概念 | 理解了吗？ |
|------|----------|
| API 调用结构 | ✓ |
| 流式响应处理 | ✓ |
| 工具结果处理 | ✓ |
| API Key 管理 | ✓ |
| ChatService 封装 | ✓ |

---

## 下一篇

👉 [04 - 添加交互界面](04-repl-interface.md) —— 用 Ink 构建彩色终端 UI

`★ Insight ─────────────────────────────────────`
AI API 调用的核心是**消息循环**：用户消息 → API 调用 → 检查响应类型（文本/工具调用）→ 如果是工具调用，执行工具并把结果加回消息 → 再次调用 API → 直到得到最终文本回复。这个循环看起来复杂，但每个步骤都很简单。
`─────────────────────────────────────────────────`
