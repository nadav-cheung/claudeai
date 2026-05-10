# P3 - 命令行开发基础：构建你的第一个 CLI 工具

> **本章目标**：学完本章后，你将掌握命令行开发的核心技能，能够使用 commander.js 构建功能完整的 CLI 工具。

---

## 1. 命令行工具概述

### 1.1 什么是 CLI 工具？

CLI（Command-Line Interface）工具是通过终端命令使用的程序：

```bash
# Git 是一个 CLI 工具
git init
git add .
git commit -m "Initial commit"

# npm 也是 CLI 工具
npm install
npm run build
npm test
```

### 1.2 CLI vs GUI

| 方面 | CLI | GUI |
|------|-----|-----|
| 交互方式 | 文本命令 | 图形界面 |
| 自动化 | 易于脚本化 | 难以自动化 |
| 学习曲线 | 较陡 | 较平缓 |
| 远程使用 | 天然支持 | 需要额外配置 |
| 适合场景 | 服务器、开发工具 | 普通用户 |

### 1.3 知名 CLI 工具

- **Git** - 版本控制
- **npm/yarn/pnpm** - 包管理
- **Docker** - 容器化
- **kubectl** - Kubernetes 控制
- **Claude Code** - AI 编程助手

---

## 2. commander.js 快速入门

### 2.1 什么是 commander.js？

commander.js 是 Node.js 最流行的 CLI 参数解析库：
- 自动生成帮助信息
- 支持子命令
- 类型验证
- 全局和本地安装支持

### 2.2 基本用法

```typescript
import { Command } from 'commander';

const program = new Command();

program
  .name('mytool')
  .description('我的第一个 CLI 工具')
  .version('1.0.0');

program.parse();
```

运行：
```bash
mytool --help
mytool --version
```

### 2.3 添加选项

```typescript
import { Command } from 'commander';

const program = new Command();

program
  .name('greeter')
  .description('打招呼工具');

program
  .option('-n, --name <name>', '名字', 'World')
  .option('-u, --uppercase', '使用大写')
  .action((options) => {
    let greeting = `Hello, ${options.name}!`;
    if (options.uppercase) {
      greeting = greeting.toUpperCase();
    }
    console.log(greeting);
  });

program.parse();
```

使用：
```bash
greeter                      # Hello, World!
greeter --name Alice        # Hello, Alice!
greeter -n Bob -u          # HELLO, BOB!
greeter --uppercase         # HELLO, WORLD!
```

### 2.4 选项类型

```typescript
program
  .option('-s, --string <value>', '字符串', 'default')           // 字符串
  .option('-n, --number <value>', '数字', '0')                    // 数字需要自己转换
  .option('-b, --boolean', '布尔值')                              // 无值时为 true
  .option('-l, --list <items>', '列表，用逗号分隔', val => val.split(','))
  .option('-c, --choices <choice>', '选择', ['a', 'b', 'c'])
```

---

## 3. 子命令

### 3.1 基本子命令

```typescript
const program = new Command();

program.name('todo');

// 添加子命令
program
  .command('add <task>')
  .description('添加新任务')
  .action((task) => {
    console.log(`添加任务: ${task}`);
  });

program
  .command('list')
  .description('列出所有任务')
  .action(() => {
    console.log('任务列表:');
    console.log('1. 买牛奶');
    console.log('2. 写代码');
  });

program
  .command('done <index>')
  .description('完成任务')
  .action((index) => {
    console.log(`完成任务 #${index}`);
  });

program.parse();
```

使用：
```bash
todo add 写代码        # 添加新任务
todo list              # 列出所有任务
todo done 1            # 完成任务
```

### 3.2 带选项的子命令

```typescript
program
  .command('add <task>')
  .description('添加新任务')
  .option('-p, --priority <level>', '优先级', 'normal')
  .option('-t, --tag <tag>', '标签')
  .action((task, options) => {
    console.log(`任务: ${task}`);
    console.log(`优先级: ${options.priority}`);
    console.log(`标签: ${options.tag || '无'}`);
  });
```

### 3.3 可链式调用的子命令

```typescript
// 使用 .addHelpText() 添加使用说明
program
  .command('config')
  .description('配置管理');

program
  .command('config set <key> <value>')
  .description('设置配置项')
  .action((key, value) => {
    console.log(`设置 ${key} = ${value}`);
  });

program
  .command('config get <key>')
  .description('获取配置项')
  .action((key) => {
    console.log(`${key} = some-value`);
  });
```

---

## 4. 交互式输入

### 4.1 使用 inquirer.js

inquirer.js 提供交互式提示：

```typescript
import inquirer from 'inquirer';

