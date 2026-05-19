# 第 13 章：RAG 检索增强生成

> **本章目标**：构建完整的 RAG（Retrieval-Augmented Generation）系统，掌握从文档摄入、分块策略、嵌入模型选择、向量数据库集成到多种检索策略（稀疏/稠密/混合）的全链路实现。深入理解 Agentic RAG、Graph RAG 等高级模式。使用 Claude-as-Judge 方法论系统化评估 RAG 输出质量。完成本章后，你将拥有一个可投入生产使用的、不依赖特定厂商的 RAG 管线。

---

## 13.1 概念全景

### RAG 在 Anthropic 生态系统中的位置

检索增强生成（RAG）是连接大语言模型与外部知识的关键技术范式。在 Anthropic 生态中，RAG 扮演着特别重要的角色，原因有三：

**1. Claude 没有原生嵌入模型。** 与 OpenAI（提供 text-embedding-3 系列）和 Cohere（提供 Embed 系列）不同，Anthropic 的战略是不提供自有嵌入模型。这意味着每个基于 Claude 构建的 RAG 系统都必须集成第三方嵌入提供商。这不是限制，而是设计选择——它促使生态中的嵌入模型保持竞争和创新。本章将详细对比主流嵌入模型及其与 Claude 配合的最佳实践。

**2. RAG 是"上下文工程"的核心。** Claude 的强大之处在于其指令遵循和推理能力。RAG 的本质不是"让模型更聪明"，而是"给模型正确的上下文"。将 RAG 理解为上下文工程（Context Engineering）——如何从海量数据中精准提取与用户意图最相关的信息，并以最优格式注入 Claude 的上下文窗口——是本章的核心视角。

**3. Claude-as-Judge 使 RAG 评估可工程化。** 传统 RAG 评估依赖人工标注或粗糙的字符串匹配指标（ROUGE、BLEU）。Claude 的强指令遵循能力使其成为优秀的"评估法官"——能够以接近人类的一致性和细粒度，评估 RAG 输出的忠实性（Faithfulness）、相关性（Relevance）和完整性（Completeness）。

### RAG 技术演进路线

从 2023 年到 2026 年，RAG 技术经历了五代演进：

| 代际 | 名称 | 时期 | 检索方式 | 准确率 | 核心特征 |
|------|------|------|----------|--------|----------|
| 1.0 | Naive RAG | 2022-2023 | 单向量搜索（TF-IDF/BM25） | 60-70% | 简单分块 + 关键词检索 + 直接拼接 |
| 2.0 | Advanced RAG | 2023-2024 | 混合检索 + 重排序 | 80-85% | 稠密向量 + 语义分块 + 重排序管道 |
| 3.0 | Agentic RAG | 2024-2025 | 多 Agent 并行检索 | 90%+ | 查询路由 + 工具调用 + 自反思 |
| 4.0 | Graph RAG | 2025 | 向量 + 图结构 | 92%+ | 知识图谱 + 多跳推理 + 实体关系 |
| 5.0 | Self-Evolving RAG | 2026 | 自主学习进化 | 95%+ | 动态知识更新 + 多模态融合 + 持续学习 |

**关键洞察**：2026 年的 RAG 不再是简单的"检索 + 生成"，而是融合了 Agent 自主决策、知识图谱结构化理解和持续自我进化的智能系统。但无论范式如何演进，核心管道——分块、嵌入、检索、生成——始终是基础。本章将从基础管道出发，逐步构建到 Agentic RAG。

### 本章学习成果

完成本章的学习和编码练习后，你将能够：

1. 设计并实现完整的 RAG 管线：文档摄入、分块、嵌入、索引、检索、生成。
2. 理解和对比主流嵌入模型（OpenAI、Voyage、Cohere、BGE-M3）的适用场景。
3. 实现三种检索策略（BM25 稀疏检索、稠密向量检索、RRF 混合检索）并理解各自优劣。
4. 使用 Claude-as-Judge 对 RAG 输出进行忠实性、相关性和完整性的三维度量化评估。
5. 理解并实现 Agentic RAG 模式——Agent 驱动的自主检索决策。

---

