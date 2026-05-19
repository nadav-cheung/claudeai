"""
Chapter 8: Compaction Handler.

Implements context compaction (auto-summarization) for long-running
Claude conversations. When the context window approaches capacity, the
handler replaces early conversation history with a structured summary
to free token space for new interactions.

Core strategies:
  1. Summarization: Replace early messages with a structured summary
     preserving task goals, key decisions, current state, and pending items.
  2. Truncation: Simply drop early messages (fallback, cached-cold path).

Uses the Anthropic-defined compaction thresholds (75-92% context usage).
"""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Context usage thresholds (fraction of max window)
DEFAULT_COMPACT_THRESHOLD = 0.80   # 80% - trigger compaction
MIN_COMPACT_THRESHOLD = 0.75       # 75% - minimum before compaction
MAX_COMPACT_THRESHOLD = 0.92       # 92% - maximum safe threshold

# How many of the most recent messages to always preserve
DEFAULT_PRESERVE_RECENT = 4

# Minimum number of messages before compaction is worthwhile
MIN_MESSAGES_FOR_COMPACTION = 6

# Time threshold for cache-cold detection (seconds)
CACHE_COLD_THRESHOLD_SECONDS = 300  # 5 minutes


class CompactionStrategy(Enum):
    """Available compaction strategies."""

    SUMMARIZE = "summarize"    # Replace early messages with LLM-generated summary
    TRUNCATE = "truncate"      # Simply drop early messages


@dataclass
class CompactionResult:
    """Result of a compaction operation."""

    compacted_messages: List[Dict[str, Any]]
    tokens_before: int
    tokens_after: int
    strategy: CompactionStrategy
    summary: Optional[str] = None
    messages_removed: int = 0
    cache_safe: bool = True  # Whether cache_edits was used (True) or direct edit (False)

    @property
    def tokens_saved(self) -> int:
        return self.tokens_before - self.tokens_after

    @property
    def savings_pct(self) -> float:
        if self.tokens_before == 0:
            return 0.0
        return round(self.tokens_saved / self.tokens_before * 100, 1)


@dataclass
class CompactionSnapshot:
    """A checkpoint of compaction state for rollback."""

    messages: List[Dict[str, Any]]
    timestamp: float = field(default_factory=time.time)
    checksum: str = ""


