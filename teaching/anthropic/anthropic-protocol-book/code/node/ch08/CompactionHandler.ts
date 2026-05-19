/**
 * Chapter 8: Compaction Handler (TypeScript).
 *
 * Implements context compaction (auto-summarization) for long-running
 * Claude conversations. When the context window approaches capacity, the
 * handler replaces early conversation history with a structured summary
 * to free token space for new interactions.
 *
 * Core strategies:
 *   1. Summarization: Replace early messages with structured summary
 *   2. Truncation: Simply drop early messages (fallback, cached-cold path)
 */

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

export const DEFAULT_COMPACT_THRESHOLD = 0.80;
export const MIN_COMPACT_THRESHOLD = 0.75;
export const MAX_COMPACT_THRESHOLD = 0.92;
export const DEFAULT_PRESERVE_RECENT = 4;
export const MIN_MESSAGES_FOR_COMPACTION = 6;
export const CACHE_COLD_THRESHOLD_SECONDS = 300; // 5 minutes

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export type CompactionStrategy = "summarize" | "truncate";

export interface Message {
  role: "user" | "assistant" | "system";
  content: string | Record<string, unknown>[];
  [key: string]: unknown;
}

export interface CompactionResult {
  compactedMessages: Message[];
  tokensBefore: number;
  tokensAfter: number;
  strategy: CompactionStrategy;
  summary?: string;
  messagesRemoved: number;
  cacheSafe: boolean;
  tokensSaved: number;
  savingsPct: number;
}

export interface CompactionSnapshot {
  messages: Message[];
  timestamp: number;
  checksum: string;
}

export interface CacheEditsBlock {
  type: "cache_edits";
  edits: { delete: string }[];
}

export interface CacheEditsResult {
  messages: Message[];
  cache_edits: CacheEditsBlock;
}

// ---------------------------------------------------------------------------
// CompactionHandler
// ---------------------------------------------------------------------------

export class CompactionHandler {
  public readonly threshold: number;
  public readonly preserveRecent: number;
  public readonly defaultStrategy: CompactionStrategy;
  public readonly modelContextWindow: number;

  private lastApiResponseTime: number | null = null;
  private snapshots: CompactionSnapshot[] = [];

  constructor(
    threshold: number = DEFAULT_COMPACT_THRESHOLD,
    preserveRecent: number = DEFAULT_PRESERVE_RECENT,
    defaultStrategy: CompactionStrategy = "summarize",
    modelContextWindow: number = 200_000,
  ) {
    if (threshold < MIN_COMPACT_THRESHOLD || threshold > MAX_COMPACT_THRESHOLD) {
      throw new Error(
        `threshold must be between ${MIN_COMPACT_THRESHOLD} and ${MAX_COMPACT_THRESHOLD}, got ${threshold}`,
      );
    }
    if (preserveRecent < 1) {
      throw new Error("preserve_recent must be at least 1");
    }

    this.threshold = threshold;
    this.preserveRecent = preserveRecent;
    this.defaultStrategy = defaultStrategy;
    this.modelContextWindow = modelContextWindow;
  }

  // ----------------------------------------------------------------
  // Should-compact decision
  // ----------------------------------------------------------------

  shouldCompact(
    currentTokens: number,
    maxTokens?: number,
    messageCount?: number,
  ): boolean {
    const window = maxTokens ?? this.modelContextWindow;
    if (window <= 0) return false;

    const usagePct = currentTokens / window;
    if (usagePct < this.threshold) return false;

    if (messageCount !== undefined && messageCount < MIN_MESSAGES_FOR_COMPACTION) {
      return false;
    }

    return true;
  }

  shouldCompactByUsage(contextUsagePct: number): boolean {
    // Normalize to 0.0-1.0 range
    if (contextUsagePct > 1.0) {
      contextUsagePct = contextUsagePct / 100.0;
    }
    return contextUsagePct >= this.threshold;
  }

  // ----------------------------------------------------------------
  // Compaction execution
  // ----------------------------------------------------------------

  compact(
    messages: Message[],
    contextWindow?: number,
    strategy?: CompactionStrategy,
    summaryFn?: (messages: Message[]) => string,
  ): CompactionResult {
    const effectiveStrategy = strategy ?? this.defaultStrategy;
    const window = contextWindow ?? this.modelContextWindow;

    if (messages.length <= this.preserveRecent) {
      return {
        compactedMessages: [...messages],
        tokensBefore: 0,
        tokensAfter: 0,
        strategy: effectiveStrategy,
        messagesRemoved: 0,
        cacheSafe: true,
        tokensSaved: 0,
        savingsPct: 0,
      };
    }

    const tokensBefore = this.estimateTokens(messages);

    // Split: early messages to compact + recent to preserve
    const splitIdx = Math.max(0, messages.length - this.preserveRecent);
    const earlyMessages = messages.slice(0, splitIdx);
    const recentMessages = messages.slice(splitIdx);

    if (earlyMessages.length === 0) {
      return {
        compactedMessages: recentMessages,
        tokensBefore,
        tokensAfter: this.estimateTokens(recentMessages),
        strategy: effectiveStrategy,
        messagesRemoved: 0,
        cacheSafe: true,
        tokensSaved: tokensBefore - this.estimateTokens(recentMessages),
        savingsPct: 0,
      };
    }

    // Save snapshot before compaction
    this.createSnapshot(messages);

    const isCacheCold = this.isCacheCold();

    let summary: string | undefined;
    let compacted: Message[];
    let cacheSafe: boolean;

    if (effectiveStrategy === "summarize") {
      summary = summaryFn
        ? summaryFn(earlyMessages)
        : this.generateSummary(earlyMessages);

      const summaryMsg: Message = {
        role: "user",
        content: `<conversation_summary>\n${summary}\n</conversation_summary>`,
      };

      compacted = [summaryMsg, ...recentMessages];
      cacheSafe = !isCacheCold;
    } else {
      compacted = recentMessages;
      cacheSafe = false;
    }

    const tokensAfter = this.estimateTokens(compacted);

    return {
      compactedMessages: compacted,
      tokensBefore,
      tokensAfter,
      strategy: effectiveStrategy,
      summary: summary ?? undefined,
      messagesRemoved: earlyMessages.length,
      cacheSafe,
      tokensSaved: tokensBefore - tokensAfter,
      savingsPct: tokensBefore > 0
        ? Math.round(((tokensBefore - tokensAfter) / tokensBefore) * 1000) / 10
        : 0,
    };
  }

