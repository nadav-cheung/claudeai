# 20 - 构建你的第一个插件

> **本章目标**：通过实战项目，构建一个完整的 Claude Code 插件，掌握插件开发的完整流程。

---

## 1. 项目规划

### 1.1 我们要构建什么？

我们将构建一个 **Git 工具箱插件**，提供常用的 Git 操作：

```text
Git Toolkit Plugin
├── 提交工具 (Commit)
├── 分支工具 (Branch)
├── 状态工具 (Status)
└── 日志工具 (Log)
```

### 1.2 技术栈

- TypeScript
- Claude Code Plugin API
- simple-git (Git 操作库)

---

## 2. 项目初始化

### 2.1 创建项目

```bash
# 创建项目目录
mkdir claude-plugin-git-toolkit
cd claude-plugin-git-toolkit

# 初始化 npm
npm init -y

# 安装依赖
npm install simple-git
npm install --save-dev typescript @types/node
```

### 2.2 配置 TypeScript

```json
// tsconfig.json
{
  "compilerOptions": {
    "target": "ES2022",
    "module": "ESNext",
    "moduleResolution": "bundler",
    "lib": ["ES2022"],
    "outDir": "./dist",
    "rootDir": "./src",
    "strict": true,
    "esModuleInterop": true
  },
  "include": ["src/**/*"]
}
```

### 2.3 项目结构

```
claude-plugin-git-toolkit/
├── src/
│   ├── index.ts           # 插件入口
│   ├── tools/
│   │   ├── commit.ts
│   │   ├── branch.ts
│   │   ├── status.ts
│   │   └── log.ts
│   └── types.ts           # 类型定义
├── package.json
├── tsconfig.json
└── README.md
```

---

## 3. 实现工具

### 3.1 类型定义

```typescript
// src/types.ts
export interface GitToolResult {
  success: boolean;
  result?: string;
  error?: string;
}

export interface CommitOptions {
  message: string;
  all?: boolean;
}

export interface BranchOptions {
  name: string;
  create?: boolean;
  checkout?: boolean;
}
```

### 3.2 Commit 工具

```typescript
// src/tools/commit.ts
import simpleGit, { SimpleGit } from 'simple-git';
import { GitToolResult, CommitOptions } from '../types.js';

export class CommitTool {
  name = 'git_commit';
  description = '提交更改到 Git 仓库';

  input_schema = {
    type: 'object' as const,
    properties: {
      message: {
        type: 'string' as const,
        description: '提交消息',
      },
      all: {
        type: 'boolean' as const,
        description: '自动暂存所有更改',
        default: false,
      },
    },
    required: ['message'],
  };

  async execute(args: CommitOptions): Promise<GitToolResult> {
    const git: SimpleGit = simpleGit();

    try {
      if (args.all) {
        await git.add(['-A']);
      }

      const result = await git.commit(args.message);

      return {
        success: true,
        result: `提交成功: ${result.commit}\n${result.summary.changes} 个文件被更改`,
      };
    } catch (error) {
      return {
        success: false,
        error: `提交失败: ${(error as Error).message}`,
      };
    }
  }
}
```

### 3.3 Branch 工具

```typescript
// src/tools/branch.ts
import simpleGit, { SimpleGit } from 'simple-git';
import { GitToolResult, BranchOptions } from '../types.js';

export class BranchTool {
  name = 'git_branch';
  description = '管理 Git 分支';

  input_schema = {
    type: 'object' as const,
    properties: {
      name: {
        type: 'string' as const,
        description: '分支名称',
      },
      create: {
        type: 'boolean' as const,
        description: '创建新分支',
        default: false,
      },
      checkout: {
        type: 'boolean' as const,
        description: '切换到分支',
        default: false,
      },
    },
    required: ['name'],
  };

  async execute(args: BranchOptions): Promise<GitToolResult> {
    const git: SimpleGit = simpleGit();

    try {
      if (args.create && args.checkout) {
        await git.checkoutLocalBranch(args.name);
        return { success: true, result: `创建并切换到分支: ${args.name}` };
      }

      if (args.create) {
        await git.branch([args.name]);
        return { success: true, result: `创建分支: ${args.name}` };
      }

      if (args.checkout) {
        await git.checkout(args.name);
        return { success: true, result: `切换到分支: ${args.name}` };
      }

      // 列出分支
      const branches = await git.branchLocal();
      return {
        success: true,
        result: `当前分支: ${branches.current}\n所有分支:\n${branches.all.join('\n')}`,
      };
    } catch (error) {
      return {
        success: false,
        error: `分支操作失败: ${(error as Error).message}`,
      };
    }
  }
}
```

