"""
Tests for Chapter 10: Memory Client.
"""

import pytest

from memory_client import MemoryClient, Memory, MemoryStore, MemoryVersion, DreamResult


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def client() -> MemoryClient:
    return MemoryClient()


@pytest.fixture
def store_id(client: MemoryClient) -> str:
    return client.create_memory_store("Test Store", "A test memory store")


@pytest.fixture
def populated_store(client: MemoryClient, store_id: str) -> str:
    """Store with 3 memories in organized structure."""
    client.store_memory(store_id, "/preferences/formatting.md", "Use tabs, not spaces.")
    client.store_memory(store_id, "/preferences/language.md", "Prefer Python and TypeScript.")
    client.store_memory(store_id, "/errors/build.md", "Error: missing dependency X. Solution: pip install X.")
    return store_id


# ---------------------------------------------------------------------------
# Memory Store CRUD tests
# ---------------------------------------------------------------------------


class TestMemoryStoreCRUD:
    def test_create_store(self, client: MemoryClient) -> None:
        sid = client.create_memory_store("Test", "Description")
        assert sid.startswith("memstore_")
        store = client.get_memory_store(sid)
        assert store is not None
        assert store.name == "Test"
        assert store.description == "Description"
        assert store.created_at is not None
        assert store.archived_at is None
        assert not store.is_archived()

    def test_list_stores(self, client: MemoryClient) -> None:
        client.create_memory_store("A", "")
        client.create_memory_store("B", "")
        stores = client.list_memory_stores()
        assert len(stores) == 2
        names = [s.name for s in stores]
        assert "A" in names
        assert "B" in names

    def test_list_stores_excludes_archived(self, client: MemoryClient) -> None:
        sid1 = client.create_memory_store("Active", "")
        sid2 = client.create_memory_store("Archived", "")
        client.archive_memory_store(sid2)
        stores = client.list_memory_stores()
        assert len(stores) == 1
        assert stores[0].id == sid1

    def test_list_stores_include_archived(self, client: MemoryClient) -> None:
        sid1 = client.create_memory_store("Active", "")
        sid2 = client.create_memory_store("Archived", "")
        client.archive_memory_store(sid2)
        stores = client.list_memory_stores(include_archived=True)
        assert len(stores) == 2

    def test_get_missing_store(self, client: MemoryClient) -> None:
        assert client.get_memory_store("nonexistent") is None

    def test_archive_store(self, client: MemoryClient, store_id: str) -> None:
        client.archive_memory_store(store_id)
        store = client.get_memory_store(store_id)
        assert store is not None
        assert store.is_archived()
        assert store.archived_at is not None

    def test_archive_already_archived_raises(self, client: MemoryClient, store_id: str) -> None:
        client.archive_memory_store(store_id)
        with pytest.raises(ValueError, match="already archived"):
            client.archive_memory_store(store_id)

    def test_archive_nonexistent_raises(self, client: MemoryClient) -> None:
        with pytest.raises(ValueError, match="not found"):
            client.archive_memory_store("nonexistent")

    def test_delete_store(self, client: MemoryClient, store_id: str) -> None:
        client.delete_memory_store(store_id)
        assert client.get_memory_store(store_id) is None

    def test_delete_nonexistent_no_error(self, client: MemoryClient) -> None:
        client.delete_memory_store("nonexistent")  # Should not raise


# ---------------------------------------------------------------------------
# Memory CRUD tests
# ---------------------------------------------------------------------------


