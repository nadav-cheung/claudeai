"""
Chapter 10: Memory Client.

Protocol-level implementation of Anthropic's Memory API for
Claude Managed Agents, providing Memory Store management,
Memory CRUD, Version audit trail, and Dreaming integration.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional


# ---------------------------------------------------------------------------
# Data Models
# ---------------------------------------------------------------------------


@dataclass
class MemoryStore:
    """Represents a Memory Store in the Anthropic API."""

    id: str  # memstore_...
    name: str
    description: str = ""
    created_at: Optional[str] = None
    archived_at: Optional[str] = None

    def is_archived(self) -> bool:
        return self.archived_at is not None


@dataclass
class Memory:
    """Represents a single Memory within a Memory Store."""

    id: str  # mem_...
    memory_store_id: str
    path: str
    content: str
    content_sha256: str = ""
    content_size_bytes: int = 0
    memory_version_id: str = ""  # memver_...
    created_at: Optional[str] = None
    updated_at: Optional[str] = None

    @property
    def type(self) -> str:
        return "memory"


@dataclass
class MemoryVersion:
    """An immutable snapshot of a Memory at a point in time."""

    id: str  # memver_...
    memory_id: str
    memory_store_id: str
    content: str
    operation: str  # "create" | "update" | "delete"
    session_id: str = ""
    created_at: Optional[str] = None


@dataclass
class DreamResult:
    """Result of a Dreaming consolidation job."""

    dream_id: str
    output_store_id: str
    status: str  # "running" | "completed" | "failed"
    merged_count: int = 0
    updated_count: int = 0
    deleted_count: int = 0
    patterns_found: List[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Simulated Store (standalone, no network calls)
# ---------------------------------------------------------------------------


class MemoryClient:
    """Client for Anthropic Memory API.

    Manages Memory Stores, Memories, Versions, and Dreaming operations.
    This is a protocol-level implementation using in-memory storage
    for illustration and testing purposes. In production, these methods
    map to the REST API endpoints documented at:
    https://platform.claude.com/docs/en/managed-agents/memory

    Usage::

        client = MemoryClient()
        store_id = client.create_memory_store("User Preferences", "Per-user prefs")
        mem_id = client.store_memory(store_id, "/formatting.md", "Use tabs")
        mems = client.search_memories(store_id, "tabs")
        client.delete_memory(store_id, mem_id)
    """

    def __init__(self) -> None:
        self._stores: Dict[str, MemoryStore] = {}
        self._memories: Dict[str, Dict[str, Memory]] = {}  # store_id -> {memory_id: Memory}
        self._versions: Dict[str, List[MemoryVersion]] = {}  # store_id -> [versions]
        self._id_counter: int = 0

    def _next_id(self, prefix: str) -> str:
        self._id_counter += 1
        return f"{prefix}_{self._id_counter:04d}"

    # ------------------------------------------------------------------
    # Memory Store CRUD
    # ------------------------------------------------------------------

    def create_memory_store(self, name: str, description: str = "") -> str:
        """Create a new Memory Store.

        Maps to: ``POST /v1/memory_stores``
        SDK: ``client.beta.memory_stores.create(name, description)``

        Args:
            name: Human-readable store name.
            description: Description passed to the agent about this store's purpose.

        Returns:
            The store ID (``memstore_...``).
        """
        store_id = self._next_id("memstore")
        now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        self._stores[store_id] = MemoryStore(
            id=store_id,
            name=name,
            description=description,
            created_at=now,
        )
        self._memories[store_id] = {}
        self._versions[store_id] = []
        return store_id

    def list_memory_stores(self, include_archived: bool = False) -> List[MemoryStore]:
        """List all Memory Stores in the workspace.

        Maps to: ``GET /v1/memory_stores``
        SDK: ``client.beta.memory_stores.list(include_archived=...)``
        """
        stores = list(self._stores.values())
        if not include_archived:
            stores = [s for s in stores if not s.is_archived()]
        return stores

    def get_memory_store(self, store_id: str) -> Optional[MemoryStore]:
        """Retrieve a single Memory Store by ID.

        Maps to: ``GET /v1/memory_stores/{id}``
        """
        return self._stores.get(store_id)

    def archive_memory_store(self, store_id: str) -> None:
        """Archive a Memory Store (one-way, irreversible).

        Maps to: ``POST /v1/memory_stores/{id}/archive``
        SDK: ``client.beta.memory_stores.archive(id)``

        After archiving, the store becomes read-only and cannot be
        attached to new sessions.
        """
        store = self._stores.get(store_id)
        if store is None:
            raise ValueError(f"Memory store '{store_id}' not found")
        if store.is_archived():
            raise ValueError(f"Memory store '{store_id}' is already archived")
        store.archived_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

    def delete_memory_store(self, store_id: str) -> None:
        """Permanently delete a Memory Store and all its memories and versions.

        Maps to: ``DELETE /v1/memory_stores/{id}``
        SDK: ``client.beta.memory_stores.delete(id)``
        """
        self._stores.pop(store_id, None)
        self._memories.pop(store_id, None)
        self._versions.pop(store_id, None)

    # ------------------------------------------------------------------
    # Memory CRUD
    # ------------------------------------------------------------------

    def store_memory(
        self,
        store_id: str,
        path: str,
        content: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Create a new Memory in a Store. Does NOT overwrite existing.

        Maps to: ``POST /v1/memory_stores/{store_id}/memories``
        SDK: ``client.beta.memory_stores.memories.create(store_id, path, content)``

        Args:
            store_id: The store to write to.
            path: Memory path (e.g., ``/preferences/formatting.md``).
            content: Text content (max 100 KB).
            metadata: Optional metadata (stored as structured comment in content).

        Returns:
            The memory ID (``mem_...``).

        Raises:
            ValueError: If store not found, archived, or path already exists.
        """
        self._ensure_store_active(store_id)

        # Check for existing memory at this path
        existing = self._find_by_path(store_id, path)
        if existing is not None:
            raise ValueError(f"Memory already exists at path '{path}'. Use update_memory() to modify.")

        return self._create_memory_internal(store_id, path, content)

    def write_memory(
        self,
        store_id: str,
        path: str,
        content: str,
        precondition: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Upsert a Memory: creates or overwrites at the given path.

        Maps to: SDK ``client.beta.memory_stores.memories.write(...)``

        Args:
            store_id: The store to write to.
            path: Memory path.
            content: Text content.
            precondition: Optional, e.g., ``{"type": "not_exists"}``.

        Returns:
            The memory ID.
        """
        self._ensure_store_active(store_id)

        if precondition and precondition.get("type") == "not_exists":
            existing = self._find_by_path(store_id, path)
            if existing is not None:
                raise ValueError(f"Precondition 'not_exists' failed: path '{path}' already exists")

        existing = self._find_by_path(store_id, path)
        if existing is not None:
            return self.update_memory(store_id, existing.id, content=content)
        return self._create_memory_internal(store_id, path, content)

    def retrieve_memory(self, store_id: str, memory_id: str) -> Optional[Memory]:
        """Retrieve a single Memory by ID.

        Maps to: ``GET /v1/memory_stores/{store_id}/memories/{memory_id}``
        SDK: ``client.beta.memory_stores.memories.retrieve(memory_id, store_id)``
        """
        store_mems = self._memories.get(store_id, {})
        return store_mems.get(memory_id)

    def list_memories(
        self,
        store_id: str,
        path_prefix: Optional[str] = None,
        limit: int = 20,
        order_by: str = "path",
        order: str = "asc",
    ) -> List[Memory]:
        """List memories in a store, optionally filtered by path_prefix.

        Maps to: ``GET /v1/memory_stores/{store_id}/memories``
        SDK: ``client.beta.memory_stores.memories.list(store_id, path_prefix, ...)``

        Args:
            store_id: The store to list.
            path_prefix: Optional path prefix filter (directory-scoped with trailing ``/``).
            limit: Maximum number of results.
            order_by: Sort field (``"path"`` or ``"created_at"``).
            order: ``"asc"`` or ``"desc"``.
        """
        store_mems = self._memories.get(store_id, {})
        memories = list(store_mems.values())

        if path_prefix is not None:
            memories = [m for m in memories if m.path.startswith(path_prefix)]

        # Sort
        reverse = order == "desc"
        if order_by == "created_at":
            memories.sort(key=lambda m: m.created_at or "", reverse=reverse)
        else:
            memories.sort(key=lambda m: m.path, reverse=reverse)

        return memories[:limit]

    def update_memory(
        self,
        store_id: str,
        memory_id: str,
        content: Optional[str] = None,
        path: Optional[str] = None,
        precondition: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Update an existing Memory.

        Maps to: SDK ``client.beta.memory_stores.memories.update(...)``

        Args:
            store_id: The store containing the memory.
            memory_id: The memory to update.
            content: New content (optional).
            path: New path / rename (optional).
            precondition: Optional ``{"type": "content_sha256", "content_sha256": "..."}``.

        Returns:
            The memory ID.

        Raises:
            ValueError: If precondition fails or memory not found.
        """
        self._ensure_store_active(store_id)

        store_mems = self._memories.get(store_id, {})
        mem = store_mems.get(memory_id)
        if mem is None:
            raise ValueError(f"Memory '{memory_id}' not found in store '{store_id}'")

        # Check precondition
        if precondition and precondition.get("type") == "content_sha256":
            expected = precondition.get("content_sha256", "")
            if mem.content_sha256 != expected:
                raise ValueError(
                    f"Precondition failed: content_sha256 mismatch. "
                    f"Expected {expected[:12]}..., got {mem.content_sha256[:12]}..."
                )

        old_content = mem.content
        if content is not None:
            mem.content = content
        if path is not None:
            mem.path = path

        mem.content_sha256 = self._sha256(mem.content)
        mem.content_size_bytes = len(mem.content.encode("utf-8"))
        now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        mem.updated_at = now

        # Record version and update head pointer
        new_version_id = self._record_version(
            store_id,
            memory_id=memory_id,
            content=old_content,
            operation="update",
        )
        mem.memory_version_id = new_version_id

        return memory_id

    def delete_memory(
        self,
        store_id: str,
        memory_id: str,
        expected_content_sha256: Optional[str] = None,
    ) -> None:
        """Delete a Memory.

        Maps to: SDK ``client.beta.memory_stores.memories.delete(memory_id, store_id)``

        Args:
            store_id: The store containing the memory.
            memory_id: The memory to delete.
            expected_content_sha256: Optional conditional deletion guard.

        Raises:
            ValueError: If SHA256 mismatch or memory not found.
        """
        store_mems = self._memories.get(store_id, {})
        mem = store_mems.get(memory_id)
        if mem is None:
            raise ValueError(f"Memory '{memory_id}' not found in store '{store_id}'")

        if expected_content_sha256 and mem.content_sha256 != expected_content_sha256:
            raise ValueError("Conditional deletion failed: content_sha256 mismatch")

        # Record version before deleting
        self._record_version(
            store_id,
            memory_id=memory_id,
            content=mem.content,
            operation="delete",
        )
        del store_mems[memory_id]

    def search_memories(self, store_id: str, query: str) -> List[Memory]:
        """Full-text search across memories in a store.

        Simple substring match implementation. In production, this maps
        to listing memories with path_prefix filtering, combined with
        client-side content search.

        Args:
            store_id: The store to search.
            query: Search query string (substring match on path and content).

        Returns:
            Matching memories, ranked by relevance (path match > content match).
        """
        store_mems = self._memories.get(store_id, {})
        query_lower = query.lower()
        results: List[Memory] = []

        for mem in store_mems.values():
            score = 0
            if query_lower in mem.path.lower():
                score += 10
            if query_lower in mem.content.lower():
                score += 5
            if score > 0:
                results.append((score, mem))

        results.sort(key=lambda x: x[0], reverse=True)
        return [mem for _, mem in results]

    # ------------------------------------------------------------------
    # Memory Version Audit
    # ------------------------------------------------------------------

    def list_versions(
        self,
        store_id: str,
        memory_id: Optional[str] = None,
        operation: Optional[str] = None,
    ) -> List[MemoryVersion]:
        """List memory versions for audit purposes.

        Maps to: SDK ``client.beta.memory_stores.memory_versions.list(store_id, ...)``

        Args:
            store_id: The store to query.
            memory_id: Optional filter by specific memory.
            operation: Optional filter by operation type (``"create"``, ``"update"``, ``"delete"``).

        Returns:
            Versions in newest-first order.
        """
        versions = self._versions.get(store_id, [])
        if memory_id is not None:
            versions = [v for v in versions if v.memory_id == memory_id]
        if operation is not None:
            versions = [v for v in versions if v.operation == operation]
        return sorted(versions, key=lambda v: v.created_at or "", reverse=True)

    def retrieve_version(self, store_id: str, version_id: str) -> Optional[MemoryVersion]:
        """Retrieve a specific version's full content.

        Maps to: SDK ``client.beta.memory_stores.memory_versions.retrieve(version_id, store_id)``
        """
        versions = self._versions.get(store_id, [])
        for v in versions:
            if v.id == version_id:
                return v
        return None

    def redact_version(self, store_id: str, version_id: str) -> None:
        """Redact content from a historical version while keeping audit metadata.

        Maps to: SDK ``client.beta.memory_stores.memory_versions.redact(version_id, store_id)``

        A version that is the current head of a live memory cannot be redacted.
        """
        versions = self._versions.get(store_id, [])
        for v in versions:
            if v.id == version_id:
                # Check if this is the current head
                store_mems = self._memories.get(store_id, {})
                mem = store_mems.get(v.memory_id)
                if mem is not None and mem.memory_version_id == version_id:
                    raise ValueError(
                        f"Cannot redact version '{version_id}': it is the current head "
                        f"of memory '{v.memory_id}'. Write a new version first."
                    )
                v.content = "[REDACTED]"
                return
        raise ValueError(f"Version '{version_id}' not found in store '{store_id}'")

    def rollback_memory(self, store_id: str, memory_id: str, version_id: str) -> str:
        """Rollback a memory to a previous version.

        There is no dedicated restore endpoint. This retrieves the version
        content and writes it back via update.

        Args:
            store_id: The store containing the memory.
            memory_id: The memory to rollback.
            version_id: The target version to restore.

        Returns:
            The memory ID.
        """
        version = self.retrieve_version(store_id, version_id)
        if version is None:
            raise ValueError(f"Version '{version_id}' not found")
        if version.memory_id != memory_id:
            raise ValueError(
                f"Version '{version_id}' belongs to memory '{version.memory_id}', "
                f"not '{memory_id}'"
            )
        return self.update_memory(store_id, memory_id, content=version.content)

    # ------------------------------------------------------------------
    # Dreaming
    # ------------------------------------------------------------------

    def start_dream(
        self,
        source_store_id: str,
        session_ids: Optional[List[str]] = None,
        instructions: str = "",
    ) -> DreamResult:
        """Start a Dreaming consolidation job.

        Maps to: ``POST /v1/dreams`` (requires ``dreaming-2026-04-21`` beta header)

        Dreaming reads the source store and up to 100 session transcripts,
        then produces a NEW store with merged facts, removed contradictions,
        and surfaced patterns. The source store is never modified.

        Args:
            source_store_id: The store to analyze and optimize.
            session_ids: Optional list of session transcripts (max 100).
            instructions: Optional guidance for the dream (max 4096 chars).

        Returns:
            DreamResult with the dream ID and output store ID.
        """
        if source_store_id not in self._stores:
            raise ValueError(f"Source store '{source_store_id}' not found")

        if len(instructions) > 4096:
            raise ValueError("Instructions must be 4,096 characters or fewer")

        dream_id = self._next_id("dream")
        output_store_id = self.create_memory_store(
            name=f"Dream Output ({dream_id})",
            description=f"Optimized memory from {source_store_id}",
        )

        # Simulated consolidation: copy non-duplicate content from source
        source_mems = self._memories.get(source_store_id, {})
        seen_hashes: Dict[str, str] = {}  # sha256 -> memory_id
        dupes_removed = 0

        for mem in source_mems.values():
            if mem.content_sha256 in seen_hashes:
                dupes_removed += 1
                continue
            seen_hashes[mem.content_sha256] = mem.id
            self._create_memory_internal(output_store_id, mem.path, mem.content)

        return DreamResult(
            dream_id=dream_id,
            output_store_id=output_store_id,
            status="completed",
            merged_count=dupes_removed,
            updated_count=0,
            deleted_count=0,
            patterns_found=["Consolidated duplicate memories"],
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _ensure_store_active(self, store_id: str) -> None:
        store = self._stores.get(store_id)
        if store is None:
            raise ValueError(f"Memory store '{store_id}' not found")
        if store.is_archived():
            raise ValueError(f"Memory store '{store_id}' is archived (read-only)")

    def _find_by_path(self, store_id: str, path: str) -> Optional[Memory]:
        store_mems = self._memories.get(store_id, {})
        for mem in store_mems.values():
            if mem.path == path:
                return mem
        return None

    def _create_memory_internal(self, store_id: str, path: str, content: str) -> str:
        if len(content.encode("utf-8")) > 100 * 1024:
            raise ValueError("Memory content exceeds 100 KB limit")

        memory_id = self._next_id("mem")
        sha = self._sha256(content)
        now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

        # Record version first so memory_version_id matches the actual version
        version_id = self._record_version(store_id, memory_id, content, "create")

        mem = Memory(
            id=memory_id,
            memory_store_id=store_id,
            path=path,
            content=content,
            content_sha256=sha,
            content_size_bytes=len(content.encode("utf-8")),
            memory_version_id=version_id,
            created_at=now,
            updated_at=now,
        )
        self._memories[store_id][memory_id] = mem
        return memory_id

    def _record_version(
        self,
        store_id: str,
        memory_id: str,
        content: str,
        operation: str,
    ) -> str:
        version_id = self._next_id("memver")
        now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        version = MemoryVersion(
            id=version_id,
            memory_id=memory_id,
            memory_store_id=store_id,
            content=content,
            operation=operation,
            created_at=now,
        )
        self._versions.setdefault(store_id, []).append(version)
        return version_id

    @staticmethod
    def _sha256(s: str) -> str:
        import hashlib

        return hashlib.sha256(s.encode("utf-8")).hexdigest()
