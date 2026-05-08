# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 项目背景

这是从 `@anthropic-ai/claude-code` v2.1.88 npm 包 source map 中提取的 TypeScript 源码。代码位于 `src/`。

这不是官方可构建发布的完整工程——它是源码提取物，用于学习、理解和实验性修改。

## 目录结构

```
src/
├── main.tsx              # CLI 入口点，Commander.js 参数解析
├── entrypoints/init.ts   # 初始化逻辑（memoized）
├── bootstrap/state.ts    # 全局响应式状态（createSignal）
├── replLauncher.tsx     # REPL 启动入口
├── components/App.tsx   # React Context 根组件
├── screens/REPL.tsx     # 主交互界面
├── cli/                  # CLI 底层 I/O
├── commands/             # 斜杠命令实现（/help, /compact 等）
├── tools/                # 工具实现（文件读写、搜索、Agent 等 30+ 个）
├── services/
│   ├── api/             # Anthropic API 通信
│   ├── tools/           # 工具执行引擎
│   ├── compact/         # 上下文压缩
│   ├── mcp/             # MCP 协议客户端
│   └── analytics/       # GrowthBook A/B 测试
├── state/AppStateStore.ts  # React 状态管理
├── context.ts            # system prompt 构建
├── Tool.ts              # 工具接口定义
├── tools.ts             # 工具注册表
├── types/               # TypeScript 类型定义
├── utils/               # 工具函数库
├── skills/              # 内置技能系统
├── coordinator/         # 多 Agent 协调模式
├── tasks/               # 后台任务
└── voice/               # 语音模式
```

## 关键架构模式

### Feature Flags（条件编译）
```typescript
import { feature } from 'bun:bundle'
const coordinatorModeModule = feature('COORDINATOR_MODE')
  ? require('./coordinator/coordinatorMode.js')
  : null
```

### 懒加载打破循环依赖
```typescript
const getTool = () => require('./tools/Tool.js').Tool
```

### 全局状态（bootstrap/state.ts）
使用 `createSignal()` 实现响应式全局状态，不依赖 React Context：
```typescript
import { state } from './bootstrap/state.js'
const sessionId = state.sessionId.get()
```

## 核心数据流

```
用户输入 → PromptInput → commands.ts（斜杠命令）
                          → messages.ts → API 调用
                                        → tool_use 响应
                                        → services/tools/toolExecution.ts
                                        → 工具执行 → tool_result
                                        → 循环直到模型停止
```

## 关键文件

| 文件 | 作用 |
| :--- | :--- |
| `src/main.tsx` | CLI 入口，参数解析，启动编排 |
| `src/services/api/claude.ts` | API 通信层 |
| `src/services/tools/toolExecution.ts` | 工具执行入口 |
| `src/services/compact/compact.ts` | 上下文压缩 |
| `src/Tool.ts` | 工具接口定义 |
| `src/tools.ts` | 工具注册表 |
| `src/bootstrap/state.ts` | 全局状态单例 |
| `src/entrypoints/init.ts` | 初始化逻辑 |

## 构建与测试

此项目是提取的源码，没有构建脚本或测试套件。验证方式：
1. 阅读 `teaching/` 目录中的架构文档
2. 参考 `teaching/code-walkthrough-index.md` 的代码片段速查表
3. 手动验证：修改后对照原始 npm 包行为

## vendor 目录

`vendor/` 包含从属的 native 模块源码：
- `image-processor-src/` - 图片处理
- `audio-capture-src/` - 音频捕获
- `modifiers-napi-src/` - NAPI 修饰符
- `url-handler-src/` - URL 处理

## 学习资源

`teaching/` 目录包含详细的中文架构文档：
- `00-overview.md` - 全局架构总览（含完整目录结构图）
- `code-walkthrough-index.md` - 代码片段速查表（工具执行、API调用等核心代码行号）
- `01-11-*.md` - 各模块详解

**快速定位**：使用 `teaching/code-walkthrough-index.md` 中的速查表找到核心代码行号

## 敏感逻辑提示

涉及以下功能时请重点分析调用边界：
- 权限系统（`tools/` 中的工具执行）
- 文件写入（`tools/FileWriteTool/`）
- Shell 执行（`tools/BashTool/`）
- 远程会话（`remote/`, `server/`）
- MCP 集成（`services/mcp/`）
- Token/上下文压缩（`services/compact/`）

## 源码识别提示

### React Compiler 产物
Claude Code 使用了 React Compiler（React Forget）优化。阅读源码时注意：
- `_c(N)` — 创建缓存实例的调用，N 是编译器分配的槽号
- `$[0]`、`$[1]` — 缓存的变量槽
- `if ($[0] !== x || $[1] !== y)` — 编译后自动生成的相等性检查

这些不是手写代码，是编译器产物，核心逻辑在上面的 JSX 里。

## 验证修改

由于没有构建脚本和测试套件：
1. 对照原始 npm 包行为验证功能
2. 使用 `teaching/code-walkthrough-index.md` 中的代码片段速查定位关键代码
3. 人工测试：对比修改前后 CLI 的实际行为差异

## 工作方式

1. 先阅读代码，再下结论。使用 teaching/ 目录的架构文档辅助理解
2. 使用 grep/rg 搜索符号和调用链，给出具体文件路径和函数名
3. 保持改动最小，遵循现有代码风格；如有不确定性，明确指出
