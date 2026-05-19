/**
 * Tests for MessageBuilder.ts — Messages API request construction.
 *
 * Covers:
 * - ContentBlock subclasses (TextBlock, ImageBlock, ToolUseBlock, ToolResultBlock)
 * - Message class (user/assistant, plain-string vs array content)
 * - MessageRequest validation and serialization
 * - Edge cases: empty strings, invalid params, multi-turn conversations
 */

import { describe, it, expect } from "vitest";
import {
  ContentBlock,
  TextBlock,
  ImageBlock,
  ToolUseBlock,
  ToolResultBlock,
  Message,
  MessageRequest,
  SUPPORTED_IMAGE_MEDIA_TYPES,
  MESSAGES_ENDPOINT,
  simpleTextRequest,
  multimodalRequest,
  type SupportedImageMediaType,
  type ToolDefinition,
} from "./MessageBuilder.js";

// ---------------------------------------------------------------------------
// 1×1 transparent PNG
// ---------------------------------------------------------------------------
const ONE_PIXEL_PNG_B64 =
  "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk" +
  "+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg==";

// =================================================================
// TextBlock
// =================================================================

describe("TextBlock", () => {
  it("serializes basic text", () => {
    const block = new TextBlock("Hello, world");
    expect(block.toJSON()).toEqual({ type: "text", text: "Hello, world" });
  });

  it("serializes with cache control", () => {
    const block = new TextBlock("Repeat after me", { type: "ephemeral" });
    const d = block.toJSON();
    expect(d.cache_control).toEqual({ type: "ephemeral" });
  });

  it("serializes with citations", () => {
    const citations = [
      {
        type: "char_location",
        cited_text: "...",
        document_index: 0,
        document_title: "Test",
        start_char_index: 0,
        end_char_index: 3,
      },
    ];
    const block = new TextBlock("Citing something", undefined, citations);
    expect(block.toJSON().citations).toEqual(citations);
  });

  it("allows empty text", () => {
    const block = new TextBlock("");
    expect(block.toJSON().text).toBe("");
  });

  it("deserializes from dict", () => {
    const block = ContentBlock.fromDict({ type: "text", text: "Deserialized" });
    expect(block).toBeInstanceOf(TextBlock);
    expect((block as TextBlock).text).toBe("Deserialized");
  });
});

// =================================================================
// ImageBlock
// =================================================================

describe("ImageBlock", () => {
  it("creates from base64 PNG", () => {
    const block = ImageBlock.fromBase64(ONE_PIXEL_PNG_B64, "image/png");
    const d = block.toJSON();
    expect(d.type).toBe("image");
    expect(d.source.type).toBe("base64");
    expect(d.source.media_type).toBe("image/png");
    expect(d.source.data).toBe(ONE_PIXEL_PNG_B64);
  });

  it("strips data URI prefix from base64", () => {
    const dataUri = `data:image/png;base64,${ONE_PIXEL_PNG_B64}`;
    const block = ImageBlock.fromBase64(dataUri, "image/png");
    expect(block.source.data).toBe(ONE_PIXEL_PNG_B64);
  });

  it("rejects unsupported media type", () => {
    expect(() => {
      ImageBlock.fromBase64(ONE_PIXEL_PNG_B64, "image/bmp" as SupportedImageMediaType);
    }).toThrow(/Unsupported media_type/);
  });

  it("rejects empty base64 data", () => {
    expect(() => {
      ImageBlock.fromBase64("", "image/png");
    }).toThrow(/empty/);
  });

  it("rejects oversized base64 data", () => {
    const big = "A".repeat(7 * 1024 * 1024);
    expect(() => {
      ImageBlock.fromBase64(big, "image/jpeg");
    }).toThrow(/exceeds/);
  });

  it("creates from URL", () => {
    const block = ImageBlock.fromUrl("https://example.com/photo.jpg");
    expect(block.toJSON().source).toEqual({
      type: "url",
      url: "https://example.com/photo.jpg",
    });
  });

  it("rejects non-HTTP URL", () => {
    expect(() => {
      ImageBlock.fromUrl("ftp://files.example.com/img.png");
    }).toThrow(/must start with/);
  });

  it("allows HTTP URL", () => {
    const block = ImageBlock.fromUrl("http://example.com/photo.jpg");
    expect(block.toJSON().source.url).toBe("http://example.com/photo.jpg");
  });

  it("supports all four media types", () => {
    for (const mt of SUPPORTED_IMAGE_MEDIA_TYPES) {
      const block = ImageBlock.fromBase64(ONE_PIXEL_PNG_B64, mt);
      expect(block.source.media_type).toBe(mt);
    }
  });

  it("deserializes base64 image from dict", () => {
    const block = ContentBlock.fromDict({
      type: "image",
      source: {
        type: "base64",
        media_type: "image/png",
        data: ONE_PIXEL_PNG_B64,
      },
    });
    expect(block).toBeInstanceOf(ImageBlock);
    expect((block as ImageBlock).source.data).toBe(ONE_PIXEL_PNG_B64);
  });

  it("deserializes URL image from dict", () => {
    const block = ContentBlock.fromDict({
      type: "image",
      source: { type: "url", url: "https://example.com/img.png" },
    });
    expect(block).toBeInstanceOf(ImageBlock);
    expect((block as ImageBlock).source.url).toBe("https://example.com/img.png");
  });

  it("attaches cache_control", () => {
    const block = ImageBlock.fromUrlWithCache(
      "https://example.com/img.png",
      { type: "ephemeral" },
    );
    expect(block.toJSON().cache_control).toEqual({ type: "ephemeral" });
  });
});

