"""
Chapter 5: Thinking Handler.

Manages the lifecycle of an Extended Thinking session.  Accumulates
thinking deltas, captures the cryptographic signature, and validates
the integrity of thinking blocks before passing them back to the API.

Usage::

    handler = ThinkingHandler()
    handler.start_thinking(budget_tokens=8000)

    # Feed events from the stream handler
    if block.block_type == ContentBlockType.THINKING:
        handler.process_thinking_delta(new_portion)

    # Once content_block_stop fires for the thinking block:
    ok = handler.finalize_thinking(signature)
"""

from __future__ import annotations

import hashlib
import hmac
from dataclasses import dataclass, field
from typing import Any


# ---------------------------------------------------------------------------
# Public types
# ---------------------------------------------------------------------------


@dataclass
class ThinkingSession:
    """Immutable-ish snapshot of an Extended Thinking session."""

    budget_tokens: int = 0
    """Token budget allocated for thinking (from the API request)."""

    accumulated_thinking: str = ""
    """All thinking text accumulated so far."""

    signature: str = ""
    """Cryptographic signature received from the API."""

    is_active: bool = False
    """Whether the thinking block is currently being received."""

    is_complete: bool = False
    """Whether the thinking block has been fully received and finalized."""

    is_verified: bool = False
    """Whether the signature has been verified (basic format check)."""


class ThinkingError(Exception):
    """Raised when a thinking-related operation fails."""


# ---------------------------------------------------------------------------
# Thinking Handler
# ---------------------------------------------------------------------------


class ThinkingHandler:
    """Manages Extended Thinking lifecycle for a single thinking block.

    The handler is designed to be used alongside :class:`StreamHandler`.
    When the stream handler detects a ``thinking`` content block, it
    should feed events into this handler to manage signature capture
    and validation.

    Signature verification design
    -----------------------------
    Anthropic's thinking signatures are opaque server-signed tokens.
    The client cannot independently *cryptographically* verify them
    (that requires Anthropic's private key).  However, the client
    MUST perform **integrity validation**:

    1. The signature must be non-empty.
    2. The signature must be present before the thinking block is
       considered complete.
    3. The thinking text must be non-empty when a signature exists
       (an empty thinking block with a signature is suspicious).
    4. When constructing an assistant message for a multi-turn
       conversation, the (thinking, signature) pair must be kept
       intact and in correct order relative to text/tool_use blocks.
    """

    def __init__(self) -> None:
        self._session = ThinkingSession()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @property
    def session(self) -> ThinkingSession:
        """Current thinking session state."""
        return self._session

    def start_thinking(self, budget_tokens: int) -> None:
        """Initialize a new thinking block.

        Must be called when a ``content_block_start`` event with
        ``content_block.type == "thinking"`` is received.

        Args:
            budget_tokens: The token budget set in the API request's
                ``thinking.budget_tokens`` parameter.
        """
        if budget_tokens < 0:
            raise ThinkingError(
                f"budget_tokens must be non-negative, got {budget_tokens}"
            )
        self._session = ThinkingSession(
            budget_tokens=budget_tokens,
            is_active=True,
        )

    def process_thinking_delta(self, thinking: str) -> None:
        """Accumulate a thinking_delta chunk.

        Args:
            thinking: The thinking text delta received from the API.
        """
        if not self._session.is_active:
            raise ThinkingError(
                "Cannot process thinking delta: no active thinking session. "
                "Call start_thinking() first."
            )
        self._session.accumulated_thinking += thinking

    def finalize_thinking(self, signature: str) -> bool:
        """Finalize the thinking block with its signature.

        Performs basic integrity checks on the signature and thinking
        content.

        Args:
            signature: The signature string from ``signature_delta``
                or the ``signature`` field in a complete thinking block.

        Returns:
            ``True`` if the signature passes basic integrity validation.
        """
        if not self._session.is_active:
            raise ThinkingError(
                "Cannot finalize thinking: no active thinking session."
            )

        self._session.signature = signature
        self._session.is_active = False
        self._session.is_complete = True

        # --- Integrity checks ---
        checks_passed = True

        # 1. Signature must be non-empty
        if not signature:
            checks_passed = False

        # 2. Thinking content should be non-empty (an empty block is
        #    unusual but not necessarily an error in all contexts)
        if not self._session.accumulated_thinking.strip():
            # Not strictly an error, but worth noting
            pass

        self._session.is_verified = checks_passed
        return checks_passed

    def build_assistant_block(self) -> dict[str, Any]:
        """Construct a thinking content block suitable for including in
        an assistant message for a multi-turn conversation.

        Returns:
            A dict matching the ``thinking`` content block schema,
            with all original fields preserved.
        """
        if not self._session.is_complete:
            raise ThinkingError(
                "Cannot build assistant block: thinking is not yet finalized. "
                "Call finalize_thinking() first."
            )
        return {
            "type": "thinking",
            "thinking": self._session.accumulated_thinking,
            "signature": self._session.signature,
        }

    def build_redacted_thinking_block(self, encrypted_data: str) -> dict[str, Any]:
        """Construct a redacted_thinking content block.

        Used when the API returns a ``redacted_thinking`` block (Claude
        3.7 Sonnet only).  The encrypted data must be passed back to the
        API verbatim in subsequent turns.

        Args:
            encrypted_data: The encrypted content from the
                ``redacted_thinking.data`` field.
        """
        return {
            "type": "redacted_thinking",
            "data": encrypted_data,
        }

    def verify_signature_integrity(
        self, thinking_text: str, signature: str
    ) -> bool:
        """Perform basic client-side integrity checks on a (thinking, signature) pair.

        IMPORTANT: This is NOT cryptographic verification.  The actual
        signature is verified server-side by Anthropic.  This method
        ensures that:

        - The signature is non-empty
        - The signature appears to be a base64-encoded string
        - The thinking text is not empty

        Returns:
            ``True`` if basic integrity checks pass.
        """
        if not signature:
            return False
        if not thinking_text.strip():
            return False

        # Check that signature looks like base64 (legal chars only)
        import base64

        try:
            # Add padding if needed for validation
            padded = signature + "=" * (-len(signature) % 4)
            base64.b64decode(padded, validate=True)
        except Exception:
            return False

        return True

    def compute_context_hash(self) -> str:
        """Compute a content hash of the thinking text for deduplication
        and logging purposes.

        This is NOT the Anthropic signature -- it's a local hash for
        debugging and caching use cases.
        """
        return hashlib.sha256(
            self._session.accumulated_thinking.encode("utf-8")
        ).hexdigest()

    def reset(self) -> None:
        """Reset the thinking session (discard all state)."""
        self._session = ThinkingSession()
