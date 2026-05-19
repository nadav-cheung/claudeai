/**
 * Tests for Chapter 5: SSE Parser, Stream Handler, and Thinking Handler.
 *
 * Covers:
 * - SSEParser: chunked input, boundary-spanning events, ping filtering,
 *   multi-line data, comment handling, error handling
 * - StreamHandler: full event lifecycle, text accumulation, thinking
 *   block handling, tool_use handling, final message construction
 * - ThinkingHandler: session lifecycle, signature validation,
 *   assistant block construction, redacted thinking, context hash
 */

import { describe, it, expect } from "vitest";
import { SSEParser, SSEParseError, ParsedEvent } from "./SSEParser.js";
import {
  StreamHandler,
  ContentBlockType,
  StreamState,
} from "./StreamHandler.js";
import { ThinkingHandler, ThinkingError } from "./ThinkingHandler.js";

// ============================================================================
// Helpers
// ============================================================================

/** Build an event dict matching SSE data format. */
function makeEvent(
  eventType: string,
  extra: Record<string, unknown> = {},
): Record<string, unknown> {
  return { type: eventType, ...extra };
}

// ============================================================================
// SSEParser Tests
// ============================================================================

describe("SSEParser", () => {
  describe("basic parsing", () => {
    it("parses a single message_start event", () => {
      const parser = new SSEParser();
      const raw =
        'event: message_start\n' +
        'data: {"type": "message_start", "message": {"id": "msg_01", "model": "claude-3"}}\n\n';
      const events = parser.feed(raw);
      expect(events).toHaveLength(1);
      expect(events[0]!.event).toBe("message_start");
      expect((events[0]!.data["message"] as Record<string, unknown>)!["id"]).toBe(
        "msg_01",
      );
    });

    it("parses a single content_block_delta", () => {
      const parser = new SSEParser();
      const raw =
        'event: content_block_delta\n' +
        'data: {"type": "content_block_delta", "index": 0, "delta": {"type": "text_delta", "text": "Hello"}}\n\n';
      const events = parser.feed(raw);
      expect(events).toHaveLength(1);
      expect(events[0]!.event).toBe("content_block_delta");
      expect(
        ((events[0]!.data["delta"] as Record<string, unknown>)!["text"] as string),
      ).toBe("Hello");
    });

    it("filters out ping events", () => {
      const parser = new SSEParser();
      const raw = 'event: ping\ndata: {"type": "ping"}\n\n';
      const events = parser.feed(raw);
      expect(events).toHaveLength(0);
    });

    it("ignores comment lines", () => {
      const parser = new SSEParser();
      const raw =
        ": this is a comment\n" +
        'event: message_stop\n' +
        'data: {"type": "message_stop"}\n\n';
      const events = parser.feed(raw);
      expect(events).toHaveLength(1);
      expect(events[0]!.event).toBe("message_stop");
    });
  });

  describe("chunked input", () => {
    it("handles event split across chunks", () => {
      const parser = new SSEParser();
      const chunk1 =
        'event: content_block_delta\ndata: {"type": "content_block_d';
      const chunk2 =
        'elta", "index": 0, "delta": {"type": "text_delta", "text": "Hello"}}\n\n';

      const events1 = parser.feed(chunk1);
      expect(events1).toHaveLength(0);

      const events2 = parser.feed(chunk2);
      expect(events2).toHaveLength(1);
      expect(events2[0]!.event).toBe("content_block_delta");
    });

    it("handles multiple events in one chunk", () => {
      const parser = new SSEParser();
      const raw =
        'event: message_start\ndata: {"type": "message_start", "message": {"id": "A"}}\n\n' +
        'event: content_block_delta\ndata: {"type": "content_block_delta", "index": 0, "delta": {"type": "text_delta", "text": "X"}}\n\n' +
        'event: message_stop\ndata: {"type": "message_stop"}\n\n';
      const events = parser.feed(raw);
      expect(events).toHaveLength(3);
      expect(events[0]!.event).toBe("message_start");
      expect(events[1]!.event).toBe("content_block_delta");
      expect(events[2]!.event).toBe("message_stop");
    });

    it("handles byte-by-byte feeding", () => {
      const parser = new SSEParser();
      const raw =
        'event: message_stop\ndata: {"type": "message_stop"}\n\n';
      let allEvents: ParsedEvent[] = [];
      for (const ch of raw) {
        const evts = parser.feed(ch);
        allEvents = allEvents.concat(evts);
      }
      expect(allEvents).toHaveLength(1);
      expect(allEvents[0]!.event).toBe("message_stop");
    });

    it("handles carriage return line endings", () => {
      const parser = new SSEParser();
      const raw =
        "event: message_stop\r\n" +
        'data: {"type": "message_stop"}\r\n' +
        "\r\n";
      const events = parser.feed(raw);
      expect(events).toHaveLength(1);
      expect(events[0]!.event).toBe("message_stop");
    });
  });

  describe("edge cases", () => {
    it("handles multi-line data field", () => {
      const parser = new SSEParser();
      const raw =
        "event: test\n" +
        'data: {"line1": 1,\n' +
        'data: "line2": 2}\n\n';
      const events = parser.feed(raw);
      expect(events).toHaveLength(1);
      expect(events[0]!.data).toEqual({ line1: 1, line2: 2 });
    });

    it("defaults event type to 'message' when no event field", () => {
      const parser = new SSEParser();
      const raw = 'data: {"type": "custom"}\n\n';
      const events = parser.feed(raw);
      expect(events).toHaveLength(1);
      expect(events[0]!.event).toBe("message");
    });

    it("throws on invalid JSON", () => {
      const parser = new SSEParser();
      const raw = "event: test\ndata: {invalid json}\n\n";
      expect(() => parser.feed(raw)).toThrow(SSEParseError);
    });

    it("empty feed returns no events", () => {
      const parser = new SSEParser();
      expect(parser.feed("")).toHaveLength(0);
    });

    it("flush drains remaining partial event", () => {
      const parser = new SSEParser();
      parser.feed('event: test\ndata: {"x": 1}');
      const flushed = parser.flush();
      expect(flushed).toHaveLength(1);
      expect(flushed[0]!.data).toEqual({ x: 1 });
    });

    it("reset clears the buffer", () => {
      const parser = new SSEParser();
      parser.feed('event: test\ndata: {"x": 1}');
      parser.reset();
      expect(parser.flush()).toHaveLength(0);
    });

    it("handles unicode content", () => {
      const parser = new SSEParser();
      const raw =
        'event: content_block_delta\n' +
        'data: {"type": "content_block_delta", "index": 0, "delta": {"type": "text_delta", "text": "你好世界"}}\n\n';
      const events = parser.feed(raw);
      expect(events).toHaveLength(1);
      expect(
        ((events[0]!.data["delta"] as Record<string, unknown>)!["text"] as string),
      ).toBe("你好世界");
    });
  });
});

