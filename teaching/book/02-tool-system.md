# 02 - 实现工具调用系统

> **本章目标**：学完本章后，你将理解工具调用的设计思想，能够为 Mini-Claude 实现一个可扩展的工具注册与执行系统。

---

## 1. 什么是工具调用系统？

### 1.1 从一个问题开始

当用户说"帮我读取 package.json"时，Claude Code 需要：
1. 理解用户意图（读取文件）
2. 调用正确的工具（FileReadTool）
3. 获取结果并返回给用户

这就是**工具调用系统**的核心职责。

### 1.2 工具调用流程

```
用户消息 → AI 模型推理 → 需要工具？ → 执行工具 → 返回结果 → AI 继续推理 → 最终回复
```

**关键点**：工具调用是一个循环，不是一次性操作。AI 可能需要调用多个工具才能回答。

---

## 2. 设计工具接口

### 2.1 工具的本质

工具是一个**有名称、描述、参数和执行逻辑的函数**。

```typescript
// 工具接口
interface Tool {
  name: string;           // 工具名称
  description: string;     // 工具描述（AI 用它决定何时使用）
  parameters: Parameter[];  // 参数定义
  execute: (params: Record<string, unknown>) => Promise<ToolResult>;
}
```

### 2.2 定义工具接口

```typescript
// src/tools/tool.ts

export interface Parameter {
  name: string;
  description: string;
  type: 'string' | 'number' | 'boolean' | 'object';
  required: boolean;
}

export interface ToolResult {
  success: boolean;
  result?: string;
  error?: string;
}

export interface Tool {
  name: string;
  description: string;
  parameters: Parameter[];
  execute(params: Record<string, unknown>): Promise<ToolResult>;
}
```

### 2.3 Claude Code 的工具定义

Claude Code 的 `src/Tool.ts` 定义了完整的工具接口：

```typescript
// Claude Code 的工具接口（简化版）
export interface Tool {
  name: string;
  description: string;
  input_schema: {
    type: 'object';
    properties: Record<string, unknown>;
    required?: string[];
  };
  execute(args: unknown, context: ToolContext): Promise<ToolResult>;
}
```

---

## 3. 实现文件读取工具

### 3.1 创建工具目录

```bash
mkdir -p src/tools
```

### 3.2 文件读取工具

```typescript
// src/tools/FileReadTool.ts
import * as fs from 'fs/promises';
import * as path from 'path';
import { Tool, ToolResult, Parameter } from './tool.js';

export class FileReadTool implements Tool {
  name = 'read';
  description = '读取文件内容。适用于查看文本文件、代码、配置文件等。';

  parameters: Parameter[] = [
    {
      name: 'file_path',
      description: '要读取的文件路径',
      type: 'string',
      required: true,
    },
  ];

  async execute(params: Record<string, unknown>): Promise<ToolResult> {
    const filePath = params.file_path as string;

    if (!filePath) {
      return {
        success: false,
        error: '缺少必需参数: file_path',
      };
    }

    try {
      const resolvedPath = path.resolve(filePath);
      const content = await fs.readFile(resolvedPath, 'utf-8');
      return {
        success: true,
        result: content,
      };
    } catch (error) {
      return {
        success: false,
        error: `读取文件失败: ${(error as Error).message}`,
      };
    }
  }
}
```

### 3.3 文件写入工具

