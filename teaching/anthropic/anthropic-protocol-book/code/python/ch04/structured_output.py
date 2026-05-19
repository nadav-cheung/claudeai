"""
Chapter 4: Structured Outputs Client.

Protocol-level implementation of Anthropic's structured outputs feature
using the `output_config` request parameter with JSON Schema constraints.

This module wraps the Chapter 1 AnthropicClient to add constrained JSON
output generation, schema validation, and data extraction capabilities.
"""

from __future__ import annotations

import json
import re
from typing import Any


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


class StructuredOutputClient:
    """Client for generating structured JSON output from Claude.

    Wraps the Chapter 1 AnthropicClient, adding the ``output_config``
    parameter that enforces JSON Schema constraints on the response.

    Usage::

        from ch01.client import AnthropicClient
        from ch04.structured_output import StructuredOutputClient

        client = StructuredOutputClient(AnthropicClient())

        result = client.create(
            model="claude-sonnet-4-20250514",
            messages=[{"role": "user", "content": "List 3 colors"}],
            json_schema={
                "type": "object",
                "properties": {
                    "colors": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["colors"],
            },
            system="Respond with valid JSON only.",
        )
    """

    def __init__(self, client: Any) -> None:
        """Wrap an existing AnthropicClient instance (or any compatible object).

        The *client* must implement a ``post(**kwargs) -> dict`` method.
        """
        self._client = client

    # ------------------------------------------------------------------
    # create()
    # ------------------------------------------------------------------

    def create(
        self,
        model: str,
        messages: list[dict[str, Any]],
        json_schema: dict[str, Any],
        *,
        system: str | None = None,
        max_tokens: int = 4096,
        effort: str | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Generate a message with output constrained to *json_schema*.

        Parameters
        ----------
        model:
            Model identifier (e.g. ``"claude-sonnet-4-20250514"``).
        messages:
            Conversation messages in Anthropic Content Block format.
        json_schema:
            JSON Schema that the response MUST conform to.  The top-level
            ``type`` must be ``"object"``.  Nested ``$ref``, ``oneOf``,
            ``anyOf``, and ``allOf`` are NOT supported by the API.
        system:
            Optional system prompt.
        max_tokens:
            Hard cap on output tokens.  Defaults to 4096.
        effort:
            Optional effort level for the output schema enforcement.
            Supported values: ``"low"``, ``"medium"``, ``"high"``,
            ``"xhigh"``, ``"max"``.  Default (``None``) uses the API
            default.
        **kwargs:
            Additional parameters forwarded to ``AnthropicClient.post``
            (e.g. ``temperature``, ``top_p``).

        Returns
        -------
        dict
            Parsed JSON response body.  The assistant's text content is
            available at ``result["content"][0]["text"]`` and can be
            deserialised with ``json.loads`` to obtain the structured
            object.
        """
        output_config: dict[str, Any] = {
            "format": {
                "type": "json_schema",
                "schema": json_schema,
            },
        }
        if effort is not None:
            output_config["effort"] = effort

        return self._client.post(
            messages=messages,
            model=model,
            max_tokens=max_tokens,
            system=system,
            output_config=output_config,
            **kwargs,
        )

    # ------------------------------------------------------------------
    # extract()
    # ------------------------------------------------------------------

    def extract(
        self,
        model: str,
        text: str,
        json_schema: dict[str, Any],
        *,
        field_description: str = "Extract the requested information.",
        max_tokens: int = 4096,
        effort: str | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Extract structured data from unstructured *text*.

        This is a convenience wrapper around :meth:`create` that
        constructs a data-extraction prompt automatically.

        Parameters
        ----------
        model:
            Model identifier.
        text:
            The raw text to extract structured data from.
        json_schema:
            JSON Schema describing the desired output shape.
        field_description:
            A human-readable description of what to extract.
            This is included in the user prompt.
        max_tokens:
            Output token cap (default 4096).
        effort:
            Optional effort level.

        Returns
        -------
        dict
            The deserialised structured object extracted from *text*.
        """
        user_message: dict[str, Any] = {
            "role": "user",
            "content": (
                f"{field_description}\n\n"
                f"Input text:\n{text}\n\n"
                "Return ONLY the JSON object, with no additional text."
            ),
        }

        system_prompt = (
            "You are a data extraction assistant. "
            "Your only task is to extract structured information from the "
            "provided text. Always return valid JSON conforming to the "
            "specified schema. Do NOT include explanations, markdown "
            "fencing, or any text outside the JSON object."
        )

        response = self.create(
            model=model,
            messages=[user_message],
            json_schema=json_schema,
            system=system_prompt,
            max_tokens=max_tokens,
            effort=effort,
            **kwargs,
        )

        # Parse the JSON from the response text.
        raw_text = response["content"][0]["text"]
        return _parse_json_response(raw_text)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

_JSON_BLOCK_RE = re.compile(r"```(?:json)?\s*\n?(.*?)\n?```", re.DOTALL)


def _parse_json_response(text: str) -> dict[str, Any]:
    """Parse a JSON object from a model response that may include markdown.

    Tries (in order):
    1. ``json.loads`` on the raw text.
    2. Extract content from a ```json ... ``` fenced block.
    3. Extract content from a ``` ... ``` fenced block.
    """
    # Attempt 1: pure JSON
    try:
        return json.loads(text)  # type: ignore[no-any-return]
    except (json.JSONDecodeError, ValueError):
        pass

    # Attempt 2: ```json ... ```
    m = _JSON_BLOCK_RE.search(text)
    if m:
        return json.loads(m.group(1))  # type: ignore[no-any-return]

    # Attempt 3: find the outermost { ... } pair
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        return json.loads(text[start : end + 1])  # type: ignore[no-any-return]

    raise ValueError(f"Could not parse JSON from response text: {text[:200]}")