// =================================================================
// ToolUseBlock
// =================================================================

describe("ToolUseBlock", () => {
  it("serializes correctly", () => {
    const block = new ToolUseBlock("toolu_01ABC123", "get_weather", {
      location: "San Francisco, CA",
    });
    expect(block.toJSON()).toEqual({
      type: "tool_use",
      id: "toolu_01ABC123",
      name: "get_weather",
      input: { location: "San Francisco, CA" },
    });
  });

  it("defaults input to empty object", () => {
    const block = new ToolUseBlock("toolu_X", "ping");
    expect(block.toJSON().input).toEqual({});
  });

  it("deserializes from dict", () => {
    const block = ContentBlock.fromDict({
      type: "tool_use",
      id: "toolu_XYZ",
      name: "search",
      input: { q: "hello" },
    });
    expect(block).toBeInstanceOf(ToolUseBlock);
    const t = block as ToolUseBlock;
    expect(t.id).toBe("toolu_XYZ");
    expect(t.name).toBe("search");
    expect(t.input).toEqual({ q: "hello" });
  });
});

// =================================================================
// ToolResultBlock
// =================================================================

describe("ToolResultBlock", () => {
  it("serializes string content", () => {
    const block = new ToolResultBlock("toolu_X", "42 degrees");
    const d = block.toJSON();
    expect(d.tool_use_id).toBe("toolu_X");
    expect(d.content).toBe("42 degrees");
    expect(d.is_error).toBeUndefined();
  });

  it("serializes array content", () => {
    const block = new ToolResultBlock("toolu_X", [{ type: "text", text: "Image generated" }]);
    expect(Array.isArray(block.toJSON().content)).toBe(true);
  });

  it("sets is_error to true", () => {
    const block = new ToolResultBlock("toolu_X", "Timeout", true);
    expect(block.toJSON().is_error).toBe(true);
  });

  it("sets is_error to false", () => {
    const block = new ToolResultBlock("toolu_X", "OK", false);
    expect(block.toJSON().is_error).toBe(false);
  });

  it("success factory method", () => {
    const block = ToolResultBlock.success("toolu_X", "Done");
    expect(block.isError).toBe(false);
    expect(block.content).toBe("Done");
  });

  it("error factory method", () => {
    const block = ToolResultBlock.error("toolu_X", "failed");
    expect(block.isError).toBe(true);
    expect(block.content).toBe("failed");
  });

  it("attaches cache_control", () => {
    const block = new ToolResultBlock("toolu_X", "OK", undefined, {
      type: "ephemeral",
    });
    expect(block.toJSON().cache_control).toEqual({ type: "ephemeral" });
  });

  it("deserializes from dict", () => {
    const block = ContentBlock.fromDict({
      type: "tool_result",
      tool_use_id: "toolu_X",
      content: "result",
    });
    expect(block).toBeInstanceOf(ToolResultBlock);
    expect((block as ToolResultBlock).toolUseId).toBe("toolu_X");
  });
});