### 3.4 Status 工具

```typescript
// src/tools/status.ts
import simpleGit, { SimpleGit } from 'simple-git';
import { GitToolResult } from '../types.js';

export class StatusTool {
  name = 'git_status';
  description = '查看 Git 仓库状态';

  input_schema = {
    type: 'object' as const,
    properties: {},
  };

  async execute(): Promise<GitToolResult> {
    const git: SimpleGit = simpleGit();

    try {
      const status = await git.status();

      let result = `当前分支: ${status.current}\n`;
      result += `干净的工作区: ${status.isClean()}\n\n`;

      if (status.modified.length > 0) {
        result += `修改的文件 (${status.modified.length}):\n`;
        status.modified.forEach(f => result += `  M ${f}\n`);
      }

      if (status.staged.length > 0) {
        result += `\n暂存的更改 (${status.staged.length}):\n`;
        status.staged.forEach(f => result += `  A ${f}\n`);
      }

      if (status.created.length > 0) {
        result += `\n新文件 (${status.created.length}):\n`;
        status.created.forEach(f => result += `  ? ${f}\n`);
      }

      if (status.deleted.length > 0) {
        result += `\n删除的文件 (${status.deleted.length}):\n`;
        status.deleted.forEach(f => result += `  D ${f}\n`);
      }

      return { success: true, result };
    } catch (error) {
      return {
        success: false,
        error: `获取状态失败: ${(error as Error).message}`,
      };
    }
  }
}
```

---

## 4. 插件入口

### 4.1 插件定义

```typescript
// src/index.ts
import { CommitTool } from './tools/commit.js';
import { BranchTool } from './tools/branch.js';
import { StatusTool } from './tools/status.js';
import { LogTool } from './tools/log.js';

// 插件元数据
export const pluginMeta = {
  name: 'git-toolkit',
  version: '1.0.0',
  description: 'Git 工具箱插件，提供常用的 Git 操作',
};

// 导出工具
export const tools = [
  new CommitTool(),
  new BranchTool(),
  new StatusTool(),
  new LogTool(),
];

// 默认导出
export default {
  name: pluginMeta.name,
  version: pluginMeta.version,
  description: pluginMeta.description,
  tools,
};
```

### 4.2 完整的 Log 工具

```typescript
// src/tools/log.ts
import simpleGit, { SimpleGit } from 'simple-git';
import { GitToolResult } from '../types.js';

export class LogTool {
  name = 'git_log';
  description = '查看 Git 提交历史';

  input_schema = {
    type: 'object' as const,
    properties: {
      limit: {
        type: 'number' as const,
        description: '显示最近 N 条提交',
        default: 10,
      },
    },
  };

  async execute(args: { limit?: number } = {}): Promise<GitToolResult> {
    const git: SimpleGit = simpleGit();
    const limit = args.limit || 10;

    try {
      const log = await git.log({ maxCount: limit });

      if (log.all.length === 0) {
        return { success: true, result: '没有提交历史' };
      }

      let result = `最近 ${log.all.length} 条提交:\n\n`;

      log.all.forEach((commit, i) => {
        result += `${i + 1}. ${commit.hash.slice(0, 7)}\n`;
        result += `   ${commit.date}\n`;
        result += `   ${commit.message}\n`;
        result += `   ${commit.author_name}\n\n`;
      });

      return { success: true, result };
    } catch (error) {
      return {
        success: false,
        error: `获取日志失败: ${(error as Error).message}`,
      };
    }
  }
}
```

---

## 5. 测试

### 5.1 本地测试

```bash
# 1. 编译 TypeScript
npm run build

# 2. 在 Claude Code 中加载插件
# 在项目根目录运行 Claude Code

# 3. 测试工具
# /git_status
# /git_commit "Initial commit"
# /git_log
```

### 5.2 测试脚本