## 13.2 协议规范逐层拆解

### 13.2.1 文档处理管道

RAG 管线的入口是文档处理。原始文档（PDF、Markdown、HTML、纯文本）需要经过解析、清洗和元数据提取三个阶段。

**解析（Parse）**

文档解析的目标是将各种格式统一为纯文本。对于 PDF，常用工具包括 PyMuPDF（Python）和 pdf-parse（Node.js）。HTML 可使用 BeautifulSoup 或 cheerio 提取正文。关键原则是保留文档结构信息——段落边界、标题层级、列表结构——这些信息在后续的分块和检索中影响巨大。

**清洗（Clean）**

现实世界的文档充斥着噪音：页眉页脚、页码、广告、水印、特殊字符。清洗策略包括：
- 正则表达式移除重复的页眉/页脚模式
- Unicode 规范化（NFC/NFKC）
- 移除控制字符和零宽字符
- 保留有意义的空白（段落分隔）但压缩多余空白

**元数据提取（Metadata Extraction）**

元数据是检索质量的倍增器。好的元数据允许在检索时进行过滤和加权。至少应提取：
- 文档标题
- 来源/路径
- 创建/修改时间
- 文档类型
- 章节/段落编号
- 自定义标签

### 13.2.2 分块策略

分块（Chunking）是 RAG 管线中最被低估但影响最大的环节。分块太大，检索精度下降，Claude 上下文被无关信息占据。分块太小，语义碎片化，丢失上下文连贯性。

以下是四种主流分块策略的对比：

| 策略 | 原理 | 优点 | 缺点 | 适用场景 |
|------|------|------|------|----------|
| **固定大小** | 按字符/token 数等距切分 | 简单、可预测、向量均匀 | 语义截断、信息碎片化 | 初版原型、均匀结构文档 |
| **语义分块** | 按自然边界（段落、句子）递归切分 | 保留语义完整性 | 块大小不均、边界判断复杂 | 文章、文档、对话记录 |
| **递归分块** | 按分隔符优先级（`\n\n` → `\n` → `.` → ` `）递进 | 平衡大小和语义 | 计算开销略高 | 通用场景、混合格式 |
| **Agentic 分块** | 由 LLM 或 Agent 判断最佳切分点 | 语义最准确、可处理复杂结构 | 成本高、延迟大 | 高价值知识库、结构化文档 |

**Agentic Chunking 详解（2026 新模式）**

Agentic Chunking 是 2025-2026 年出现的新范式。它使用一个小型/廉价的 LLM（如 Claude Haiku）来分析文档结构，动态决定分块边界。流程如下：

```
文档 → LLM分析结构（识别章节、主题转换、表格边界）
     → 输出分块计划（JSON: [{start: 0, end: 1500, topic: "RAG基础"}, ...]）
     → 按计划执行切分
     → 每个块附带 LLM 生成的主题标签
```

优势：LLM 能理解"第3章第2节讨论的向量数据库与第4章的应用实例应该归为一组"这种隐含语义关系。代价是每个文档需要额外的 LLM 调用。

**固定大小分块的实现**（本管线默认策略）：

```python
# 固定大小分块 + 重叠
chunks = TextChunker.fixed_size(
    doc,
    chunk_size=1000,    # 每块最多 1000 字符
    chunk_overlap=200,  # 相邻块重叠 200 字符
)
```

重叠（overlap）的设计意图：在块边界附近的句子可能因为被截断而失去上下文。重叠确保边界信息在相邻块中都有备份，显著提升检索召回率。典型实践是重叠 10-20% 的 chunk_size。

### 13.2.3 嵌入模型选择

Anthropic **没有**提供自有嵌入模型。这是 Anthropic 与 OpenAI、Cohere 的战略差异。在 Claude 生态中，你必须选择第三方嵌入模型。以下是对比：

