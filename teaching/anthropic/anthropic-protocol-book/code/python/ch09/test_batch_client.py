"""
Tests for Chapter 9: BatchClient.

These tests validate protocol correctness — request/response shape,
status parsing, result parsing, and error handling — using httpx mock
transport so no real API key is required.
"""

from __future__ import annotations

import json
import time
from typing import Any, Dict, List

import httpx
import pytest

from batch_client import (
    ANTHROPIC_VERSION,
    DEFAULT_BASE_URL,
    BatchClient,
    BatchProcessingStatus,
    BatchResult,
    MessageRequest,
    ResultType,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _json_bytes(data: Any) -> bytes:
    return json.dumps(data).encode()


def _mock_transport(
    handler,
) -> httpx.MockTransport:
    """Return a MockTransport that delegates to *handler*(request) -> response."""
    return httpx.MockTransport(handler)


def _client(handler) -> BatchClient:
    client = BatchClient(api_key="sk-ant-test", base_url=DEFAULT_BASE_URL)
    client._client = httpx.Client(
        base_url=client._base_url,
        headers={
            "x-api-key": "sk-ant-test",
            "anthropic-version": ANTHROPIC_VERSION,
            "content-type": "application/json",
        },
        transport=_mock_transport(handler),
    )
    return client


# ---------------------------------------------------------------------------
# create_batch
# ---------------------------------------------------------------------------


class TestCreateBatch:
    def test_returns_batch_id(self):
        def handler(request: httpx.Request) -> httpx.Response:
            body = json.loads(request.read())
            assert len(body["requests"]) == 2
            assert body["requests"][0]["custom_id"] == "r1"
            return httpx.Response(
                200,
                json={"id": "msgbatch_test123", "processing_status": "in_progress"},
            )

        c = _client(handler)
        bid = c.create_batch([
            MessageRequest("r1", {"model": "claude-sonnet-4-20250514", "max_tokens": 100, "messages": [{"role": "user", "content": "Hi"}]}),
            MessageRequest("r2", {"model": "claude-sonnet-4-20250514", "max_tokens": 100, "messages": [{"role": "user", "content": "Bye"}]}),
        ])
        assert bid == "msgbatch_test123"

    def test_raises_on_http_error(self):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(401, json={"error": {"type": "authentication_error", "message": "bad key"}})

        c = _client(handler)
        with pytest.raises(httpx.HTTPStatusError):
            c.create_batch([
                MessageRequest("r1", {"model": "claude-sonnet-4-20250514", "max_tokens": 100, "messages": [{"role": "user", "content": "Hi"}]}),
            ])


# ---------------------------------------------------------------------------
# get_batch_status
# ---------------------------------------------------------------------------


class TestGetBatchStatus:
    def test_parses_in_progress(self):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={
                "id": "msgbatch_x",
                "processing_status": "in_progress",
                "request_counts": {"processing": 100, "succeeded": 0, "errored": 0, "canceled": 0, "expired": 0},
                "created_at": "2026-05-17T10:00:00Z",
                "expires_at": "2026-05-18T10:00:00Z",
            })

        c = _client(handler)
        info = c.get_batch_status("msgbatch_x")
        assert info.processing_status == BatchProcessingStatus.IN_PROGRESS
        assert info.id == "msgbatch_x"
        assert info.request_counts["processing"] == 100

    def test_parses_ended(self):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={
                "id": "msgbatch_done",
                "processing_status": "ended",
                "request_counts": {"processing": 0, "succeeded": 98, "errored": 2, "canceled": 0, "expired": 0},
                "created_at": "2026-05-17T10:00:00Z",
                "ended_at": "2026-05-17T10:45:00Z",
                "expires_at": "2026-05-18T10:00:00Z",
                "results_url": "https://api.anthropic.com/v1/messages/batches/msgbatch_done/results",
            })

        c = _client(handler)
        info = c.get_batch_status("msgbatch_done")
        assert info.processing_status == BatchProcessingStatus.ENDED
        assert info.request_counts["succeeded"] == 98
        assert info.request_counts["errored"] == 2
        assert info.results_url is not None


# ---------------------------------------------------------------------------
# get_batch_results
# ---------------------------------------------------------------------------


