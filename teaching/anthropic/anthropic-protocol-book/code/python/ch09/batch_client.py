"""
Chapter 9: BatchClient — async bulk processing via the Message Batches API.

Protocol-level implementation that communicates directly with the Anthropic
HTTP API (no SDK dependency). Covers the full MessageBatch lifecycle:
create → poll status → retrieve results → interpret per-request outcomes.

Verified against official docs (docs.anthropic.com, May 2026):
  - 50% cost discount on all models
  - 24-hour completion SLA (batches expire after 24h)
  - Results available for 29 days
  - Max 100 000 requests or 256 MB per batch
  - Per-request result types: succeeded, errored, canceled, expired
  - Prompt caching supported (5-min ephemeral TTL, best-effort)
  - 1-hour cache TTL available via cache_control ttl parameter
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

import httpx


# ---------------------------------------------------------------------------
# Domain types
# ---------------------------------------------------------------------------


class BatchProcessingStatus(str, Enum):
    """MessageBatch lifecycle states.

    Per the Anthropic API: a batch starts in ``in_progress``, then transitions
    to ``ended`` once every request has been processed.  Users may also
    explicitly cancel a batch (``canceled``), or the system will expire it
    if processing exceeds 24 hours (``expired``).
    """

    IN_PROGRESS = "in_progress"
    ENDED = "ended"
    CANCELED = "canceled"
    EXPIRED = "expired"


class ResultType(str, Enum):
    """Per-request outcome within a completed batch.

    ``succeeded``
        The request was processed and the model returned a message.  You
        are billed for these requests at the batch rate.
    ``errored``
        The request could not be processed (invalid params, internal server
        error, etc.).  You are **not** billed.
    ``canceled``
        The batch was canceled before this request reached the model.
        You are **not** billed.
    ``expired``
        The 24-hour SLA elapsed before this request could be processed.
        You are **not** billed.
    """

    SUCCEEDED = "succeeded"
    ERRORED = "errored"
    CANCELED = "canceled"
    EXPIRED = "expired"


@dataclass
class MessageRequest:
    """A single request within a batch.

    Attributes:
        custom_id:
            Client-defined identifier.  Must be unique within the batch.
            Used to correlate results back to source requests since the
            response order is not guaranteed.
        params:
            Standard Messages API parameters (``model``, ``max_tokens``,
            ``messages``, and optionally ``system``, ``tools``, ``temperature``,
            ``top_p``, ``stop_sequences``, ``metadata``, etc.).
    """

    custom_id: str
    params: Dict[str, Any]


@dataclass
class BatchInfo:
    """Summary returned by the ``/v1/messages/batches/{id}`` endpoint."""

    id: str
    processing_status: BatchProcessingStatus
    request_counts: Dict[str, int] = field(default_factory=dict)
    created_at: str = ""
    ended_at: str = ""
    expires_at: str = ""
    results_url: Optional[str] = None
    raw: Dict[str, Any] = field(default_factory=dict)


@dataclass
class BatchResult:
    """Single per-request result extracted from the JSONL results stream."""

    custom_id: str
    result_type: ResultType
    message: Optional[Dict[str, Any]] = None  # Present when succeeded
    error: Optional[Dict[str, Any]] = None     # Present when errored
    raw: Dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# HTTP client
# ---------------------------------------------------------------------------

DEFAULT_BASE_URL = "https://api.anthropic.com"
ANTHROPIC_VERSION = "2023-06-01"


class BatchClient:
    """Asynchronous bulk processing via the Anthropic Message Batches API.

    Communicates directly over HTTP — no SDK dependency.  Designed for
    protocol-level education: every method maps 1:1 to a documented endpoint.

    Usage::

        client = BatchClient(api_key="sk-ant-...")
        batch_id = client.create_batch([
            MessageRequest(custom_id="q1", params={...}),
            MessageRequest(custom_id="q2", params={...}),
        ])
        results = client.wait_for_completion(batch_id)

    Reference endpoints
    -------------------
    =======  =====================================================
    Method    Endpoint
    =======  =====================================================
    POST      /v1/messages/batches
    GET       /v1/messages/batches/{message_batch_id}
    GET       /v1/messages/batches/{message_batch_id}/results
    POST      /v1/messages/batches/{message_batch_id}/cancel
    GET       /v1/messages/batches
    =======  =====================================================
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: str = DEFAULT_BASE_URL,
    ) -> None:
        self._api_key = api_key or os.environ.get("ANTHROPIC_API_KEY", "")
        self._base_url = base_url.rstrip("/")
        self._client = httpx.Client(
            base_url=self._base_url,
            headers={
                "x-api-key": self._api_key,
                "anthropic-version": ANTHROPIC_VERSION,
                "content-type": "application/json",
            },
            timeout=httpx.Timeout(120.0),
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def create_batch(self, requests: List[MessageRequest]) -> str:
        """Create a new Message Batch and return its ``batch_id``.

        The batch starts in ``in_progress``.  Requests are processed
        asynchronously and independently — one failure does not affect others.
        """
        body = {
            "requests": [
                {"custom_id": r.custom_id, "params": r.params} for r in requests
            ]
        }
        resp = self._client.post("/v1/messages/batches", json=body)
        resp.raise_for_status()
        data = resp.json()
        return data["id"]

    def get_batch_status(self, batch_id: str) -> BatchInfo:
        """Retrieve the current state of a Message Batch."""
        resp = self._client.get(f"/v1/messages/batches/{batch_id}")
        resp.raise_for_status()
        data = resp.json()
        return BatchInfo(
            id=data["id"],
            processing_status=BatchProcessingStatus(data["processing_status"]),
            request_counts=data.get("request_counts", {}),
            created_at=data.get("created_at", ""),
            ended_at=data.get("ended_at", ""),
            expires_at=data.get("expires_at", ""),
            results_url=data.get("results_url"),
            raw=data,
        )

    def get_batch_results(self, batch_id: str) -> List[BatchResult]:
        """Download and parse a completed batch's JSONL results.

        Each line of the response is a JSON object representing one request's
        outcome.  The ``custom_id`` field allows you to correlate results
        back to the original requests.
        """
        resp = self._client.get(
            f"/v1/messages/batches/{batch_id}/results",
        )
        resp.raise_for_status()
        return [self._parse_result_line(line) for line in resp.text.strip().splitlines() if line.strip()]

    def cancel_batch(self, batch_id: str) -> BatchInfo:
        """Cancel an in-progress batch.

        Already-processed requests retain their outcomes; pending requests
        are marked ``canceled`` and you are not billed for them.
        """
        resp = self._client.post(
            f"/v1/messages/batches/{batch_id}/cancel",
        )
        resp.raise_for_status()
        data = resp.json()
        return BatchInfo(
            id=data["id"],
            processing_status=BatchProcessingStatus(data["processing_status"]),
            request_counts=data.get("request_counts", {}),
            created_at=data.get("created_at", ""),
            ended_at=data.get("ended_at", ""),
            expires_at=data.get("expires_at", ""),
            results_url=data.get("results_url"),
            raw=data,
        )

    def list_batches(self, limit: int = 20, after_id: Optional[str] = None) -> List[BatchInfo]:
        """List all batches in the workspace, newest first.

        Args:
            limit: Max batches to return (default 20, max 100).
            after_id: Cursor — return batches after this ID.
        """
        params: Dict[str, Any] = {"limit": limit}
        if after_id:
            params["after_id"] = after_id
        resp = self._client.get("/v1/messages/batches", params=params)
        resp.raise_for_status()
        data = resp.json()
        return [
            BatchInfo(
                id=b["id"],
                processing_status=BatchProcessingStatus(b["processing_status"]),
                request_counts=b.get("request_counts", {}),
                created_at=b.get("created_at", ""),
                ended_at=b.get("ended_at", ""),
                expires_at=b.get("expires_at", ""),
                results_url=b.get("results_url"),
                raw=b,
            )
            for b in data.get("data", [])
        ]

    def wait_for_completion(
        self,
        batch_id: str,
        poll_interval: int = 60,
        max_wait: int = 86400,
    ) -> List[BatchResult]:
        """Block until the batch finishes, then return results.

        Args:
            batch_id: The batch to wait for.
            poll_interval: Seconds between status checks (default 60).
            max_wait: Maximum total wait in seconds (default 86 400 = 24h).

        Returns:
            Parsed per-request results.

        Raises:
            TimeoutError: If the batch does not finish within ``max_wait``.
            RuntimeError: If the batch expires or is canceled.
        """
        deadline = time.monotonic() + max_wait
        terminal = {
            BatchProcessingStatus.ENDED,
            BatchProcessingStatus.CANCELED,
            BatchProcessingStatus.EXPIRED,
        }

        while time.monotonic() < deadline:
            info = self.get_batch_status(batch_id)
            if info.processing_status in terminal:
                break
            time.sleep(poll_interval)
        else:
            raise TimeoutError(
                f"Batch {batch_id} did not complete within {max_wait}s"
            )

        if info.processing_status == BatchProcessingStatus.ENDED:
            return self.get_batch_results(batch_id)

        if info.processing_status == BatchProcessingStatus.EXPIRED:
            raise RuntimeError(
                f"Batch {batch_id} expired (24h SLA exceeded)"
            )

        if info.processing_status == BatchProcessingStatus.CANCELED:
            raise RuntimeError(
                f"Batch {batch_id} was canceled"
            )

        return []  # unreachable

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_result_line(line: str) -> BatchResult:
        data = json.loads(line)
        custom_id = data.get("custom_id", "")
        result = data.get("result", {})

        result_type_str = result.get("type", "")

        try:
            result_type = ResultType(result_type_str)
        except ValueError:
            result_type = ResultType.ERRORED

        return BatchResult(
            custom_id=custom_id,
            result_type=result_type,
            message=result.get("message") if result_type == ResultType.SUCCEEDED else None,
            error=result.get("error") if result_type == ResultType.ERRORED else None,
            raw=data,
        )

    # ------------------------------------------------------------------
    # Batch + Cache combo helpers
    # ------------------------------------------------------------------

    @staticmethod
    def make_cacheable_request(
        custom_id: str,
        model: str,
        max_tokens: int,
        user_message: str,
        system_prompt: str = "",
        cache_ttl: Optional[int] = None,  # seconds; None → 5-min default
    ) -> MessageRequest:
        """Factory for a request with prompt-caching enabled.

        When used inside a batch, the batch processing engine attempts to
        re-use cached prefixes across requests that share identical content,
        on a best-effort basis.  Cache hit rates typically range from 30-98%
        depending on traffic patterns.

        The 1-hour TTL (``cache_ttl=3600``) is useful when batch requests
        are spread out over a longer window, though note that batch cache
        behaviour is still best-effort.

        Args:
            custom_id: Unique request identifier.
            model: Model ID string.
            max_tokens: Max output tokens.
            user_message: The user's question / prompt.
            system_prompt: Optional system-level instructions (cached).
            cache_ttl: If provided, sets ``ttl`` in ``cache_control`` for
                       a 1-hour cache. Omit for default 5-min ephemeral.
        """
        system: list[dict[str, Any]] = []
        if system_prompt:
            cache_ctl: dict[str, Any] = {"type": "ephemeral"}
            if cache_ttl is not None:
                cache_ctl["ttl"] = cache_ttl
            system.append({
                "type": "text",
                "text": system_prompt,
                "cache_control": cache_ctl,
            })

        params: dict[str, Any] = {
            "model": model,
            "max_tokens": max_tokens,
            "messages": [{"role": "user", "content": user_message}],
        }
        if system:
            params["system"] = system

        return MessageRequest(custom_id=custom_id, params=params)