| 模型 | 提供商 | 维度 | 最大输入 | 价格(/1M tokens) | 特点 | 推荐场景 |
|------|--------|------|----------|------------------|------|----------|
| text-embedding-3-small | OpenAI | 512/1536 | 8,191 | $0.02 | 可变维度、性价比高 | 通用 RAG、预算敏感 |
| text-embedding-3-large | OpenAI | 256/1024/3072 | 8,191 | $0.13 | 顶级性能、Matryoshka | 高精度需求、多语言 |
| voyage-3 | Voyage AI | 1024 | 32,000 | $0.06 | 32K上下文窗口、检索优化 | 长文档、学术论文 |
| voyage-3-lite | Voyage AI | 512 | 32,000 | $0.02 | 轻量但优秀的检索质量 | 低成本生产部署 |
| voyage-code-3 | Voyage AI | 1024 | 32,000 | $0.06 | 代码语义理解专项优化 | 代码搜索、技术文档 |
| embed-v4.0 | Cohere | 1024 | 128,000 | $0.10 | 超长上下文、多语言 | 超长文档、多语言场景 |
| bge-m3 | BAAI (开源) | 1024 | 8,192 | 免费 | 开源、多语言、自托管 | 隐私敏感、离线部署 |

**选型决策树：**

```
需要自托管/离线？
├── 是 → bge-m3（免费、本地部署）
└── 否 → 主要处理什么类型的内容？
    ├── 长文档(>8K tokens) → 需要超长上下文？
    │   ├── 是(>32K) → Cohere embed-v4.0 (128K)
    │   └── 否(8K-32K) → Voyage voyage-3 (32K)
    ├── 代码搜索 → Voyage voyage-code-3
    └── 通用/多语言 → 预算？
        ├── 低 → text-embedding-3-small
        └── 高 → text-embedding-3-large
```

**重要考量**：嵌入模型的维度直接影响向量数据库的存储成本和检索速度。1024维约需4KB存储/向量，1536维约需6KB。百万级文档意味着数GB的向量存储。使用 OpenAI 的 Matryoshka 特性可在保持语义质量的同时将维度压缩至256维，存储成本降低80%以上。

### 13.2.4 向量数据库

向量数据库是 RAG 的存储和检索引擎。选型需要在以下维度权衡：

| 数据库 | 类型 | 开源 | 部署模式 | 混合搜索 | 过滤 | 适合规模 | 核心优势 |
|--------|------|------|----------|----------|------|----------|----------|
| **Pinecone** | 专用向量DB | 否 | 全托管(Serverless) | 有限 | 元数据过滤 | 中大型 | 零运维、自动扩缩、最快启动 |
| **Qdrant** | 专用向量DB | 是 | 自托管/云 | 原生(BM25+向量) | 强标量过滤 | 中大型 | Rust性能、混合搜索、灵活部署 |
| **Weaviate** | AI原生向量DB | 是 | 自托管/云 | 原生(关键词+向量) | 强 | 中大型 | GraphQL接口、内置向量化模块 |
| **pgvector** | PostgreSQL扩展 | 是 | 取决于PG | 需自建 | SQL级过滤 | 小中型 | 零新基础设施、ACID事务、SQL兼容 |
| **Milvus** | 专用向量DB | 是 | 自托管/云 | 需集成 | 强 | 大型 | 分布式架构、GPU加速、十亿级向量 |
| **ChromaDB** | 嵌入式向量DB | 是 | 嵌入式/Server | 有限 | 基础 | 原型/小型 | 极其轻量、Python原生、快速原型 |

**选型决策树：**

```
当前处于什么阶段？
├── 原型/MVP → ChromaDB 或 内存存储（如本章的 InMemoryVectorStore）
├── 已有 PostgreSQL → pgvector（零额外基础设施）
├── 需要生产部署 →
│   ├── 不想管运维 → Pinecone Serverless
│   ├── 需要混合搜索 + 自托管 → Qdrant 或 Weaviate
│   ├── 十亿级向量 → Milvus（分布式）
│   └── 已有K8s生态 → Qdrant（单二进制，极简部署）
└── 学习/教学 → 本章的 InMemoryVectorStore（零依赖，理解原理）
```

**本章实现的设计选择**

本章使用 `InMemoryVectorStore` 进行教学。它是一个纯 Python/TypeScript 实现，功能完整（cosine相似度搜索、增删、清空），适合学习和单元测试。生产环境中，只需将 `InMemoryVectorStore` 替换为上述任何数据库的适配器——管线的其余部分（分块、嵌入、检索策略）完全不变。

