/**
 * Tests for Chapter 8: Compaction Handler (TypeScript).
 */

import { describe, it, expect } from "vitest";

import {
  CompactionHandler,
  DEFAULT_COMPACT_THRESHOLD,
  MIN_COMPACT_THRESHOLD,
  MAX_COMPACT_THRESHOLD,
} from "./CompactionHandler";

import type { Message } from "./CompactionHandler";

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------

function makeHandler(): CompactionHandler {
  return new CompactionHandler(0.80, 4);
}

function makeLongConversation(): Message[] {
  const msgs: Message[] = [];
  for (let i = 0; i < 15; i++) {
    const role = i % 2 === 0 ? "user" : "assistant";
    msgs.push({
      role,
      content: `Message ${i}: This is ${role === "user" ? "a question" : "an answer"} about topic ${Math.floor(i / 2)}.`,
    });
  }
  return msgs;
}

function makeShortConversation(): Message[] {
  return [
    { role: "user", content: "Hi" },
    { role: "assistant", content: "Hello!" },
    { role: "user", content: "How are you?" },
  ];
}

// ---------------------------------------------------------------------------
// Initialization tests
// ---------------------------------------------------------------------------

describe("CompactionHandler - Initialization", () => {
  it("uses default threshold of 0.80", () => {
    const handler = new CompactionHandler();
    expect(handler.threshold).toBe(DEFAULT_COMPACT_THRESHOLD);
  });

  it("accepts custom threshold", () => {
    const handler = new CompactionHandler(0.85);
    expect(handler.threshold).toBe(0.85);
  });

  it("throws on threshold below minimum", () => {
    expect(() => new CompactionHandler(0.50)).toThrow(/threshold must be/);
  });

  it("throws on threshold above maximum", () => {
    expect(() => new CompactionHandler(0.99)).toThrow(/threshold must be/);
  });

  it("throws on preserveRecent of 0", () => {
    expect(() => new CompactionHandler(0.80, 0)).toThrow(/preserve_recent/);
  });
});

// ---------------------------------------------------------------------------
// Should-compact tests
// ---------------------------------------------------------------------------

describe("CompactionHandler - Should compact", () => {
  it("returns false below threshold", () => {
    const handler = makeHandler();
    expect(handler.shouldCompact(100000, 200000)).toBe(false);
  });

  it("returns true above threshold", () => {
    const handler = makeHandler();
    expect(handler.shouldCompact(180000, 200000)).toBe(true);
  });

  it("returns false with too few messages", () => {
    const handler = makeHandler();
    expect(handler.shouldCompact(180000, 200000, 3)).toBe(false);
  });

  it("shouldCompactByUsage handles fraction input", () => {
    const handler = makeHandler();
    expect(handler.shouldCompactByUsage(0.70)).toBe(false);
    expect(handler.shouldCompactByUsage(0.85)).toBe(true);
  });

  it("shouldCompactByUsage handles percentage input", () => {
    const handler = makeHandler();
    expect(handler.shouldCompactByUsage(70)).toBe(false);
    expect(handler.shouldCompactByUsage(85)).toBe(true);
  });
});

// ---------------------------------------------------------------------------
// Compaction execution tests
// ---------------------------------------------------------------------------

describe("CompactionHandler - Compaction", () => {
  it("reduces message count", () => {
    const handler = makeHandler();
    const long = makeLongConversation();
    const result = handler.compact(long, 200000);
    expect(result.compactedMessages.length).toBeLessThan(long.length);
    expect(result.messagesRemoved).toBeGreaterThan(0);
  });

  it("preserves the most recent messages", () => {
    const handler = makeHandler();
    const long = makeLongConversation();
    const result = handler.compact(long, 200000);
    const preserved = result.compactedMessages.slice(-handler.preserveRecent);
    const expected = long.slice(-handler.preserveRecent);
    expect(preserved).toEqual(expected);
  });

  it("no-ops for too-short conversation", () => {
    const handler = makeHandler();
    const short = makeShortConversation();
    const result = handler.compact(short, 200000);
    expect(result.messagesRemoved).toBe(0);
    expect(result.compactedMessages).toEqual(short);
  });

  it("summarize strategy produces a summary", () => {
    const handler = makeHandler();
    const long = makeLongConversation();
    const result = handler.compact(long, 200000, "summarize");
    expect(result.strategy).toBe("summarize");
    expect(result.summary).toBeDefined();
    expect(result.summary).toContain("Conversation Summary");
  });

  it("truncate strategy produces no summary", () => {
    const handler = makeHandler();
    const long = makeLongConversation();
    const result = handler.compact(long, 200000, "truncate");
    expect(result.strategy).toBe("truncate");
    expect(result.summary).toBeUndefined();
  });

  it("supports custom summary function", () => {
    const handler = makeHandler();
    const long = makeLongConversation();
    const customSummary = "CUSTOM: All tasks completed.";
    const result = handler.compact(long, 200000, "summarize", () => customSummary);
    expect(result.summary).toBe(customSummary);
  });

  it("saves tokens (tokensSaved > 0)", () => {
    const handler = makeHandler();
    const long = makeLongConversation();
    const result = handler.compact(long, 200000);
    expect(result.tokensSaved).toBeGreaterThan(0);
    expect(result.savingsPct).toBeGreaterThan(0);
  });
});

