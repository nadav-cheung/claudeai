/**
 * Chapter 10: Citation Parser (TypeScript).
 *
 * Protocol-level implementation of Anthropic's Citations API,
 * parsing structured citation data from Claude responses and
 * formatting it into human-readable reference lists.
 */

// ---------------------------------------------------------------------------
// Citation Types
// ---------------------------------------------------------------------------

export enum CitationType {
  CHAR_LOCATION = "char_location",
  PAGE_LOCATION = "page_location",
  CONTENT_BLOCK_LOCATION = "content_block_location",
  WEB_SEARCH_RESULT_LOCATION = "web_search_result_location",
  SEARCH_RESULT_LOCATION = "search_result_location",
}

// ---------------------------------------------------------------------------
// Citation Data Model
// ---------------------------------------------------------------------------

export interface CitationData {
  cited_text: string;
  document_title: string;
  citation_type: CitationType;
  document_index: number;
  file_id?: string;
  // char_location
  start_char_index?: number;
  end_char_index?: number;
  // page_location
  start_page_number?: number;
  end_page_number?: number;
  // content_block_location
  start_block_index?: number;
  end_block_index?: number;
  // web search
  url?: string;
  // search result
  source?: string;
  search_result_index?: number;
}

export interface CitationSummary {
  total_citations: number;
  unique_citations: number;
  unique_documents: number;
  by_type: Record<string, number>;
  documents: string[];
}

// ---------------------------------------------------------------------------
// Citation Parser
// ---------------------------------------------------------------------------

/**
 * Parses and formats citations from Claude API responses.
 *
 * Handles extraction of citations from content blocks, deduplication,
 * and formatting for human-readable output (numbered references,
 * markdown, plain text).
 *
 * Usage:
 * ```typescript
 * const parser = new CitationParser();
 * const citations = parser.parseCitations(contentBlock);
 * const formatted = parser.formatReferences(citations);
 * ```
 */
export class CitationParser {
  /**
   * Extract all citations from a single content block.
   *
   * Handles both:
   * - Direct citations array on TextBlock (non-streaming)
   * - citations_delta within content_block_delta (streaming)
   */
  parseCitations(contentBlock: Record<string, unknown>): CitationData[] {
    const citations: CitationData[] = [];

    // Handle content_block_delta (streaming)
    if (contentBlock.type === "content_block_delta") {
      const delta = (contentBlock.delta as Record<string, unknown>) ?? {};
      if (delta.type === "citations_delta") {
        const citationData = (delta.citation as Record<string, unknown>) ?? {};
        const parsed = this.parseSingleCitation(citationData);
        if (parsed) citations.push(parsed);
      }
      return citations;
    }

    // Handle direct citations array (non-streaming TextBlock)
    if (Array.isArray(contentBlock.citations)) {
      for (const citationData of contentBlock.citations) {
        const parsed = this.parseSingleCitation(citationData as Record<string, unknown>);
        if (parsed) citations.push(parsed);
      }
    }

    // Handle content array (nested within messages)
    if (Array.isArray(contentBlock.content)) {
      for (const block of contentBlock.content) {
        if (typeof block === "object" && block !== null && Array.isArray((block as Record<string, unknown>).citations)) {
          const blockCitations = (block as Record<string, unknown>).citations as Array<Record<string, unknown>>;
          for (const citationData of blockCitations) {
            const parsed = this.parseSingleCitation(citationData);
            if (parsed) citations.push(parsed);
          }
        }
      }
    }

    return citations;
  }

  /**
   * Extract all citations from a full Messages API response.
   */
  parseResponse(response: Record<string, unknown>): CitationData[] {
    const allCitations: CitationData[] = [];
    const content = (response.content as Array<Record<string, unknown>>) ?? [];
    for (const block of content) {
      allCitations.push(...this.parseCitations(block));
    }
    return allCitations;
  }

  private parseSingleCitation(data: Record<string, unknown>): CitationData | null {
    if (!data || typeof data !== "object") return null;

    const typeStr = data.type as string;
    if (!Object.values(CitationType).includes(typeStr as CitationType)) {
      return null;
    }

    return {
      cited_text: (data.cited_text as string) ?? "",
      document_title: (data.document_title as string) ?? "",
      citation_type: typeStr as CitationType,
      document_index: (data.document_index as number) ?? 0,
      file_id: data.file_id as string | undefined,
      start_char_index: data.start_char_index as number | undefined,
      end_char_index: data.end_char_index as number | undefined,
      start_page_number: data.start_page_number as number | undefined,
      end_page_number: data.end_page_number as number | undefined,
      start_block_index: data.start_block_index as number | undefined,
      end_block_index: data.end_block_index as number | undefined,
      url: data.url as string | undefined,
      source: data.source as string | undefined,
      search_result_index: data.search_result_index as number | undefined,
    };
  }

  // ------------------------------------------------------------------
  // Location Summary
  // ------------------------------------------------------------------