### 13.2.5 检索策略

检索是 RAG 系统的核心。不同检索策略解决不同的问题。

**稀疏检索（Sparse Retrieval）**

基于关键词匹配的经典方法，代表算法为 BM25。BM25 是 TF-IDF 的改进版本，考虑了词频饱和度和文档长度归一化。

BM25 公式：

```
BM25(q, d) = Σ IDF(qi) × (f(qi,d) × (k1+1)) / (f(qi,d) + k1×(1-b+b×|d|/avgdl))

其中：
- IDF(qi) = log((N-df+0.5)/(df+0.5)+1)  逆文档频率
- f(qi,d)  = 词频
- |d|      = 文档长度
- avgdl    = 平均文档长度
- k1       = 词频饱和参数（通常1.5）
- b        = 长度归一化参数（通常0.75）
```

BM25 的优势：
- 无需训练，零成本部署
- 对专有名词、ID、代码标识符等精确匹配极其有效
- 可解释性强——你知道为什么某段文本被检索到

BM25 的劣势：
- 无法理解语义相似性（"汽车"和"轿车"被视为不同词）
- 无法处理跨语言检索
- 对同义词和释义不敏感

**稠密检索（Dense Retrieval）**

使用嵌入模型将查询和文档映射到同一向量空间，通过向量相似度（通常是余弦相似度）进行检索。

稠密检索的优势：
- 理解语义——"如何提高内存效率"能匹配到"优化RAM使用"
- 跨语言能力——英文查询可检索中文文档（使用多语言嵌入模型）
- 处理同义词和释义

稠密检索的劣势：
- 依赖嵌入模型质量
- 对专有名词和代码等"低语义密度"内容效果不如BM25
- 计算成本较高

**混合检索（Hybrid Retrieval）+ RRF 融合**

混合检索结合了稀疏和稠密两种策略。业界最常用的融合方法是 **Reciprocal Rank Fusion (RRF)**：

```
RRF(d) = Σ (1 / (k + rank_i(d)))

其中：
- k = RRF 常数（通常 60）
- rank_i(d) = 文档 d 在第 i 个检索系统中的排名（从1开始）
```

RRF 的优雅之处在于：它不需要对两种检索的分数进行归一化（BM25分数和余弦相似度分数不可直接比较），而是纯粹基于排名进行融合。k=60 是经验最优值，目的是平滑极端排名的权重。

**多阶段检索（Multi-Stage Retrieval）**

生产级 RAG 系统通常采用多阶段检索：

```
阶段1（粗筛）：使用轻量级方法（BM25 或 Annoy 近似向量搜索）从百万级文档中召回 top-1000
阶段2（精排）：使用更精确的方法（稠密向量 + 重排序模型）从 top-1000 中选出 top-20
阶段3（上下文窗口）：将 top-20 中适合 Claude 上下文窗口的 top-5 送入生成
```

**重排序（Reranking）**

检索阶段返回的文档可能顺序不够理想。重排序模型专门针对"给定查询，这两个文档哪个更相关"进行训练。

常用重排序方案：
- **Cohere Rerank v3**：API 服务，直接返回重排后的结果
- **Cross-Encoder（如 BGE-Reranker-v2）**：本地部署，查询-文档对联合编码计算相关性分数
- **Claude as Reranker**：直接让 Claude 对候选文档进行排序——质量最高但延迟和成本也最高

### 13.2.6 高级 RAG 模式

**Adaptive RAG（自适应 RAG）——查询路由**

并非所有查询都需要相同的检索策略。Adaptive RAG 的核心思想是使用一个路由分类器在多个检索路径之间切换：

```
用户查询 → 分类器（Claude Haiku 或 轻量分类模型）
    ├── "事实查询" → BM25 稀疏检索（快、精确）
    ├── "概念问题" → 稠密向量检索（语义理解）
    ├── "多跳推理" → 迭代检索 + 知识图谱
    ├── "实时信息" → Web Search API
    └── "复合查询" → 多路并行 → RRF 融合
```

**Self-RAG（自反思 RAG）**

