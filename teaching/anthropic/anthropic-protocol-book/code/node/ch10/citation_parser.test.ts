/**
 * Tests for Chapter 10: Citation Parser (TypeScript).
 */

import { describe, it, expect } from "vitest";
import { CitationParser, CitationType, CitationData } from "./CitationParser";

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------

function sampleCitations(): CitationData[] {
  return [
    {
      cited_text: "Once your order ships, you'll receive an email with a tracking number.",
      document_title: "Order Tracking Information",
      citation_type: CitationType.CHAR_LOCATION,
      document_index: 0,
      start_char_index: 0,
      end_char_index: 75,
    },
    {
      cited_text: "If you haven't received a tracking number within 48 hours, please contact support.",
      document_title: "Order Tracking Information",
      citation_type: CitationType.CHAR_LOCATION,
      document_index: 0,
      start_char_index: 76,
      end_char_index: 160,
    },
    {
      cited_text: "We experiment with methods for training a harmless AI assistant.",
      document_title: "Constitutional AI Paper",
      citation_type: CitationType.PAGE_LOCATION,
      document_index: 0,
      start_page_number: 1,
      end_page_number: 2,
    },
  ];
}

// ---------------------------------------------------------------------------
// parseCitations
// ---------------------------------------------------------------------------

describe("parseCitations", () => {
  it("parses char_location citations from a TextBlock", () => {
    const parser = new CitationParser();
    const block = {
      type: "text",
      text: "You'll receive an email with your tracking number.",
      citations: [
        {
          type: "char_location",
          cited_text: "Once your order ships, you'll receive an email.",
          document_index: 0,
          document_title: "Order Tracking Information",
        },
      ],
    };

    const citations = parser.parseCitations(block);
    expect(citations).toHaveLength(1);
    expect(citations[0]!.citation_type).toBe(CitationType.CHAR_LOCATION);
    expect(citations[0]!.document_title).toBe("Order Tracking Information");
  });

  it("parses page_location citations", () => {
    const parser = new CitationParser();
    const block = {
      type: "text",
      text: "answer",
      citations: [
        {
          type: "page_location",
          cited_text: "We experiment with methods.",
          document_index: 0,
          document_title: "Constitutional AI Paper",
          start_page_number: 1,
          end_page_number: 2,
        },
      ],
    };

    const citations = parser.parseCitations(block);
    expect(citations).toHaveLength(1);
    expect(citations[0]!.citation_type).toBe(CitationType.PAGE_LOCATION);
    expect(citations[0]!.start_page_number).toBe(1);
    expect(citations[0]!.end_page_number).toBe(2);
  });

  it("parses content_block_location citations", () => {
    const parser = new CitationParser();
    const block = {
      type: "text",
      text: "answer",
      citations: [
        {
          type: "content_block_location",
          cited_text: "Full article text.",
          document_index: 0,
          document_title: "Order Tracking Information",
          start_block_index: 0,
          end_block_index: 0,
        },
      ],
    };

    const citations = parser.parseCitations(block);
    expect(citations).toHaveLength(1);
    expect(citations[0]!.citation_type).toBe(CitationType.CONTENT_BLOCK_LOCATION);
  });

  it("parses streaming content_block_delta with citations_delta", () => {
    const parser = new CitationParser();
    const deltaBlock = {
      type: "content_block_delta",
      index: 0,
      delta: {
        type: "citations_delta",
        citation: {
          type: "char_location",
          cited_text: "Once your order ships.",
          document_index: 0,
          document_title: "Order Tracking Information",
          start_char_index: 0,
          end_char_index: 60,
        },
      },
    };

    const citations = parser.parseCitations(deltaBlock);
    expect(citations).toHaveLength(1);
    expect(citations[0]!.citation_type).toBe(CitationType.CHAR_LOCATION);
  });

  it("returns empty for block without citations", () => {
    const parser = new CitationParser();
    expect(parser.parseCitations({ type: "text", text: "No citations" })).toHaveLength(0);
  });

  it("filters out unknown citation types", () => {
    const parser = new CitationParser();
    const block = {
      type: "text",
      text: "test",
      citations: [
        {
          type: "invalid_type",
          cited_text: "some text",
          document_title: "Some Doc",
        },
      ],
    };
    expect(parser.parseCitations(block)).toHaveLength(0);
  });

  it("parses multiple citations", () => {
    const parser = new CitationParser();
    const block = {
      type: "text",
      text: "answer",
      citations: [
        { type: "char_location", cited_text: "Text A.", document_title: "Doc A" },
        { type: "char_location", cited_text: "Text B.", document_title: "Doc B" },
      ],
    };
    expect(parser.parseCitations(block)).toHaveLength(2);
  });

  it("parses from content array", () => {
    const parser = new CitationParser();
    const block = {
      content: [
        {
          type: "text",
          text: "answer",
          citations: [
            { type: "char_location", cited_text: "Cited.", document_title: "Test Doc" },
          ],
        },
      ],
    };
    expect(parser.parseCitations(block)).toHaveLength(1);
  });

  it("parses full response", () => {
    const parser = new CitationParser();
    const response = {
      id: "msg_123",
      content: [
        {
          type: "text",
          text: "First part",
          citations: [
            { type: "char_location", cited_text: "Source A.", document_title: "Doc A" },
          ],
        },
        {
          type: "text",
          text: "Second part",
          citations: [
            {
              type: "page_location",
              cited_text: "Source B.",
              document_title: "Doc B",
              start_page_number: 3,
              end_page_number: 4,
            },
          ],
        },
      ],
    };
    expect(parser.parseResponse(response)).toHaveLength(2);
  });
});