class TestGetBatchResults:
    def test_parses_jsonl_succeeded_errored_canceled_expired(self):
        """Each line of the JSONL is one request outcome."""
        jsonl = (
            '{"custom_id":"q1","result":{"type":"succeeded","message":{"id":"msg_1","role":"assistant","content":[{"type":"text","text":"Hello"}]}}}\n'
            '{"custom_id":"q2","result":{"type":"errored","error":{"type":"invalid_request_error","message":"Bad param"}}}\n'
            '{"custom_id":"q3","result":{"type":"canceled"}}\n'
            '{"custom_id":"q4","result":{"type":"expired"}}\n'
        )

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, content=jsonl)

        c = _client(handler)
        results = c.get_batch_results("msgbatch_done")

        assert len(results) == 4

        # succeeded
        assert results[0].custom_id == "q1"
        assert results[0].result_type == ResultType.SUCCEEDED
        assert results[0].message is not None
        assert results[0].message["content"][0]["text"] == "Hello"
        assert results[0].error is None

        # errored
        assert results[1].custom_id == "q2"
        assert results[1].result_type == ResultType.ERRORED
        assert results[1].error is not None
        assert results[1].error["type"] == "invalid_request_error"

        # canceled
        assert results[2].custom_id == "q3"
        assert results[2].result_type == ResultType.CANCELED

        # expired
        assert results[3].custom_id == "q4"
        assert results[3].result_type == ResultType.EXPIRED


# ---------------------------------------------------------------------------
# cancel_batch
# ---------------------------------------------------------------------------


class TestCancelBatch:
    def test_cancel_returns_updated_batch_info(self):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={
                "id": "msgbatch_cx",
                "processing_status": "canceled",
                "request_counts": {"processing": 0, "succeeded": 5, "errored": 0, "canceled": 95, "expired": 0},
            })

        c = _client(handler)
        info = c.cancel_batch("msgbatch_cx")
        assert info.processing_status == BatchProcessingStatus.CANCELED
        assert info.request_counts["canceled"] == 95


# ---------------------------------------------------------------------------
# list_batches
# ---------------------------------------------------------------------------


class TestListBatches:
    def test_lists_batches_with_pagination(self):
        batches_data = [
            {"id": "msgbatch_a", "processing_status": "ended", "request_counts": {"succeeded": 10}},
            {"id": "msgbatch_b", "processing_status": "in_progress", "request_counts": {"processing": 5}},
        ]

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={
                "data": batches_data,
                "has_more": False,
                "first_id": "msgbatch_a",
                "last_id": "msgbatch_b",
            })

        c = _client(handler)
        batches = c.list_batches(limit=10)
        assert len(batches) == 2
        assert batches[0].id == "msgbatch_a"
        assert batches[0].processing_status == BatchProcessingStatus.ENDED
        assert batches[1].id == "msgbatch_b"
        assert batches[1].processing_status == BatchProcessingStatus.IN_PROGRESS


# ---------------------------------------------------------------------------
# wait_for_completion
# ---------------------------------------------------------------------------


