/**
 * Tests for Chapter 13: RAG Pipeline and Claude-as-Judge (TypeScript).
 *
 * All tests use mocked fetch so they run without API keys.
 */

import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import {
  Document,
  Chunk,
  BM25,
  InMemoryVectorStore,
  TextChunker,
  RAGPipeline,
  type Embedder,
  type GeneratorFn,
  type RetrievalResultDict,
} from "./RAGPipeline";
import {
  ClaudeJudge,
  computeRetrievalMetrics,
  parseJsonResponse,
  type JudgeConfig,
} from "./ClaudeJudge";

// ---------------------------------------------------------------------------
// Mock embedder
// ---------------------------------------------------------------------------

class MockEmbedder implements Embedder {
  readonly dimension = 128;

  async embed(texts: readonly string[]): Promise<number[][]> {
    return texts.map((t) => this.encode(t));
  }

  async embedQuery(query: string): Promise<number[]> {
    return this.encode(query);
  }

  private encode(text: string): number[] {
    const vec = new Array<number>(128).fill(0);
    const lower = text.toLowerCase();
    for (let i = 0; i < lower.length; i++) {
      const idx = lower.charCodeAt(i) % 128;
      vec[idx] += 1.0 / (i + 1);
    }
    const norm = Math.sqrt(vec.reduce((sum, v) => sum + v * v, 0));
    return norm > 0 ? vec.map((v) => v / norm) : vec;
  }
}

// ---------------------------------------------------------------------------
// Mock generator
// ---------------------------------------------------------------------------

const mockGenerateFn: GeneratorFn = async (
  query: string,
  context: string,
  _model: string,
): Promise<string> => {
  const queryTerms = query.toLowerCase().split(/\s+/);
  const sentences: string[] = [];
  for (const line of context.split("\n")) {
    for (const sent of line.split(". ")) {
      if (queryTerms.some((t) => sent.toLowerCase().includes(t))) {
        sentences.push(sent.trim());
      }
    }
  }
  if (sentences.length > 0) {
    return sentences.slice(0, 3).join(". ") + ".";
  }
  return "Based on the provided context, I cannot find sufficient information.";
};

// ---------------------------------------------------------------------------
// Sample documents
// ---------------------------------------------------------------------------

const SAMPLE_DOCS = [
  new Document(
    "Retrieval-Augmented Generation (RAG) is a technique that combines " +
      "information retrieval with large language models. RAG enhances LLM " +
      "responses by providing relevant external knowledge at inference time. " +
      "This reduces hallucinations and improves factual accuracy.",
    { title: "Introduction to RAG" },
  ),
  new Document(
    "Vector databases store embeddings — numerical representations of text " +
      "that capture semantic meaning. Popular vector databases include Pinecone, " +
      "Weaviate, Qdrant, and pgvector. They support similarity search using " +
      "metrics like cosine distance and Euclidean distance.",
    { title: "Vector Databases" },
  ),
  new Document(
    "Claude is Anthropic's family of large language models. Claude models " +
      "are designed with Constitutional AI principles, emphasizing helpfulness, " +
      "honesty, and harmlessness. They can be accessed via the Anthropic API " +
      "at api.anthropic.com.",
    { title: "Claude Models" },
  ),
  new Document(
    "Embedding models convert text into fixed-length vectors. OpenAI provides " +
      "text-embedding-3-small (1536 dimensions) and text-embedding-3-large " +
      "(3072 dimensions). Voyage AI offers voyage-3 with 1024 dimensions and " +
      "a 32K token context window. Cohere's embed-v4.0 also has 1024 dimensions. " +
      "For open-source options, BAAI's bge-m3 is a strong choice supporting " +
      "multilingual embeddings.",
    { title: "Embedding Models" },
  ),
  new Document(
    "Hybrid search combines sparse retrieval (BM25 or SPLADE for keyword " +
      "matching) with dense retrieval (vector similarity for semantic matching). " +
      "Reciprocal Rank Fusion (RRF) merges the two result sets without needing " +
      "to normalize scores. This approach significantly improves retrieval " +
      "quality compared to using either method alone.",
    { title: "Hybrid Search" },
  ),
];

