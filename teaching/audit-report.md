# 内容审计报告：旧版教学材料 vs v2 图书

> 审计日期：2026-05-10
> 审计范围：part-0-preparation、part-2-architecture、part-3-contributor、part-4-advanced、appendix 中的 14 个旧文件
> 对照版本：v2 四卷本图书对应章节

---

## 审计总览

| 类别 | 旧文件数 | 内容完全冗余 | 有独有价值 | 建议合并 |
|------|---------|-------------|-----------|---------|
| part-0-preparation | 4 | 0 | 4 | 2 |
| part-2-architecture | 4 | 0 | 4 | 1 |
| part-3-contributor | 2 | 0 | 2 | 1 |
| part-4-advanced | 1 | 0 | 1 | 1 |
| appendix | 4 | 2 | 2 | 2 |

---

## 逐文件详细审计

### 1. part-0-preparation/P1-TypeScript入门.md

| 旧文件 | 独有内容（v2缺什么） | 值得合并？→ 目标v2章节 | 冗余可删？ |
|--------|---------------------|----------------------|-----------|
| P1-TypeScript入门.md | **完整的 TypeScript 速成教程**（~730行），覆盖：原始类型、类型推断、数组/元组/枚举、接口与继承、联合/交叉类型、类型守卫、泛型（函数/接口/约束）、6种工具类型（Partial/Required/Pick/Omit/Record）、async/await 与 Promise、模块系统 import/export、实战练习（类型安全工具库、Result 类型）、常见 TS 错误与解决方案。v2 没有任何章节提供这种"从零开始"的 TS 基础教程——卷四第01章讨论"为什么选 TS"是架构决策讨论，不是教学材料。 | **值得合并** → 作为卷四的补充章节，或在卷一第01章后作为"前置知识附录"。建议保留完整内容，仅删去与 v2 重复的泛型/联合类型基础提及。 | 否 |

### 2. part-0-preparation/P2-Nodejs与Bun入门.md

| 旧文件 | 独有内容（v2缺什么） | 值得合并？→ 目标v2章节 | 冗余可删？ |
|--------|---------------------|----------------------|-----------|
| P2-Nodejs与Bun入门.md | **完整的 Node.js/Bun 运行时教程**（~640行），覆盖：运行时概念对比（Node vs Bun）、安装步骤（nvm/Bun）、npm 包管理器完整操作（init/install/scripts）、语义化版本（SemVer）详解、文件系统操作（fs/promises + Bun.file）、网络请求（fetch + POST + AbortController 超时）、命令行参数解析（process.argv + yargs）、环境变量（process.env + dotenv）、进程管理（pid/cwd/exit/SIGINT）、commander.js 使用示例、Bun 特有功能（Bun.file/Bun.serve/自动加载 .env）、实战练习。v2 无任何等效内容。 | **值得合并** → 作为卷四的补充附录，或在卷一安装说明后扩展。其中的 SemVer、文件操作、进程管理等知识对理解 Claude Code 源码有直接帮助。 | 否 |

### 3. part-0-preparation/P3-CLI开发基础.md

| 旧文件 | 独有内容（v2缺什么） | 值得合并？→ 目标v2章节 | 冗余可删？ |
|--------|---------------------|----------------------|-----------|
| P3-CLI开发基础.md | **CLI 工具开发完整教程**（~740行），覆盖：CLI vs GUI 对比、commander.js 完整 API（选项/子命令/链式命令）、inquirer.js 交互式输入（input/list/confirm/password）、输出格式化（chalk 彩色 + ora 进度条 + table 表格）、配置文件管理、命令历史记录、自定义 CLIError 错误类、**完整的 Todo CLI 实战项目**（~120行可运行代码）、tab 补全/调试/发布到 npm。v2 无任何 commander/inquirer/chalk/ora 教学内容。 | **部分值得合并** → chalk/ora/table 的使用技巧可作为"终端 UI 工具箱"附录。完整的 Todo CLI 项目已由 v2 卷三的工具开发章节替代，但 CLI 开发基础知识（commander + inquirer）对新手有独立价值，可保留为卷三的前置附录。 | 部分可删（实战项目代码与 v2 重复） |

### 4. part-0-preparation/P4-React基础速成.md

