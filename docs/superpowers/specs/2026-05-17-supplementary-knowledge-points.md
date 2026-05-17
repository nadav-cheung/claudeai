# 《跟着消息走》补充知识点设计

> **状态**: 待实施
> **日期**: 2026-05-17
> **背景**: 网络专家会审发现全书 66 章在 Token 经济学、网络深度、AI 评估、可观测性、安全纵深、Streaming Backpressure、CI/CD 配置管理、多模态等维度存在知识盲区
> **实施策略**: 按优先级分批补充，优先 Critical/High，尽量扩展现有章节而非新增

---

## 补充策略

| 优先级 | 模块 | 实施方式 | 原因 |
|--------|------|---------|------|
| Critical | Token 经济学 | **新章（卷四 ch52.5）** | 内容独立，不适合塞入现有章 |
| High | 网络深度 | **扩展 ch53** | 位于卷五起点，天然网络相关 |
| High | AI 评估 | **新附录 G** | 跨卷知识，不适合插入某一卷 |
| High | 可观测性 | **扩展 ch38** | 卷三调试，天然可观测性相关 |
| Medium | 安全纵深 | **扩展 ch51** | 卷四安全章，自然延伸 |
| Medium | Streaming Backpressure | **扩展 ch55** | 卷五流式解析章，自然延伸 |
| Medium | CI/CD 配置管理 | **扩展 ch66 或新附录** | 卷五框架终章，发布后自然需要 CI |
| Low | 多模态深度 | **扩展 ch04** | 卷一输入处理章 |

---

## 1. [Critical] Token 经济学与成本优化 — 新章 ch52.5

### 1.1 定位

插入卷四末尾（ch52 之后、卷五之前），作为从"分析别人"到"自己构建"的桥梁。读者已理解架构，即将开始卷五的框架实现，此时理解 token 经济学能让他们在卷五做出更好的设计决策。

### 1.2 章节结构

```
# 第 52.5 章：Token 经济学 — 每一个 Token 都在燃烧预算

> 你已经理解了 Claude Code 的全部架构。但在动手实现之前，
> 有一个贯穿全书却被我们刻意回避的底层约束：Token 不是免费的。

## 路线图（卷四→卷五的桥）

## 一、Token 怎么计数

### 1.1 Tokenizer 的原理
- BPE (Byte Pair Encoding) 的核心算法
- 为什么 "hello" 是 1 个 token，但 "Claude" 可能是 2 个
- 不同模型的 tokenizer 差异对照表（Claude vs GPT-4 vs Gemini）
- Claude 的 tokenizer 特点：代码语言的压缩比

### 1.2 不调用 API 如何估算 Token 数
- 经验公式：英文 ~4 chars/token，中文 ~1.5 chars/token
- tiktoken 库的使用与局限
- Claude Code 源码中的 token 估算逻辑
- 自建最简 token counter（代码示例）

### 1.3 Conversation 中的 Token 分布解剖
- 用一次真实 Agent 会话分析 token 分布：
  system prompt (20-30%) + tools (15-25%) + conversation (40-50%) + thinking (10-30%)
- 饼图展示每种 token 的成本占比
- 不同任务类型的分布差异（简单问答 vs 大重构）

## 二、Prompt Caching 的经济学

### 2.1 缓存的盈利模型
- Cache write: 1.25× 输入价格
- Cache read: 0.10× 输入价格
- 盈亏平衡点：同一缓存需命中 ≥ 2 次

### 2.2 缓存命中率分析
- 什么样的 system prompt 缓存命中率高
- SYSTEM_PROMPT_DYNAMIC_BOUNDARY 的经济意图
- 动态部分 vs 静态部分的 token 比例
- 工具定义的缓存策略（工具变了缓存就失效）

### 2.3 缓存预热 (Cache Warming)
- 发送 `max_tokens: 0` 的请求预热缓存
- 什么时候值得预热（长对话的第一轮）
- 预热的成本 vs 收益

## 三、模型选择的决策树

### 3.1 三级模型的经济学分工
- Opus: 每 1M token ~$15 (输入) / $75 (输出) — 何时用？
- Sonnet: 每 1M token ~$3 / $15 — 默认选择
- Haiku: 每 1M token ~$0.80 / $4 — 何时用？

### 3.2 自动降级策略
- 什么场景可以用 Haiku 代替 Sonnet？
  - 文件分类、简单摘要、工具参数预填充
- 什么场景必须用 Opus？
  - 复杂重构、安全审查、多文件分析

### 3.3 实际成本归因
- 一次典型会话的成本拆解（真实数据）
- 子 Agent 的经济学：fork 的 token 成本
- Compaction 的性价比：压缩消耗的 token vs 释放的 token

## 四、Thinking 的成本
- thinking token 与普通 output token 的价格差异
- budget_tokens 的最佳值：太多浪费，太少没用
- adaptive thinking 的经济学
- 什么时候不需要 thinking（简单任务关闭 thinking 省钱）

## 五、成本监控与告警

### 5.1 Claude Code 的 cost-tracker 实现
- src/cost-tracker.ts 源码走读
- usage 字段的实时追踪
- 会话级和项目级的成本汇总

### 5.2 成本告警
- 单次调用 token 超标告警
- 会话累计成本告警
- 成本上限自动停止

## 六、卷五的经济学预设
- 你在卷五要构建的 Agent 框架如何内置成本控制
- 给框架用户的成本最佳实践建议
```

