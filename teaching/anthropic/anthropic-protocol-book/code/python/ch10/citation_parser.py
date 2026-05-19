"""
Chapter 10: Citation Parser.

Protocol-level implementation of Anthropic's Citations API,
parsing structured citation data from Claude responses and
formatting it into human-readable reference lists.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


# ---------------------------------------------------------------------------
# Citation Types
# ---------------------------------------------------------------------------


class CitationType(str, Enum):
    """Enumeration of all supported citation location types."""

    CHAR_LOCATION = "char_location"
    PAGE_LOCATION = "page_location"
    CONTENT_BLOCK_LOCATION = "content_block_location"
    WEB_SEARCH_RESULT_LOCATION = "web_search_result_location"
    SEARCH_RESULT_LOCATION = "search_result_location"


# ---------------------------------------------------------------------------
# Citation Data Models
# ---------------------------------------------------------------------------


@dataclass
class Citation:
    """Structured representation of a single citation.

    Maps to the Anthropic API citation objects returned in
    ``TextBlock.citations`` or ``content_block_delta.delta.citation``.
    """

    cited_text: str
    document_title: str
    citation_type: CitationType
    document_index: int = 0
    file_id: Optional[str] = None
    # char_location fields
    start_char_index: Optional[int] = None
    end_char_index: Optional[int] = None
    # page_location fields
    start_page_number: Optional[int] = None
    end_page_number: Optional[int] = None
    # content_block_location fields
    start_block_index: Optional[int] = None
    end_block_index: Optional[int] = None
    # web search fields
    url: Optional[str] = None
    # search result fields
    source: Optional[str] = None
    search_result_index: Optional[int] = None

    @property
    def location_summary(self) -> str:
        """Human-readable location description."""
        if self.citation_type == CitationType.CHAR_LOCATION:
            return f"chars {self.start_char_index}-{self.end_char_index}"
        elif self.citation_type == CitationType.PAGE_LOCATION:
            return f"pages {self.start_page_number}-{self.end_page_number}"
        elif self.citation_type == CitationType.CONTENT_BLOCK_LOCATION:
            return f"blocks {self.start_block_index}-{self.end_block_index}"
        elif self.citation_type == CitationType.WEB_SEARCH_RESULT_LOCATION:
            return self.url or "web result"
        elif self.citation_type == CitationType.SEARCH_RESULT_LOCATION:
            return f"result #{self.search_result_index}" if self.search_result_index else "search result"
        return "unknown"

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary matching the API response format."""
        result: Dict[str, Any] = {
            "type": self.citation_type.value,
            "cited_text": self.cited_text,
            "document_title": self.document_title,
            "document_index": self.document_index,
        }
        if self.file_id is not None:
            result["file_id"] = self.file_id
        if self.start_char_index is not None:
            result["start_char_index"] = self.start_char_index
        if self.end_char_index is not None:
            result["end_char_index"] = self.end_char_index
        if self.start_page_number is not None:
            result["start_page_number"] = self.start_page_number
        if self.end_page_number is not None:
            result["end_page_number"] = self.end_page_number
        if self.start_block_index is not None:
            result["start_block_index"] = self.start_block_index
        if self.end_block_index is not None:
            result["end_block_index"] = self.end_block_index
        if self.url is not None:
            result["url"] = self.url
        if self.source is not None:
            result["source"] = self.source
        if self.search_result_index is not None:
            result["search_result_index"] = self.search_result_index
        return result


# ---------------------------------------------------------------------------
# Citation Parser
# ---------------------------------------------------------------------------


