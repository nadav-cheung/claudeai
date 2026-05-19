/**
 * MessageBuilder - Anthropic Messages API request construction.
 *
 * This module provides a type-safe, zero-dependency builder for constructing
 * Anthropic Messages API request bodies. It models Content Blocks, Messages,
 * and the full MessageRequest according to the API specification.
 *
 * Protocol reference: POST https://api.anthropic.com/v1/messages
 *
 * Key design decisions:
 * - No dependency on the @anthropic-ai/sdk — this is a protocol-level builder.
 * - All classes implement toJSON() for JSON serialization.
 * - Strict TypeScript types throughout for safety and self-documentation.
 * - Supports plain-string content as shorthand per the API spec.
 */

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

export const SUPPORTED_IMAGE_MEDIA_TYPES = [
  "image/jpeg",
  "image/png",
  "image/gif",
  "image/webp",
] as const;

export type SupportedImageMediaType = (typeof SUPPORTED_IMAGE_MEDIA_TYPES)[number];

/** Practical guidance: 5 MB max for base64 images. */
export const MAX_BASE64_IMAGE_BYTES = 5 * 1024 * 1024;

/** Practical guidance: 10 MB max for URL images. */
export const MAX_URL_IMAGE_BYTES = 10 * 1024 * 1024;

/** The Messages API endpoint. */
export const MESSAGES_ENDPOINT = "https://api.anthropic.com/v1/messages";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export type Role = "user" | "assistant";

export type StopReason =
  | "end_turn"
  | "max_tokens"
  | "stop_sequence"
  | "tool_use"
  | "pause_turn"
  | "refusal";

export type ServiceTier = "auto" | "standard_only";

export type CacheTTL = "5m" | "1h";

/** Shape of the ephemeral cache control object. */
export interface CacheControl {
  type: "ephemeral";
  ttl?: CacheTTL;
}

// ---------------------------------------------------------------------------
// Content Block Types
// ---------------------------------------------------------------------------

export type ContentBlockType = "text" | "image" | "tool_use" | "tool_result";

/** Base interface for all content blocks. */
export interface ContentBlockDict {
  type: ContentBlockType;
  [key: string]: unknown;
}

/** Text content block serialized form. */
export interface TextBlockDict extends ContentBlockDict {
  type: "text";
  text: string;
  cache_control?: CacheControl | null;
  citations?: Array<Record<string, unknown>> | null;
}

/** Base64 image source. */
export interface Base64ImageSource {
  type: "base64";
  media_type: SupportedImageMediaType;
  data: string;
}

/** URL image source. */
export interface URLImageSource {
  type: "url";
  url: string;
}

export type ImageSource = Base64ImageSource | URLImageSource;

/** Image content block serialized form. */
export interface ImageBlockDict extends ContentBlockDict {
  type: "image";
  source: ImageSource;
  cache_control?: CacheControl | null;
}

/** Tool-use content block serialized form. */
export interface ToolUseBlockDict extends ContentBlockDict {
  type: "tool_use";
  id: string;
  name: string;
  input: Record<string, unknown>;
}

/** Tool-result content block serialized form. */
export interface ToolResultBlockDict extends ContentBlockDict {
  type: "tool_result";
  tool_use_id: string;
  content: string | Array<Record<string, unknown>>;
  is_error?: boolean | null;
  cache_control?: CacheControl | null;
}

/** Union of all content block dicts. */
export type AnyContentBlockDict =
  | TextBlockDict
  | ImageBlockDict
  | ToolUseBlockDict
  | ToolResultBlockDict;

// ---------------------------------------------------------------------------
// Message Types
// ---------------------------------------------------------------------------

/** A message can have string or array-of-blocks content (per API spec). */
export type MessageContent = string | ContentBlock[];

export interface MessageDict {
  role: Role;
  content: string | AnyContentBlockDict[];
}

// ---------------------------------------------------------------------------
// Tool definition type (for the `tools` array in the request)
// ---------------------------------------------------------------------------

export interface ToolDefinition {
  name: string;
  description?: string;
  input_schema: {
    type: "object";
    properties?: Record<string, unknown>;
    required?: string[];
  };
}

// ---------------------------------------------------------------------------
// Request Types
// ---------------------------------------------------------------------------

export interface ThinkingConfig {
  type: "enabled";
  budget_tokens: number;
}

export interface ToolChoiceBase {
  type: "auto" | "any" | "none";
  disable_parallel_tool_use?: boolean;
}