// ---------------------------------------------------------------------------
// TextChunker
// ---------------------------------------------------------------------------

describe("TextChunker", () => {
  it("fixed-size chunking creates multiple chunks", () => {
    const doc = new Document("ABCDEFGHIJ".repeat(20));
    const chunks = TextChunker.fixedSize(doc, 50, 10);
    expect(chunks.length).toBeGreaterThan(1);
    for (const c of chunks) {
      expect(c.content.length).toBeLessThanOrEqual(50);
    }
  });

  it("fixed-size chunking creates overlapping chunks", () => {
    const doc = new Document("ABCDEFGHIJ".repeat(20));
    const chunks = TextChunker.fixedSize(doc, 50, 10);
    if (chunks.length >= 2) {
      expect(chunks[0]!.content.slice(-10)).toBe(chunks[1]!.content.slice(0, 10));
    }
  });

  it("semantic chunking works on paragraphs", () => {
    const doc = new Document(
      "First paragraph about RAG. It has multiple sentences. " +
        "Second paragraph about vector databases. It also has details.\n\n" +
        "Third paragraph with different topic about Claude models.",
    );
    const chunks = TextChunker.semantic(doc, 500);
    expect(chunks.length).toBeGreaterThanOrEqual(1);
  });

  it("single chunk for small document", () => {
    const doc = new Document("Short text.");
    const chunks = TextChunker.fixedSize(doc, 1000);
    expect(chunks.length).toBe(1);
    expect(chunks[0]!.content).toBe("Short text.");
  });

  it("handles empty document", () => {
    const doc = new Document("");
    const chunks = TextChunker.fixedSize(doc);
    // Empty content produces no chunks (nothing to chunk)
    expect(chunks.length).toBe(0);
  });
});

// ---------------------------------------------------------------------------
// BM25
// ---------------------------------------------------------------------------

describe("BM25", () => {
  it("ranks relevant chunks first", () => {
    const chunks = [
      new Chunk("RAG combines retrieval with generation", "d1", 0),
      new Chunk("Vector databases store embeddings", "d2", 0),
      new Chunk("Claude is an LLM from Anthropic", "d3", 0),
    ];
    const bm25 = new BM25();
    bm25.index(chunks);

    const results = bm25.search("retrieval generation");
    expect(results.length).toBeGreaterThan(0);
    expect(results[0]![0].content).toContain("RAG");
  });

  it("returns empty for empty corpus", () => {
    const bm25 = new BM25();
    bm25.index([]);
    expect(bm25.search("anything")).toEqual([]);
  });
});

// ---------------------------------------------------------------------------
// InMemoryVectorStore
// ---------------------------------------------------------------------------

describe("InMemoryVectorStore", () => {
  it("adds and searches by cosine similarity", () => {
    const store = new InMemoryVectorStore();
    store.add(
      [new Chunk("hello world", "d1", 0), new Chunk("goodbye world", "d2", 0)],
      [
        [1, 0, 0],
        [0, 1, 0],
      ],
    );

    const results = store.search([1, 0.1, 0], 2);
    expect(results.length).toBe(2);
    expect(results[0]![0].content).toBe("hello world");
    expect(results[0]![1]).toBeGreaterThan(results[1]![1]!);
  });

  it("returns empty for empty store", () => {
    const store = new InMemoryVectorStore();
    expect(store.search([1, 0])).toEqual([]);
  });

  it("clear empties the store", () => {
    const store = new InMemoryVectorStore();
    store.add([new Chunk("test", "d1", 0)], [[0.5, 0.5]]);
    expect(store.length).toBe(1);
    store.clear();
    expect(store.length).toBe(0);
  });

  it("throws on mismatched chunk/vector lengths", () => {
    const store = new InMemoryVectorStore();
    expect(() =>
      store.add([new Chunk("x", "d1", 0)], [
        [0.1],
        [0.2],
      ]),
    ).toThrow("same length");
  });
});

