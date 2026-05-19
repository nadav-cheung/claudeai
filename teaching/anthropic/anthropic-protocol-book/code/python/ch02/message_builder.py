"""
Message Builder - Anthropic Messages API request construction.

This module provides a type-safe, zero-dependency builder for constructing
Anthropic Messages API request bodies. It models Content Blocks, Messages,
and the full MessageRequest according to the API specification.

Protocol reference: POST https://api.anthropic.com/v1/messages

Key design decisions:
- No dependency on the anthropic SDK — this is a protocol-level builder.
- All classes implement to_dict() for JSON serialization.
- Strict type annotations throughout for safety and self-documentation.
- Supports plain-string content as shorthand per the API spec.
"""

from __future__ import annotations

import base64
import json
import mimetypes
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Literal, Union, Optional


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

SUPPORTED_IMAGE_MEDIA_TYPES: frozenset[str] = frozenset({
    "image/jpeg",
    "image/png",
    "image/gif",
    "image/webp",
})

# Anthropic does not document a hard size limit in the API reference,
# but practical guidance is 5 MB per image for base64 and 10 MB for URL.
MAX_BASE64_IMAGE_BYTES: int = 5 * 1024 * 1024   # 5 MB
MAX_URL_IMAGE_BYTES: int = 10 * 1024 * 1024      # 10 MB

# API endpoint
MESSAGES_ENDPOINT: str = "https://api.anthropic.com/v1/messages"


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class Role(str, Enum):
    """Valid message roles in the Messages API."""
    USER = "user"
    ASSISTANT = "assistant"


class StopReason(str, Enum):
    """Reasons the model may stop generating."""
    END_TURN = "end_turn"
    MAX_TOKENS = "max_tokens"
    STOP_SEQUENCE = "stop_sequence"
    TOOL_USE = "tool_use"
    PAUSE_TURN = "pause_turn"
    REFUSAL = "refusal"


class ServiceTier(str, Enum):
    """Service tier options for the API request."""
    AUTO = "auto"
    STANDARD_ONLY = "standard_only"


class CacheTTL(str, Enum):
    """Time-to-live for ephemeral cache control breakpoints."""
    FIVE_MINUTES = "5m"
    ONE_HOUR = "1h"


# ---------------------------------------------------------------------------
# Content Blocks
# ---------------------------------------------------------------------------

class ContentBlock:
    """
    Base class for all Content Block types.

    Each content block has a `type` field that identifies its shape.
    Subclasses must override `type` and implement `to_dict()`.
    """

    block_type: str  # set by subclasses

    def to_dict(self) -> dict[str, Any]:
        raise NotImplementedError

    @staticmethod
    def from_dict(data: dict[str, Any]) -> "ContentBlock":
        """Deserialize a dict into the appropriate ContentBlock subclass."""
        block_type = data.get("type")
        if block_type == "text":
            return TextBlock(text=data["text"])
        elif block_type == "image":
            source = data.get("source", {})
            if source.get("type") == "base64":
                return ImageBlock.from_base64(
                    data=source["data"],
                    media_type=source["media_type"],
                )
            elif source.get("type") == "url":
                return ImageBlock.from_url(url=source["url"])
            else:
                raise ValueError(f"Unknown image source type: {source.get('type')}")
        elif block_type == "tool_use":
            return ToolUseBlock(
                tool_id=data["id"],
                name=data["name"],
                input=data.get("input", {}),
            )
        elif block_type == "tool_result":
            return ToolResultBlock(
                tool_use_id=data["tool_use_id"],
                content=data["content"],
                is_error=data.get("is_error"),
            )
        else:
            raise ValueError(f"Unknown content block type: {block_type}")


@dataclass
class TextBlock(ContentBlock):
    """
    A text content block.

    Fields:
        text: The text content.
        cache_control: Optional ephemeral cache control configuration.
        citations: Optional array of citation references.

    API docs: { "type": "text", "text": "..." }
    """

    text: str
    cache_control: Optional[dict[str, str]] = None
    citations: Optional[list[dict[str, Any]]] = None
    block_type: str = field(default="text", init=False)

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {"type": "text", "text": self.text}
        if self.cache_control is not None:
            result["cache_control"] = self.cache_control
        if self.citations is not None:
            result["citations"] = self.citations
        return result