export interface ToolChoiceTool {
  type: "tool";
  name: string;
  disable_parallel_tool_use?: boolean;
}

export type ToolChoice = ToolChoiceBase | ToolChoiceTool;

export interface MessageRequestDict {
  model: string;
  messages: MessageDict[];
  max_tokens: number;
  system?: string | Array<{ type: "text"; text: string; cache_control?: CacheControl }>;
  temperature?: number;
  top_p?: number;
  top_k?: number;
  stop_sequences?: string[];
  stream?: boolean;
  metadata?: Record<string, string>;
  tools?: ToolDefinition[];
  tool_choice?: ToolChoice;
  thinking?: ThinkingConfig;
  service_tier?: ServiceTier;
  cache_control?: CacheControl;
}

// ---------------------------------------------------------------------------
// Content Block Classes
// ---------------------------------------------------------------------------

/**
 * Base class for all Content Block types.
 * Each subclass sets `blockType` and implements `toJSON()`.
 */
export abstract class ContentBlock {
  abstract readonly blockType: ContentBlockType;

  abstract toJSON(): AnyContentBlockDict;

  /**
   * Deserialize a plain object into the appropriate ContentBlock subclass.
   */
  static fromDict(data: AnyContentBlockDict): ContentBlock {
    switch (data.type) {
      case "text": {
        const td = data as TextBlockDict;
        return new TextBlock(td.text, td.cache_control ?? undefined, td.citations ?? undefined);
      }
      case "image": {
        const id = data as ImageBlockDict;
        if (id.source.type === "base64") {
          return ImageBlock.fromBase64(id.source.data, id.source.media_type);
        } else {
          return ImageBlock.fromUrl(id.source.url);
        }
      }
      case "tool_use": {
        const tud = data as ToolUseBlockDict;
        return new ToolUseBlock(tud.id, tud.name, tud.input);
      }
      case "tool_result": {
        const trd = data as ToolResultBlockDict;
        return new ToolResultBlock(
          trd.tool_use_id,
          trd.content,
          trd.is_error ?? undefined,
          trd.cache_control ?? undefined,
        );
      }
      default:
        throw new Error(`Unknown content block type: ${(data as ContentBlockDict).type}`);
    }
  }
}

// ---------------------------------------------------------------------------
// TextBlock
// ---------------------------------------------------------------------------

export class TextBlock extends ContentBlock {
  readonly blockType = "text" as const;

  constructor(
    public readonly text: string,
    public readonly cacheControl?: CacheControl,
    public readonly citations?: Array<Record<string, unknown>>,
  ) {
    super();
  }

  toJSON(): TextBlockDict {
    const result: TextBlockDict = { type: "text", text: this.text };
    if (this.cacheControl) {
      result.cache_control = this.cacheControl;
    }
    if (this.citations) {
      result.citations = this.citations;
    }
    return result;
  }
}

// ---------------------------------------------------------------------------
// ImageBlock
// ---------------------------------------------------------------------------

export class ImageBlock extends ContentBlock {
  readonly blockType = "image" as const;

  private constructor(
    public readonly source: ImageSource,
    public readonly cacheControl?: CacheControl,
  ) {
    super();
    // Validate source type at construction time
    if (source.type !== "base64" && source.type !== "url") {
      throw new Error(`Invalid image source type: ${(source as Record<string, unknown>).type}`);
    }
  }

  /** Create from base64-encoded data. Strips data URI prefix if present. */
  static fromBase64(data: string, mediaType: SupportedImageMediaType): ImageBlock {
    if (!SUPPORTED_IMAGE_MEDIA_TYPES.includes(mediaType)) {
      throw new Error(
        `Unsupported media_type: ${mediaType}. Supported: ${SUPPORTED_IMAGE_MEDIA_TYPES.join(", ")}`,
      );
    }

    const cleaned = ImageBlock._stripDataUriPrefix(data);
    if (!cleaned.trim()) {
      throw new Error("Base64 data cannot be empty.");
    }

    // Rough size check
    const estimatedBytes = Math.floor((cleaned.length * 3) / 4);
    if (estimatedBytes > MAX_BASE64_IMAGE_BYTES) {
      throw new Error(
        `Estimated image size (${estimatedBytes} bytes) exceeds ` +
          `the recommended limit of ${MAX_BASE64_IMAGE_BYTES} bytes.`,
      );
    }

    return new ImageBlock({ type: "base64", media_type: mediaType, data: cleaned });
  }

