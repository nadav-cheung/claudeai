# 附录 I：向量数据库 — Agent 的记忆引擎

> 第 27 章讲了 Agent 如何跨越会话记住事情。附录 E 讲了 RAG 的原理。
> 但中间缺了一环：记忆到底存在哪、怎么查？向量数据库就是这一环。

---

## I.1 为什么文件存储不够用

Claude Code 的 `memory/` 目录用 Markdown 文件存储记忆。这对个人使用够了——你通常只有几十条记忆，一条 `grep` 就能找到相关的。

但当你的 Agent 框架被用于更大的场景——成百上千条记忆、跨项目共享、需要语义理解——文件存储暴露三个问题：

**问题 1：关键词搜索的盲区。** 你记了一条"用户偏好使用 React 18 的 useId hook"。当用户问"我想用 React 的 ID 生成功能"，关键词搜索找不到——"ID" ≠ "useId"。

**问题 2：无法排序。** 关键词搜索是二元的——匹配或不匹配。但你需要知道哪条记忆"最相关"。"React 状态管理"和"Zustand 最佳实践"语义上高度相关，但关键词不重叠。

**问题 3：线性增长。** 每次查询都要遍历所有记忆。100 条时还行，1000 条时每个请求增加 1 秒。

向量数据库解决了这三件事：**语义搜索、相似度排序、亚线性检索**。

---

## I.2 嵌入模型：把文字变成向量

向量数据库的第一步是把文字变成一个固定长度的浮点数数组——**嵌入向量（Embedding）**。

### 是什么

```
"用户偏好 React 18 useId hook"
      ↓ 嵌入模型
[0.023, -0.451, 0.782, ...]  ← 1536 个浮点数
```

同一个模型下，语义相似的文字产生相近的向量。"React 18 useId" 和 "React ID 生成" 的向量余弦相似度 > 0.85，而 "Python asyncio" 和它们的相似度 < 0.3。

### 选型对比

| 模型 | 维度 | 价格 ($/1M tokens) | 中英文 | 本地 |
|------|------|-------------------|--------|------|
| text-embedding-3-small (OpenAI) | 1536 | $0.02 | 英文优，中文可 | 否 |
| text-embedding-3-large (OpenAI) | 3072 | $0.13 | 最好，但贵 | 否 |
| voyage-code-3 (Voyage AI) | 2048 | $0.06 | 代码特化 | 否 |
| bge-large-en-v1.5 (BAAI) | 1024 | 免费 | 英文 | 是 |
| bge-m3 (BAAI) | 1024 | 免费 | 中英多语 | 是 |
| nomic-embed-text (Nomic) | 768 | 免费 | 英文 | 是 (Ollama) |

**建议**：开发/个人项目用 bge-m3（免费+本地+多语）。生产环境用 text-embedding-3-small（便宜+稳定）。

### 最简嵌入代码

```typescript
// → 使用 OpenAI 嵌入 API
async function embed(text: string): Promise<number[]> {
  const response = await fetch("https://api.openai.com/v1/embeddings", {
    method: "POST",
    headers: {
      "Authorization": `Bearer ${process.env.OPENAI_API_KEY}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      model: "text-embedding-3-small",
      input: text,
    }),
  })
  const data = await response.json()
  return data.data[0].embedding  // number[1536]
}

// → 使用 Ollama 本地嵌入（免费，无需 API key）
async function embedLocal(text: string): Promise<number[]> {
  const response = await fetch("http://localhost:11434/api/embeddings", {
    method: "POST",
    body: JSON.stringify({ model: "nomic-embed-text", prompt: text }),
  })
  const data = await response.json()
  return data.embedding  // number[768]
}
```

### 相似度计算

```typescript
// → 余弦相似度：最常用的向量相似度度量
function cosineSimilarity(a: number[], b: number[]): number {
  let dot = 0, normA = 0, normB = 0
  for (let i = 0; i < a.length; i++) {
    dot += a[i] * b[i]
    normA += a[i] * a[i]
    normB += b[i] * b[i]
  }
  return dot / (Math.sqrt(normA) * Math.sqrt(normB))
}

// 典型阈值：
// > 0.85 — 高度相关（基本同一个话题）
// 0.70-0.85 — 相关（值得检索）
// < 0.70 — 不相关
```

---

## I.3 向量数据库选型

向量数据库的核心能力：存向量 → 建索引 → 快速查最相似的 K 个。

| 数据库 | 部署 | 规模 | 特点 |
|--------|------|------|------|
| **Chroma** | 本地/Python | 小-中 | 零配置，5 行代码开始 |
| **LanceDB** | 本地/Node.js | 小-中 | 原生 JS 支持，无服务端 |
| **pgvector** | PostgreSQL 扩展 | 中-大 | 生产级，和业务数据共存 |
| **Pinecone** | 托管 | 大 | 零运维，贵 |
| **Qdrant** | 自托管/云 | 中-大 | Rust 实现，性能好 |
| **Milvus** | 自托管 | 大-超大 | 分布式，十亿级向量 |

### 选型决策树

```
你的规模？
  < 10K 条记忆 → Chroma 或 LanceDB（本地，零配置）
  10K - 1M 条   → pgvector（已有 PG）或 Qdrant（性能优先）
  > 1M 条        → Pinecone（托管）或 Milvus（自建）

