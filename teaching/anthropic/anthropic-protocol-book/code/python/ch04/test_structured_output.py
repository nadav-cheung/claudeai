"""
Tests for Chapter 4 Structured Outputs client.

All tests use httpx MockTransport -- no real API calls.
"""

from __future__ import annotations

import json

import httpx
import pytest

from structured_output import StructuredOutputClient, _parse_json_response


# ---------------------------------------------------------------------------
# JSON Schema fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def color_schema() -> dict:
    return {
        "type": "object",
        "properties": {
            "colors": {"type": "array", "items": {"type": "string"}},
            "count": {"type": "integer"},
        },
        "required": ["colors"],
    }


@pytest.fixture
def person_schema() -> dict:
    return {
        "type": "object",
        "properties": {
            "name": {"type": "string"},
            "age": {"type": "integer"},
            "email": {"type": "string"},
        },
        "required": ["name", "age"],
    }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class _FakeClient:
    """Minimal fake that records the last request and returns a canned response."""

    def __init__(self, response_body: dict | list | None = None) -> None:
        self.last_kwargs: dict = {}
        self._response = response_body

    def post(self, **kwargs) -> dict:
        self.last_kwargs = kwargs
        if self._response is not None:
            return self._response
        return {
            "id": "msg_fake",
            "type": "message",
            "role": "assistant",
            "content": [{"type": "text", "text": '{"colors":["red","green","blue"],"count":3}'}],
            "model": "claude-sonnet-4-20250514",
            "stop_reason": "end_turn",
            "stop_sequence": None,
            "usage": {"input_tokens": 50, "output_tokens": 30},
        }


def _fake_client_with_text(text: str) -> _FakeClient:
    return _FakeClient({
        "id": "msg_fake",
        "type": "message",
        "role": "assistant",
        "content": [{"type": "text", "text": text}],
        "model": "claude-fake",
        "stop_reason": "end_turn",
        "stop_sequence": None,
        "usage": {"input_tokens": 10, "output_tokens": 5},
    })


# ---------------------------------------------------------------------------
# StructuredOutputClient tests
# ---------------------------------------------------------------------------


class TestStructuredOutputClientCreate:
    """Tests for the create() method."""

    def test_create_passes_output_config(self, color_schema):
        fc = _FakeClient()
        sut = StructuredOutputClient(fc)

        sut.create(
            model="claude-sonnet-4-20250514",
            messages=[{"role": "user", "content": "List colors"}],
            json_schema=color_schema,
            system="Be concise.",
        )

        kwargs = fc.last_kwargs
        assert kwargs["model"] == "claude-sonnet-4-20250514"
        assert kwargs["system"] == "Be concise."
        assert kwargs["max_tokens"] == 4096

        oc = kwargs["output_config"]
        assert oc["format"]["type"] == "json_schema"
        assert oc["format"]["schema"] == color_schema

    def test_create_defaults_max_tokens(self, color_schema):
        fc = _FakeClient()
        sut = StructuredOutputClient(fc)
        sut.create(
            model="x",
            messages=[],
            json_schema=color_schema,
        )
        assert fc.last_kwargs["max_tokens"] == 4096

    def test_create_custom_max_tokens(self, color_schema):
        fc = _FakeClient()
        sut = StructuredOutputClient(fc)
        sut.create(
            model="x",
            messages=[],
            json_schema=color_schema,
            max_tokens=256,
        )
        assert fc.last_kwargs["max_tokens"] == 256

    def test_create_with_effort(self, color_schema):
        fc = _FakeClient()
        sut = StructuredOutputClient(fc)
        sut.create(
            model="x",
            messages=[],
            json_schema=color_schema,
            effort="high",
        )
        assert fc.last_kwargs["output_config"]["effort"] == "high"

    def test_create_without_effort(self, color_schema):
        fc = _FakeClient()
        sut = StructuredOutputClient(fc)
        sut.create(
            model="x",
            messages=[],
            json_schema=color_schema,
        )
        assert "effort" not in fc.last_kwargs["output_config"]

    def test_create_passes_extra_kwargs(self, color_schema):
        fc = _FakeClient()
        sut = StructuredOutputClient(fc)
        sut.create(
            model="x",
            messages=[],
            json_schema=color_schema,
            temperature=0.3,
            top_p=0.9,
        )
        assert fc.last_kwargs["temperature"] == 0.3
        assert fc.last_kwargs["top_p"] == 0.9

    def test_create_returns_response(self, color_schema):
        fc = _FakeClient()
        sut = StructuredOutputClient(fc)
        result = sut.create(
            model="x",
            messages=[],
            json_schema=color_schema,
        )
        assert result["id"] == "msg_fake"
        assert result["content"][0]["text"] is not None