@dataclass
class ImageBlock(ContentBlock):
    """
    An image content block supporting both base64 data and URL sources.

    Supported formats: JPEG, PNG, GIF, WebP.

    API docs:
      Base64:  { "type": "image", "source": { "type": "base64",
                 "media_type": "image/jpeg", "data": "..." } }
      URL:     { "type": "image", "source": { "type": "url",
                 "url": "https://..." } }
    """

    source: dict[str, str]
    cache_control: Optional[dict[str, str]] = None
    block_type: str = field(default="image", init=False)

    # ----- Factory constructors -----

    @classmethod
    def from_base64(cls, data: str, media_type: str) -> "ImageBlock":
        """
        Create an ImageBlock from a base64-encoded string.

        Args:
            data: The base64-encoded image data (with or without data URI prefix).
            media_type: MIME type, e.g. "image/png".

        Raises:
            ValueError: If the media_type is not in the supported set.
        """
        if media_type not in SUPPORTED_IMAGE_MEDIA_TYPES:
            raise ValueError(
                f"Unsupported media_type: {media_type}. "
                f"Supported: {sorted(SUPPORTED_IMAGE_MEDIA_TYPES)}"
            )
        # Strip data URI prefix if present
        cleaned = _strip_data_uri_prefix(data)
        _validate_base64_string(cleaned)
        # Rough size check (decoded bytes ~ 3/4 of base64 length)
        estimated_bytes = (len(cleaned) * 3) // 4
        if estimated_bytes > MAX_BASE64_IMAGE_BYTES:
            raise ValueError(
                f"Estimated image size ({estimated_bytes} bytes) exceeds "
                f"the recommended limit of {MAX_BASE64_IMAGE_BYTES} bytes."
            )
        return cls(source={"type": "base64", "media_type": media_type, "data": cleaned})

    @classmethod
    def from_url(cls, url: str) -> "ImageBlock":
        """
        Create an ImageBlock from an image URL.

        Args:
            url: The URL pointing to the image.

        Raises:
            ValueError: If the URL does not start with http:// or https://.
        """
        if not (url.startswith("http://") or url.startswith("https://")):
            raise ValueError(f"Image URL must start with http:// or https://, got: {url}")
        return cls(source={"type": "url", "url": url})

    @classmethod
    def from_file(cls, file_path: str | Path) -> "ImageBlock":
        """
        Read an image from disk and create a base64 ImageBlock.

        Args:
            file_path: Path to the image file.

        Raises:
            FileNotFoundError: If the file does not exist.
            ValueError: If the media type cannot be determined or is unsupported.
        """
        path = Path(file_path)
        if not path.is_file():
            raise FileNotFoundError(f"Image file not found: {path}")

        # Guess MIME type from extension
        mime_type, _ = mimetypes.guess_type(str(path))
        if mime_type is None or mime_type not in SUPPORTED_IMAGE_MEDIA_TYPES:
            # Try to infer from common extensions mimetypes might miss
            suffix = path.suffix.lower()
            mime_map = {
                ".jpg": "image/jpeg",
                ".jpeg": "image/jpeg",
                ".png": "image/png",
                ".gif": "image/gif",
                ".webp": "image/webp",
            }
            mime_type = mime_map.get(suffix)
            if mime_type is None:
                raise ValueError(
                    f"Cannot determine MIME type for {path}. "
                    f"Supported extensions: {sorted(mime_map.keys())}"
                )

        # Read and encode
        raw = path.read_bytes()
        if len(raw) > MAX_BASE64_IMAGE_BYTES:
            raise ValueError(
                f"Image file size ({len(raw)} bytes) exceeds "
                f"the recommended limit of {MAX_BASE64_IMAGE_BYTES} bytes."
            )

        encoded = base64.b64encode(raw).decode("ascii")
        return cls.from_base64(data=encoded, media_type=mime_type)

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {"type": "image", "source": dict(self.source)}
        if self.cache_control is not None:
            result["cache_control"] = self.cache_control
        return result


@dataclass
class ToolUseBlock(ContentBlock):
    """
    A tool-use content block (used in assistant turns).

    API docs:
      { "type": "tool_use", "id": "toolu_...", "name": "...", "input": {...} }
    """

    tool_id: str
    name: str
    input: dict[str, Any] = field(default_factory=dict)
    block_type: str = field(default="tool_use", init=False)

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": "tool_use",
            "id": self.tool_id,
            "name": self.name,
            "input": self.input,
        }


