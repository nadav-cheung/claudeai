# Claude Code 源码之旅——从零基础到架构贡献者

> 一本源码分析书，带你理解 Claude Code 从按键到回复的每一步。

## 适合谁

会 TypeScript/JavaScript 基础（函数、类、接口、异步），不要求熟悉 CLI 框架或 LLM API。
所有进阶知识（React hooks、Ink 终端渲染、Zod schema、流式响应等）在书中逐步引入。

## 五卷结构

| 卷 | 主题 | 你会获得的能力 |
|----|------|---------------|
| 卷零 | 出发前的地图 | 理解 LLM CLI 和 Agent 是什么 |
| 卷一 | 一次 `query()` 调用的旅程 | 能追踪请求流程、定位 bug、修改源码 |
| 卷二 | 拆开每个齿轮 | 能理解设计模式、读懂任意模块 |
| 卷三 | 造一个新齿轮 | 能独立添加新工具/命令、提交 PR |
| 卷四 | 为什么要这样设计 | 能参与架构讨论、理解设计权衡 |

## 目录

### 卷零：出发前的地图
- [第 1 章：什么是 Claude Code](volume-0-basics/ch01-what-is-claude-code.md)
- [第 2 章：什么是 Agentic Loop](volume-0-basics/ch02-what-is-agentic-loop.md)

### 卷一：一次 `query()` 调用的旅程
- [第 3 章：准备工具箱](volume-1-journey/ch03-toolbox.md)
- [第 4 章：第 1 站——输入捕获](volume-1-journey/ch04-input-capture.md)
- [第 5 章：第 2 站——系统提示](volume-1-journey/ch05-system-prompt.md)
- [第 6 章：第 3 站——工具注册](volume-1-journey/ch06-tool-registration.md)
- [第 7 章：第 4 站——API 调用](volume-1-journey/ch07-api-call.md)
- [第 8 章：第 5 站——工具执行](volume-1-journey/ch08-tool-execution.md)
- [第 9 章：第 6 站——循环与状态](volume-1-journey/ch09-loop-state.md)
- [第 10 章：第 7 站——渲染输出](volume-1-journey/ch10-rendering.md)
- [第 11 章：第 8 站——权限与安全](volume-1-journey/ch11-permissions.md)
- [第 12 章：旅程复盘](volume-1-journey/ch12-journey-review.md)

### 卷二：拆开每个齿轮
- [第 13 章：模块系统——入口与编译时消除](volume-2-patterns/ch13-module-system.md)
- [第 14 章：工具接口——统一的 Tool 类型](volume-2-patterns/ch14-tool-interface.md)
- [第 15 章：Ink 与终端 UI](volume-2-patterns/ch15-ink-terminal-ui.md)
- [第 16 章：权限系统——分层规则引擎](volume-2-patterns/ch16-permission-system.md)
- [第 17 章：Hook 系统——工具调用的拦截](volume-2-patterns/ch17-hook-system.md)
- [第 18 章：斜杠命令与插件系统](volume-2-patterns/ch18-slash-commands-plugins.md)
- [第 19 章：MCP 协议与 Bridge/SDK](volume-2-patterns/ch19-mcp-bridge-sdk.md)
- [第 20 章：状态管理——从 Bootstrap 到 AppState](volume-2-patterns/ch20-state-management.md)

### 卷三：造一个新齿轮
- [第 21 章：扩展准备](volume-3-building/ch21-dev-setup.md)
- [第 22 章：造一个新 Tool](volume-3-building/ch22-new-tool.md)
- [第 23 章：造一个斜杠命令](volume-3-building/ch23-new-command.md)
- [第 24 章：造一个 MCP 客户端](volume-3-building/ch24-new-mcp-client.md)
- [第 25 章：造一个输出样式](volume-3-building/ch25-new-output-style.md)
- [第 26 章：造一个 Hook 脚本](volume-3-building/ch26-new-hook-script.md)
- [第 27 章：高级扩展——任务系统与子代理](volume-3-building/ch27-advanced-extension.md)
- [第 28 章：终章——集成实战](volume-3-building/ch28-integration-capstone.md)

### 卷四：为什么要这样设计
- [第 29 章：为什么用 Ink](volume-4-why/ch29-why-ink.md)
- [第 30 章：为什么用 Zod 验证工具输入](volume-4-why/ch30-why-zod.md)
- [第 31 章：为什么 query.ts 是一个大 AsyncGenerator](volume-4-why/ch31-why-big-query.md)
- [第 32 章：为什么权限系统是分层的](volume-4-why/ch32-why-layered-permissions.md)
- [第 33 章：为什么自定义 Ink fork](volume-4-why/ch33-why-ink-fork.md)
- [第 34 章：为什么工具执行是流式的](volume-4-why/ch34-why-streaming-execution.md)
- [第 35 章：为什么 CLAUDE.md 是指令系统](volume-4-why/ch35-why-claudemd-memory.md)
- [第 36 章：架构的全景与边界](volume-4-why/ch36-panorama.md)

### 附录
- [TypeScript 进阶速查](appendix/typescript-primer.md)
- [术语表](appendix/glossary.md)
- [源码文件速查表](appendix/source-map.md)
- [源码版本追踪表](appendix/version-tracking.md)

## 配套代码

[lab/](lab/) 目录包含 ~30 个可运行的 TypeScript 示例，每个文件通过 `// → src/...` 注释指向真实源码。

## 写作规范

- 源码引用优先使用符号名，不硬编码行号
- 每章开头标注：`源码验证日期：YYYY-MM-DD，基于 commit <short-hash>`
- 首次出现的术语给出中英文
- 每章至少 1 个"试一试"环节
- 每章至少 1 个 Mermaid 流程图或架构图
