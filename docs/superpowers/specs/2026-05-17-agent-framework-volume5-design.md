# 《跟着消息走》卷五：Agent的造物法则 — 设计规格

> **状态**: 已实施
> **日期**: 2026-05-17
> **依赖**: 卷四 (ch41-52) 架构分析、附录F 概念形式化分析
> **写作语言**: 中文为主，TypeScript 源码保留英文，协议字段保留英文

---

## 目标

卷五是全书的终极卷——读者不再分析别人的源码，而是从零开始，用 TypeScript 实现一套能与 Claude API 完整通信的 Agent 框架。

| 卷 | 读者能力 | 核心 |
|----|---------|------|
| 卷四 | 参与架构讨论、理解设计权衡 | 向后看：为什么这样设计 |
| 卷五 | 独立实现 Anthropic 协议栈、构建自己的 Agent 框架 | 向前走：从零造出来 |

---

## 读者画像

完成卷一~卷四的读者。已理解 Claude Code 的全部核心架构和设计权衡。现在需要将知识转化为创造能力——能独立实现一个可运行的 Agent 框架。

---

## 叙事线索

**从 HTTP 请求到完整的 Agent 框架**。14 章每章构建一个独立组件，最终在 ch66 组装为完整的 AgentFramework。

```
Ch53: ApiClient (HTTP)
  ↓
Ch54: MessageBuilder + Ch55: StreamParser + Ch56: ToolExecutor
  ↓
Ch57: McpClient/Server + Ch58: ResourceRegistry
  ↓
Ch59: ThinkingManager + Ch60: CacheStrategy + Ch61: OutputController
  ↓
Ch62: ConfigLoader
  ↓
Ch63: AgentLoop + Ch64: ToolRouter + Ch65: SkillInjector
  ↓
Ch66: AgentFramework (顶层组装)
```

---

## 卷五结构 (14 章)

### 第一部分：API 通信基础 (ch53-56)

| 章 | 标题 | 构建的组件 | 协议规范来源 |
|----|------|-----------|-------------|
| 53 | 一个 HTTP 请求之外 | ApiClient — 认证、Headers、HTTPS 通信 | Messages API headers |
| 54 | 消息的形状 | MessageBuilder — ContentBlock 构造、多模态消息 | Content Blocks 规范 |
| 55 | 文字如溪流 | StreamParser — SSE 协议解析、增量文本累积 | SSE Streaming 规范 |
| 56 | 工具调用的双面人生 | ToolExecutor — tool_use 解析、tool_result 组装 | Tool Use / Function Calling |

### 第二部分：MCP 协议实现 (ch57-58)

| 章 | 标题 | 构建的组件 | 协议规范来源 |
|----|------|-----------|-------------|
| 57 | MCP 的双面 | McpClient/Server — 双角色、传输层 (stdio/HTTP) | MCP Transport |
| 58 | MCP 原语的三位一体 | ResourceRegistry — Tools/Resources/Prompts 管理 | MCP Primitives |

### 第三部分：高级 API 特性 (ch59-61)

| 章 | 标题 | 构建的组件 | 协议规范来源 |
|----|------|-----------|-------------|
| 59 | 思维被拉长了 | ThinkingManager — extended/adaptive thinking | Extended Thinking |
| 60 | 聪明的缓存 | CacheStrategy — prompt caching, cache breakpoints | Prompt Caching |
| 61 | 输出的精确控制 | OutputController — structured output, stop sequences | Output Configuration |

### 第四部分：框架组装 (ch62-66)

| 章 | 标题 | 构建的组件 | 协议规范来源 |
|----|------|-----------|-------------|
| 62 | 配置的多重宇宙 | ConfigLoader — 多层配置合并、权限模式 | CLI Configuration Protocol |
| 63 | 循环的引擎 | AgentLoop — while 循环、终止条件、压缩触发 | Agentic Loop 模式 (卷一+卷四) |
| 64 | 工具的路由与调度 | ToolRouter — 工具注册表、中间件链、并发调度 | Agent 工具编排架构 |
| 65 | 技能的编织 | SkillInjector — skill 定义、加载、注入 | Skills 系统 |
| 66 | 你的 Agent 框架 | AgentFramework — 全部组件顶层组装 | 全书协议实现 |

---

## 每章内部结构 (统一)

1. **路线图** — Mermaid 图，高亮本章在卷五中的位置
2. **协议规范** — 引用 Anthropic/MCP 官方规范原文，解释关键字段和语义
3. **TypeScript 实现** — 完整的组件源码（生产级，非简化版）
4. **验证** — 用真实 API 调用验证实现的正确性
5. **试一试** — 扩展或修改本章实现的组件
6. **下一站预告** — 引向下一章将构建的组件

---

## 与卷四的关系

卷四讨论"为什么这样设计"（被动理解），卷五实践"我怎么实现"（主动构建）。每章的协议规范分析直接引用卷四的设计结论作为决策依据。

---

## 与附录 F 的关系

附录 F（AI 概念关系形式化分析）为卷五提供理论基础：
- Messages API 的形式化定义 → ch53-56 实现
- MCP 的形式化定义 → ch57-58 实现
- Extended Thinking/Cache 的形式化定义 → ch59-61 实现
- Agent/SubAgent/Skill 的形式化定义 → ch63-66 实现
- 六层架构模型 → 全书框架设计的理论依据

---

## 质量标准

### 协议准确性
- 所有协议字段与 Anthropic Messages API 最新版一致（2023-06-01 header）
- MCP 实现基于规范 2025-11-25（最新 Release Candidate）
- 每章开头标注协议验证日期

### 代码完整性
- 每章的 TypeScript 组件是完整可编译的
- 组件之间有明确的 import/export 依赖关系
- ch66 将所有组件组装为可运行的 AgentFramework

### 叙事质量
- 每章开头有路线图定位
- 协议规范先解释再实现
- 代码注释充分

---

## 不做什么

- 不是 Claude Code 的源码分析（那是卷一~卷四的内容）
- 不是 Anthropic API 的官方文档翻译
- 不是生产级框架（教学优先，完整性次之）
- 不追求极致性能（关注正确性和可理解性）

---

## 修订记录

### 初版 (2026-05-17)
- 基于 V3 合并版书籍的实际结构撰写
- 卷五为 V3 新增，超越了 V2 spec 的四卷设计
- 每章对应一个独立的协议/组件实现
