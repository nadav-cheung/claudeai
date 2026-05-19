/**
 * Chapter 13: RAG Pipeline — Retrieval-Augmented Generation (TypeScript).
 *
 * A vendor-agnostic RAG pipeline with pluggable embedders, vector stores,
 * retrieval strategies, and generators. Designed for the Anthropic ecosystem.
 *
 * Key features:
 *   - Document ingestion with configurable chunking
 *   - Multiple retrieval strategies: sparse, dense, hybrid
 *   - Reciprocal Rank Fusion (RRF) for hybrid search
 *   - Claude-powered answer generation
 *   - End-to-end query() method
 */

import { createHash } from "node:crypto";

// ---------------------------------------------------------------------------
// Data models
// ---------------------------------------------------------------------------

export interface DocumentMetadata {
  [key: string]: unknown;
}

export class Document {
  readonly content: string;
  readonly metadata: DocumentMetadata;
  readonly docId: string;

  constructor(content: string, metadata: DocumentMetadata = {}) {
    this.content = content;
    this.metadata = metadata;
    this.docId = createHash("sha256").update(content).digest("hex").slice(0, 16);
  }
}

export class Chunk {
  readonly content: string;
  readonly docId: string;
  readonly chunkIndex: number;
  readonly metadata: DocumentMetadata;
  readonly chunkId: string;

  constructor(
    content: string,
    docId: string,
    chunkIndex: number,
    metadata: DocumentMetadata = {},
  ) {
    this.content = content;
    this.docId = docId;
    this.chunkIndex = chunkIndex;
    this.metadata = metadata;
    const raw = `${docId}:${chunkIndex}`;
    this.chunkId = createHash("sha256").update(raw).digest("hex").slice(0, 16);
  }
}

export interface RetrievalResult {
  readonly chunk: Chunk;
  readonly score: number;
  readonly strategy: "sparse" | "dense" | "hybrid";
}

export interface RetrievalResultDict {
  readonly content: string;
  readonly docId: string;
  readonly score: number;
  readonly chunkId: string;
  readonly strategy: string;
  readonly metadata: DocumentMetadata;
}

export interface QueryResult {
  readonly answer: string;
  readonly retrievedChunks: readonly RetrievalResultDict[];
  readonly strategy: string;
}

// ---------------------------------------------------------------------------
// Embedder interface
// ---------------------------------------------------------------------------

export interface Embedder {
  readonly dimension: number;
  embed(texts: readonly string[]): Promise<number[][]>;
  embedQuery(query: string): Promise<number[]>;
}

// ---------------------------------------------------------------------------
// Concrete embedders
// ---------------------------------------------------------------------------

export class OpenAIEmbedder implements Embedder {
  private readonly apiKey: string;
  private readonly model: string;
  private readonly dims: number;
  private static readonly defaultDims: Record<string, number> = {
    "text-embedding-3-small": 1536,
    "text-embedding-3-large": 3072,
  };

  constructor(
    apiKey: string,
    model: string = "text-embedding-3-small",
    dimensions?: number,
  ) {
    this.apiKey = apiKey;
    this.model = model;
    this.dims =
      dimensions ?? OpenAIEmbedder.defaultDims[model] ?? 1536;
  }

  get dimension(): number {
    return this.dims;
  }

  async embed(texts: readonly string[]): Promise<number[][]> {
    const body: Record<string, unknown> = { model: this.model, input: texts };
    if (this.dims) body["dimensions"] = this.dims;

    const resp = await fetch("https://api.openai.com/v1/embeddings", {
      method: "POST",
      headers: {
        Authorization: `Bearer ${this.apiKey}`,
        "Content-Type": "application/json",
      },
      body: JSON.stringify(body),
    });
    if (!resp.ok) throw new Error(`OpenAI embed failed: ${resp.status}`);
    const data = (await resp.json()) as {
      data: { embedding: number[] }[];
    };
    return data.data.map((item) => item.embedding);
  }

  async embedQuery(query: string): Promise<number[]> {
    const results = await this.embed([query]);
    return results[0]!;
  }
}

export class VoyageEmbedder implements Embedder {
  private readonly apiKey: string;
  private readonly model: string;
  private static readonly dims: Record<string, number> = {
    "voyage-3": 1024,
    "voyage-3-lite": 512,
    "voyage-code-3": 1024,
  };

  constructor(apiKey: string, model: string = "voyage-3") {
    this.apiKey = apiKey;
    this.model = model;
  }

  get dimension(): number {
    return VoyageEmbedder.dims[this.model] ?? 1024;
  }

