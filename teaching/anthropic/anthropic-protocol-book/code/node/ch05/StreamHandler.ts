/**
 * Chapter 5: Stream Handler (TypeScript).
 *
 * High-level event dispatcher that sits on top of `SSEParser` and
 * provides business-level semantics for Anthropic streaming responses.
 * Accumulates text, tracks content blocks, surfaces usage stats, and
 * routes errors.
 *
 * @example
 * ```ts
 * const handler = new StreamHandler();
 * for (const parsed of parser.feed(chunk)) {
 *   const text = handler.handleEvent(parsed.data);
 *   if (text) process.stdout.write(text);
 * }
 * ```
 */

// ---------------------------------------------------------------------------
// Supporting types
// ---------------------------------------------------------------------------

export const enum ContentBlockType {
  Text,
  Thinking,
  ToolUse,
  RedactedThinking,
  Unknown,
}

export interface ContentBlock {
  index: number;
  blockType: ContentBlockType;
  text: string;
  thinking: string;
  signature: string;
  toolUseId: string;
  toolName: string;
  toolInput: string;
  finished: boolean;
}

/** Snapshot of the current stream processing state. */
export interface StreamState {
  messageId: string;
  model: string;
  role: string;
  contentBlocks: ContentBlock[];
  stopReason: string | null;
  stopSequence: string | null;
  inputTokens: number;
  outputTokens: number;
  finished: boolean;
  error: Record<string, unknown> | null;
}

/** Return type for `StreamHandler.getFinalMessage()`. */
export interface FinalMessage {
  id: string;
  type: string;
  role: string;
  model: string;
  content: Record<string, unknown>[];
  stop_reason: string | null;
  stop_sequence: string | null;
  usage: {
    input_tokens: number;
    output_tokens: number;
  };
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function blockTypeFromStr(s: string): ContentBlockType {
  const mapping: Record<string, ContentBlockType> = {
    text: ContentBlockType.Text,
    thinking: ContentBlockType.Thinking,
    redacted_thinking: ContentBlockType.RedactedThinking,
    tool_use: ContentBlockType.ToolUse,
  };
  return mapping[s] ?? ContentBlockType.Unknown;
}

function makeContentBlock(index: number): ContentBlock {
  return {
    index,
    blockType: ContentBlockType.Unknown,
    text: "",
    thinking: "",
    signature: "",
    toolUseId: "",
    toolName: "",
    toolInput: "",
    finished: false,
  };
}

function ensureBlock(state: StreamState, index: number): ContentBlock {
  while (state.contentBlocks.length <= index) {
    state.contentBlocks.push(makeContentBlock(state.contentBlocks.length));
  }
  const block = state.contentBlocks[index];
  if (!block) return makeContentBlock(index);
  return block;
}

// ---------------------------------------------------------------------------
// Stream Handler
// ---------------------------------------------------------------------------

export class StreamHandler {
  private state: StreamState;

  constructor(state?: StreamState) {
    this.state = state ?? createEmptyState();
  }

  /** Current accumulated stream state. */
  getState(): Readonly<StreamState> {
    return this.state;
  }

  // ------------------------------------------------------------------
  // Public API
  // ------------------------------------------------------------------

  /**
   * Dispatch a single parsed SSE event.
   *
   * @returns A displayable text string if the event carries a text
   *          delta, or `undefined` for non-text events.
   */
  handleEvent(event: Record<string, unknown>): string | undefined {
    const eventType = (event["type"] as string) ?? "";
    if (!eventType) return undefined;

    switch (eventType) {
      case "message_start":
        return this.onMessageStart(event);
      case "content_block_start":
        return this.onContentBlockStart(event);
      case "content_block_delta":
        return this.onContentBlockDelta(event);
      case "content_block_stop":
        return this.onContentBlockStop(event);
      case "message_delta":
        return this.onMessageDelta(event);
      case "message_stop":
        return this.onMessageStop();
      case "ping":
        return this.onPing();
      case "error":
        return this.onError(event);
      default:
        // Unknown event types are silently ignored per versioning policy
        return undefined;
    }
  }

  /**
   * Construct a Message object from accumulated state.
   *
   * This mimics the structure returned by the non-streaming API.
   */
  getFinalMessage(): FinalMessage {
    const content: Record<string, unknown>[] = [];
    for (const block of this.state.contentBlocks) {
      if (!block.finished) continue;

      switch (block.blockType) {
        case ContentBlockType.Text:
          content.push({ type: "text", text: block.text });
          break;
        case ContentBlockType.Thinking:
          content.push({
            type: "thinking",
            thinking: block.thinking,
            signature: block.signature,
          });
          break;
        case ContentBlockType.ToolUse: {
          let toolInput: unknown = {};
          try {
            toolInput = block.toolInput ? JSON.parse(block.toolInput) : {};
          } catch {
            // partial JSON -- use raw string
            toolInput = block.toolInput;
          }
          content.push({
            type: "tool_use",
            id: block.toolUseId,
            name: block.toolName,
            input: toolInput,
          });
          break;
        }
        case ContentBlockType.RedactedThinking:
          content.push({
            type: "redacted_thinking",
            data: block.thinking,
          });
          break;
      }
    }

    return {
      id: this.state.messageId,
      type: "message",
      role: this.state.role || "assistant",
      model: this.state.model,
      content,
      stop_reason: this.state.stopReason,
      stop_sequence: this.state.stopSequence,
      usage: {
        input_tokens: this.state.inputTokens,
        output_tokens: this.state.outputTokens,
      },
    };
  }