// =================================================================
// ContentBlock.fromDict - unknown type
// =================================================================

describe("ContentBlock.fromDict edge cases", () => {
  it("throws on unknown type", () => {
    expect(() => {
      ContentBlock.fromDict({ type: "unknown_block" } as never);
    }).toThrow(/Unknown content block type/);
  });
});

// =================================================================
// Message
// =================================================================

describe("Message", () => {
  it("creates user message with string content", () => {
    const msg = Message.user("Hello");
    expect(msg.toJSON()).toEqual({ role: "user", content: "Hello" });
  });

  it("creates assistant message with string content", () => {
    const msg = Message.assistant("I am Claude.");
    expect(msg.toJSON()).toEqual({ role: "assistant", content: "I am Claude." });
  });

  it("creates user message with array content", () => {
    const blocks = [new TextBlock("Hi"), new TextBlock("there")];
    const msg = Message.user(blocks);
    const d = msg.toJSON();
    expect(d.role).toBe("user");
    expect(Array.isArray(d.content)).toBe(true);
    expect((d.content as unknown[]).length).toBe(2);
  });

  it("rejects empty string content", () => {
    expect(() => {
      Message.user("");
    }).toThrow(/cannot be an empty string/);
  });

  it("rejects invalid role", () => {
    expect(() => {
      new Message("system" as never, "I am the system");
    }).toThrow(/Invalid role/);
  });

  it("user factory preserves role", () => {
    expect(Message.user("x").role).toBe("user");
  });

  it("assistant factory preserves role", () => {
    expect(Message.assistant("x").role).toBe("assistant");
  });
});

// =================================================================
// MessageRequest
// =================================================================