  async embed(texts: readonly string[]): Promise<number[][]> {
    const resp = await fetch("https://api.voyageai.com/v1/embeddings", {
      method: "POST",
      headers: {
        Authorization: `Bearer ${this.apiKey}`,
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        model: this.model,
        input: texts,
        input_type: "document",
      }),
    });
    if (!resp.ok) throw new Error(`Voyage embed failed: ${resp.status}`);
    const data = (await resp.json()) as {
      data: { embedding: number[] }[];
    };
    return data.data.map((item) => item.embedding);
  }

  async embedQuery(query: string): Promise<number[]> {
    const results = await this.embed([query]);
    return results[0]!;
  }
}

// ---------------------------------------------------------------------------
// BM25 — Sparse Retrieval
// ---------------------------------------------------------------------------

export class BM25 {
  private k1: number;
  private b: number;
  private corpus: Chunk[] = [];
  private docFreq: Map<string, number> = new Map();
  private avgdl = 0;

  constructor(k1: number = 1.5, b: number = 0.75) {
    this.k1 = k1;
    this.b = b;
  }

  index(chunks: readonly Chunk[]): void {
    this.corpus = [...chunks];
    this.docFreq = new Map();
    let totalLen = 0;

    for (const chunk of chunks) {
      const terms = new Set(this.tokenize(chunk.content));
      for (const t of terms) {
        this.docFreq.set(t, (this.docFreq.get(t) ?? 0) + 1);
      }
      totalLen += this.tokenize(chunk.content).length;
    }
    this.avgdl = totalLen / Math.max(chunks.length, 1);
  }

  search(query: string, topK: number = 5): [Chunk, number][] {
    const N = this.corpus.length;
    const queryTerms = this.tokenize(query);
    const scores: [number, number][] = [];

    for (let idx = 0; idx < this.corpus.length; idx++) {
      const chunk = this.corpus[idx]!;
      const docTerms = this.tokenize(chunk.content);
      const docLen = docTerms.length;
      const tf = new Map<string, number>();
      for (const t of docTerms) {
        tf.set(t, (tf.get(t) ?? 0) + 1);
      }

      let score = 0;
      for (const qt of queryTerms) {
        const df = this.docFreq.get(qt);
        if (df === undefined) continue;
        const f = tf.get(qt) ?? 0;
        const idf = Math.log((N - df + 0.5) / (df + 0.5) + 1);
        const numerator = f * (this.k1 + 1);
        const denominator =
          f + this.k1 * (1 - this.b + (this.b * docLen) / this.avgdl);
        score += idf * (numerator / denominator);
      }
      scores.push([idx, score]);
    }

    scores.sort((a, b) => b[1] - a[1]);
    return scores
      .slice(0, topK)
      .filter(([, s]) => s > 0)
      .map(([idx, score]) => [this.corpus[idx]!, score]);
  }

  private tokenize(text: string): string[] {
    return text.toLowerCase().match(/\w+/g) ?? [];
  }
}

// ---------------------------------------------------------------------------
// In-Memory Vector Store
// ---------------------------------------------------------------------------

function cosineSimilarity(a: number[], b: number[]): number {
  let dot = 0;
  let normA = 0;
  let normB = 0;
  for (let i = 0; i < a.length; i++) {
    dot += a[i]! * b[i]!;
    normA += a[i]! * a[i]!;
    normB += b[i]! * b[i]!;
  }
  if (normA === 0 || normB === 0) return 0;
  return dot / (Math.sqrt(normA) * Math.sqrt(normB));
}

export class InMemoryVectorStore {
  private chunks: Chunk[] = [];
  private vectors: number[][] = [];

  add(chunks: readonly Chunk[], vectors: readonly number[][]): void {
    if (chunks.length !== vectors.length) {
      throw new Error("chunks and vectors must have the same length");
    }
    this.chunks.push(...chunks);
    this.vectors.push(...vectors);
  }

  search(queryVector: number[], topK: number = 5): [Chunk, number][] {
    if (this.vectors.length === 0) return [];

    const scores = this.chunks.map((chunk, i) => {
      const score = cosineSimilarity(queryVector, this.vectors[i]!);
      return [chunk, score] as [Chunk, number];
    });

    scores.sort((a, b) => b[1] - a[1]);
    return scores.slice(0, topK);
  }

  clear(): void {
    this.chunks = [];
    this.vectors = [];
  }

  get length(): number {
    return this.chunks.length;
  }
}

// ---------------------------------------------------------------------------
// Chunking strategies
// ---------------------------------------------------------------------------

export class TextChunker {
  static fixedSize(
    doc: Document,
    chunkSize: number = 1000,
    chunkOverlap: number = 200,
  ): Chunk[] {
    const chunks: Chunk[] = [];
    const text = doc.content;
    let i = 0;

    while (i < text.length) {
      const end = Math.min(i + chunkSize, text.length);
      const chunkText = text.slice(i, end);
      chunks.push(
        new Chunk(chunkText, doc.docId, chunks.length, {
          ...doc.metadata,
          chunk_start: i,
          chunk_end: end,
        }),
      );
      if (end >= text.length) break;
      i = end - chunkOverlap;
    }
    return chunks;
  }