  getLocationSummary(citation: CitationData): string {
    switch (citation.citation_type) {
      case CitationType.CHAR_LOCATION:
        return `chars ${citation.start_char_index}-${citation.end_char_index}`;
      case CitationType.PAGE_LOCATION:
        return `pages ${citation.start_page_number}-${citation.end_page_number}`;
      case CitationType.CONTENT_BLOCK_LOCATION:
        return `blocks ${citation.start_block_index}-${citation.end_block_index}`;
      case CitationType.WEB_SEARCH_RESULT_LOCATION:
        return citation.url ?? "web result";
      case CitationType.SEARCH_RESULT_LOCATION:
        return citation.search_result_index !== undefined
          ? `result #${citation.search_result_index}`
          : "search result";
      default:
        return "unknown";
    }
  }

  // ------------------------------------------------------------------
  // Formatting
  // ------------------------------------------------------------------

  /**
   * Format a single citation as a numbered reference line.
   */
  formatCitation(citation: CitationData, index: number): string {
    const cited = citation.cited_text.replace(/\n/g, " ").replace(/\r/g, " ")
      .replace(/\s+/g, " ");
    const location = this.getLocationSummary(citation);
    return `[${index}] "${cited}" found in "${citation.document_title}" (${location})`;
  }

  /**
   * Format all citations as a numbered reference list.
   * Deduplicates by (document_title, cited_text) key.
   */
  formatReferences(citations: CitationData[]): string {
    const deduped = this.deduplicate(citations);
    return deduped.map((c, i) => this.formatCitation(c, i + 1)).join("\n");
  }

  /**
   * Annotate text with citation markers.
   */
  annotateText(
    text: string,
    citations: CitationData[],
    style: "numbered" | "inline" = "numbered",
  ): string {
    const deduped = this.deduplicate(citations);

    if (deduped.length === 0) return text;

    if (style === "numbered") {
      const markers = deduped.map((_, i) => ` [${i + 1}]`).join("");
      return text + markers;
    } else {
      const notes = deduped.map(
        (c, i) => `  [${i + 1}] Source: ${c.document_title}`,
      );
      return text + "\n" + notes.join("\n");
    }
  }

  /**
   * Format citations as a Markdown reference section.
   */
  formatAsMarkdown(citations: CitationData[]): string {
    const deduped = this.deduplicate(citations);
    const lines = ["### References", ""];
    for (let i = 0; i < deduped.length; i++) {
      const c = deduped[i]!;
      const cited = c.cited_text.replace(/\n/g, " ").replace(/\r/g, " ")
        .replace(/\s+/g, " ");
      lines.push(
        `${i + 1}. **${c.document_title}** (${this.getLocationSummary(c)}): ` +
          `"${cited}"`,
      );
    }
    return lines.join("\n");
  }

  // ------------------------------------------------------------------
  // Deduplication
  // ------------------------------------------------------------------

  /**
   * Remove duplicate citations, keeping first occurrence.
   * Duplicates are identified by (document_title, cited_text).
   */
  deduplicate(citations: CitationData[]): CitationData[] {
    const seen = new Set<string>();
    const result: CitationData[] = [];
    for (const c of citations) {
      const key = `${c.document_title}::${c.cited_text.trim()}`;
      if (!seen.has(key)) {
        seen.add(key);
        result.push(c);
      }
    }
    return result;
  }

  // ------------------------------------------------------------------
  // Verification
  // ------------------------------------------------------------------

  /**
   * Verify that a citation's cited_text exists within the source.
   */
  verifyCitation(citation: CitationData, sourceText: string): boolean {
    const cited = citation.cited_text.replace(/\s+/g, " ").trim();
    const source = sourceText.replace(/\s+/g, " ").trim();
    return source.includes(cited);
  }

  /**
   * Verify all citations against their source documents.
   */
  verifyAll(
    citations: CitationData[],
    sources: Record<string, string>,
  ): Record<string, boolean> {
    const results: Record<string, boolean> = {};
    for (let i = 0; i < citations.length; i++) {
      const c = citations[i]!;
      const key = `[${i + 1}] ${c.document_title}`;
      const source = sources[c.document_title] ?? "";
      results[key] = this.verifyCitation(c, source);
    }
    return results;
  }

  // ------------------------------------------------------------------
  // Summary / Statistics
  // ------------------------------------------------------------------

  /**
   * Generate summary statistics for a set of citations.
   */
  summarize(citations: CitationData[]): CitationSummary {
    const types: Record<string, number> = {};
    const documents = new Set<string>();

    for (const c of citations) {
      types[c.citation_type] = (types[c.citation_type] ?? 0) + 1;
      if (c.document_title) {
        documents.add(c.document_title);
      }
    }

    return {
      total_citations: citations.length,
      unique_citations: this.deduplicate(citations).length,
      unique_documents: documents.size,
      by_type: types,
      documents: Array.from(documents).sort(),
    };
  }
}