class TestWaitForCompletion:
    def test_returns_results_when_already_ended(self):
        call_count: List[int] = [0]

        def handler(request: httpx.Request) -> httpx.Response:
            call_count[0] += 1
            if "/results" in str(request.url):
                return httpx.Response(200, content='{"custom_id":"q1","result":{"type":"succeeded","message":{"id":"m1","role":"assistant","content":[{"type":"text","text":"OK"}]}}}\n')
            return httpx.Response(200, json={
                "id": "msgbatch_done",
                "processing_status": "ended",
                "request_counts": {"succeeded": 1},
            })

        c = _client(handler)
        results = c.wait_for_completion("msgbatch_done", poll_interval=0.01)
        assert len(results) == 1
        assert results[0].result_type == ResultType.SUCCEEDED
        assert call_count[0] == 2  # one status check + one results fetch

    def test_raises_timeout(self):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={
                "id": "msgbatch_slow",
                "processing_status": "in_progress",
                "request_counts": {"processing": 1},
            })

        c = _client(handler)
        with pytest.raises(TimeoutError, match="did not complete"):
            c.wait_for_completion("msgbatch_slow", poll_interval=0.01, max_wait=0.05)

    def test_raises_on_expired(self):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={
                "id": "msgbatch_exp",
                "processing_status": "expired",
                "request_counts": {"expired": 10},
            })

        c = _client(handler)
        with pytest.raises(RuntimeError, match="expired"):
            c.wait_for_completion("msgbatch_exp", poll_interval=0.01)

    def test_raises_on_canceled(self):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={
                "id": "msgbatch_cxl",
                "processing_status": "canceled",
                "request_counts": {"canceled": 10},
            })

        c = _client(handler)
        with pytest.raises(RuntimeError, match="canceled"):
            c.wait_for_completion("msgbatch_cxl", poll_interval=0.01)

    def test_polls_until_ended(self):
        """Simulate 2 polls where the batch transitions from in_progress to ended."""
        status_calls: List[int] = [0]

        def handler(request: httpx.Request) -> httpx.Response:
            if "/results" in str(request.url):
                return httpx.Response(200, content='{"custom_id":"q1","result":{"type":"succeeded","message":{"id":"m1","role":"assistant","content":[{"type":"text","text":"Done"}]}}}\n')
            status_calls[0] += 1
            if status_calls[0] == 1:
                return httpx.Response(200, json={
                    "id": "msgbatch_wip",
                    "processing_status": "in_progress",
                    "request_counts": {"processing": 1},
                })
            return httpx.Response(200, json={
                "id": "msgbatch_wip",
                "processing_status": "ended",
                "request_counts": {"succeeded": 1},
            })

        c = _client(handler)
        results = c.wait_for_completion("msgbatch_wip", poll_interval=0.01)
        assert len(results) == 1
        assert results[0].result_type == ResultType.SUCCEEDED
        assert status_calls[0] == 2


# ---------------------------------------------------------------------------
# make_cacheable_request
# ---------------------------------------------------------------------------


class TestMakeCacheableRequest:
    def test_default_ephemeral_cache(self):
        req = BatchClient.make_cacheable_request(
            custom_id="c1",
            model="claude-sonnet-4-20250514",
            max_tokens=200,
            user_message="What is the book about?",
            system_prompt="You are a literary critic.",
        )
        assert req.custom_id == "c1"
        assert req.params["system"][0]["cache_control"] == {"type": "ephemeral"}
        assert "ttl" not in req.params["system"][0]["cache_control"]

    def test_one_hour_cache_ttl(self):
        req = BatchClient.make_cacheable_request(
            custom_id="c2",
            model="claude-sonnet-4-20250514",
            max_tokens=200,
            user_message="Summarize.",
            system_prompt="You are a helpful assistant.",
            cache_ttl=3600,
        )
        assert req.params["system"][0]["cache_control"]["ttl"] == 3600
        assert req.params["system"][0]["cache_control"]["type"] == "ephemeral"

    def test_no_system_prompt(self):
        req = BatchClient.make_cacheable_request(
            custom_id="c3",
            model="claude-sonnet-4-20250514",
            max_tokens=100,
            user_message="Hello",
        )
        assert "system" not in req.params
        assert req.params["messages"][0]["content"] == "Hello"


# ---------------------------------------------------------------------------
# Domain types
# ---------------------------------------------------------------------------


class TestDomainTypes:
    def test_batch_processing_status_values(self):
        assert BatchProcessingStatus.IN_PROGRESS.value == "in_progress"
        assert BatchProcessingStatus.ENDED.value == "ended"
        assert BatchProcessingStatus.CANCELED.value == "canceled"
        assert BatchProcessingStatus.EXPIRED.value == "expired"

    def test_result_type_values(self):
        assert ResultType.SUCCEEDED.value == "succeeded"
        assert ResultType.ERRORED.value == "errored"
        assert ResultType.CANCELED.value == "canceled"
        assert ResultType.EXPIRED.value == "expired"

    def test_message_request_construction(self):
        req = MessageRequest(
            custom_id="test-1",
            params={
                "model": "claude-haiku-3-5-20241022",
                "max_tokens": 50,
                "messages": [{"role": "user", "content": "ping"}],
            },
        )
        assert req.custom_id == "test-1"
        assert req.params["model"] == "claude-haiku-3-5-20241022"
