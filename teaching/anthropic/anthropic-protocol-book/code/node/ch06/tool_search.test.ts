/**
 * Tests for Chapter 6: Embedding-based Tool Search (TypeScript).
 */

import { describe, it, expect, beforeEach } from "vitest";
import { EmbeddingToolSearch } from "./ToolSearch";

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------

const sampleTools = [
  {
    name: "github_create_pr",
    description:
      "Create a pull request on GitHub with title, description, and target branch",
    input_schema: {
      type: "object" as const,
      properties: {
        title: { type: "string", description: "PR title" },
        body: { type: "string", description: "PR description" },
        base: { type: "string", description: "Target branch" },
        head: { type: "string", description: "Source branch" },
      },
      required: ["title", "base", "head"],
    },
  },
  {
    name: "github_list_issues",
    description:
      "List GitHub issues with optional filters for state, labels, and assignee",
    input_schema: {
      type: "object" as const,
      properties: {
        state: { type: "string", description: "open, closed, or all" },
        labels: { type: "array", items: { type: "string" } },
      },
      required: [],
    },
  },
  {
    name: "slack_send_message",
    description:
      "Send a message to a Slack channel or direct message. Supports markdown formatting.",
    input_schema: {
      type: "object" as const,
      properties: {
        channel: { type: "string", description: "Channel ID or name" },
        text: {
          type: "string",
          description: "Message content with markdown",
        },
      },
      required: ["channel", "text"],
    },
  },
  {
    name: "slack_list_channels",
    description: "List all Slack channels in the workspace",
    input_schema: {
      type: "object" as const,
      properties: {
        exclude_archived: {
          type: "boolean",
          description: "Filter out archived channels",
        },
      },
      required: [],
    },
  },
  {
    name: "get_weather",
    description:
      "Get current weather conditions for a specific location including temperature, humidity, and wind speed",
    input_schema: {
      type: "object" as const,
      properties: {
        location: {
          type: "string",
          description: "City name with optional country code",
        },
        unit: { type: "string", description: "celsius or fahrenheit" },
      },
      required: ["location"],
    },
  },
  {
    name: "get_forecast",
    description:
      "Get 5-day weather forecast for a location with daily high/low temperatures and conditions",
    input_schema: {
      type: "object" as const,
      properties: {
        location: { type: "string", description: "City name" },
        days: { type: "integer", description: "Number of days (1-5)" },
      },
      required: ["location"],
    },
  },
  {
    name: "jira_create_ticket",
    description:
      "Create a Jira ticket with title, description, priority, and assignee",
    input_schema: {
      type: "object" as const,
      properties: {
        project: { type: "string", description: "Jira project key" },
        summary: { type: "string", description: "Ticket summary" },
        priority: { type: "string", description: "Priority level" },
      },
      required: ["project", "summary"],
    },
  },
  {
    name: "database_query",
    description:
      "Execute SQL queries against the internal PostgreSQL database. Returns results as JSON array of row objects.",
    input_schema: {
      type: "object" as const,
      properties: {
        sql: { type: "string", description: "SQL query to execute" },
        params: { type: "array", description: "Query parameters" },
      },
      required: ["sql"],
    },
  },
  {
    name: "send_email",
    description:
      "Send an email via SMTP with to, cc, subject, and body fields",
    input_schema: {
      type: "object" as const,
      properties: {
        to: { type: "string", description: "Recipient email" },
        subject: { type: "string", description: "Email subject" },
        body: { type: "string", description: "Email body (HTML supported)" },
      },
      required: ["to", "subject", "body"],
    },
  },
  {
    name: "read_file",
    description:
      "Read contents of a file from the local filesystem at the given path",
    input_schema: {
      type: "object" as const,
      properties: {
        path: { type: "string", description: "Absolute file path" },
        encoding: {
          type: "string",
          description: "File encoding (default utf-8)",
        },
      },
      required: ["path"],
    },
  },
];

let indexedSearch: EmbeddingToolSearch;

beforeEach(() => {
  indexedSearch = new EmbeddingToolSearch(384);
  indexedSearch.indexTools(sampleTools);
});

// ---------------------------------------------------------------------------
// Initialization
// ---------------------------------------------------------------------------

describe("Initialization", () => {
  it("has default dimension 384", () => {
    const search = new EmbeddingToolSearch();
    expect(search.getEmbeddingDim()).toBe(384);
    expect(search.getToolCount()).toBe(0);
    expect(search.isIndexed).toBe(false);
  });

  it("accepts custom dimension", () => {
    const search = new EmbeddingToolSearch(768);
    expect(search.getEmbeddingDim()).toBe(768);
  });

  it("throws on zero dimension", () => {
    expect(() => new EmbeddingToolSearch(0)).toThrow(/positive/);
  });

  it("throws on negative dimension", () => {
    expect(() => new EmbeddingToolSearch(-1)).toThrow(/positive/);
  });
});

// ---------------------------------------------------------------------------
// Indexing
// ---------------------------------------------------------------------------