  // ----------------------------------------------------------------
  // Summary generation
  // ----------------------------------------------------------------

  private generateSummary(messages: Message[]): string {
    const userMessages = messages.filter((m) => m.role === "user");
    const assistantMessages = messages.filter((m) => m.role === "assistant");

    const parts: string[] = ["## Conversation Summary"];

    if (userMessages.length > 0) {
      parts.push("### Task Goal");
      for (const msg of userMessages.slice(0, 5)) {
        const text = this.extractText(msg.content);
        if (text) {
          parts.push(`- ${text.slice(0, 200)}`);
        }
      }
    }

    if (assistantMessages.length > 0) {
      parts.push("### Key Actions");
      for (const msg of assistantMessages.slice(-5)) {
        const text = this.extractText(msg.content);
        if (text) {
          parts.push(`- ${text.slice(0, 200)}`);
        }
      }
    }

    parts.push("### Stats");
    parts.push(`- User messages summarized: ${userMessages.length}`);
    parts.push(`- Assistant messages summarized: ${assistantMessages.length}`);
    parts.push(`- Total messages compacted: ${messages.length}`);

    return parts.join("\n");
  }

  private extractText(content: string | Record<string, unknown>[]): string {
    if (typeof content === "string") return content;
    const texts: string[] = [];
    for (const block of content) {
      if (block.type === "text" && typeof block.text === "string") {
        texts.push(block.text);
      } else if (block.type === "tool_result") {
        texts.push("[tool result]");
      }
    }
    return texts.join(" ");
  }

  // ----------------------------------------------------------------
  // Token estimation
  // ----------------------------------------------------------------

  private estimateTokens(messages: Message[]): number {
    let totalChars = 0;
    for (const msg of messages) {
      const content = msg.content;
      if (typeof content === "string") {
        totalChars += content.length;
      } else if (Array.isArray(content)) {
        for (const block of content) {
          if (typeof block.text === "string") {
            totalChars += block.text.length;
          }
        }
      }
      totalChars += 50; // role metadata overhead
    }
    return Math.max(1, Math.floor(totalChars / 4));
  }

  // ----------------------------------------------------------------
  // Cache state tracking
  // ----------------------------------------------------------------

  markApiResponse(): void {
    this.lastApiResponseTime = Date.now();
  }

  private isCacheCold(): boolean {
    if (this.lastApiResponseTime === null) return true;
    const elapsed = (Date.now() - this.lastApiResponseTime) / 1000;
    return elapsed > CACHE_COLD_THRESHOLD_SECONDS;
  }

  // ----------------------------------------------------------------
  // Snapshots for rollback
  // ----------------------------------------------------------------

  private createSnapshot(messages: Message[]): void {
    const snapshot: CompactionSnapshot = {
      messages: structuredClone(messages),
      timestamp: Date.now(),
      checksum: "snapshot",  // simplified; production would use crypto.hash
    };
    this.snapshots.push(snapshot);
    if (this.snapshots.length > 5) {
      this.snapshots = this.snapshots.slice(-5);
    }
  }

  rollback(): Message[] | null {
    const snapshot = this.snapshots.pop();
    return snapshot ? snapshot.messages : null;
  }

  // ----------------------------------------------------------------
  // Cache-aware compaction (Cached MC pattern)
  // ----------------------------------------------------------------

  createCacheEdits(
    messages: Message[],
    toolIdsToDelete: string[],
  ): CacheEditsResult {
    const edits: { delete: string }[] = toolIdsToDelete.map((id) => ({
      delete: id,
    }));

    const annotated = messages.map((msg) => {
      const content = msg.content;
      if (!Array.isArray(content)) return { ...msg };

      const newContent = content.map((block) => {
        const blockCopy = { ...block };
        if (
          blockCopy.type === "tool_result" &&
          typeof blockCopy.tool_use_id === "string" &&
          toolIdsToDelete.includes(blockCopy.tool_use_id)
        ) {
          blockCopy.cache_reference = blockCopy.tool_use_id;
        }
        return blockCopy;
      });

      return { ...msg, content: newContent };
    });

    return {
      messages: annotated,
      cache_edits: { type: "cache_edits", edits },
    };
  }

  // ----------------------------------------------------------------
  // Factory methods
  // ----------------------------------------------------------------

  static forShortConversation(): CompactionHandler {
    return new CompactionHandler(0.90, 8);
  }

  static forMediumConversation(): CompactionHandler {
    return new CompactionHandler(0.85, 6);
  }

  static forLongConversation(): CompactionHandler {
    return new CompactionHandler(0.75, 4);
  }
}