class TestStructuredOutputClientExtract:
    """Tests for the extract() convenience method."""

    def test_extract_pure_json_response(self, person_schema):
        fc = _fake_client_with_text('{"name":"Alice","age":30,"email":"alice@example.com"}')
        sut = StructuredOutputClient(fc)

        result = sut.extract(
            model="claude-sonnet-4-20250514",
            text="Alice is 30 years old.",
            json_schema=person_schema,
        )

        assert result["name"] == "Alice"
        assert result["age"] == 30
        assert result["email"] == "alice@example.com"

    def test_extract_json_in_markdown_fence(self, person_schema):
        fc = _fake_client_with_text(
            'Here is the result:\n```json\n{"name":"Bob","age":25}\n```'
        )
        sut = StructuredOutputClient(fc)

        result = sut.extract(
            model="x",
            text="Bob is 25.",
            json_schema=person_schema,
        )

        assert result["name"] == "Bob"
        assert result["age"] == 25

    def test_extract_constructs_prompt(self, person_schema):
        fc = _fake_client_with_text('{"name":"Eve","age":40}')
        sut = StructuredOutputClient(fc)

        sut.extract(
            model="x",
            text="Eve is 40.",
            json_schema=person_schema,
            field_description="Get the person info.",
        )

        user_msg = fc.last_kwargs["messages"][0]
        assert "Get the person info." in user_msg["content"]
        assert "Eve is 40." in user_msg["content"]
        assert fc.last_kwargs["system"] is not None

    def test_extract_uses_effort(self, person_schema):
        fc = _fake_client_with_text('{"name":"Dan","age":22}')
        sut = StructuredOutputClient(fc)

        sut.extract(
            model="x",
            text="Dan is 22.",
            json_schema=person_schema,
            effort="low",
        )

        assert fc.last_kwargs["output_config"]["effort"] == "low"

    def test_extract_complex_schema(self):
        schema = {
            "type": "object",
            "properties": {
                "title": {"type": "string"},
                "tags": {"type": "array", "items": {"type": "string"}},
                "metadata": {
                    "type": "object",
                    "properties": {
                        "author": {"type": "string"},
                        "priority": {"type": "integer", "enum": [1, 2, 3]},
                    },
                    "required": ["author"],
                },
            },
            "required": ["title", "tags"],
        }
        response = {
            "title": "My Document",
            "tags": ["important", "review"],
            "metadata": {"author": "Nadav", "priority": 1},
        }
        fc = _fake_client_with_text(json.dumps(response))
        sut = StructuredOutputClient(fc)

        result = sut.extract(
            model="x",
            text="Dummy",
            json_schema=schema,
        )

        assert result["title"] == "My Document"
        assert result["tags"] == ["important", "review"]
        assert result["metadata"]["author"] == "Nadav"
        assert result["metadata"]["priority"] == 1


# ---------------------------------------------------------------------------
# _parse_json_response tests
# ---------------------------------------------------------------------------


class TestParseJsonResponse:
    def test_parses_pure_json(self):
        result = _parse_json_response('{"a":1,"b":"two"}')
        assert result == {"a": 1, "b": "two"}

    def test_parses_json_in_fenced_block(self):
        text = 'Some intro text\n```json\n{"x": [1,2,3]}\n```\nSome outro'
        result = _parse_json_response(text)
        assert result == {"x": [1, 2, 3]}

    def test_parses_json_in_untyped_fenced_block(self):
        text = '```\n{"key": "value"}\n```'
        result = _parse_json_response(text)
        assert result == {"key": "value"}

    def test_parses_json_surrounded_by_text(self):
        text = 'Sure! Here you go: {"items": ["a","b"]} Hope that helps!'
        result = _parse_json_response(text)
        assert result == {"items": ["a", "b"]}

    def test_handles_nested_braces(self):
        text = '{"outer": {"inner": [1,2,3]}}'
        result = _parse_json_response(text)
        assert result == {"outer": {"inner": [1, 2, 3]}}

    def test_raises_on_garbage(self):
        with pytest.raises(ValueError, match="Could not parse JSON"):
            _parse_json_response("this is not json at all")

    def test_parses_empty_object(self):
        result = _parse_json_response("{}")
        assert result == {}
