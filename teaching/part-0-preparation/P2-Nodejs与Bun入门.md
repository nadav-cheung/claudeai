# P2 - Node.js 与 Bun 入门：JavaScript 运行时

> **本章目标**：学完本章后，你将掌握 Node.js 和 Bun 的基本用法，能够运行 JavaScript/TypeScript 代码，理解包管理器的使用。

---

## 1. Node.js 与 Bun 简介

### 1.1 什么是运行时？

**JavaScript 最初是为浏览器设计的脚本语言**：
- Chrome/Firefox/Safari 都有内置的 JavaScript 引擎
- 但它只能在浏览器中运行

**Node.js 让 JavaScript 跑在服务器端**：
- 基于 Chrome V8 引擎
- 可以读写文件、执行命令、网络通信
- 让 JavaScript 成为真正的"全栈"语言

**Bun 是新一代 JavaScript 运行时**：
- 比 Node.js 更快（启动快、执行快）
- 内置 TypeScript 支持（直接运行 .ts 文件）
- 兼容 Node.js 生态
- Claude Code 使用 Bun 作为运行时

### 1.2 安装

**安装 Node.js**（推荐使用 nvm 管理版本）：
```bash
# 使用 nvm 安装
curl -o- https://raw.githubusercontent.com/nvm-sh/nvm/v0.39.0/install.sh | bash
nvm install 20
nvm use 20

# 验证
node --version  # v20.x.x
npm --version   # 10.x.x
```

**安装 Bun**：
```bash
# macOS/Linux
curl -fsSL https://bun.sh/install | bash

# Windows (PowerShell)
irm bun.sh/install.ps1 | iex

# 验证
bun --version  # 1.x.x
```

### 1.3 运行第一个程序

**用 Node.js 运行**：
```bash
# 创建文件
echo 'console.log("Hello from Node.js!")' > hello.js

# 运行
node hello.js
```

**用 Bun 运行**：
```bash
# 直接运行 TypeScript（不需要编译）
echo 'console.log("Hello from Bun!")' > hello.ts
bun hello.ts

# 或者直接运行 JavaScript
bun hello.js
```

---

## 2. npm 包管理器

### 2.1 npm 基础

npm（Node Package Manager）是 Node.js 内置的包管理器：

```bash
# 初始化项目（创建 package.json）
npm init -y

# 安装一个包
npm install lodash

# 安装到开发依赖（仅开发时使用）
npm install --save-dev typescript

# 全局安装（命令行工具）
npm install -g typescript

# 查看已安装的包
npm list

# 查看包信息
npm info lodash
```

### 2.2 package.json 结构

```json
{
  "name": "my-project",
  "version": "1.0.0",
  "description": "我的项目",
  "main": "dist/index.js",
  "scripts": {
    "build": "tsc",
    "start": "node dist/index.js",
    "dev": "ts-node src/index.ts"
  },
  "dependencies": {
    "lodash": "^4.17.21"
  },
  "devDependencies": {
    "typescript": "^5.0.0"
  }
}
```

### 2.3 运行脚本

npm 允许在 package.json 中定义快捷命令：

```bash
# 运行定义的脚本
npm run build
npm run dev

# 特殊脚本（不需要 run）
npm start
npm test
```

### 2.4 语义化版本（SemVer）

npm 使用语义化版本号：`major.minor.patch`

```
4.17.21
 │   │   │
 │   │   └── patch 版本（bug 修复）
 │   └────── minor 版本（新功能，向后兼容）
 └────────── major 版本（破坏性变更）
```

版本范围：
```json
{
  "dependencies": {
    "lodash": "^4.17.21",    // ^ 允许 minor 和 patch 更新
    "express": "~4.17.0",     // ~ 只允许 patch 更新
    "typescript": "5.0.0"      // 精确版本
  }
}
```

---

## 3. 文件系统操作

### 3.1 读取文件

**Node.js（使用 fs 模块）**：
```typescript
import * as fs from 'fs/promises';

// 异步读取
async function readFile(path: string): Promise<string> {
  const content = await fs.readFile(path, 'utf-8');
  return content;
}

const content = await readFile('./config.json');
console.log(content);
```

**Bun（更简单）**：
```typescript
// Bun 原生支持 top-level await
const content = await Bun.file('./config.json').text();
console.log(content);

// 读取 JSON
const config = await Bun.file('./config.json').json();
```

### 3.2 写入文件

```typescript
import * as fs from 'fs/promises';

// 写入文本
await fs.writeFile('./output.txt', 'Hello, World!', 'utf-8');

// 追加内容
await fs.appendFile('./output.txt', '\nNew line', 'utf-8');

// Bun 方式
await Bun.write('./output.txt', 'Hello, World!');
```

### 3.3 检查文件/目录

