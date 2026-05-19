"""
Chapter 5: Stream Handler.

High-level event dispatcher that sits on top of :class:`SSEParser`
and provides business-level semantics for Anthropic streaming
responses.  Accumulates text, tracks content blocks, surfaces usage
stats, and routes errors.

Usage::

    handler = StreamHandler()
    handler.handle_event(parsed_event)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any


# ---------------------------------------------------------------------------
# Supporting types
# ---------------------------------------------------------------------------


class ContentBlockType(Enum):
    TEXT = auto()
    THINKING = auto()
    TOOL_USE = auto()
    REDACTED_THINKING = auto()
    UNKNOWN = auto()


@dataclass
class ContentBlock:
    """Represents a single content block being accumulated from a stream."""

    index: int
    block_type: ContentBlockType = ContentBlockType.UNKNOWN
    text: str = ""
    thinking: str = ""
    signature: str = ""
    tool_use_id: str = ""
    tool_name: str = ""
    tool_input: str = ""  # accumulated partial JSON
    finished: bool = False


@dataclass
class StreamState:
    """Snapshot of the current stream processing state."""

    message_id: str = ""
    model: str = ""
    role: str = ""
    content_blocks: list[ContentBlock] = field(default_factory=list)
    stop_reason: str | None = None
    stop_sequence: str | None = None
    input_tokens: int = 0
    output_tokens: int = 0
    finished: bool = False
    error: dict[str, Any] | None = None

    @property
    def text(self) -> str:
        """Concatenated text from all text-type content blocks."""
        return "".join(
            b.text
            for b in self.content_blocks
            if b.block_type == ContentBlockType.TEXT
        )

    @property
    def thinking_text(self) -> str:
        """Concatenated thinking from all thinking-type content blocks."""
        return "".join(
            b.thinking
            for b in self.content_blocks
            if b.block_type == ContentBlockType.THINKING
        )


# ---------------------------------------------------------------------------
# Event payload type (discriminated union via type field)
# ---------------------------------------------------------------------------

@dataclass
class _RawEvent:
    type: str
    index: int | None = None
    delta: dict[str, Any] | None = None
    content_block: dict[str, Any] | None = None
    message: dict[str, Any] | None = None
    usage: dict[str, Any] | None = None
    error: dict[str, Any] | None = None


# ---------------------------------------------------------------------------
# Stream Handler
# ---------------------------------------------------------------------------


class StreamHandler:
    """High-level handler for Anthropic streaming events.

    Translates raw SSE events into accumulated state and emits
    displayable text deltas to the caller.

    Usage::

        state = StreamState()
        handler = StreamHandler(state)

        for parsed_event in parser.feed(chunk):
            text = handler.handle_event(parsed_event)
            if text:
                print(text, end="", flush=True)
    """

    def __init__(self, state: StreamState | None = None) -> None:
        self._state = state or StreamState()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @property
    def state(self) -> StreamState:
        """Current accumulated stream state."""
        return self._state

    def handle_event(self, event: dict[str, Any]) -> str | None:
        """Dispatch a single parsed SSE event.

        Returns:
            A displayable text string if the event carries a text
            delta, or ``None`` for non-text events.
        """
        event_type = event.get("type", "")
        if not event_type:
            return None

        handler = _DISPATCH.get(event_type)
        if handler is not None:
            return handler(self, event)
        # Unknown event types are silently ignored per Anthropic's
        # versioning policy.
        return None

    # ------------------------------------------------------------------
    # Event handlers (one per Anthropic event type)
    # ------------------------------------------------------------------

    def _on_message_start(self, event: dict[str, Any]) -> None:
        msg = event.get("message", {})
        self._state.message_id = msg.get("id", "")
        self._state.model = msg.get("model", "")
        self._state.role = msg.get("role", "")
        usage = msg.get("usage", {})
        self._state.input_tokens = usage.get("input_tokens", 0)
        self._state.output_tokens = usage.get("output_tokens", 0)
        self._state.content_blocks = []

    def _on_content_block_start(self, event: dict[str, Any]) -> None:
        index = event.get("index", -1)
        block_data = event.get("content_block", {})
        block_type_str = block_data.get("type", "")

        block_type = _block_type_from_str(block_type_str)

        block = ContentBlock(index=index, block_type=block_type)

        if block_type == ContentBlockType.TOOL_USE:
            block.tool_use_id = block_data.get("id", "")
            block.tool_name = block_data.get("name", "")

        # Ensure content_blocks list is large enough
        while len(self._state.content_blocks) <= index:
            self._state.content_blocks.append(
                ContentBlock(index=len(self._state.content_blocks))
            )
        self._state.content_blocks[index] = block

    def _on_content_block_delta(self, event: dict[str, Any]) -> str | None:
        index = event.get("index", -1)
        delta = event.get("delta", {})
        delta_type = delta.get("type", "")

        # Ensure block exists
        while len(self._state.content_blocks) <= index:
            self._state.content_blocks.append(ContentBlock(index=index))
        block = self._state.content_blocks[index]

        if delta_type == "text_delta":
            text = delta.get("text", "")
            block.text += text
            if block.block_type == ContentBlockType.UNKNOWN:
                block.block_type = ContentBlockType.TEXT
            return text

        elif delta_type == "thinking_delta":
            thinking = delta.get("thinking", "")
            block.thinking += thinking
            if block.block_type == ContentBlockType.UNKNOWN:
                block.block_type = ContentBlockType.THINKING
            return None

        elif delta_type == "signature_delta":
            block.signature = delta.get("signature", "")
            return None

        elif delta_type == "input_json_delta":
            partial = delta.get("partial_json", "")
            block.tool_input += partial
            return None

        elif delta_type == "citations_delta":
            # Citations are accumulated but not returned as text
            return None

        # Unknown delta types are silently ignored.
        return None

    def _on_content_block_stop(self, event: dict[str, Any]) -> None:
        index = event.get("index", -1)
        while len(self._state.content_blocks) <= index:
            self._state.content_blocks.append(ContentBlock(index=index))
        self._state.content_blocks[index].finished = True

    def _on_message_delta(self, event: dict[str, Any]) -> None:
        delta = event.get("delta", {})
        self._state.stop_reason = delta.get("stop_reason")
        self._state.stop_sequence = delta.get("stop_sequence")
        usage = event.get("usage", {})
        self._state.output_tokens = usage.get("output_tokens", self._state.output_tokens)

    def _on_message_stop(self, event: dict[str, Any]) -> None:  # noqa: ARG002
        self._state.finished = True

    def _on_ping(self, event: dict[str, Any]) -> None:  # noqa: ARG002
        pass  # Transport-level keepalive -- nothing to do.

    def _on_error(self, event: dict[str, Any]) -> None:
        self._state.error = event.get("error", {})
        self._state.finished = True

    # ------------------------------------------------------------------
    # Convenience
    # ------------------------------------------------------------------

    def get_final_message(self) -> dict[str, Any]:
        """Construct a Message object from accumulated state.

        This mimics the structure returned by the non-streaming API.
        """
        content: list[dict[str, Any]] = []
        for block in self._state.content_blocks:
            if not block.finished:
                continue
            if block.block_type == ContentBlockType.TEXT:
                content.append({"type": "text", "text": block.text})
            elif block.block_type == ContentBlockType.THINKING:
                content.append(
                    {
                        "type": "thinking",
                        "thinking": block.thinking,
                        "signature": block.signature,
                    }
                )
            elif block.block_type == ContentBlockType.TOOL_USE:
                import json

                try:
                    tool_input = json.loads(block.tool_input) if block.tool_input else {}
                except json.JSONDecodeError:
                    tool_input = {}
                content.append(
                    {
                        "type": "tool_use",
                        "id": block.tool_use_id,
                        "name": block.tool_name,
                        "input": tool_input,
                    }
                )
            elif block.block_type == ContentBlockType.REDACTED_THINKING:
                content.append(
                    {
                        "type": "redacted_thinking",
                        "data": block.thinking,
                    }
                )

        return {
            "id": self._state.message_id,
            "type": "message",
            "role": self._state.role or "assistant",
            "model": self._state.model,
            "content": content,
            "stop_reason": self._state.stop_reason,
            "stop_sequence": self._state.stop_sequence,
            "usage": {
                "input_tokens": self._state.input_tokens,
                "output_tokens": self._state.output_tokens,
            },
        }

    def reset(self) -> None:
        """Reset all accumulated state (for reuse)."""
        self._state = StreamState()


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _block_type_from_str(s: str) -> ContentBlockType:
    """Map a string content block type to the enum."""
    mapping: dict[str, ContentBlockType] = {
        "text": ContentBlockType.TEXT,
        "thinking": ContentBlockType.THINKING,
        "redacted_thinking": ContentBlockType.REDACTED_THINKING,
        "tool_use": ContentBlockType.TOOL_USE,
    }
    return mapping.get(s, ContentBlockType.UNKNOWN)


# Dispatch table -- maps event types to handler methods
_DISPATCH: dict[str, Any] = {
    "message_start": StreamHandler._on_message_start,
    "content_block_start": StreamHandler._on_content_block_start,
    "content_block_delta": StreamHandler._on_content_block_delta,
    "content_block_stop": StreamHandler._on_content_block_stop,
    "message_delta": StreamHandler._on_message_delta,
    "message_stop": StreamHandler._on_message_stop,
    "ping": StreamHandler._on_ping,
    "error": StreamHandler._on_error,
}
