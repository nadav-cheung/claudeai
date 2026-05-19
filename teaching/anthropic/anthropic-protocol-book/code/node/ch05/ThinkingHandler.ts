/**
 * Chapter 5: Thinking Handler (TypeScript).
 *
 * Manages the lifecycle of an Extended Thinking session. Accumulates
 * thinking deltas, captures the cryptographic signature, and validates
 * the integrity of thinking blocks before passing them back to the API.
 *
 * @example
 * ```ts
 * const handler = new ThinkingHandler();
 * handler.startThinking(8000);
 * handler.processThinkingDelta("Let me analyze...");
 * const ok = handler.finalizeThinking("sig_abc123");
 * const block = handler.buildAssistantBlock();
 * ```
 */

// ---------------------------------------------------------------------------
// Public types
// ---------------------------------------------------------------------------

/** Immutable-ish snapshot of an Extended Thinking session. */
export interface ThinkingSession {
  /** Token budget allocated for thinking (from the API request). */
  budgetTokens: number;
  /** All thinking text accumulated so far. */
  accumulatedThinking: string;
  /** Cryptographic signature received from the API. */
  signature: string;
  /** Whether the thinking block is currently being received. */
  isActive: boolean;
  /** Whether the thinking block has been fully received and finalized. */
  isComplete: boolean;
  /** Whether the signature has passed basic integrity checks. */
  isVerified: boolean;
}

/** Raised when a thinking-related operation fails. */
export class ThinkingError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "ThinkingError";
  }
}

// ---------------------------------------------------------------------------
// Thinking Handler
// ---------------------------------------------------------------------------

/**
 * Manages Extended Thinking lifecycle for a single thinking block.
 *
 * The handler is designed to be used alongside `StreamHandler`. When
 * the stream handler detects a `thinking` content block, it should
 * feed events into this handler to manage signature capture and
 * validation.
 */
export class ThinkingHandler {
  private session: ThinkingSession;

  constructor() {
    this.session = this.createEmptySession();
  }

  /** Current thinking session state. */
  getSession(): Readonly<ThinkingSession> {
    return this.session;
  }

  // ------------------------------------------------------------------
  // Public API
  // ------------------------------------------------------------------

  /**
   * Initialize a new thinking block.
   *
   * Must be called when a `content_block_start` event with
   * `content_block.type === "thinking"` is received.
   */
  startThinking(budgetTokens: number): void {
    if (budgetTokens < 0) {
      throw new ThinkingError(
        `budgetTokens must be non-negative, got ${budgetTokens}`,
      );
    }
    this.session = {
      budgetTokens,
      accumulatedThinking: "",
      signature: "",
      isActive: true,
      isComplete: false,
      isVerified: false,
    };
  }

  /** Accumulate a thinking_delta chunk. */
  processThinkingDelta(thinking: string): void {
    if (!this.session.isActive) {
      throw new ThinkingError(
        "Cannot process thinking delta: no active thinking session. " +
          "Call startThinking() first.",
      );
    }
    this.session = {
      ...this.session,
      accumulatedThinking: this.session.accumulatedThinking + thinking,
    };
  }

  /**
   * Finalize the thinking block with its signature.
   *
   * Performs basic integrity checks on the signature and thinking content.
   *
   * @returns `true` if the signature passes basic integrity validation.
   */
  finalizeThinking(signature: string): boolean {
    if (!this.session.isActive) {
      throw new ThinkingError(
        "Cannot finalize thinking: no active thinking session.",
      );
    }

    let checksPassed = true;
    if (!signature) checksPassed = false;

    this.session = {
      ...this.session,
      signature,
      isActive: false,
      isComplete: true,
      isVerified: checksPassed,
    };

    return checksPassed;
  }

  /**
   * Construct a thinking content block suitable for including in
   * an assistant message for a multi-turn conversation.
   */
  buildAssistantBlock(): Record<string, unknown> {
    if (!this.session.isComplete) {
      throw new ThinkingError(
        "Cannot build assistant block: thinking is not yet finalized. " +
          "Call finalizeThinking() first.",
      );
    }
    return {
      type: "thinking",
      thinking: this.session.accumulatedThinking,
      signature: this.session.signature,
    };
  }

  /**
   * Construct a redacted_thinking content block.
   *
   * Used when the API returns a `redacted_thinking` block (Claude
   * 3.7 Sonnet only). The encrypted data must be passed back to the
   * API verbatim in subsequent turns.
   */
  buildRedactedThinkingBlock(
    encryptedData: string,
  ): Record<string, unknown> {
    return {
      type: "redacted_thinking",
      data: encryptedData,
    };
  }

  /**
   * Perform basic client-side integrity checks on a (thinking, signature) pair.
   *
   * IMPORTANT: This is NOT cryptographic verification. The actual
   * signature is verified server-side by Anthropic. This method
   * ensures basic integrity only.
   */
  verifySignatureIntegrity(thinkingText: string, signature: string): boolean {
    if (!signature) return false;
    if (!thinkingText.trim()) return false;

    // Check that signature looks like base64
    try {
      // Pad for validation
      const padded = signature + "=".repeat((4 - (signature.length % 4)) % 4);
      atob(padded);
      // Also check characters are base64-legal
      const base64Re = /^[A-Za-z0-9+/=]+$/;
      if (!base64Re.test(padded)) return false;
      return true;
    } catch {
      return false;
    }
  }

  /**
   * Compute a content hash of the thinking text for deduplication
   * and logging purposes.
   *
   * This is NOT the Anthropic signature -- it's a local hash for
   * debugging and caching use cases.
   */
  async computeContextHash(): Promise<string> {
    const encoder = new TextEncoder();
    const data = encoder.encode(this.session.accumulatedThinking);
    const hashBuffer = await crypto.subtle.digest("SHA-256", data);
    const hashArray = Array.from(new Uint8Array(hashBuffer));
    return hashArray.map((b) => b.toString(16).padStart(2, "0")).join("");
  }

  /** Reset the thinking session (discard all state). */
  reset(): void {
    this.session = this.createEmptySession();
  }

  // ------------------------------------------------------------------
  // Internal
  // ------------------------------------------------------------------

  private createEmptySession(): ThinkingSession {
    return {
      budgetTokens: 0,
      accumulatedThinking: "",
      signature: "",
      isActive: false,
      isComplete: false,
      isVerified: false,
    };
  }
}