Self-RAG 的核心是让 LLM 在生成过程中反思检索质量。流程：

```
1. 检索 → 获得候选文档
2. LLM 判断："这些文档是否足以回答问题？"
   ├── 足够 → 生成答案
   └── 不足 → 重新构造查询 → 二次检索
3. 生成答案 → LLM 自我检查："答案的每句话是否有上下文支撑？"
   ├── 有支撑 → 输出
   └── 无支撑 → 标注不确定部分 → 可选三次检索
```

**Agentic RAG（Agent 驱动 RAG）——完整端到端示例**

这是 2025-2026 年最重要的 RAG 范式升级。Agentic RAG 将检索过程交给一个自主 Agent 管理，Agent 可以：

1. 分解复杂问题为子问题
2. 为每个子问题选择独立检索策略
3. 并行执行多路检索
4. 合并、去重、验证结果
5. 决定是否需要更多轮检索
6. 汇总所有发现生成最终答案

完整流程示例：

```
用户查询："比较OpenAI和Voyage的嵌入模型在RAG场景下的性能和成本"

Agent 分解：
├── 子问题1: "OpenAI embedding models specifications and pricing" → Web Search API
├── 子问题2: "Voyage AI embedding models specifications and pricing" → Web Search API
├── 子问题3: "Embedding model benchmarks for RAG retrieval quality" → 内部知识库(稠密)
└── 子问题4: "Text embedding cost comparison 2026" → 内部知识库 + Web Search

并行执行（4个检索任务同时进行）

Agent 汇总：
1. 提取每个子问题的关键信息
2. 交叉验证数据一致性
3. 发现矛盾 → 追加一轮定向检索
4. 组织对比结构 → 送入 Claude 生成

Claude 生成结构化对比答案
```

**Graph RAG（图增强 RAG）**

Graph RAG 在传统向量检索基础上引入知识图谱。核心思想：文档中的实体（人名、公司、产品、概念）和它们之间的关系（雇佣、收购、依赖、因果）构成图结构，可以在检索时提供额外的上下文。

典型场景：
- 法律文档：引用关系、先例关系
- 医疗知识库：症状-疾病-药物-副作用关系链
- 企业知识管理：员工-项目-客户-合同关联

Graph RAG 的技术栈通常涉及：Neo4j（图数据库）+ 实体关系抽取模型 + 向量数据库（混合架构）。

### 13.2.7 RAG 评估体系

RAG 评估分为两个层面：**检索质量**和**生成质量**。

**检索质量指标**

| 指标 | 公式 | 含义 | 适用场景 |
|------|------|------|----------|
| **Recall@K** | 检索到的相关文档数 / 总相关文档数 | 在top-K中找到了多少相关文档 | 不想遗漏（法律、医疗） |
| **Precision@K** | 检索到的相关文档数 / K | top-K中有多少是真正相关的 | 不想噪声（问答系统） |
| **MRR** | 1 / 第一个相关文档的排名 | 第一个正确答案出现的位置 | 事实查询、FAQ |
| **NDCG@K** | DCG@K / IDCG@K | 考虑排名位置加权的质量 | 排序质量要求高 |

**生成质量指标**

生成质量更难以自动化评估。传统指标（ROUGE、BLEU）基于表面文本匹配，无法捕捉语义层面的忠实性和相关性。这是 Claude-as-Judge 方法论的核心价值所在。

**Claude-as-Judge：完整实现**

Claude-as-Judge 使用 Claude 模型作为评估者，对 RAG 输出进行三个维度的量化评估。

**维度1：忠实性（Faithfulness）**

评估答案中的每一个主张是否都有上下文支撑。

```
Prompt 设计原则：
1. 明确定义"忠实"的含义——每个主张都必须被上下文直接支撑
2. 给出分级评分标准（0.0-1.0，含描述）
3. 要求输出结构化JSON：score + reasoning + 支撑/未支撑主张列表
4. 使用 temperature=0.0 确保评估一致性
```

**维度2：相关性（Relevance）**

评估答案是否直接回应用户的问题。

**维度3：完整性（Completeness）**

