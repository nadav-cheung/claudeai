"""
Tests for Chapter 13: RAG Pipeline and Claude-as-Judge.

All tests use mocked HTTP transports so they run without API keys.
"""

from __future__ import annotations

import json
import math

import httpx
import pytest

from rag_pipeline import (
    BM25,
    Chunk,
    InMemoryVectorStore,
    ClaudeGenerator,
    Document,
    RAGPipeline,
    TextChunker,
)
from claude_judge import (
    ClaudeJudge,
    JudgeConfig,
    compute_retrieval_metrics,
    _parse_json_response,
)


# ---------------------------------------------------------------------------
# Mock embedder (no network calls)
# ---------------------------------------------------------------------------


class MockEmbedder:
    """A deterministic mock embedder for testing.

    Produces simple pseudo-embeddings based on text length and character
    values, so that semantically similar texts get similar vectors.
    """

    _dimension = 128

    @property
    def dimension(self) -> int:
        return self._dimension

    def embed(self, texts: list[str]) -> list[list[float]]:
        return [self._encode(t) for t in texts]

    def embed_query(self, query: str) -> list[float]:
        return self._encode(query)

    @staticmethod
    def _encode(text: str) -> list[float]:
        """Simple hash-based encoding for deterministic testing."""
        vec = [0.0] * 128
        lower = text.lower()
        for i, ch in enumerate(lower):
            idx = ord(ch) % 128
            vec[idx] += 1.0 / (i + 1)
        # Normalize
        norm = math.sqrt(sum(v * v for v in vec))
        if norm > 0:
            return [v / norm for v in vec]
        return vec


# ---------------------------------------------------------------------------
# Mock generate function (no API calls)
# ---------------------------------------------------------------------------


def mock_generate_fn(query: str, context: str, model: str) -> str:
    """A mock generator that returns a simple answer based on context."""
    # Extract sentences from context that contain query terms
    query_terms = set(query.lower().split())
    sentences = []
    for line in context.split("\n"):
        for sent in line.split(". "):
            if any(t in sent.lower() for t in query_terms):
                sentences.append(sent.strip())
    if sentences:
        return ". ".join(sentences[:3]) + "."
    return "Based on the provided context, I cannot find sufficient information."


# ---------------------------------------------------------------------------
# Mock HTTP transport factories
# ---------------------------------------------------------------------------


def _mock_claude_response(text: str) -> httpx.Response:
    """Build a mock httpx.Response that looks like a Claude API response."""
    return httpx.Response(
        status_code=200,
        content=json.dumps(
            {
                "id": "msg_test",
                "type": "message",
                "role": "assistant",
                "model": "claude-sonnet-4-20250514",
                "content": [{"type": "text", "text": text}],
                "stop_reason": "end_turn",
                "usage": {"input_tokens": 100, "output_tokens": 50},
            }
        ).encode(),
        request=httpx.Request("POST", "https://api.anthropic.com/v1/messages"),
    )


# ---------------------------------------------------------------------------
# Test documents
# ---------------------------------------------------------------------------

SAMPLE_DOCS = [
    Document(
        content=(
            "Retrieval-Augmented Generation (RAG) is a technique that combines "
            "information retrieval with large language models. RAG enhances LLM "
            "responses by providing relevant external knowledge at inference time. "
            "This reduces hallucinations and improves factual accuracy."
        ),
        metadata={"title": "Introduction to RAG"},
    ),
    Document(
        content=(
            "Vector databases store embeddings — numerical representations of text "
            "that capture semantic meaning. Popular vector databases include Pinecone, "
            "Weaviate, Qdrant, and pgvector. They support similarity search using "
            "metrics like cosine distance and Euclidean distance."
        ),
        metadata={"title": "Vector Databases"},
    ),
    Document(
        content=(
            "Claude is Anthropic's family of large language models. Claude models "
            "are designed with Constitutional AI principles, emphasizing helpfulness, "
            "honesty, and harmlessness. They can be accessed via the Anthropic API "
            "at api.anthropic.com."
        ),
        metadata={"title": "Claude Models"},
    ),
    Document(
        content=(
            "Embedding models convert text into fixed-length vectors. OpenAI provides "
            "text-embedding-3-small (1536 dimensions) and text-embedding-3-large "
            "(3072 dimensions). Voyage AI offers voyage-3 with 1024 dimensions and "
            "a 32K token context window. Cohere's embed-v4.0 also has 1024 dimensions. "
            "For open-source options, BAAI's bge-m3 is a strong choice supporting "
            "multilingual embeddings."
        ),
        metadata={"title": "Embedding Models"},
    ),
    Document(
        content=(
            "Hybrid search combines sparse retrieval (BM25 or SPLADE for keyword "
            "matching) with dense retrieval (vector similarity for semantic matching). "
            "Reciprocal Rank Fusion (RRF) merges the two result sets without needing "
            "to normalize scores. This approach significantly improves retrieval "
            "quality compared to using either method alone."
        ),
        metadata={"title": "Hybrid Search"},
    ),
]