  /** Create from an image URL. */
  static fromUrl(url: string): ImageBlock {
    if (!url.startsWith("http://") && !url.startsWith("https://")) {
      throw new Error(`Image URL must start with http:// or https://, got: ${url}`);
    }
    return new ImageBlock({ type: "url", url });
  }

  /** Create from base64 with optional cache control. */
  static fromBase64WithCache(
    data: string,
    mediaType: SupportedImageMediaType,
    cacheControl?: CacheControl,
  ): ImageBlock {
    const block = ImageBlock.fromBase64(data, mediaType);
    return new ImageBlock(block.source, cacheControl);
  }

  /** Create from URL with optional cache control. */
  static fromUrlWithCache(url: string, cacheControl?: CacheControl): ImageBlock {
    const block = ImageBlock.fromUrl(url);
    return new ImageBlock(block.source, cacheControl);
  }

  toJSON(): ImageBlockDict {
    const result: ImageBlockDict = {
      type: "image",
      source: { ...this.source },
    };
    if (this.cacheControl) {
      result.cache_control = this.cacheControl;
    }
    return result;
  }

  private static _stripDataUriPrefix(data: string): string {
    if (data.startsWith("data:")) {
      const commaIdx = data.indexOf(",");
      if (commaIdx !== -1) {
        return data.substring(commaIdx + 1);
      }
    }
    return data;
  }
}

// ---------------------------------------------------------------------------
// ToolUseBlock
// ---------------------------------------------------------------------------

export class ToolUseBlock extends ContentBlock {
  readonly blockType = "tool_use" as const;

  constructor(
    public readonly id: string,
    public readonly name: string,
    public readonly input: Record<string, unknown> = {},
  ) {
    super();
  }

  toJSON(): ToolUseBlockDict {
    return {
      type: "tool_use",
      id: this.id,
      name: this.name,
      input: this.input,
    };
  }
}

// ---------------------------------------------------------------------------
// ToolResultBlock
// ---------------------------------------------------------------------------

export class ToolResultBlock extends ContentBlock {
  readonly blockType = "tool_result" as const;

  constructor(
    public readonly toolUseId: string,
    public readonly content: string | Array<Record<string, unknown>>,
    public readonly isError?: boolean,
    public readonly cacheControl?: CacheControl,
  ) {
    super();
  }

  /** Shorthand for a successful tool result. */
  static success(toolUseId: string, content: string): ToolResultBlock {
    return new ToolResultBlock(toolUseId, content, false);
  }

  /** Shorthand for a tool execution error. */
  static error(toolUseId: string, errorMessage: string): ToolResultBlock {
    return new ToolResultBlock(toolUseId, errorMessage, true);
  }

  toJSON(): ToolResultBlockDict {
    const result: ToolResultBlockDict = {
      type: "tool_result",
      tool_use_id: this.toolUseId,
      content: this.content,
    };
    if (this.isError !== undefined) {
      result.is_error = this.isError;
    }
    if (this.cacheControl) {
      result.cache_control = this.cacheControl;
    }
    return result;
  }
}

// ---------------------------------------------------------------------------
// Message
// ---------------------------------------------------------------------------

export class Message {
  readonly role: Role;
  readonly content: MessageContent;

  constructor(role: Role, content: MessageContent) {
    if (role !== "user" && role !== "assistant") {
      throw new Error(`Invalid role: ${role}. Must be 'user' or 'assistant'.`);
    }
    if (typeof content === "string" && content.length === 0) {
      throw new Error("Message content cannot be an empty string.");
    }
    this.role = role;
    this.content = content;
  }

  static user(content: MessageContent): Message {
    return new Message("user", content);
  }

  static assistant(content: MessageContent): Message {
    return new Message("assistant", content);
  }

  toJSON(): MessageDict {
    if (typeof this.content === "string") {
      return { role: this.role, content: this.content };
    }
    return {
      role: this.role,
      content: this.content.map((block) => block.toJSON()),
    };
  }
}

// ---------------------------------------------------------------------------
// MessageRequest
// ---------------------------------------------------------------------------

export class MessageRequest {
  readonly model: string;
  readonly messages: Message[];
  readonly maxTokens: number;
  readonly system?: string | Array<{ type: "text"; text: string; cache_control?: CacheControl }>;
  readonly temperature?: number;
  readonly topP?: number;
  readonly topK?: number;
  readonly stopSequences?: string[];
  readonly stream: boolean;
  readonly metadata?: Record<string, string>;
  readonly tools?: ToolDefinition[];
  readonly toolChoice?: ToolChoice;
  readonly thinking?: ThinkingConfig;
  readonly serviceTier?: ServiceTier;
  readonly cacheControl?: CacheControl;