// ---------------------------------------------------------------------------
// RAGPipeline
// ---------------------------------------------------------------------------

describe("RAGPipeline", () => {
  let pipeline: RAGPipeline;

  beforeEach(() => {
    pipeline = new RAGPipeline({
      embedder: new MockEmbedder(),
      generateFn: mockGenerateFn,
      chunkSize: 300,
      chunkOverlap: 50,
      topK: 3,
    });
  });

  it("ingests documents and returns chunk count", async () => {
    const count = await pipeline.ingest(SAMPLE_DOCS);
    expect(count).toBeGreaterThan(0);
    expect(pipeline.chunkCount).toBe(count);
  });

  it("retrieves with sparse strategy", async () => {
    await pipeline.ingest(SAMPLE_DOCS);
    const results = await pipeline.retrieve("vector database", {
      strategy: "sparse",
    });
    expect(results.length).toBeGreaterThan(0);
    for (const r of results) {
      expect(r.strategy).toBe("sparse");
    }
  });

  it("retrieves with dense strategy", async () => {
    await pipeline.ingest(SAMPLE_DOCS);
    const results = await pipeline.retrieve("what is an embedding model", {
      strategy: "dense",
    });
    expect(results.length).toBeGreaterThan(0);
    for (const r of results) {
      expect(r.strategy).toBe("dense");
    }
  });

  it("retrieves with hybrid strategy", async () => {
    await pipeline.ingest(SAMPLE_DOCS);
    const results = await pipeline.retrieve("Claude model", {
      strategy: "hybrid",
    });
    expect(results.length).toBeGreaterThan(0);
    for (const r of results) {
      expect(r.strategy).toBe("hybrid");
    }
  });

  it("queries end-to-end", async () => {
    await pipeline.ingest(SAMPLE_DOCS);
    const result = await pipeline.query("What is RAG?");
    expect(result.answer).toBeTruthy();
    expect(result.retrievedChunks.length).toBeGreaterThan(0);
  });

  it("queries return structured results", async () => {
    await pipeline.ingest(SAMPLE_DOCS);
    const result = await pipeline.query("Tell me about vector databases", {
      topK: 2,
    });
    expect(typeof result.answer).toBe("string");
    expect(result.answer.length).toBeGreaterThan(0);
    expect(result.retrievedChunks.length).toBeLessThanOrEqual(2);
  });

  it("ingesting empty docs returns 0", async () => {
    const count = await pipeline.ingest([]);
    expect(count).toBe(0);
  });

  it("clear resets state", async () => {
    await pipeline.ingest(SAMPLE_DOCS);
    expect(pipeline.chunkCount).toBeGreaterThan(0);
    pipeline.clear();
    expect(pipeline.chunkCount).toBe(0);
  });

  it("semantic chunking strategy works", async () => {
    const count = await pipeline.ingest(SAMPLE_DOCS, {
      chunkStrategy: "semantic",
    });
    expect(count).toBeGreaterThan(0);
  });

  it("throws on unknown strategy", async () => {
    await pipeline.ingest(SAMPLE_DOCS);
    await expect(
      pipeline.retrieve("test", { strategy: "unknown" }),
    ).rejects.toThrow("Unknown retrieval strategy");
  });
});

// ---------------------------------------------------------------------------
// ClaudeJudge
// ---------------------------------------------------------------------------

function mockClaudeFetch(responseJson: unknown): void {
  const mockResp = {
    ok: true,
    status: 200,
    json: async () =>
      ({
        content: [{ type: "text", text: JSON.stringify(responseJson) }],
      }) as Record<string, unknown>,
  };
  (globalThis as unknown as { fetch: typeof fetch }).fetch = vi
    .fn()
    .mockResolvedValue(mockResp as Response);
}

