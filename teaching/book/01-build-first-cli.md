# 01 - 构建你的第一个 CLI 工具

> **本章目标**：学完本章后，你将能够使用 commander.js 构建一个功能完整的 CLI 工具，支持参数解析、子命令、彩色输出和交互式输入。

---

## 1. 项目概述

### 1.1 我们要构建什么？

本章我们将构建一个 **mini-claude** —— 一个简化版的 Claude Code CLI 工具。它看起来是这样的：

```bash
# 查看帮助
mini-claude --help

# 聊天模式
mini-claude chat "你好，解释一下什么是 TypeScript"

# 读取文件
mini-claude read ./package.json

# 执行命令
mini-claude exec "ls -la"

# 查看状态
mini-claude status
```

### 1.2 技术栈

| 技术 | 用途 | 本章位置 |
|------|------|----------|
| Bun | 运行时 | 安装与运行 |
| TypeScript | 类型安全 | 全程使用 |
| commander.js | 参数解析 | 2-3 节 |
| chalk | 彩色输出 | 4 节 |
| inquirer.js | 交互式输入 | 5 节 |

---

## 2. 项目初始化

### 2.1 创建项目

```bash
# 创建项目目录
mkdir mini-claude
cd mini-claude

# 初始化 npm 项目
npm init -y

# 安装 TypeScript（开发依赖）
npm install --save-dev typescript @types/node

# 安装运行时（Bun）
# macOS/Linux:
curl -fsSL https://bun.sh/install | bash

# 安装 CLI 相关依赖
npm install commander chalk inquirer
```

### 2.2 配置 TypeScript

创建 `tsconfig.json`：

```json
{
  "compilerOptions": {
    "target": "ES2022",
    "module": "ESNext",
    "moduleResolution": "bundler",
    "lib": ["ES2022"],
    "outDir": "./dist",
    "rootDir": "./src",
    "strict": true,
    "esModuleInterop": true,
    "skipLibCheck": true,
    "forceConsistentCasingInFileNames": true
  },
  "include": ["src/**/*"],
  "exclude": ["node_modules"]
}
```

### 2.3 项目结构

```text
mini-claude/
├── src/
│   └── index.ts          # 主入口
├── package.json
├── tsconfig.json
└── README.md
```

### 2.4 package.json 配置

修改 `package.json`，添加 bin 字段使 CLI 可执行：

```json
{
  "name": "mini-claude",
  "version": "1.0.0",
  "description": "一个简化版的 Claude Code CLI 工具",
  "type": "module",
  "main": "dist/index.js",
  "bin": {
    "mini-claude": "./dist/index.js"
  },
  "scripts": {
    "build": "tsc",
    "start": "node dist/index.js"
  },
  "dependencies": {
    "commander": "^12.0.0",
    "chalk": "^5.3.0",
    "inquirer": "^9.2.0"
  },
  "devDependencies": {
    "typescript": "^5.0.0",
    "@types/node": "^20.0.0"
  }
}
```

---

## 3. 基础框架

### 3.1 创建主入口文件

```typescript
// src/index.ts
import { Command } from 'commander';

const program = new Command();

program
  .name('mini-claude')
  .description('一个简化版的 Claude Code CLI 工具')
  .version('1.0.0');

program.parse();
```

### 3.2 添加子命令

```typescript
// src/index.ts
import { Command } from 'commander';
import chalk from 'chalk';

const program = new Command();

program
  .name('mini-claude')
  .description('一个简化版的 Claude Code CLI 工具')
  .version('1.0.0');

// 状态命令
program
  .command('status')
  .description('查看当前状态')
  .action(() => {
    console.log(chalk.blue('📊 Mini-Claude 状态'));
    console.log(chalk.gray('─'.repeat(40)));
    console.log(`版本: ${chalk.green('1.0.0')}`);
    console.log(`模式: ${chalk.yellow('交互模式')}`);
  });

program.parse();
```

