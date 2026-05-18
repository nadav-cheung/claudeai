# 附录 C：术语表

> 本书涉及的中英文术语速查。按拼音排序，格式：中文名 | 英文名 | 简要说明。

---

## A

| 中文术语 | 英文术语 | 说明 |
|---------|---------|------|
| ANSI 转义码 | ANSI escape codes | 终端控制字符序列标准，用于控制光标位置、颜色、清屏等，Claude Code 通过它们实现终端 UI 的精确绘制 |

## B

| 中文术语 | 英文术语 | 说明 |
|---------|---------|------|
| Branded Types | Branded Types / Nominal Types | 通过交叉类型 `string & { __brand: 'X' }` 区分语义相同但不应混用的类型，如 toolName 与 messageId |
| 编译时消除 | Compile-time elimination / Dead code elimination | 在打包阶段通过 Babel 插件将 `feature("flag")` 调用替换为布尔常量，未启用的功能分支在产物中被完全移除 |

## C

| 中文术语 | 英文术语 | 说明 |
|---------|---------|------|
| 上下文窗口 | Context window | LLM 单次请求能处理的最大 token 数量，超出时需压缩或截断对话历史 |
| 上下文压缩 | Compaction / Context compression | 将对话历史压缩为摘要以释放 token 空间的策略，包括 Snip、Microcompact、Autocompact 等多层管线 |
| 上下文坍塌 | Context collapse | 上下文超过阈值时触发的"排水"操作：将对话历史压缩为摘要后清空原始消息 |
| 响应式压缩 | Reactive compact | 在每次查询循环迭代结束时评估上下文使用率，若超阈值则自动触发压缩 |
| 帧缓冲 | Frame buffer | 累积一帧内所有输出操作，在帧结束时一次性写入终端，避免闪烁——类似游戏开发中的双缓冲 |

## D

| 中文术语 | 英文术语 | 说明 |
|---------|---------|------|
| 递减收益 | Diminishing returns | 上下文管理的经济原则：上下文越长，每多一个 token 带来的边际效用递减，因此需主动压缩以维持模型效果 |

## E

| 中文术语 | 英文术语 | 说明 |
|---------|---------|------|
| 扩展思考 | Extended Thinking | Claude 的深度推理模式，模型在回复前先进行内部推理（thinking block），适用于复杂分析任务 |

## F

| 中文术语 | 英文术语 | 说明 |
|---------|---------|------|
| Fiber 协调器 | Fiber reconciler | React 架构的核心模块，比较前后两棵 Fiber 树的差异并生成更新指令；Ink 实现了自定义 Reconciler 将 DOM 操作替换为终端输出 |

## G

| 中文术语 | 英文术语 | 说明 |
|---------|---------|------|
| 工具调用 | Tool use / tool_use | Anthropic API 的消息类型：模型发出 `tool_use` 表示希望调用某工具，客户端执行后返回 `tool_result` |
| 工具结果 | Tool result / tool_result | 客户端执行工具后返回给模型的结果消息类型，与 `tool_use` 配对形成闭环 |
| 工具结果预算 | Tool result budget | 四层压缩管线的第一层：裁剪过大的工具输出，零成本 |
| 滚动裁剪 | Snip | 四层压缩管线的第二层：用轻量摘要替换旧工具结果，极低成本 |
| 概览压缩 | Microcompact | 四层压缩管线的第三层：在流式循环末尾轻量压缩，低成本 |
| 自动压缩 | Autocompact | 四层压缩管线的第四层：上下文即将溢出时调用模型进行完整摘要，高成本 |

## H

| 中文术语 | 英文术语 | 说明 |
|---------|---------|------|
| 钩子 | Hook | 在特定生命周期事件（如工具执行前后、会话停止时）触发的用户自定义脚本，允许外部系统介入执行流程 |

## I

| 中文术语 | 英文术语 | 说明 |
|---------|---------|------|
| Ink | Ink | Vadim Demedes 开发的终端 React 框架，将 React 组件模型适配到终端环境，用组件树描述 TUI 布局 |

## J

| 中文术语 | 英文术语 | 说明 |
|---------|---------|------|
| 记忆化 | Memoize | 缓存函数返回值的装饰器模式，Claude Code 用它避免重复计算（如 system prompt 组装、Git 状态查询） |

## K

| 中文术语 | 英文术语 | 说明 |
|---------|---------|------|
| 可并发安全 | isConcurrencySafe | 工具的元数据属性，标记该工具是否可与其他工具并发执行；文件写入等有副作用的工具标记为 `false` |

## L

| 中文术语 | 英文术语 | 说明 |
|---------|---------|------|
| 流式响应 | Streaming | LLM 逐 token 产出响应而非一次性返回，Claude Code 通过 AsyncGenerator 实现流式消费 |

## M

| 中文术语 | 英文术语 | 说明 |
|---------|---------|------|
| 模型上下文协议 | MCP (Model Context Protocol) | Anthropic 定义的开放协议，允许外部工具服务器通过标准接口向 LLM 提供工具和数据 |
| Mailbox | Mailbox | 子 Agent 的消息邮箱机制，用于在主 Agent 和子 Agent 之间传递消息与结果 |