describe("MessageRequest", () => {
  it("builds minimal request", () => {
    const req = new MessageRequest({
      model: "claude-sonnet-4-20250514",
      messages: [Message.user("Hi")],
      maxTokens: 1024,
    });
    const d = req.toJSON();
    expect(d.model).toBe("claude-sonnet-4-20250514");
    expect(d.max_tokens).toBe(1024);
    expect(d.messages.length).toBe(1);
    expect(d.system).toBeUndefined();
    expect(d.temperature).toBeUndefined();
    expect(d.stream).toBeUndefined();
  });

  it("sets stream flag", () => {
    const req = new MessageRequest({
      model: "claude-sonnet-4-20250514",
      messages: [Message.user("Hi")],
      maxTokens: 100,
      stream: true,
    });
    expect(req.toJSON().stream).toBe(true);
  });

  it("stream defaults to not-included when false", () => {
    const req = new MessageRequest({
      model: "claude-sonnet-4-20250514",
      messages: [Message.user("Hi")],
      maxTokens: 100,
    });
    expect(req.toJSON().stream).toBeUndefined();
  });

  it("builds full request with all parameters", () => {
    const tools: ToolDefinition[] = [
      {
        name: "get_weather",
        description: "Get the current weather for a city.",
        input_schema: {
          type: "object",
          properties: { city: { type: "string", description: "City name" } },
          required: ["city"],
        },
      },
    ];

    const req = new MessageRequest({
      model: "claude-opus-4-7",
      messages: [
        Message.user("What's the weather?"),
        Message.assistant([
          new ToolUseBlock("toolu_01A", "get_weather", { city: "Paris" }),
        ]),
        Message.user([ToolResultBlock.success("toolu_01A", "Sunny, 22C")]),
      ],
      maxTokens: 2048,
      system: "You are a helpful weather assistant.",
      temperature: 0.7,
      topP: 0.9,
      topK: 40,
      stopSequences: ["\n\n---"],
      metadata: { user_id: "usr_abc123" },
      tools,
    });

    const d = req.toJSON();
    expect(d.model).toBe("claude-opus-4-7");
    expect(d.max_tokens).toBe(2048);
    expect(d.system).toBe("You are a helpful weather assistant.");
    expect(d.temperature).toBe(0.7);
    expect(d.top_p).toBe(0.9);
    expect(d.top_k).toBe(40);
    expect(d.stop_sequences).toEqual(["\n\n---"]);
    expect(d.metadata).toEqual({ user_id: "usr_abc123" });
    expect(d.messages.length).toBe(3);

    // third message content[0] should be tool_result
    const lastContent = d.messages[2]!.content;
    if (Array.isArray(lastContent)) {
      expect(lastContent[0]!.type).toBe("tool_result");
    }
  });

  it("accepts system as text blocks", () => {
    const req = new MessageRequest({
      model: "claude-sonnet-4-20250514",
      messages: [Message.user("Hi")],
      maxTokens: 100,
      system: [{ type: "text", text: "Be concise." }],
    });
    expect(req.toJSON().system).toEqual([{ type: "text", text: "Be concise." }]);
  });

  it("accepts service_tier auto", () => {
    const req = new MessageRequest({
      model: "claude-sonnet-4-20250514",
      messages: [Message.user("Hi")],
      maxTokens: 100,
      serviceTier: "auto",
    });
    expect(req.toJSON().service_tier).toBe("auto");
  });

  it("accepts service_tier standard_only", () => {
    const req = new MessageRequest({
      model: "claude-sonnet-4-20250514",
      messages: [Message.user("Hi")],
      maxTokens: 100,
      serviceTier: "standard_only",
    });
    expect(req.toJSON().service_tier).toBe("standard_only");
  });

  it("rejects invalid service_tier", () => {
    expect(() => {
      new MessageRequest({
        model: "claude-sonnet-4-20250514",
        messages: [Message.user("Hi")],
        maxTokens: 100,
        serviceTier: "premium" as never,
      });
    }).toThrow(/Invalid service_tier/);
  });

  it("accepts cache_control", () => {
    const req = new MessageRequest({
      model: "claude-sonnet-4-20250514",
      messages: [Message.user("Hi")],
      maxTokens: 100,
      cacheControl: { type: "ephemeral" },
    });
    expect(req.toJSON().cache_control).toEqual({ type: "ephemeral" });
  });

  it("accepts thinking config", () => {
    const req = new MessageRequest({
      model: "claude-sonnet-4-20250514",
      messages: [Message.user("Complex problem")],
      maxTokens: 4096,
      thinking: { type: "enabled", budget_tokens: 1024 },
    });
    expect(req.toJSON().thinking).toEqual({
      type: "enabled",
      budget_tokens: 1024,
    });
  });

  it("accepts tool_choice", () => {
    const req = new MessageRequest({
      model: "claude-sonnet-4-20250514",
      messages: [Message.user("Hi")],
      maxTokens: 100,
      tools: [
        {
          name: "search",
          description: "Search",
          input_schema: { type: "object" },
        },
      ],
      toolChoice: { type: "auto" },
    });
    expect(req.toJSON().tool_choice).toEqual({ type: "auto" });
  });

  // ---- Validation ----

  it("rejects empty model", () => {
    expect(() => {
      new MessageRequest({
        model: "",
        messages: [Message.user("Hi")],
        maxTokens: 100,
      });
    }).toThrow(/model must be a non-empty string/);
  });

  it("rejects empty messages", () => {
    expect(() => {
      new MessageRequest({
        model: "claude-sonnet-4-20250514",
        messages: [],
        maxTokens: 100,
      });
    }).toThrow(/messages list cannot be empty/);
  });

  it("rejects maxTokens zero", () => {
    expect(() => {
      new MessageRequest({
        model: "claude-sonnet-4-20250514",
        messages: [Message.user("Hi")],
        maxTokens: 0,
      });
    }).toThrow(/max_tokens must be >= 1/);
  });

  it("rejects maxTokens negative", () => {
    expect(() => {
      new MessageRequest({
        model: "claude-sonnet-4-20250514",
        messages: [Message.user("Hi")],
        maxTokens: -1,
      });
    }).toThrow(/max_tokens must be >= 1/);
  });

  it("rejects temperature out of range (high)", () => {
    expect(() => {
      new MessageRequest({
        model: "claude-sonnet-4-20250514",
        messages: [Message.user("Hi")],
        maxTokens: 100,
        temperature: 1.5,
      });
    }).toThrow(/temperature must be in/);
  });

  it("rejects temperature out of range (low)", () => {
    expect(() => {
      new MessageRequest({
        model: "claude-sonnet-4-20250514",
        messages: [Message.user("Hi")],
        maxTokens: 100,
        temperature: -0.1,
      });
    }).toThrow(/temperature must be in/);
  });

  it("rejects top_p out of range", () => {
    expect(() => {
      new MessageRequest({
        model: "claude-sonnet-4-20250514",
        messages: [Message.user("Hi")],
        maxTokens: 100,
        topP: 2.0,
      });
    }).toThrow(/top_p must be in/);
  });

  it("rejects top_k negative", () => {
    expect(() => {
      new MessageRequest({
        model: "claude-sonnet-4-20250514",
        messages: [Message.user("Hi")],
        maxTokens: 100,
        topK: -5,
      });
    }).toThrow(/top_k must be >= 0/);
  });

  // ---- toJsonString ----

  it("serializes to compact JSON string", () => {
    const req = new MessageRequest({
      model: "claude-sonnet-4-20250514",
      messages: [Message.user("Hello")],
      maxTokens: 100,
    });
    const raw = req.toJsonString();
    const parsed = JSON.parse(raw);
    expect(parsed.model).toBe("claude-sonnet-4-20250514");
  });

  it("serializes to pretty JSON string", () => {
    const req = new MessageRequest({
      model: "claude-sonnet-4-20250514",
      messages: [Message.user("Hello")],
      maxTokens: 100,
    });
    const raw = req.toJsonString(2);
    expect(raw).toContain("\n");
  });
});