| 旧文件 | 独有内容（v2缺什么） | 值得合并？→ 目标v2章节 | 冗余可删？ |
|--------|---------------------|----------------------|-----------|
| P4-React基础速成.md | **React 基础速成 + Ink 入门**（~650行），覆盖：JSX 语法（表达式/属性/样式）、组件与 Props（解构/默认值）、useState（函数式更新/对象状态合并）、useEffect（依赖数组/清理函数）、条件渲染与列表渲染（三元/&&/key）、**Ink 核心组件对照表**（Box=div, Text=span, Static, Spacer）、Claude Code REPL 简化版代码、Ink Todo 应用完整代码、自定义 Hook（useDebounce）练习。v2 卷二第03章深入 Ink 渲染管线（Fiber/协调器/Yoga），但不教 React 基础。 | **部分值得合并** → "React 核心概念 5 分钟速览"（JSX/Props/State/useEffect）和"Ink 核心组件对照表"可提取为卷二第03章的前置附录。Ink Todo 完整代码和练习已由 v2 替代。 | 部分可删（Ink 深度内容由 v2 覆盖） |

### 5. part-2-architecture/05-全局架构总览.md

| 旧文件 | 独有内容（v2缺什么） | 值得合并？→ 目标v2章节 | 冗余可删？ |
|--------|---------------------|----------------------|-----------|
| 05-全局架构总览.md | **Mini-Claude 到 Claude Code 的组件映射表**（7行精确映射：Tool 接口/工具/服务/REPL/入口）、**核心差距分析表**（11维对比：工具数/参数校验/权限/MCP/API/流式/错误/状态/Shell）、**Feature Flag 条件编译机制**（bun:bundle feature() 死代码消除）、**全局状态两层架构详解**（bootstrap/state.ts Signal vs React Context）、**替代方案对比表**（Ink vs ncurses/blessed, Signal vs Redux）、**启动时序图的 5 个 Phase 及耗时**（模块加载~135ms, CLI解析~5ms, init~100ms, 认证~50ms, REPL渲染~50ms）、**Contributor 指南的危险逻辑红绿灯**（main.tsx:591/PATH劫持/bootstrap state/init memoize/Feature flags）、**调试方法**（--debug/profileCheckpoint/INK_DEBUG=1）、Java Spring 对比表（入口/状态/工具/上下文/拦截器/配置/模块化 7维映射）。v2 卷二第01章是目录结构地图，不讲 Mini-Claude 映射、Feature Flag、状态架构、启动性能。 | **部分值得合并** → "Mini-Claude 组件映射表"和"核心差距分析表"是 v2 缺失的桥梁内容，建议整合到卷二第01章末尾。"Feature Flag 条件编译"和"状态两层架构"建议整合到对应的 v2 深度章节。Java 对比表可移至卷四。 | 部分可删（分层架构图与 v2 重复） |

### 6. part-2-architecture/14-记忆与持久化.md

| 旧文件 | 独有内容（v2缺什么） | 值得合并？→ 目标v2章节 | 冗余可删？ |
|--------|---------------------|----------------------|-----------|
| 14-记忆与持久化.md | **记忆系统完整源码导览**（~660行），v2 卷二第11章覆盖了记忆概念和提取流程，但旧版独有的内容包括：**6层持久化层次结构图**（Transcript/CLAUDE.md/AutoMem/SessionMem/TeamMem/Settings）、**CLAUDE.md 加载流程 6 步详解**（收集路径/解析frontmatter/@include处理/优先级排序/大小检查40K字符限制/Hook触发）、**记忆类型体系 MEMORY_TYPE_VALUES 枚举**（User/Project/Local/Managed/AutoMem/TeamMem）、**会话 JSONL 格式详细说明**（10种消息类型字段）、**TEXT_FILE_EXTENSIONS 白名单**（15种扩展名）、**Session Memory 完整模板**（9个section：Title/CurrentState/TaskSpec/Files/Workflow/Errors/Documentation/Learnings/KeyResults/Worklog）、**Agent transcript 存储路径**（subagents/ + transcriptSubdir）、**Java 缓存对比表**（6维：JSONL/JPA, 记忆类型, @Async, @PropertySource, @Import, 文件锁）。 | **部分值得合并** → "CLAUDE.md 加载流程 6 步详解"和"@include 指令支持"的精确规则是 v2 缺失的工程细节，建议补充到卷二第11章。"Session Memory 完整模板"是实用参考，可保留为附录。Java 对比表移至卷四。 | 部分可删（概念层与 v2 重复） |