```typescript
// src/tools/FileWriteTool.ts
import * as fs from 'fs/promises';
import * as path from 'path';
import { Tool, ToolResult, Parameter } from './tool.js';

export class FileWriteTool implements Tool {
  name = 'write';
  description = '写入内容到文件。如果文件存在则覆盖，不存在则创建。';

  parameters: Parameter[] = [
    {
      name: 'file_path',
      description: '要写入的文件路径',
      type: 'string',
      required: true,
    },
    {
      name: 'content',
      description: '要写入的内容',
      type: 'string',
      required: true,
    },
  ];

  async execute(params: Record<string, unknown>): Promise<ToolResult> {
    const filePath = params.file_path as string;
    const content = params.content as string;

    if (!filePath || !content) {
      return {
        success: false,
        error: '缺少必需参数: file_path 或 content',
      };
    }

    try {
      const resolvedPath = path.resolve(filePath);
      const dir = path.dirname(resolvedPath);
      await fs.mkdir(dir, { recursive: true });
      await fs.writeFile(resolvedPath, content, 'utf-8');
      return {
        success: true,
        result: `文件已写入: ${resolvedPath}`,
      };
    } catch (error) {
      return {
        success: false,
        error: `写入文件失败: ${(error as Error).message}`,
      };
    }
  }
}
```

---

## 4. 实现 Shell 执行工具

### 4.1 Shell 执行工具

```typescript
// src/tools/ShellTool.ts
import { exec } from 'child_process';
import { promisify } from 'util';
import { Tool, ToolResult, Parameter } from './tool.js';

const execAsync = promisify(exec);

export class ShellTool implements Tool {
  name = 'shell';
  description = '执行 Shell 命令。适用于文件操作、git 命令、npm 脚本等。';

  parameters: Parameter[] = [
    {
      name: 'command',
      description: '要执行的 Shell 命令',
      type: 'string',
      required: true,
    },
    {
      name: 'timeout',
      description: '超时时间（毫秒）',
      type: 'number',
      required: false,
    },
  ];

  async execute(params: Record<string, unknown>): Promise<ToolResult> {
    const command = params.command as string;
    const timeout = (params.timeout as number) || 30000;

    if (!command) {
      return {
        success: false,
        error: '缺少必需参数: command',
      };
    }

    try {
      const { stdout, stderr } = await execAsync(command, {
        timeout,
        cwd: process.cwd(),
      });

      let output = '';
      if (stdout) {
        output += stdout;
      }
      if (stderr) {
        output += '\n[stderr]\n' + stderr;
      }

      return {
        success: true,
        result: output || '(命令执行完成，无输出)',
      };
    } catch (error) {
      const execError = error as { killed?: boolean; code?: number; message?: string };
      return {
        success: false,
        error: `命令执行失败: ${execError.message}${execError.killed ? ' (超时)' : ''}`,
      };
    }
  }
}
```

---

## 5. 工具注册表

### 5.1 为什么需要注册表？

当工具多了以后，需要一个地方统一管理：
- 列出所有可用工具
- 根据名称查找工具
- 动态添加/移除工具

### 5.2 实现工具注册表

```typescript
// src/tools/registry.ts
import { Tool } from './tool.js';
import { FileReadTool } from './FileReadTool.js';
import { FileWriteTool } from './FileWriteTool.js';
import { ShellTool } from './ShellTool.js';

class ToolRegistry {
  private tools: Map<string, Tool> = new Map();

  constructor() {
    this.register(new FileReadTool());
    this.register(new FileWriteTool());
    this.register(new ShellTool());
  }

  register(tool: Tool): void {
    this.tools.set(tool.name, tool);
    console.log(`✓ 注册工具: ${tool.name}`);
  }

  get(name: string): Tool | undefined {
    return this.tools.get(name);
  }

  list(): Tool[] {
    return Array.from(this.tools.values());
  }

  has(name: string): boolean {
    return this.tools.has(name);
  }
}

export const registry = new ToolRegistry();
```

### 5.3 查看所有工具

```typescript
// 列出所有工具
function listTools() {
  const tools = registry.list();
  console.log('\n📦 可用工具:');
  console.log('─'.repeat(50));
  tools.forEach((tool) => {
    console.log(`\n${tool.name}`);
    console.log(`  描述: ${tool.description}`);
    console.log(`  参数:`);
    tool.parameters.forEach((param) => {
      const required = param.required ? '✓' : '○';
      console.log(`    [${required}] ${param.name} (${param.type})`);
    });
  });
}
```

---

## 6. 整合到 CLI

