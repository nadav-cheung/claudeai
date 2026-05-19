/**
 * Chapter 6: Embedding-based Tool Search (TypeScript).
 *
 * Semantic tool discovery using cosine similarity over hash-based
 * embedding vectors. Mirrors Anthropic's Tool Search Tool behavior
 * with custom embedding-based search.
 */

interface ToolSearchEntryData {
  name: string;
  description: string;
  input_schema: Record<string, unknown>;
}

interface SearchResult {
  name: string;
  description: string;
  input_schema: Record<string, unknown>;
  score: number;
}

/**
 * Semantic tool search using embedding-based cosine similarity.
 *
 * Usage:
 * ```typescript
 * const search = new EmbeddingToolSearch(384);
 * search.indexTools([...toolDefinitions]);
 * const results = search.search("weather forecast", 3);
 * ```
 */
export class EmbeddingToolSearch {
  private tools: ToolSearchEntryData[] = [];
  private embeddings: number[][] | null = null;
  private readonly dim: number;

  constructor(embeddingDim: number = 384) {
    if (embeddingDim <= 0) {
      throw new Error("embeddingDim must be positive");
    }
    this.dim = embeddingDim;
  }

  // ------------------------------------------------------------------
  // Indexing
  // ------------------------------------------------------------------

  indexTools(
    tools: Array<{
      name: string;
      description: string;
      input_schema: Record<string, unknown>;
    }>,
  ): void {
    this.tools = tools.map((t) => ({
      name: t.name,
      description: t.description ?? "",
      input_schema: t.input_schema ?? { type: "object", properties: {} },
    }));

    const texts = this.tools.map((t) => this.toSearchText(t));
    this.embeddings = this.computeEmbeddings(texts);
  }

  private toSearchText(entry: ToolSearchEntryData): string {
    const parts: string[] = [entry.name, entry.description];
    const props = (entry.input_schema as Record<string, unknown>)
      .properties as Record<string, Record<string, unknown>> | undefined;
    if (props) {
      for (const [propName, propDef] of Object.entries(props)) {
        parts.push(propName);
        if (propDef && typeof propDef.description === "string") {
          parts.push(propDef.description);
        }
      }
    }
    return parts.join(" ");
  }

  private computeEmbeddings(texts: string[]): number[][] {
    return texts.map((text) => {
      const tokens = text.toLowerCase().split(/\s+/);
      const vec = new Array<number>(this.dim).fill(0);
      for (const token of tokens) {
        const idx = this.hashToken(token) % this.dim;
        vec[idx] += 1.0;
      }
      // L2 normalize
      const norm = Math.sqrt(vec.reduce((s, v) => s + v * v, 0));
      if (norm > 0) {
        for (let i = 0; i < vec.length; i++) {
          vec[i] /= norm;
        }
      }
      return vec;
    });
  }

  private hashToken(token: string): number {
    let hash = 0;
    for (let i = 0; i < token.length; i++) {
      const char = token.charCodeAt(i);
      hash = ((hash << 5) - hash + char) | 0;
    }
    return Math.abs(hash);
  }

  // ------------------------------------------------------------------
  // Search
  // ------------------------------------------------------------------

  search(query: string, topK: number = 5): SearchResult[] {
    if (this.tools.length === 0 || !this.embeddings) {
      return [];
    }

    const queryEmb = this.computeEmbeddings([query])[0]!;
    const scores: Array<{ index: number; score: number }> = [];

    for (let i = 0; i < this.embeddings.length; i++) {
      scores.push({
        index: i,
        score: EmbeddingToolSearch.cosineSimilarity(
          queryEmb,
          this.embeddings[i]!,
        ),
      });
    }

    scores.sort((a, b) => b.score - a.score);

    return scores.slice(0, topK).map(({ index, score }) => ({
      name: this.tools[index]!.name,
      description: this.tools[index]!.description,
      input_schema: this.tools[index]!.input_schema,
      score: Math.round(score * 10000) / 10000,
    }));
  }

  searchByRegex(
    pattern: string,
  ): Array<{
    name: string;
    description: string;
    input_schema: Record<string, unknown>;
  }> {
    const regex = new RegExp(pattern);
    return this.tools
      .filter((t) => regex.test(this.toSearchText(t)))
      .map((t) => ({
        name: t.name,
        description: t.description,
        input_schema: t.input_schema,
      }));
  }

  // ------------------------------------------------------------------
  // Utilities
  // ------------------------------------------------------------------

  static cosineSimilarity(a: number[], b: number[]): number {
    if (a.length !== b.length) {
      throw new Error(
        `Vector dimension mismatch: ${a.length} vs ${b.length}`,
      );
    }
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

  // ------------------------------------------------------------------
  // Properties
  // ------------------------------------------------------------------

  getToolCount(): number {
    return this.tools.length;
  }

  getEmbeddingDim(): number {
    return this.dim;
  }

  get isIndexed(): boolean {
    return this.embeddings !== null && this.tools.length > 0;
  }
}