### 1.3 代码示例类型
- 最简 token count estimator (~15 行)
- Cache hit rate 计算器 (~30 行)
- 成本追踪器（CostTracker 极简实现，~40 行）
- 模型选择决策树函数 (~20 行)

---

## 2. [High] 网络深度 — 扩展 ch53

### 2.1 扩展方式

在现有 ch53（一个 HTTP 请求之外）中新增 2 节，不改变现有结构。

### 2.2 新增节

```
## 第 N 节：不只是 POST — HTTP 的隐藏细节

### N.1 HTTP/2 多路复用
- Messages API 默认使用 HTTP/2
- 多路复用的含义：一个连接承载多个并发请求
- 对 Agent 的意义：多个 SubAgent 同时调 API 时共享连接
- fetch() 在 Node.js 中如何处理 HTTP/2（自动协商）

### N.2 TLS 1.3 握手
- 每次 API 调用的 TLS 开销：~1-2 RTT
- Session Resumption / TLS False Start
- 企业环境中的自定义 CA 证书
- NODE_EXTRA_CA_CERTS 环境变量
- 代码：如何配置自定义 CA

### N.3 企业代理穿透
- HTTP_PROXY / HTTPS_PROXY / NO_PROXY 的完整语义
- 代码：ApiClient 支持代理
- Agent 隧道 vs HTTP 隧道
- 常见代理故障排查

## 第 N+1 节：当网络不可靠 — 重试与韧性

### N+1.1 指数退避 (Exponential Backoff)
- 为什么退避因子选 2 而不是随机值
- Jitter 的作用（避免惊群效应）
- 代码：最简指数退避实现 (~15 行)
- 最大重试次数和最大等待时间

### N+1.2 可重试 vs 不可重试错误
- 429 (Rate Limit) / 529 (Overloaded) / 5xx → 可重试
- 400 / 401 / 403 → 不可重试（重试也不会成功）
- 幂等性保证
- Claude Code 的 withRetry 实现走读

### N+1.3 速率限制 (Rate Limiting)
- Anthropic API 的 RPM/TPM 限制
- 如何从响应头读取剩余配额
- 代码：RateLimiter 的令牌桶实现 (~25 行)
- 企业 Tier 的速率限制差异

### N+1.4 DNS 与连接池
- Node.js 的默认 DNS TTL 行为
- 连接池耗尽的现象和排查
- undici http agent 的连接池参数
```

---

## 3. [High] AI 评估与 Agent Benchmarking — 新附录 G

### 3.1 定位

作为全书最后一个附录（在附录 F 形式化分析之后），因为评估需要全书知识做基础。

### 3.2 附录结构

