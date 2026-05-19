"""
Tests for message_builder.py — Messages API request construction.

Covers:
- ContentBlock subclasses (TextBlock, ImageBlock, ToolUseBlock, ToolResultBlock)
- Message class (user/assistant, plain-string vs array content)
- MessageRequest validation and serialization
- Edge cases: empty strings, invalid params, multi-turn conversations
"""

import base64
import json
import tempfile
from pathlib import Path

import pytest

from message_builder import (
    CacheTTL,
    ContentBlock,
    ImageBlock,
    Message,
    MessageRequest,
    Role,
    ServiceTier,
    StopReason,
    SUPPORTED_IMAGE_MEDIA_TYPES,
    TextBlock,
    ToolResultBlock,
    ToolUseBlock,
    MESSAGES_ENDPOINT,
    multimodal_request,
    simple_text_request,
)


# =================================================================
# TextBlock
# =================================================================

class TestTextBlock:
    def test_basic_serialization(self):
        block = TextBlock(text="Hello, world")
        assert block.to_dict() == {"type": "text", "text": "Hello, world"}

    def test_with_cache_control(self):
        block = TextBlock(text="Repeat after me", cache_control={"type": "ephemeral"})
        d = block.to_dict()
        assert d["type"] == "text"
        assert d["text"] == "Repeat after me"
        assert d["cache_control"] == {"type": "ephemeral"}

    def test_with_citations(self):
        citations = [{"type": "char_location", "cited_text": "...", "document_index": 0,
                       "document_title": "Test", "start_char_index": 0, "end_char_index": 3}]
        block = TextBlock(text="Citing something", citations=citations)
        d = block.to_dict()
        assert d["citations"] == citations

    def test_empty_text_allowed(self):
        """Empty text is technically allowed by the API (though unusual)."""
        block = TextBlock(text="")
        assert block.to_dict() == {"type": "text", "text": ""}

    def test_deserialization(self):
        d = {"type": "text", "text": "Deserialized"}
        block = ContentBlock.from_dict(d)
        assert isinstance(block, TextBlock)
        assert block.text == "Deserialized"


# =================================================================
# ImageBlock
# =================================================================