// ============================================================================
// StreamHandler Tests
// ============================================================================

describe("StreamHandler", () => {
  describe("full text stream lifecycle", () => {
    it("processes a complete text stream from start to finish", () => {
      const handler = new StreamHandler();

      // message_start
      handler.handleEvent(
        makeEvent("message_start", {
          message: {
            id: "msg_test123",
            model: "claude-sonnet-4-5-20250929",
            role: "assistant",
            content: [],
            stop_reason: null,
            stop_sequence: null,
            usage: { input_tokens: 10, output_tokens: 1 },
          },
        }),
      );

      const state = handler.getState();
      expect(state.messageId).toBe("msg_test123");
      expect(state.inputTokens).toBe(10);

      // content_block_start (text)
      handler.handleEvent(
        makeEvent("content_block_start", {
          index: 0,
          content_block: { type: "text", text: "" },
        }),
      );
      expect(handler.getState().contentBlocks).toHaveLength(1);
      expect(handler.getState().contentBlocks[0]!.blockType).toBe(
        ContentBlockType.Text,
      );

      // Deltas
      const t1 = handler.handleEvent(
        makeEvent("content_block_delta", {
          index: 0,
          delta: { type: "text_delta", text: "Hello" },
        }),
      );
      expect(t1).toBe("Hello");

      handler.handleEvent(
        makeEvent("content_block_delta", {
          index: 0,
          delta: { type: "text_delta", text: " " },
        }),
      );
      handler.handleEvent(
        makeEvent("content_block_delta", {
          index: 0,
          delta: { type: "text_delta", text: "World" },
        }),
      );

      expect(handler.getText()).toBe("Hello World");

      // content_block_stop
      handler.handleEvent(makeEvent("content_block_stop", { index: 0 }));
      expect(handler.getState().contentBlocks[0]!.finished).toBe(true);

      // message_delta
      handler.handleEvent(
        makeEvent("message_delta", {
          delta: { stop_reason: "end_turn", stop_sequence: null },
          usage: { output_tokens: 15 },
        }),
      );
      expect(handler.getState().stopReason).toBe("end_turn");

      // message_stop
      handler.handleEvent(makeEvent("message_stop"));
      expect(handler.getState().finished).toBe(true);

      // Final message
      const msg = handler.getFinalMessage();
      expect(msg.id).toBe("msg_test123");
      expect((msg.content[0] as Record<string, unknown>)!["text"]).toBe(
        "Hello World",
      );
    });
  });

  describe("event handling", () => {
    it("handles ping silently", () => {
      const handler = new StreamHandler();
      const result = handler.handleEvent(makeEvent("ping"));
      expect(result).toBeUndefined();
    });

    it("handles error event", () => {
      const handler = new StreamHandler();
      handler.handleEvent(
        makeEvent("error", {
          error: { type: "overloaded_error", message: "Overloaded" },
        }),
      );
      expect(handler.getState().finished).toBe(true);
      expect(handler.getState().error).not.toBeNull();
      expect(
        (handler.getState().error as Record<string, unknown>)!["type"],
      ).toBe("overloaded_error");
    });

    it("ignores unknown event types", () => {
      const handler = new StreamHandler();
      expect(handler.handleEvent({ type: "future_event_v99" })).toBeUndefined();
    });
  });

  describe("thinking block handling", () => {
    it("processes a full thinking + text stream", () => {
      const handler = new StreamHandler();

      handler.handleEvent(
        makeEvent("message_start", {
          message: {
            id: "msg_thinking",
            model: "claude-sonnet-4-5-20250929",
            role: "assistant",
            content: [],
            stop_reason: null,
            stop_sequence: null,
            usage: { input_tokens: 20, output_tokens: 1 },
          },
        }),
      );

      // thinking block start
      handler.handleEvent(
        makeEvent("content_block_start", {
          index: 0,
          content_block: { type: "thinking", thinking: "" },
        }),
      );
      expect(handler.getState().contentBlocks[0]!.blockType).toBe(
        ContentBlockType.Thinking,
      );

      // thinking delta
      handler.handleEvent(
        makeEvent("content_block_delta", {
          index: 0,
          delta: { type: "thinking_delta", thinking: "Let me think..." },
        }),
      );
      expect(handler.getState().contentBlocks[0]!.thinking).toContain(
        "Let me think",
      );

      // signature delta
      handler.handleEvent(
        makeEvent("content_block_delta", {
          index: 0,
          delta: {
            type: "signature_delta",
            signature: "abc123signature",
          },
        }),
      );
      expect(handler.getState().contentBlocks[0]!.signature).toBe(
        "abc123signature",
      );

      // stop thinking block
      handler.handleEvent(makeEvent("content_block_stop", { index: 0 }));

      // text block
      handler.handleEvent(
        makeEvent("content_block_start", {
          index: 1,
          content_block: { type: "text", text: "" },
        }),
      );
      handler.handleEvent(
        makeEvent("content_block_delta", {
          index: 1,
          delta: { type: "text_delta", text: "The answer is 42." },
        }),
      );
      handler.handleEvent(makeEvent("content_block_stop", { index: 1 }));

      // finish
      handler.handleEvent(
        makeEvent("message_delta", {
          delta: { stop_reason: "end_turn" },
          usage: { output_tokens: 100 },
        }),
      );
      handler.handleEvent(makeEvent("message_stop"));

      const msg = handler.getFinalMessage();
      expect(msg.content).toHaveLength(2);
      expect((msg.content[0] as Record<string, unknown>)!["type"]).toBe(
        "thinking",
      );
      expect((msg.content[1] as Record<string, unknown>)!["type"]).toBe("text");
    });
  });

  describe("tool_use block handling", () => {
    it("handles tool_use blocks", () => {
      const handler = new StreamHandler();

      handler.handleEvent(
        makeEvent("message_start", {
          message: {
            id: "msg_tool",
            model: "claude-3",
            role: "assistant",
            content: [],
            stop_reason: null,
            stop_sequence: null,
            usage: { input_tokens: 5, output_tokens: 1 },
          },
        }),
      );

      handler.handleEvent(
        makeEvent("content_block_start", {
          index: 0,
          content_block: {
            type: "tool_use",
            id: "toolu_01ABC",
            name: "get_weather",
            input: {},
          },
        }),
      );

      expect(handler.getState().contentBlocks[0]!.toolUseId).toBe(
        "toolu_01ABC",
      );
      expect(handler.getState().contentBlocks[0]!.toolName).toBe("get_weather");

      handler.handleEvent(
        makeEvent("content_block_delta", {
          index: 0,
          delta: {
            type: "input_json_delta",
            partial_json: '{"location": "SF"}',
          },
        }),
      );

      handler.handleEvent(makeEvent("content_block_stop", { index: 0 }));
      handler.handleEvent(
        makeEvent("message_delta", {
          delta: { stop_reason: "tool_use" },
          usage: { output_tokens: 50 },
        }),
      );
      handler.handleEvent(makeEvent("message_stop"));

      const msg = handler.getFinalMessage();
      expect(msg.stop_reason).toBe("tool_use");
      expect((msg.content[0] as Record<string, unknown>)!["type"]).toBe(
        "tool_use",
      );
    });

    it("handles multiple content blocks (text + tool_use)", () => {
      const handler = new StreamHandler();

      handler.handleEvent(
        makeEvent("message_start", {
          message: {
            id: "msg_multi",
            model: "claude-3",
            role: "assistant",
            content: [],
            stop_reason: null,
            stop_sequence: null,
            usage: { input_tokens: 10, output_tokens: 1 },
          },
        }),
      );

      // First block: text
      handler.handleEvent(
        makeEvent("content_block_start", {
          index: 0,
          content_block: { type: "text", text: "" },
        }),
      );
      handler.handleEvent(
        makeEvent("content_block_delta", {
          index: 0,
          delta: { type: "text_delta", text: "Let me check." },
        }),
      );
      handler.handleEvent(makeEvent("content_block_stop", { index: 0 }));

      // Second block: tool_use
      handler.handleEvent(
        makeEvent("content_block_start", {
          index: 1,
          content_block: {
            type: "tool_use",
            id: "toolu_XYZ",
            name: "search",
            input: {},
          },
        }),
      );
      handler.handleEvent(makeEvent("content_block_stop", { index: 1 }));

      handler.handleEvent(
        makeEvent("message_delta", {
          delta: { stop_reason: "tool_use" },
          usage: { output_tokens: 30 },
        }),
      );
      handler.handleEvent(makeEvent("message_stop"));

      expect(handler.getState().contentBlocks).toHaveLength(2);
      expect(handler.getState().contentBlocks[0]!.blockType).toBe(
        ContentBlockType.Text,
      );
      expect(handler.getState().contentBlocks[1]!.blockType).toBe(
        ContentBlockType.ToolUse,
      );
    });
  });

  describe("state management", () => {
    it("reset clears state", () => {
      const handler = new StreamHandler();
      handler.handleEvent(
        makeEvent("message_start", {
          message: {
            id: "msg_x",
            model: "m",
            role: "assistant",
            content: [],
            stop_reason: null,
            stop_sequence: null,
            usage: { input_tokens: 1, output_tokens: 1 },
          },
        }),
      );
      handler.reset();
      expect(handler.getState().messageId).toBe("");
      expect(handler.getState().contentBlocks).toHaveLength(0);
    });
  });
});

