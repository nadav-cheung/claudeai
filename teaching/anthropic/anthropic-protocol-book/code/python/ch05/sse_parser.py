"""
Chapter 5: SSE (Server-Sent Events) Parser.

A dependency-free, incremental SSE parser that conforms to the WHATWG
Server-Sent Events specification.  Handles chunked input, multi-line
data fields, keepalive pings, and boundary-spanning events.

Usage::

    parser = SSEParser()
    for chunk in http_response.iter_bytes():
        for event in parser.feed(chunk):
            handle(event)
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any


# ---------------------------------------------------------------------------
# Public types
# ---------------------------------------------------------------------------


@dataclass
class ParsedEvent:
    """A single decoded SSE event ready for application consumption."""

    event: str
    """Event type (e.g. ``message_start``, ``content_block_delta``)."""

    data: dict[str, Any]
    """Parsed JSON data carried by the event."""


@dataclass
class SSEParseError(Exception):
    """Raised when an SSE event cannot be parsed correctly."""

    message: str
    raw_data: str | None = None


# ---------------------------------------------------------------------------
# SSE Parser
# ---------------------------------------------------------------------------


class SSEParser:
    """Incremental SSE (Server-Sent Events) parser.

    Feed raw bytes as they arrive from the network.  The parser
    buffers incomplete events internally and yields complete,
    parsed events as they are detected.

    Design decisions
    ----------------
    - **Zero allocations for idle connections:** ``feed(b\"\")`` is a
      near-no-op -- only a bounds check on the buffer.
    - **No regex.** The parser uses `.split()` and `.partition()` for speed.
    - **Comment/keepalive filtering.** ``ping`` events and comment lines
      are silently dropped -- they never appear in the output.
    """

    def __init__(self) -> None:
        self._buffer: str = ""

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def feed(self, chunk: bytes) -> list[ParsedEvent]:
        """Feed raw bytes into the parser.

        Returns a list of zero or more complete :class:`ParsedEvent`
        objects decoded from the stream so far.
        """
        # Normalize line endings: \r\n → \n, standalone \r → \n
        text = chunk.decode("utf-8", errors="replace")
        text = text.replace("\r\n", "\n").replace("\r", "\n")
        self._buffer += text

        events: list[ParsedEvent] = []
        while True:
            idx = self._buffer.find("\n\n")
            if idx == -1:
                break
            event_text = self._buffer[:idx]
            self._buffer = self._buffer[idx + 2 :]  # skip the \n\n
            parsed = self._parse_event(event_text)
            if parsed is not None:
                events.append(parsed)
        return events

    def flush(self) -> list[ParsedEvent]:
        """Return any remaining complete events in the buffer.

        Call this when the underlying stream has closed to drain the
        last event (which might not end with ``\\n\\n``).
        """
        if not self._buffer.strip():
            self._buffer = ""
            return []
        events: list[ParsedEvent] = []
        parsed = self._parse_event(self._buffer)
        if parsed is not None:
            events.append(parsed)
        self._buffer = ""
        return events

    def reset(self) -> None:
        """Reset the parser to a pristine state (discards buffer)."""
        self._buffer = ""

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_event(event_text: str) -> ParsedEvent | None:
        """Parse a single SSE event from its text representation.

        Implements the WHATWG SSE parsing algorithm for a single
        event block (text between two ``\\n\\n`` delimiters).

        Returns ``None`` for events that should be silently ignored
        (comments, keepalive pings with no data).
        """
        event_type: str = "message"
        data_parts: list[str] = []

        for line in event_text.split("\n"):
            line = line.rstrip("\r")

            # Empty line -- ignored
            if line == "":
                continue

            # Comment line (starts with colon) -- ignored
            if line.startswith(":"):
                continue

            # Look for the colon separator
            colon_pos = line.find(":")
            if colon_pos == -1:
                # Field with no value -- treat as empty field
                field_name = line
                field_value = ""
            else:
                field_name = line[:colon_pos]
                # Skip exactly one optional space after colon
                if len(line) > colon_pos + 1 and line[colon_pos + 1] == " ":
                    field_value = line[colon_pos + 2 :]
                else:
                    field_value = line[colon_pos + 1 :]

            if field_name == "event":
                event_type = field_value
            elif field_name == "data":
                data_parts.append(field_value)
            # id and retry fields are accepted but not used by
            # Anthropic's API, so we ignore them.

        # If no data parts, treat as keepalive/comment
        if not data_parts:
            return None

        # Merge multiple data lines with LF
        merged_data = "\n".join(data_parts)

        # Parse JSON
        try:
            parsed_data: dict[str, Any] = json.loads(merged_data)
        except json.JSONDecodeError as exc:
            raise SSEParseError(
                f"Invalid JSON in SSE data field: {exc}",
                raw_data=merged_data,
            ) from exc

        # Silently drop ping events -- they are transport-layer keepalives
        if event_type == "ping" or parsed_data.get("type") == "ping":
            return None

        return ParsedEvent(event=event_type, data=parsed_data)
