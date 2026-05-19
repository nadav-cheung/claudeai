"""
Tests for Chapter 8: Compaction Handler.
"""

import pytest

from compaction_handler import (
    CACHE_COLD_THRESHOLD_SECONDS,
    DEFAULT_COMPACT_THRESHOLD,
    MAX_COMPACT_THRESHOLD,
    MIN_COMPACT_THRESHOLD,
    MIN_MESSAGES_FOR_COMPACTION,
    CompactionHandler,
    CompactionResult,
    CompactionStrategy,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def handler() -> CompactionHandler:
    return CompactionHandler(threshold=0.80, preserve_recent=4)


@pytest.fixture
def long_conversation() -> list:
    """15-message conversation: 7 user/assistant pairs + initial user."""
    msgs = []
    for i in range(15):
        role = "user" if i % 2 == 0 else "assistant"
        msgs.append({
            "role": role,
            "content": f"Message {i}: This is {'a question' if role == 'user' else 'an answer'} about topic {i // 2}.",
        })
    return msgs


@pytest.fixture
def short_conversation() -> list:
    """3-message conversation: too short for compaction."""
    return [
        {"role": "user", "content": "Hi"},
        {"role": "assistant", "content": "Hello!"},
        {"role": "user", "content": "How are you?"},
    ]


# ---------------------------------------------------------------------------
# Initialization tests
# ---------------------------------------------------------------------------


class TestInitialization:
    def test_default_threshold(self) -> None:
        handler = CompactionHandler()
        assert handler.threshold == DEFAULT_COMPACT_THRESHOLD

    def test_custom_threshold(self) -> None:
        handler = CompactionHandler(threshold=0.85)
        assert handler.threshold == 0.85

    def test_threshold_below_min_raises(self) -> None:
        with pytest.raises(ValueError, match="threshold must be"):
            CompactionHandler(threshold=0.50)

    def test_threshold_above_max_raises(self) -> None:
        with pytest.raises(ValueError, match="threshold must be"):
            CompactionHandler(threshold=0.99)

    def test_preserve_recent_zero_raises(self) -> None:
        with pytest.raises(ValueError, match="preserve_recent"):
            CompactionHandler(preserve_recent=0)


# ---------------------------------------------------------------------------
# Should-compact tests
# ---------------------------------------------------------------------------


class TestShouldCompact:
    def test_below_threshold(self, handler: CompactionHandler) -> None:
        assert not handler.should_compact(current_tokens=100000, max_tokens=200000)

    def test_above_threshold(self, handler: CompactionHandler) -> None:
        assert handler.should_compact(current_tokens=180000, max_tokens=200000)

    def test_too_few_messages(self, handler: CompactionHandler) -> None:
        assert not handler.should_compact(
            current_tokens=180000,
            max_tokens=200000,
            message_count=3,
        )

    def test_should_compact_by_usage_pct_fraction(self, handler: CompactionHandler) -> None:
        assert not handler.should_compact_by_usage(0.70)
        assert handler.should_compact_by_usage(0.85)

    def test_should_compact_by_usage_pct_integer(self, handler: CompactionHandler) -> None:
        """context_usage_pct as percentage (85 = 85%)."""
        assert not handler.should_compact_by_usage(70.0)
        assert handler.should_compact_by_usage(85.0)


# ---------------------------------------------------------------------------
# Compaction execution tests
# ---------------------------------------------------------------------------


class TestCompaction:
    def test_compact_reduces_message_count(
        self, handler: CompactionHandler, long_conversation: list
    ) -> None:
        result = handler.compact(long_conversation, context_window=200000)
        # Should have summary + preserve_recent messages
        assert len(result.compacted_messages) < len(long_conversation)
        assert result.messages_removed > 0

    def test_compact_preserves_recent(
        self, handler: CompactionHandler, long_conversation: list
    ) -> None:
        result = handler.compact(long_conversation, context_window=200000)
        preserved = result.compacted_messages[-handler.preserve_recent:]
        expected = long_conversation[-handler.preserve_recent:]
        assert preserved == expected

    def test_compact_too_few_messages_noop(
        self, handler: CompactionHandler, short_conversation: list
    ) -> None:
        result = handler.compact(short_conversation, context_window=200000)
        assert result.messages_removed == 0
        assert result.compacted_messages == short_conversation

    def test_compact_with_summarize_strategy(
        self, handler: CompactionHandler, long_conversation: list
    ) -> None:
        result = handler.compact(
            long_conversation,
            context_window=200000,
            strategy=CompactionStrategy.SUMMARIZE,
        )
        assert result.strategy == CompactionStrategy.SUMMARIZE
        assert result.summary is not None
        assert "Conversation Summary" in result.summary

    def test_compact_with_truncate_strategy(
        self, handler: CompactionHandler, long_conversation: list
    ) -> None:
        result = handler.compact(
            long_conversation,
            context_window=200000,
            strategy=CompactionStrategy.TRUNCATE,
        )
        assert result.strategy == CompactionStrategy.TRUNCATE
        assert result.summary is None

    def test_compact_with_custom_summary_fn(
        self, handler: CompactionHandler, long_conversation: list
    ) -> None:
        custom_summary = "CUSTOM: All tasks completed."

        def custom_fn(messages):
            return custom_summary

        result = handler.compact(
            long_conversation,
            context_window=200000,
            summary_fn=custom_fn,
        )
        assert result.summary == custom_summary

    def test_tokens_saved_positive(
        self, handler: CompactionHandler, long_conversation: list
    ) -> None:
        result = handler.compact(long_conversation, context_window=200000)
        assert result.tokens_saved > 0
        assert result.savings_pct > 0


# ---------------------------------------------------------------------------
# CompactionResult tests
# ---------------------------------------------------------------------------


class TestCompactionResult:
    def test_basic_result(self) -> None:
        result = CompactionResult(
            compacted_messages=[{"role": "user", "content": "hi"}],
            tokens_before=1000,
            tokens_after=300,
            strategy=CompactionStrategy.SUMMARIZE,
            summary="Test summary",
            messages_removed=5,
        )
        assert result.tokens_saved == 700
        assert result.savings_pct == 70.0
        assert result.cache_safe is True

    def test_zero_tokens_before(self) -> None:
        result = CompactionResult(
            compacted_messages=[],
            tokens_before=0,
            tokens_after=0,
            strategy=CompactionStrategy.TRUNCATE,
        )
        assert result.savings_pct == 0.0


# ---------------------------------------------------------------------------
# Snapshot and rollback tests
# ---------------------------------------------------------------------------


class TestSnapshots:
    def test_rollback_restores_state(
        self, handler: CompactionHandler, long_conversation: list
    ) -> None:
        result = handler.compact(long_conversation, context_window=200000)
        assert len(result.compacted_messages) < len(long_conversation)

        restored = handler.rollback()
        assert restored is not None
        assert len(restored) == len(long_conversation)

    def test_rollback_empty(self, handler: CompactionHandler) -> None:
        assert handler.rollback() is None

    def test_max_5_snapshots(
        self, handler: CompactionHandler, long_conversation: list
    ) -> None:
        for _ in range(10):
            handler.compact(long_conversation, context_window=200000)
        # Should only have 5 snapshots (the limit)
        snapshots_restored = 0
        while handler.rollback() is not None:
            snapshots_restored += 1
        assert snapshots_restored <= 5

    def test_consecutive_compaction_and_rollback(
        self, handler: CompactionHandler, long_conversation: list
    ) -> None:
        result1 = handler.compact(long_conversation, context_window=200000)
        compacted1 = result1.compacted_messages

        # Compact again
        result2 = handler.compact(compacted1, context_window=200000)

        # Rollback once
        restored = handler.rollback()
        assert restored == compacted1


# ---------------------------------------------------------------------------
# Cache-aware features
# ---------------------------------------------------------------------------


class TestCacheFeatures:
    def test_mark_api_response(self, handler: CompactionHandler) -> None:
        handler.mark_api_response()
        assert handler._last_api_response_time is not None

    def test_cache_cold_detection(self, handler: CompactionHandler) -> None:
        # No response recorded yet -> cache is cold
        assert handler._is_cache_cold() is True

        # Mark recent response -> cache is warm
        handler.mark_api_response()
        assert handler._is_cache_cold() is False

    def test_create_cache_edits(self, handler: CompactionHandler) -> None:
        messages = [
            {
                "role": "user",
                "content": [
                    {"type": "tool_result", "tool_use_id": "tool_001", "content": "result 1"},
                    {"type": "tool_result", "tool_use_id": "tool_002", "content": "result 2"},
                ],
            },
        ]
        result = handler.create_cache_edits(
            messages,
            tool_ids_to_delete=["tool_001"],
        )

        # Should have cache_edits block
        assert "cache_edits" in result
        assert result["cache_edits"]["type"] == "cache_edits"
        assert len(result["cache_edits"]["edits"]) == 1
        assert result["cache_edits"]["edits"][0] == {"delete": "tool_001"}

    def test_create_cache_edits_empty(self, handler: CompactionHandler) -> None:
        result = handler.create_cache_edits([], tool_ids_to_delete=[])
        assert result["cache_edits"]["edits"] == []

    def test_create_cache_edits_adds_reference(self, handler: CompactionHandler) -> None:
        messages = [
            {
                "role": "user",
                "content": [
                    {"type": "tool_result", "tool_use_id": "tool_abc", "content": "data"},
                ],
            },
        ]
        result = handler.create_cache_edits(
            messages,
            tool_ids_to_delete=["tool_abc"],
        )
        annotated = result["messages"][0]["content"]
        assert annotated[0]["cache_reference"] == "tool_abc"


# ---------------------------------------------------------------------------
# Factory methods
# ---------------------------------------------------------------------------


class TestFactories:
    def test_short_conversation_handler(self) -> None:
        h = CompactionHandler.for_short_conversation()
        assert h.threshold == 0.90
        assert h.preserve_recent == 8

    def test_medium_conversation_handler(self) -> None:
        h = CompactionHandler.for_medium_conversation()
        assert h.threshold == 0.85
        assert h.preserve_recent == 6

    def test_long_conversation_handler(self) -> None:
        h = CompactionHandler.for_long_conversation()
        assert h.threshold == 0.75
        assert h.preserve_recent == 4
