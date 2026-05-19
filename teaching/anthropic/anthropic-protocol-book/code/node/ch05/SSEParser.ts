/**
 * Chapter 5: SSE (Server-Sent Events) Parser (TypeScript).
 *
 * A dependency-free, incremental SSE parser that conforms to the WHATWG
 * Server-Sent Events specification. Handles chunked input, multi-line
 * data fields, keepalive pings, and boundary-spanning events.
 *
 * @example
 * ```ts
 * const parser = new SSEParser();
 * for (const event of parser.feed(chunk)) {
 *   console.log(event.event, event.data);
 * }
 * ```
 */

// ---------------------------------------------------------------------------
// Public types
// ---------------------------------------------------------------------------

/** A single decoded SSE event ready for application consumption. */
export interface ParsedEvent {
  /** Event type (e.g. "message_start", "content_block_delta"). */
  readonly event: string;
  /** Parsed JSON data carried by the event. */
  readonly data: Record<string, unknown>;
}

/** Raised when an SSE event cannot be parsed correctly. */
export class SSEParseError extends Error {
  readonly rawData: string | null;

  constructor(message: string, rawData?: string) {
    super(message);
    this.name = "SSEParseError";
    this.rawData = rawData ?? null;
  }
}

// ---------------------------------------------------------------------------
// SSE Parser
// ---------------------------------------------------------------------------

/**
 * Incremental SSE (Server-Sent Events) parser.
 *
 * Feed raw data as it arrives from the network. The parser buffers
 * incomplete events internally and yields complete, parsed events
 * as they are detected.
 */
export class SSEParser {
  private buffer = "";

  /**
   * Feed a chunk of raw SSE data into the parser.
   *
   * @returns Zero or more complete `ParsedEvent` objects decoded from
   *          the stream so far.
   */
  feed(chunk: string): ParsedEvent[] {
    this.buffer += chunk.replace(/\r\n/g, "\n").replace(/\r/g, "\n");

    const events: ParsedEvent[] = [];

    // eslint-disable-next-line no-constant-condition
    while (true) {
      const idx = this.buffer.indexOf("\n\n");
      if (idx === -1) break;

      const eventText = this.buffer.slice(0, idx);
      this.buffer = this.buffer.slice(idx + 2); // skip the \n\n
      const parsed = this.parseEvent(eventText);
      if (parsed !== null) {
        events.push(parsed);
      }
    }

    return events;
  }

  /**
   * Return any remaining complete events in the buffer.
   *
   * Call this when the underlying stream has closed to drain the
   * last event (which may not end with `\n\n`).
   */
  flush(): ParsedEvent[] {
    if (this.buffer.trim() === "") {
      this.buffer = "";
      return [];
    }

    const events: ParsedEvent[] = [];
    const parsed = this.parseEvent(this.buffer);
    if (parsed !== null) {
      events.push(parsed);
    }
    this.buffer = "";
    return events;
  }

  /** Reset the parser to a pristine state (discards buffer). */
  reset(): void {
    this.buffer = "";
  }

  // ------------------------------------------------------------------
  // Internal helpers
  // ------------------------------------------------------------------

  /**
   * Parse a single SSE event from its text representation.
   *
   * Implements the WHATWG SSE parsing algorithm for a single
   * event block (text between two `\n\n` delimiters).
   *
   * @returns A `ParsedEvent`, or `null` for events that should be
   *          silently ignored (comments, keepalive pings).
   */
  private parseEvent(eventText: string): ParsedEvent | null {
    let eventType = "message";
    const dataParts: string[] = [];

    for (const line of eventText.split("\n")) {
      const trimmed = line.endsWith("\r") ? line.slice(0, -1) : line;

      // Empty line -- ignored
      if (trimmed === "") continue;

      // Comment line (starts with colon) -- ignored
      if (trimmed.startsWith(":")) continue;

      // Look for the colon separator
      const colonPos = trimmed.indexOf(":");
      let fieldName: string;
      let fieldValue: string;

      if (colonPos === -1) {
        // Field with no value
        fieldName = trimmed;
        fieldValue = "";
      } else {
        fieldName = trimmed.slice(0, colonPos);
        // Skip exactly one optional space after colon
        if (trimmed.length > colonPos + 1 && trimmed[colonPos + 1] === " ") {
          fieldValue = trimmed.slice(colonPos + 2);
        } else {
          fieldValue = trimmed.slice(colonPos + 1);
        }
      }

      if (fieldName === "event") {
        eventType = fieldValue;
      } else if (fieldName === "data") {
        dataParts.push(fieldValue);
      }
      // id and retry fields are accepted but not used by Anthropic's API
    }

    // If no data parts, treat as keepalive/comment
    if (dataParts.length === 0) return null;

    const mergedData = dataParts.join("\n");

    // Parse JSON
    let parsedData: Record<string, unknown>;
    try {
      parsedData = JSON.parse(mergedData) as Record<string, unknown>;
    } catch (err) {
      throw new SSEParseError(
        `Invalid JSON in SSE data field: ${err instanceof Error ? err.message : String(err)}`,
        mergedData,
      );
    }

    // Silently drop ping events -- transport-layer keepalives
    if (eventType === "ping" || parsedData["type"] === "ping") {
      return null;
    }

    return { event: eventType, data: parsedData };
  }
}