async function askQuestions() {
  const answers = await inquirer.prompt([
    {
      type: 'input',
      name: 'name',
      message: '你叫什么名字?',
      default: 'World'
    },
    {
      type: 'list',
      name: 'color',
      message: '你最喜欢什么颜色?',
      choices: ['红色', '绿色', '蓝色', '黄色']
    },
    {
      type: 'confirm',
      name: 'subscribe',
      message: '想要订阅我们的 newsletter 吗?',
      default: true
    },
    {
      type: 'password',
      name: 'password',
      message: '请输入密码'
    }
  ]);

  console.log('答案:', answers);
}
```

### 4.2 组合 commander 和 inquirer

```typescript
program
  .command('create')
  .description('创建新项目')
  .action(async () => {
    const answers = await inquirer.prompt([
      {
        type: 'input',
        name: 'projectName',
        message: '项目名称:',
        validate: (input) => input.length > 0 || '名称不能为空'
      },
      {
        type: 'list',
        name: 'template',
        message: '选择模板:',
        choices: ['javascript', 'typescript', 'react']
      }
    ]);

    console.log(`创建项目: ${answers.projectName}`);
    console.log(`使用模板: ${answers.template}`);
  });
```

---

## 5. 输出格式化

### 5.1 彩色输出

使用 chalk 库实现彩色输出：

```typescript
import chalk from 'chalk';

console.log(chalk.red('错误信息'));
console.log(chalk.green('成功信息'));
console.log(chalk.blue('信息'));
console.log(chalk.yellow('警告'));

console.log(chalk.bgRed.white('重要提示'));
console.log(chalk.bold('粗体'));
console.log(chalk.italic('斜体'));
console.log(chalk.underline('下划线'));

// 组合使用
console.log(chalk.green.bold('✓ ') + '安装成功');
console.log(chalk.red.bold('✗ ') + '安装失败');
console.log(chalk.yellow.bold('⚠ ') + '警告: 配置可能不正确');
```

### 5.2 进度条

使用 ora 库显示进度：

```typescript
import ora from 'ora';

const spinner = ora('正在下载文件...').start();

setTimeout(() => {
  spinner.text = '正在处理...';
}, 1000);

setTimeout(() => {
  spinner.succeed('完成!');
}, 2000);

// 失败状态
spinner.fail('下载失败');
```

### 5.3 表格输出

```typescript
import { table } from 'table';

const data = [
  ['Name', 'Age', 'City'],
  ['Alice', '25', 'Beijing'],
  ['Bob', '30', 'Shanghai'],
  ['Charlie', '35', 'Shenzhen']
];

console.log(table(data));
```

---

## 6. 文件操作实战

### 6.1 配置文件管理

```typescript
import * as fs from 'fs/promises';
import * as path from 'path';
import { fileURLToPath } from 'url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const configPath = path.join(__dirname, 'config.json');

interface Config {
  name: string;
  version: string;
  options: Record<string, unknown>;
}

async function loadConfig(): Promise<Config> {
  try {
    const content = await fs.readFile(configPath, 'utf-8');
    return JSON.parse(content);
  } catch {
    // 返回默认配置
    return {
      name: 'my-cli',
      version: '1.0.0',
      options: {}
    };
  }
}

async function saveConfig(config: Config): Promise<void> {
  await fs.writeFile(configPath, JSON.stringify(config, null, 2), 'utf-8');
}
```

### 6.2 命令历史记录

```typescript
import * as fs from 'fs/promises';
import * as path from 'path';

const historyPath = path.join(process.env.HOME || '', '.mycli-history');

async function addToHistory(command: string): Promise<void> {
  await fs.appendFile(historyPath, `${command}\n`, 'utf-8');
}

async function getHistory(): Promise<string[]> {
  try {
    const content = await fs.readFile(historyPath, 'utf-8');
    return content.split('\n').filter(line => line.length > 0);
  } catch {
    return [];
  }
}
```

---

## 7. 错误处理

### 7.1 自定义错误类

```typescript
class CLIError extends Error {
  constructor(
    message: string,
    public code: string,
    public suggestion?: string
  ) {
    super(message);
    this.name = 'CLIError';
  }
}

// 使用
function validateInput(input: unknown): void {
  if (!input) {
    throw new CLIError(
      '输入不能为空',
      'EMPTY_INPUT',
      '请提供有效的输入值'
    );
  }
}
```

### 7.2 优雅的错误处理

```typescript
import chalk from 'chalk';

function handleError(error: unknown): void {
  if (error instanceof CLIError) {
    console.error(chalk.red(`错误 [${error.code}]: ${error.message}`));
    if (error.suggestion) {
      console.error(chalk.yellow(`建议: ${error.suggestion}`));
    }
  } else if (error instanceof Error) {
    console.error(chalk.red(`错误: ${error.message}`));
  } else {
    console.error(chalk.red('未知错误'));
  }
  process.exit(1);
}

// 在程序入口使用
process.on('uncaughtException', handleError);
process.on('unhandledRejection', handleError);
```

---

## 8. 实战项目：构建一个 Todo CLI

### 8.1 项目初始化

```bash
# 创建项目
mkdir mytodo
cd mytodo
npm init -y

# 安装依赖
npm install commander chalk inquirer

# 创建 src 目录
mkdir src
```

### 8.2 完整代码

**src/index.ts**：
```typescript
#!/usr/bin/env node

