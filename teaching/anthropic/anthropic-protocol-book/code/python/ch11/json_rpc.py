"""
Chapter 11: JSON-RPC 2.0 Message Parser.

Protocol-level implementation of the JSON-RPC 2.0 specification as used by the
Model Context Protocol (MCP). Supports Request, Response, Error, Notification
message types, round-trip serialization, and validation.

Reference: https://www.jsonrpc.org/specification
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Dict, Optional, Union


# ---------------------------------------------------------------------------
# Message Types
# ---------------------------------------------------------------------------


@dataclass
class JSONRPCRequest:
    """JSON-RPC 2.0 Request message.

    A request represents a call to a remote method. The caller is identified
    by a unique `id` that the responder MUST echo back.

    MCP constraint: `id` MUST NOT be None — unlike base JSON-RPC, null IDs
    are not permitted in MCP contexts.
    """

    id: Union[int, str]
    method: str
    params: Optional[Dict[str, Any]] = None
    jsonrpc: str = "2.0"


@dataclass
class JSONRPCResponse:
    """JSON-RPC 2.0 successful Response message.

    MUST include the same `id` as the corresponding request.
    MUST NOT set both `result` and `error`.
    """

    id: Union[int, str]
    result: Any = None
    jsonrpc: str = "2.0"


@dataclass
class JSONRPCError:
    """JSON-RPC 2.0 Error message.

    Standard error codes:
      -32700  Parse error
      -32600  Invalid Request
      -32601  Method not found
      -32602  Invalid params
      -32603  Internal error
      -32000 to -32099  Server error (reserved for implementation-defined errors)
    """

    id: Union[int, str]
    code: int
    message: str
    data: Optional[Any] = None
    jsonrpc: str = "2.0"


@dataclass
class JSONRPCNotification:
    """JSON-RPC 2.0 Notification message.

    A one-way message that MUST NOT receive a response.
    MUST NOT include an `id` field.
    """

    method: str
    params: Optional[Dict[str, Any]] = None
    jsonrpc: str = "2.0"


# Union type for all parse-able messages
JSONRPCMessage = Union[JSONRPCRequest, JSONRPCResponse, JSONRPCError, JSONRPCNotification]

# Standard JSON-RPC 2.0 error codes
PARSE_ERROR = -32700
INVALID_REQUEST = -32600
METHOD_NOT_FOUND = -32601
INVALID_PARAMS = -32602
INTERNAL_ERROR = -32603


# ---------------------------------------------------------------------------
# Parser
# ---------------------------------------------------------------------------


class JSONRPCParseError(ValueError):
    """Raised when a raw message cannot be parsed as a valid JSON-RPC message."""

    pass


class JSONRPCParser:
    """Parse and serialize JSON-RPC 2.0 messages.

    Handles all four message types defined by the specification, plus JSON-RPC
    batch arrays (optionally). Validates structural requirements including the
    mandatory `jsonrpc` version field, presence/absence of `id`, and mutual
    exclusivity of `result`/`error`.
    """

    def parse_message(self, raw: Union[str, bytes]) -> JSONRPCMessage:
        """Parse a raw JSON-RPC 2.0 string into a typed message object.

        Args:
            raw: A UTF-8 encoded JSON string or bytes.

        Returns:
            One of JSONRPCRequest, JSONRPCResponse, JSONRPCError, or
            JSONRPCNotification.

        Raises:
            JSONRPCParseError: If the message is not valid JSON or does not
                conform to the JSON-RPC 2.0 specification.
        """
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8")

        try:
            obj = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise JSONRPCParseError(f"Invalid JSON: {exc}") from exc

        if not isinstance(obj, dict):
            raise JSONRPCParseError(
                "JSON-RPC message must be a JSON object, not an array or scalar"
            )

        # Validate jsonrpc version
        version = obj.get("jsonrpc")
        if version != "2.0":
            raise JSONRPCParseError(
                f"Invalid or missing 'jsonrpc' field: expected '2.0', got {version!r}"
            )

        has_id = "id" in obj
        has_method = "method" in obj
        has_result = "result" in obj
        has_error = "error" in obj

        # --- Notification (no id, has method) ---
        if not has_id and has_method:
            params = obj.get("params")
            return JSONRPCNotification(method=obj["method"], params=params)

        # --- Request (has id and method, no result/error) ---
        if has_id and has_method and not has_result and not has_error:
            msg_id = obj["id"]
            if msg_id is None:
                raise JSONRPCParseError("Request 'id' must not be null per MCP spec")
            if not isinstance(msg_id, (int, str)):
                raise JSONRPCParseError(
                    f"Request 'id' must be string or integer, got {type(msg_id).__name__}"
                )
            params = obj.get("params")
            return JSONRPCRequest(id=msg_id, method=obj["method"], params=params)

        # Per JSON-RPC 2.0: a response MUST NOT contain both result and error
        if has_result and has_error:
            raise JSONRPCParseError(
                "A JSON-RPC message must not contain both 'result' and 'error'"
            )

        # --- Error (has id and error; no result) ---
        if has_id and has_error:
            error_obj = obj["error"]
            if not isinstance(error_obj, dict):
                raise JSONRPCParseError("'error' must be an object")
            if "code" not in error_obj:
                raise JSONRPCParseError("'error' must contain 'code'")
            if not isinstance(error_obj["code"], int):
                raise JSONRPCParseError("'error.code' must be an integer")
            if "message" not in error_obj:
                raise JSONRPCParseError("'error' must contain 'message'")
            return JSONRPCError(
                id=obj["id"],
                code=error_obj["code"],
                message=error_obj["message"],
                data=error_obj.get("data"),
            )

        # --- Response (has id and result; no error) ---
        if has_id and has_result and not has_error:
            return JSONRPCResponse(id=obj["id"], result=obj["result"])

        raise JSONRPCParseError(
            "Cannot determine message type: structure does not match any "
            "JSON-RPC 2.0 message variant"
        )

    def parse_batch(
        self, raw: Union[str, bytes]
    ) -> list[JSONRPCMessage]:
        """Parse a JSON-RPC 2.0 batch array.

        Args:
            raw: A JSON string or bytes containing an array of JSON-RPC messages.

        Returns:
            List of parsed message objects (may be empty if array is empty).
        """
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8")

        try:
            obj = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise JSONRPCParseError(f"Invalid JSON: {exc}") from exc

        if not isinstance(obj, list):
            raise JSONRPCParseError("Batch must be a JSON array")

        return [self.parse_message(json.dumps(item)) for item in obj]

    def serialize(self, msg: JSONRPCMessage) -> str:
        """Serialize a typed message back to a JSON-RPC 2.0 JSON string.

        Args:
            msg: A JSONRPCRequest, JSONRPCResponse, JSONRPCError, or
                JSONRPCNotification.

        Returns:
            A compact JSON string (no trailing newline).
        """
        if isinstance(msg, JSONRPCRequest):
            d: Dict[str, Any] = {
                "jsonrpc": msg.jsonrpc,
                "id": msg.id,
                "method": msg.method,
            }
            if msg.params is not None:
                d["params"] = msg.params
            return json.dumps(d, ensure_ascii=False)

        elif isinstance(msg, JSONRPCResponse):
            d = {"jsonrpc": msg.jsonrpc, "id": msg.id, "result": msg.result}
            return json.dumps(d, ensure_ascii=False)

        elif isinstance(msg, JSONRPCError):
            error_dict: Dict[str, Any] = {
                "code": msg.code,
                "message": msg.message,
            }
            if msg.data is not None:
                error_dict["data"] = msg.data
            d = {
                "jsonrpc": msg.jsonrpc,
                "id": msg.id,
                "error": error_dict,
            }
            return json.dumps(d, ensure_ascii=False)

        elif isinstance(msg, JSONRPCNotification):
            d: Dict[str, Any] = {
                "jsonrpc": msg.jsonrpc,
                "method": msg.method,
            }
            if msg.params is not None:
                d["params"] = msg.params
            return json.dumps(d, ensure_ascii=False)

        else:
            raise TypeError(f"Unknown message type: {type(msg).__name__}")

    def serialize_batch(self, messages: list[JSONRPCMessage]) -> str:
        """Serialize a list of messages as a JSON-RPC 2.0 batch array."""
        items = []
        for msg in messages:
            # Deserialize each message to a dict so we can combine them
            items.append(json.loads(self.serialize(msg)))
        return json.dumps(items, ensure_ascii=False)


# ---------------------------------------------------------------------------
# Factory helpers
# ---------------------------------------------------------------------------


def make_request(
    request_id: Union[int, str],
    method: str,
    params: Optional[Dict[str, Any]] = None,
) -> JSONRPCRequest:
    """Create a JSON-RPC 2.0 request."""
    return JSONRPCRequest(id=request_id, method=method, params=params)


def make_response(request_id: Union[int, str], result: Any) -> JSONRPCResponse:
    """Create a JSON-RPC 2.0 successful response."""
    return JSONRPCResponse(id=request_id, result=result)


def make_error(
    request_id: Union[int, str],
    code: int,
    message: str,
    data: Optional[Any] = None,
) -> JSONRPCError:
    """Create a JSON-RPC 2.0 error response."""
    return JSONRPCError(id=request_id, code=code, message=message, data=data)


def make_notification(
    method: str,
    params: Optional[Dict[str, Any]] = None,
) -> JSONRPCNotification:
    """Create a JSON-RPC 2.0 notification."""
    return JSONRPCNotification(method=method, params=params)
