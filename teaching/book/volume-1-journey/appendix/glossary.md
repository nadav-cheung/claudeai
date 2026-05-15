# 附录 A：术语表

### AsyncGenerator（异步生成器）
ES2018 引入的异步迭代协议实现，函数声明为 `async function*`，通过 `yield` 逐个产出值，调用者用 `for await...of` 消费——Claude Code 的流式响应核心机制。

### yield*（委托）
将一个可迭代对象（包括 AsyncGenerator）的所有产出值逐个转发给外层生成器，Claude Code 用它将子查询的流式输出无缝透传给调用者。

### for await...of
异步迭代语法，自动等待每次 `next()` 返回的 Promise，是消费 AsyncGenerator 的标准写法。

### System Prompt（系统提示）
发送给 LLM 的最高优先级指令文本，定义角色、约束和可用工具，位于对话上下文的最前端。

### Prompt Cache（提示缓存）
Anthropic API 的优化特性：标记不变的 prompt 前缀可被缓存，避免重复计费和重传，Claude Code 用 `SYSTEM_PROMPT_DYNAMIC_BOUNDARY` 分界静态区与动态区以最大化命中率。

### SYSTEM_PROMPT_DYNAMIC_BOUNDARY
System prompt 中的一条特殊分隔标记，其上方为稳定不变的"静态区"（可命中缓存），下方为随会话状态变化的"动态区"。

### CLAUDE.md
项目级配置文件（可嵌套多级），包含代码库说明、行为偏好和约束规则，被加载到 system prompt 的动态区中指导模型行为。

### MCP（Model Context Protocol）
Anthropic 定义的开放协议，允许外部工具服务器通过标准接口向 LLM 提供工具和数据，Claude Code 在启动时发现并注册 MCP 工具。

### StreamingToolExecutor
管理工具并行执行状态的核心类，维护一个执行队列，根据 `isConcurrencySafe` 标记决定工具是否可以同时运行。

### isConcurrencySafe
工具的元数据属性，标记该工具是否可与其他工具并发执行；文件写入等有副作用的工具标记为 `false`，必须串行。

### PermissionMode（权限模式）
Claude Code 的安全分级机制，包括 `default`（询问）、`plan`（只读）、`auto`（AI 分类器自动决定）等模式，控制工具执行的审批流程。

### feature() 编译时消除
在打包阶段通过 Babel 插件将 `feature("flag")` 调用替换为布尔常量，未启用的功能分支在产物中被完全移除（dead code elimination）。

### Memoize（记忆化）
缓存函数返回值的装饰器模式，Claude Code 用它避免重复计算（如 system prompt 组装、Git 状态查询），在上下文不变时直接返回缓存结果。

### GrowthBook
开源特性开关（feature flag）平台，Claude Code 通过其 SDK 获取实验分组和功能开关状态，实现灰度发布和 A/B 测试。

### Tool Result Budget / Snip / Microcompact / Autocompact（四层压缩管线）
上下文管理的四个递进策略：Tool Result Budget 裁剪过大的工具输出（零成本），Snip 用轻量摘要替换旧工具结果（极低成本），Microcompact 在流式循环末尾轻量压缩（低成本），Autocompact 在上下文即将溢出时调用模型进行完整摘要压缩（高成本）。每层在前一层不够时触发。

### Context Collapse drain
上下文超过阈值时触发的"排水"操作：将对话历史压缩为摘要后清空原始消息，释放 token 预算以继续对话。

### Reactive Compact
响应式压缩策略，在每次查询循环迭代结束时评估上下文使用率，若超过阈值则自动触发压缩，避免被动溢出。

### Ink（终端 React 框架）
Vadim Demedes 开发的库，将 React 组件模型适配到终端环境，用组件树描述 TUI 布局，通过自定义 React Reconciler 渲染到终端。

### Yoga（Flexbox 布局引擎）
Facebook 的跨平台布局引擎，实现了 CSS Flexbox 算法，Ink 用它计算终端组件的位置和尺寸。

### Reconciler（协调器）
React 架构的核心模块，负责比较前后两棵 Fiber 树的差异并生成更新指令；Ink 实现了自定义 Reconciler 将 DOM 操作替换为终端输出。

### Frame Buffer（帧缓冲）
累积一帧内所有输出操作，在帧结束时一次性写入终端，避免闪烁和撕裂——类似于游戏开发中的双缓冲技术。

### ANSI escape codes
终端控制字符序列标准，用于控制光标位置、颜色、清屏等，Claude Code 的渲染引擎通过它们实现终端 UI 的精确绘制。

### tool_use / tool_result
Anthropic API 的消息类型对：模型发出 `tool_use` 表示希望调用某工具，客户端执行后返回 `tool_result`，形成工具调用闭环。

### Extended Thinking（扩展思考）
Claude 的深度推理模式，模型在回复前先进行一段不可见的内部推理（thinking block），适用于复杂分析任务。

### Hook（钩子）
在特定生命周期事件（如工具执行前后、会话停止时）触发的用户自定义脚本，允许外部系统介入 Claude Code 的执行流程。

### State 不可变更新
在 `queryLoop` 中通过展开运算符 `{...state, field: newValue}` 更新状态，而非直接修改，确保每个循环迭代的状态快照独立可追溯。

### diminishing returns（收益递减）
上下文管理的经济原则：当上下文越长时，每多一个 token 带来的边际效用递减，因此需要主动压缩以维持模型效果。