// =================================================================
// Convenience constructors
// =================================================================

describe("Convenience constructors", () => {
  it("simpleTextRequest builds a valid request", () => {
    const req = simpleTextRequest("Tell me a joke");
    const d = req.toJSON();
    expect(d.model).toBe("claude-sonnet-4-20250514");
    expect(d.messages[0]?.content).toBe("Tell me a joke");
    expect(d.max_tokens).toBe(1024);
  });

  it("simpleTextRequest accepts custom model and system", () => {
    const req = simpleTextRequest("Hi", "claude-opus-4-7", 500, "Be helpful.");
    const d = req.toJSON();
    expect(d.model).toBe("claude-opus-4-7");
    expect(d.system).toBe("Be helpful.");
    expect(d.max_tokens).toBe(500);
  });

  it("multimodalRequest combines text and images", () => {
    const image = ImageBlock.fromUrl("https://example.com/chart.png");
    const req = multimodalRequest("Describe this chart:", [image]);
    const d = req.toJSON();
    const content = d.messages[0]!.content;
    expect(Array.isArray(content)).toBe(true);
    if (Array.isArray(content)) {
      expect(content.length).toBe(2);
      expect(content[0]!.type).toBe("text");
      expect(content[1]!.type).toBe("image");
    }
  });

  it("multimodalRequest handles multiple images", () => {
    const images = [
      ImageBlock.fromUrl("https://example.com/a.jpg"),
      ImageBlock.fromUrl("https://example.com/b.jpg"),
    ];
    const req = multimodalRequest("Compare:", images);
    const content = req.toJSON().messages[0]!.content;
    expect(Array.isArray(content)).toBe(true);
    if (Array.isArray(content)) {
      expect(content.length).toBe(3);
    }
  });
});

// =================================================================
// Endpoint constant
// =================================================================

describe("Constants", () => {
  it("exports correct endpoint", () => {
    expect(MESSAGES_ENDPOINT).toBe("https://api.anthropic.com/v1/messages");
  });
});