```typescript
import * as fs from 'fs/promises';

async function checkPath(path: string) {
  try {
    const stats = await fs.stat(path);
    if (stats.isDirectory()) {
      console.log(`${path} 是一个目录`);
    } else if (stats.isFile()) {
      console.log(`${path} 是一个文件，大小: ${stats.size} bytes`);
    }
  } catch (error) {
    console.log(`${path} 不存在`);
  }
}

await checkPath('./src');
await checkPath('./package.json');
await checkPath('./nonexistent');
```

### 3.4 目录操作

```typescript
import * as fs from 'fs/promises';

// 创建目录
await fs.mkdir('./新目录', { recursive: true });

// 读取目录内容
const files = await fs.readdir('./src');
console.log(files);  // ['index.ts', 'utils.ts', ...]

// 删除目录
await fs.rmdir('./空目录');

// 删除文件
await fs.unlink('./不需要的文件.txt');
```

---

## 4. 网络请求（fetch）

### 4.1 基础 GET 请求

**Node.js 18+ / Bun（原生支持 fetch）**：
```typescript
// GET 请求
const response = await fetch('https://api.example.com/users');
const users = await response.json();
console.log(users);

// 检查响应状态
if (!response.ok) {
  throw new Error(`HTTP error! status: ${response.status}`);
}
```

### 4.2 POST 请求

```typescript
// POST 请求
const response = await fetch('https://api.example.com/users', {
  method: 'POST',
  headers: {
    'Content-Type': 'application/json',
  },
  body: JSON.stringify({
    name: 'Alice',
    email: 'alice@example.com'
  })
});

const newUser = await response.json();
console.log(newUser);
```

### 4.3 处理超时

```typescript
// 使用 AbortController 实现超时
const controller = new AbortController();
const timeoutId = setTimeout(() => controller.abort(), 5000);

try {
  const response = await fetch('https://slow-api.example.com/data', {
    signal: controller.signal
  });
  const data = await response.json();
  console.log(data);
} catch (error) {
  if (error.name === 'AbortError') {
    console.log('请求超时');
  } else {
    console.error('请求失败:', error);
  }
} finally {
  clearTimeout(timeoutId);
}
```

---

## 5. 命令行参数与环境变量

### 5.1 读取命令行参数

**Node.js**：
```typescript
// process.argv 包含 [node, script.js, arg1, arg2, ...]
const args = process.argv.slice(2);

console.log('参数:', args);

// 解析命名参数
function parseArgs(argv: string[]) {
  const result: Record<string, string | boolean> = {};
  for (let i = 0; i < argv.length; i++) {
    const arg = argv[i];
    if (arg.startsWith('--')) {
      const key = arg.slice(2);
      const next = argv[i + 1];
      if (next && !next.startsWith('--')) {
        result[key] = next;
        i++;
      } else {
        result[key] = true;
      }
    }
  }
  return result;
}

const parsed = parseArgs(['--name', 'Alice', '--verbose']);
// { name: 'Alice', verbose: true }
```

**使用 yargs 库（更方便）**：
```typescript
import yargs from 'yargs';
import { hideBin } from 'yargs/helpers';

const argv = yargs(hideBin(process.argv))
  .option('name', {
    alias: 'n',
    type: 'string',
    description: '你的名字',
    demandOption: true
  })
  .option('verbose', {
    alias: 'v',
    type: 'boolean',
    description: '显示详细信息',
    default: false
  })
  .argv;

console.log(`Hello, ${argv.name}!`);
if (argv.verbose) {
  console.log('Verbose mode enabled');
}
```

### 5.2 读取环境变量

```typescript
// 读取环境变量
const port = process.env.PORT || 3000;
const apiKey = process.env.API_KEY;

if (!apiKey) {
  console.error('请设置 API_KEY 环境变量');
  process.exit(1);
}

// 使用 dotenv 加载 .env 文件
import 'dotenv/config';
```

**.env 文件示例**：
```
PORT=3000
API_KEY=your-secret-key-here
NODE_ENV=development
```

---

## 6. 进程管理

### 6.1 进程信息

```typescript
// 进程信息
console.log('进程 ID:', process.pid);
console.log('当前目录:', process.cwd());
console.log('平台:', process.platform);
console.log('Node 版本:', process.version);
console.log('环境变量:', process.env);
```

### 6.2 退出进程

```typescript
// 正常退出
process.exit(0);

// 异常退出
process.exit(1);

// 监听退出信号
process.on('SIGINT', () => {
  console.log('收到 Ctrl+C');
  process.exit(0);
});

process.on('SIGTERM', () => {
  console.log('收到终止信号');
  process.exit(0);
});
```

---

## 7. 使用第三方包

### 7.1 搜索和安装

```bash
# 搜索包
npm search cli argument parser

# 查看包信息
npm info commander

# 安装
npm install commander

# 同时安装并记录到 package.json
npm install commander @types/node
```

### 7.2 使用示例：commander.js