## P

| 中文术语 | 英文术语 | 说明 |
|---------|---------|------|
| 提示缓存 | Prompt cache | Anthropic API 的优化特性：标记不变的 prompt 前缀可被缓存，避免重复计费和重传 |
| 动态边界 | SYSTEM_PROMPT_DYNAMIC_BOUNDARY | System prompt 中的分隔标记，上方为可缓存静态区，下方为随会话状态变化的动态区 |
| 权限模式 | PermissionMode | Claude Code 的安全分级机制，包括 `default`（询问）、`plan`（只读）、`auto`（AI 分类器决定）等模式 |
| Plugin | Plugin | Claude Code 的插件系统，允许第三方扩展功能，通过标准接口注册工具和 Hook |

## Q

| 中文术语 | 英文术语 | 说明 |
|---------|---------|------|
| 签名/信号 | Signal | 通过 `createSignal()` 创建的发布-订阅对象，15 行代码实现类型安全的事件通信 |

## S

| 中文术语 | 英文术语 | 说明 |
|---------|---------|------|
| 系统提示 | System prompt | 发送给 LLM 的最高优先级指令文本，定义角色、约束和可用工具，位于对话上下文最前端 |
| 状态不可变更新 | State immutable update | 在 `queryLoop` 中通过展开运算符 `{...state, field: newValue}` 更新状态，确保每个循环迭代的状态快照独立 |
| Speculative 执行 | Speculative execution | 推测性执行：在等待用户确认的同时预先执行工具，若用户批准则直接使用结果，否则丢弃 |
| Skill | Skill | Claude Code 的技能系统，以 `/` 前缀调用的命名命令，可自定义注册 |

## T

| 中文术语 | 英文术语 | 说明 |
|---------|---------|------|
| Token | Token | LLM 处理文本的基本单位，约 4 个字符或 0.75 个英文单词；上下文窗口以 token 计量 |
| 同步流式生成器 | AsyncGenerator | ES2018 异步迭代协议实现，函数声明为 `async function*`，通过 `yield` 逐个产出值 |
| yield* 委托 | yield* delegation | 将一个可迭代对象的所有产出值逐个转发给外层生成器，用于子查询的流式输出透传 |
| for await...of | for await...of | 异步迭代语法，自动等待每次 `next()` 返回的 Promise，消费 AsyncGenerator 的标准写法 |

## Y

| 中文术语 | 英文术语 | 说明 |
|---------|---------|------|
| Yoga | Yoga (Flexbox engine) | Facebook 的跨平台布局引擎，实现 CSS Flexbox 算法，Ink 用它计算终端组件的位置和尺寸 |
| 异步迭代 | Async iteration | 通过 `AsyncGenerator` + `for await...of` 实现的异步数据流消费模式 |

## Z

| 中文术语 | 英文术语 | 说明 |
|---------|---------|------|
| Zod Schema | Zod | TypeScript 生态最主流的运行时验证库，弥补 TS 类型只在编译时生效的缺口，`z.infer` 可从 Schema 自动生成类型 |
| 子代理 | Subagent / Sub-agent | 由主 Agent 派生的子任务执行单元，通过 Mailbox 机制与主 Agent 通信 |
| Agentic Loop | Agentic Loop | Agent 的核心执行循环：接收输入 → 调用模型 → 执行工具 → 再调用模型，直到任务完成 |

---

## 跨卷核心概念对照

下表列出贯穿全书多个卷的核心概念及其首次出现的章节（使用全局章节编号 ch01-ch66）：

| 概念 | 类型 | 首次出现 | 所在章 |
|------|------|---------|--------|
| `query()` / `queryLoop()` | 函数 | ch07 | 第 7 章：信封飞向远方 |
| `AsyncGenerator` yield 链 | 模式 | ch07 | 第 7 章：信封飞向远方（知识补全） |
| `createSignal()` | 函数 | ch17 | 第 17 章：打开引擎室的门（状态管理） |
| `PermissionMode` | 类型 | ch22 | 第 22 章：安全门卫 |
| Ink + Fiber Reconciler | 框架 | ch19 | 第 19 章：React 在终端里奔跑 |
| `buildTool()` 工厂 | 函数 | ch20 | 第 20 章：工具的 DNA |
| MCP 协议 | 协议 | ch25 | 第 25 章：外部世界的入口 |
| Prompt Cache | 特性 | ch05 | 第 5 章：消息被装进信封（动态边界） |
| Compaction 管线 | 策略 | ch13 | 第 13 章：对话越来越长 |
| Hook 生命周期 | 机制 | ch24 | 第 24 章：Hook 系统 |
| Zod Schema | 库 | 附录 B | 附录 B：Java 到 TypeScript 迁移 |
| Skill 系统 | 机制 | ch23 | 第 23 章：斜杠命令与插件系统 |
