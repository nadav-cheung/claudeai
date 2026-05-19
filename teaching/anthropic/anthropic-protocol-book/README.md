# Anthropic 协议深度剖析：Python & Node.js 实现指南

## 关于本书

本书是一本面向有经验开发者的技术书籍，深度剖析 Anthropic API 协议栈的全部公开特性。读完本书后，读者能够用自己的语言从零实现 Anthropic API 协议栈的所有核心能力。

### 协议时效

基于 2026 年最新协议版本（Claude Opus 4.7 / Sonnet 4.6 / Haiku 4.5 时代）。

## 推荐阅读路径

### 路径 A："我要实现自己的 SDK"
第 1 章 → 第 2 章 → 第 4 章 → 第 5 章 → 第 6 章 → 第 8 章 → 第 9 章 → 第 17 章

### 路径 B："我要构建 Agent 系统"
第 1 章 → 第 2 章 → 第 6 章 → 第 8 章 → 第 11-12 章 → 第 14 章 → 第 15 章 → 第 17 章

### 路径 C："我要搭建 RAG 系统"
第 1 章 → 第 3 章 → 第 8 章 → 第 13 章

## 目录

### 第一部分：基础协议
- 第 1 章：Anthropic API 基础 — 认证、通信、错误处理
- 第 2 章：Messages API 核心协议 — Content Blocks、多模态、参数体系
- 第 3 章：LLM 模型深度剖析 — 模型族、Token 机制、Pricing

### 第二部分：核心协议特性
- 第 4 章：Structured Outputs — Constrained Decoding、JSON Schema 约束
- 第 5 章：Streaming 与 Extended Thinking — SSE 协议、Thinking 签名
- 第 6 章：Tool Use & Function Calling — 标准/Strict/Advanced Tool Use
- 第 7 章：Computer Use — 桌面环境操控协议
- 第 8 章：上下文管理 — Prompt Caching 与 Compaction
- 第 9 章：Batch API — 异步批量处理
- 第 10 章：Memory 与 Citations — 持久化记忆、引用溯源

### 第三部分：生态协议
- 第 11 章：MCP 协议规范 — JSON-RPC、原语、传输层、授权、安全
- 第 12 章：MCP 实战构建 — Server/Client/Tasks 实现

### 第四部分：应用模式
- 第 13 章：RAG 检索增强生成 — Pipeline、Claude-as-Judge、Agentic RAG
- 第 14 章：Agent SDK 与 Agent 模式 — 单/多 Agent 架构
- 第 15 章：Claude Managed Agents — 托管运行时
- 第 16 章：LangChain & LangGraph — Agent 工程平台

### 第五部分：生产实践
- 第 17 章：生产实践 — 限流、重试、安全、预算、可观测性

### 附录
- 附录 A：API 快速参考表
- 附录 B：模型对比矩阵
- 附录 C：自测题答案
- 附录 D：术语表（中英对照）
- 附录 E：协议版本变更记录

## 代码运行说明

每章代码可独立运行，不依赖 Anthropic 官方 SDK。

**Python（3.12+）：**
```bash
cd code/python/chXX
pip install httpx pytest
python -m pytest test_*.py -v
```

**Node.js（22+ / TypeScript 5.x）：**
```bash
cd code/node/chXX
npm install
npx vitest run
```

## 写作进度

| 章节 | 协议规范 | Python 实现 | Node.js 实现 | 自测题 |
|------|----------|-------------|--------------|--------|
| 第 1 章 | ✅ | ✅ | ✅ | ✅ |
| 第 2 章 | ✅ | ✅ | ✅ | ✅ |
| 第 3 章 | ✅ | ✅ | ✅ | ✅ |
| 第 4 章 | ✅ | ✅ | ✅ | ✅ |
| 第 5 章 | ✅ | ✅ | ✅ | ✅ |
| 第 6 章 | ✅ | ✅ | ✅ | ✅ |
| 第 7 章 | ✅ | ✅ | ✅ | ✅ |
| 第 8 章 | ✅ | ✅ | ✅ | ✅ |
| 第 9 章 | ✅ | ✅ | ✅ | ✅ |
| 第 10 章 | ✅ | ✅ | ✅ | ✅ |
| 第 11 章 | ✅ | ✅ | ✅ | ✅ |
| 第 12 章 | ✅ | ✅ | ✅ | ✅ |
| 第 13 章 | ✅ | ✅ | ✅ | ✅ |
| 第 14 章 | ✅ | ✅ | ✅ | ✅ |
| 第 15 章 | ✅ | ✅ | ✅ | ✅ |
| 第 16 章 | ✅ | ✅ | ✅ | ✅ |
| 第 17 章 | ✅ | ✅ | ✅ | ✅ |

**总计：17 章全部完成，~1760 tests 通过（Python + Node.js）**