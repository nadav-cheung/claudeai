"""
Chapter 13: RAG Pipeline — Retrieval-Augmented Generation.

A vendor-agnostic RAG pipeline with pluggable embedders, vector stores,
retrieval strategies, and generators. Designed for the Anthropic ecosystem:
Anthropic has no native embedding model, so this pipeline integrates
third-party embeddings (OpenAI, Voyage, Cohere) and uses Claude for generation.

Key features:
  - Document ingestion with configurable chunking
  - Multiple retrieval strategies: sparse, dense, hybrid
  - Reciprocal Rank Fusion (RRF) for hybrid search
  - Claude-powered answer generation
  - End-to-end query() method
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from abc import ABC, abstractmethod
from collections import Counter
from dataclasses import dataclass, field
from typing import Any, Protocol

# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------


@dataclass
class Document:
    """A single document with metadata and content."""

    content: str
    metadata: dict[str, Any] = field(default_factory=dict)
    doc_id: str = ""

    def __post_init__(self) -> None:
        if not self.doc_id:
            self.doc_id = hashlib.sha256(self.content.encode()).hexdigest()[:16]


@dataclass
class Chunk:
    """A chunk of text produced by splitting a document."""

    content: str
    doc_id: str
    chunk_index: int
    metadata: dict[str, Any] = field(default_factory=dict)
    chunk_id: str = ""

    def __post_init__(self) -> None:
        if not self.chunk_id:
            raw = f"{self.doc_id}:{self.chunk_index}"
            self.chunk_id = hashlib.sha256(raw.encode()).hexdigest()[:16]


@dataclass
class RetrievalResult:
    """A single retrieval hit with score and metadata."""

    chunk: Chunk
    score: float
    strategy: str  # "sparse", "dense", or "hybrid"


# ---------------------------------------------------------------------------
# Embedder protocol
# ---------------------------------------------------------------------------


class Embedder(ABC):
    """Abstract interface for embedding models.

    Anthropic does NOT provide an embedding model. Applications must use
    third-party providers: OpenAI, Voyage, Cohere, or local models (bge-m3).

    This abstraction lets you swap providers without changing pipeline logic.
    """

    @property
    @abstractmethod
    def dimension(self) -> int:
        """Output vector dimensionality."""

    @abstractmethod
    def embed(self, texts: list[str]) -> list[list[float]]:
        """Embed a batch of texts into vectors."""

    def embed_query(self, query: str) -> list[float]:
        """Embed a single query string."""
        return self.embed([query])[0]


# ---------------------------------------------------------------------------
# Concrete embedder implementations
# ---------------------------------------------------------------------------


class OpenAIEmbedder(Embedder):
    """OpenAI text-embedding-3-small or text-embedding-3-large.

    Supports Matryoshka representation (variable output dimensions).
    """

    def __init__(
        self,
        api_key: str,
        model: str = "text-embedding-3-small",
        dimensions: int | None = None,
    ) -> None:
        self._api_key = api_key
        self._model = model
        self._dimensions = dimensions
        self._default_dims = {"text-embedding-3-small": 1536, "text-embedding-3-large": 3072}

    @property
    def dimension(self) -> int:
        return self._dimensions or self._default_dims.get(self._model, 1536)

    def embed(self, texts: list[str]) -> list[list[float]]:
        import httpx

        body: dict[str, Any] = {"model": self._model, "input": texts}
        if self._dimensions is not None:
            body["dimensions"] = self._dimensions

        resp = httpx.post(
            "https://api.openai.com/v1/embeddings",
            headers={
                "Authorization": f"Bearer {self._api_key}",
                "Content-Type": "application/json",
            },
            json=body,
            timeout=30.0,
        )
        resp.raise_for_status()
        data = resp.json()
        return [item["embedding"] for item in data["data"]]


class VoyageEmbedder(Embedder):
    """Voyage AI embedding models (voyage-3, voyage-3-lite, voyage-code-3).

    Known for excellent retrieval quality and large context windows (32K tokens).
    """

    def __init__(self, api_key: str, model: str = "voyage-3") -> None:
        self._api_key = api_key
        self._model = model
        self._dims = {
            "voyage-3": 1024,
            "voyage-3-lite": 512,
            "voyage-code-3": 1024,
        }

    @property
    def dimension(self) -> int:
        return self._dims.get(self._model, 1024)

    def embed(self, texts: list[str]) -> list[list[float]]:
        import httpx

        resp = httpx.post(
            "https://api.voyageai.com/v1/embeddings",
            headers={
                "Authorization": f"Bearer {self._api_key}",
                "Content-Type": "application/json",
            },
            json={"model": self._model, "input": texts, "input_type": "document"},
            timeout=30.0,
        )
        resp.raise_for_status()
        data = resp.json()
        return [item["embedding"] for item in data["data"]]


class CohereEmbedder(Embedder):
    """Cohere Embed v4.0 with 128K token context window."""

    def __init__(
        self,
        api_key: str,
        model: str = "embed-v4.0",
        input_type: str = "search_document",
    ) -> None:
        self._api_key = api_key
        self._model = model
        self._input_type = input_type
        self._dims = {"embed-v4.0": 1024, "embed-multilingual-v3.0": 1024}

    @property
    def dimension(self) -> int:
        return self._dims.get(self._model, 1024)

    def embed(self, texts: list[str]) -> list[list[float]]:
        import httpx

        resp = httpx.post(
            "https://api.cohere.com/v2/embed",
            headers={
                "Authorization": f"Bearer {self._api_key}",
                "Content-Type": "application/json",
            },
            json={"model": self._model, "texts": texts, "input_type": self._input_type},
            timeout=30.0,
        )
        resp.raise_for_status()
        data = resp.json()
        return data["embeddings"]


# ---------------------------------------------------------------------------
# BM25 (Sparse retrieval)
# ---------------------------------------------------------------------------


class BM25:
    """Pure-Python BM25 implementation for sparse retrieval.

    BM25 is a bag-of-words ranking function that excels at keyword matching
    and complements dense vector search in hybrid retrieval setups.
    """

    def __init__(self, k1: float = 1.5, b: float = 0.75) -> None:
        self._k1 = k1
        self._b = b
        self._corpus: list[Chunk] = []
        self._doc_freq: Counter[str] = Counter()
        self._avgdl: float = 0.0

    def index(self, chunks: list[Chunk]) -> None:
        self._corpus = chunks
        self._doc_freq = Counter()
        total_len = 0
        for chunk in chunks:
            terms = set(self._tokenize(chunk.content))
            for t in terms:
                self._doc_freq[t] += 1
            total_len += len(self._tokenize(chunk.content))
        self._avgdl = total_len / max(len(chunks), 1)

    def search(self, query: str, top_k: int = 5) -> list[tuple[Chunk, float]]:
        N = len(self._corpus)
        query_terms = self._tokenize(query)
        scores: list[tuple[int, float]] = []

        for idx, chunk in enumerate(self._corpus):
            doc_terms = self._tokenize(chunk.content)
            doc_len = len(doc_terms)
            tf = Counter(doc_terms)
            score = 0.0
            for qt in query_terms:
                if qt not in self._doc_freq:
                    continue
                f = tf.get(qt, 0)
                df = self._doc_freq[qt]
                idf = math.log((N - df + 0.5) / (df + 0.5) + 1.0)
                numerator = f * (self._k1 + 1.0)
                denominator = f + self._k1 * (1.0 - self._b + self._b * doc_len / self._avgdl)
                score += idf * numerator / denominator
            scores.append((idx, score))

        scores.sort(key=lambda x: x[1], reverse=True)
        return [(self._corpus[idx], score) for idx, score in scores[:top_k] if score > 0]

    @staticmethod
    def _tokenize(text: str) -> list[str]:
        return re.findall(r"\w+", text.lower())


# ---------------------------------------------------------------------------
# Vector Store (in-memory)
# ---------------------------------------------------------------------------


class InMemoryVectorStore:
    """A simple in-memory vector store with cosine similarity search.

    Production systems should replace this with Pinecone, Weaviate, Qdrant,
    pgvector, or Milvus. This store is for learning and testing.
    """

    def __init__(self) -> None:
        self._chunks: list[Chunk] = []
        self._vectors: list[list[float]] = []

    def add(self, chunks: list[Chunk], vectors: list[list[float]]) -> None:
        if len(chunks) != len(vectors):
            raise ValueError("chunks and vectors must have the same length")
        self._chunks.extend(chunks)
        self._vectors.extend(vectors)

    def search(self, query_vector: list[float], top_k: int = 5) -> list[tuple[Chunk, float]]:
        if not self._vectors:
            return []
        scores = [
            (self._chunks[i], _cosine_similarity(query_vector, vec))
            for i, vec in enumerate(self._vectors)
        ]
        scores.sort(key=lambda x: x[1], reverse=True)
        return scores[:top_k]

    def clear(self) -> None:
        self._chunks.clear()
        self._vectors.clear()

    def __len__(self) -> int:
        return len(self._chunks)


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


# ---------------------------------------------------------------------------
# Chunking strategies
# ---------------------------------------------------------------------------


class TextChunker:
    """Collection of chunking strategies.

    Each strategy returns a list of Chunk objects from a Document.
    """

    @staticmethod
    def fixed_size(
        doc: Document,
        chunk_size: int = 1000,
        chunk_overlap: int = 200,
    ) -> list[Chunk]:
        """Fixed-size chunking with configurable overlap."""
        chunks: list[Chunk] = []
        text = doc.content
        i = 0
        while i < len(text):
            end = min(i + chunk_size, len(text))
            chunk_text = text[i:end]
            chunks.append(
                Chunk(
                    content=chunk_text,
                    doc_id=doc.doc_id,
                    chunk_index=len(chunks),
                    metadata={**doc.metadata, "chunk_start": i, "chunk_end": end},
                )
            )
            if end >= len(text):
                break
            i = end - chunk_overlap
        return chunks

    @staticmethod
    def semantic(
        doc: Document,
        max_chunk_size: int = 2000,
        separators: list[str] | None = None,
    ) -> list[Chunk]:
        """Recursive semantic chunking by splitting on natural boundaries."""
        if separators is None:
            separators = ["\n\n", "\n", ". ", "! ", "? ", "; ", " "]

        def _split(text: str, sep_index: int = 0) -> list[str]:
            if len(text) <= max_chunk_size or sep_index >= len(separators):
                return [text]
            sep = separators[sep_index]
            parts = text.split(sep)
            result: list[str] = []
            current = ""
            for part in parts:
                if len(current) + len(part) + len(sep) <= max_chunk_size:
                    current = (current + sep + part) if current else part
                else:
                    if current:
                        result.extend(_split(current, sep_index + 1))
                    current = part
            if current:
                result.extend(_split(current, sep_index + 1))
            return result

        segments = _split(doc.content)
        return [
            Chunk(
                content=seg,
                doc_id=doc.doc_id,
                chunk_index=i,
                metadata={**doc.metadata, "chunk_strategy": "semantic"},
            )
            for i, seg in enumerate(segments)
        ]


# ---------------------------------------------------------------------------
# Generator interface
# ---------------------------------------------------------------------------


class GeneratorCallable(Protocol):
    """Protocol for the generation callback used by RAGPipeline.

    The pipeline calls this with (query, context_text, model) and expects
    the generated answer string back. This decouples the RAG logic from
    the specific LLM provider.
    """

    def __call__(self, query: str, context: str, model: str) -> str: ...


# ---------------------------------------------------------------------------
# RAG Pipeline
# ---------------------------------------------------------------------------


@dataclass
class RAGPipeline:
    """End-to-end RAG pipeline: ingest -> retrieve -> generate.

    Usage::

        embedder = OpenAIEmbedder(api_key="sk-...")
        pipeline = RAGPipeline(
            embedder=embedder,
            generate_fn=my_claude_generator,
            chunk_size=1000,
            chunk_overlap=200,
        )
        docs = [Document(content="...", metadata={"source": "doc1.txt"})]
        pipeline.ingest(docs)
        answer = pipeline.query("What is RAG?")
    """

    embedder: Embedder
    generate_fn: GeneratorCallable
    chunk_size: int = 1000
    chunk_overlap: int = 200
    top_k: int = 5
    default_strategy: str = "hybrid"

    # Internal state
    _vector_store: InMemoryVectorStore = field(default_factory=InMemoryVectorStore)
    _bm25: BM25 = field(default_factory=BM25)
    _all_chunks: list[Chunk] = field(default_factory=list)

    # ----------------------------------------------------------------
    # Ingestion
    # ----------------------------------------------------------------

    def ingest(
        self,
        documents: list[Document],
        chunk_size: int | None = None,
        chunk_overlap: int | None = None,
        chunk_strategy: str = "fixed",
    ) -> int:
        """Ingest documents: chunk, embed, index.

        Returns the total number of chunks created.
        """
        cs = chunk_size if chunk_size is not None else self.chunk_size
        co = chunk_overlap if chunk_overlap is not None else self.chunk_overlap

        all_chunks: list[Chunk] = []
        for doc in documents:
            if chunk_strategy == "semantic":
                chunks = TextChunker.semantic(doc, max_chunk_size=cs)
            else:
                chunks = TextChunker.fixed_size(doc, chunk_size=cs, chunk_overlap=co)
            all_chunks.extend(chunks)

        if not all_chunks:
            return 0

        # Generate embeddings for all chunks
        texts = [c.content for c in all_chunks]
        vectors = self.embedder.embed(texts)

        # Index into vector store (dense)
        self._vector_store.add(all_chunks, vectors)

        # Index into BM25 (sparse)
        combined = self._all_chunks + all_chunks
        self._all_chunks = combined
        self._bm25.index(combined)

        return len(all_chunks)

    # ----------------------------------------------------------------
    # Retrieval
    # ----------------------------------------------------------------

    def retrieve(
        self,
        query: str,
        top_k: int | None = None,
        strategy: str | None = None,
    ) -> list[dict[str, Any]]:
        """Retrieve relevant chunks using the specified strategy.

        Strategies:
          - "sparse": BM25 keyword matching
          - "dense": vector similarity search
          - "hybrid": combines both via Reciprocal Rank Fusion (RRF)

        Returns list of dicts with keys: content, doc_id, score, chunk_id, strategy.
        """
        k = top_k if top_k is not None else self.top_k
        strat = strategy if strategy is not None else self.default_strategy

        if strat == "sparse":
            results = self._sparse_retrieve(query, k)
        elif strat == "dense":
            results = self._dense_retrieve(query, k)
        elif strat == "hybrid":
            results = self._hybrid_retrieve(query, k)
        else:
            raise ValueError(f"Unknown retrieval strategy: {strat}")

        return [
            {
                "content": r.chunk.content,
                "doc_id": r.chunk.doc_id,
                "score": r.score,
                "chunk_id": r.chunk.chunk_id,
                "strategy": r.strategy,
                "metadata": r.chunk.metadata,
            }
            for r in results
        ]

    def _sparse_retrieve(self, query: str, top_k: int) -> list[RetrievalResult]:
        hits = self._bm25.search(query, top_k=top_k)
        return [RetrievalResult(chunk=c, score=s, strategy="sparse") for c, s in hits]

    def _dense_retrieve(self, query: str, top_k: int) -> list[RetrievalResult]:
        qv = self.embedder.embed_query(query)
        hits = self._vector_store.search(qv, top_k=top_k)
        return [RetrievalResult(chunk=c, score=s, strategy="dense") for c, s in hits]

    def _hybrid_retrieve(self, query: str, top_k: int) -> list[RetrievalResult]:
        """Hybrid retrieval with Reciprocal Rank Fusion (RRF).

        RRF combines sparse and dense rankings without requiring
        score normalization. Formula: RRF(d) = sum(1 / (k + rank_i(d)))
        """
        sparse_results = self._sparse_retrieve(query, top_k * 3)
        dense_results = self._dense_retrieve(query, top_k * 3)

        rrf_scores: dict[str, tuple[Chunk, float]] = {}
        rrf_k = 60  # RRF constant

        for rank, result in enumerate(sparse_results):
            key = result.chunk.chunk_id
            score = 1.0 / (rrf_k + rank + 1)
            rrf_scores[key] = (result.chunk, rrf_scores.get(key, (result.chunk, 0.0))[1] + score)

        for rank, result in enumerate(dense_results):
            key = result.chunk.chunk_id
            score = 1.0 / (rrf_k + rank + 1)
            rrf_scores[key] = (result.chunk, rrf_scores.get(key, (result.chunk, 0.0))[1] + score)

        sorted_results = sorted(rrf_scores.values(), key=lambda x: x[1], reverse=True)
        return [
            RetrievalResult(chunk=chunk, score=score, strategy="hybrid")
            for chunk, score in sorted_results[:top_k]
        ]

    # ----------------------------------------------------------------
    # Generation
    # ----------------------------------------------------------------

    def generate(
        self,
        query: str,
        context: str,
        model: str = "claude-sonnet-4-20250514",
    ) -> str:
        """Generate an answer using the provided context."""
        return self.generate_fn(query, context, model)

    # ----------------------------------------------------------------
    # End-to-end
    # ----------------------------------------------------------------

    def query(
        self,
        query: str,
        top_k: int | None = None,
        strategy: str | None = None,
        model: str = "claude-sonnet-4-20250514",
    ) -> dict[str, Any]:
        """End-to-end RAG query: retrieve + generate.

        Returns a dict with keys: answer, retrieved_chunks, strategy.
        """
        retrieved = self.retrieve(query, top_k=top_k, strategy=strategy)
        context = "\n\n---\n\n".join(
            f"[Source: {r['doc_id']}] {r['content']}" for r in retrieved
        )
        answer = self.generate(query, context, model=model)
        return {
            "answer": answer,
            "retrieved_chunks": retrieved,
            "strategy": strategy or self.default_strategy,
        }

    # ----------------------------------------------------------------
    # Management
    # ----------------------------------------------------------------

    def clear(self) -> None:
        """Reset all indexes and clear stored chunks."""
        self._vector_store.clear()
        self._bm25 = BM25()
        self._all_chunks.clear()

    @property
    def chunk_count(self) -> int:
        return len(self._all_chunks)


# ---------------------------------------------------------------------------
# Built-in Claude generation helper
# ---------------------------------------------------------------------------


class ClaudeGenerator:
    """Generate answers using the Anthropic Messages API.

    Convertible to a GeneratorCallable via __call__.
    """

    def __init__(
        self,
        api_key: str,
        base_url: str = "https://api.anthropic.com/v1/messages",
        api_version: str = "2023-06-01",
    ) -> None:
        self._api_key = api_key
        self._base_url = base_url
        self._api_version = api_version

    def __call__(self, query: str, context: str, model: str) -> str:
        return self.generate(query, context, model)

    def generate(self, query: str, context: str, model: str) -> str:
        import httpx

        system_prompt = (
            "You are a precise, factual assistant. Answer the user's question "
            "using ONLY the provided context. If the context does not contain "
            "sufficient information, state that clearly. Cite sources when possible."
        )

        user_message = (
            f"Context:\n{context}\n\n"
            f"Question: {query}\n\n"
            f"Answer based on the context above."
        )

        resp = httpx.post(
            self._base_url,
            headers={
                "x-api-key": self._api_key,
                "anthropic-version": self._api_version,
                "Content-Type": "application/json",
            },
            json={
                "model": model,
                "max_tokens": 1024,
                "system": system_prompt,
                "messages": [
                    {
                        "role": "user",
                        "content": [{"type": "text", "text": user_message}],
                    }
                ],
            },
            timeout=60.0,
        )
        resp.raise_for_status()
        data = resp.json()
        blocks = data.get("content", [])
        for block in blocks:
            if block.get("type") == "text":
                return block["text"]
        return ""