### 3.3 编译和测试

```bash
# 编译 TypeScript
npm run build

# 测试
node dist/index.js --help
node dist/index.js status
```

输出：

```text
Usage: mini-claude [options] [command]

一个简化版的 Claude Code CLI 工具

Options:
  -V, --version  output the version number
  -h, --help     display help for command

Commands:
  status         查看当前状态
  help           display help for command
```

---

## 4. 完善子命令

### 4.1 读取文件命令

```typescript
import * as fs from 'fs/promises';
import * as path from 'path';

// 读取文件命令
const readCommand = program
  .command('read <file>')
  .description('读取文件内容')
  .argument('<file>', '要读取的文件路径')
  .action(async (file) => {
    try {
      const resolvedPath = path.resolve(file);
      const content = await fs.readFile(resolvedPath, 'utf-8');
      console.log(chalk.blue(`📄 ${resolvedPath}`));
      console.log(chalk.gray('─'.repeat(40)));
      console.log(content);
    } catch (error) {
      console.error(chalk.red(`✗ 读取失败: ${(error as Error).message}`));
    }
  });
```

### 4.2 执行命令

```typescript
import { exec } from 'child_process';
import { promisify } from 'util';

const execAsync = promisify(exec);

// 执行命令
const execCommand = program
  .command('exec <command>')
  .description('执行 Shell 命令')
  .argument('<command>', '要执行的命令')
  .action(async (command) => {
    try {
      console.log(chalk.blue(`⚡ 执行: ${command}`));
      const { stdout, stderr } = await execAsync(command);
      if (stdout) {
        console.log(chalk.green(stdout));
      }
      if (stderr) {
        console.log(chalk.yellow(stderr));
      }
    } catch (error) {
      console.error(chalk.red(`✗ 执行失败: ${(error as Error).message}`));
    }
  });
```

### 4.3 聊天命令（基础版）

```typescript
// 聊天命令
const chatCommand = program
  .command('chat <message>')
  .description('发送消息')
  .argument('<message>', '要发送的消息')
  .action((message) => {
    console.log(chalk.blue(`💬 你: ${message}`));
    console.log(chalk.gray('─'.repeat(40)));
    // 模拟 AI 回复
    console.log(chalk.green(`🤖 Mini-Claude: 这是一个模拟回复。你说的是: "${message}"`));
  });
```

---

## 5. 交互式模式

### 5.1 实现交互模式

在没有参数时进入交互式对话：

```typescript
// 交互式模式
async function interactiveMode() {
  const inquirer = await import('inquirer');

  console.log(chalk.blue('╔══════════════════════════════════════╗'));
  console.log(chalk.blue('║     Welcome to Mini-Claude CLI!       ║'));
  console.log(chalk.blue('╚══════════════════════════════════════╝'));
  console.log(chalk.gray('输入消息开始对话，输入 "exit" 退出\n'));

  while (true) {
    const { message } = await inquirer.default.prompt([
      {
        type: 'input',
        name: 'message',
        message: chalk.green('你: '),
      },
    ]);

    if (message.toLowerCase() === 'exit') {
      console.log(chalk.yellow('\n👋 再见！'));
      break;
    }

    console.log(chalk.gray('─'.repeat(40)));
    console.log(chalk.green(`🤖 Mini-Claude: 收到: "${message}"`));
    console.log();
  }
}

// 修改 program.parse() 逻辑
if (process.argv.length === 2) {
  // 无参数时进入交互模式
  interactiveMode();
} else {
  program.parse();
}
```

### 5.2 添加退出命令

在 status 命令中添加返回码：

```typescript
// 退出命令
program
  .command('exit')
  .description('退出程序')
  .action(() => {
    console.log(chalk.yellow('👋 再见！'));
    process.exit(0);
  });
```

---

## 6. 完整代码

### 6.1 最终版本 src/index.ts

