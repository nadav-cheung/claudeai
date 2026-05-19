"""
Tests for Chapter 6: Embedding-based Tool Search.
"""

import pytest

from tool_search import EmbeddingToolSearch, ToolSearchEntry


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def sample_tools() -> list[dict]:
    """10 realistic tool definitions for search testing."""
    return [
        {
            "name": "github_create_pr",
            "description": "Create a pull request on GitHub with title, description, and target branch",
            "input_schema": {
                "type": "object",
                "properties": {
                    "title": {"type": "string", "description": "PR title"},
                    "body": {"type": "string", "description": "PR description"},
                    "base": {"type": "string", "description": "Target branch"},
                    "head": {"type": "string", "description": "Source branch"},
                },
                "required": ["title", "base", "head"],
            },
        },
        {
            "name": "github_list_issues",
            "description": "List GitHub issues with optional filters for state, labels, and assignee",
            "input_schema": {
                "type": "object",
                "properties": {
                    "state": {"type": "string", "description": "open, closed, or all"},
                    "labels": {"type": "array", "items": {"type": "string"}},
                },
                "required": [],
            },
        },
        {
            "name": "slack_send_message",
            "description": "Send a message to a Slack channel or direct message. Supports markdown formatting.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "channel": {"type": "string", "description": "Channel ID or name"},
                    "text": {"type": "string", "description": "Message content with markdown"},
                },
                "required": ["channel", "text"],
            },
        },
        {
            "name": "slack_list_channels",
            "description": "List all Slack channels in the workspace",
            "input_schema": {
                "type": "object",
                "properties": {
                    "exclude_archived": {"type": "boolean", "description": "Filter out archived channels"},
                },
                "required": [],
            },
        },
        {
            "name": "get_weather",
            "description": "Get current weather conditions for a specific location including temperature, humidity, and wind speed",
            "input_schema": {
                "type": "object",
                "properties": {
                    "location": {"type": "string", "description": "City name with optional country code"},
                    "unit": {"type": "string", "description": "celsius or fahrenheit"},
                },
                "required": ["location"],
            },
        },
        {
            "name": "get_forecast",
            "description": "Get 5-day weather forecast for a location with daily high/low temperatures and conditions",
            "input_schema": {
                "type": "object",
                "properties": {
                    "location": {"type": "string", "description": "City name"},
                    "days": {"type": "integer", "description": "Number of days (1-5)"},
                },
                "required": ["location"],
            },
        },
        {
            "name": "jira_create_ticket",
            "description": "Create a Jira ticket with title, description, priority, and assignee",
            "input_schema": {
                "type": "object",
                "properties": {
                    "project": {"type": "string", "description": "Jira project key"},
                    "summary": {"type": "string", "description": "Ticket summary"},
                    "priority": {"type": "string", "description": "Priority level"},
                },
                "required": ["project", "summary"],
            },
        },
        {
            "name": "database_query",
            "description": "Execute SQL queries against the internal PostgreSQL database. Returns results as JSON array of row objects.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "sql": {"type": "string", "description": "SQL query to execute"},
                    "params": {"type": "array", "description": "Query parameters"},
                },
                "required": ["sql"],
            },
        },
        {
            "name": "send_email",
            "description": "Send an email via SMTP with to, cc, subject, and body fields",
            "input_schema": {
                "type": "object",
                "properties": {
                    "to": {"type": "string", "description": "Recipient email"},
                    "subject": {"type": "string", "description": "Email subject"},
                    "body": {"type": "string", "description": "Email body (HTML supported)"},
                },
                "required": ["to", "subject", "body"],
            },
        },
        {
            "name": "read_file",
            "description": "Read contents of a file from the local filesystem at the given path",
            "input_schema": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Absolute file path"},
                    "encoding": {"type": "string", "description": "File encoding (default utf-8)"},
                },
                "required": ["path"],
            },
        },
    ]


@pytest.fixture
def empty_search() -> EmbeddingToolSearch:
    return EmbeddingToolSearch()


@pytest.fixture
def indexed_search(sample_tools: list[dict]) -> EmbeddingToolSearch:
    search = EmbeddingToolSearch(embedding_dim=384)
    search.index_tools(sample_tools)
    return search