// ============================================================================
// ThinkingHandler Tests
// ============================================================================

describe("ThinkingHandler", () => {
  describe("lifecycle", () => {
    it("startThinking initializes the session", () => {
      const handler = new ThinkingHandler();
      handler.startThinking(8000);
      expect(handler.getSession().isActive).toBe(true);
      expect(handler.getSession().budgetTokens).toBe(8000);
    });

    it("throws on negative budget", () => {
      const handler = new ThinkingHandler();
      expect(() => handler.startThinking(-100)).toThrow(ThinkingError);
    });

    it("allows zero budget", () => {
      const handler = new ThinkingHandler();
      handler.startThinking(0);
      expect(handler.getSession().budgetTokens).toBe(0);
    });

    it("processThinkingDelta accumulates text", () => {
      const handler = new ThinkingHandler();
      handler.startThinking(4000);
      handler.processThinkingDelta("Step 1: ");
      handler.processThinkingDelta("analyze.");
      expect(handler.getSession().accumulatedThinking).toBe(
        "Step 1: analyze.",
      );
    });

    it("processThinkingDelta without start throws", () => {
      const handler = new ThinkingHandler();
      expect(() => handler.processThinkingDelta("something")).toThrow(
        ThinkingError,
      );
    });

    it("finalizeThinking with valid signature", () => {
      const handler = new ThinkingHandler();
      handler.startThinking(2000);
      handler.processThinkingDelta("My reasoning...");
      const result = handler.finalizeThinking("sig_abc123");
      expect(result).toBe(true);
      expect(handler.getSession().isComplete).toBe(true);
      expect(handler.getSession().signature).toBe("sig_abc123");
    });

    it("finalizeThinking with empty signature returns false", () => {
      const handler = new ThinkingHandler();
      handler.startThinking(2000);
      handler.processThinkingDelta("reasoning");
      expect(handler.finalizeThinking("")).toBe(false);
    });

    it("finalizeThinking without start throws", () => {
      const handler = new ThinkingHandler();
      expect(() => handler.finalizeThinking("sig")).toThrow(ThinkingError);
    });
  });

  describe("assistant block construction", () => {
    it("builds a valid assistant thinking block", () => {
      const handler = new ThinkingHandler();
      handler.startThinking(5000);
      handler.processThinkingDelta("Think about X");
      handler.finalizeThinking("sig_valid");

      const block = handler.buildAssistantBlock();
      expect(block["type"]).toBe("thinking");
      expect(block["thinking"]).toBe("Think about X");
      expect(block["signature"]).toBe("sig_valid");
    });

    it("throws if not yet finalized", () => {
      const handler = new ThinkingHandler();
      handler.startThinking(1000);
      expect(() => handler.buildAssistantBlock()).toThrow(ThinkingError);
    });

    it("builds redacted thinking block", () => {
      const handler = new ThinkingHandler();
      const block = handler.buildRedactedThinkingBlock("encrypted_here");
      expect(block["type"]).toBe("redacted_thinking");
      expect(block["data"]).toBe("encrypted_here");
    });
  });

  describe("signature validation", () => {
    it("validates a proper base64 signature", () => {
      const handler = new ThinkingHandler();
      const sig = btoa("test signature data 12345");
      expect(handler.verifySignatureIntegrity("thinking text", sig)).toBe(true);
    });

    it("rejects empty signature", () => {
      const handler = new ThinkingHandler();
      expect(handler.verifySignatureIntegrity("text", "")).toBe(false);
    });

    it("rejects whitespace-only thinking", () => {
      const handler = new ThinkingHandler();
      const sig = btoa("data");
      expect(handler.verifySignatureIntegrity("   ", sig)).toBe(false);
    });

    it("rejects invalid base64 chars", () => {
      const handler = new ThinkingHandler();
      expect(
        handler.verifySignatureIntegrity("text", "!!!invalid!!!"),
      ).toBe(false);
    });
  });

  describe("context hash", () => {
    it("produces a 64-char SHA-256 hex digest", async () => {
      const handler = new ThinkingHandler();
      handler.startThinking(1000);
      handler.processThinkingDelta("test content");
      const h = await handler.computeContextHash();
      expect(h).toHaveLength(64);
      expect(/^[0-9a-f]+$/.test(h)).toBe(true);
    });

    it("is deterministic", async () => {
      const h1 = new ThinkingHandler();
      h1.startThinking(1000);
      h1.processThinkingDelta("same content");

      const h2 = new ThinkingHandler();
      h2.startThinking(1000);
      h2.processThinkingDelta("same content");

      expect(await h1.computeContextHash()).toBe(await h2.computeContextHash());
    });
  });

  describe("reset", () => {
    it("clears all session state", () => {
      const handler = new ThinkingHandler();
      handler.startThinking(5000);
      handler.processThinkingDelta("data");
      handler.reset();

      expect(handler.getSession().isActive).toBe(false);
      expect(handler.getSession().accumulatedThinking).toBe("");
      expect(handler.getSession().budgetTokens).toBe(0);
    });
  });
});

