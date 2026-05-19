"""
Tests for Chapter 5: SSE Parser, Stream Handler, and Thinking Handler.

Covers:
- SSEParser: chunked input, boundary-spanning events, ping filtering,
  multi-line data, comment handling, error handling
- StreamHandler: full event lifecycle, text accumulation, thinking
  block handling, tool_use handling, final message construction
- ThinkingHandler: session lifecycle, signature validation,
  assistant block construction, redacted thinking, context hash
"""

from __future__ import annotations

import json
import pytest

from sse_parser import SSEParser, ParsedEvent, SSEParseError
from stream_handler import (
    StreamHandler,
    StreamState,
    ContentBlockType,
    ContentBlock,
)
from thinking_handler import (
    ThinkingHandler,
    ThinkingSession,
    ThinkingError,
)


# ============================================================================
# SSEParser Tests
# ============================================================================


class TestSSEParserBasic:
    """Tests for basic SSE parsing (single-chunk, single event)."""

    def test_single_message_start_event(self):
        parser = SSEParser()
        raw = (
            b'event: message_start\n'
            b'data: {"type": "message_start", "message": {"id": "msg_01", "model": "claude-3"}}\n\n'
        )
        events = parser.feed(raw)
        assert len(events) == 1
        assert events[0].event == "message_start"
        assert events[0].data["type"] == "message_start"
        assert events[0].data["message"]["id"] == "msg_01"

    def test_single_content_block_delta(self):
        parser = SSEParser()
        raw = (
            b'event: content_block_delta\n'
            b'data: {"type": "content_block_delta", "index": 0, "delta": {"type": "text_delta", "text": "Hello"}}\n\n'
        )
        events = parser.feed(raw)
        assert len(events) == 1
        assert events[0].event == "content_block_delta"
        assert events[0].data["delta"]["text"] == "Hello"

    def test_ping_events_are_filtered(self):
        parser = SSEParser()
        raw = (
            b'event: ping\n'
            b'data: {"type": "ping"}\n\n'
        )
        events = parser.feed(raw)
        assert len(events) == 0  # ping should be silently dropped

    def test_comment_lines_are_ignored(self):
        parser = SSEParser()
        raw = (
            b': this is a comment\n'
            b'event: message_stop\n'
            b'data: {"type": "message_stop"}\n\n'
        )
        events = parser.feed(raw)
        assert len(events) == 1
        assert events[0].event == "message_stop"


class TestSSEParserChunked:
    """Tests for incremental parsing across multiple chunks."""

    def test_event_split_across_chunks(self):
        parser = SSEParser()
        chunk1 = b'event: content_block_delta\ndata: {"type": "content_block_d'
        chunk2 = b'elta", "index": 0, "delta": {"type": "text_delta", "text": "Hello"}}\n\n'

        events1 = parser.feed(chunk1)
        assert len(events1) == 0  # incomplete

        events2 = parser.feed(chunk2)
        assert len(events2) == 1
        assert events2[0].event == "content_block_delta"

    def test_multiple_events_in_one_chunk(self):
        parser = SSEParser()
        raw = (
            b'event: message_start\ndata: {"type": "message_start", "message": {"id": "A"}}\n\n'
            b'event: content_block_delta\ndata: {"type": "content_block_delta", "index": 0, "delta": {"type": "text_delta", "text": "X"}}\n\n'
            b'event: message_stop\ndata: {"type": "message_stop"}\n\n'
        )
        events = parser.feed(raw)
        assert len(events) == 3
        assert events[0].event == "message_start"
        assert events[1].event == "content_block_delta"
        assert events[2].event == "message_stop"

    def test_event_split_byte_by_byte(self):
        """Boundary torture test: feed one byte at a time."""
        parser = SSEParser()
        raw = b'event: message_stop\ndata: {"type": "message_stop"}\n\n'
        all_events: list[ParsedEvent] = []
        for byte in raw:
            chunk = bytes([byte])
            events = parser.feed(chunk)
            all_events.extend(events)
        assert len(all_events) == 1
        assert all_events[0].event == "message_stop"

    def test_carriage_return_handling(self):
        """Events may contain \\r\\n line endings."""
        parser = SSEParser()
        raw = (
            b'event: message_stop\r\n'
            b'data: {"type": "message_stop"}\r\n'
            b'\r\n'
        )
        events = parser.feed(raw)
        assert len(events) == 1
        assert events[0].event == "message_stop"