# ---------------------------------------------------------------------------
# Initialization tests
# ---------------------------------------------------------------------------


class TestInitialization:
    def test_default_dimension(self) -> None:
        search = EmbeddingToolSearch()
        assert search.embedding_dim == 384
        assert search.tool_count == 0
        assert not search.is_indexed

    def test_custom_dimension(self) -> None:
        search = EmbeddingToolSearch(embedding_dim=768)
        assert search.embedding_dim == 768

    def test_zero_dimension_raises(self) -> None:
        with pytest.raises(ValueError, match="positive"):
            EmbeddingToolSearch(embedding_dim=0)

    def test_negative_dimension_raises(self) -> None:
        with pytest.raises(ValueError, match="positive"):
            EmbeddingToolSearch(embedding_dim=-1)


# ---------------------------------------------------------------------------
# Indexing tests
# ---------------------------------------------------------------------------


class TestIndexing:
    def test_index_sets_tool_count(self, sample_tools: list[dict]) -> None:
        search = EmbeddingToolSearch()
        assert search.tool_count == 0
        search.index_tools(sample_tools)
        assert search.tool_count == 10
        assert search.is_indexed

    def test_index_with_empty_list(self, empty_search: EmbeddingToolSearch) -> None:
        empty_search.index_tools([])
        assert empty_search.tool_count == 0

    def test_index_preserves_tool_metadata(self, indexed_search: EmbeddingToolSearch) -> None:
        results = indexed_search.search_by_regex("github")
        names = [r["name"] for r in results]
        assert "github_create_pr" in names
        assert "github_list_issues" in names

    def test_re_index_replaces_tools(self, empty_search: EmbeddingToolSearch) -> None:
        empty_search.index_tools([
            {"name": "tool_a", "description": "First tool", "input_schema": {"type": "object", "properties": {}, "required": []}},
        ])
        assert empty_search.tool_count == 1
        empty_search.index_tools([
            {"name": "tool_b", "description": "Second tool", "input_schema": {"type": "object", "properties": {}, "required": []}},
        ])
        assert empty_search.tool_count == 1


# ---------------------------------------------------------------------------
# Search tests
# ---------------------------------------------------------------------------


class TestSearch:
    def test_search_slack(self, indexed_search: EmbeddingToolSearch) -> None:
        results = indexed_search.search("send message to slack", top_k=3)
        assert len(results) > 0
        # slack_send_message should be the top or near-top result
        names = [r["name"] for r in results]
        assert "slack_send_message" in names

    def test_search_weather(self, indexed_search: EmbeddingToolSearch) -> None:
        results = indexed_search.search("what is the weather", top_k=3)
        names = [r["name"] for r in results]
        assert "get_weather" in names or "get_forecast" in names

    def test_search_github(self, indexed_search: EmbeddingToolSearch) -> None:
        results = indexed_search.search("create github pull request", top_k=3)
        names = [r["name"] for r in results]
        assert "github_create_pr" in names

    def test_search_scores_in_range(self, indexed_search: EmbeddingToolSearch) -> None:
        results = indexed_search.search("weather forecast", top_k=5)
        for r in results:
            assert 0 <= r["score"] <= 1

    def test_search_scores_descending(self, indexed_search: EmbeddingToolSearch) -> None:
        results = indexed_search.search("query database", top_k=5)
        if len(results) > 1:
            for i in range(len(results) - 1):
                assert results[i]["score"] >= results[i + 1]["score"]

    def test_search_top_k_limit(self, indexed_search: EmbeddingToolSearch) -> None:
        results = indexed_search.search("file", top_k=2)
        assert len(results) <= 2

    def test_search_empty_index(self, empty_search: EmbeddingToolSearch) -> None:
        results = empty_search.search("anything")
        assert results == []

    def test_search_each_result_has_required_fields(
        self, indexed_search: EmbeddingToolSearch
    ) -> None:
        results = indexed_search.search("jira ticket", top_k=3)
        for r in results:
            assert "name" in r
            assert "description" in r
            assert "input_schema" in r
            assert "score" in r


# ---------------------------------------------------------------------------
# Regex search tests
# ---------------------------------------------------------------------------