### 7. part-2-architecture/15-Skills与插件系统.md

| 旧文件 | 独有内容（v2缺什么） | 值得合并？→ 目标v2章节 | 冗余可删？ |
|--------|---------------------|----------------------|-----------|
| 15-Skills与插件系统.md | **Skills 系统深度源码分析**（~510行），v2 卷三第08章覆盖插件开发，但旧版独有的内容包括：**Skill 四来源架构**（bundled/skills目录/MCP/Plugin）及对应的加载函数映射、**Skill 去重策略的 realpath 原因**（虚拟/容器/NFS文件系统的 inode 不可靠）、**Bundled Skill 惰性提取文件机制**（extractionPromise + extractBundledSkillFiles）、**条件 Skill 动态激活**（paths frontmatter + activateConditionalSkillsForPaths）、**inline vs fork 执行模式对比表**（5维：执行位置/token预算/上下文/场景/权限）、**Plugin 生命周期 6 阶段 Mermaid 图**（安装→settings声明→物化→installed_plugins_v2.json/启用禁用→更新settings+清缓存/更新→下载+版本记录/卸载→删除settings+标记孤儿）、**settings-first 设计原因**（reconciliation 机制）、**原子 Hook 注册**（先 clear 后 register 的原因）、**Skill 来源优先级 6 级表**（bundled>managed>user>project>additional>commands legacy）。 | **部分值得合并** → "Skill 四来源架构"、"去重策略原因"、"inline vs fork 对比表"、"Skill 来源优先级"是理解 Claude Code 扩展系统的关键知识，建议整合到卷三第08章的 Skill 部分。"settings-first 设计原因"和"原子 Hook 注册"的工程决策解释也值得保留。 | 部分可删（Plugin 安装流程与 v2 重复） |

### 8. part-2-architecture/16-API通信与远程.md

| 旧文件 | 独有内容（v2缺什么） | 值得合并？→ 目标v2章节 | 冗余可删？ |
|--------|---------------------|----------------------|-----------|
| 16-API通信与远程.md | **API 通信完整参考**（~420行），v2 卷二第12章深入重试和错误分类，但旧版独有的内容包括：**四种认证方式对比表**（API Key/OAuth/AWS Bedrock/Google Vertex + 配置 + 适用场景）、**OAuth PKCE 完整流程 7 步时序图**（code_verifier → code_challenge → 浏览器授权 → 回调 → token 交换）、**消息标准化 isAPISendable 过滤规则**（progress/context_collapse/compact_boundary 不发送）、**远程会话架构**（RemoteSession/Bridge/Direct Connect 三种模式）、**toolToAPISchema 工具 Schema 转换**、**错误处理策略三分类表**（指数退避/立即失败/静默重试 + 适用场景）、**远程会话 Mermaid 图**（本地CLI→SSH/WebSocket→远程实例→API）、**Java 对比表**（AsyncGenerator/RestTemplate, 消息转换器, Spring Retry, OAuth, RMI/gRPC）。 | **部分值得合并** → "四种认证方式对比表"和"OAuth PKCE 完整流程"是 v2 缺失的重要知识，建议补充到卷二第12章。"消息标准化过滤规则"和"远程会话架构概述"也值得补充。"错误处理策略三分类"与 v2 的错误分类互补。 | 部分可删（重试循环与 v2 重复） |

### 9. part-3-contributor/19-向ClaudeCode贡献代码.md

| 旧文件 | 独有内容（v2缺什么） | 值得合并？→ 目标v2章节 | 冗余可删？ |
|--------|---------------------|----------------------|-----------|
| 19-向ClaudeCode贡献代码.md | **完整的开源贡献教程**（~770行），v2 卷三第11章覆盖 Git 工作流和 PR 流程，但旧版独有的内容包括：**TypeScript 命名规范**（好 vs 坏的变量命名示例）、**函数设计单一职责原则**（对比好的单参数 vs 坏的多option对象）、**自定义错误类层次**（ToolExecutionError/PermissionError/ApiError + Result 类型）、**代码审查 5 要点**（功能正确性/边界/性能/可读性/测试）和**反馈类型 5 标记**（nitpick/suggestion/question/issue/praise + 是否阻塞）、**完整代码审查练习**（DoubleReadTool 代码审查 + 4点审查意见示例）、**架构腐化识别 7 类问题表**（CI/CD/代码审查瓶颈/技术债/文档不一致/依赖管理/Flaky tests/流程不透明）、**技术债详情 5 项深度分析**（每项含：问题描述/源码位置/历史原因/工程代价/未修原因/渐进方案）、**寻找贡献点 4 策略**（good first issue/help wanted/最近关闭PR/gh命令）、**Bun 测试完整示例**（ReadTool 测试套件含 Mock/权限/错误/边界条件 4 组）、**响应审查反馈的 ASCII 流程图**。 | **值得合并** → "架构腐化识别表"和"技术债详情 5 项"是极有价值的工程知识，v2 完全没有。建议整合到卷三第11章末尾作为"项目健康度"一节。"代码审查练习"和"反馈类型标记"也有教学价值，建议保留。"Bun 测试完整示例"可移至卷三的测试章节。 | 部分可删（Fork/PR 流程与 v2 重复） |