  static semantic(
    doc: Document,
    maxChunkSize: number = 2000,
    separators: string[] = ["\n\n", "\n", ". ", "! ", "? ", "; ", " "],
  ): Chunk[] {
    function split(text: string, sepIndex: number = 0): string[] {
      if (text.length <= maxChunkSize || sepIndex >= separators.length) {
        return [text];
      }
      const sep = separators[sepIndex]!;
      const parts = text.split(sep);
      const result: string[] = [];
      let current = "";

      for (const part of parts) {
        if (current.length + part.length + sep.length <= maxChunkSize) {
          current = current ? current + sep + part : part;
        } else {
          if (current) result.push(...split(current, sepIndex + 1));
          current = part;
        }
      }
      if (current) result.push(...split(current, sepIndex + 1));
      return result;
    }

    const segments = split(doc.content);
    return segments.map(
      (seg, i) =>
        new Chunk(seg, doc.docId, i, {
          ...doc.metadata,
          chunk_strategy: "semantic",
        }),
    );
  }
}

// ---------------------------------------------------------------------------
// Generator types
// ---------------------------------------------------------------------------

export type GeneratorFn = (
  query: string,
  context: string,
  model: string,
) => Promise<string>;

// ---------------------------------------------------------------------------
// Claude Generator
// ---------------------------------------------------------------------------

export class ClaudeGenerator {
  private readonly apiKey: string;
  private readonly baseUrl: string;
  private readonly apiVersion: string;

  constructor(
    apiKey: string,
    baseUrl: string = "https://api.anthropic.com/v1/messages",
    apiVersion: string = "2023-06-01",
  ) {
    this.apiKey = apiKey;
    this.baseUrl = baseUrl;
    this.apiVersion = apiVersion;
  }

  async generate(
    query: string,
    context: string,
    model: string,
  ): Promise<string> {
    const systemPrompt =
      "You are a precise, factual assistant. Answer the user's question " +
      "using ONLY the provided context. If the context does not contain " +
      "sufficient information, state that clearly. Cite sources when possible.";

    const userMessage =
      `Context:\n${context}\n\n` +
      `Question: ${query}\n\n` +
      `Answer based on the context above.`;

    const resp = await fetch(this.baseUrl, {
      method: "POST",
      headers: {
        "x-api-key": this.apiKey,
        "anthropic-version": this.apiVersion,
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        model,
        max_tokens: 1024,
        system: systemPrompt,
        messages: [
          {
            role: "user",
            content: [{ type: "text", text: userMessage }],
          },
        ],
      }),
    });

    if (!resp.ok) throw new Error(`Claude API error: ${resp.status}`);
    const data = (await resp.json()) as {
      content: { type: string; text: string }[];
    };

    for (const block of data.content) {
      if (block.type === "text") return block.text;
    }
    return "";
  }
}

// ---------------------------------------------------------------------------
// RAG Pipeline
// ---------------------------------------------------------------------------

export interface RAGPipelineConfig {
  embedder: Embedder;
  generateFn?: GeneratorFn;
  chunkSize?: number;
  chunkOverlap?: number;
  topK?: number;
  defaultStrategy?: string;
}

export class RAGPipeline {
  readonly embedder: Embedder;
  readonly generateFn?: GeneratorFn;
  readonly chunkSize: number;
  readonly chunkOverlap: number;
  readonly topK: number;
  readonly defaultStrategy: string;

  private vectorStore: InMemoryVectorStore = new InMemoryVectorStore();
  private bm25: BM25 = new BM25();
  private allChunks: Chunk[] = [];

  constructor(config: RAGPipelineConfig) {
    this.embedder = config.embedder;
    this.generateFn = config.generateFn;
    this.chunkSize = config.chunkSize ?? 1000;
    this.chunkOverlap = config.chunkOverlap ?? 200;
    this.topK = config.topK ?? 5;
    this.defaultStrategy = config.defaultStrategy ?? "hybrid";
  }

  // ----------------------------------------------------------------
  // Ingestion
  // ----------------------------------------------------------------