class TestSSEParserEdgeCases:
    """Tests for edge cases and error handling."""

    def test_multi_line_data_field(self):
        parser = SSEParser()
        raw = (
            b'event: test\n'
            b'data: {"line1": 1,\n'
            b'data: "line2": 2}\n\n'
        )
        events = parser.feed(raw)
        assert len(events) == 1
        assert events[0].data == {"line1": 1, "line2": 2}

    def test_no_event_field_defaults_to_message(self):
        parser = SSEParser()
        raw = b'data: {"type": "custom"}\n\n'
        events = parser.feed(raw)
        assert len(events) == 1
        assert events[0].event == "message"

    def test_invalid_json_raises(self):
        parser = SSEParser()
        raw = b'event: test\ndata: {invalid json}\n\n'
        with pytest.raises(SSEParseError):
            parser.feed(raw)

    def test_empty_feed_returns_no_events(self):
        parser = SSEParser()
        events = parser.feed(b"")
        assert len(events) == 0

    def test_flush_drains_remaining(self):
        parser = SSEParser()
        # Feed a partial event (no trailing \n\n)
        raw = b'event: test\ndata: {"x": 1}'
        events = parser.feed(raw)
        assert len(events) == 0  # incomplete

        flushed = parser.flush()
        assert len(flushed) == 1
        assert flushed[0].data == {"x": 1}

    def test_reset_clears_buffer(self):
        parser = SSEParser()
        parser.feed(b'event: test\ndata: {"x": 1}')  # incomplete
        parser.reset()
        events = parser.flush()
        assert len(events) == 0

    def test_ping_with_event_field(self):
        parser = SSEParser()
        raw = (
            b'event: ping\n'
            b'data: {"type": "ping"}\n\n'
        )
        events = parser.feed(raw)
        assert len(events) == 0

    def test_unknown_event_type_passed_through(self):
        """Unknown event types are preserved -- StreamHandler filters them."""
        parser = SSEParser()
        raw = (
            b'event: custom_event\n'
            b'data: {"type": "custom_event", "payload": "test"}\n\n'
        )
        events = parser.feed(raw)
        assert len(events) == 1
        assert events[0].event == "custom_event"

    def test_unicode_content(self):
        parser = SSEParser()
        raw = (
            'event: content_block_delta\n'
            'data: {"type": "content_block_delta", "index": 0, "delta": {"type": "text_delta", "text": "你好世界"}}\n\n'
        ).encode("utf-8")
        events = parser.feed(raw)
        assert len(events) == 1
        assert events[0].data["delta"]["text"] == "你好世界"


# ============================================================================
# StreamHandler Tests
# ============================================================================