class TestMemoryCRUD:
    def test_store_memory(self, client: MemoryClient, store_id: str) -> None:
        mem_id = client.store_memory(store_id, "/test.md", "Hello world")
        assert mem_id.startswith("mem_")
        mem = client.retrieve_memory(store_id, mem_id)
        assert mem is not None
        assert mem.content == "Hello world"
        assert mem.path == "/test.md"
        assert mem.content_sha256
        assert mem.content_size_bytes > 0

    def test_store_memory_duplicate_path_raises(self, client: MemoryClient, store_id: str) -> None:
        client.store_memory(store_id, "/test.md", "First")
        with pytest.raises(ValueError, match="already exists"):
            client.store_memory(store_id, "/test.md", "Second")

    def test_write_memory_upsert(self, client: MemoryClient, store_id: str) -> None:
        # First write creates
        mem_id1 = client.write_memory(store_id, "/test.md", "Original")
        mem = client.retrieve_memory(store_id, mem_id1)
        assert mem is not None
        assert mem.content == "Original"
        # Second write updates
        mem_id2 = client.write_memory(store_id, "/test.md", "Updated")
        assert mem_id2 == mem_id1
        mem = client.retrieve_memory(store_id, mem_id2)
        assert mem is not None
        assert mem.content == "Updated"

    def test_write_memory_not_exists_precondition(self, client: MemoryClient, store_id: str) -> None:
        client.write_memory(store_id, "/test.md", "First")
        with pytest.raises(ValueError, match="not_exists"):
            client.write_memory(store_id, "/test.md", "Second", precondition={"type": "not_exists"})

    def test_store_into_archived_store_raises(self, client: MemoryClient, store_id: str) -> None:
        client.archive_memory_store(store_id)
        with pytest.raises(ValueError, match="archived"):
            client.store_memory(store_id, "/test.md", "content")

    def test_store_into_nonexistent_store_raises(self, client: MemoryClient) -> None:
        with pytest.raises(ValueError, match="not found"):
            client.store_memory("nonexistent", "/test.md", "content")

    def test_retrieve_missing_memory(self, client: MemoryClient, store_id: str) -> None:
        assert client.retrieve_memory(store_id, "nonexistent") is None

    def test_list_memories(self, client: MemoryClient, populated_store: str) -> None:
        memories = client.list_memories(populated_store)
        assert len(memories) == 3

    def test_list_memories_with_path_prefix(self, client: MemoryClient, populated_store: str) -> None:
        memories = client.list_memories(populated_store, path_prefix="/preferences/")
        assert len(memories) == 2
        paths = [m.path for m in memories]
        assert "/preferences/formatting.md" in paths
        assert "/preferences/language.md" in paths
        assert "/errors/build.md" not in paths

    def test_list_memories_desc_order(self, client: MemoryClient, populated_store: str) -> None:
        memories = client.list_memories(populated_store, order="desc")
        assert len(memories) == 3
        # Should be reverse alphabetical by path
        assert memories[0].path > memories[-1].path

    def test_update_memory_content(self, client: MemoryClient, store_id: str) -> None:
        mem_id = client.store_memory(store_id, "/test.md", "Original")
        client.update_memory(store_id, mem_id, content="Updated")
        mem = client.retrieve_memory(store_id, mem_id)
        assert mem is not None
        assert mem.content == "Updated"

    def test_update_memory_path(self, client: MemoryClient, store_id: str) -> None:
        mem_id = client.store_memory(store_id, "/test.md", "Original")
        client.update_memory(store_id, mem_id, path="/archive/test.md")
        mem = client.retrieve_memory(store_id, mem_id)
        assert mem is not None
        assert mem.path == "/archive/test.md"

    def test_update_content_sha256_precondition(self, client: MemoryClient, store_id: str) -> None:
        mem_id = client.store_memory(store_id, "/test.md", "Original")
        mem = client.retrieve_memory(store_id, mem_id)
        # Update with correct hash
        client.update_memory(
            store_id, mem_id, content="Updated",
            precondition={"type": "content_sha256", "content_sha256": mem.content_sha256},
        )
        assert client.retrieve_memory(store_id, mem_id).content == "Updated"

    def test_update_content_sha256_mismatch_raises(self, client: MemoryClient, store_id: str) -> None:
        mem_id = client.store_memory(store_id, "/test.md", "Original")
        with pytest.raises(ValueError, match="content_sha256 mismatch"):
            client.update_memory(
                store_id, mem_id, content="Updated",
                precondition={"type": "content_sha256", "content_sha256": "wrong_hash"},
            )

    def test_delete_memory(self, client: MemoryClient, store_id: str) -> None:
        mem_id = client.store_memory(store_id, "/test.md", "content")
        client.delete_memory(store_id, mem_id)
        assert client.retrieve_memory(store_id, mem_id) is None

    def test_delete_memory_conditional(self, client: MemoryClient, store_id: str) -> None:
        mem_id = client.store_memory(store_id, "/test.md", "content")
        mem = client.retrieve_memory(store_id, mem_id)
        client.delete_memory(store_id, mem_id, expected_content_sha256=mem.content_sha256)
        assert client.retrieve_memory(store_id, mem_id) is None

    def test_delete_memory_wrong_sha256_raises(self, client: MemoryClient, store_id: str) -> None:
        mem_id = client.store_memory(store_id, "/test.md", "content")
        with pytest.raises(ValueError, match="Conditional deletion failed"):
            client.delete_memory(store_id, mem_id, expected_content_sha256="wrong")