### 10. part-3-contributor/20-构建你的第一个插件.md

| 旧文件 | 独有内容（v2缺什么） | 值得合并？→ 目标v2章节 | 冗余可删？ |
|--------|---------------------|----------------------|-----------|
| 20-构建你的第一个插件.md | **插件开发实战教程**（~870行），v2 卷三第08章覆盖插件结构，但旧版独有的内容包括：**Hook 事件的完整列表**（28种 HookEvent：PreToolUse/PostToolUse/SessionStart/Stop/PreCompact/SubagentStart/Elicitation/ConfigChange/WorktreeCreate 等），v2 只列了 4 种；**4 种 HookCommand 类型详解**（command/prompt/agent/http + 各自参数），v2 未展开；**架构腐化识别 7 项**（插件隔离不完整/版本兼容缺失/状态清理不完整/Hook 注册竞争/配置不一致/生命周期 Hook 不标准/命名错误）；**技术债详情 5 项**（插件组件加载错误隔离/版本兼容机制/卸载后状态残留/配置验证缺失/Hook Matcher 过于简单）；**完整 Git Toolkit 插件实现**（ConfigTool + hooks 实现 + npm 发布流程 + pre-publish 检查清单脚本）；**插件设计 4 原则**（单一职责/幂等性/错误隔离/版本兼容）；**本地测试两种方式**（npm link / --add-dir）。 | **部分值得合并** → "28 种 Hook 事件完整列表"和"4 种 HookCommand 类型详解"是 v2 缺失的重要参考，建议补充到卷三第08章。"架构腐化识别"和"技术债详情"与旧版第19章互补，建议合并后放在卷三。"插件设计 4 原则"值得保留。 | 部分可删（插件目录结构/生命周期与 v2 重复） |

### 11. part-4-advanced/21-TypeScript实战对比.md

| 旧文件 | 独有内容（v2缺什么） | 值得合并？→ 目标v2章节 | 冗余可删？ |
|--------|---------------------|----------------------|-----------|
| 21-TypeScript实战对比.md | **TypeScript vs Java 架构对比深度分析**（~500行），v2 卷四第01章讨论"为什么选 TS"但不做语言对比。旧版独有的内容包括：**结构化类型 vs 标称类型 Mermaid 对比图**、**buildTool 工厂模式与 Spring FactoryBean 代码对比**、**createSignal 15行实现与 Java Flow.Subscriber 代码对比**、**runToolUse AsyncGenerator 与 CompletableFuture 链式代码对比**、**PermissionMode 5 种模式决策图 vs Java SecurityManager**、**TOOL_DEFAULTS 默认值填充机制**、**Signal 为什么只需 15 行的解释**（CLI 单线程/无背压/无多线程发布订阅）、**4 项常见坑对比**（类型推断/内存泄漏/异步错误/泛型约束）、**设计模式映射总表**（8对：buildTool/FactoryBean, 胖接口/Command, Signal/Flow, AsyncGenerator/CompletableFuture, getAppState/ServiceLocator, Map+LRU/@Cacheable, Zod/Hibernate Validator, PermissionModes/SecurityManager）。 | **值得合并** → 整个文件的核心价值是"设计模式映射总表"和 3 组代码对比。v2 卷四完全缺少 Java 视角。建议将"设计模式映射总表"和核心代码对比整合到卷四第01章末尾，或作为卷四的独立附录。 | 否 |

### 12. appendix/A1-TypeScript实战技巧.md