评估答案是否覆盖了上下文中所有与问题相关的关键信息。

**综合评估 Prompt 设计关键原则**：

1. **角色设定**：明确 Claude 是"RAG系统评估专家"，不是助手
2. **评分锚定**：为每个分数段（0.0-1.0）提供行为描述，减少评分漂移
3. **结构化输出**：强制 JSON 格式，包含分数和推理过程
4. **Temperature=0.0**：消除随机性，确保可复现评估
5. **分离关注点**：相关性只看 query-answer 对，忠实性只看 context-answer 对——避免混淆

**评估结果解释**：

```json
{
  "faithfulness": {"score": 0.9, "reasoning": "..."},
  "relevance": {"score": 0.85, "reasoning": "..."},
  "completeness": {"score": 0.7, "reasoning": "..."},
  "overall_score": 0.82,
  "overall_assessment": "答案准确但不够全面，遗漏了成本对比信息。"
}
```

overall_score < 0.7 通常意味着需要显著改进：可能是检索质量不佳（检索到的文档不相关或不完整），或者是生成 prompt 需要调整。

---

## 13.3 Python 实现

完整的 Python 实现在 `code/python/ch13/` 目录下：

- `rag_pipeline.py`：RAG 管线核心——分块、嵌入、检索、生成
- `claude_judge.py`：Claude-as-Judge 评估器——忠实性、相关性、完整性
- `test_rag.py`：40 个单元测试 + 端到端集成测试

### 核心架构

```
RAGPipeline
├── ingest(documents)          # 文档摄入：分块 → 嵌入 → 索引(BM25 + VectorStore)
│   └── TextChunker            # 分块策略：fixed_size / semantic
├── retrieve(query, strategy)  # 检索：sparse / dense / hybrid(RRF)
│   ├── BM25                   # 稀疏检索（关键词匹配）
│   ├── InMemoryVectorStore    # 稠密检索（向量相似度）
│   └── RRF Fusion             # 混合检索（排名融合）
├── generate(query, context)   # 生成：Claude API 调用
└── query(query)               # 端到端：retrieve → generate
```

### 关键设计决策

**1. Embedder 抽象**：使用 ABC 协议，支持 OpenAI、Voyage、Cohere 三种嵌入提供商的即插即用切换。

```python
# 切换嵌入模型只需替换 embedder 实例
embedder_openai = OpenAIEmbedder(api_key="sk-...", model="text-embedding-3-small")
embedder_voyage = VoyageEmbedder(api_key="vp-...", model="voyage-3")
```

**2. GeneratorCallable 协议**：生成函数通过 Protocol 注入，解耦 RAG 逻辑与 LLM 提供商。

**3. BM25 纯 Python 实现**：零依赖的 BM25 实现，支持可配置的 k1 和 b 参数。

**4. RRF 混合检索**：RRF 常数 k=60，先召回 top_k*3 候选再融合，确保融合池足够大。

### 使用示例

```python
from rag_pipeline import RAGPipeline, Document, ClaudeGenerator, OpenAIEmbedder

# 1. 配置组件
embedder = OpenAIEmbedder(api_key="sk-...")
generator = ClaudeGenerator(api_key="sk-ant-...")

# 2. 构建管线
pipeline = RAGPipeline(
    embedder=embedder,
    generate_fn=generator,
    chunk_size=1000,
    chunk_overlap=200,
)

# 3. 摄入文档
docs = [
    Document(content="RAG stands for Retrieval-Augmented Generation..."),
    Document(content="Vector databases store embeddings..."),
    Document(content="Claude is Anthropic's LLM family..."),
    Document(content="Embedding models convert text to vectors..."),
    Document(content="Hybrid search combines sparse and dense retrieval..."),
]
pipeline.ingest(docs)

# 4. 端到端查询
result = pipeline.query("What is hybrid search and why use it?")
print(result["answer"])           # Claude 生成的答案
print(result["retrieved_chunks"])  # 检索到的上下文块

# 5. Claude-as-Judge 评估
from claude_judge import ClaudeJudge

judge = ClaudeJudge(api_key="sk-ant-...")
evaluation = judge.comprehensive_eval(
    query="What is hybrid search and why use it?",
    answer=result["answer"],
    context="\n".join(c["content"] for c in result["retrieved_chunks"]),
)
print(f"Overall score: {evaluation['overall_score']}")
```