```typescript
#!/usr/bin/env node

import { Command } from 'commander';
import chalk from 'chalk';
import * as fs from 'fs/promises';
import * as path from 'path';
import { exec } from 'child_process';
import { promisify } from 'util';

const execAsync = promisify(exec);

const program = new Command();

program
  .name('mini-claude')
  .description('一个简化版的 Claude Code CLI 工具')
  .version('1.0.0');

// 状态命令
program
  .command('status')
  .description('查看当前状态')
  .action(() => {
    console.log(chalk.blue('📊 Mini-Claude 状态'));
    console.log(chalk.gray('─'.repeat(40)));
    console.log(`版本: ${chalk.green('1.0.0')}`);
    console.log(`模式: ${chalk.yellow('交互模式')}`);
    console.log(`工作目录: ${chalk.gray(process.cwd())}`);
  });

// 读取文件命令
program
  .command('read <file>')
  .description('读取文件内容')
  .action(async (file) => {
    try {
      const resolvedPath = path.resolve(file);
      const content = await fs.readFile(resolvedPath, 'utf-8');
      console.log(chalk.blue(`📄 ${resolvedPath}`));
      console.log(chalk.gray('─'.repeat(40)));
      console.log(content);
    } catch (error) {
      console.error(chalk.red(`✗ 读取失败: ${(error as Error).message}`));
    }
  });

// 执行命令
program
  .command('exec <command>')
  .description('执行 Shell 命令')
  .action(async (command) => {
    try {
      console.log(chalk.blue(`⚡ 执行: ${command}`));
      const { stdout, stderr } = await execAsync(command);
      if (stdout) {
        console.log(chalk.green(stdout));
      }
      if (stderr) {
        console.log(chalk.yellow(stderr));
      }
    } catch (error) {
      console.error(chalk.red(`✗ 执行失败: ${(error as Error).message}`));
    }
  });

// 聊天命令
program
  .command('chat <message>')
  .description('发送消息')
  .action((message) => {
    console.log(chalk.blue(`💬 你: ${message}`));
    console.log(chalk.gray('─'.repeat(40)));
    console.log(chalk.green(`🤖 Mini-Claude: 这是一个模拟回复。你说的是: "${message}"`));
  });

// 交互式模式
async function interactiveMode() {
  const inquirer = await import('inquirer');

  console.log(chalk.blue('╔══════════════════════════════════════╗'));
  console.log(chalk.blue('║     Welcome to Mini-Claude CLI!       ║'));
  console.log(chalk.blue('╚══════════════════════════════════════╝'));
  console.log(chalk.gray('输入消息开始对话，输入 "exit" 退出\n'));

  while (true) {
    const { message } = await inquirer.default.prompt([
      {
        type: 'input',
        name: 'message',
        message: chalk.green('你: '),
      },
    ]);

    if (message.toLowerCase() === 'exit') {
      console.log(chalk.yellow('\n👋 再见！'));
      break;
    }

    console.log(chalk.gray('─'.repeat(40)));
    console.log(chalk.green(`🤖 Mini-Claude: 收到: "${message}"`));
    console.log();
  }
}

// 无参数时进入交互模式
if (process.argv.length === 2) {
  interactiveMode();
} else {
  program.parse();
}
```

---

## 7. 测试与调试

### 7.1 链接到全局

```bash
# 编译
npm run build

# 链接到全局（开发时）
npm link

# 测试
mini-claude --help
mini-claude status
mini-claude chat "你好"
mini-claude read ./package.json
mini-claude exec "pwd"
```

### 7.2 常见错误

**错误 1：权限不足**

```bash
# 如果执行时提示权限错误
chmod +x dist/index.js
```

**错误 2：找不到模块**

```bash
# 确保已安装依赖
npm install

# 如果还是找不到，清理缓存
rm -rf node_modules package-lock.json
npm install
```

---

## 8. 与 Claude Code 对比