// ---------------------------------------------------------------------------
// Formatting
// ---------------------------------------------------------------------------

describe("Formatting", () => {
  it("formats a single citation", () => {
    const parser = new CitationParser();
    const formatted = parser.formatCitation(sampleCitations()[0]!, 1);
    expect(formatted).toMatch(/^\[1\]/);
    expect(formatted).toContain("Order Tracking Information");
  });

  it("formats page citation", () => {
    const parser = new CitationParser();
    const formatted = parser.formatCitation(sampleCitations()[2]!, 3);
    expect(formatted).toMatch(/^\[3\]/);
    expect(formatted).toContain("Constitutional AI Paper");
    expect(formatted).toContain("pages 1-2");
  });

  it("formats references with deduplication", () => {
    const parser = new CitationParser();
    const formatted = parser.formatReferences(sampleCitations());
    const lines = formatted.split("\n");
    expect(lines.length).toBeGreaterThanOrEqual(2);
    expect(lines[0]).toMatch(/^\[1\]/);
  });

  it("deduplicates exact matches in formatReferences", () => {
    const parser = new CitationParser();
    const dup: CitationData = {
      cited_text: "Same cited text.",
      document_title: "Same Doc",
      citation_type: CitationType.CHAR_LOCATION,
      document_index: 0,
    };
    const formatted = parser.formatReferences([dup, dup, dup]);
    const lines = formatted.split("\n");
    expect(lines).toHaveLength(1);
  });

  it("formats as markdown", () => {
    const parser = new CitationParser();
    const md = parser.formatAsMarkdown(sampleCitations());
    expect(md).toContain("### References");
    expect(md).toContain("**Order Tracking Information**");
    expect(md).toContain("**Constitutional AI Paper**");
  });
});

// ---------------------------------------------------------------------------
// annotateText
// ---------------------------------------------------------------------------

describe("annotateText", () => {
  it("annotates with numbered style", () => {
    const parser = new CitationParser();
    const text = "Here is the answer.";
    const annotated = parser.annotateText(text, sampleCitations(), "numbered");
    expect(annotated).toContain("[1]");
    expect(annotated).toContain(text);
  });

  it("annotates with inline style", () => {
    const parser = new CitationParser();
    const text = "Here is the answer.";
    const annotated = parser.annotateText(text, sampleCitations(), "inline");
    expect(annotated).toContain("Source:");
    expect(annotated).toContain("Order Tracking Information");
  });

  it("returns text unchanged for empty citations", () => {
    const parser = new CitationParser();
    expect(parser.annotateText("Just text.", [])).toBe("Just text.");
  });

  it("uses numbered as default style", () => {
    const parser = new CitationParser();
    const annotated = parser.annotateText("Hello.", sampleCitations());
    expect(annotated).toContain("[1]");
  });
});

// ---------------------------------------------------------------------------
// Deduplication
// ---------------------------------------------------------------------------

describe("deduplicate", () => {
  it("removes exact duplicates", () => {
    const parser = new CitationParser();
    const c1: CitationData = {
      cited_text: "Same text.",
      document_title: "Same Doc",
      citation_type: CitationType.CHAR_LOCATION,
      document_index: 0,
    };
    const c2 = { ...c1 };
    expect(parser.deduplicate([c1, c2])).toHaveLength(1);
  });

  it("keeps different cited_text in same doc", () => {
    const parser = new CitationParser();
    const c1: CitationData = {
      cited_text: "Text A.",
      document_title: "Doc",
      citation_type: CitationType.CHAR_LOCATION,
      document_index: 0,
    };
    const c2: CitationData = {
      cited_text: "Text B.",
      document_title: "Doc",
      citation_type: CitationType.CHAR_LOCATION,
      document_index: 0,
    };
    expect(parser.deduplicate([c1, c2])).toHaveLength(2);
  });

  it("keeps same text in different docs", () => {
    const parser = new CitationParser();
    const c1: CitationData = {
      cited_text: "Same text.",
      document_title: "Doc A",
      citation_type: CitationType.CHAR_LOCATION,
      document_index: 0,
    };
    const c2: CitationData = {
      cited_text: "Same text.",
      document_title: "Doc B",
      citation_type: CitationType.CHAR_LOCATION,
      document_index: 0,
    };
    expect(parser.deduplicate([c1, c2])).toHaveLength(2);
  });

  it("handles empty list", () => {
    const parser = new CitationParser();
    expect(parser.deduplicate([])).toHaveLength(0);
  });
});