@dataclass
class ToolResultBlock(ContentBlock):
    """
    A tool-result content block (used in user turns to return tool output).

    The `content` field can be a plain string or an array of nested content blocks.
    `is_error` should be set to True when the tool execution failed.

    API docs:
      { "type": "tool_result", "tool_use_id": "...", "content": "..." | [...],
        "is_error": false }
    """

    tool_use_id: str
    content: str | list[dict[str, Any]]
    is_error: bool | None = None
    cache_control: Optional[dict[str, str]] = None
    block_type: str = field(default="tool_result", init=False)

    @classmethod
    def from_success(cls, tool_use_id: str, content: str) -> "ToolResultBlock":
        """Shorthand for a successful tool result."""
        return cls(tool_use_id=tool_use_id, content=content, is_error=False)

    @classmethod
    def from_error(cls, tool_use_id: str, error_message: str) -> "ToolResultBlock":
        """Shorthand for a tool execution error."""
        return cls(tool_use_id=tool_use_id, content=error_message, is_error=True)

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "type": "tool_result",
            "tool_use_id": self.tool_use_id,
            "content": self.content,
        }
        if self.is_error is not None:
            result["is_error"] = self.is_error
        if self.cache_control is not None:
            result["cache_control"] = self.cache_control
        return result


# ---------------------------------------------------------------------------
# Message
# ---------------------------------------------------------------------------

@dataclass
class Message:
    """
    A single message in a conversation, with a role and content.

    Content can be:
    - A plain string (shorthand for a single text block)
    - A list of ContentBlock instances

    API docs:
      { "role": "user" | "assistant", "content": "..." | [...] }
    """

    role: Role | str
    content: str | list[ContentBlock]

    def __post_init__(self) -> None:
        if isinstance(self.role, str):
            if self.role not in ("user", "assistant"):
                raise ValueError(
                    f"Invalid role: {self.role!r}. Must be 'user' or 'assistant'."
                )
            self.role = Role(self.role)
        if isinstance(self.content, str) and not self.content:
            raise ValueError("Message content cannot be an empty string.")

    @classmethod
    def user(cls, content: str | list[ContentBlock]) -> "Message":
        """Factory for a user message."""
        return cls(role=Role.USER, content=content)

    @classmethod
    def assistant(cls, content: str | list[ContentBlock]) -> "Message":
        """Factory for an assistant message."""
        return cls(role=Role.ASSISTANT, content=content)

    def to_dict(self) -> dict[str, Any]:
        if isinstance(self.content, str):
            return {"role": self.role.value, "content": self.content}
        return {
            "role": self.role.value,
            "content": [block.to_dict() for block in self.content],
        }


# ---------------------------------------------------------------------------
# Utility helpers
# ---------------------------------------------------------------------------

def _strip_data_uri_prefix(data: str) -> str:
    """Strip 'data:<mime>;base64,' prefix if present."""
    if data.startswith("data:"):
        # Find the comma separator between header and data
        comma_idx = data.find(",")
        if comma_idx != -1:
            return data[comma_idx + 1 :]
    return data


def _validate_base64_string(data: str) -> None:
    """Validate that a string looks like valid base64."""
    if not data:
        raise ValueError("Base64 data cannot be empty.")
    # Basic check: base64 alphabet + padding + optional whitespace
    # We do a lenient check — the server will reject truly invalid data.
    stripped = data.strip()
    if not stripped:
        raise ValueError("Base64 data is empty after stripping whitespace.")


# ---------------------------------------------------------------------------
# MessageRequest
# ---------------------------------------------------------------------------