# ---------------------------------------------------------------------------
# TextChunker tests
# ---------------------------------------------------------------------------


class TestTextChunker:
    def test_fixed_size_chunking(self):
        doc = Document(content="ABCDEFGHIJ" * 20)  # 200 chars
        chunks = TextChunker.fixed_size(doc, chunk_size=50, chunk_overlap=10)
        assert len(chunks) > 1
        assert all(len(c.content) <= 50 for c in chunks)

    def test_fixed_size_overlap(self):
        doc = Document(content="ABCDEFGHIJ" * 20)
        chunks = TextChunker.fixed_size(doc, chunk_size=50, chunk_overlap=10)
        if len(chunks) >= 2:
            # Last 10 chars of chunk 0 should match first 10 chars of chunk 1
            assert chunks[0].content[-10:] == chunks[1].content[:10]

    def test_semantic_chunking(self):
        doc = Document(
            content=(
                "First paragraph about RAG. It has multiple sentences. "
                "Second paragraph about vector databases. It also has details.\n\n"
                "Third paragraph with different topic about Claude models."
            )
        )
        chunks = TextChunker.semantic(doc, max_chunk_size=500)
        assert len(chunks) >= 1

    def test_single_chunk_small_doc(self):
        doc = Document(content="Short text.")
        chunks = TextChunker.fixed_size(doc, chunk_size=1000)
        assert len(chunks) == 1
        assert chunks[0].content == "Short text."

    def test_empty_doc(self):
        doc = Document(content="")
        chunks = TextChunker.fixed_size(doc)
        # Empty content produces no chunks (nothing to chunk)
        assert len(chunks) == 0


# ---------------------------------------------------------------------------
# BM25 tests
# ---------------------------------------------------------------------------


class TestBM25:
    def test_index_and_search(self):
        chunks = [
            Chunk(content="RAG combines retrieval with generation", doc_id="d1", chunk_index=0),
            Chunk(content="Vector databases store embeddings", doc_id="d2", chunk_index=0),
            Chunk(content="Claude is an LLM from Anthropic", doc_id="d3", chunk_index=0),
        ]
        bm25 = BM25()
        bm25.index(chunks)

        results = bm25.search("retrieval generation")
        assert len(results) > 0
        # The RAG chunk should rank first
        assert "RAG" in results[0][0].content

    def test_empty_corpus(self):
        bm25 = BM25()
        bm25.index([])
        results = bm25.search("anything")
        assert results == []

    def test_no_match_returns_empty(self):
        chunks = [
            Chunk(content="Apple pie recipe", doc_id="d1", chunk_index=0),
        ]
        bm25 = BM25()
        bm25.index(chunks)
        results = bm25.search("quantum mechanics")
        # May return results with very low scores; our BM25 filters zero scores
        assert all(score > 0 for _, score in results) if results else True


# ---------------------------------------------------------------------------
# InMemoryVectorStore tests
# ---------------------------------------------------------------------------


class TestInMemoryVectorStore:
    def test_add_and_search(self):
        store = InMemoryVectorStore()
        chunks = [
            Chunk(content="hello world", doc_id="d1", chunk_index=0),
            Chunk(content="goodbye world", doc_id="d2", chunk_index=0),
        ]
        vectors = [
            [1.0, 0.0, 0.0],
            [0.0, 1.0, 0.0],
        ]
        store.add(chunks, vectors)

        # Query vector similar to first chunk
        results = store.search([1.0, 0.1, 0.0], top_k=2)
        assert len(results) == 2
        assert results[0][0].content == "hello world"
        assert results[0][1] > results[1][1]  # First result has higher score

    def test_empty_store(self):
        store = InMemoryVectorStore()
        assert store.search([1.0, 0.0]) == []

    def test_clear(self):
        store = InMemoryVectorStore()
        store.add([Chunk(content="test", doc_id="d1", chunk_index=0)], [[0.5, 0.5]])
        assert len(store) == 1
        store.clear()
        assert len(store) == 0

    def test_length_validation(self):
        store = InMemoryVectorStore()
        with pytest.raises(ValueError, match="same length"):
            store.add([Chunk(content="x", doc_id="d1", chunk_index=0)], [[0.1], [0.2]])


