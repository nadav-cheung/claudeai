"""
Tests for Chapter 10: Citation Parser.
"""

import pytest

from citation_parser import (
    CitationParser,
    Citation,
    CitationType,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def parser() -> CitationParser:
    return CitationParser()


@pytest.fixture
def sample_citations() -> list[Citation]:
    return [
        Citation(
            cited_text="Once your order ships, you'll receive an email with a tracking number.",
            document_title="Order Tracking Information",
            citation_type=CitationType.CHAR_LOCATION,
            document_index=0,
            start_char_index=0,
            end_char_index=75,
        ),
        Citation(
            cited_text="If you haven't received a tracking number within 48 hours, please contact support.",
            document_title="Order Tracking Information",
            citation_type=CitationType.CHAR_LOCATION,
            document_index=0,
            start_char_index=76,
            end_char_index=160,
        ),
        Citation(
            cited_text="We experiment with methods for training a harmless AI assistant.",
            document_title="Constitutional AI Paper",
            citation_type=CitationType.PAGE_LOCATION,
            document_index=0,
            start_page_number=1,
            end_page_number=2,
        ),
    ]


@pytest.fixture
def char_location_block() -> dict:
    """Simulates a non-streaming TextBlock with char_location citations."""
    return {
        "type": "text",
        "text": "You'll receive an email with your tracking number once your order ships.",
        "citations": [
            {
                "type": "char_location",
                "cited_text": "Once your order ships, you'll receive an email.",
                "document_index": 0,
                "document_title": "Order Tracking Information",
            }
        ],
    }


@pytest.fixture
def page_location_block() -> dict:
    """Simulates a non-streaming TextBlock with page_location citations."""
    return {
        "type": "text",
        "text": "Constitutional AI is a method for training harmless AI assistants.",
        "citations": [
            {
                "type": "page_location",
                "cited_text": "We experiment with methods for training a harmless AI assistant.",
                "document_index": 0,
                "document_title": "Constitutional AI Paper",
                "start_page_number": 1,
                "end_page_number": 2,
            }
        ],
    }


@pytest.fixture
def content_block_location_block() -> dict:
    """Simulates a non-streaming TextBlock with content_block_location citations."""
    return {
        "type": "text",
        "text": "Based on the help article...",
        "citations": [
            {
                "type": "content_block_location",
                "cited_text": "Full article text here about order tracking.",
                "document_index": 0,
                "document_title": "Order Tracking Information",
                "start_block_index": 0,
                "end_block_index": 0,
            }
        ],
    }


@pytest.fixture
def streaming_delta_block() -> dict:
    """Simulates a content_block_delta event with citations_delta."""
    return {
        "type": "content_block_delta",
        "index": 0,
        "delta": {
            "type": "citations_delta",
            "citation": {
                "type": "char_location",
                "cited_text": "Once your order ships, you'll receive an email.",
                "document_index": 0,
                "document_title": "Order Tracking Information",
                "start_char_index": 0,
                "end_char_index": 60,
            },
        },
    }


# ---------------------------------------------------------------------------
# parse_citations tests
# ---------------------------------------------------------------------------


class TestParseCitations:
    def test_parse_char_location(self, parser: CitationParser, char_location_block: dict) -> None:
        citations = parser.parse_citations(char_location_block)
        assert len(citations) == 1
        c = citations[0]
        assert c.citation_type == CitationType.CHAR_LOCATION
        assert c.document_title == "Order Tracking Information"
        assert "your order ships" in c.cited_text

    def test_parse_page_location(self, parser: CitationParser, page_location_block: dict) -> None:
        citations = parser.parse_citations(page_location_block)
        assert len(citations) == 1
        c = citations[0]
        assert c.citation_type == CitationType.PAGE_LOCATION
        assert c.start_page_number == 1
        assert c.end_page_number == 2
        assert c.document_title == "Constitutional AI Paper"

    def test_parse_content_block_location(self, parser: CitationParser, content_block_location_block: dict) -> None:
        citations = parser.parse_citations(content_block_location_block)
        assert len(citations) == 1
        c = citations[0]
        assert c.citation_type == CitationType.CONTENT_BLOCK_LOCATION
        assert c.start_block_index == 0
        assert c.end_block_index == 0

    def test_parse_streaming_delta(self, parser: CitationParser, streaming_delta_block: dict) -> None:
        citations = parser.parse_citations(streaming_delta_block)
        assert len(citations) == 1
        c = citations[0]
        assert c.citation_type == CitationType.CHAR_LOCATION
        assert c.document_title == "Order Tracking Information"

    def test_parse_empty_block(self, parser: CitationParser) -> None:
        citations = parser.parse_citations({"type": "text", "text": "No citations here"})
        assert len(citations) == 0

    def test_parse_invalid_type(self, parser: CitationParser) -> None:
        citations = parser.parse_citations({
            "type": "text",
            "text": "test",
            "citations": [
                {
                    "type": "invalid_type",
                    "cited_text": "some text",
                    "document_title": "Some Doc",
                }
            ],
        })
        assert len(citations) == 0  # Unknown type returns None, filtered out

    def test_parse_multiple_citations(self, parser: CitationParser) -> None:
        block = {
            "type": "text",
            "text": "answer",
            "citations": [
                {
                    "type": "char_location",
                    "cited_text": "Text from doc A.",
                    "document_title": "Doc A",
                },
                {
                    "type": "char_location",
                    "cited_text": "Text from doc B.",
                    "document_title": "Doc B",
                },
            ],
        }
        citations = parser.parse_citations(block)
        assert len(citations) == 2

    def test_parse_from_content_array(self, parser: CitationParser) -> None:
        """Test parsing from a parent dict with 'content' array."""
        block = {
            "content": [
                {
                    "type": "text",
                    "text": "answer",
                    "citations": [
                        {
                            "type": "char_location",
                            "cited_text": "Cited text.",
                            "document_title": "Test Doc",
                        }
                    ],
                }
            ]
        }
        citations = parser.parse_citations(block)
        assert len(citations) == 1

    def test_parse_response(self, parser: CitationParser) -> None:
        response = {
            "id": "msg_123",
            "content": [
                {
                    "type": "text",
                    "text": "First part",
                    "citations": [
                        {
                            "type": "char_location",
                            "cited_text": "Source text A.",
                            "document_title": "Doc A",
                        }
                    ],
                },
                {
                    "type": "text",
                    "text": "Second part",
                    "citations": [
                        {
                            "type": "page_location",
                            "cited_text": "Source text B.",
                            "document_title": "Doc B",
                            "start_page_number": 3,
                            "end_page_number": 4,
                        }
                    ],
                },
            ],
        }
        citations = parser.parse_response(response)
        assert len(citations) == 2


# ---------------------------------------------------------------------------
# format_citation / format_references tests
# ---------------------------------------------------------------------------


class TestFormatCitations:
    def test_format_single_citation(self, parser: CitationParser, sample_citations: list[Citation]) -> None:
        formatted = parser.format_citation(sample_citations[0], 1)
        assert formatted.startswith("[1]")
        assert "Order Tracking Information" in formatted
        assert "email with a tracking number" in formatted

    def test_format_page_citation(self, parser: CitationParser, sample_citations: list[Citation]) -> None:
        formatted = parser.format_citation(sample_citations[2], 3)
        assert formatted.startswith("[3]")
        assert "Constitutional AI Paper" in formatted
        assert "pages 1-2" in formatted

    def test_format_references(self, parser: CitationParser, sample_citations: list[Citation]) -> None:
        formatted = parser.format_references(sample_citations)
        lines = formatted.split("\n")
        # 3 unique citations (the two from Order Tracking are different cited_text)
        assert len(lines) == 3
        assert lines[0].startswith("[1]")
        assert lines[1].startswith("[2]")
        assert lines[2].startswith("[3]")

    def test_format_references_deduplicates(self, parser: CitationParser) -> None:
        dup = Citation(
            cited_text="Same cited text.",
            document_title="Same Doc",
            citation_type=CitationType.CHAR_LOCATION,
        )
        citations = [dup, dup, dup]
        formatted = parser.format_references(citations)
        lines = formatted.split("\n")
        assert len(lines) == 1  # Deduped

    def test_format_as_markdown(self, parser: CitationParser, sample_citations: list[Citation]) -> None:
        md = parser.format_as_markdown(sample_citations)
        assert "### References" in md
        assert "**Order Tracking Information**" in md
        assert "**Constitutional AI Paper**" in md


# ---------------------------------------------------------------------------
# annotate_text tests
# ---------------------------------------------------------------------------


class TestAnnotateText:
    def test_annotate_numbered(self, parser: CitationParser, sample_citations: list[Citation]) -> None:
        text = "Here is the answer to your question."
        annotated = parser.annotate_text(text, sample_citations, style="numbered")
        assert "[1]" in annotated
        assert "[2]" in annotated
        assert "[3]" in annotated
        assert text in annotated

    def test_annotate_inline(self, parser: CitationParser, sample_citations: list[Citation]) -> None:
        text = "Here is the answer."
        annotated = parser.annotate_text(text, sample_citations, style="inline")
        assert "Source:" in annotated
        assert "Order Tracking Information" in annotated

    def test_annotate_empty_citations(self, parser: CitationParser) -> None:
        text = "Just text."
        annotated = parser.annotate_text(text, [], style="numbered")
        assert annotated == "Just text."

    def test_annotate_default_style(self, parser: CitationParser, sample_citations: list[Citation]) -> None:
        text = "Hello."
        annotated = parser.annotate_text(text, sample_citations)
        assert "[1]" in annotated


# ---------------------------------------------------------------------------
# Deduplication tests
# ---------------------------------------------------------------------------


class TestDeduplicate:
    def test_deduplicate_exact_duplicates(self, parser: CitationParser) -> None:
        c1 = Citation(
            cited_text="Same text.",
            document_title="Same Doc",
            citation_type=CitationType.CHAR_LOCATION,
        )
        c2 = Citation(
            cited_text="Same text.",
            document_title="Same Doc",
            citation_type=CitationType.CHAR_LOCATION,
        )
        result = parser.deduplicate([c1, c2])
        assert len(result) == 1

    def test_deduplicate_different_text(self, parser: CitationParser) -> None:
        c1 = Citation(
            cited_text="Text A.",
            document_title="Doc",
            citation_type=CitationType.CHAR_LOCATION,
        )
        c2 = Citation(
            cited_text="Text B.",
            document_title="Doc",
            citation_type=CitationType.CHAR_LOCATION,
        )
        result = parser.deduplicate([c1, c2])
        assert len(result) == 2

    def test_deduplicate_different_docs_same_text(self, parser: CitationParser) -> None:
        c1 = Citation(
            cited_text="Same text.",
            document_title="Doc A",
            citation_type=CitationType.CHAR_LOCATION,
        )
        c2 = Citation(
            cited_text="Same text.",
            document_title="Doc B",
            citation_type=CitationType.CHAR_LOCATION,
        )
        result = parser.deduplicate([c1, c2])
        assert len(result) == 2

    def test_deduplicate_empty_list(self, parser: CitationParser) -> None:
        result = parser.deduplicate([])
        assert len(result) == 0


# ---------------------------------------------------------------------------
# Verification tests
# ---------------------------------------------------------------------------


class TestVerification:
    def test_verify_citation_found(self, parser: CitationParser) -> None:
        c = Citation(
            cited_text="The quick brown fox.",
            document_title="Test",
            citation_type=CitationType.CHAR_LOCATION,
        )
        source = "Lorem ipsum. The quick brown fox. Dolor sit amet."
        assert parser.verify_citation(c, source) is True

    def test_verify_citation_not_found(self, parser: CitationParser) -> None:
        c = Citation(
            cited_text="Missing text.",
            document_title="Test",
            citation_type=CitationType.CHAR_LOCATION,
        )
        source = "Completely different content."
        assert parser.verify_citation(c, source) is False

    def test_verify_all(self, parser: CitationParser) -> None:
        c1 = Citation(
            cited_text="The quick brown fox.",
            document_title="Doc A",
            citation_type=CitationType.CHAR_LOCATION,
        )
        c2 = Citation(
            cited_text="Missing in source.",
            document_title="Doc A",
            citation_type=CitationType.CHAR_LOCATION,
        )
        results = parser.verify_all(
            [c1, c2],
            sources={"Doc A": "Lorem ipsum. The quick brown fox. Dolor sit amet."},
        )
        keys = list(results.keys())
        assert results[keys[0]] is True  # c1 found
        assert results[keys[1]] is False  # c2 not found

    def test_verify_whitespace_normalized(self, parser: CitationParser) -> None:
        c = Citation(
            cited_text="The   quick\nbrown   fox.",
            document_title="Test",
            citation_type=CitationType.CHAR_LOCATION,
        )
        source = "The quick brown fox."
        assert parser.verify_citation(c, source) is True


# ---------------------------------------------------------------------------
# Summarize tests
# ---------------------------------------------------------------------------


class TestSummarize:
    def test_summarize(self, parser: CitationParser, sample_citations: list[Citation]) -> None:
        summary = parser.summarize(sample_citations)
        assert summary["total_citations"] == 3
        assert summary["unique_citations"] == 3
        assert summary["unique_documents"] == 2
        assert "char_location" in summary["by_type"]
        assert "page_location" in summary["by_type"]
        assert "Constitutional AI Paper" in summary["documents"]

    def test_summarize_with_duplicates(self, parser: CitationParser) -> None:
        c = Citation(
            cited_text="Same text.",
            document_title="Doc",
            citation_type=CitationType.CHAR_LOCATION,
        )
        summary = parser.summarize([c, c, c])
        assert summary["total_citations"] == 3
        assert summary["unique_citations"] == 1


# ---------------------------------------------------------------------------
# location_summary tests
# ---------------------------------------------------------------------------


class TestLocationSummary:
    def test_char_location_summary(self) -> None:
        c = Citation(
            cited_text="text",
            document_title="Doc",
            citation_type=CitationType.CHAR_LOCATION,
            start_char_index=10,
            end_char_index=50,
        )
        assert c.location_summary == "chars 10-50"

    def test_page_location_summary(self) -> None:
        c = Citation(
            cited_text="text",
            document_title="Doc",
            citation_type=CitationType.PAGE_LOCATION,
            start_page_number=3,
            end_page_number=5,
        )
        assert c.location_summary == "pages 3-5"

    def test_content_block_location_summary(self) -> None:
        c = Citation(
            cited_text="text",
            document_title="Doc",
            citation_type=CitationType.CONTENT_BLOCK_LOCATION,
            start_block_index=0,
            end_block_index=2,
        )
        assert c.location_summary == "blocks 0-2"

    def test_web_search_summary(self) -> None:
        c = Citation(
            cited_text="text",
            document_title="Web Page",
            citation_type=CitationType.WEB_SEARCH_RESULT_LOCATION,
            url="https://example.com",
        )
        assert c.location_summary == "https://example.com"

    def test_search_result_summary(self) -> None:
        c = Citation(
            cited_text="text",
            document_title="Result",
            citation_type=CitationType.SEARCH_RESULT_LOCATION,
            search_result_index=5,
        )
        assert c.location_summary == "result #5"


# ---------------------------------------------------------------------------
# to_dict tests
# ---------------------------------------------------------------------------


class TestToDict:
    def test_char_location_to_dict(self) -> None:
        c = Citation(
            cited_text="Cited.",
            document_title="Doc",
            citation_type=CitationType.CHAR_LOCATION,
            document_index=0,
            start_char_index=10,
            end_char_index=20,
        )
        d = c.to_dict()
        assert d["type"] == "char_location"
        assert d["cited_text"] == "Cited."
        assert d["start_char_index"] == 10
        assert d["end_char_index"] == 20

    def test_page_location_to_dict(self) -> None:
        c = Citation(
            cited_text="Cited.",
            document_title="PDF Doc",
            citation_type=CitationType.PAGE_LOCATION,
            start_page_number=1,
            end_page_number=2,
        )
        d = c.to_dict()
        assert d["type"] == "page_location"
        assert d["start_page_number"] == 1

    def test_dict_excludes_none_fields(self) -> None:
        c = Citation(
            cited_text="T.",
            document_title="D",
            citation_type=CitationType.CHAR_LOCATION,
        )
        d = c.to_dict()
        assert "start_page_number" not in d
        assert "url" not in d