```typescript
import { Command } from 'commander';

const program = new Command();

program
  .name('my-cli')
  .description('我的 CLI 工具')
  .version('1.0.0');

program
  .command('greet <name>')
  .description('打招呼')
  .option('-u, --uppercase', '使用大写')
  .action((name, options) => {
    const greeting = `Hello, ${name}!`;
    console.log(options.uppercase ? greeting.toUpperCase() : greeting);
  });

program.parse();
```

使用：
```bash
my-cli greet Alice           # Hello, Alice!
my-cli greet Bob --uppercase # HELLO, BOB!
my-cli --version            # 1.0.0
```

---

## 8. Bun 特有功能

### 8.1 Bun.file() - 更简单的文件操作

```typescript
// 读取文件
const content = await Bun.file('./data.txt').text();
const json = await Bun.file('./config.json').json();
const buffer = await Bun.file('./image.png').arrayBuffer();

// 写入文件
await Bun.write('./output.txt', 'Hello!');

// 判断文件是否存在
const file = Bun.file('./exists.txt');
console.log(await file.exists());  // true 或 false
```

### 8.2 Bun.serve() - 内置 HTTP 服务器

```typescript
Bun.serve({
  port: 3000,
  fetch(request) {
    return new Response('Hello, World!');
  },
});

console.log('服务器运行在 http://localhost:3000');
```

### 8.3 自动加载 .env

Bun 自动加载 .env 文件，无需额外配置：
```typescript
// Bun 自动读取 .env 文件
console.log(process.env.DATABASE_URL);  // 直接使用
```

---

## 9. 实战练习

### 练习 1：创建一个文件备份工具

```typescript
// 实现一个工具，可以：
// 1. 读取源文件
// 2. 在文件名后添加 .bak 后缀
// 3. 写入备份文件
// 4. 支持批量备份目录

import * as fs from 'fs/promises';
import * as path from 'path';

async function backupFile(sourcePath: string): Promise<void> {
  // 你的实现
}

async function backupDirectory(dirPath: string): Promise<void> {
  // 你的实现：列出目录所有文件，逐个备份
}

// 测试
await backupFile('./package.json');
await backupDirectory('./src');
```

**答案要点**：
- 使用 `fs.readFile` 读取
- 生成目标路径：`path.join(dir, basename + '.bak')`
- 使用 `fs.mkdir` 确保目录存在
- 使用 `fs.readdir` 列出文件

### 练习 2：创建一个简单的 HTTP 客户端

```typescript
// 实现一个 fetch 封装，自动处理：
// 1. JSON 请求/响应
// 2. 错误处理
// 3. 超时

interface ApiResponse<T> {
  success: boolean;
  data?: T;
  error?: string;
}

async function apiRequest<T>(
  url: string,
  options?: RequestInit
): Promise<ApiResponse<T>> {
  // 你的实现
}

// 测试
const result = await apiRequest<User[]>('https://jsonplaceholder.typicode.com/users');
if (result.success) {
  console.log(result.data);
} else {
  console.error(result.error);
}
```

---

## 10. 常见问题

### Q1: Node.js 和 Bun 哪个更好？

**选择 Node.js 如果**：
- 需要稳定性和广泛的生态支持
- 需要运行在生产环境
- 依赖很多只支持 Node 的包

**选择 Bun 如果**：
- 想要更快的开发体验
- 使用 TypeScript 为主
- 项目不依赖复杂的 native 模块

### Q2: 如何管理多个 Node.js 版本？

使用 nvm（Node Version Manager）：
```bash
nvm install 20      # 安装 20.x
nvm install 18      # 安装 18.x
nvm use 20         # 使用 20.x
nvm alias default 20 # 设置默认版本
```

### Q3: package-lock.json 是什么？

package-lock.json 锁定实际安装的精确版本：
- 确保团队成员安装相同版本
- 加快 `npm install` 速度
- **应该提交到 Git**

---

## 总结

| 主题 | 关键点 |
|------|-------|
| npm | `npm init`, `npm install`, `npm run` |
| 文件操作 | `fs/promises` 模块，`Bun.file()` |
| 网络请求 | `fetch` API，`POST` 请求 |
| 命令行参数 | `process.argv`，`yargs` 库 |
| 环境变量 | `process.env`，`.env` 文件 |
| Bun 特色 | 内置 TypeScript 支持，自动加载 .env |

---

## 下一篇

👉 [P3 - 命令行开发基础](P3-CLI开发基础.md) —— 构建你的第一个 CLI 工具

`★ Insight ─────────────────────────────────────`
Node.js 和 Bun 都是 JavaScript 运行时，但定位略有不同。Node.js 像"老大哥"——稳定、成熟、生态丰富。Bun 像"年轻人"——快速、新潮、开发者体验好。Claude Code 选 Bun 是因为它对 TypeScript 的原生支持和更快的启动速度，这对 CLI 工具很重要。在你的项目中，两者都可以用，根据团队熟悉度和依赖来选择。
`─────────────────────────────────────────────────`