// ============================================================================
// Integration Tests
// ============================================================================

describe("Integration", () => {
  it("processes a full thinking + text stream pipeline", () => {
    const parser = new SSEParser();
    const streamHandler = new StreamHandler();
    const thinkHandler = new ThinkingHandler();

    const rawEvents = [
      'event: message_start\ndata: {"type": "message_start", "message": {"id": "msg_int", "type": "message", "role": "assistant", "content": [], "model": "claude-sonnet-4-5-20250929", "stop_reason": null, "stop_sequence": null, "usage": {"input_tokens": 50, "output_tokens": 1}}}\n\n',
      'event: content_block_start\ndata: {"type": "content_block_start", "index": 0, "content_block": {"type": "thinking", "thinking": ""}}\n\n',
      'event: content_block_delta\ndata: {"type": "content_block_delta", "index": 0, "delta": {"type": "thinking_delta", "thinking": "Let me solve this step by step.\\n\\n"}}\n\n',
      'event: content_block_delta\ndata: {"type": "content_block_delta", "index": 0, "delta": {"type": "thinking_delta", "thinking": "First, consider the constraints."}}\n\n',
      'event: content_block_delta\ndata: {"type": "content_block_delta", "index": 0, "delta": {"type": "signature_delta", "signature": "dGVzdCBzaWduYXR1cmUgZGF0YQ=="}}\n\n',
      'event: content_block_stop\ndata: {"type": "content_block_stop", "index": 0}\n\n',
      'event: content_block_start\ndata: {"type": "content_block_start", "index": 1, "content_block": {"type": "text", "text": ""}}\n\n',
      'event: content_block_delta\ndata: {"type": "content_block_delta", "index": 1, "delta": {"type": "text_delta", "text": "Based on my analysis, "}}\n\n',
      'event: content_block_delta\ndata: {"type": "content_block_delta", "index": 1, "delta": {"type": "text_delta", "text": "the answer is 42."}}\n\n',
      'event: content_block_stop\ndata: {"type": "content_block_stop", "index": 1}\n\n',
      'event: message_delta\ndata: {"type": "message_delta", "delta": {"stop_reason": "end_turn", "stop_sequence": null}, "usage": {"output_tokens": 250}}\n\n',
      'event: message_stop\ndata: {"type": "message_stop"}\n\n',
    ];

    // Feed events through parser
    const allParsed: ParsedEvent[] = [];
    for (const raw of rawEvents) {
      allParsed.push(...parser.feed(raw));
    }

    // Process through StreamHandler and ThinkingHandler
    let accumulatedText = "";
    let thinkingStarted = false;

    for (const event of allParsed) {
      const text = streamHandler.handleEvent(event.data);
      if (text) accumulatedText += text;

      const data = event.data;
      if (data["type"] === "content_block_delta") {
        const delta = (data["delta"] as Record<string, unknown>) ?? {};
        if (delta["type"] === "thinking_delta") {
          if (!thinkingStarted) {
            thinkHandler.startThinking(8000);
            thinkingStarted = true;
          }
          thinkHandler.processThinkingDelta(delta["thinking"] as string);
        } else if (delta["type"] === "signature_delta") {
          thinkHandler.finalizeThinking(delta["signature"] as string);
        }
      }
    }

    // Verify text
    expect(accumulatedText).toBe("Based on my analysis, the answer is 42.");

    // Verify thinking
    expect(thinkHandler.getSession().accumulatedThinking).toContain(
      "step by step",
    );
    expect(thinkHandler.getSession().isComplete).toBe(true);
    expect(thinkHandler.getSession().signature).toBe(
      "dGVzdCBzaWduYXR1cmUgZGF0YQ==",
    );

    // Verify final message
    const msg = streamHandler.getFinalMessage();
    expect(msg.stop_reason).toBe("end_turn");
    expect(msg.content).toHaveLength(2);

    // Verify assistant block
    const assistantBlock = thinkHandler.buildAssistantBlock();
    expect(assistantBlock["signature"]).toBe(
      "dGVzdCBzaWduYXR1cmUgZGF0YQ==",
    );
  });

  it("handles stream interruption by error", () => {
    const parser = new SSEParser();
    const handler = new StreamHandler();

    const raw =
      'event: message_start\ndata: {"type": "message_start", "message": {"id": "err_test", "type": "message", "role": "assistant", "content": [], "model": "claude-3", "stop_reason": null, "stop_sequence": null, "usage": {"input_tokens": 5, "output_tokens": 1}}}\n\n' +
      'event: content_block_delta\ndata: {"type": "content_block_delta", "index": 0, "delta": {"type": "text_delta", "text": "Partial"}}\n\n' +
      'event: error\ndata: {"type": "error", "error": {"type": "overloaded_error", "message": "Service overloaded"}}\n\n';

    const parsed = parser.feed(raw);
    for (const event of parsed) {
      handler.handleEvent(event.data);
    }

    const state = handler.getState();
    expect(state.finished).toBe(true);
    expect(state.error).not.toBeNull();
    expect((state.error as Record<string, unknown>)!["type"]).toBe(
      "overloaded_error",
    );
    expect(handler.getText()).toContain("Partial");
  });
});