### 6.1 修改主入口

```typescript
// src/index.ts
import { Command } from 'commander';
import chalk from 'chalk';
import { registry, listTools } from './tools/registry.js';
import { interactiveMode } from './interactive.js';

const program = new Command();

program
  .name('mini-claude')
  .description('一个简化版的 Claude Code CLI 工具（带工具系统）')
  .version('1.0.0');

// 工具列表命令
program
  .command('tools')
  .description('列出所有可用工具')
  .action(() => {
    listTools();
  });

// 执行工具命令
program
  .command('tool <name>')
  .description('执行指定工具')
  .option('-p, --param <key=value>', '工具参数，格式: key=value')
  .action(async (name, options) => {
    const tool = registry.get(name);
    if (!tool) {
      console.error(chalk.red(`✗ 未知工具: ${name}`));
      console.log(chalk.yellow('使用 "mini-claude tools" 查看所有可用工具'));
      return;
    }

    // 解析参数
    const params: Record<string, unknown> = {};
    if (options.param) {
      const paramStrings = Array.isArray(options.param)
        ? options.param
        : [options.param];
      for (const p of paramStrings) {
        const [key, value] = p.split('=');
        params[key] = value;
      }
    }

    console.log(chalk.blue(`⚡ 执行工具: ${name}`));
    console.log(chalk.gray(`参数: ${JSON.stringify(params)}`));
    console.log();

    const result = await tool.execute(params);
    if (result.success) {
      console.log(chalk.green('✓ 成功'));
      console.log(chalk.gray('─'.repeat(40)));
      console.log(result.result);
    } else {
      console.error(chalk.red(`✗ 失败: ${result.error}`));
    }
  });

// 状态命令
program
  .command('status')
  .description('查看当前状态')
  .action(() => {
    console.log(chalk.blue('📊 Mini-Claude 状态'));
    console.log(chalk.gray('─'.repeat(40)));
    console.log(`版本: ${chalk.green('1.0.0')}`);
    console.log(`工具数量: ${chalk.yellow(registry.list().length)}`);
    console.log(`工作目录: ${chalk.gray(process.cwd())}`);
  });

// 无参数时进入交互模式
if (process.argv.length === 2) {
  interactiveMode();
} else {
  program.parse();
}
```

### 6.2 增强交互模式

```typescript
// src/interactive.ts
import inquirer from 'inquirer';
import chalk from 'chalk';
import { registry } from './tools/registry.js';

export async function interactiveMode() {
  console.log(chalk.blue('╔══════════════════════════════════════╗'));
  console.log(chalk.blue('║   Mini-Claude CLI (with Tools!)       ║'));
  console.log(chalk.blue('╚══════════════════════════════════════╝'));
  console.log(chalk.gray('命令列表:'));
  console.log(chalk.gray('  tools - 查看所有工具'));
  console.log(chalk.gray('  exit  - 退出程序'));
  console.log(chalk.gray('  或直接输入消息与 AI 对话\n'));

  while (true) {
    const { input } = await inquirer.prompt([
      {
        type: 'input',
        name: 'input',
        message: chalk.green('> '),
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

    // 模拟 AI 决定使用工具
    console.log(chalk.gray('─'.repeat(40)));
    console.log(chalk.green('🤖 Mini-Claude: 收到消息'));
    console.log(chalk.gray(`(工具系统已就绪，可使用 ${registry.list().length} 个工具)`));
    console.log();
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

---

## 7. 测试工具系统

### 7.1 编译和测试

```bash
npm run build
```

### 7.2 测试命令

```bash
# 查看工具列表
mini-claude tools

# 执行 read 工具
mini-claude tool read --param file_path=./package.json

# 执行 shell 工具
mini-claude tool shell --param command="pwd"