class CompactionHandler:
    """Manages context compaction for long-running Claude conversations.

    Handles:
      - Monitoring context usage and triggering compaction when thresholds met
      - Generating structured summaries of early conversation history
      - Deciding between cache-safe (via cache_edits) and direct compaction
      - Maintaining snapshots for potential rollback

    Usage::

        handler = CompactionHandler(
            threshold=0.80,
            preserve_recent=4,
        )
        if handler.should_compact(current_tokens, max_tokens):
            result = handler.compact(messages, context_window=200000)
            messages = result.compacted_messages
    """

    def __init__(
        self,
        threshold: float = DEFAULT_COMPACT_THRESHOLD,
        preserve_recent: int = DEFAULT_PRESERVE_RECENT,
        strategy: CompactionStrategy = CompactionStrategy.SUMMARIZE,
        model_context_window: int = 200000,
    ) -> None:
        """Initialize the compaction handler.

        Args:
            threshold: Context usage fraction (0.0-1.0) at which to compact.
            preserve_recent: Number of most recent messages to keep intact.
            strategy: Default compaction strategy.
            model_context_window: Maximum context window size for the model.

        Raises:
            ValueError: If threshold is outside valid range.
        """
        if not MIN_COMPACT_THRESHOLD <= threshold <= MAX_COMPACT_THRESHOLD:
            raise ValueError(
                f"threshold must be between {MIN_COMPACT_THRESHOLD} and "
                f"{MAX_COMPACT_THRESHOLD}, got {threshold}"
            )
        if preserve_recent < 1:
            raise ValueError("preserve_recent must be at least 1")

        self.threshold = threshold
        self.preserve_recent = preserve_recent
        self.default_strategy = strategy
        self.model_context_window = model_context_window

        self._last_api_response_time: Optional[float] = None
        self._snapshots: List[CompactionSnapshot] = []
        self._summary_cache: Dict[str, str] = {}

    # ------------------------------------------------------------------
    # Should-compact decision
    # ------------------------------------------------------------------

    def should_compact(
        self,
        current_tokens: int,
        max_tokens: Optional[int] = None,
        message_count: Optional[int] = None,
    ) -> bool:
        """Determine whether compaction should be triggered.

        Args:
            current_tokens: Current estimated token count in context.
            max_tokens: Maximum context window size (defaults to model_context_window).
            message_count: Current number of messages in the conversation.

        Returns:
            True if compaction should be triggered.
        """
        window = max_tokens or self.model_context_window
        if window <= 0:
            return False

        usage_pct = current_tokens / window
        if usage_pct < self.threshold:
            return False

        if message_count is not None and message_count < MIN_MESSAGES_FOR_COMPACTION:
            return False

        return True

    def should_compact_by_usage(self, context_usage_pct: float) -> bool:
        """Simple check: should we compact based on context usage percentage?

        Args:
            context_usage_pct: Context usage as a percentage (0.0-100.0 or 0.0-1.0).

        Returns:
            True if compaction should be triggered.
        """
        # Normalize to 0.0-1.0 range
        if context_usage_pct > 1.0:
            context_usage_pct = context_usage_pct / 100.0
        return context_usage_pct >= self.threshold

    # ------------------------------------------------------------------
    # Compaction execution
    # ------------------------------------------------------------------

    def compact(
        self,
        messages: List[Dict[str, Any]],
        context_window: Optional[int] = None,
        strategy: Optional[CompactionStrategy] = None,
        summary_fn: Optional[callable] = None,
    ) -> CompactionResult:
        """Compact message history.

        Args:
            messages: Full message list (role/content format).
            context_window: Max context window for the model.
            strategy: Override default strategy.
            summary_fn: Optional custom summary generator. If not provided,
                        uses the _generate_summary method (which calls an LLM).
                        Signature: (messages_to_summarize) -> str

        Returns:
            CompactionResult with compacted messages and statistics.
        """
        strategy = strategy or self.default_strategy
        window = context_window or self.model_context_window

        if len(messages) <= self.preserve_recent:
            return CompactionResult(
                compacted_messages=list(messages),
                tokens_before=0,
                tokens_after=0,
                strategy=strategy,
            )

        # Estimate tokens before
        tokens_before = self._estimate_tokens(messages)

        # Split: early messages (to compact) + recent messages (to preserve)
        split_idx = max(0, len(messages) - self.preserve_recent)
        early_messages = list(messages[:split_idx])
        recent_messages = list(messages[split_idx:])

        if not early_messages:
            return CompactionResult(
                compacted_messages=recent_messages,
                tokens_before=tokens_before,
                tokens_after=self._estimate_tokens(recent_messages),
                strategy=strategy,
                messages_removed=0,
            )

        # Save snapshot before compaction
        self._create_snapshot(messages)

        is_cache_cold = self._is_cache_cold()

        if strategy == CompactionStrategy.SUMMARIZE:
            # Generate summary
            if summary_fn:
                summary = summary_fn(early_messages)
            else:
                summary = self._generate_summary(early_messages)

            # Prepend summary as a synthetic system message
            summary_msg = {
                "role": "user",
                "content": f"<conversation_summary>\n{summary}\n</conversation_summary>",
            }

            compacted = [summary_msg] + recent_messages

            # When cache is hot, we would use cache_edits in production
            # Here we note whether the approach was cache-safe
            cache_safe = not is_cache_cold

        else:  # TRUNCATE
            compacted = recent_messages
            summary = None
            cache_safe = False  # truncation always changes prefix bytes

        tokens_after = self._estimate_tokens(compacted)

        return CompactionResult(
            compacted_messages=compacted,
            tokens_before=tokens_before,
            tokens_after=tokens_after,
            strategy=strategy,
            summary=summary,
            messages_removed=len(early_messages),
            cache_safe=cache_safe,
        )

    # ------------------------------------------------------------------
    # Summary generation
    # ------------------------------------------------------------------

    def _generate_summary(
        self,
        messages: List[Dict[str, Any]],
    ) -> str:
        """Generate a structured summary of the conversation history.

        In production, this would call an LLM to produce the summary.
        This implementation produces a structural template; integrate
        with your actual LLM call.

        The summary format follows Claude Code conventions:
          - Task Goal: what the user wants to accomplish
          - Key Decisions: decisions made and their rationale
          - Current State: what's been done, file state, test status
          - Pending Items: what's left to do
        """
        # Extract key information from messages
        user_messages = [
            m for m in messages
            if m.get("role") == "user"
        ]
        assistant_messages = [
            m for m in messages
            if m.get("role") == "assistant"
        ]

        # Build structured summary
        parts = ["## Conversation Summary"]

        # Task goals from user messages
        if user_messages:
            parts.append("### Task Goal")
            for i, msg in enumerate(user_messages[:5]):
                content = self._extract_text(msg.get("content", ""))
                if content:
                    parts.append(f"- {content[:200]}")

        # Key decisions from assistant responses
        if assistant_messages:
            parts.append("### Key Actions")
            for i, msg in enumerate(assistant_messages[-5:]):
                content = self._extract_text(msg.get("content", ""))
                if content:
                    parts.append(f"- {content[:200]}")

        # Summary statistics
        parts.append(f"### Stats")
        parts.append(f"- User messages summarized: {len(user_messages)}")
        parts.append(f"- Assistant messages summarized: {len(assistant_messages)}")
        parts.append(f"- Total messages compacted: {len(messages)}")

        return "\n".join(parts)

    @staticmethod
    def _extract_text(content: Any) -> str:
        """Extract text content from a message content field."""
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            texts = []
            for block in content:
                if isinstance(block, dict):
                    if block.get("type") == "text":
                        texts.append(str(block.get("text", "")))
                    elif block.get("type") == "tool_result":
                        texts.append("[tool result]")
            return " ".join(texts)
        return str(content)

    # ------------------------------------------------------------------
    # Token estimation
    # ------------------------------------------------------------------

    @staticmethod
    def _estimate_tokens(messages: List[Dict[str, Any]]) -> int:
        """Rough token count estimation (4 chars ≈ 1 token for English).

        For production use, replace with tiktoken or Anthropic's tokenizer.
        """
        total_chars = 0
        for msg in messages:
            content = msg.get("content", "")
            if isinstance(content, str):
                total_chars += len(content)
            elif isinstance(content, list):
                for block in content:
                    if isinstance(block, dict):
                        text = block.get("text", "")
                        if isinstance(text, str):
                            total_chars += len(text)
            # Account for role metadata overhead
            total_chars += 50

        return max(1, total_chars // 4)

    # ------------------------------------------------------------------
    # Cache state tracking
    # ------------------------------------------------------------------

    def mark_api_response(self) -> None:
        """Record the time of the last API response for cache-cold detection."""
        self._last_api_response_time = time.time()

    def _is_cache_cold(self) -> bool:
        """Check if the prompt cache has likely expired."""
        if self._last_api_response_time is None:
            return True
        elapsed = time.time() - self._last_api_response_time
        return elapsed > CACHE_COLD_THRESHOLD_SECONDS

    # ------------------------------------------------------------------
    # Snapshots for rollback
    # ------------------------------------------------------------------

    def _create_snapshot(self, messages: List[Dict[str, Any]]) -> None:
        """Create a snapshot of current messages for potential rollback."""
        serialized = str(messages).encode("utf-8")
        checksum = hashlib.sha256(serialized).hexdigest()[:16]
        snapshot = CompactionSnapshot(
            messages=list(messages),
            checksum=checksum,
        )
        self._snapshots.append(snapshot)
        # Keep only the last 5 snapshots
        if len(self._snapshots) > 5:
            self._snapshots = self._snapshots[-5:]

    def rollback(self) -> Optional[List[Dict[str, Any]]]:
        """Roll back to the most recent pre-compaction snapshot.

        Returns:
            The previous message list, or None if no snapshots exist.
        """
        if not self._snapshots:
            return None
        snapshot = self._snapshots.pop()
        return snapshot.messages

    # ------------------------------------------------------------------
    # Cache-aware compaction (Cached MC pattern)
    # ------------------------------------------------------------------

    def create_cache_edits(
        self,
        messages: List[Dict[str, Any]],
        tool_ids_to_delete: List[str],
    ) -> Dict[str, Any]:
        """Create cache_edits block for cache-safe compaction.

        In production with Cached Microcompact, this tells the server to
        delete specific tool_result contents from the KV cache without
        modifying the message bytes (preserving cache prefix integrity).

        Args:
            messages: Current message list.
            tool_ids_to_delete: List of tool_use_id values to delete from cache.

        Returns:
            A dict with cache_edits and cache_reference annotations.
        """
        edits = [{"delete": tid} for tid in tool_ids_to_delete]

        # Annotate messages with cache_reference for each tool_result
        annotated = []
        for msg in messages:
            msg_copy = dict(msg)
            content = msg_copy.get("content")
            if isinstance(content, list):
                new_content = []
                for block in content:
                    block_copy = dict(block)
                    if block_copy.get("type") == "tool_result":
                        tool_id = block_copy.get("tool_use_id")
                        if tool_id and tool_id in tool_ids_to_delete:
                            block_copy["cache_reference"] = tool_id
                    new_content.append(block_copy)
                msg_copy["content"] = new_content
            annotated.append(msg_copy)

        return {
            "messages": annotated,
            "cache_edits": {"type": "cache_edits", "edits": edits},
        }

    # ------------------------------------------------------------------
    # Threshold tuning
    # ------------------------------------------------------------------

    @classmethod
    def for_short_conversation(cls) -> "CompactionHandler":
        """Factory: handler tuned for short conversations (< 10 turns)."""
        return cls(threshold=0.90, preserve_recent=8)

    @classmethod
    def for_medium_conversation(cls) -> "CompactionHandler":
        """Factory: handler tuned for medium conversations (10-30 turns)."""
        return cls(threshold=0.85, preserve_recent=6)

    @classmethod
    def for_long_conversation(cls) -> "CompactionHandler":
        """Factory: handler tuned for long conversations (> 30 turns)."""
        return cls(threshold=0.75, preserve_recent=4)