class TestRegexSearch:
    def test_search_by_regex_simple(self, indexed_search: EmbeddingToolSearch) -> None:
        results = indexed_search.search_by_regex("github")
        names = [r["name"] for r in results]
        assert len(names) >= 2
        assert "github_create_pr" in names
        assert "github_list_issues" in names

    def test_search_by_regex_case_sensitive(self, indexed_search: EmbeddingToolSearch) -> None:
        results = indexed_search.search_by_regex("GITHUB")
        assert len(results) == 0

    def test_search_by_regex_case_insensitive(self, indexed_search: EmbeddingToolSearch) -> None:
        results = indexed_search.search_by_regex("(?i)github")
        assert len(results) >= 2

    def test_search_by_regex_prefix(self, indexed_search: EmbeddingToolSearch) -> None:
        results = indexed_search.search_by_regex("^slack_")
        names = [r["name"] for r in results]
        assert len(names) == 2
        assert "slack_send_message" in names
        assert "slack_list_channels" in names

    def test_search_by_regex_no_match(self, indexed_search: EmbeddingToolSearch) -> None:
        results = indexed_search.search_by_regex("nonexistent_tool_xyz")
        assert results == []

    def test_search_by_regex_description(self, indexed_search: EmbeddingToolSearch) -> None:
        results = indexed_search.search_by_regex("PostgreSQL")
        names = [r["name"] for r in results]
        assert "database_query" in names

    def test_search_by_regex_results_have_no_score(self, indexed_search: EmbeddingToolSearch) -> None:
        results = indexed_search.search_by_regex("slack")
        for r in results:
            assert "score" not in r
            assert "name" in r
            assert "description" in r


# ---------------------------------------------------------------------------
# ToolSearchEntry tests
# ---------------------------------------------------------------------------


class TestToolSearchEntry:
    def test_to_search_text_includes_all(self) -> None:
        entry = ToolSearchEntry(
            name="test_tool",
            description="A test tool for unit tests",
            input_schema={
                "type": "object",
                "properties": {
                    "param1": {"type": "string", "description": "First parameter"},
                    "param2": {"type": "integer"},
                },
                "required": ["param1"],
            },
        )
        text = entry.to_search_text()
        assert "test_tool" in text
        assert "A test tool for unit tests" in text
        assert "param1" in text
        assert "First parameter" in text
        assert "param2" in text

    def test_to_search_text_empty_props(self) -> None:
        entry = ToolSearchEntry(
            name="simple",
            description="Simple tool",
            input_schema={"type": "object", "properties": {}, "required": []},
        )
        text = entry.to_search_text()
        assert text == "simple Simple tool"


# ---------------------------------------------------------------------------
# Cosine similarity tests
# ---------------------------------------------------------------------------


class TestCosineSimilarity:
    def test_identical_vectors(self) -> None:
        a = [1.0, 0.0, 0.0]
        b = [1.0, 0.0, 0.0]
        assert EmbeddingToolSearch._cosine_similarity(a, b) == pytest.approx(1.0)

    def test_orthogonal_vectors(self) -> None:
        a = [1.0, 0.0]
        b = [0.0, 1.0]
        assert EmbeddingToolSearch._cosine_similarity(a, b) == pytest.approx(0.0)

    def test_opposite_vectors(self) -> None:
        a = [1.0, 0.0]
        b = [-1.0, 0.0]
        assert EmbeddingToolSearch._cosine_similarity(a, b) == pytest.approx(-1.0)

    def test_zero_vector(self) -> None:
        a = [0.0, 0.0]
        b = [1.0, 2.0]
        assert EmbeddingToolSearch._cosine_similarity(a, b) == 0.0

    def test_dimension_mismatch_raises(self) -> None:
        with pytest.raises(ValueError, match="dimension mismatch"):
            EmbeddingToolSearch._cosine_similarity([1.0, 2.0], [1.0, 2.0, 3.0])

    def test_search_deterministic(self, indexed_search: EmbeddingToolSearch) -> None:
        """Multiple searches with same query should return same results."""
        results1 = indexed_search.search("weather forecast", top_k=5)
        results2 = indexed_search.search("weather forecast", top_k=5)
        assert results1 == results2