describe("ClaudeJudge", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("evaluates faithfulness", async () => {
    mockClaudeFetch({
      score: 0.95,
      reasoning: "All claims supported.",
      supported_claims: ["RAG combines retrieval and generation"],
      unsupported_claims: [],
    });

    const judge = new ClaudeJudge({ apiKey: "sk-test" });
    const result = await judge.evaluateFaithfulness(
      "RAG combines retrieval and generation.",
      "RAG is a technique that combines retrieval and generation.",
    );
    expect(result.score).toBeGreaterThanOrEqual(0);
    expect(result.score).toBeLessThanOrEqual(1);
    expect(result.reasoning).toBeTruthy();
  });

  it("evaluates relevance", async () => {
    mockClaudeFetch({
      score: 1.0,
      reasoning: "Directly addresses the query.",
      relevant_parts: ["Vector databases store embeddings"],
      irrelevant_parts: [],
    });

    const judge = new ClaudeJudge({ apiKey: "sk-test" });
    const result = await judge.evaluateRelevance(
      "Vector databases store embeddings for similarity search.",
      "What do vector databases store?",
    );
    expect(result.score).toBe(1.0);
  });

  it("evaluates completeness", async () => {
    mockClaudeFetch({
      score: 0.7,
      reasoning: "Covers most key points.",
      covered_points: ["Embedding models convert text to vectors"],
      missed_points: ["Pricing comparison between providers"],
    });

    const judge = new ClaudeJudge({ apiKey: "sk-test" });
    const result = await judge.evaluateCompleteness(
      "Embedding models convert text to vectors.",
      "Embedding models convert text to vectors. Pricing varies by provider.",
    );
    expect(result.score).toBe(0.7);
  });

  it("performs comprehensive evaluation", async () => {
    mockClaudeFetch({
      faithfulness: { score: 0.9, reasoning: "Mostly faithful." },
      relevance: { score: 0.9, reasoning: "Directly on topic." },
      completeness: { score: 0.8, reasoning: "Minor omissions." },
      overall_score: 0.87,
      overall_assessment: "Good answer with high faithfulness and relevance.",
    });

    const judge = new ClaudeJudge({ apiKey: "sk-test" });
    const result = await judge.comprehensiveEval(
      "What is RAG?",
      "RAG is a technique combining retrieval with generation.",
      "RAG combines retrieval with generation to improve accuracy.",
    );
    expect(result.faithfulness).toBeDefined();
    expect(result.relevance).toBeDefined();
    expect(result.completeness).toBeDefined();
    expect(result.overall_score).toBeGreaterThan(0);
  });

  it("evaluates a batch of test cases", async () => {
    mockClaudeFetch({
      faithfulness: { score: 0.9, reasoning: "ok" },
      relevance: { score: 1.0, reasoning: "ok" },
      completeness: { score: 0.8, reasoning: "ok" },
      overall_score: 0.9,
      overall_assessment: "Good.",
    });

    const judge = new ClaudeJudge({ apiKey: "sk-test" });
    const results = await judge.evaluateBatch([
      { query: "Q1", answer: "A1", context: "C1" },
      { query: "Q2", answer: "A2", context: "C2" },
    ]);
    expect(results.length).toBe(2);
    expect(results[0]!.overall_score).toBe(0.9);
  });
});

// ---------------------------------------------------------------------------
// parseJsonResponse
// ---------------------------------------------------------------------------

describe("parseJsonResponse", () => {
  it("parses clean JSON", () => {
    const result = parseJsonResponse('{"score": 0.85, "reasoning": "test"}');
    expect(result.score).toBe(0.85);
    expect(result.reasoning).toBe("test");
  });

  it("parses JSON in code block", () => {
    const result = parseJsonResponse(
      '```json\n{"score": 0.9, "reasoning": "test"}\n```',
    );
    expect(result.score).toBe(0.9);
  });

  it("parses JSON with surrounding text", () => {
    const result = parseJsonResponse(
      'Here is my evaluation:\n\n{"score": 0.75, "reasoning": "ok"}\n\nHope this helps.',
    );
    expect(result.score).toBe(0.75);
  });

  it("falls back gracefully on invalid JSON", () => {
    const result = parseJsonResponse("I cannot parse this");
    expect(result.score).toBe(0.0);
    expect(result.reasoning).toContain("Failed to parse");
  });
});