| 旧文件 | 独有内容（v2缺什么） | 值得合并？→ 目标v2章节 | 冗余可删？ |
|--------|---------------------|----------------------|-----------|
| A1-TypeScript实战技巧.md | **TS 高级类型模式手册**（~800行），覆盖：Branded Types（标称类型模拟）、Discriminated Unions（可辨识联合 + 穷尽检查）、Const Assertions、条件类型（infer/ElementType/Awaited/Parameters）、映射类型（键重映射 Getters）、递归类型（DeepReadonly/JSON/TreeNode）、ESM vs CommonJS、路径别名 @/、动态导入、Result 类型模式、自定义错误类层次、方法装饰器（memoize/log）、类型守卫（is/asserts）、工具类型速查（12种）、declare module 扩展、as const satisfies 模式、**完整 TypedEventEmitter 实现**（~130行代码 + once/off/emit/removeAllListeners）、**完整 DeepPartial/DeepRequired/DeepReadonly/DeepMutable 实现**、PickByValue/OmitByValue/RequiredKeys/OptionalKeys 工具类型。v2 无等效内容。 | **值得合并** → "Branded Types"、"Discriminated Unions"、"TypedEventEmitter 完整实现"、"DeepPartial 系列"是高质量的教学材料。建议压缩后作为卷四的"TypeScript 高级模式速查"附录。 | 否 |

### 13. appendix/A13-TypeScript实战.md

| 旧文件 | 独有内容（v2缺什么） | 值得合并？→ 目标v2章节 | 冗余可删？ |
|--------|---------------------|----------------------|-----------|
| A13-TypeScript实战.md | **Java→TypeScript 迁移手册**（~1050行），覆盖：类/接口/泛型/访问修饰符的 Java vs TS 代码对比（每对都有 TS + Java 双代码块）、Zod Schema 实战（替代 Jakarta Validation：基础 schema/运行时验证/z.infer/transform 预处理）、AsyncGenerator 分页流 vs Java Flux 对比、Promise.all/Promise.allSettled、AbortController 取消、条件导入（Feature Flag bun:bundle）、循环依赖处理 3 方案对比、条件类型/映射类型/模板字面量类型、Result 类型模式、自定义 AppError 层次 + 错误工厂、TypeScript 装饰器（类/方法）vs Java 注解对比、reflect-metadata 元编程、CLI 工具完整项目结构、Vitest 配置和单元测试/Mock 示例、性能优化（memoize/分批处理/订阅清理）、**迁移检查清单总表**（10维 Java→TS 对应关系）。与 A1 有 ~30% 内容重叠。 | **部分值得合并** → "Zod Schema 实战"（v2 卷四第01章提到 Zod 但不教用法）和"Vitest 测试示例"（v2 缺少测试教学）值得提取。Java 对比代码块可合并到旧版第21章后统一移入卷四。"迁移检查清单总表"也值得保留。 | 部分可删（与 A1 重叠的泛型/条件类型/映射类型部分） |

### 14. appendix/A3-常用命令速查表.md

| 旧文件 | 独有内容（v2缺什么） | 值得合并？→ 目标v2章节 | 冗余可删？ |
|--------|---------------------|----------------------|-----------|
| A3-常用命令速查表.md | **开发命令参考**（~450行），覆盖：npm/bun 安装/构建/测试命令、Claude Code CLI 命令（基本用法/工具调用/MCP服务器/Permission 相关）、Git 工作流（分支/提交规范/PR）、调试命令（verbose/性能分析/内存调试）、代码质量（lint/format）、依赖管理、文件操作、Docker 容器、发布相关、REPL 内命令（/exit/help/theme/clear/compact/skills）、环境变量速查表（8个）、常见错误代码（6个）、快速参考卡片（开发/调试流程）。 | **可保留为附录** → 作为快速参考卡片有价值，但内容泛泛（大部分是通用 npm/git 知识，不是 Claude Code 特有的）。建议大幅精简，只保留"Claude Code CLI 命令"、"REPL 内命令"和"环境变量速查"三部分，其余删去。 | 大部分可删（通用命令无需保留） |

### 15. appendix/A2-代码附录.md

