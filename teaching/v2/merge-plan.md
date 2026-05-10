# 旧文档合并计划

> 基于 audit-report.md 的审计结果，将旧 teaching/ 中有价值的独有内容整合到 v2 书中，然后删除旧文件。

## 合并任务（按优先级排序）

### Task 1: 卷三第08章补充 Hook/Skill 细节
**目标文件:** `卷三-造物主的工坊/第08章-开发完整插件.md`
**来源:** `part-3-contributor/20-构建你的第一个插件.md`
**合并内容:**
- 28 种 HookEvent 完整列表（v2 只列了 4 种）
- 4 种 HookCommand 类型详解（command/prompt/agent/http）
- Skill 四来源架构（bundled/skills目录/MCP/Plugin）
- inline vs fork 执行模式对比表
- 插件设计 4 原则（单一职责/幂等性/错误隔离/版本兼容）

### Task 2: 卷三第11章补充项目健康度分析
**目标文件:** `卷三-造物主的工坊/第11章-从代码到贡献.md`
**来源:** `part-3-contributor/19-向ClaudeCode贡献代码.md`
**合并内容:**
- 架构腐化识别 7 类问题表
- 技术债详情 5 项深度分析
- 代码审查反馈类型 5 标记（nitpick/suggestion/question/issue/praise）
- 完整代码审查练习（DoubleReadTool 示例）

### Task 3: 卷二第12章补充认证和远程会话
**目标文件:** `卷二-引擎室的秘密/第12章-API通信的暗面.md`
**来源:** `part-2-architecture/16-API通信与远程.md`
**合并内容:**
- 四种认证方式对比表（API Key/OAuth/AWS Bedrock/Google Vertex）
- OAuth PKCE 完整流程 7 步时序图
- 远程会话架构概述（RemoteSession/Bridge/Direct Connect）

### Task 4: 卷二第01章补充映射表
**目标文件:** `卷二-引擎室的秘密/第01章-打开引擎室的门.md`
**来源:** `part-2-architecture/05-全局架构总览.md`
**合并内容:**
- Mini-Claude 到 Claude Code 组件映射表
- 核心差距分析表（11维对比）

### Task 5: 卷二第11章补充工程细节
**目标文件:** `卷二-引擎室的秘密/第11章-跨越会话的记忆.md`
**来源:** `part-2-architecture/14-记忆与持久化.md`
**合并内容:**
- CLAUDE.md 加载流程 6 步详解
- @include 指令支持规则
- Session Memory 完整模板（9 section）

### Task 6: 新建附录 A — TypeScript 速成
**目标文件:** `卷四-架构师的棋盘/附录A-TypeScript速成.md`（新文件）
**来源:** `part-0-preparation/P1-TypeScript入门.md` + `appendix/A1-TypeScript实战技巧.md`
**合并内容:**
- P1 的 TS 基础教学骨架（类型/接口/泛型/联合类型/async-await/模块）
- A1 的精华：Branded Types、Discriminated Unions、TypedEventEmitter 实现、DeepPartial 系列

### Task 7: 新建附录 B — Java→TypeScript 迁移指南
**目标文件:** `卷四-架构师的棋盘/附录B-Java到TypeScript迁移.md`（新文件）
**来源:** `part-4-advanced/21-TypeScript实战对比.md` + `appendix/A13-TypeScript实战.md`
**合并内容:**
- 设计模式映射总表（8 对 TS/Java 对比）
- 核心代码对比（buildTool/FactoryBean、Signal/Flow、AsyncGenerator/CompletableFuture）
- Zod Schema 实战教学
- 迁移检查清单总表

### Task 8: 新建附录 C — 命令速查
**目标文件:** `卷四-架构师的棋盘/附录C-命令速查.md`（新文件）
**来源:** `appendix/A3-常用命令速查表.md`（大幅精简）
**合并内容:**
- 仅保留：Claude Code CLI 命令 + REPL 内命令 + 环境变量速查

### Task 9: 新建附录 D — 核心源码路径
**目标文件:** `卷四-架构师的棋盘/附录D-核心源码路径.md`（新文件）
**来源:** `appendix/A2-代码附录.md`（大幅精简）
**合并内容:**
- 文件路径映射表（17 个核心源码路径）
- 核心数据结构速查（ContentBlock/ToolCall/Usage）

### Task 10: 清理旧文件
**删除:**
- `teaching/part-0-preparation/` 全部
- `teaching/part-1-tutorial/` 全部
- `teaching/part-2-architecture/` 全部
- `teaching/part-3-contributor/` 全部
- `teaching/part-4-advanced/` 全部
- `teaching/appendix/` 全部
- `teaching/book/` 全部
- `teaching/BOOK-ARCHITECTURE.md`
- `teaching/SUMMARY.md`
- `teaching/quick-start.md`
- `teaching/引言-如何阅读本书.md`
- `teaching/RalphLoop进度.md`
- `teaching/code-walkthrough-index.md`
- `teaching/MASTER-PLAN.md`
- `teaching/book-structure.md`
- `teaching/audit-report.md`（本次审计报告）
**保留:**
- `teaching/v2/` 全部（成品书）
- `teaching/README.md` → 更新为指向 v2 的入口

## 执行顺序

Task 1-5 是对现有章节的补充（编辑操作）→ 并行执行
Task 6-9 是新建附录文件 → 并行执行
Task 10 是清理 → 最后执行