describe("Indexing", () => {
  it("sets tool count after indexing", () => {
    const search = new EmbeddingToolSearch();
    expect(search.getToolCount()).toBe(0);
    search.indexTools(sampleTools);
    expect(search.getToolCount()).toBe(10);
    expect(search.isIndexed).toBe(true);
  });

  it("handles empty tool list", () => {
    const search = new EmbeddingToolSearch();
    search.indexTools([]);
    expect(search.getToolCount()).toBe(0);
  });

  it("preserves tool metadata", () => {
    const results = indexedSearch.searchByRegex("github");
    const names = results.map((r) => r.name);
    expect(names).toContain("github_create_pr");
    expect(names).toContain("github_list_issues");
  });

  it("re-indexing replaces tools", () => {
    const search = new EmbeddingToolSearch();
    search.indexTools([
      { name: "tool_a", description: "First", input_schema: { type: "object", properties: {}, required: [] } },
    ]);
    expect(search.getToolCount()).toBe(1);
    search.indexTools([
      { name: "tool_b", description: "Second", input_schema: { type: "object", properties: {}, required: [] } },
    ]);
    expect(search.getToolCount()).toBe(1);
  });
});

// ---------------------------------------------------------------------------
// Search
// ---------------------------------------------------------------------------

describe("Search", () => {
  it("finds slack-related tools for slack query", () => {
    const results = indexedSearch.search("send message to slack", 3);
    expect(results.length).toBeGreaterThan(0);
    const names = results.map((r) => r.name);
    expect(names).toContain("slack_send_message");
  });

  it("finds weather tools for weather query", () => {
    const results = indexedSearch.search("what is the weather", 3);
    const names = results.map((r) => r.name);
    const hasWeather = names.includes("get_weather") || names.includes("get_forecast");
    expect(hasWeather).toBe(true);
  });

  it("finds github tools for PR query", () => {
    const results = indexedSearch.search("create github pull request", 3);
    const names = results.map((r) => r.name);
    expect(names).toContain("github_create_pr");
  });

  it("returns scores in [0, 1] range", () => {
    const results = indexedSearch.search("weather forecast", 5);
    for (const r of results) {
      expect(r.score).toBeGreaterThanOrEqual(0);
      expect(r.score).toBeLessThanOrEqual(1);
    }
  });

  it("returns scores in descending order", () => {
    const results = indexedSearch.search("query database", 5);
    for (let i = 1; i < results.length; i++) {
      expect(results[i - 1]!.score).toBeGreaterThanOrEqual(results[i]!.score);
    }
  });

  it("respects top_k limit", () => {
    const results = indexedSearch.search("file", 2);
    expect(results.length).toBeLessThanOrEqual(2);
  });

  it("returns empty for unindexed search", () => {
    const search = new EmbeddingToolSearch();
    expect(search.search("anything")).toEqual([]);
  });

  it("each result has required fields", () => {
    const results = indexedSearch.search("jira ticket", 3);
    for (const r of results) {
      expect(r).toHaveProperty("name");
      expect(r).toHaveProperty("description");
      expect(r).toHaveProperty("input_schema");
      expect(r).toHaveProperty("score");
    }
  });

  it("is deterministic", () => {
    const r1 = indexedSearch.search("weather forecast", 5);
    const r2 = indexedSearch.search("weather forecast", 5);
    expect(r1).toEqual(r2);
  });
});

// ---------------------------------------------------------------------------
// Regex search
// ---------------------------------------------------------------------------

describe("Regex search", () => {
  it("matches simple patterns", () => {
    const results = indexedSearch.searchByRegex("github");
    const names = results.map((r) => r.name);
    expect(names.length).toBeGreaterThanOrEqual(2);
    expect(names).toContain("github_create_pr");
    expect(names).toContain("github_list_issues");
  });

  it("is case-sensitive by default", () => {
    const results = indexedSearch.searchByRegex("GITHUB");
    expect(results).toHaveLength(0);
  });

  it("supports case-insensitive flag", () => {
    // JavaScript RegExp doesn't support (?i) inline — test a flag-less pattern
    const results = indexedSearch.searchByRegex("github|GitHub");
    expect(results.length).toBeGreaterThanOrEqual(2);
  });

  it("matches prefix patterns", () => {
    const results = indexedSearch.searchByRegex("^slack_");
    const names = results.map((r) => r.name);
    expect(names).toHaveLength(2);
    expect(names).toContain("slack_send_message");
    expect(names).toContain("slack_list_channels");
  });

  it("returns empty for no match", () => {
    expect(indexedSearch.searchByRegex("nonexistent_tool_xyz")).toEqual([]);
  });

  it("matches description text", () => {
    const results = indexedSearch.searchByRegex("PostgreSQL");
    const names = results.map((r) => r.name);
    expect(names).toContain("database_query");
  });

  it("regex results have no score field", () => {
    const results = indexedSearch.searchByRegex("slack");
    for (const r of results) {
      expect(r).not.toHaveProperty("score");
      expect(r).toHaveProperty("name");
      expect(r).toHaveProperty("description");
    }
  });
});

// ---------------------------------------------------------------------------
// Cosine similarity
// ---------------------------------------------------------------------------

describe("Cosine similarity", () => {
  it("identical vectors = 1", () => {
    expect(EmbeddingToolSearch.cosineSimilarity([1, 0, 0], [1, 0, 0])).toBeCloseTo(1);
  });

  it("orthogonal vectors = 0", () => {
    expect(EmbeddingToolSearch.cosineSimilarity([1, 0], [0, 1])).toBeCloseTo(0);
  });

  it("opposite vectors = -1", () => {
    expect(EmbeddingToolSearch.cosineSimilarity([1, 0], [-1, 0])).toBeCloseTo(-1);
  });

  it("zero vector returns 0", () => {
    expect(EmbeddingToolSearch.cosineSimilarity([0, 0], [1, 2])).toBe(0);
  });

  it("throws on dimension mismatch", () => {
    expect(() =>
      EmbeddingToolSearch.cosineSimilarity([1, 2], [1, 2, 3]),
    ).toThrow(/dimension mismatch/);
  });
});