// ---------------------------------------------------------------------------
// Verification
// ---------------------------------------------------------------------------

describe("Verification", () => {
  it("verifies citation found in source", () => {
    const parser = new CitationParser();
    const c: CitationData = {
      cited_text: "The quick brown fox.",
      document_title: "Test",
      citation_type: CitationType.CHAR_LOCATION,
      document_index: 0,
    };
    expect(parser.verifyCitation(c, "Lorem ipsum. The quick brown fox. Dolor.")).toBe(true);
  });

  it("verifies citation not found in source", () => {
    const parser = new CitationParser();
    const c: CitationData = {
      cited_text: "Missing text.",
      document_title: "Test",
      citation_type: CitationType.CHAR_LOCATION,
      document_index: 0,
    };
    expect(parser.verifyCitation(c, "Completely different content.")).toBe(false);
  });

  it("verifyAll returns correct results", () => {
    const parser = new CitationParser();
    const c1: CitationData = {
      cited_text: "The quick brown fox.",
      document_title: "Doc A",
      citation_type: CitationType.CHAR_LOCATION,
      document_index: 0,
    };
    const c2: CitationData = {
      cited_text: "Missing in source.",
      document_title: "Doc A",
      citation_type: CitationType.CHAR_LOCATION,
      document_index: 0,
    };
    const results = parser.verifyAll([c1, c2], {
      "Doc A": "Lorem ipsum. The quick brown fox. Dolor sit amet.",
    });
    const keys = Object.keys(results);
    expect(results[keys[0]!]).toBe(true);
    expect(results[keys[1]!]).toBe(false);
  });

  it("normalizes whitespace for comparison", () => {
    const parser = new CitationParser();
    const c: CitationData = {
      cited_text: "The   quick\nbrown   fox.",
      document_title: "Test",
      citation_type: CitationType.CHAR_LOCATION,
      document_index: 0,
    };
    expect(parser.verifyCitation(c, "The quick brown fox.")).toBe(true);
  });
});

// ---------------------------------------------------------------------------
// Summarize
// ---------------------------------------------------------------------------

describe("summarize", () => {
  it("summarizes citation statistics", () => {
    const parser = new CitationParser();
    const summary = parser.summarize(sampleCitations());
    expect(summary.total_citations).toBe(3);
    expect(summary.unique_citations).toBe(3);
    expect(summary.unique_documents).toBe(2);
    expect(summary.by_type["char_location"]).toBe(2);
    expect(summary.by_type["page_location"]).toBe(1);
    expect(summary.documents).toContain("Constitutional AI Paper");
  });

  it("counts duplicate citations correctly", () => {
    const parser = new CitationParser();
    const c: CitationData = {
      cited_text: "Same text.",
      document_title: "Doc",
      citation_type: CitationType.CHAR_LOCATION,
      document_index: 0,
    };
    const summary = parser.summarize([c, c, c]);
    expect(summary.total_citations).toBe(3);
    expect(summary.unique_citations).toBe(1);
  });
});

// ---------------------------------------------------------------------------
// getLocationSummary
// ---------------------------------------------------------------------------

describe("getLocationSummary", () => {
  it("formats char location", () => {
    const parser = new CitationParser();
    const c: CitationData = {
      cited_text: "text",
      document_title: "Doc",
      citation_type: CitationType.CHAR_LOCATION,
      document_index: 0,
      start_char_index: 10,
      end_char_index: 50,
    };
    expect(parser.getLocationSummary(c)).toBe("chars 10-50");
  });

  it("formats page location", () => {
    const parser = new CitationParser();
    const c: CitationData = {
      cited_text: "text",
      document_title: "Doc",
      citation_type: CitationType.PAGE_LOCATION,
      document_index: 0,
      start_page_number: 3,
      end_page_number: 5,
    };
    expect(parser.getLocationSummary(c)).toBe("pages 3-5");
  });

  it("formats content block location", () => {
    const parser = new CitationParser();
    const c: CitationData = {
      cited_text: "text",
      document_title: "Doc",
      citation_type: CitationType.CONTENT_BLOCK_LOCATION,
      document_index: 0,
      start_block_index: 0,
      end_block_index: 2,
    };
    expect(parser.getLocationSummary(c)).toBe("blocks 0-2");
  });

  it("formats web search location", () => {
    const parser = new CitationParser();
    const c: CitationData = {
      cited_text: "text",
      document_title: "Web",
      citation_type: CitationType.WEB_SEARCH_RESULT_LOCATION,
      document_index: 0,
      url: "https://example.com",
    };
    expect(parser.getLocationSummary(c)).toBe("https://example.com");
  });

  it("formats search result location", () => {
    const parser = new CitationParser();
    const c: CitationData = {
      cited_text: "text",
      document_title: "Result",
      citation_type: CitationType.SEARCH_RESULT_LOCATION,
      document_index: 0,
      search_result_index: 5,
    };
    expect(parser.getLocationSummary(c)).toBe("result #5");
  });
});