# ---------------------------------------------------------------------------
# Search tests
# ---------------------------------------------------------------------------


class TestSearch:
    def test_search_by_content(self, client: MemoryClient, populated_store: str) -> None:
        results = client.search_memories(populated_store, "tabs")
        assert len(results) == 1
        assert results[0].path == "/preferences/formatting.md"

    def test_search_by_path(self, client: MemoryClient, populated_store: str) -> None:
        results = client.search_memories(populated_store, "language")
        assert len(results) >= 1
        paths = [m.path for m in results]
        assert any("language" in p for p in paths)

    def test_search_no_results(self, client: MemoryClient, populated_store: str) -> None:
        results = client.search_memories(populated_store, "zzz_nonexistent")
        assert len(results) == 0

    def test_search_case_insensitive(self, client: MemoryClient, populated_store: str) -> None:
        results = client.search_memories(populated_store, "PYTHON")
        assert len(results) >= 1

    def test_search_empty_store(self, client: MemoryClient, store_id: str) -> None:
        results = client.search_memories(store_id, "anything")
        assert len(results) == 0


# ---------------------------------------------------------------------------
# Memory Version tests
# ---------------------------------------------------------------------------


class TestMemoryVersions:
    def test_version_created_on_store(self, client: MemoryClient, store_id: str) -> None:
        mem_id = client.store_memory(store_id, "/test.md", "v1")
        versions = client.list_versions(store_id)
        assert len(versions) >= 1
        create_versions = [v for v in versions if v.operation == "create"]
        assert len(create_versions) == 1
        assert create_versions[0].content == "v1"

    def test_version_created_on_update(self, client: MemoryClient, store_id: str) -> None:
        mem_id = client.store_memory(store_id, "/test.md", "v1")
        client.update_memory(store_id, mem_id, content="v2")
        versions = client.list_versions(store_id, memory_id=mem_id)
        assert len(versions) >= 2
        operations = [v.operation for v in versions]
        assert "create" in operations
        assert "update" in operations

    def test_filter_by_operation(self, client: MemoryClient, store_id: str) -> None:
        mem_id = client.store_memory(store_id, "/test.md", "v1")
        client.update_memory(store_id, mem_id, content="v2")
        updates = client.list_versions(store_id, operation="update")
        assert len(updates) == 1
        assert updates[0].operation == "update"

    def test_retrieve_version(self, client: MemoryClient, store_id: str) -> None:
        mem_id = client.store_memory(store_id, "/test.md", "original")
        versions = client.list_versions(store_id, memory_id=mem_id)
        version_id = versions[0].id
        v = client.retrieve_version(store_id, version_id)
        assert v is not None
        assert v.content == "original"

    def test_version_outlives_deleted_memory(self, client: MemoryClient, store_id: str) -> None:
        mem_id = client.store_memory(store_id, "/test.md", "content")
        client.delete_memory(store_id, mem_id)
        versions = client.list_versions(store_id)
        assert len(versions) >= 2  # create + delete versions survive

    def test_rollback_memory(self, client: MemoryClient, store_id: str) -> None:
        mem_id = client.store_memory(store_id, "/test.md", "v1")
        client.update_memory(store_id, mem_id, content="v2")
        # Find the "create" version (v1)
        versions = client.list_versions(store_id, memory_id=mem_id, operation="create")
        v1_version_id = versions[0].id
        client.rollback_memory(store_id, mem_id, v1_version_id)
        mem = client.retrieve_memory(store_id, mem_id)
        assert mem is not None
        assert mem.content == "v1"

    def test_redact_version(self, client: MemoryClient, store_id: str) -> None:
        mem_id = client.store_memory(store_id, "/test.md", "sensitive content")
        # Create a second version so the first is no longer head
        client.update_memory(store_id, mem_id, content="safe content")
        versions = client.list_versions(store_id, memory_id=mem_id, operation="create")
        old_version_id = versions[0].id
        client.redact_version(store_id, old_version_id)
        v = client.retrieve_version(store_id, old_version_id)
        assert v is not None
        assert v.content == "[REDACTED]"

    def test_redact_head_version_raises(self, client: MemoryClient, store_id: str) -> None:
        mem_id = client.store_memory(store_id, "/test.md", "content")
        mem = client.retrieve_memory(store_id, mem_id)
        head_version_id = mem.memory_version_id
        with pytest.raises(ValueError, match="current head"):
            client.redact_version(store_id, head_version_id)