class TestStreamHandlerLifecycle:
    """Tests for the complete streaming lifecycle."""

    def _make_event(self, event_type: str, **kwargs) -> dict:
        """Helper to build event dicts matching the SSE data format."""
        return {"type": event_type, **kwargs}

    def test_full_text_stream_lifecycle(self):
        state = StreamState()
        handler = StreamHandler(state)

        # message_start
        handler.handle_event(
            self._make_event(
                "message_start",
                message={
                    "id": "msg_test123",
                    "model": "claude-sonnet-4-5-20250929",
                    "role": "assistant",
                    "content": [],
                    "stop_reason": None,
                    "stop_sequence": None,
                    "usage": {"input_tokens": 10, "output_tokens": 1},
                },
            )
        )
        assert state.message_id == "msg_test123"
        assert state.input_tokens == 10

        # content_block_start (text)
        handler.handle_event(
            self._make_event(
                "content_block_start",
                index=0,
                content_block={"type": "text", "text": ""},
            )
        )
        assert len(state.content_blocks) == 1
        assert state.content_blocks[0].block_type == ContentBlockType.TEXT

        # content_block_delta x 3
        t1 = handler.handle_event(
            self._make_event(
                "content_block_delta",
                index=0,
                delta={"type": "text_delta", "text": "Hello"},
            )
        )
        assert t1 == "Hello"

        t2 = handler.handle_event(
            self._make_event(
                "content_block_delta",
                index=0,
                delta={"type": "text_delta", "text": " "},
            )
        )
        assert t2 == " "

        t3 = handler.handle_event(
            self._make_event(
                "content_block_delta",
                index=0,
                delta={"type": "text_delta", "text": "World"},
            )
        )
        assert t3 == "World"

        assert state.text == "Hello World"

        # content_block_stop
        handler.handle_event(
            self._make_event("content_block_stop", index=0)
        )
        assert state.content_blocks[0].finished is True

        # message_delta
        handler.handle_event(
            self._make_event(
                "message_delta",
                delta={"stop_reason": "end_turn", "stop_sequence": None},
                usage={"output_tokens": 15},
            )
        )
        assert state.stop_reason == "end_turn"
        assert state.output_tokens == 15

        # message_stop
        handler.handle_event(
            self._make_event("message_stop")
        )
        assert state.finished is True

        # Verify final message construction
        msg = handler.get_final_message()
        assert msg["id"] == "msg_test123"
        assert msg["stop_reason"] == "end_turn"
        assert msg["content"][0]["text"] == "Hello World"

    def test_ping_event_handled_silently(self):
        state = StreamState()
        handler = StreamHandler(state)
        result = handler.handle_event(self._make_event("ping"))
        assert result is None
        assert state.finished is False

    def test_error_event_stops_stream(self):
        state = StreamState()
        handler = StreamHandler(state)
        handler.handle_event(
            self._make_event(
                "error",
                error={"type": "overloaded_error", "message": "Overloaded"},
            )
        )
        assert state.finished is True
        assert state.error is not None
        assert state.error["type"] == "overloaded_error"

    def test_unknown_event_type_ignored(self):
        state = StreamState()
        handler = StreamHandler(state)
        # Should not raise
        result = handler.handle_event({"type": "future_event_v99"})
        assert result is None


class TestStreamHandlerThinking:
    """Tests for thinking block handling within StreamHandler."""

    def _make_event(self, event_type: str, **kwargs) -> dict:
        return {"type": event_type, **kwargs}

    def test_thinking_block_lifecycle(self):
        state = StreamState()
        handler = StreamHandler(state)

        # message_start
        handler.handle_event(
            self._make_event(
                "message_start",
                message={
                    "id": "msg_thinking",
                    "model": "claude-sonnet-4-5-20250929",
                    "role": "assistant",
                    "content": [],
                    "stop_reason": None,
                    "stop_sequence": None,
                    "usage": {"input_tokens": 20, "output_tokens": 1},
                },
            )
        )

        # thinking block start
        handler.handle_event(
            self._make_event(
                "content_block_start",
                index=0,
                content_block={"type": "thinking", "thinking": ""},
            )
        )
        assert state.content_blocks[0].block_type == ContentBlockType.THINKING

        # thinking deltas
        handler.handle_event(
            self._make_event(
                "content_block_delta",
                index=0,
                delta={"type": "thinking_delta", "thinking": "Let me think..."},
            )
        )
        assert "Let me think" in state.content_blocks[0].thinking

        # signature delta
        handler.handle_event(
            self._make_event(
                "content_block_delta",
                index=0,
                delta={
                    "type": "signature_delta",
                    "signature": "abc123signature",
                },
            )
        )
        assert state.content_blocks[0].signature == "abc123signature"

        # thinking block stop
        handler.handle_event(
            self._make_event("content_block_stop", index=0)
        )
        assert state.content_blocks[0].finished is True

        # text block
        handler.handle_event(
            self._make_event(
                "content_block_start",
                index=1,
                content_block={"type": "text", "text": ""},
            )
        )
        handler.handle_event(
            self._make_event(
                "content_block_delta",
                index=1,
                delta={"type": "text_delta", "text": "The answer is 42."},
            )
        )
        handler.handle_event(
            self._make_event("content_block_stop", index=1)
        )

        # message_delta
        handler.handle_event(
            self._make_event(
                "message_delta",
                delta={"stop_reason": "end_turn", "stop_sequence": None},
                usage={"output_tokens": 100},
            )
        )
        handler.handle_event(self._make_event("message_stop"))

        # Verify final message
        msg = handler.get_final_message()
        assert len(msg["content"]) == 2
        assert msg["content"][0]["type"] == "thinking"
        assert msg["content"][0]["signature"] == "abc123signature"
        assert msg["content"][1]["type"] == "text"
        assert msg["content"][1]["text"] == "The answer is 42."