```
# 附录 G：Agent 评估 — 你怎么知道你的 Agent 够好了

> 摘要：卷五结束后你有了自己的 Agent 框架。但你怎么知道它
> 比别人的好、比上一个版本好？本附录提供 Agent 评估的完整框架。

## G.1 评估的四个维度

| 维度 | 度量 | 什么算好 |
|------|------|---------|
| 任务完成率 | 成功完成 / 总任务数 | > 80% 的简单任务、> 60% 的复杂任务 |
| 效率 | 完成任务消耗的 token 数 | 同任务下 token 越低越好 |
| 安全性 | 危险操作被阻止的比率 | 100% 阻止、0% 误报率不可兼得 |
| 可靠性 | 相同输入得到相同正确结果的比率 | 越高越好（需要非零 temperature） |

## G.2 基准数据集

### G.2.1 代码任务基准
- SWE-bench Verified：真实 GitHub issue 修复
- HumanEval / MBPP：函数级代码生成
- LiveCodeBench：实时更新的编程题

### G.2.2 Agent 任务基准
- SWE-bench Multimodal：含 UI 截图的 bug 修复
- WebArena：网页交互任务
- GAIA：通用 Agent 任务

### G.2.3 如何自建评估集
- 从 GitHub Issues 中提取
- 从项目历史 bug 中构建
- 评估集的最小规模：≥ 20 个任务

## G.3 工具调用评估

### G.3.1 工具选择准确率
- 给定 N 个场景描述，判断 Agent 是否选择了正确工具
- 构造正例和负例

### G.3.2 参数准确性
- 工具调用的参数是否正确
- 部分匹配的评分策略

### G.3.3 工具链正确性
- 多步工具调用的顺序是否正确
- 读→分析→修改→测试 的顺序验证

## G.4 评估流水线

### G.4.1 自动化评估脚本
- 输入：评估任务集（JSON）
- 输出：成功/失败 + token 消耗 + 时间
- 代码：最简评估 runner (~30 行)

### G.4.2 回归检测
- 每次修改 system prompt 或工具定义后跑评估
- 和 baseline 对比
- 回归阈值：任务完成率下降 > 5% 则回退

### G.4.3 CI 集成
- 在 CI 中运行轻量评估（~5 个核心任务）
- 完整评估在 nightly build 中运行
- 成本控制：评估的 token 预算

## G.5 Agent 间对比方法

### G.5.1 控制的变量
- 相同的任务集
- 相同的工具集
- 相同的模型
- 不同的 system prompt / Skill / Agent 架构

### G.5.2 对比报告模板
- 任务完成率对比表
- Token 效率对比（token/task）
- 时间效率对比（seconds/task）
- 错误类型分布

## G.6 Claude Code 的自我评估
- 如何在 Claude Code 中使用评估思维
- 用 Claude 评估 Claude 的可行性
- LLM-as-Judge 的陷阱
```

---

## 4. [High] 可观测性与分布式追踪 — 扩展 ch38

### 4.1 扩展方式

ch38（调试的艺术）位于卷三，当前偏向个人调试（断点、console.log）。新增 2 节覆盖可观测性。

### 4.2 新增节

```
## 第 N 节：不只是 console.log — 结构化可观测性

### N.1 结构化日志
- 为什么 console.log 不够（不可搜索、不可聚合、无上下文）
- JSON Lines 格式
- 每条日志的最小字段：timestamp, level, sessionId, message, context
- 代码：结构化 Logger 实现 (~25 行)

### N.2 分布式追踪基础
- Span：一次操作的开始和结束
- Trace：多个 Span 的树状结构
- 在 Agent Loop 中埋 Span：
  turn_start → api_call → tool_execute → tool_result → turn_end

### N.3 OpenTelemetry 入门
- Claude Code 中 OTel 的使用（src/services/analytics/）
- 最简 OTel 集成示例 (~20 行)
- Exporters：Console / OTLP / Jaeger

## 第 N+1 节：Agent 专属监控面板

### N+1.1 核心指标
- Turn Count：平均几轮完成一个任务
- Token / Turn：每轮消耗多少 token
- Tool Latency：每种工具的平均执行时间
- Error Rate：工具调用失败率
- Cache Hit Rate：prompt cache 命中率
- Cost / Task：完成一个任务的平均成本

### N+1.2 仪表盘设计
- 实时 vs 汇总
- 单会话切片 vs 全量聚合
- 异常检测：当某个指标偏离基线 2σ 时告警

### N+1.3 代码：最简指标收集器
- Counter, Histogram, Gauge 的实现 (~30 行)
- 如何不侵入业务代码地收集指标
```

---

## 5. [Medium] 安全纵深补充 — 扩展 ch51

### 5.1 扩展方式

ch51（安全的纵深防御）位于卷四，已覆盖权限模型和安全设计。新增 2 节覆盖工程安全。