| 旧文件 | 独有内容（v2缺什么） | 值得合并？→ 目标v2章节 | 冗余可删？ |
|--------|---------------------|----------------------|-----------|
| A2-代码附录.md | **核心源码接口签名速查**（~530行），覆盖：Tool 接口定义、工具注册表函数签名、工具执行函数签名、权限模式枚举、权限结果接口、规则引擎类、拒绝追踪器、消息类型（UserMessage/AssistantMessage/ToolResultMessage）、压缩策略接口和枚举、Token 计算函数、MCP 连接配置类型、Agent 任务类型（Local/InProcessTeammate/Remote）、API 消息流函数签名、重试选项接口、OAuth 函数签名、Skills 加载函数、Bundled Skills 函数、Plugin 操作函数、Hook 加载函数、会话状态接口、ContentBlock/ToolCall/Usage/Error 数据结构、**文件路径映射表**（17个核心源码路径）。 | **可保留为附录** → "文件路径映射表"和"核心数据结构速查"（ContentBlock/ToolCall/Usage）有参考价值。但大量接口签名已在 v2 各章节中内联展示，且部分内容（如 RuleEngine、DenialTracker）可能是简化的伪代码而非真实源码。建议仅保留"文件路径映射表"和"数据结构速查"，其余删去。 | 大部分可删（接口签名已在 v2 各章节展示） |

---

## 优先级排序：最值得合并的独有内容

### 高优先级（v2 明确缺失且读者需要）

1. **TypeScript 基础速成**（P1）—— v2 无任何 TS 教学，读者需要前置知识
2. **28 种 Hook 事件完整列表 + 4 种 HookCommand 类型**（20）—— v2 只列了 4 种 Hook，这是插件开发的核心参考
3. **Mini-Claude 到 Claude Code 组件映射表**（05）—— v2 缺少 Part 1 到 Part 2 的桥梁
4. **架构腐化识别 + 技术债详情**（19 + 20）—— v2 无工程健康度分析视角
5. **四种认证方式对比 + OAuth PKCE 流程**（16）—— v2 不覆盖认证

### 中优先级（有独立价值但可后续处理）

6. **TypeScript vs Java 设计模式映射总表**（21）—— Java 背景读者的关键桥梁
7. **Branded Types / Discriminated Unions / TypedEventEmitter**（A1）—— 高级 TS 模式参考
8. **Skill 四来源架构 + inline vs fork 对比**（15）—— 理解扩展系统的关键知识
9. **CLAUDE.md 加载 6 步详解 + @include 规则**（14）—— 工程细节
10. **Zod Schema 实战教学**（A13）—— v2 提到 Zod 但不教用法

### 低优先级（参考价值但非必需）

11. Node.js/Bun 运行时教程（P2）
12. CLI 开发教程（P3）
13. Vitest 测试教学（A13）
14. 命令速查表精简版（A3）
15. 文件路径映射表（A2）

---

## 建议合并策略

| 目标 v2 位置 | 应合并的旧内容 | 合并方式 |
|-------------|--------------|---------|
| 卷四 新增"附录A：TypeScript 速成" | P1 全文 + A1 精华（Branded Types/Discriminated Unions/TypedEventEmitter） | 压缩 P1 保留教学骨架，A1 提取高级模式单独成节 |
| 卷四 新增"附录B：Java→TypeScript 迁移指南" | 第21章映射总表 + A13 Zod 实战 + 迁移检查清单 | 合并为一份面向 Java 读者的迁移附录 |
| 卷三第08章 补充 | 旧版20的 Hook 事件完整列表 + HookCommand 类型 + Skill 四来源 + inline/fork 对比 | 直接插入 v2 第08章对应位置 |
| 卷三第11章 补充 | 旧版19的架构腐化识别 + 技术债详情 + 代码审查练习 | 新增"项目健康度"和"代码审查实战"两节 |
| 卷二第01章 补充 | 旧版05的 Mini-Claude 映射表 + 核心差距分析表 | 插入第01章末尾作为"从 Part 1 过渡"桥接内容 |
| 卷二第11章 补充 | 旧版14的 CLAUDE.md 加载 6 步 + @include 规则 + Session Memory 模板 | 补充工程细节到 v2 的概念层内容后 |
| 卷二第12章 补充 | 旧版16的认证方式对比 + OAuth PKCE 流程 + 远程会话架构 | 新增"认证"和"远程会话"两节 |
| 全书末尾 新增"附录C：命令速查" | A3 精简版（仅 Claude Code CLI + REPL 命令 + 环境变量） | 大幅精简后保留 |
| 全书末尾 新增"附录D：核心源码路径" | A2 的文件路径映射表 + 数据结构速查 | 仅保留这两个表 |