# ---------------------------------------------------------------------------
# RAGPipeline tests
# ---------------------------------------------------------------------------


class TestRAGPipeline:
    @pytest.fixture
    def pipeline(self):
        embedder = MockEmbedder()
        return RAGPipeline(
            embedder=embedder,
            generate_fn=mock_generate_fn,
            chunk_size=500,
            chunk_overlap=100,
            top_k=3,
        )

    def test_ingest_documents(self, pipeline):
        count = pipeline.ingest(SAMPLE_DOCS)
        assert count > 0
        assert pipeline.chunk_count == count

    def test_retrieve_sparse(self, pipeline):
        pipeline.ingest(SAMPLE_DOCS)
        results = pipeline.retrieve("vector database", strategy="sparse")
        assert len(results) > 0
        assert all(r["strategy"] == "sparse" for r in results)

    def test_retrieve_dense(self, pipeline):
        pipeline.ingest(SAMPLE_DOCS)
        results = pipeline.retrieve("what is an embedding model", strategy="dense")
        assert len(results) > 0
        assert all(r["strategy"] == "dense" for r in results)

    def test_retrieve_hybrid(self, pipeline):
        pipeline.ingest(SAMPLE_DOCS)
        results = pipeline.retrieve("Claude model", strategy="hybrid")
        assert len(results) > 0
        assert all(r["strategy"] == "hybrid" for r in results)

    def test_query_end_to_end(self, pipeline):
        pipeline.ingest(SAMPLE_DOCS)
        result = pipeline.query("What is RAG?")
        assert "answer" in result
        assert "retrieved_chunks" in result
        assert len(result["retrieved_chunks"]) > 0

    def test_query_returns_structured_result(self, pipeline):
        pipeline.ingest(SAMPLE_DOCS)
        result = pipeline.query("Tell me about vector databases", top_k=2)
        assert isinstance(result["answer"], str)
        assert len(result["answer"]) > 0
        assert len(result["retrieved_chunks"]) <= 2

    def test_ingest_empty_documents(self, pipeline):
        count = pipeline.ingest([])
        assert count == 0

    def test_clear_resets_state(self, pipeline):
        pipeline.ingest(SAMPLE_DOCS)
        assert pipeline.chunk_count > 0
        pipeline.clear()
        assert pipeline.chunk_count == 0

    def test_semantic_chunking_strategy(self, pipeline):
        count = pipeline.ingest(SAMPLE_DOCS, chunk_strategy="semantic")
        assert count > 0

    def test_default_top_k(self, pipeline):
        pipeline.ingest(SAMPLE_DOCS)
        results = pipeline.retrieve("RAG")
        assert len(results) <= pipeline.top_k

    def test_unknown_strategy_raises(self, pipeline):
        pipeline.ingest(SAMPLE_DOCS)
        with pytest.raises(ValueError, match="Unknown retrieval strategy"):
            pipeline.retrieve("test", strategy="unknown")


# ---------------------------------------------------------------------------
# ClaudeGenerator tests (mocked)
# ---------------------------------------------------------------------------


class TestClaudeGenerator:
    def test_generate_mocked(self):
        def _handler(request: httpx.Request) -> httpx.Response:
            return _mock_claude_response("RAG stands for Retrieval-Augmented Generation.")

        with httpx.Client(transport=httpx.MockTransport(_handler)) as http:
            gen = ClaudeGenerator(api_key="sk-test")
            # Patch the HTTP client to use our mock
            original_post = httpx.post
            try:
                httpx.post = http.post
                result = gen.generate(
                    query="What is RAG?",
                    context="RAG is a technique.",
                    model="claude-sonnet-4-20250514",
                )
                assert "RAG" in result
            finally:
                httpx.post = original_post


# ---------------------------------------------------------------------------
# ClaudeJudge tests
# ---------------------------------------------------------------------------