你的技术栈？
  已有 PostgreSQL → pgvector（零额外基础设施）
  Node.js only   → LanceDB（嵌入式，无服务端进程）
  Python 为主    → Chroma
```

---

## I.4 最简 RAG 实现（50 行）

```typescript
// → minimal-rag.ts — 从零到可用的 RAG 系统
import { LanceDB } from "@lancedb/lancedb"  // 嵌入式向量数据库
import { embedLocal } from "./embedding"     // 嵌入函数

interface Memory {
  id: string
  content: string
  metadata: { timestamp: string; source?: string }
}

class MemoryStore {
  private db: any
  private table: any

  async init(path: string): Promise<void> {
    this.db = await LanceDB.connect(path)
    // 如果表不存在则创建
    const tables = await this.db.tableNames()
    if (!tables.includes("memories")) {
      this.table = await this.db.createTable("memories", [
        { id: "seed", vector: new Array(768).fill(0), content: "", metadata: "{}" }
      ])
    } else {
      this.table = await this.db.openTable("memories")
    }
  }

  // 存：文字 → 向量 → 数据库
  async add(memory: Memory): Promise<void> {
    const vector = await embedLocal(memory.content)
    await this.table.add([{
      id: memory.id,
      vector,
      content: memory.content,
      metadata: JSON.stringify(memory.metadata),
    }])
  }

  // 查：query → 向量 → 最相似的 K 个
  async search(query: string, k = 5): Promise<Memory[]> {
    const queryVector = await embedLocal(query)
    const results = await this.table
      .search(queryVector)
      .limit(k)
      .toArray()

    return results.map((r: any) => ({
      id: r.id,
      content: r.content,
      metadata: JSON.parse(r.metadata),
    }))
  }
}

// 使用
const store = new MemoryStore()
await store.init("./agent-memories")

await store.add({
  id: "mem-1",
  content: "用户偏好 React 18 的 useId hook 来生成唯一 ID",
  metadata: { timestamp: new Date().toISOString(), source: "conversation" },
})

await store.add({
  id: "mem-2",
  content: "项目使用 Zustand 做状态管理，不要引入 Redux",
  metadata: { timestamp: new Date().toISOString(), source: "conversation" },
})

// 语义搜索："ID 生成" 能命中 "useId hook"
const results = await store.search("React 中如何生成唯一 ID", 3)
console.log(results.map(r => r.content))
```

---

## I.5 生产级优化

### Chunk 策略

长文本（如整个文件的代码）不能直接嵌入——嵌入模型有输入长度限制（通常 512-8192 tokens），且长文本的语义被稀释。

```typescript
// → 固定大小 + 重叠的 Chunk 策略
function chunkText(text: string, chunkSize = 500, overlap = 50): string[] {
  const chunks: string[] = []
  let i = 0
  while (i < text.length) {
    chunks.push(text.substring(i, i + chunkSize))
    i += chunkSize - overlap  // 重叠 50 字符，避免语义断裂
  }
  return chunks
}
```

更好的策略是按语义边界分割（段落、函数边界），但固定大小+重叠是最简起点。

### Re-ranking：粗排 + 精排

向量检索很快但不完美。生产 RAG 通常用两阶段：

```
第一阶段（粗排）：向量相似度 → 取 Top 50
第二阶段（精排）：用更精确（但更慢）的模型 → 重排 Top 50 → 取 Top 5
```

```typescript
// → 两阶段检索
async function searchWithRerank(query: string, k = 5): Promise<Memory[]> {
  // 第一阶段：向量检索（快，500ms）
  const candidates = await store.search(query, 50)

  // 第二阶段：Cross-encoder 重排（慢但准，200ms）
  // Cross-encoder 同时看 query 和 document，判断相关性
  const reranked = await rerankWithCrossEncoder(query, candidates)

  return reranked.slice(0, k)
}
```

### 增量索引

新增记忆时不要重建整个索引。LanceDB 和大多数向量数据库支持追加写入：

```typescript
// LanceDB 的追加写入
await table.add([{ id, vector, content, metadata }])  // 增量，不重建
```

---

## 试一试

### 基础：用 Ollama 跑本地嵌入

```bash
# 安装 Ollama 并拉取嵌入模型
ollama pull nomic-embed-text

# 测试嵌入
curl http://localhost:11434/api/embeddings \
  -d '{"model": "nomic-embed-text", "prompt": "Hello world"}'
```

### 进阶：构建完整的 MemoryStore

用上面的 `MemoryStore` 实现一个 Agent 的记忆系统——每次对话结束后自动把关键信息存入，下次对话开始时检索相关记忆。

### 挑战：对比不同嵌入模型

用同一批记忆（50 条），分别用 bge-m3 和 text-embedding-3-small 做嵌入，对比检索结果的质量。找 10 个 query，人工标注"相关记忆"，计算 precision@5。

---

> 向量数据库不是魔法——它只是把"这个和那个像不像"这个直觉问题，变成了可计算的数学问题。