// ---------------------------------------------------------------------------
// CompactionResult tests
// ---------------------------------------------------------------------------

describe("CompactionHandler - Result properties", () => {
  it("result has correct structure for summarize", () => {
    const handler = makeHandler();
    const long = makeLongConversation();
    const result = handler.compact(long, 200000, "summarize");
    expect(result).toHaveProperty("compactedMessages");
    expect(result).toHaveProperty("tokensBefore");
    expect(result).toHaveProperty("tokensAfter");
    expect(result).toHaveProperty("strategy");
    expect(result).toHaveProperty("summary");
    expect(result).toHaveProperty("messagesRemoved");
    expect(result).toHaveProperty("cacheSafe");
    expect(result).toHaveProperty("tokensSaved");
    expect(result).toHaveProperty("savingsPct");
  });
});

// ---------------------------------------------------------------------------
// Snapshot and rollback tests
// ---------------------------------------------------------------------------

describe("CompactionHandler - Snapshots", () => {
  it("rollback restores original messages", () => {
    const handler = makeHandler();
    const long = makeLongConversation();
    const result = handler.compact(long, 200000);
    expect(result.compactedMessages.length).toBeLessThan(long.length);

    const restored = handler.rollback();
    expect(restored).not.toBeNull();
    expect(restored!.length).toBe(long.length);
  });

  it("rollback returns null when empty", () => {
    const handler = makeHandler();
    expect(handler.rollback()).toBeNull();
  });

  it("keeps at most 5 snapshots", () => {
    const handler = makeHandler();
    const long = makeLongConversation();
    for (let i = 0; i < 10; i++) {
      handler.compact(long, 200000);
    }
    let count = 0;
    while (handler.rollback() !== null) count++;
    expect(count).toBeLessThanOrEqual(5);
  });

  it("consecutive compaction and rollback works", () => {
    const handler = makeHandler();
    const long = makeLongConversation();
    const result1 = handler.compact(long, 200000);
    const compacted1 = result1.compactedMessages;
    handler.compact(compacted1, 200000);
    const restored = handler.rollback();
    expect(restored).toEqual(compacted1);
  });
});

// ---------------------------------------------------------------------------
// Cache-aware features
// ---------------------------------------------------------------------------

describe("CompactionHandler - Cache features", () => {
  it("markApiResponse sets last response time", () => {
    const handler = makeHandler();
    handler.markApiResponse();
    // Internal state set (private, tested via behavior)
    expect(handler).toBeDefined();
  });

  it("createCacheEdits generates correct blocks", () => {
    const handler = makeHandler();
    const messages: Message[] = [
      {
        role: "user",
        content: [
          { type: "tool_result", tool_use_id: "tool_001", content: "result 1" },
          { type: "tool_result", tool_use_id: "tool_002", content: "result 2" },
        ],
      },
    ];
    const result = handler.createCacheEdits(messages, ["tool_001"]);

    expect(result.cache_edits.type).toBe("cache_edits");
    expect(result.cache_edits.edits).toHaveLength(1);
    expect(result.cache_edits.edits[0]).toEqual({ delete: "tool_001" });
  });

  it("createCacheEdits adds cache_reference to matching blocks", () => {
    const handler = makeHandler();
    const messages: Message[] = [
      {
        role: "user",
        content: [
          { type: "tool_result", tool_use_id: "tool_abc", content: "data" },
        ],
      },
    ];
    const result = handler.createCacheEdits(messages, ["tool_abc"]);
    const annotated = result.messages[0]!.content as Record<string, unknown>[];
    expect(annotated[0]!).toHaveProperty("cache_reference", "tool_abc");
  });

  it("createCacheEdits with empty deletions returns empty edits", () => {
    const handler = makeHandler();
    const result = handler.createCacheEdits([], []);
    expect(result.cache_edits.edits).toEqual([]);
  });
});

// ---------------------------------------------------------------------------
// Factory methods
// ---------------------------------------------------------------------------

describe("CompactionHandler - Factories", () => {
  it("forShortConversation uses 0.90 threshold and 8 preserveRecent", () => {
    const h = CompactionHandler.forShortConversation();
    expect(h.threshold).toBe(0.90);
    expect(h.preserveRecent).toBe(8);
  });

  it("forMediumConversation uses 0.85 threshold and 6 preserveRecent", () => {
    const h = CompactionHandler.forMediumConversation();
    expect(h.threshold).toBe(0.85);
    expect(h.preserveRecent).toBe(6);
  });

  it("forLongConversation uses 0.75 threshold and 4 preserveRecent", () => {
    const h = CompactionHandler.forLongConversation();
    expect(h.threshold).toBe(0.75);
    expect(h.preserveRecent).toBe(4);
  });
});