### 5.2 新增节

```
## 第 N 节：供给链安全

### N.1 npm 依赖的信任模型
- 一个 npm install 到底装了多少代码
- 依赖树中的权限：postinstall 脚本可以做什么
- --ignore-scripts 的作用和代价
- package-lock.json / bun.lock 的完整性校验

### N.2 自建依赖审查
- npm audit 的局限
- 审查新增依赖的清单：
  - 维护者是谁
  - 最近更新时间
  - 下载量和社区反馈
  - 是否有 native addon

## 第 N+1 节：Prompt Injection 防御

### N+1.1 间接注入的攻击向量
- 工具结果中包含恶意指令
- 用户文件变成攻击载体（README 里藏着 prompt injection）
- 多轮对话中的污染传播

### N+1.2 防御分层
- L1：输入过滤（检测已知注入模式）
- L2：输出分割（system prompt 中的不可逾越边界）
- L3：权限阻断（敏感操作必须用户确认）
- L4：能力限制（Agent 能做的事越少，被注入后的危害越小）

### N+1.3 Secret 泄露防护
- 工具输出中意外包含 API key 的检测
- 正则匹配常见 secret 格式
- 自动脱敏（替换为 [REDACTED]）
- Claude Code 中的实现参考

### N+1.4 MCP Server 安全审计
- 连接第三方 MCP Server 的风险
- 审计清单：
  - Server 能访问什么文件/网络
  - Server 是否修改工具列表
  - Server 的日志是否泄露数据
- 沙箱化 MCP Server（Docker/进程隔离）
```

---

## 6. [Medium] Streaming Backpressure — 扩展 ch55

### 6.1 扩展方式

ch55（文字如溪流）讲 SSE 解析和 StreamParser 实现。新增 1 节覆盖工程实践。

### 6.2 新增节

```
## 第 N 节：当溪流比处理快 — Backpressure 与断线恢复

### N.1 Backpressure 问题
- 场景：模型以 100 token/s 出字，但工具执行需要 3 秒
- 在 Agent Loop 中，流不会被积压因为每轮是串行的
- 但如果做了 pre-fetch / 预测性工具调用，需要 backpressure

### N.2 AsyncGenerator 的天然 Backpressure
- for await...of 自动在每次 yield 后暂停
- 消费者慢时，生成者自然被阻塞
- 代码：带手动 backpressure 的流消费者

### N.3 SSE 断线处理
- 网络中断时 SSE 连接断开
- EventSource 的自动重连（Last-Event-Id）
- 手动 fetch + ReadableStream 的重连策略
- 重连后如何恢复（从上次成功消费的 content block 继续）

### N.4 流式传输中的错误边界
- 流中间出现 JSON 解析错误
- 部分消费策略：能用的部分先用
- 放弃策略：完整丢弃当前响应，重试
- Claude Code 中的处理方式（src/services/api/claude.ts 走读）
```

---

## 7. [Medium] CI/CD 与 Agent 配置管理

### 7.1 定位

放在卷五的扩展内容中，或者作为 ch66 的补充节，或者放在框架发布示例之后。

### 7.2 建议结构（扩展 ch66 的"框架发布"节，或新附录 H）

```
## 附录 H：Agent 框架的 CI/CD 与配置管理

### H.1 版本策略

#### H.1.1 什么需要版本管理
- Agent 框架代码：semver
- System Prompt：内容 hash
- 工具定义：schema hash
- Skill 定义：YAML + git
- 配置文件：分环境管理

#### H.1.2 配置回退机制
- 新版本配置上线后出问题如何快速回滚
- 配置版本与框架版本的兼容矩阵

### H.2 CI 流水线设计

#### H.2.1 轻量 CI（每次 PR）
- TypeScript 编译（tsc --noEmit）
- Lint（ESLint / biome）
- 单元测试（vitest）
- 类型检查
- 预计耗时：< 2 分钟

#### H.2.2 完整 CI（合并到 main 时）
- 以上全部 +
- 集成测试（真实 API 调用，需 API key）
- E2E 测试（完整 Agent 任务执行）
- 预计耗时：5-10 分钟

#### H.2.3 示例：GitHub Actions 配置
- 完整的 .github/workflows/ci.yml 示例

### H.3 金丝雀发布与 A/B 测试

#### H.3.1 System Prompt 的 A/B 测试
- 随机分流到 A/B 两组
- 对比任务完成率、token 效率
- 达到统计显著性（p < 0.05）再全量切换

#### H.3.2 工具定义的金丝雀发布
- 新工具先给 5% 用户使用
- 监控错误率和用户反馈
- 逐步放量：5% → 25% → 100%

### H.4 监控与回滚
- 关键指标仪表盘（从附录 H.1 可观测性引入数据）
- 自动回滚条件（错误率 > X% 持续 Y 分钟）
- 配置回滚的操作方式（git revert + 重新部署）
```