class TestStreamHandlerToolUse:
    """Tests for tool_use block handling within StreamHandler."""

    def _make_event(self, event_type: str, **kwargs) -> dict:
        return {"type": event_type, **kwargs}

    def test_tool_use_block_lifecycle(self):
        state = StreamState()
        handler = StreamHandler(state)

        # message_start
        handler.handle_event(
            self._make_event(
                "message_start",
                message={
                    "id": "msg_tool",
                    "model": "claude-sonnet-4-5-20250929",
                    "role": "assistant",
                    "content": [],
                    "stop_reason": None,
                    "stop_sequence": None,
                    "usage": {"input_tokens": 5, "output_tokens": 1},
                },
            )
        )

        # tool_use block start
        handler.handle_event(
            self._make_event(
                "content_block_start",
                index=0,
                content_block={
                    "type": "tool_use",
                    "id": "toolu_01ABC",
                    "name": "get_weather",
                    "input": {},
                },
            )
        )
        assert state.content_blocks[0].tool_use_id == "toolu_01ABC"
        assert state.content_blocks[0].tool_name == "get_weather"

        # input_json deltas
        handler.handle_event(
            self._make_event(
                "content_block_delta",
                index=0,
                delta={
                    "type": "input_json_delta",
                    "partial_json": '{"location": "SF"}',
                },
            )
        )
        assert '"location": "SF"' in state.content_blocks[0].tool_input

        # content_block_stop
        handler.handle_event(
            self._make_event("content_block_stop", index=0)
        )

        # message_delta + stop
        handler.handle_event(
            self._make_event(
                "message_delta",
                delta={"stop_reason": "tool_use", "stop_sequence": None},
                usage={"output_tokens": 50},
            )
        )
        handler.handle_event(self._make_event("message_stop"))

        msg = handler.get_final_message()
        assert msg["stop_reason"] == "tool_use"
        assert msg["content"][0]["type"] == "tool_use"
        assert msg["content"][0]["name"] == "get_weather"

    def test_multiple_content_blocks(self):
        """Test text block followed by tool_use block."""
        state = StreamState()
        handler = StreamHandler(state)

        handler.handle_event(
            self._make_event(
                "message_start",
                message={
                    "id": "msg_multi",
                    "model": "claude-3",
                    "role": "assistant",
                    "content": [],
                    "stop_reason": None,
                    "stop_sequence": None,
                    "usage": {"input_tokens": 10, "output_tokens": 1},
                },
            )
        )

        # First block: text
        handler.handle_event(
            self._make_event(
                "content_block_start",
                index=0,
                content_block={"type": "text", "text": ""},
            )
        )
        handler.handle_event(
            self._make_event(
                "content_block_delta",
                index=0,
                delta={"type": "text_delta", "text": "Let me check."},
            )
        )
        handler.handle_event(
            self._make_event("content_block_stop", index=0)
        )

        # Second block: tool_use (at index 1)
        handler.handle_event(
            self._make_event(
                "content_block_start",
                index=1,
                content_block={
                    "type": "tool_use",
                    "id": "toolu_XYZ",
                    "name": "search",
                    "input": {},
                },
            )
        )
        handler.handle_event(
            self._make_event(
                "content_block_delta",
                index=1,
                delta={
                    "type": "input_json_delta",
                    "partial_json": '{"q": "test"}',
                },
            )
        )
        handler.handle_event(
            self._make_event("content_block_stop", index=1)
        )

        handler.handle_event(
            self._make_event(
                "message_delta",
                delta={"stop_reason": "tool_use"},
                usage={"output_tokens": 30},
            )
        )
        handler.handle_event(self._make_event("message_stop"))

        assert len(state.content_blocks) == 2
        assert state.content_blocks[0].block_type == ContentBlockType.TEXT
        assert state.content_blocks[1].block_type == ContentBlockType.TOOL_USE

    def test_reset_clears_state(self):
        state = StreamState()
        handler = StreamHandler(state)
        handler.handle_event(
            self._make_event(
                "message_start",
                message={
                    "id": "msg_x",
                    "model": "m",
                    "role": "assistant",
                    "content": [],
                    "stop_reason": None,
                    "stop_sequence": None,
                    "usage": {"input_tokens": 1, "output_tokens": 1},
                },
            )
        )
        handler.reset()
        assert handler.state.message_id == ""
        assert handler.state.content_blocks == []