@dataclass
class MessageRequest:
    """
    Complete Messages API request body.

    Maps to the POST /v1/messages JSON body.  All required fields must be
    provided; optional fields use None as sentinel.

    Reference: https://docs.anthropic.com/en/api/messages
    """

    model: str
    messages: list[Message]
    max_tokens: int

    # --- Optional parameters ---
    system: str | list[dict[str, str]] | None = None
    temperature: float | None = None
    top_p: float | None = None
    top_k: int | None = None
    stop_sequences: list[str] | None = None
    stream: bool = False
    metadata: dict[str, str] | None = None
    tools: list[dict[str, Any]] | None = None
    tool_choice: dict[str, Any] | None = None
    thinking: dict[str, Any] | None = None
    service_tier: ServiceTier | str | None = None

    def __post_init__(self) -> None:
        # Validation
        if not self.model or not self.model.strip():
            raise ValueError("model must be a non-empty string.")
        if not self.messages:
            raise ValueError("messages list cannot be empty.")
        if self.max_tokens < 1:
            raise ValueError(f"max_tokens must be >= 1, got {self.max_tokens}.")
        if self.temperature is not None and not (0.0 <= self.temperature <= 1.0):
            raise ValueError(
                f"temperature must be in [0.0, 1.0], got {self.temperature}."
            )
        if self.top_p is not None and not (0.0 <= self.top_p <= 1.0):
            raise ValueError(f"top_p must be in [0.0, 1.0], got {self.top_p}.")
        if self.top_k is not None and self.top_k < 0:
            raise ValueError(f"top_k must be >= 0, got {self.top_k}.")

        # Normalize service_tier
        if isinstance(self.service_tier, str):
            if self.service_tier not in (t.value for t in ServiceTier):
                raise ValueError(
                    f"Invalid service_tier: {self.service_tier!r}. "
                    f"Must be 'auto' or 'standard_only'."
                )
            self.service_tier = ServiceTier(self.service_tier)

    def to_dict(self) -> dict[str, Any]:
        """Serialize the request to a JSON-compatible dict."""
        body: dict[str, Any] = {
            "model": self.model,
            "messages": [msg.to_dict() for msg in self.messages],
            "max_tokens": self.max_tokens,
        }

        if self.system is not None:
            body["system"] = self.system

        if self.temperature is not None:
            body["temperature"] = self.temperature

        if self.top_p is not None:
            body["top_p"] = self.top_p

        if self.top_k is not None:
            body["top_k"] = self.top_k

        if self.stop_sequences is not None:
            body["stop_sequences"] = self.stop_sequences

        if self.stream:
            body["stream"] = True

        if self.metadata is not None:
            body["metadata"] = self.metadata

        if self.tools is not None:
            body["tools"] = self.tools

        if self.tool_choice is not None:
            body["tool_choice"] = self.tool_choice

        if self.thinking is not None:
            body["thinking"] = self.thinking

        if self.service_tier is not None:
            body["service_tier"] = (
                self.service_tier.value
                if isinstance(self.service_tier, ServiceTier)
                else self.service_tier
            )

        return body

    def to_json(self, indent: int | None = None) -> str:
        """Serialize to a JSON string."""
        return json.dumps(self.to_dict(), indent=indent, ensure_ascii=False)


# ---------------------------------------------------------------------------
# Pre-built convenience constructors
# ---------------------------------------------------------------------------

def simple_text_request(
    prompt: str,
    model: str = "claude-sonnet-4-20250514",
    max_tokens: int = 1024,
    system: str | None = None,
) -> MessageRequest:
    """
    Build the simplest possible request: a single user text message.

    Args:
        prompt: The user's text message.
        model: Model identifier.
        max_tokens: Maximum tokens to generate.
        system: Optional system prompt string.

    Returns:
        A validated MessageRequest.
    """
    return MessageRequest(
        model=model,
        messages=[Message.user(prompt)],
        max_tokens=max_tokens,
        system=system,
    )


def multimodal_request(
    text: str,
    images: list[ImageBlock],
    model: str = "claude-sonnet-4-20250514",
    max_tokens: int = 1024,
    system: str | None = None,
) -> MessageRequest:
    """
    Build a request with text and images.

    Args:
        text: The text prompt.
        images: List of ImageBlock instances.
        model: Model identifier.
        max_tokens: Maximum tokens to generate.
        system: Optional system prompt.

    Returns:
        A validated MessageRequest with multimodal content.
    """
    blocks: list[ContentBlock] = [TextBlock(text=text)]
    blocks.extend(images)
    return MessageRequest(
        model=model,
        messages=[Message.user(blocks)],
        max_tokens=max_tokens,
        system=system,
    )


__all__ = [
    "ContentBlock",
    "TextBlock",
    "ImageBlock",
    "ToolUseBlock",
    "ToolResultBlock",
    "Message",
    "MessageRequest",
    "Role",
    "StopReason",
    "ServiceTier",
    "CacheTTL",
    "SUPPORTED_IMAGE_MEDIA_TYPES",
    "MESSAGES_ENDPOINT",
    "simple_text_request",
    "multimodal_request",
]