---

## 8. [Low] 多模态深度 — 扩展 ch04

### 8.1 扩展方式

ch04（回车键之后）的 4.8 节已涉及附件系统和图片粘贴。新增 1 节深度展开。

### 8.2 新增节

```
## 第 4.N 节：当消息不仅有文字 — 多模态输入深度

### 4.N.1 Vision 的工作原理
- Claude 的视觉能力：截图、图表、PDF
- image content block 的结构：
  { type: "image", source: { type: "base64", media_type: "image/png", data: "..." } }
- 图片如何消耗 token（分辨率 → token 数映射表）
- 图片 token 比文字 token 贵多少

### 4.N.2 图片预处理
- Claude Code 的图片大小调整逻辑（maybeResizeAndDownsampleImageBlock）
- 为什么要调整：原始截图可能 4K → 大量 token
- 压缩阈值和策略：1024px 宽、JPEG 质量 85%
- 代码：最简图片压缩器 (~15 行)

### 4.N.3 PDF 处理
- PDF 作为多页图片序列 vs 提取文本
- Claude Code 的 PDF 阅读策略
- 大 PDF 的分页读取（Read 工具中 pages 参数的实现）

### 4.N.4 语音输入
- src/voice/ 目录的结构
- 语音 → 文本的流程
- Whisper API 或其他 STT 方案

### 4.N.5 多模态的未来
- 视频理解（逐帧分析）
- 实时屏幕共享 + Agent 指导
- 音频输出（TTS）
```

---

## 9. 实施优先级与工作量估算

| 序号 | 模块 | 工作量 | 依赖 | 建议顺序 |
|------|------|--------|------|---------|
| 1 | Token 经济学（ch52.5） | 新章 500 行 | 卷四完成 | 1st |
| 2 | 网络深度（ch53 扩展） | +2 节 250 行 | ch53 存在 | 2nd |
| 3 | AI 评估（附录 G） | 新附录 400 行 | 卷五完成 | 3rd（读者需要先能构建 Agent） |
| 4 | 可观测性（ch38 扩展） | +2 节 200 行 | ch38 存在 | 4th |
| 5 | 安全纵深（ch51 扩展） | +2 节 250 行 | ch51 存在 | 5th |
| 6 | Backpressure（ch55 扩展） | +1 节 120 行 | ch55 存在 | 6th |
| 7 | CI/CD + 配置管理（附录 H） | 新附录 350 行 | 卷五完成 | 7th |
| 8 | 多模态（ch04 扩展） | +1 节 150 行 | ch04 存在 | 8th |

总计新增：约 **2 章 + 2 附录 + 8 扩展节**，约 **2,000-2,500 行**，约 **1.5-2.5 万字**。

---

## 10. 与现有章节的整合

```
卷零（ch01-02）
  └── 无变更

卷一（ch03-16）
  └── ch04 扩展：多模态深度 (+1 节)

卷二（ch17-28）
  └── 无变更

卷三（ch29-40）
  └── ch38 扩展：可观测性与分布式追踪 (+2 节)

卷四（ch41-52）
  ├── ch51 扩展：供给链安全 + Prompt Injection 防御 (+2 节)
  └── ch52.5 新增：Token 经济学与成本优化 (新章)

卷五（ch53-66）
  ├── ch53 扩展：网络深度 (+2 节)
  ├── ch55 扩展：Backpressure (+1 节)
  └── ch66 扩展后 → 附录 H：CI/CD 与配置管理

附录
  ├── 附录 G 新增：Agent 评估与 Benchmarking
  └── 附录 H 新增：Agent 框架的 CI/CD 与配置管理
```

---

**文档版本**: 1.0
**创建日期**: 2026-05-17
**状态**: 待实施