| 功能 | Mini-Claude | Claude Code |
|------|-------------|------------|
| 参数解析 | commander.js | Commander.js (相同) |
| 彩色输出 | chalk | chalk (相同) |
| 交互输入 | inquirer.js | 自定义 readline |
| 子命令 | chat, read, exec, status | chat, tool, compact, etc. |
| AI 对话 | 模拟回复 | 真实 Claude API |
| 工具执行 | exec (直接 shell) | 沙箱环境 |

**Claude Code 的优势**：
- 真实的 AI API 集成
- 完整的工具调用系统
- 权限和安全控制
- 上下文管理
- 流式输出

---

## 9. 练习

### 练习 1：添加 `--version` 简化标志

**目标**：为 `mini-claude status` 命令添加 `-V` 简写

**步骤**：
1. 找到 status 命令的定义
2. 添加 `.option('-V')` 标志
3. 测试 `mini-claude status -V`

**答案**：
```typescript
program
  .command('status')
  .description('查看当前状态')
  .option('-V, --verbose', '详细输出')
  .action((options) => {
    console.log(chalk.blue('📊 Mini-Claude 状态'));
    console.log(chalk.gray('─'.repeat(40)));
    console.log(`版本: ${chalk.green('1.0.0')}`);
    console.log(`模式: ${chalk.yellow('交互模式')}`);
    if (options.verbose) {
      console.log(`工作目录: ${chalk.gray(process.cwd())}`);
      console.log(`Node 版本: ${chalk.gray(process.version)}`);
    }
  });
```

### 练习 2：实现 `mini-claude config` 命令

**目标**：添加一个查看/修改配置的子命令

**提示**：
- 使用 `console.log` 输出当前配置
- 配置可以存储在 `~/.mini-claude.json`

**答案要点**：
```typescript
// 配置命令
program
  .command('config')
  .description('查看/修改配置')
  .argument('[key]', '配置项名称')
  .argument('[value]', '配置项值')
  .action((key, value) => {
    if (!key) {
      // 显示所有配置
      console.log('当前配置:', config);
    } else if (!value) {
      // 显示指定配置
      console.log(`${key} = ${config[key]}`);
    } else {
      // 设置配置
      config[key] = value;
      console.log(`已设置 ${key} = ${value}`);
    }
  });
```

### 练习 3：添加彩色日志

**目标**：使用 chalk 样式化输出，区分不同级别的日志

**步骤**：
1. 添加 `info`, `warn`, `error` 辅助函数
2. 在不同场景使用不同颜色

**答案**：
```typescript
const log = {
  info: (msg: string) => console.log(chalk.blue('ℹ ' + msg)),
  warn: (msg: string) => console.log(chalk.yellow('⚠ ' + msg)),
  error: (msg: string) => console.log(chalk.red('✗ ' + msg)),
  success: (msg: string) => console.log(chalk.green('✓ ' + msg)),
};

// 使用
log.info('程序启动');
log.warn('这是一个警告');
log.error('发生错误');
log.success('操作成功');
```

---

## 总结

| 技能 | 学会了吗？ |
|------|----------|
| 项目初始化 | ✓ |
| TypeScript 配置 | ✓ |
| Commander.js 子命令 | ✓ |
| Chalk 彩色输出 | ✓ |
| Inquirer 交互输入 | ✓ |
| 文件读取 | ✓ |
| Shell 执行 | ✓ |

---

## 下一篇

👉 [02 - 实现工具调用系统](02-tool-system.md) —— 给 Mini-Claude 添加真正的工具

`★ Insight ─────────────────────────────────────`
CLI 工具的本质是**接收命令 → 执行操作 → 返回结果**。Commander.js 负责解析你输入的 `mini-claude read ./file.txt`，chalk 负责让输出更美观，inquirer.js 负责在交互模式下读取你的下一行输入。把这三块拼在一起，你就有了构建任何 CLI 工具的基础骨架。
`─────────────────────────────────────────────────`