### 测试覆盖（40个测试）

```bash
cd code/python/ch13
python -m pytest test_rag.py -v
```

测试范围：
- TextChunker：固定大小分块、重叠、语义分块、空文档
- BM25：索引、检索、空语料库、无匹配
- InMemoryVectorStore：增删、余弦搜索、长度验证
- RAGPipeline：摄入、三种检索策略、端到端查询、语义分块、清除
- ClaudeGenerator：Mock HTTP 测试
- ClaudeJudge：忠实性、相关性、完整性、综合评估、批量评估
- JSON解析：纯JSON、代码块包装、文本环绕、非法JSON回退
- 检索指标：Recall@K、Precision@K、MRR
- 端到端集成：5文档摄入 → 3问题查询 → 检索质量验证

---

## 13.4 Node.js 实现

完整的 TypeScript 实现在 `code/node/ch13/` 目录下：

- `RAGPipeline.ts`：RAG 管线核心（与 Python 版本功能对等）
- `ClaudeJudge.ts`：Claude-as-Judge 评估器
- `rag.test.ts`：36 个 vitest 测试

API 设计与 Python 版本保持一致，同时遵循 TypeScript 的类型安全惯例。

### 使用示例

```typescript
import { RAGPipeline, Document, ClaudeGenerator, OpenAIEmbedder } from "./RAGPipeline";
import { ClaudeJudge } from "./ClaudeJudge";

// 1. 配置
const embedder = new OpenAIEmbedder("sk-...");
const generator = new ClaudeGenerator("sk-ant-...");

// 2. 构建管线
const pipeline = new RAGPipeline({
  embedder,
  generateFn: (q, c, m) => generator.generate(q, c, m),
  chunkSize: 1000,
  chunkOverlap: 200,
});

// 3. 摄入文档
const docs = [
  new Document("RAG stands for Retrieval-Augmented Generation..."),
  new Document("Vector databases store embeddings..."),
  new Document("Claude is Anthropic's LLM family..."),
  new Document("Embedding models convert text to vectors..."),
  new Document("Hybrid search combines sparse and dense retrieval..."),
];
await pipeline.ingest(docs);

// 4. 端到端查询
const result = await pipeline.query("What is hybrid search?");
console.log(result.answer);
console.log(result.retrievedChunks);

// 5. Claude-as-Judge 评估
const judge = new ClaudeJudge({ apiKey: "sk-ant-..." });
const eval_ = await judge.comprehensiveEval(
  "What is hybrid search?",
  result.answer,
  result.retrievedChunks.map(c => c.content).join("\n"),
);
console.log(`Overall score: ${eval_.overall_score}`);
```

### 测试覆盖（36个测试）

```bash
cd code/node
npx vitest run ch13
```

测试范围与 Python 版本对等，额外覆盖 TypeScript 类型安全验证和 async/await 流程。

---

## 13.5 最佳实践

### 分块大小调优

分块大小是 RAG 系统中影响最大的超参数。没有"最佳"值，需要根据以下因素权衡：

| 因素 | 小分块(256-512) | 中分块(512-1000) | 大分块(1000-2000) |
|------|-----------------|------------------|-------------------|
| 检索精度 | 高（更精确匹配） | 中 | 低（噪声多） |
| 上下文连贯性 | 低（碎片化） | 中 | 高（完整论述） |
| 向量存储成本 | 高（更多向量） | 中 | 低 |
| 嵌入API成本 | 高 | 中 | 低 |
| Claude上下文效率 | 需要更多块填充窗口 | 适中 | 每块信息密度高 |

**调优方法论**：

1. 准备一个包含 20-50 个查询 + 标注相关文档的评估集
2. 从 chunk_size=1000, overlap=200 开始作为基线
3. 分别测试 chunk_size ∈ {256, 512, 1000, 1500, 2000}，保持 overlap=20% chunk_size
4. 使用 Recall@K 和 MRR 衡量不同配置的检索质量
5. 选择 Recall@K 最高的配置，然后主观评估生成质量