# 进入交互模式
mini-claude
```

---

## 8. 与 Claude Code 对比

| 方面 | Mini-Claude | Claude Code |
|------|-------------|------------|
| 工具接口 | 简化版 Tool 接口 | 完整 Tool 接口（含 schema） |
| 工具数量 | 3 个 | 30+ 个 |
| 工具注册 | 硬编码 | 动态注册 + MCP 扩展 |
| 参数校验 | 手动 | JSON Schema 自动校验 |
| 错误处理 | 基础 try/catch | 细粒度错误分类 |
| 执行环境 | 直接 exec | 沙箱 + 权限控制 |

**Claude Code 的优势**：
- 完整的 JSON Schema 校验
- 工具执行的安全隔离
- MCP 协议支持动态扩展工具
- 详细的执行日志和错误追踪

---

## 9. 练习

### 练习 1：实现 `GrepTool`

**目标**：添加一个搜索文件内容的工具

**提示**：
- 使用 Node.js 的 `fs` 和 `path` 模块
- 读取文件内容后用正则表达式搜索
- 返回匹配的行号和内容

**答案要点**：
```typescript
export class GrepTool implements Tool {
  name = 'grep';
  description = '在文件中搜索匹配的文本';

  parameters = {
    type: 'object',
    properties: {
      pattern: { type: 'string', description: '搜索模式（正则表达式）' },
      file_path: { type: 'string', description: '文件路径' },
    },
    required: ['pattern', 'file_path'],
  };

  async execute(args: { pattern: string; file_path: string }) {
    const content = await fs.readFile(args.file_path, 'utf-8');
    const regex = new RegExp(args.pattern, 'g');
    const lines = content.split('\n');
    const matches = lines
      .map((line, i) => ({ line: i + 1, content: line }))
      .filter(({ content }) => regex.test(content));

    return {
      success: true,
      result: matches.map(m => `${m.line}: ${m.content}`).join('\n'),
    };
  }
}
```

### 练习 2：为工具添加调用计数

**目标**：统计每个工具被调用的次数

**提示**：
- 在 ToolRegistry 中添加计数器
- 工具每次执行时增加计数
- 添加 `mini-claude stats` 命令显示统计

**答案要点**：
```typescript
class ToolRegistry {
  private tools: Map<string, Tool> = new Map();
  private callCounts: Map<string, number> = new Map();

  execute(name: string, params: unknown): ToolResult {
    const count = this.callCounts.get(name) || 0;
    this.callCounts.set(name, count + 1);
    // ... 执行工具
  }

  getStats() {
    return Array.from(this.callCounts.entries())
      .sort((a, b) => b[1] - a[1]);
  }
}
```

### 练习 3：实现工具别名

**目标**：为工具添加别名支持（如 `r` 等于 `read`）

**提示**：
- 在注册工具时指定别名
- 在 get() 方法中支持别名查找

**答案要点**：
```typescript
class ToolRegistry {
  private tools: Map<string, Tool> = new Map();
  private aliases: Map<string, string> = new Map();

  register(tool: Tool, alias?: string): void {
    this.tools.set(tool.name, tool);
    if (alias) {
      this.aliases.set(alias, tool.name);
    }
  }

  get(name: string): Tool | undefined {
    const realName = this.aliases.get(name) || name;
    return this.tools.get(realName);
  }
}
```

---

## 总结

| 概念 | 理解了吗？ |
|------|----------|
| 工具接口设计 | ✓ |
| Tool.execute() 执行模型 | ✓ |
| 工具注册表模式 | ✓ |
| 参数传递与校验 | ✓ |
| CLI 集成 | ✓ |

---

## 下一篇

👉 [03 - 接入 AI API](03-ai-integration.md) —— 让 Mini-Claude 真正与 AI 对话

`★ Insight ─────────────────────────────────────`
工具系统的核心是**接口一致性**。不管工具是读取文件、执行命令还是搜索网页，都遵循相同的 `Tool` 接口。这让 AI 可以透明地调用任何工具——它只需要知道工具的名称、描述和参数，不需要关心实现细节。这就是**依赖倒置**的应用。
`─────────────────────────────────────────────────`