```typescript
// test.ts - 简单的测试脚本
import { CommitTool, BranchTool, StatusTool, LogTool } from './src/index.js';

async function test() {
  const tools = [
    new StatusTool(),
    new CommitTool(),
    new BranchTool(),
    new LogTool(),
  ];

  for (const tool of tools) {
    console.log(`\n测试工具: ${tool.name}`);
    console.log(`描述: ${tool.description}`);

    const result = await tool.execute({});
    console.log(`结果:`, result);
  }
}

test();
```

---

## 6. 发布

### 6.1 准备发布

```json
// package.json
{
  "name": "@your-name/claude-plugin-git-toolkit",
  "version": "1.0.0",
  "description": "Git 工具箱插件",
  "main": "dist/index.js",
  "type": "module",
  "keywords": ["claude-code", "plugin", "git"],
  "license": "MIT"
}
```

### 6.2 发布到 npm

```bash
# 1. 登录 npm
npm login

# 2. 发布
npm publish --access public
```

---

## 7. 练习

### 练习 1：添加 Git 配置工具

**目标**：为 Git Toolkit 插件添加 `git_config` 工具

**提示**：
- 读取/设置 Git 配置项
- 支持 `--global` 和 `--local` 选项

**答案要点**：
```typescript
export class ConfigTool {
  name = 'git_config';
  description = '读取或设置 Git 配置';

  input_schema = {
    type: 'object' as const,
    properties: {
      key: { type: 'string', description: '配置项名称' },
      value: { type: 'string', description: '配置值（留空则读取）' },
      global: { type: 'boolean', description: '是否操作全局配置', default: false },
    },
  };

  async execute(args: { key?: string; value?: string; global?: boolean }) {
    const git = simpleGit();
    const scope = args.global ? ['--global'] : ['--local'];

    if (args.value) {
      await git.raw(['config', ...scope, args.key, args.value]);
      return { success: true, result: `已设置 ${args.key} = ${args.value}` };
    } else {
      const result = await git.raw(['config', ...scope, args.key!]);
      return { success: true, result: result.trim() };
    }
  }
}
```

### 练习 2：实现插件生命周期钩子

**目标**：为 Git Toolkit 添加 `onMessage` 钩子，自动在消息中添加 Git 状态

**提示**：
- 实现 `hooks.onMessage`
- 在用户消息中检测 Git 相关的关键词

**答案要点**：
```typescript
const gitToolkitPlugin = {
  name: 'git-toolkit',
  version: '1.0.0',

  tools: [new CommitTool(), new BranchTool(), new StatusTool(), new LogTool()],

  hooks: {
    onMessage(message: Message): Message | void {
      // 如果用户提到 "git status"，自动触发状态检查
      if (message.content.includes('git status')) {
        // 可以在这里添加自动的 Git 状态信息
      }
      return message;
    },

    onComplete(): void {
      console.log('Git 操作会话结束');
    },
  },
};
```

### 练习 3：发布插件到 npm

**目标**：将你的插件发布到 npm

**步骤**：
1. 在 [npmjs.com](https://www.npmjs.com/) 注册账号
2. 验证邮箱
3. 在插件目录运行 `npm login`
4. 运行 `npm publish --access public`

**检查清单**：
```bash
# 发布前检查
npm run build                    # 确保编译通过
npm test                        # 确保测试通过
npm ls                          # 检查依赖版本
npm view <package-name>         # 确认包名未被占用
```

---

## 7. 总结

恭喜！你已经完成了：

```
✅ 插件项目初始化
✅ 定义工具接口
✅ 实现 4 个 Git 工具
✅ 测试和调试
✅ 发布准备
```

---

## 下一步

你已经完成了本书的所有内容！

**你已经学会了**：
1. TypeScript 基础
2. Node.js / Bun 运行时
3. CLI 开发
4. React / Ink UI
5. 构建 Mini-Claude
6. 深入理解 Claude Code 架构
7. 阅读大型源码
8. 调试技巧
9. 开源贡献
10. 构建插件

**接下来你可以**：
1. 为 Mini-Claude 添加更多功能
2. 为 Claude Code 贡献代码
3. 构建自己的插件
4. 深入研究感兴趣的模块

---

`★ Insight ─────────────────────────────────────`
构建插件的过程就是一个"小型的系统设计"——你需要定义接口、实现功能、处理错误、编写测试。这和构建完整应用的过程是一样的，只是规模更小。当你掌握了插件开发，你就掌握了构建复杂系统所需的所有核心技能。
`─────────────────────────────────────────────────`

---

**全书完 🎉**