// ---------------------------------------------------------------------------
// Retrieval metrics
// ---------------------------------------------------------------------------

describe("computeRetrievalMetrics", () => {
  it("perfect retrieval gives 1.0 scores", () => {
    const metrics = computeRetrievalMetrics(
      ["a", "b", "c"],
      new Set(["a", "b", "c"]),
    );
    expect(metrics.recall_at_k).toBe(1.0);
    expect(metrics.precision_at_k).toBe(1.0);
    expect(metrics.mrr).toBe(1.0);
  });

  it("partial retrieval", () => {
    const metrics = computeRetrievalMetrics(
      ["a", "b", "c", "d"],
      new Set(["b", "e"]),
      3,
    );
    expect(metrics.recall_at_k).toBe(0.5);
    expect(metrics.precision_at_k).toBeCloseTo(1.0 / 3.0);
  });

  it("MRR reflects first relevant rank", () => {
    const metrics = computeRetrievalMetrics(
      ["x", "a", "y"],
      new Set(["a", "b"]),
    );
    expect(metrics.mrr).toBe(1.0 / 2.0);
  });

  it("zero relevant returns zero recall", () => {
    const metrics = computeRetrievalMetrics(
      ["x", "y"],
      new Set<string>(),
    );
    expect(metrics.recall_at_k).toBe(0.0);
  });

  it("empty retrieved returns zero scores", () => {
    const metrics = computeRetrievalMetrics([], new Set(["a"]));
    expect(metrics.recall_at_k).toBe(0.0);
    expect(metrics.mrr).toBe(0.0);
  });
});

// ---------------------------------------------------------------------------
// End-to-end integration: ingest 5 docs -> query 3 questions
// ---------------------------------------------------------------------------

describe("End-to-End Integration", () => {
  it("full pipeline: ingest 5 docs, query 3 questions, verify retrieval quality", async () => {
    const pipeline = new RAGPipeline({
      embedder: new MockEmbedder(),
      generateFn: mockGenerateFn,
      chunkSize: 300,
      chunkOverlap: 50,
      topK: 3,
    });

    // Step 1: Ingest 5 documents
    const count = await pipeline.ingest(SAMPLE_DOCS);
    expect(count).toBeGreaterThan(0);

    // Step 2: Query 3 questions
    const questions = [
      "What is RAG and how does it help LLMs?",
      "What vector databases are commonly used?",
      "How does hybrid search work?",
    ];

    const results = [];
    for (const q of questions) {
      const result = await pipeline.query(q, { strategy: "hybrid" });
      expect(result.answer.length).toBeGreaterThan(0);
      expect(result.retrievedChunks.length).toBeGreaterThan(0);
      results.push(result);
    }
    expect(results.length).toBe(3);

    // Step 3: Verify retrieval quality by content relevance
    const q0Chunks = results[0]!.retrievedChunks;
    const ragTerms = q0Chunks.filter(
      (c) =>
        c.content.includes("RAG") ||
        c.content.toLowerCase().includes("retrieval"),
    );
    expect(ragTerms.length).toBeGreaterThan(0);

    const q1Chunks = results[1]!.retrievedChunks;
    const dbTerms = q1Chunks.filter(
      (c) =>
        c.content.toLowerCase().includes("pinecone") ||
        c.content.toLowerCase().includes("weaviate") ||
        c.content.toLowerCase().includes("qdrant") ||
        c.content.toLowerCase().includes("pgvector"),
    );
    expect(dbTerms.length).toBeGreaterThan(0);

    const q2Chunks = results[2]!.retrievedChunks;
    const hybridTerms = q2Chunks.filter(
      (c) =>
        c.content.toLowerCase().includes("hybrid") ||
        c.content.toLowerCase().includes("bm25") ||
        c.content.toLowerCase().includes("rrf") ||
        c.content.toLowerCase().includes("sparse"),
    );
    expect(hybridTerms.length).toBeGreaterThan(0);
  });
});