### 混合搜索权重调优

RRF 的默认 k=60 对大多数场景效果良好。如需更精细的控制：

**加权 RRF**：

```
RRF_weighted(d) = w_sparse / (k + rank_sparse(d)) + w_dense / (k + rank_dense(d))
```

对于精确匹配需求强的场景（如代码搜索），增大 w_sparse。对于语义理解需求强的场景（如概念问答），增大 w_dense。

### Judge Prompt 设计指南

Claude-as-Judge 评估的可靠性高度依赖 prompt 设计。关键原则：

1. **评分锚定**：为每个分数等级提供具体的行为描述，不要只说"0-1分"
2. **关注点分离**：一次只评估一个维度。综合评估虽然高效，但 Claude 可能混淆忠实性和相关性
3. **要求证据**：不仅要求分数，还要求列出支撑/未支撑的具体主张——这让分数可审计
4. **Temperature=0.0**：评估需要一致性，不是创意
5. **校准检查**：定期用人工标注的样本检查 Claude 评分与人工评分的一致性

### 生产部署检查清单

- [ ] 嵌入模型选择匹配内容类型和预算
- [ ] 分块策略已通过评估集验证
- [ ] 向量数据库选型匹配规模和运维能力
- [ ] 混合检索权重已根据场景调优
- [ ] 重排序模块已集成（如果检索质量不足）
- [ ] Claude-as-Judge 评估管道已建立并定期运行
- [ ] 检索指标（Recall@K、MRR）已设定基线和告警阈值
- [ ] 生成质量（faithfulness、relevance、completeness）定期抽样评估
- [ ] 文档更新机制已建立（增量索引或定期重建）

---

## 13.6 自测题

**1. 基础概念题**：Anthropic 为什么不提供自有嵌入模型？在构建基于 Claude 的 RAG 系统时，这一设计决策对开发者意味着什么？（请从战略和技术两个角度回答）

**2. 检索策略题**：在什么场景下应该优先使用 BM25 稀疏检索而非稠密向量检索？给出至少两个具体例子并解释原因。

**3. 编码题**：修改 `rag_pipeline.py` 中的 `RAGPipeline`，添加一个 `adaptive_retrieve` 方法，根据查询特征自动选择检索策略：
   - 如果查询包含引号或`"`包裹的精确短语 → 使用 `sparse`
   - 如果查询包含"What is"或"How to"等概念性开头 → 使用 `dense`
   - 否则 → 使用 `hybrid`

**4. 评估设计题**：使用 `ClaudeJudge` 为你的 RAG 系统建立评估管道。写出完整的评估脚本，包括：
   - 至少 3 个测试查询
   - 对每个查询运行 RAG 并收集答案
   - 使用 `evaluate_batch` 批量评估
   - 输出汇总报告（平均分、最低分、改进建议）

**5. 编码题（Agentic RAG）**：扩展 `RAGPipeline`，实现一个简单的 Agentic 检索循环：
   - 第一次检索后，Agent 检查检索结果的 `score` 值
   - 如果所有结果 score < 0.3，Agent 自动改写查询（例如用 Claude Haiku 生成查询变体）
   - 用改写后的查询执行第二次检索
   - 最多 3 轮迭代
   - 将最终结果与单轮检索结果进行对比

---

## 13.7 小结

本章构建了完整的 RAG 系统——从文档摄入到评估反馈的闭环。核心要点：

1. **RAG 本质是上下文工程**：目标不是让模型更聪明，而是给模型最优的上下文。
2. **分块是最大的杠杆**：投入时间调优分块策略的回报远高于模型选择或 prompt 微调。
3. **混合检索是生产标配**：BM25 + 稠密向量 + RRF 的组合在绝大多数场景优于单一策略。
4. **Claude-as-Judge 让评估可工程化**：忠实性、相关性、完整性三维度量化评估，取代主观判断。
5. **Agentic RAG 是 2026 趋势**：Agent 驱动的自主检索决策正在取代静态管道。
6. **嵌入模型选择影响全局**：维度、上下文窗口、价格三角权衡，没有银弹。
