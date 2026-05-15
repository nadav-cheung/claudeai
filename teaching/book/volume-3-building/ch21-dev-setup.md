# 第 21 章：扩展准备——开发环境与构建系统

> 源码验证日期：2026-05-15，基于 commit `0d81bb6`

本章是卷三的第一章。接下来 7 章每章都是一个完整的扩展项目。本章先搭建开发环境、理解构建系统和测试策略。

---

## 技术栈概览

Claude Code 的技术栈：

| 类别 | 技术 |
|------|------|
| **语言** | TypeScript（`.ts` / `.tsx`） |
| **运行时** | Node.js >= 18 + Bun API |
| **打包器** | Bun 内置打包器 |
| **模块系统** | ESM（`"type": "module"`） |
| **CLI 框架** | Commander.js（`@commander-js/extra-typings`） |
| **终端 UI** | React + 自定义 Ink fork（`src/ink/`） |
| **验证** | Zod v4 |
| **MCP 协议** | `@modelcontextprotocol/sdk` |
| **AI SDK** | `@anthropic-ai/sdk` |
| **测试** | Vitest |
| **可观测性** | OpenTelemetry |

---

## 开发环境搭建

### 前置条件

```bash
# Node.js >= 18
node --version

# Bun（用于打包和运行时）
bun --version

# Git
git --version
```

### 克隆和安装

```bash
git clone <repo-url>
cd claude-code

# 安装依赖
bun install

# 运行（开发模式）
bun run dev

# 运行测试
bun test

# 构建
bun run build
```

### 目录结构要点

```
src/
├── entrypoints/       # 入口文件（cli.tsx, mcp.ts, sdk/）
├── main.tsx           # 完整 CLI 应用
├── tools/             # 40+ 工具实现
│   ├── BashTool/      # 每个工具有独立目录
│   ├── FileEditTool/
│   └── ...
├── commands/          # 70+ 斜杠命令
│   ├── compact/
│   ├── config/
│   └── ...
├── ink/               # 自定义 Ink fork
├── components/        # React 组件
├── services/          # 业务服务
│   ├── mcp/           # MCP 客户端
│   ├── tools/         # 工具执行引擎
│   └── api/           # API 调用
├── utils/             # 工具函数
├── constants/         # 常量和 prompt
├── state/             # 状态管理
└── bootstrap/         # 启动状态
```

---

## 构建系统

### Bun 打包器

Claude Code 使用 Bun 的内置打包器（不是 webpack/rollup/esbuild）：

```typescript
// feature() 从 bun:bundle 导入——编译时求值
import { feature } from 'bun:bundle'

// --define 替换编译时常量
// process.env.USER_TYPE → 'ant' 或 'external'
// "external" → 'ant' 或 'external'
// MACRO.VERSION → 版本号字符串
```

### 多构建目标

| 目标 | 入口 | USER_TYPE | Feature Flags |
|------|------|-----------|---------------|
| CLI（外部） | `cli.tsx` | `'external'` | 大部分关闭 |
| CLI（ant） | `cli.tsx` | `'ant'` | 全部开启 |
| MCP Server | `mcp.ts` | — | — |
| Agent SDK | `agentSdkTypes.ts` | — | — |

---

## 测试策略

### 测试框架

Claude Code 使用 Vitest 作为测试框架。

### 测试类型

```typescript
// 1. 单元测试——测试单个函数
describe('bashToolHasPermission', () => {
  it('should deny eval commands', () => {
    const result = bashToolHasPermission('eval "rm -rf /"', context)
    expect(result.behavior).toBe('deny')
  })
})

// 2. 集成测试——测试组件交互
describe('StreamingToolExecutor', () => {
  it('should execute safe tools in parallel', async () => {
    const executor = new StreamingToolExecutor(...)
    executor.addTool(readToolBlock)
    executor.addTool(grepToolBlock)
    // 验证两者并行执行
  })
})

// 3. 工具测试——测试 Tool 接口实现
describe('GlobTool', () => {
  it('should find files matching pattern', async () => {
    const result = await GlobTool.call({ pattern: '*.ts', path: '/project' })
    expect(result.data.files.length).toBeGreaterThan(0)
  })
})
```

### 测试约定

- 测试文件与源文件同目录或放在 `__tests__/` 子目录
- 使用 `process.env.NODE_ENV === 'test'` 条件包含测试专用工具
- `resetStateForTests()` 重置全局状态

---

## 扩展开发模式

卷三的每个扩展项目都遵循类似的模式：

### 模式 1：添加新工具

```
1. 在 src/tools/MyTool/ 创建工具目录
2. 定义 Zod inputSchema
3. 实现 buildTool({ name, call, ... })
4. 在 src/tools.ts 的 getAllBaseTools() 中注册
5. 测试
```

### 模式 2：添加斜杠命令

```
1. 在 src/commands/my-command/ 创建命令目录
2. 选择命令类型（prompt / local / local-jsx）
3. 实现命令逻辑
4. 在 src/commands.ts 中注册
5. 测试
```

### 模式 3：添加 Hook 脚本

```
1. 编写 Shell 脚本（从 stdin 读 JSON，向 stdout 写 JSON）
2. 在 settings.json 中配置 Hook
3. 测试触发和结果
```

---

## 实战准备

在开始后续章节前，确保：

1. 能成功运行 `bun install`
2. 能启动 Claude Code（`bun run dev` 或 `claude`）
3. 能运行测试（`bun test`）
4. 有一个用于测试的项目目录

---

## 检查点

- **技术栈**：TypeScript + Bun + React/Ink + Zod + MCP SDK
- **构建系统**：Bun 打包器，`feature()` 编译时消除，多构建目标
- **测试框架**：Vitest，单元/集成/工具三种测试
- **扩展模式**：工具（buildTool + 注册）、命令（类型选择 + 注册）、Hook（脚本 + 配置）

**下一章**：第 22 章开始第一个实战项目——造一个 GitHub Issue 创建工具。
