"""
Tests for Chapter 11: JSON-RPC 2.0 Message Parser.

Covers all four message types, serialization round-trips, batch processing,
error handling, edge cases, and MCP-specific constraints.
"""

import json

import pytest

from json_rpc import (
    JSONRPCError,
    JSONRPCNotification,
    JSONRPCParseError,
    JSONRPCParser,
    JSONRPCRequest,
    JSONRPCResponse,
    make_error,
    make_notification,
    make_request,
    make_response,
    INVALID_REQUEST,
    INVALID_PARAMS,
    INTERNAL_ERROR,
    METHOD_NOT_FOUND,
    PARSE_ERROR,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def parser() -> JSONRPCParser:
    return JSONRPCParser()


# ---------------------------------------------------------------------------
# Request Tests
# ---------------------------------------------------------------------------


class TestRequest:
    def test_create_and_serialize(self, parser: JSONRPCParser) -> None:
        req = make_request(1, "test/echo", {"message": "hello"})
        raw = parser.serialize(req)
        parsed = json.loads(raw)
        assert parsed == {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "test/echo",
            "params": {"message": "hello"},
        }

    def test_parse_minimal_request(self, parser: JSONRPCParser) -> None:
        msg = parser.parse_message(
            '{"jsonrpc":"2.0","id":1,"method":"ping"}'
        )
        assert isinstance(msg, JSONRPCRequest)
        assert msg.id == 1
        assert msg.method == "ping"
        assert msg.params is None

    def test_parse_request_with_string_id(self, parser: JSONRPCParser) -> None:
        msg = parser.parse_message(
            '{"jsonrpc":"2.0","id":"req-abc","method":"fetch"}'
        )
        assert isinstance(msg, JSONRPCRequest)
        assert msg.id == "req-abc"
        assert msg.method == "fetch"

    def test_request_with_params(self, parser: JSONRPCParser) -> None:
        msg = parser.parse_message(
            '{"jsonrpc":"2.0","id":2,"method":"add","params":{"a":1,"b":2}}'
        )
        assert isinstance(msg, JSONRPCRequest)
        assert msg.params == {"a": 1, "b": 2}

    def test_round_trip_request(self, parser: JSONRPCParser) -> None:
        original = make_request(42, "tools/list", {"cursor": "abc"})
        raw = parser.serialize(original)
        parsed = parser.parse_message(raw)
        assert isinstance(parsed, JSONRPCRequest)
        assert parsed.id == original.id
        assert parsed.method == original.method
        assert parsed.params == original.params

    def test_id_must_not_be_null(self, parser: JSONRPCParser) -> None:
        with pytest.raises(JSONRPCParseError, match="must not be null"):
            parser.parse_message('{"jsonrpc":"2.0","id":null,"method":"test"}')

    def test_id_must_be_string_or_int(self, parser: JSONRPCParser) -> None:
        with pytest.raises(JSONRPCParseError, match="must be string or integer"):
            parser.parse_message('{"jsonrpc":"2.0","id":[1,2],"method":"test"}')


# ---------------------------------------------------------------------------
# Response Tests
# ---------------------------------------------------------------------------


class TestResponse:
    def test_create_and_serialize(self, parser: JSONRPCParser) -> None:
        resp = make_response(1, {"status": "ok"})
        raw = parser.serialize(resp)
        parsed = json.loads(raw)
        assert parsed == {
            "jsonrpc": "2.0",
            "id": 1,
            "result": {"status": "ok"},
        }

    def test_parse_response(self, parser: JSONRPCParser) -> None:
        msg = parser.parse_message(
            '{"jsonrpc":"2.0","id":3,"result":{"name":"Alice","age":30}}'
        )
        assert isinstance(msg, JSONRPCResponse)
        assert msg.id == 3
        assert msg.result == {"name": "Alice", "age": 30}

    def test_response_with_null_result(self, parser: JSONRPCParser) -> None:
        msg = parser.parse_message(
            '{"jsonrpc":"2.0","id":5,"result":null}'
        )
        assert isinstance(msg, JSONRPCResponse)
        assert msg.result is None

    def test_round_trip_response(self, parser: JSONRPCParser) -> None:
        original = make_response("abc", [1, 2, 3])
        raw = parser.serialize(original)
        parsed = parser.parse_message(raw)
        assert isinstance(parsed, JSONRPCResponse)
        assert parsed.id == original.id
        assert parsed.result == original.result

    def test_response_must_not_have_both_result_and_error(
        self, parser: JSONRPCParser,
    ) -> None:
        with pytest.raises(JSONRPCParseError, match="must not contain both"):
            parser.parse_message(
                '{"jsonrpc":"2.0","id":1,"result":"ok","error":{"code":-1,"message":"err"}}'
            )


# ---------------------------------------------------------------------------
# Error Tests
# ---------------------------------------------------------------------------


class TestError:
    def test_create_and_serialize(self, parser: JSONRPCParser) -> None:
        err = make_error(1, -32601, "Method not found")
        raw = parser.serialize(err)
        parsed = json.loads(raw)
        assert parsed == {
            "jsonrpc": "2.0",
            "id": 1,
            "error": {
                "code": -32601,
                "message": "Method not found",
            },
        }

    def test_parse_error_with_data(self, parser: JSONRPCParser) -> None:
        msg = parser.parse_message(
            json.dumps({
                "jsonrpc": "2.0",
                "id": 2,
                "error": {
                    "code": -32602,
                    "message": "Invalid params",
                    "data": {"field": "uri", "reason": "missing"},
                },
            })
        )
        assert isinstance(msg, JSONRPCError)
        assert msg.id == 2
        assert msg.code == -32602
        assert msg.message == "Invalid params"
        assert msg.data == {"field": "uri", "reason": "missing"}

    def test_parse_error_minimal(self, parser: JSONRPCParser) -> None:
        msg = parser.parse_message(
            '{"jsonrpc":"2.0","id":99,"error":{"code":-32000,"message":"Server error"}}'
        )
        assert isinstance(msg, JSONRPCError)
        assert msg.code == -32000

    def test_error_missing_code_field(self, parser: JSONRPCParser) -> None:
        with pytest.raises(JSONRPCParseError, match="must contain 'code'"):
            parser.parse_message(
                '{"jsonrpc":"2.0","id":1,"error":{"message":"no code"}}'
            )

    def test_error_code_must_be_integer(self, parser: JSONRPCParser) -> None:
        with pytest.raises(JSONRPCParseError, match="must be an integer"):
            parser.parse_message(
                '{"jsonrpc":"2.0","id":1,"error":{"code":"abc","message":"bad"}}'
            )

    def test_error_missing_message_field(self, parser: JSONRPCParser) -> None:
        with pytest.raises(JSONRPCParseError, match="must contain 'message'"):
            parser.parse_message(
                '{"jsonrpc":"2.0","id":1,"error":{"code":-1}}'
            )

    def test_round_trip_error(self, parser: JSONRPCParser) -> None:
        original = make_error(
            "req-99", -32602, "Invalid params", {"details": "bad type"}
        )
        raw = parser.serialize(original)
        parsed = parser.parse_message(raw)
        assert isinstance(parsed, JSONRPCError)
        assert parsed.id == original.id
        assert parsed.code == original.code
        assert parsed.message == original.message
        assert parsed.data == original.data


# ---------------------------------------------------------------------------
# Notification Tests
# ---------------------------------------------------------------------------


class TestNotification:
    def test_create_and_serialize(self, parser: JSONRPCParser) -> None:
        notif = make_notification(
            "notifications/initialized"
        )
        raw = parser.serialize(notif)
        parsed = json.loads(raw)
        assert parsed == {
            "jsonrpc": "2.0",
            "method": "notifications/initialized",
        }

    def test_parse_notification_with_params(self, parser: JSONRPCParser) -> None:
        msg = parser.parse_message(
            '{"jsonrpc":"2.0","method":"notifications/progress",'
            '"params":{"progressToken":"t1","progress":50,"total":100}}'
        )
        assert isinstance(msg, JSONRPCNotification)
        assert msg.method == "notifications/progress"
        assert msg.params == {"progressToken": "t1", "progress": 50, "total": 100}

    def test_parse_notification_no_params(self, parser: JSONRPCParser) -> None:
        msg = parser.parse_message(
            '{"jsonrpc":"2.0","method":"notifications/initialized"}'
        )
        assert isinstance(msg, JSONRPCNotification)
        assert msg.method == "notifications/initialized"
        assert msg.params is None

    def test_notification_must_not_have_id(self, parser: JSONRPCParser) -> None:
        """If a message has method but no id, it's parsed as notification."""
        # This is correct behavior for JSON-RPC: notification = no id + has method
        msg = parser.parse_message(
            '{"jsonrpc":"2.0","method":"notifications/cancelled",'
            '"params":{"requestId":123}}'
        )
        assert isinstance(msg, JSONRPCNotification)
        assert not hasattr(msg, "id")

    def test_round_trip_notification(self, parser: JSONRPCParser) -> None:
        original = make_notification(
            "notifications/resources/updated",
            {"uri": "file:///project/src/main.rs"},
        )
        raw = parser.serialize(original)
        parsed = parser.parse_message(raw)
        assert isinstance(parsed, JSONRPCNotification)
        assert parsed.method == original.method
        assert parsed.params == original.params


# ---------------------------------------------------------------------------
# Validation / Error Cases
# ---------------------------------------------------------------------------


class TestValidation:
    def test_invalid_json(self, parser: JSONRPCParser) -> None:
        with pytest.raises(JSONRPCParseError, match="Invalid JSON"):
            parser.parse_message("not json at all")

    def test_not_a_dict(self, parser: JSONRPCParser) -> None:
        with pytest.raises(JSONRPCParseError, match="must be a JSON object"):
            parser.parse_message("[1, 2, 3]")

    def test_missing_jsonrpc_version(self, parser: JSONRPCParser) -> None:
        with pytest.raises(JSONRPCParseError, match="Invalid or missing 'jsonrpc'"):
            parser.parse_message('{"id":1,"method":"test"}')

    def test_wrong_jsonrpc_version(self, parser: JSONRPCParser) -> None:
        with pytest.raises(JSONRPCParseError, match="expected '2.0'"):
            parser.parse_message('{"jsonrpc":"1.0","id":1,"method":"test"}')

    def test_ambiguous_message(self, parser: JSONRPCParser) -> None:
        """A message with id but no method, result, or error cannot be typed."""
        with pytest.raises(JSONRPCParseError, match="Cannot determine"):
            parser.parse_message('{"jsonrpc":"2.0","id":1}')


# ---------------------------------------------------------------------------
# Batch Tests
# ---------------------------------------------------------------------------


class TestBatch:
    def test_parse_batch_requests(self, parser: JSONRPCParser) -> None:
        raw = json.dumps([
            {"jsonrpc": "2.0", "id": 1, "method": "ping"},
            {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
            {"jsonrpc": "2.0", "method": "notifications/cancelled",
             "params": {"requestId": 1}},
        ])
        messages = parser.parse_batch(raw)
        assert len(messages) == 3
        assert isinstance(messages[0], JSONRPCRequest)
        assert isinstance(messages[1], JSONRPCRequest)
        assert isinstance(messages[2], JSONRPCNotification)

    def test_empty_batch(self, parser: JSONRPCParser) -> None:
        messages = parser.parse_batch("[]")
        assert messages == []

    def test_batch_not_an_array(self, parser: JSONRPCParser) -> None:
        with pytest.raises(JSONRPCParseError, match="must be a JSON array"):
            parser.parse_batch('{"a":1}')

    def test_serialize_batch(self, parser: JSONRPCParser) -> None:
        messages = [
            make_request(1, "ping"),
            make_response(2, "ok"),
        ]
        raw = parser.serialize_batch(messages)
        parsed_messages = parser.parse_batch(raw)
        assert len(parsed_messages) == 2
        assert isinstance(parsed_messages[0], JSONRPCRequest)
        assert isinstance(parsed_messages[1], JSONRPCResponse)

    def test_batch_with_error_in_item(self, parser: JSONRPCParser) -> None:
        raw = json.dumps([
            {"jsonrpc": "2.0", "id": 1, "method": "ok"},
            {"jsonrpc": "2.0"},  # missing method and id
        ])
        with pytest.raises(JSONRPCParseError):
            parser.parse_batch(raw)


# ---------------------------------------------------------------------------
# MCP Lifecycle Messages (Real-World Examples)
# ---------------------------------------------------------------------------


class TestMCPRealWorld:
    """Test parsing of actual MCP lifecycle and feature messages."""

    def test_initialize_request(self, parser: JSONRPCParser) -> None:
        raw = json.dumps({
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2025-03-26",
                "capabilities": {
                    "roots": {"listChanged": True},
                    "sampling": {},
                },
                "clientInfo": {"name": "TestClient", "version": "1.0.0"},
            },
        })
        msg = parser.parse_message(raw)
        assert isinstance(msg, JSONRPCRequest)
        assert msg.method == "initialize"
        assert msg.params["protocolVersion"] == "2025-03-26"
        assert msg.params["capabilities"]["sampling"] == {}

    def test_initialize_response(self, parser: JSONRPCParser) -> None:
        raw = json.dumps({
            "jsonrpc": "2.0",
            "id": 1,
            "result": {
                "protocolVersion": "2025-03-26",
                "capabilities": {
                    "tools": {"listChanged": True},
                    "resources": {"subscribe": True, "listChanged": True},
                },
                "serverInfo": {"name": "TestServer", "version": "2.0.0"},
            },
        })
        msg = parser.parse_message(raw)
        assert isinstance(msg, JSONRPCResponse)
        assert msg.result["serverInfo"]["name"] == "TestServer"

    def test_tools_list_request(self, parser: JSONRPCParser) -> None:
        msg = parser.parse_message(
            '{"jsonrpc":"2.0","id":2,"method":"tools/list","params":{"cursor":"p1"}}'
        )
        assert isinstance(msg, JSONRPCRequest)
        assert msg.method == "tools/list"

    def test_tools_call_response(self, parser: JSONRPCParser) -> None:
        raw = json.dumps({
            "jsonrpc": "2.0",
            "id": 3,
            "result": {
                "content": [{"type": "text", "text": "72F, sunny"}],
                "isError": False,
            },
        })
        msg = parser.parse_message(raw)
        assert isinstance(msg, JSONRPCResponse)
        assert msg.result["isError"] is False

    def test_sampling_create_message(self, parser: JSONRPCParser) -> None:
        raw = json.dumps({
            "jsonrpc": "2.0",
            "id": 10,
            "method": "sampling/createMessage",
            "params": {
                "messages": [
                    {"role": "user", "content": {"type": "text", "text": "Hello"}}
                ],
                "maxTokens": 100,
            },
        })
        msg = parser.parse_message(raw)
        assert isinstance(msg, JSONRPCRequest)
        assert msg.method == "sampling/createMessage"

    def test_resource_updated_notification(self, parser: JSONRPCParser) -> None:
        raw = json.dumps({
            "jsonrpc": "2.0",
            "method": "notifications/resources/updated",
            "params": {"uri": "file:///project/main.rs"},
        })
        msg = parser.parse_message(raw)
        assert isinstance(msg, JSONRPCNotification)
        assert msg.params["uri"] == "file:///project/main.rs"


# ---------------------------------------------------------------------------
# serialize() type error
# ---------------------------------------------------------------------------


def test_serialize_unknown_type_raises(parser: JSONRPCParser) -> None:
    with pytest.raises(TypeError, match="Unknown message type"):
        parser.serialize("not a message")  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# bytes input
# ---------------------------------------------------------------------------


def test_parse_bytes_input(parser: JSONRPCParser) -> None:
    msg = parser.parse_message(
        b'{"jsonrpc":"2.0","id":1,"method":"ping"}'
    )
    assert isinstance(msg, JSONRPCRequest)
    assert msg.method == "ping"