class CitationParser:
    """Parses and formats citations from Claude API responses.

    Handles extraction of citations from content blocks, deduplication,
    and formatting for human-readable output (numbered references,
    markdown, plain text).

    Usage::

        parser = CitationParser()
        citations = parser.parse_citations(content_block)
        formatted = parser.format_references(citations)
    """

    def parse_citations(self, content_block: Dict[str, Any]) -> List[Citation]:
        """Extract all citations from a single content block.

        Handles both:
        - Direct ``citations`` array on ``TextBlock`` (non-streaming)
        - ``citations_delta`` within ``content_block_delta`` (streaming)

        Args:
            content_block: A content block dict from the API response or
                a ``content_block_delta`` event.

        Returns:
            List of parsed Citation objects.
        """
        citations: List[Citation] = []

        # Handle content_block_delta (streaming)
        if content_block.get("type") == "content_block_delta":
            delta = content_block.get("delta", {})
            if delta.get("type") == "citations_delta":
                citation_data = delta.get("citation", {})
                parsed = self._parse_single_citation(citation_data)
                if parsed:
                    citations.append(parsed)
            return citations

        # Handle direct citations array (non-streaming TextBlock)
        if "citations" in content_block:
            for citation_data in content_block["citations"]:
                parsed = self._parse_single_citation(citation_data)
                if parsed:
                    citations.append(parsed)

        # Handle content array (nested within messages)
        if "content" in content_block:
            for block in content_block["content"]:
                if isinstance(block, dict) and "citations" in block:
                    for citation_data in block["citations"]:
                        parsed = self._parse_single_citation(citation_data)
                        if parsed:
                            citations.append(parsed)

        return citations

    def parse_response(self, response: Dict[str, Any]) -> List[Citation]:
        """Extract all citations from a full Messages API response.

        Walks the entire response content array and collects citations
        from all text blocks.

        Args:
            response: The full response dict from ``client.messages.create()``.

        Returns:
            All citations found in the response.
        """
        all_citations: List[Citation] = []
        content = response.get("content", [])
        for block in content:
            all_citations.extend(self.parse_citations(block))
        return all_citations

    def _parse_single_citation(self, data: Dict[str, Any]) -> Optional[Citation]:
        """Parse a single citation dict into a Citation object."""
        if not data or not isinstance(data, dict):
            return None

        citation_type_str = data.get("type", "")
        try:
            citation_type = CitationType(citation_type_str)
        except ValueError:
            return None  # Unknown citation type

        return Citation(
            cited_text=data.get("cited_text", ""),
            document_title=data.get("document_title", ""),
            citation_type=citation_type,
            document_index=data.get("document_index", 0),
            file_id=data.get("file_id"),
            start_char_index=data.get("start_char_index"),
            end_char_index=data.get("end_char_index"),
            start_page_number=data.get("start_page_number"),
            end_page_number=data.get("end_page_number"),
            start_block_index=data.get("start_block_index"),
            end_block_index=data.get("end_block_index"),
            url=data.get("url"),
            source=data.get("source"),
            search_result_index=data.get("search_result_index"),
        )

    # ------------------------------------------------------------------
    # Formatting
    # ------------------------------------------------------------------

    def format_citation(self, citation: Citation, index: int) -> str:
        """Format a single citation as a numbered reference line.

        Args:
            citation: The citation to format.
            index: The reference number (1-indexed).

        Returns:
            Formatted string like ``[1] "cited text..." found in "Document Title" (pages 1-2)``
        """
        cited = citation.cited_text.replace("\n", " ").replace("\r", " ")
        cited = " ".join(cited.split())  # normalize whitespace
        location = citation.location_summary
        return f'[{index}] "{cited}" found in "{citation.document_title}" ({location})'

    def format_references(self, citations: List[Citation]) -> str:
        """Format all citations as a numbered reference list.

        Deduplicates citations by (document_title, cited_text) key.
        Returns a string with numbered reference lines, one per unique citation.

        Args:
            citations: List of citations (may contain duplicates).

        Returns:
            Multi-line reference list string.
        """
        deduped = self._deduplicate(citations)
        lines: List[str] = []
        for i, citation in enumerate(deduped, start=1):
            lines.append(self.format_citation(citation, i))
        return "\n".join(lines)

    def annotate_text(
        self,
        text: str,
        citations: List[Citation],
        style: str = "numbered",
    ) -> str:
        """Annotate text with citation markers.

        Args:
            text: The plain text from Claude's response.
            citations: Citations associated with this text.
            style: ``"numbered"`` for [1][2] markers, ``"inline"`` for inline notes.

        Returns:
            Annotated text string.
        """
        deduped = self._deduplicate(citations)

        if not deduped:
            return text

        if style == "numbered":
            markers = "".join(f" [{i}]" for i in range(1, len(deduped) + 1))
            return text + markers
        elif style == "inline":
            notes = []
            for i, c in enumerate(deduped, start=1):
                notes.append(f"  [{i}] Source: {c.document_title}")
            return text + "\n" + "\n".join(notes)
        else:
            return text

    def format_as_markdown(self, citations: List[Citation]) -> str:
        """Format citations as a Markdown reference section.

        Args:
            citations: List of citations.

        Returns:
            Markdown-formatted string with a "References" heading.
        """
        deduped = self._deduplicate(citations)
        lines = ["### References", ""]
        for i, citation in enumerate(deduped, start=1):
            cited = citation.cited_text.replace("\n", " ").replace("\r", " ")
            cited = " ".join(cited.split())
            lines.append(
                f"{i}. **{citation.document_title}** ({citation.location_summary}): "
                f'"{cited}"'
            )
        return "\n".join(lines)

    # ------------------------------------------------------------------
    # Deduplication
    # ------------------------------------------------------------------

    def _deduplicate(self, citations: List[Citation]) -> List[Citation]:
        """Remove duplicate citations, keeping first occurrence.

        Duplicates are identified by (document_title, cited_text).
        """
        seen: set = set()
        result: List[Citation] = []
        for c in citations:
            key = (c.document_title, c.cited_text.strip())
            if key not in seen:
                seen.add(key)
                result.append(c)
        return result

    def deduplicate(self, citations: List[Citation]) -> List[Citation]:
        """Public deduplication method (same as internal).

        Returns deduplicated list preserving first-occurrence order.
        """
        return self._deduplicate(citations)

    # ------------------------------------------------------------------
    # Verification
    # ------------------------------------------------------------------

    def verify_citation(
        self,
        citation: Citation,
        source_text: str,
    ) -> bool:
        """Verify that a citation's cited_text exists within the source.

        Args:
            citation: The citation to verify.
            source_text: The original source document text.

        Returns:
            True if cited_text is found in source_text.
        """
        cited = citation.cited_text.strip()
        # Normalize for comparison
        cited_norm = " ".join(cited.split())
        source_norm = " ".join(source_text.split())
        return cited_norm in source_norm

    def verify_all(
        self,
        citations: List[Citation],
        sources: Dict[str, str],
    ) -> Dict[str, bool]:
        """Verify all citations against their source documents.

        Args:
            citations: List of citations to verify.
            sources: Map of document_title -> full source text.

        Returns:
            Dict mapping citation key to verification result.
        """
        results: Dict[str, bool] = {}
        for i, c in enumerate(citations):
            key = f"[{i + 1}] {c.document_title}"
            source = sources.get(c.document_title, "")
            results[key] = self.verify_citation(c, source)
        return results

    # ------------------------------------------------------------------
    # Summary / Statistics
    # ------------------------------------------------------------------

    def summarize(self, citations: List[Citation]) -> Dict[str, Any]:
        """Generate summary statistics for a set of citations.

        Returns:
            Dict with counts by type, unique documents, and total count.
        """
        types: Dict[str, int] = {}
        documents: set = set()
        for c in citations:
            types[c.citation_type.value] = types.get(c.citation_type.value, 0) + 1
            if c.document_title:
                documents.add(c.document_title)

        return {
            "total_citations": len(citations),
            "unique_citations": len(self._deduplicate(citations)),
            "unique_documents": len(documents),
            "by_type": types,
            "documents": sorted(documents),
        }