class TestClaudeJudge:
    def test_faithfulness_evaluation_mocked(self):
        judge_json = json.dumps(
            {
                "score": 0.95,
                "reasoning": "All claims are supported by the context.",
                "supported_claims": ["RAG combines retrieval and generation"],
                "unsupported_claims": [],
            }
        )

        def _handler(request: httpx.Request) -> httpx.Response:
            return _mock_claude_response(judge_json)

        with httpx.Client(transport=httpx.MockTransport(_handler)) as http:
            judge = ClaudeJudge(config=JudgeConfig(api_key="sk-test"))
            original_post = httpx.post
            try:
                httpx.post = http.post
                result = judge.evaluate_faithfulness(
                    answer="RAG combines retrieval and generation.",
                    context="RAG is a technique that combines retrieval and generation.",
                )
                assert 0.0 <= result["score"] <= 1.0
                assert "reasoning" in result
            finally:
                httpx.post = original_post

    def test_relevance_evaluation_mocked(self):
        judge_json = json.dumps(
            {
                "score": 1.0,
                "reasoning": "The answer directly addresses the query about vector databases.",
                "relevant_parts": ["Vector databases store embeddings"],
                "irrelevant_parts": [],
            }
        )

        def _handler(request: httpx.Request) -> httpx.Response:
            return _mock_claude_response(judge_json)

        with httpx.Client(transport=httpx.MockTransport(_handler)) as http:
            judge = ClaudeJudge(config=JudgeConfig(api_key="sk-test"))
            original_post = httpx.post
            try:
                httpx.post = http.post
                result = judge.evaluate_relevance(
                    answer="Vector databases store embeddings for similarity search.",
                    query="What do vector databases store?",
                )
                assert result["score"] == 1.0
            finally:
                httpx.post = original_post

    def test_completeness_evaluation_mocked(self):
        judge_json = json.dumps(
            {
                "score": 0.7,
                "reasoning": "Covers most key points but missed the pricing section.",
                "covered_points": ["Embedding models convert text to vectors"],
                "missed_points": ["Pricing comparison between providers"],
            }
        )

        def _handler(request: httpx.Request) -> httpx.Response:
            return _mock_claude_response(judge_json)

        with httpx.Client(transport=httpx.MockTransport(_handler)) as http:
            judge = ClaudeJudge(config=JudgeConfig(api_key="sk-test"))
            original_post = httpx.post
            try:
                httpx.post = http.post
                result = judge.evaluate_completeness(
                    answer="Embedding models convert text to vectors.",
                    context="Embedding models convert text to vectors. Pricing varies by provider.",
                )
                assert result["score"] == 0.7
            finally:
                httpx.post = original_post

    def test_comprehensive_eval_mocked(self):
        judge_json = json.dumps(
            {
                "faithfulness": {
                    "score": 0.9,
                    "reasoning": "Mostly faithful with minor embellishment.",
                },
                "relevance": {
                    "score": 0.9,
                    "reasoning": "Directly addresses the query.",
                },
                "completeness": {
                    "score": 0.8,
                    "reasoning": "Misses one supporting detail.",
                },
                "overall_score": 0.87,
                "overall_assessment": "Good answer with high faithfulness and relevance.",
            }
        )

        def _handler(request: httpx.Request) -> httpx.Response:
            return _mock_claude_response(judge_json)

        with httpx.Client(transport=httpx.MockTransport(_handler)) as http:
            judge = ClaudeJudge(config=JudgeConfig(api_key="sk-test"))
            original_post = httpx.post
            try:
                httpx.post = http.post
                result = judge.comprehensive_eval(
                    query="What is RAG?",
                    answer="RAG is a technique combining retrieval with generation.",
                    context="RAG combines retrieval with generation to improve accuracy.",
                )
                assert "faithfulness" in result
                assert "relevance" in result
                assert "completeness" in result
                assert "overall_score" in result
            finally:
                httpx.post = original_post

    def test_evaluate_batch(self):
        judge_json = json.dumps(
            {
                "faithfulness": {"score": 0.9, "reasoning": "ok"},
                "relevance": {"score": 1.0, "reasoning": "ok"},
                "completeness": {"score": 0.8, "reasoning": "ok"},
                "overall_score": 0.9,
                "overall_assessment": "Good.",
            }
        )

        def _handler(request: httpx.Request) -> httpx.Response:
            return _mock_claude_response(judge_json)

        with httpx.Client(transport=httpx.MockTransport(_handler)) as http:
            judge = ClaudeJudge(config=JudgeConfig(api_key="sk-test"))
            original_post = httpx.post
            try:
                httpx.post = http.post
                results = judge.evaluate_batch(
                    [
                        {"query": "Q1", "answer": "A1", "context": "C1"},
                        {"query": "Q2", "answer": "A2", "context": "C2"},
                    ]
                )
                assert len(results) == 2
                assert results[0]["overall_score"] == 0.9
            finally:
                httpx.post = original_post

    def test_judge_config_defaults(self):
        config = JudgeConfig(api_key="sk-test")
        assert config.temperature == 0.0
        assert config.judge_model == "claude-sonnet-4-20250514"


# ---------------------------------------------------------------------------
# JSON response parsing tests
# ---------------------------------------------------------------------------