  /** Concatenated text from all text-type content blocks. */
  getText(): string {
    let text = "";
    for (const b of this.state.contentBlocks) {
      if (b.blockType === ContentBlockType.Text) {
        text += b.text;
      }
    }
    return text;
  }

  /** Concatenated thinking from all thinking-type content blocks. */
  getThinkingText(): string {
    let thinking = "";
    for (const b of this.state.contentBlocks) {
      if (b.blockType === ContentBlockType.Thinking) {
        thinking += b.thinking;
      }
    }
    return thinking;
  }

  /** Reset all accumulated state (for reuse). */
  reset(): void {
    this.state = createEmptyState();
  }

  // ------------------------------------------------------------------
  // Event handlers
  // ------------------------------------------------------------------

  private onMessageStart(event: Record<string, unknown>): undefined {
    const msg = (event["message"] as Record<string, unknown>) ?? {};
    this.state.messageId = (msg["id"] as string) ?? "";
    this.state.model = (msg["model"] as string) ?? "";
    this.state.role = (msg["role"] as string) ?? "";
    const usage = (msg["usage"] as Record<string, unknown>) ?? {};
    this.state.inputTokens = (usage["input_tokens"] as number) ?? 0;
    this.state.outputTokens = (usage["output_tokens"] as number) ?? 0;
    this.state.contentBlocks = [];
    return undefined;
  }

  private onContentBlockStart(event: Record<string, unknown>): undefined {
    const index = (event["index"] as number) ?? -1;
    const blockData =
      (event["content_block"] as Record<string, unknown>) ?? {};
    const blockTypeStr = (blockData["type"] as string) ?? "";
    const blockType = blockTypeFromStr(blockTypeStr);

    const block = makeContentBlock(index);
    block.blockType = blockType;

    if (blockType === ContentBlockType.ToolUse) {
      block.toolUseId = (blockData["id"] as string) ?? "";
      block.toolName = (blockData["name"] as string) ?? "";
    }

    while (this.state.contentBlocks.length <= index) {
      this.state.contentBlocks.push(
        makeContentBlock(this.state.contentBlocks.length),
      );
    }
    this.state.contentBlocks[index] = block;
    return undefined;
  }

  private onContentBlockDelta(
    event: Record<string, unknown>,
  ): string | undefined {
    const index = (event["index"] as number) ?? -1;
    const delta = (event["delta"] as Record<string, unknown>) ?? {};
    const deltaType = (delta["type"] as string) ?? "";

    const block = ensureBlock(this.state, index);

    switch (deltaType) {
      case "text_delta": {
        const text = (delta["text"] as string) ?? "";
        block.text += text;
        if (block.blockType === ContentBlockType.Unknown) {
          block.blockType = ContentBlockType.Text;
        }
        return text;
      }
      case "thinking_delta": {
        const thinking = (delta["thinking"] as string) ?? "";
        block.thinking += thinking;
        if (block.blockType === ContentBlockType.Unknown) {
          block.blockType = ContentBlockType.Thinking;
        }
        return undefined;
      }
      case "signature_delta": {
        block.signature = (delta["signature"] as string) ?? "";
        return undefined;
      }
      case "input_json_delta": {
        const partial = (delta["partial_json"] as string) ?? "";
        block.toolInput += partial;
        return undefined;
      }
      default:
        // Unknown delta types are silently ignored
        return undefined;
    }
  }

  private onContentBlockStop(
    event: Record<string, unknown>,
  ): undefined {
    const index = (event["index"] as number) ?? -1;
    const block = ensureBlock(this.state, index);
    block.finished = true;
    return undefined;
  }

  private onMessageDelta(event: Record<string, unknown>): undefined {
    const delta = (event["delta"] as Record<string, unknown>) ?? {};
    this.state.stopReason = (delta["stop_reason"] as string) ?? null;
    this.state.stopSequence = (delta["stop_sequence"] as string) ?? null;
    const usage = (event["usage"] as Record<string, unknown>) ?? {};
    this.state.outputTokens =
      (usage["output_tokens"] as number) ?? this.state.outputTokens;
    return undefined;
  }

  private onMessageStop(): undefined {
    this.state.finished = true;
    return undefined;
  }

  private onPing(): undefined {
    // Transport-level keepalive -- nothing to do.
    return undefined;
  }

  private onError(event: Record<string, unknown>): undefined {
    this.state.error = (event["error"] as Record<string, unknown>) ?? {};
    this.state.finished = true;
    return undefined;
  }
}

// ---------------------------------------------------------------------------
// Internal factory
// ---------------------------------------------------------------------------

function createEmptyState(): StreamState {
  return {
    messageId: "",
    model: "",
    role: "",
    contentBlocks: [],
    stopReason: null,
    stopSequence: null,
    inputTokens: 0,
    outputTokens: 0,
    finished: false,
    error: null,
  };
}