  constructor(params: {
    model: string;
    messages: Message[];
    maxTokens: number;
    system?: string | Array<{ type: "text"; text: string; cache_control?: CacheControl }>;
    temperature?: number;
    topP?: number;
    topK?: number;
    stopSequences?: string[];
    stream?: boolean;
    metadata?: Record<string, string>;
    tools?: ToolDefinition[];
    toolChoice?: ToolChoice;
    thinking?: ThinkingConfig;
    serviceTier?: ServiceTier;
    cacheControl?: CacheControl;
  }) {
    // Validation
    if (!params.model || !params.model.trim()) {
      throw new Error("model must be a non-empty string.");
    }
    if (!params.messages || params.messages.length === 0) {
      throw new Error("messages list cannot be empty.");
    }
    if (params.maxTokens < 1) {
      throw new Error(`max_tokens must be >= 1, got ${params.maxTokens}.`);
    }
    if (params.temperature !== undefined && (params.temperature < 0 || params.temperature > 1)) {
      throw new Error(`temperature must be in [0.0, 1.0], got ${params.temperature}.`);
    }
    if (params.topP !== undefined && (params.topP < 0 || params.topP > 1)) {
      throw new Error(`top_p must be in [0.0, 1.0], got ${params.topP}.`);
    }
    if (params.topK !== undefined && params.topK < 0) {
      throw new Error(`top_k must be >= 0, got ${params.topK}.`);
    }
    if (params.serviceTier !== undefined) {
      if (params.serviceTier !== "auto" && params.serviceTier !== "standard_only") {
        throw new Error(
          `Invalid service_tier: ${params.serviceTier}. Must be 'auto' or 'standard_only'.`,
        );
      }
    }

    this.model = params.model;
    this.messages = params.messages;
    this.maxTokens = params.maxTokens;
    this.system = params.system;
    this.temperature = params.temperature;
    this.topP = params.topP;
    this.topK = params.topK;
    this.stopSequences = params.stopSequences;
    this.stream = params.stream ?? false;
    this.metadata = params.metadata;
    this.tools = params.tools;
    this.toolChoice = params.toolChoice;
    this.thinking = params.thinking;
    this.serviceTier = params.serviceTier;
    this.cacheControl = params.cacheControl;
  }

  toJSON(): MessageRequestDict {
    const body: MessageRequestDict = {
      model: this.model,
      messages: this.messages.map((m) => m.toJSON()),
      max_tokens: this.maxTokens,
    };

    if (this.system !== undefined) body.system = this.system;
    if (this.temperature !== undefined) body.temperature = this.temperature;
    if (this.topP !== undefined) body.top_p = this.topP;
    if (this.topK !== undefined) body.top_k = this.topK;
    if (this.stopSequences !== undefined) body.stop_sequences = this.stopSequences;
    if (this.stream) body.stream = true;
    if (this.metadata !== undefined) body.metadata = this.metadata;
    if (this.tools !== undefined) body.tools = this.tools;
    if (this.toolChoice !== undefined) body.tool_choice = this.toolChoice;
    if (this.thinking !== undefined) body.thinking = this.thinking;
    if (this.serviceTier !== undefined) body.service_tier = this.serviceTier;
    if (this.cacheControl !== undefined) body.cache_control = this.cacheControl;

    return body;
  }

  /**
   * Serialize to a JSON string.
   */
  toJsonString(indent?: number): string {
    return JSON.stringify(this.toJSON(), null, indent);
  }
}

// ---------------------------------------------------------------------------
// Convenience constructors
// ---------------------------------------------------------------------------

export function simpleTextRequest(
  prompt: string,
  model = "claude-sonnet-4-20250514",
  maxTokens = 1024,
  system?: string,
): MessageRequest {
  return new MessageRequest({
    model,
    messages: [Message.user(prompt)],
    maxTokens,
    system,
  });
}

export function multimodalRequest(
  text: string,
  images: ImageBlock[],
  model = "claude-sonnet-4-20250514",
  maxTokens = 1024,
  system?: string,
): MessageRequest {
  const blocks: ContentBlock[] = [new TextBlock(text), ...images];
  return new MessageRequest({
    model,
    messages: [Message.user(blocks)],
    maxTokens,
    system,
  });
}