class TestImageBlock:
    _ONE_PIXEL_PNG_B64 = (
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk"
        "+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="
    )

    def test_from_base64_png(self):
        block = ImageBlock.from_base64(self._ONE_PIXEL_PNG_B64, media_type="image/png")
        d = block.to_dict()
        assert d["type"] == "image"
        assert d["source"]["type"] == "base64"
        assert d["source"]["media_type"] == "image/png"
        assert d["source"]["data"] == self._ONE_PIXEL_PNG_B64

    def test_from_base64_strips_data_uri_prefix(self):
        data_uri = f"data:image/png;base64,{self._ONE_PIXEL_PNG_B64}"
        block = ImageBlock.from_base64(data_uri, media_type="image/png")
        assert block.source["data"] == self._ONE_PIXEL_PNG_B64

    def test_from_base64_rejects_unsupported_media_type(self):
        with pytest.raises(ValueError, match="Unsupported media_type"):
            ImageBlock.from_base64(self._ONE_PIXEL_PNG_B64, media_type="image/bmp")

    def test_from_base64_rejects_empty_data(self):
        with pytest.raises(ValueError, match="empty"):
            ImageBlock.from_base64("", media_type="image/png")

    def test_from_base64_rejects_oversized_data(self):
        # Create a string that represents > 5MB of decoded data
        big = "A" * (7 * 1024 * 1024)  # ~7MB in base64 chars
        with pytest.raises(ValueError, match="exceeds"):
            ImageBlock.from_base64(big, media_type="image/jpeg")

    def test_from_url(self):
        block = ImageBlock.from_url("https://example.com/photo.jpg")
        d = block.to_dict()
        assert d["source"] == {"type": "url", "url": "https://example.com/photo.jpg"}

    def test_from_url_rejects_non_http(self):
        with pytest.raises(ValueError, match="must start with"):
            ImageBlock.from_url("ftp://files.example.com/img.png")

    def test_from_url_allows_http(self):
        block = ImageBlock.from_url("http://example.com/photo.jpg")
        assert block.source["url"] == "http://example.com/photo.jpg"

    def test_from_file_png(self):
        # Create a minimal valid PNG file
        raw_png = base64.b64decode(self._ONE_PIXEL_PNG_B64)
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
            f.write(raw_png)
            tmp_path = f.name

        try:
            block = ImageBlock.from_file(tmp_path)
            assert block.source["type"] == "base64"
            assert block.source["media_type"] == "image/png"
        finally:
            Path(tmp_path).unlink()

    def test_from_file_not_found(self):
        with pytest.raises(FileNotFoundError):
            ImageBlock.from_file("/nonexistent/path/image.png")

    def test_from_file_unsupported_extension(self):
        with tempfile.NamedTemporaryFile(suffix=".bmp", delete=False) as f:
            f.write(b"fake bitmap content")
            tmp_path = f.name

        try:
            with pytest.raises(ValueError, match="Cannot determine MIME type"):
                ImageBlock.from_file(tmp_path)
        finally:
            Path(tmp_path).unlink()

    def test_from_file_jpeg_extension(self):
        # Minimal JPEG bytes (actually not a valid JPEG, but we test the path)
        # We use .jpg extension which should map to image/jpeg
        with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as f:
            f.write(b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00")
            tmp_path = f.name

        try:
            block = ImageBlock.from_file(tmp_path)
            assert block.source["media_type"] == "image/jpeg"
        finally:
            Path(tmp_path).unlink()

    def test_from_file_oversized(self):
        # Create a file > 5MB
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
            f.seek(6 * 1024 * 1024)
            f.write(b"\x00")
            tmp_path = f.name

        try:
            with pytest.raises(ValueError, match="exceeds"):
                ImageBlock.from_file(tmp_path)
        finally:
            Path(tmp_path).unlink()

    def test_deserialize_base64_image(self):
        d = {
            "type": "image",
            "source": {
                "type": "base64",
                "media_type": "image/png",
                "data": self._ONE_PIXEL_PNG_B64,
            },
        }
        block = ContentBlock.from_dict(d)
        assert isinstance(block, ImageBlock)
        assert block.source["data"] == self._ONE_PIXEL_PNG_B64

    def test_deserialize_url_image(self):
        d = {"type": "image", "source": {"type": "url", "url": "https://example.com/img.png"}}
        block = ContentBlock.from_dict(d)
        assert isinstance(block, ImageBlock)
        assert block.source["url"] == "https://example.com/img.png"

    def test_all_supported_formats(self):
        """Verify all four supported media types work."""
        for mt in SUPPORTED_IMAGE_MEDIA_TYPES:
            block = ImageBlock.from_base64(self._ONE_PIXEL_PNG_B64, media_type=mt)
            assert block.source["media_type"] == mt

    def test_cache_control_on_image(self):
        block = ImageBlock.from_url("https://example.com/img.png")
        block.cache_control = {"type": "ephemeral"}
        d = block.to_dict()
        assert d["cache_control"] == {"type": "ephemeral"}


# =================================================================
# ToolUseBlock
# =================================================================

class TestToolUseBlock:
    def test_basic_serialization(self):
        block = ToolUseBlock(
            tool_id="toolu_01ABC123",
            name="get_weather",
            input={"location": "San Francisco, CA"},
        )
        d = block.to_dict()
        assert d == {
            "type": "tool_use",
            "id": "toolu_01ABC123",
            "name": "get_weather",
            "input": {"location": "San Francisco, CA"},
        }

    def test_empty_input(self):
        block = ToolUseBlock(tool_id="toolu_X", name="ping")
        assert block.to_dict()["input"] == {}

    def test_deserialization(self):
        d = {
            "type": "tool_use",
            "id": "toolu_XYZ",
            "name": "search",
            "input": {"q": "hello"},
        }
        block = ContentBlock.from_dict(d)
        assert isinstance(block, ToolUseBlock)
        assert block.tool_id == "toolu_XYZ"
        assert block.name == "search"
        assert block.input == {"q": "hello"}


# =================================================================
# ToolResultBlock
# =================================================================

class TestToolResultBlock:
    def test_string_content(self):
        block = ToolResultBlock(tool_use_id="toolu_X", content="42 degrees")
        d = block.to_dict()
        assert d["tool_use_id"] == "toolu_X"
        assert d["content"] == "42 degrees"
        assert "is_error" not in d

    def test_array_content(self):
        block = ToolResultBlock(
            tool_use_id="toolu_X",
            content=[{"type": "text", "text": "Image generated"}],
        )
        d = block.to_dict()
        assert isinstance(d["content"], list)

    def test_is_error_true(self):
        block = ToolResultBlock(tool_use_id="toolu_X", content="Timeout", is_error=True)
        assert block.to_dict()["is_error"] is True

    def test_is_error_false(self):
        block = ToolResultBlock(tool_use_id="toolu_X", content="OK", is_error=False)
        assert block.to_dict()["is_error"] is False

    def test_from_success(self):
        block = ToolResultBlock.from_success("toolu_X", "Done")
        assert block.is_error is False
        assert block.content == "Done"

    def test_from_error(self):
        block = ToolResultBlock.from_error("toolu_X", "failed")
        assert block.is_error is True
        assert block.content == "failed"

    def test_cache_control(self):
        block = ToolResultBlock(
            tool_use_id="toolu_X",
            content="OK",
            cache_control={"type": "ephemeral"},
        )
        assert block.to_dict()["cache_control"] == {"type": "ephemeral"}

    def test_deserialization(self):
        d = {"type": "tool_result", "tool_use_id": "toolu_X", "content": "result"}
        block = ContentBlock.from_dict(d)
        assert isinstance(block, ToolResultBlock)
        assert block.tool_use_id == "toolu_X"


# =================================================================
# ContentBlock.from_dict - unknown type
# =================================================================

class TestContentBlockDeserialization:
    def test_unknown_type_raises(self):
        with pytest.raises(ValueError, match="Unknown content block type"):
            ContentBlock.from_dict({"type": "unknown_block", "data": "x"})


# =================================================================
# Message
# =================================================================

class TestMessage:
    def test_user_message_string_content(self):
        msg = Message.user("Hello")
        assert msg.to_dict() == {"role": "user", "content": "Hello"}

    def test_assistant_message_string_content(self):
        msg = Message.assistant("I am Claude.")
        assert msg.to_dict() == {"role": "assistant", "content": "I am Claude."}

    def test_user_message_array_content(self):
        blocks = [TextBlock(text="Hi"), TextBlock(text="there")]
        msg = Message.user(blocks)
        d = msg.to_dict()
        assert d["role"] == "user"
        assert isinstance(d["content"], list)
        assert len(d["content"]) == 2

    def test_empty_string_rejected(self):
        with pytest.raises(ValueError, match="cannot be an empty string"):
            Message.user("")

    def test_invalid_role_rejected(self):
        with pytest.raises(ValueError, match="Invalid role"):
            Message(role="system", content="I am the system")

    def test_role_enum_acceptance(self):
        msg = Message(role=Role.USER, content="test")
        assert msg.role == Role.USER

    def test_user_factory_preserves_role(self):
        msg = Message.user("x")
        assert msg.role == Role.USER

    def test_assistant_factory_preserves_role(self):
        msg = Message.assistant("x")
        assert msg.role == Role.ASSISTANT


# =================================================================
# MessageRequest
# =================================================================

class TestMessageRequest:
    def test_minimal_request(self):
        req = MessageRequest(
            model="claude-sonnet-4-20250514",
            messages=[Message.user("Hi")],
            max_tokens=1024,
        )
        d = req.to_dict()
        assert d["model"] == "claude-sonnet-4-20250514"
        assert d["max_tokens"] == 1024
        assert len(d["messages"]) == 1
        # Optional fields should be absent
        for opt in ("system", "temperature", "top_p", "top_k",
                     "stop_sequences", "tools", "metadata"):
            assert opt not in d

    def test_stream_flag(self):
        req = MessageRequest(
            model="claude-sonnet-4-20250514",
            messages=[Message.user("Hi")],
            max_tokens=100,
            stream=True,
        )
        assert req.to_dict()["stream"] is True

    def test_stream_default_false(self):
        req = MessageRequest(
            model="claude-sonnet-4-20250514",
            messages=[Message.user("Hi")],
            max_tokens=100,
        )
        assert "stream" not in req.to_dict()

    def test_full_request_with_all_params(self):
        req = MessageRequest(
            model="claude-opus-4-7",
            messages=[
                Message.user("What's the weather?"),
                Message.assistant([
                    ToolUseBlock(
                        tool_id="toolu_01A",
                        name="get_weather",
                        input={"city": "Paris"},
                    )
                ]),
                Message.user([
                    ToolResultBlock.from_success("toolu_01A", "Sunny, 22C")
                ]),
            ],
            max_tokens=2048,
            system="You are a helpful weather assistant.",
            temperature=0.7,
            top_p=0.9,
            top_k=40,
            stop_sequences=["\n\n---"],
            metadata={"user_id": "usr_abc123"},
            tools=[
                {
                    "name": "get_weather",
                    "description": "Get the current weather for a city.",
                    "input_schema": {
                        "type": "object",
                        "properties": {
                            "city": {"type": "string", "description": "City name"}
                        },
                        "required": ["city"],
                    },
                }
            ],
        )
        d = req.to_dict()
        assert d["model"] == "claude-opus-4-7"
        assert d["max_tokens"] == 2048
        assert d["system"] == "You are a helpful weather assistant."
        assert d["temperature"] == 0.7
        assert d["top_p"] == 0.9
        assert d["top_k"] == 40
        assert d["stop_sequences"] == ["\n\n---"]
        assert d["metadata"] == {"user_id": "usr_abc123"}
        assert len(d["messages"]) == 3
        # Third message should have tool_result content
        assert d["messages"][2]["content"][0]["type"] == "tool_result"

    def test_system_as_text_blocks(self):
        """System prompt can be an array of text blocks."""
        req = MessageRequest(
            model="claude-sonnet-4-20250514",
            messages=[Message.user("Hi")],
            max_tokens=100,
            system=[{"type": "text", "text": "Be concise."}],
        )
        assert req.to_dict()["system"] == [{"type": "text", "text": "Be concise."}]

    def test_service_tier_auto(self):
        req = MessageRequest(
            model="claude-sonnet-4-20250514",
            messages=[Message.user("Hi")],
            max_tokens=100,
            service_tier=ServiceTier.AUTO,
        )
        assert req.to_dict()["service_tier"] == "auto"

    def test_service_tier_standard_only(self):
        req = MessageRequest(
            model="claude-sonnet-4-20250514",
            messages=[Message.user("Hi")],
            max_tokens=100,
            service_tier="standard_only",
        )
        assert req.to_dict()["service_tier"] == "standard_only"

    def test_service_tier_invalid_string(self):
        with pytest.raises(ValueError, match="Invalid service_tier"):
            MessageRequest(
                model="claude-sonnet-4-20250514",
                messages=[Message.user("Hi")],
                max_tokens=100,
                service_tier="premium",
            )

    def test_thinking_enabled(self):
        req = MessageRequest(
            model="claude-sonnet-4-20250514",
            messages=[Message.user("Complex problem")],
            max_tokens=4096,
            thinking={"type": "enabled", "budget_tokens": 1024},
        )
        assert req.to_dict()["thinking"] == {"type": "enabled", "budget_tokens": 1024}

    def test_tool_choice(self):
        req = MessageRequest(
            model="claude-sonnet-4-20250514",
            messages=[Message.user("Hi")],
            max_tokens=100,
            tools=[{"name": "search", "description": "Search", "input_schema": {"type": "object"}}],
            tool_choice={"type": "auto"},
        )
        assert req.to_dict()["tool_choice"] == {"type": "auto"}

    # --- Validation tests ---

    def test_empty_model_rejected(self):
        with pytest.raises(ValueError, match="model must be a non-empty string"):
            MessageRequest(model="", messages=[Message.user("Hi")], max_tokens=100)

    def test_empty_messages_rejected(self):
        with pytest.raises(ValueError, match="messages list cannot be empty"):
            MessageRequest(model="claude-sonnet-4-20250514", messages=[], max_tokens=100)

    def test_max_tokens_zero_rejected(self):
        with pytest.raises(ValueError, match="max_tokens must be >= 1"):
            MessageRequest(
                model="claude-sonnet-4-20250514",
                messages=[Message.user("Hi")],
                max_tokens=0,
            )

    def test_max_tokens_negative_rejected(self):
        with pytest.raises(ValueError, match="max_tokens must be >= 1"):
            MessageRequest(
                model="claude-sonnet-4-20250514",
                messages=[Message.user("Hi")],
                max_tokens=-1,
            )

    def test_temperature_above_range(self):
        with pytest.raises(ValueError, match="temperature must be in"):
            MessageRequest(
                model="claude-sonnet-4-20250514",
                messages=[Message.user("Hi")],
                max_tokens=100,
                temperature=1.5,
            )

    def test_temperature_below_range(self):
        with pytest.raises(ValueError, match="temperature must be in"):
            MessageRequest(
                model="claude-sonnet-4-20250514",
                messages=[Message.user("Hi")],
                max_tokens=100,
                temperature=-0.1,
            )

    def test_top_p_out_of_range(self):
        with pytest.raises(ValueError, match="top_p must be in"):
            MessageRequest(
                model="claude-sonnet-4-20250514",
                messages=[Message.user("Hi")],
                max_tokens=100,
                top_p=2.0,
            )

    def test_top_k_negative(self):
        with pytest.raises(ValueError, match="top_k must be >= 0"):
            MessageRequest(
                model="claude-sonnet-4-20250514",
                messages=[Message.user("Hi")],
                max_tokens=100,
                top_k=-5,
            )

    # --- to_json ---

    def test_to_json_compact(self):
        req = MessageRequest(
            model="claude-sonnet-4-20250514",
            messages=[Message.user("Hello")],
            max_tokens=100,
        )
        raw = req.to_json()
        parsed = json.loads(raw)
        assert parsed["model"] == "claude-sonnet-4-20250514"

    def test_to_json_pretty(self):
        req = MessageRequest(
            model="claude-sonnet-4-20250514",
            messages=[Message.user("Hello")],
            max_tokens=100,
        )
        raw = req.to_json(indent=2)
        assert "\n" in raw


# =================================================================
# Convenience constructors
# =================================================================

class TestConvenienceConstructors:
    def test_simple_text_request(self):
        req = simple_text_request("Tell me a joke")
        d = req.to_dict()
        assert d["model"] == "claude-sonnet-4-20250514"
        assert d["messages"][0]["content"] == "Tell me a joke"
        assert d["max_tokens"] == 1024

    def test_simple_text_request_with_custom_model(self):
        req = simple_text_request("Hi", model="claude-opus-4-7")
        assert req.to_dict()["model"] == "claude-opus-4-7"

    def test_simple_text_request_with_system(self):
        req = simple_text_request("Hi", system="You are helpful.")
        assert req.to_dict()["system"] == "You are helpful."

    def test_multimodal_request(self):
        image = ImageBlock.from_url("https://example.com/chart.png")
        req = multimodal_request("Describe this chart:", images=[image])
        d = req.to_dict()
        content = d["messages"][0]["content"]
        assert len(content) == 2
        assert content[0]["type"] == "text"
        assert content[1]["type"] == "image"

    def test_multimodal_request_multiple_images(self):
        images = [
            ImageBlock.from_url("https://example.com/a.jpg"),
            ImageBlock.from_url("https://example.com/b.jpg"),
        ]
        req = multimodal_request("Compare:", images=images)
        assert len(req.to_dict()["messages"][0]["content"]) == 3


# =================================================================
# Endpoint constant
# =================================================================

def test_endpoint_constant():
    assert MESSAGES_ENDPOINT == "https://api.anthropic.com/v1/messages"


# =================================================================
# Enum integrity
# =================================================================

class TestEnums:
    def test_role_values(self):
        assert Role.USER.value == "user"
        assert Role.ASSISTANT.value == "assistant"

    def test_stop_reason_values(self):
        assert StopReason.END_TURN.value == "end_turn"
        assert StopReason.TOOL_USE.value == "tool_use"

    def test_service_tier_values(self):
        assert ServiceTier.AUTO.value == "auto"
        assert ServiceTier.STANDARD_ONLY.value == "standard_only"

    def test_cache_ttl_values(self):
        assert CacheTTL.FIVE_MINUTES.value == "5m"
        assert CacheTTL.ONE_HOUR.value == "1h"