# ---------------------------------------------------------------------------
# Dreaming tests
# ---------------------------------------------------------------------------


class TestDreaming:
    def test_start_dream(self, client: MemoryClient, populated_store: str) -> None:
        result = client.start_dream(populated_store)
        assert result.dream_id.startswith("dream_")
        assert result.output_store_id.startswith("memstore_")
        assert result.status == "completed"

    def test_dream_deduplicates(self, client: MemoryClient, store_id: str) -> None:
        # Create duplicate content
        client.store_memory(store_id, "/a.md", "Same content")
        client.store_memory(store_id, "/b.md", "Same content")
        client.store_memory(store_id, "/c.md", "Different")
        result = client.start_dream(store_id)
        output_mems = client.list_memories(result.output_store_id)
        # Should have 2 memories: one "Same content" + "Different"
        assert len(output_mems) == 2

    def test_dream_nonexistent_store_raises(self, client: MemoryClient) -> None:
        with pytest.raises(ValueError, match="not found"):
            client.start_dream("nonexistent")

    def test_dream_output_is_new_store(self, client: MemoryClient, populated_store: str) -> None:
        result = client.start_dream(populated_store)
        # Output should be a different store
        assert result.output_store_id != populated_store
        # Original store should be untouched
        orig_mems = client.list_memories(populated_store)
        assert len(orig_mems) == 3

    def test_dream_with_sessions(self, client: MemoryClient, populated_store: str) -> None:
        result = client.start_dream(
            populated_store,
            session_ids=["session_1", "session_2"],
            instructions="Focus on code preferences",
        )
        assert result.status == "completed"


# ---------------------------------------------------------------------------
# Memory limit tests
# ---------------------------------------------------------------------------


class TestMemoryLimits:
    def test_content_size_limit(self, client: MemoryClient, store_id: str) -> None:
        with pytest.raises(ValueError, match="100 KB"):
            client.store_memory(store_id, "/big.md", "x" * (100 * 1024 + 1))

    def test_content_at_limit(self, client: MemoryClient, store_id: str) -> None:
        mem_id = client.store_memory(store_id, "/exact.md", "x" * (100 * 1024))
        mem = client.retrieve_memory(store_id, mem_id)
        assert mem is not None
        assert mem.content_size_bytes == 100 * 1024