# ============================================================================
# ThinkingHandler Tests
# ============================================================================


class TestThinkingHandlerLifecycle:
    """Tests for the thinking handler session lifecycle."""

    def test_start_thinking_initializes_session(self):
        handler = ThinkingHandler()
        handler.start_thinking(budget_tokens=8000)
        assert handler.session.is_active is True
        assert handler.session.budget_tokens == 8000
        assert handler.session.accumulated_thinking == ""

    def test_negative_budget_raises(self):
        handler = ThinkingHandler()
        with pytest.raises(ThinkingError, match="budget_tokens"):
            handler.start_thinking(budget_tokens=-100)

    def test_zero_budget_allowed(self):
        handler = ThinkingHandler()
        handler.start_thinking(budget_tokens=0)
        assert handler.session.budget_tokens == 0

    def test_process_thinking_delta_accumulates(self):
        handler = ThinkingHandler()
        handler.start_thinking(budget_tokens=4000)
        handler.process_thinking_delta("Step 1: ")
        handler.process_thinking_delta("analyze the problem.")
        assert handler.session.accumulated_thinking == "Step 1: analyze the problem."

    def test_process_thinking_delta_without_start_raises(self):
        handler = ThinkingHandler()
        with pytest.raises(ThinkingError, match="no active thinking session"):
            handler.process_thinking_delta("something")

    def test_finalize_thinking_with_valid_signature(self):
        handler = ThinkingHandler()
        handler.start_thinking(budget_tokens=2000)
        handler.process_thinking_delta("My reasoning...")
        result = handler.finalize_thinking("sig_abc123")
        assert result is True
        assert handler.session.is_complete is True
        assert handler.session.signature == "sig_abc123"

    def test_finalize_thinking_with_empty_signature(self):
        handler = ThinkingHandler()
        handler.start_thinking(budget_tokens=2000)
        handler.process_thinking_delta("reasoning")
        result = handler.finalize_thinking("")
        assert result is False

    def test_finalize_thinking_without_start_raises(self):
        handler = ThinkingHandler()
        with pytest.raises(ThinkingError, match="no active thinking session"):
            handler.finalize_thinking("sig")

    def test_build_assistant_block(self):
        handler = ThinkingHandler()
        handler.start_thinking(budget_tokens=5000)
        handler.process_thinking_delta("Think about X")
        handler.finalize_thinking("sig_valid")

        block = handler.build_assistant_block()
        assert block["type"] == "thinking"
        assert block["thinking"] == "Think about X"
        assert block["signature"] == "sig_valid"

    def test_build_assistant_block_before_finalize_raises(self):
        handler = ThinkingHandler()
        handler.start_thinking(budget_tokens=1000)
        with pytest.raises(ThinkingError, match="not yet finalized"):
            handler.build_assistant_block()

    def test_build_redacted_thinking_block(self):
        handler = ThinkingHandler()
        block = handler.build_redacted_thinking_block("encrypted_data_here")
        assert block["type"] == "redacted_thinking"
        assert block["data"] == "encrypted_data_here"