  async ingest(
    documents: readonly Document[],
    options?: {
      chunkSize?: number;
      chunkOverlap?: number;
      chunkStrategy?: string;
    },
  ): Promise<number> {
    const cs = options?.chunkSize ?? this.chunkSize;
    const co = options?.chunkOverlap ?? this.chunkOverlap;
    const strategy = options?.chunkStrategy ?? "fixed";

    const allChunks: Chunk[] = [];
    for (const doc of documents) {
      const chunks =
        strategy === "semantic"
          ? TextChunker.semantic(doc, cs)
          : TextChunker.fixedSize(doc, cs, co);
      allChunks.push(...chunks);
    }

    if (allChunks.length === 0) return 0;

    // Generate embeddings
    const texts = allChunks.map((c) => c.content);
    const vectors = await this.embedder.embed(texts);

    // Index dense
    this.vectorStore.add(allChunks, vectors);

    // Index sparse
    this.allChunks = [...this.allChunks, ...allChunks];
    this.bm25.index(this.allChunks);

    return allChunks.length;
  }

  // ----------------------------------------------------------------
  // Retrieval
  // ----------------------------------------------------------------

  async retrieve(
    query: string,
    options?: {
      topK?: number;
      strategy?: string;
    },
  ): Promise<RetrievalResultDict[]> {
    const k = options?.topK ?? this.topK;
    const strat = options?.strategy ?? this.defaultStrategy;

    let results: RetrievalResult[];
    if (strat === "sparse") {
      results = this.sparseRetrieve(query, k);
    } else if (strat === "dense") {
      results = await this.denseRetrieve(query, k);
    } else if (strat === "hybrid") {
      results = await this.hybridRetrieve(query, k);
    } else {
      throw new Error(`Unknown retrieval strategy: ${strat}`);
    }

    return results.map((r) => ({
      content: r.chunk.content,
      docId: r.chunk.docId,
      score: r.score,
      chunkId: r.chunk.chunkId,
      strategy: r.strategy,
      metadata: { ...r.chunk.metadata },
    }));
  }

  private sparseRetrieve(query: string, topK: number): RetrievalResult[] {
    const hits = this.bm25.search(query, topK);
    return hits.map(([chunk, score]) => ({
      chunk,
      score,
      strategy: "sparse" as const,
    }));
  }

  private async denseRetrieve(
    query: string,
    topK: number,
  ): Promise<RetrievalResult[]> {
    const qv = await this.embedder.embedQuery(query);
    const hits = this.vectorStore.search(qv, topK);
    return hits.map(([chunk, score]) => ({
      chunk,
      score,
      strategy: "dense" as const,
    }));
  }

  private async hybridRetrieve(
    query: string,
    topK: number,
  ): Promise<RetrievalResult[]> {
    const sparseResults = this.sparseRetrieve(query, topK * 3);
    const denseResults = await this.denseRetrieve(query, topK * 3);

    const rrfScores = new Map<
      string,
      { chunk: Chunk; score: number }
    >();
    const rrfK = 60;

    sparseResults.forEach((result, rank) => {
      const key = result.chunk.chunkId;
      const score = 1.0 / (rrfK + rank + 1);
      const existing = rrfScores.get(key);
      rrfScores.set(key, {
        chunk: result.chunk,
        score: (existing?.score ?? 0) + score,
      });
    });

    denseResults.forEach((result, rank) => {
      const key = result.chunk.chunkId;
      const score = 1.0 / (rrfK + rank + 1);
      const existing = rrfScores.get(key);
      rrfScores.set(key, {
        chunk: result.chunk,
        score: (existing?.score ?? 0) + score,
      });
    });

    const sorted = [...rrfScores.values()].sort(
      (a, b) => b.score - a.score,
    );

    return sorted.slice(0, topK).map(({ chunk, score }) => ({
      chunk,
      score,
      strategy: "hybrid" as const,
    }));
  }

  // ----------------------------------------------------------------
  // Generation
  // ----------------------------------------------------------------

  async generate(
    query: string,
    context: string,
    model: string = "claude-sonnet-4-20250514",
  ): Promise<string> {
    if (!this.generateFn) {
      throw new Error(
        "No generateFn configured. Pass a GeneratorFn to RAGPipeline config.",
      );
    }
    return this.generateFn(query, context, model);
  }

  // ----------------------------------------------------------------
  // End-to-end
  // ----------------------------------------------------------------

  async query(
    query: string,
    options?: {
      topK?: number;
      strategy?: string;
      model?: string;
    },
  ): Promise<QueryResult> {
    const retrieved = await this.retrieve(query, options);
    const context = retrieved
      .map((r) => `[Source: ${r.docId}] ${r.content}`)
      .join("\n\n---\n\n");

    const answer = await this.generate(
      query,
      context,
      options?.model ?? "claude-sonnet-4-20250514",
    );

    return {
      answer,
      retrievedChunks: retrieved,
      strategy: options?.strategy ?? this.defaultStrategy,
    };
  }

  // ----------------------------------------------------------------
  // Management
  // ----------------------------------------------------------------

  clear(): void {
    this.vectorStore.clear();
    this.bm25 = new BM25();
    this.allChunks = [];
  }

  get chunkCount(): number {
    return this.allChunks.length;
  }
}