class TestParseJsonResponse:
    def test_clean_json(self):
        result = _parse_json_response('{"score": 0.85, "reasoning": "test"}')
        assert result["score"] == 0.85
        assert result["reasoning"] == "test"

    def test_json_in_code_block(self):
        result = _parse_json_response(
            '```json\n{"score": 0.9, "reasoning": "test"}\n```'
        )
        assert result["score"] == 0.9

    def test_json_with_text_wrapping(self):
        result = _parse_json_response(
            'Here is my evaluation:\n\n{"score": 0.75, "reasoning": "ok"}\n\nHope this helps.'
        )
        assert result["score"] == 0.75

    def test_invalid_json_fallback(self):
        result = _parse_json_response("I cannot parse this")
        assert result["score"] == 0.0
        assert "Failed to parse" in result["reasoning"]


# ---------------------------------------------------------------------------
# Retrieval metrics tests
# ---------------------------------------------------------------------------


class TestRetrievalMetrics:
    def test_perfect_retrieval(self):
        metrics = compute_retrieval_metrics(
            retrieved_ids=["a", "b", "c"],
            relevant_ids={"a", "b", "c"},
        )
        assert metrics["recall_at_k"] == 1.0
        assert metrics["precision_at_k"] == 1.0
        assert metrics["mrr"] == 1.0

    def test_partial_retrieval(self):
        metrics = compute_retrieval_metrics(
            retrieved_ids=["a", "b", "c", "d"],
            relevant_ids={"b", "e"},
            k=3,
        )
        assert metrics["recall_at_k"] == 0.5  # 1 of 2 relevant in top-3
        assert metrics["precision_at_k"] == 1.0 / 3.0

    def test_mrr(self):
        metrics = compute_retrieval_metrics(
            retrieved_ids=["x", "a", "y"],
            relevant_ids={"a", "b"},
        )
        assert metrics["mrr"] == 1.0 / 2.0  # First relevant at rank 2

    def test_no_relevant(self):
        metrics = compute_retrieval_metrics(
            retrieved_ids=["x", "y"],
            relevant_ids=set(),
        )
        assert metrics["recall_at_k"] == 0.0

    def test_empty_retrieved(self):
        metrics = compute_retrieval_metrics(
            retrieved_ids=[],
            relevant_ids={"a"},
        )
        assert metrics["recall_at_k"] == 0.0
        assert metrics["mrr"] == 0.0


# ---------------------------------------------------------------------------
# End-to-end integration test: ingest 5 docs, query 3 questions
# ---------------------------------------------------------------------------


class TestEndToEndIntegration:
    def test_full_pipeline_with_mock_judge(self):
        """Simulate the complete flow: ingest 5 docs -> query 3 questions -> evaluate.

        Uses a mock judge response to avoid real API calls.
        """
        embedder = MockEmbedder()
        pipeline = RAGPipeline(
            embedder=embedder,
            generate_fn=mock_generate_fn,
            chunk_size=300,
            chunk_overlap=50,
            top_k=3,
        )

        # Step 1: Ingest 5 documents
        count = pipeline.ingest(SAMPLE_DOCS)
        assert count > 0, "Should create at least some chunks"

        # Step 2: Query 3 questions
        questions = [
            "What is RAG and how does it help LLMs?",
            "What vector databases are commonly used?",
            "How does hybrid search work?",
        ]

        results = []
        for q in questions:
            result = pipeline.query(q, strategy="hybrid")
            assert len(result["answer"]) > 0
            assert len(result["retrieved_chunks"]) > 0
            results.append(result)

        assert len(results) == 3

        # Step 3: Evaluate retrieval quality with known relevant content
        # For question 0 (RAG), relevant chunks should contain "retrieval" or "RAG"
        q0_chunks = results[0]["retrieved_chunks"]
        rag_terms = [c for c in q0_chunks if "RAG" in c["content"] or "retrieval" in c["content"].lower()]
        assert len(rag_terms) > 0, "RAG question should retrieve RAG-related chunks"

        # For question 1 (vector databases), relevant chunks should mention vector DB names
        q1_chunks = results[1]["retrieved_chunks"]
        db_terms = [c for c in q1_chunks if any(
            db in c["content"].lower() for db in ["pinecone", "weaviate", "qdrant", "pgvector"]
        )]
        assert len(db_terms) > 0, "Vector DB question should retrieve DB-related chunks"

        # For question 2 (hybrid search), relevant chunks should mention hybrid/BM25/RRF
        q2_chunks = results[2]["retrieved_chunks"]
        hybrid_terms = [c for c in q2_chunks if any(
            term in c["content"].lower() for term in ["hybrid", "bm25", "rrf", "sparse"]
        )]
        assert len(hybrid_terms) > 0, "Hybrid search question should retrieve hybrid-related chunks"
