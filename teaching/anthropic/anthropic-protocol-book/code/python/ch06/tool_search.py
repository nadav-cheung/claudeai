"""
Chapter 6: Embedding-based Tool Search.

Implements semantic tool discovery using cosine similarity over
embedding vectors. Supports on-demand tool loading for large tool
libraries, matching the behavior of Anthropic's Tool Search Tool
with custom embedding-based search.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple
import re as _re


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------


@dataclass
class ToolSearchEntry:
    """A single tool in the search index."""

    name: str
    description: str
    input_schema: Dict[str, Any]

    def to_search_text(self) -> str:
        """Build the full-text representation used for embedding generation.

        Concatenates the tool name, description, and all parameter
        names plus their descriptions. This provides the search engine
        with a rich surface for semantic matching.
        """
        parts: List[str] = [self.name, self.description]

        props = self.input_schema.get("properties", {})
        for prop_name, prop_def in props.items():
            parts.append(prop_name)
            if isinstance(prop_def, dict):
                desc = prop_def.get("description", "")
                if desc:
                    parts.append(desc)

        return " ".join(parts)


# ---------------------------------------------------------------------------
# Search engine
# ---------------------------------------------------------------------------


class EmbeddingToolSearch:
    """Semantic tool search using embedding-based cosine similarity.

    Designed to mirror Anthropic's Tool Search Tool behavior --
    discover tools on-demand rather than loading all definitions
    into the context window.

    Supports two search modes:
    1. **Semantic**: cosine similarity over hash-based embedding vectors.
    2. **Regex**: direct pattern matching against tool metadata.

    Usage::

        search = EmbeddingToolSearch(embedding_dim=384)
        search.index_tools([
            {"name": "get_weather", "description": "...", "input_schema": {...}},
            {"name": "get_time", "description": "...", "input_schema": {...}},
        ])
        results = search.search("weather forecast", top_k=3)
    """

    def __init__(self, embedding_dim: int = 384) -> None:
        """Initialize the search engine.

        Args:
            embedding_dim: Dimensionality of the embedding vectors.
                Default 384 matches MiniLM-L6-v2. Use 768 for larger models.
        """
        if embedding_dim <= 0:
            raise ValueError("embedding_dim must be positive")
        self._tools: List[ToolSearchEntry] = []
        self._embeddings: Optional[List[List[float]]] = None
        self._embedding_dim = embedding_dim

    # ------------------------------------------------------------------
    # Indexing
    # ------------------------------------------------------------------

    def index_tools(self, tools: List[Dict[str, Any]]) -> None:
        """Build the search index from tool definitions.

        Generates embedding vectors for each tool's search text.
        In production, replace ``_compute_embeddings`` with a call
        to a real embedding model (e.g., ``text-embedding-3-small``,
        ``MiniLM-L6-v2``).

        Args:
            tools: List of tool dicts with ``name``, ``description``,
                   and ``input_schema`` keys.
        """
        self._tools.clear()

        for tool in tools:
            entry = ToolSearchEntry(
                name=tool["name"],
                description=tool.get("description", ""),
                input_schema=tool.get(
                    "input_schema", {"type": "object", "properties": {}}
                ),
            )
            self._tools.append(entry)

        # Generate embeddings for all tools
        search_texts = [t.to_search_text() for t in self._tools]
        self._embeddings = self._compute_embeddings(search_texts)

    def _compute_embeddings(self, texts: List[str]) -> List[List[float]]:
        """Compute embedding vectors for a list of texts.

        Uses a hash-based frequency vector approach for deterministic
        testing. In production, this would be replaced by a call to
        a real embedding model API (e.g., Voyage AI, OpenAI embeddings).

        The hash-based approach ensures:
        - Identical texts produce identical vectors
        - Similar texts produce similar vectors (via shared tokens)
        - Vectors are normalized to unit length for cosine similarity
        """
        dim = self._embedding_dim
        embeddings: List[List[float]] = []

        for text in texts:
            tokens = text.lower().split()
            vec = [0.0] * dim

            for token in tokens:
                idx = hash(token) % dim
                vec[idx] += 1.0

            # L2 normalize
            norm = sum(v * v for v in vec) ** 0.5
            if norm > 0:
                vec = [v / norm for v in vec]

            embeddings.append(vec)

        return embeddings

    # ------------------------------------------------------------------
    # Search
    # ------------------------------------------------------------------

    def search(self, query: str, top_k: int = 5) -> List[Dict[str, Any]]:
        """Search for tools relevant to a natural-language query.

        Generates an embedding for the query and computes cosine
        similarity against all indexed tool embeddings.

        Args:
            query: Natural language description of the desired capability.
            top_k: Maximum number of results to return.

        Returns:
            List of result dicts sorted by descending score, each containing
            ``name``, ``description``, ``input_schema``, and ``score`` (0-1).
        """
        if not self._tools or self._embeddings is None:
            return []

        query_embedding = self._compute_embeddings([query])[0]

        # Compute pairwise similarities
        scored: List[Tuple[int, float]] = []
        for i, emb in enumerate(self._embeddings):
            sim = self._cosine_similarity(query_embedding, emb)
            scored.append((i, sim))

        # Sort by score descending
        scored.sort(key=lambda x: x[1], reverse=True)

        results: List[Dict[str, Any]] = []
        for idx, score in scored[:top_k]:
            if score > 0:
                tool = self._tools[idx]
                results.append(
                    {
                        "name": tool.name,
                        "description": tool.description,
                        "input_schema": tool.input_schema,
                        "score": round(score, 4),
                    }
                )

        return results

    def search_by_regex(self, pattern: str) -> List[Dict[str, Any]]:
        """Search for tools using Python regex (mirrors the Regex variant
        of Anthropic's Tool Search Tool).

        Matches the pattern against the full search text of each tool
        (name + description + parameter names + parameter descriptions).

        Args:
            pattern: Python regex pattern (e.g., ``"(?i)weather"``).

        Returns:
            Matching tool definitions.
        """
        results: List[Dict[str, Any]] = []
        for tool in self._tools:
            search_text = tool.to_search_text()
            if _re.search(pattern, search_text):
                results.append(
                    {
                        "name": tool.name,
                        "description": tool.description,
                        "input_schema": tool.input_schema,
                    }
                )
        return results

    # ------------------------------------------------------------------
    # Utilities
    # ------------------------------------------------------------------

    @staticmethod
    def _cosine_similarity(a: List[float], b: List[float]) -> float:
        """Compute cosine similarity between two vectors.

        Returns a value between -1 and 1, where 1 means identical
        direction and 0 means orthogonal.
        """
        if len(a) != len(b):
            raise ValueError(
                f"Vector dimension mismatch: {len(a)} vs {len(b)}"
            )

        dot_product = sum(x * y for x, y in zip(a, b))
        norm_a = sum(x * x for x in a) ** 0.5
        norm_b = sum(x * x for x in b) ** 0.5

        if norm_a == 0.0 or norm_b == 0.0:
            return 0.0

        return dot_product / (norm_a * norm_b)

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def tool_count(self) -> int:
        """Number of tools in the index."""
        return len(self._tools)

    @property
    def embedding_dim(self) -> int:
        """Current embedding dimension."""
        return self._embedding_dim

    @property
    def is_indexed(self) -> bool:
        """Whether the index has been built."""
        return self._embeddings is not None and len(self._tools) > 0