import { Command } from 'commander';
import chalk from 'chalk';
import inquirer from 'inquirer';
import * as fs from 'fs/promises';
import * as path from 'path';
import { fileURLToPath } from 'url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const dataPath = path.join(__dirname, '..', 'data', 'todos.json');

interface Todo {
  id: number;
  task: string;
  completed: boolean;
  createdAt: string;
}

async function loadTodos(): Promise<Todo[]> {
  try {
    const content = await fs.readFile(dataPath, 'utf-8');
    return JSON.parse(content);
  } catch {
    return [];
  }
}

async function saveTodos(todos: Todo[]): Promise<void> {
  await fs.mkdir(path.dirname(dataPath), { recursive: true });
  await fs.writeFile(dataPath, JSON.stringify(todos, null, 2), 'utf-8');
}

const program = new Command();

program.name('mytodo').description('一个简单的 Todo CLI 工具').version('1.0.0');

// 添加任务
program
  .command('add')
  .description('添加新任务')
  .action(async () => {
    const { task } = await inquirer.prompt([
      {
        type: 'input',
        name: 'task',
        message: '任务内容:',
        validate: (input) => input.length > 0 || '任务不能为空'
      }
    ]);

    const todos = await loadTodos();
    const newTodo: Todo = {
      id: todos.length > 0 ? Math.max(...todos.map(t => t.id)) + 1 : 1,
      task,
      completed: false,
      createdAt: new Date().toISOString()
    };

    todos.push(newTodo);
    await saveTodos(todos);
    console.log(chalk.green(`✓ 已添加任务: ${task}`));
  });

// 列出任务
program
  .command('list')
  .description('列出所有任务')
  .action(async () => {
    const todos = await loadTodos();

    if (todos.length === 0) {
      console.log(chalk.yellow('暂无任务'));
      return;
    }

    console.log(chalk.bold('\n任务列表:\n'));
    todos.forEach((todo, index) => {
      const status = todo.completed ? chalk.green('✓') : chalk.gray('○');
      const task = todo.completed ? chalk.strikethrough(todo.task) : todo.task;
      console.log(`${status} ${index + 1}. ${task}`);
    });
    console.log();
  });

// 完成任务
program
  .command('done <id>')
  .description('完成任务')
  .action(async (id) => {
    const todos = await loadTodos();
    const todo = todos.find(t => t.id === parseInt(id));

    if (!todo) {
      console.log(chalk.red(`找不到任务 #${id}`));
      return;
    }

    todo.completed = true;
    await saveTodos(todos);
    console.log(chalk.green(`✓ 已完成任务: ${todo.task}`));
  });

// 删除任务
program
  .command('delete <id>')
  .description('删除任务')
  .action(async (id) => {
    const todos = await loadTodos();
    const index = todos.findIndex(t => t.id === parseInt(id));

    if (index === -1) {
      console.log(chalk.red(`找不到任务 #${id}`));
      return;
    }

    const [deleted] = todos.splice(index, 1);
    await saveTodos(todos);
    console.log(chalk.green(`✓ 已删除任务: ${deleted.task}`));
  });

program.parse();
```

### 8.3 添加可执行权限

```bash
# 在 package.json 中添加 bin 配置
# 然后链接到全局
npm link
```

### 8.4 使用

```bash
mytodo add           # 添加任务
mytodo list          # 列出任务
mytodo done 1        # 完成任务
mytodo delete 1      # 删除任务
```

---

## 9. 常见问题

### Q1: 如何让 CLI 工具支持 tab 自动补全？

使用 `tabtab` 包：
```typescript
// 添加到程序末尾
program
  .completeOption('name', {
    file: path.join(__dirname, '..', 'completions', 'mytodo.zsh')
  });
```

### Q2: 如何调试 CLI 工具？

```bash
# 使用 node --inspect
node --inspect-brk ./dist/index.js arg1 arg2

# 然后在 Chrome DevTools 中连接
```

### Q3: 如何发布 CLI 工具到 npm？

```bash
# 1. 确保 package.json 有正确的配置
{
  "name": "your-cli-name",
  "bin": {
    "your-cli": "./dist/index.js"
  }
}

# 2. 发布
npm publish
```

---

## 总结

| 技能 | 用途 |
|------|------|
| commander.js | CLI 参数解析和子命令 |
| inquirer.js | 交互式提示 |
| chalk | 彩色输出 |
| ora | 进度条 |
| 文件操作 | 持久化数据 |

---

## 下一篇

👉 [01 - 构建你的第一个CLI工具](01-build-first-cli.md) —— 开始实战项目

`★ Insight ─────────────────────────────────────`
CLI 工具的核心是**输入 → 处理 → 输出**。commander.js 负责解析输入，chalk 负责美化输出，inquirer.js 负责交互式输入。把这三块拼在一起，你就有了构建任何 CLI 工具的基础。记住，好的 CLI 工具不只是功能正确，还要有清晰的帮助信息、友好的错误提示、和漂亮的输出格式。
`─────────────────────────────────────────────────`