class TestThinkingHandlerSignature:
    """Tests for signature integrity validation."""

    def test_verify_signature_valid_base64(self):
        import base64

        handler = ThinkingHandler()
        # Create a valid base64-looking signature
        sig = base64.b64encode(b"test signature data 12345").decode()
        result = handler.verify_signature_integrity("thinking text", sig)
        assert result is True

    def test_verify_signature_empty(self):
        handler = ThinkingHandler()
        result = handler.verify_signature_integrity("text", "")
        assert result is False

    def test_verify_signature_empty_thinking(self):
        handler = ThinkingHandler()
        import base64
        sig = base64.b64encode(b"data").decode()
        result = handler.verify_signature_integrity("", sig)
        assert result is False

    def test_verify_signature_whitespace_thinking(self):
        handler = ThinkingHandler()
        import base64
        sig = base64.b64encode(b"data").decode()
        result = handler.verify_signature_integrity("   ", sig)
        assert result is False

    def test_verify_signature_invalid_chars(self):
        handler = ThinkingHandler()
        result = handler.verify_signature_integrity("text", "!!!invalid!!!")
        assert result is False

    def test_context_hash_produces_sha256(self):
        handler = ThinkingHandler()
        handler.start_thinking(budget_tokens=1000)
        handler.process_thinking_delta("test content")
        h = handler.compute_context_hash()
        assert len(h) == 64  # SHA-256 hex digest
        assert all(c in "0123456789abcdef" for c in h)

    def test_context_hash_deterministic(self):
        handler1 = ThinkingHandler()
        handler1.start_thinking(budget_tokens=1000)
        handler1.process_thinking_delta("same content")

        handler2 = ThinkingHandler()
        handler2.start_thinking(budget_tokens=1000)
        handler2.process_thinking_delta("same content")

        assert handler1.compute_context_hash() == handler2.compute_context_hash()

    def test_reset_clears_session(self):
        handler = ThinkingHandler()
        handler.start_thinking(budget_tokens=5000)
        handler.process_thinking_delta("data")
        handler.reset()

        assert handler.session.is_active is False
        assert handler.session.accumulated_thinking == ""
        assert handler.session.budget_tokens == 0


# ============================================================================
# Integration Tests: SSEParser + StreamHandler + ThinkingHandler
# ============================================================================


