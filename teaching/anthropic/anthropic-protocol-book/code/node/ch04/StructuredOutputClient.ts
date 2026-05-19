/**
 * Chapter 4: Structured Outputs Client (TypeScript).
 *
 * Protocol-level implementation of Anthropic's structured outputs feature
 * using the ``output_config`` request parameter with JSON Schema constraints.
 *
 * Wraps the Chapter 1 AnthropicClient to add constrained JSON output
 * generation, schema validation, and data extraction capabilities.
 */

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

/** JSON Schema (untyped – mirrors the wire format). */
export type JsonSchema = Record<string, unknown>;

/** The shape an underlying client must satisfy. */
export interface ClientLike {
  post(params: Record<string, unknown>): Promise<Record<string, unknown>>;
}

/** Parameters for {@link StructuredOutputClient.create}. */
export interface CreateParams {
  model: string;
  messages: readonly Record<string, unknown>[];
  jsonSchema: JsonSchema;
  system?: string;
  maxTokens?: number;
  effort?: "low" | "medium" | "high" | "xhigh" | "max";
  [key: string]: unknown;
}

/** Parameters for {@link StructuredOutputClient.extract}. */
export interface ExtractParams {
  model: string;
  text: string;
  jsonSchema: JsonSchema;
  fieldDescription?: string;
  maxTokens?: number;
  effort?: "low" | "medium" | "high" | "xhigh" | "max";
  [key: string]: unknown;
}

// ---------------------------------------------------------------------------
// StructuredOutputClient
// ---------------------------------------------------------------------------

export class StructuredOutputClient {
  private readonly client: ClientLike;

  /**
   * Wrap an existing client instance (e.g. the Chapter 1 AnthropicClient).
   * The client must implement ``post(params) -> Promise<object>``.
   */
  constructor(client: ClientLike) {
    this.client = client;
  }

  // ----------------------------------------------------------------
  // create()
  // ----------------------------------------------------------------

  /**
   * Generate a message whose output is constrained to *jsonSchema*.
   *
   * @returns The raw API response.  The assistant's text content is at
   *          ``response.content[0].text`` and is guaranteed (best-effort)
   *          to be valid JSON conforming to *jsonSchema*.
   */
  async create(params: CreateParams): Promise<Record<string, unknown>> {
    const {
      model,
      messages,
      jsonSchema,
      system,
      maxTokens = 4096,
      effort,
      ...extra
    } = params;

    const outputConfig: Record<string, unknown> = {
      format: {
        type: "json_schema",
        schema: jsonSchema,
      },
    };
    if (effort !== undefined) {
      outputConfig["effort"] = effort;
    }

    return this.client.post({
      model,
      messages,
      max_tokens: maxTokens,
      system,
      output_config: outputConfig,
      ...extra,
    });
  }

  // ----------------------------------------------------------------
  // extract()
  // ----------------------------------------------------------------

  /**
   * Extract structured data from unstructured *text*.
   *
   * Convenience wrapper around {@link create} that builds a data-extraction
   * prompt automatically and parses the JSON from the response.
   *
   * @returns The deserialised structured object.
   */
  async extract(params: ExtractParams): Promise<Record<string, unknown>> {
    const {
      model,
      text,
      jsonSchema,
      fieldDescription = "Extract the requested information.",
      maxTokens = 4096,
      effort,
      ...extra
    } = params;

    const userMessage: Record<string, unknown> = {
      role: "user",
      content: `${fieldDescription}\n\nInput text:\n${text}\n\nReturn ONLY the JSON object, with no additional text.`,
    };

    const systemPrompt =
      "You are a data extraction assistant. " +
      "Your only task is to extract structured information from the " +
      "provided text. Always return valid JSON conforming to the " +
      "specified schema. Do NOT include explanations, markdown " +
      "fencing, or any text outside the JSON object.";

    const response = await this.create({
      model,
      messages: [userMessage],
      jsonSchema,
      system: systemPrompt,
      maxTokens,
      effort,
      ...extra,
    });

    const content = response["content"];
    if (!Array.isArray(content) || content.length === 0) {
      throw new Error("Response content is empty or not an array");
    }
    const rawText = (content[0] as Record<string, unknown>)["text"];
    if (typeof rawText !== "string") {
      throw new Error("Response content[0].text is not a string");
    }
    return parseJsonResponse(rawText);
  }
}

// ---------------------------------------------------------------------------
// Internal helpers
// ---------------------------------------------------------------------------

const JSON_BLOCK_RE = /```(?:json)?\s*\n?(.*?)\n?```/s;

/**
 * Parse a JSON object from a model response that may include markdown.
 *
 * Tries (in order):
 * 1. ``JSON.parse`` on the raw text.
 * 2. Extract content from a ```json ... ``` fenced block.
 * 3. Extract content from a ``` ... ``` fenced block.
 * 4. Find the outermost ``{ ... }`` pair.
 */
export function parseJsonResponse(text: string): Record<string, unknown> {
  // Attempt 1: pure JSON
  try {
    const result = JSON.parse(text);
    if (typeof result === "object" && result !== null && !Array.isArray(result)) {
      return result as Record<string, unknown>;
    }
    throw new Error("Parsed value is not a JSON object");
  } catch {
    // fall through
  }

  // Attempt 2: ```json ... ``` or ``` ... ```
  const m = JSON_BLOCK_RE.exec(text);
  if (m?.[1]) {
    const result = JSON.parse(m[1]);
    if (typeof result === "object" && result !== null && !Array.isArray(result)) {
      return result as Record<string, unknown>;
    }
  }

  // Attempt 3: find the outermost { ... } pair
  const start = text.indexOf("{");
  const end = text.lastIndexOf("}");
  if (start !== -1 && end !== -1 && end > start) {
    const result = JSON.parse(text.slice(start, end + 1));
    if (typeof result === "object" && result !== null && !Array.isArray(result)) {
      return result as Record<string, unknown>;
    }
  }

  throw new Error(`Could not parse JSON from response text: ${text.slice(0, 200)}`);
}