class TestIntegration:
    """End-to-end tests combining all three components."""

    def test_stream_with_thinking_full_pipeline(self):
        """Simulate a full streaming response with thinking."""
        parser = SSEParser()
        state = StreamState()
        stream_handler = StreamHandler(state)
        think_handler = ThinkingHandler()

        # Simulate the raw SSE bytes for a thinking + text response
        raw_events = [
            # message_start
            'event: message_start\ndata: {"type": "message_start", "message": {"id": "msg_int", "type": "message", "role": "assistant", "content": [], "model": "claude-sonnet-4-5-20250929", "stop_reason": null, "stop_sequence": null, "usage": {"input_tokens": 50, "output_tokens": 1}}}\n\n',
            # thinking block start
            'event: content_block_start\ndata: {"type": "content_block_start", "index": 0, "content_block": {"type": "thinking", "thinking": ""}}\n\n',
            # thinking delta
            'event: content_block_delta\ndata: {"type": "content_block_delta", "index": 0, "delta": {"type": "thinking_delta", "thinking": "Let me solve this step by step.\\\\n\\\\n"}}\n\n',
            # more thinking
            'event: content_block_delta\ndata: {"type": "content_block_delta", "index": 0, "delta": {"type": "thinking_delta", "thinking": "First, consider the problem constraints."}}\n\n',
            # signature delta
            'event: content_block_delta\ndata: {"type": "content_block_delta", "index": 0, "delta": {"type": "signature_delta", "signature": "dGVzdCBzaWduYXR1cmUgZGF0YQ=="}}\n\n',
            # thinking block stop
            'event: content_block_stop\ndata: {"type": "content_block_stop", "index": 0}\n\n',
            # text block start
            'event: content_block_start\ndata: {"type": "content_block_start", "index": 1, "content_block": {"type": "text", "text": ""}}\n\n',
            # text delta
            'event: content_block_delta\ndata: {"type": "content_block_delta", "index": 1, "delta": {"type": "text_delta", "text": "Based on my analysis, "}}\n\n',
            # text delta 2
            'event: content_block_delta\ndata: {"type": "content_block_delta", "index": 1, "delta": {"type": "text_delta", "text": "the answer is 42."}}\n\n',
            # text block stop
            'event: content_block_stop\ndata: {"type": "content_block_stop", "index": 1}\n\n',
            # message_delta
            'event: message_delta\ndata: {"type": "message_delta", "delta": {"stop_reason": "end_turn", "stop_sequence": null}, "usage": {"output_tokens": 250}}\n\n',
            # message_stop
            'event: message_stop\ndata: {"type": "message_stop"}\n\n',
        ]

        # Feed all events through SSE parser
        all_parsed: list = []
        for raw in raw_events:
            parsed = parser.feed(raw.encode("utf-8"))
            all_parsed.extend(parsed)

        # Process all events through StreamHandler
        accumulated_text = ""
        thinking_started = False

        for event in all_parsed:
            text = stream_handler.handle_event(event.data)

            # Track thinking state
            data = event.data
            if data.get("type") == "content_block_delta":
                delta = data.get("delta", {})
                if delta.get("type") == "thinking_delta":
                    if not thinking_started:
                        think_handler.start_thinking(budget_tokens=8000)
                        thinking_started = True
                    think_handler.process_thinking_delta(delta["thinking"])
                elif delta.get("type") == "signature_delta":
                    think_handler.finalize_thinking(delta["signature"])

            if text:
                accumulated_text += text

        # Verify text accumulation
        assert accumulated_text == "Based on my analysis, the answer is 42."

        # Verify thinking accumulation
        assert "step by step" in think_handler.session.accumulated_thinking.lower()
        assert think_handler.session.is_complete is True
        assert think_handler.session.signature == "dGVzdCBzaWduYXR1cmUgZGF0YQ=="

        # Verify final message
        msg = stream_handler.get_final_message()
        assert msg["stop_reason"] == "end_turn"
        assert len(msg["content"]) == 2
        assert msg["content"][0]["type"] == "thinking"
        assert msg["content"][1]["type"] == "text"

        # Build assistant message for next turn
        assistant_block = think_handler.build_assistant_block()
        assert assistant_block["signature"] == "dGVzdCBzaWduYXR1cmUgZGF0YQ=="

    def test_stream_interrupted_by_error(self):
        """Test that error events are correctly handled in the pipeline."""
        parser = SSEParser()
        state = StreamState()
        handler = StreamHandler(state)

        raw = (
            'event: message_start\ndata: {"type": "message_start", "message": {"id": "err_test", "type": "message", "role": "assistant", "content": [], "model": "claude-3", "stop_reason": null, "stop_sequence": null, "usage": {"input_tokens": 5, "output_tokens": 1}}}\n\n'
            'event: content_block_delta\ndata: {"type": "content_block_delta", "index": 0, "delta": {"type": "text_delta", "text": "Partial"}}\n\n'
            'event: error\ndata: {"type": "error", "error": {"type": "overloaded_error", "message": "Service overloaded"}}\n\n'
        )

        parsed = parser.feed(raw.encode("utf-8"))
        for event in parsed:
            handler.handle_event(event.data)

        assert state.finished is True
        assert state.error is not None
        assert state.error["type"] == "overloaded_error"
        # Partial text should still be available
        assert "Partial" in state.text
