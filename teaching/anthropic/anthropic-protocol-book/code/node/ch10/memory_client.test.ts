/**
 * Tests for Chapter 10: Memory Client (TypeScript).
 */

import { describe, it, expect, beforeEach } from "vitest";
import { MemoryClient } from "./MemoryClient";

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------

function populatedClient(): { client: MemoryClient; storeId: string } {
  const client = new MemoryClient();
  const storeId = client.createMemoryStore("Test Store", "A test memory store");
  client.storeMemory(storeId, "/preferences/formatting.md", "Use tabs, not spaces.");
  client.storeMemory(storeId, "/preferences/language.md", "Prefer Python and TypeScript.");
  client.storeMemory(storeId, "/errors/build.md", "Error: missing dependency X. Solution: pip install X.");
  return { client, storeId };
}

// ---------------------------------------------------------------------------
// Memory Store CRUD
// ---------------------------------------------------------------------------

describe("Memory Store CRUD", () => {
  it("creates a memory store", () => {
    const client = new MemoryClient();
    const storeId = client.createMemoryStore("Test", "Description");
    expect(storeId).toMatch(/^memstore_/);
    const store = client.getMemoryStore(storeId);
    expect(store).toBeDefined();
    expect(store!.name).toBe("Test");
    expect(store!.description).toBe("Description");
    expect(store!.created_at).toBeDefined();
    expect(store!.archived_at).toBeNull();
  });

  it("lists stores (excluding archived)", () => {
    const client = new MemoryClient();
    client.createMemoryStore("A", "");
    client.createMemoryStore("B", "");
    const stores = client.listMemoryStores();
    expect(stores).toHaveLength(2);
    const names = stores.map((s) => s.name);
    expect(names).toContain("A");
    expect(names).toContain("B");
  });

  it("lists stores including archived", () => {
    const client = new MemoryClient();
    client.createMemoryStore("Active", "");
    const archivedId = client.createMemoryStore("Archived", "");
    client.archiveMemoryStore(archivedId);
    expect(client.listMemoryStores()).toHaveLength(1);
    expect(client.listMemoryStores(true)).toHaveLength(2);
  });

  it("returns undefined for missing store", () => {
    const client = new MemoryClient();
    expect(client.getMemoryStore("nonexistent")).toBeUndefined();
  });

  it("archives a store", () => {
    const client = new MemoryClient();
    const storeId = client.createMemoryStore("Test", "");
    client.archiveMemoryStore(storeId);
    const store = client.getMemoryStore(storeId);
    expect(store!.archived_at).toBeDefined();
  });

  it("throws when archiving already-archived store", () => {
    const client = new MemoryClient();
    const storeId = client.createMemoryStore("Test", "");
    client.archiveMemoryStore(storeId);
    expect(() => client.archiveMemoryStore(storeId)).toThrow(/already archived/);
  });

  it("throws when archiving nonexistent store", () => {
    const client = new MemoryClient();
    expect(() => client.archiveMemoryStore("nonexistent")).toThrow(/not found/);
  });

  it("deletes a store", () => {
    const client = new MemoryClient();
    const storeId = client.createMemoryStore("Test", "");
    client.deleteMemoryStore(storeId);
    expect(client.getMemoryStore(storeId)).toBeUndefined();
  });
});

// ---------------------------------------------------------------------------
// Memory CRUD
// ---------------------------------------------------------------------------

describe("Memory CRUD", () => {
  it("stores a memory", () => {
    const { client, storeId } = populatedClient();
    const memId = client.storeMemory(storeId, "/test.md", "Hello world");
    expect(memId).toMatch(/^mem_/);
    const mem = client.retrieveMemory(storeId, memId);
    expect(mem).toBeDefined();
    expect(mem!.content).toBe("Hello world");
    expect(mem!.path).toBe("/test.md");
  });

  it("throws on duplicate path", () => {
    const { client, storeId } = populatedClient();
    client.storeMemory(storeId, "/test.md", "First");
    expect(() => client.storeMemory(storeId, "/test.md", "Second")).toThrow(/already exists/);
  });

  it("writeMemory upserts", () => {
    const { client, storeId } = populatedClient();
    const id1 = client.writeMemory(storeId, "/test.md", "Original");
    const mem = client.retrieveMemory(storeId, id1);
    expect(mem!.content).toBe("Original");
    const id2 = client.writeMemory(storeId, "/test.md", "Updated");
    expect(id2).toBe(id1);
    const updated = client.retrieveMemory(storeId, id2);
    expect(updated!.content).toBe("Updated");
  });

  it("writeMemory with not_exists precondition", () => {
    const { client, storeId } = populatedClient();
    client.writeMemory(storeId, "/test.md", "First");
    expect(() =>
      client.writeMemory(storeId, "/test.md", "Second", { type: "not_exists" }),
    ).toThrow(/not_exists/);
  });

  it("throws storing into archived store", () => {
    const client = new MemoryClient();
    const storeId = client.createMemoryStore("Test", "");
    client.archiveMemoryStore(storeId);
    expect(() => client.storeMemory(storeId, "/test.md", "content")).toThrow(/archived/);
  });

  it("throws storing into nonexistent store", () => {
    const client = new MemoryClient();
    expect(() => client.storeMemory("nonexistent", "/test.md", "content")).toThrow(/not found/);
  });

  it("retrieveMemory returns undefined for missing", () => {
    const { client, storeId } = populatedClient();
    expect(client.retrieveMemory(storeId, "nonexistent")).toBeUndefined();
  });

  it("lists memories", () => {
    const { client, storeId } = populatedClient();
    const memories = client.listMemories(storeId);
    // The original 3 from fixture
    expect(memories.length).toBeGreaterThanOrEqual(3);
  });

  it("lists memories with path_prefix", () => {
    const { client, storeId } = populatedClient();
    const memories = client.listMemories(storeId, { path_prefix: "/preferences/" });
    const paths = memories.map((m) => m.path);
    expect(paths).toContain("/preferences/formatting.md");
    expect(paths).toContain("/preferences/language.md");
    expect(paths).not.toContain("/errors/build.md");
  });

  it("lists memories in desc order", () => {
    const { client, storeId } = populatedClient();
    const memories = client.listMemories(storeId, { order: "desc" });
    expect(memories.length).toBeGreaterThan(1);
    expect(memories[0]!.path.localeCompare(memories[memories.length - 1]!.path)).toBeGreaterThan(0);
  });

  it("updates memory content", () => {
    const { client, storeId } = populatedClient();
    const memId = client.storeMemory(storeId, "/test.md", "Original");
    client.updateMemory(storeId, memId, { content: "Updated" });
    const mem = client.retrieveMemory(storeId, memId);
    expect(mem!.content).toBe("Updated");
  });

  it("updates memory path", () => {
    const { client, storeId } = populatedClient();
    const memId = client.storeMemory(storeId, "/test.md", "Original");
    client.updateMemory(storeId, memId, { path: "/archive/test.md" });
    const mem = client.retrieveMemory(storeId, memId);
    expect(mem!.path).toBe("/archive/test.md");
  });

  it("updates with content_sha256 precondition", () => {
    const { client, storeId } = populatedClient();
    const memId = client.storeMemory(storeId, "/test.md", "Original");
    const mem = client.retrieveMemory(storeId, memId);
    client.updateMemory(storeId, memId, {
      content: "Updated",
      precondition: { type: "content_sha256", content_sha256: mem!.content_sha256 },
    });
    expect(client.retrieveMemory(storeId, memId)!.content).toBe("Updated");
  });

  it("throws on content_sha256 mismatch", () => {
    const { client, storeId } = populatedClient();
    const memId = client.storeMemory(storeId, "/test.md", "Original");
    expect(() =>
      client.updateMemory(storeId, memId, {
        content: "Updated",
        precondition: { type: "content_sha256", content_sha256: "wrong" },
      }),
    ).toThrow(/content_sha256 mismatch/);
  });

  it("deletes a memory", () => {
    const { client, storeId } = populatedClient();
    const memId = client.storeMemory(storeId, "/test.md", "content");
    client.deleteMemory(storeId, memId);
    expect(client.retrieveMemory(storeId, memId)).toBeUndefined();
  });

  it("deletes with conditional SHA256", () => {
    const { client, storeId } = populatedClient();
    const memId = client.storeMemory(storeId, "/test.md", "content");
    const mem = client.retrieveMemory(storeId, memId);
    client.deleteMemory(storeId, memId, mem!.content_sha256);
    expect(client.retrieveMemory(storeId, memId)).toBeUndefined();
  });

  it("throws delete on wrong SHA256", () => {
    const { client, storeId } = populatedClient();
    const memId = client.storeMemory(storeId, "/test.md", "content");
    expect(() => client.deleteMemory(storeId, memId, "wrong")).toThrow(/Conditional deletion failed/);
  });
});

// ---------------------------------------------------------------------------
// Search
// ---------------------------------------------------------------------------

describe("Search", () => {
  it("searches by content", () => {
    const { client, storeId } = populatedClient();
    const results = client.searchMemories(storeId, "tabs");
    expect(results).toHaveLength(1);
    expect(results[0]!.path).toBe("/preferences/formatting.md");
  });

  it("searches by path", () => {
    const { client, storeId } = populatedClient();
    const results = client.searchMemories(storeId, "language");
    expect(results.length).toBeGreaterThanOrEqual(1);
  });

  it("returns empty for no match", () => {
    const { client, storeId } = populatedClient();
    expect(client.searchMemories(storeId, "zzz_nonexistent")).toHaveLength(0);
  });

  it("searches case-insensitively", () => {
    const { client, storeId } = populatedClient();
    const results = client.searchMemories(storeId, "PYTHON");
    expect(results.length).toBeGreaterThanOrEqual(1);
  });
});

// ---------------------------------------------------------------------------
// Memory Versions
// ---------------------------------------------------------------------------

describe("Memory Versions", () => {
  it("creates version on store", () => {
    const client = new MemoryClient();
    const storeId = client.createMemoryStore("Test", "");
    const memId = client.storeMemory(storeId, "/test.md", "v1");
    const versions = client.listVersions(storeId);
    const creates = versions.filter((v) => v.operation === "create");
    expect(creates).toHaveLength(1);
    expect(creates[0]!.content).toBe("v1");
  });

  it("creates version on update", () => {
    const client = new MemoryClient();
    const storeId = client.createMemoryStore("Test", "");
    const memId = client.storeMemory(storeId, "/test.md", "v1");
    client.updateMemory(storeId, memId, { content: "v2" });
    const versions = client.listVersions(storeId, { memory_id: memId });
    expect(versions.length).toBeGreaterThanOrEqual(2);
  });

  it("filters by operation", () => {
    const client = new MemoryClient();
    const storeId = client.createMemoryStore("Test", "");
    const memId = client.storeMemory(storeId, "/test.md", "v1");
    client.updateMemory(storeId, memId, { content: "v2" });
    const updates = client.listVersions(storeId, { operation: "update" });
    expect(updates).toHaveLength(1);
    expect(updates[0]!.operation).toBe("update");
  });

  it("retrieves a version", () => {
    const client = new MemoryClient();
    const storeId = client.createMemoryStore("Test", "");
    const memId = client.storeMemory(storeId, "/test.md", "original");
    const versions = client.listVersions(storeId, { memory_id: memId });
    const v = client.retrieveVersion(storeId, versions[0]!.id);
    expect(v).toBeDefined();
    expect(v!.content).toBe("original");
  });

  it("versions survive after memory is deleted", () => {
    const client = new MemoryClient();
    const storeId = client.createMemoryStore("Test", "");
    const memId = client.storeMemory(storeId, "/test.md", "content");
    client.deleteMemory(storeId, memId);
    const versions = client.listVersions(storeId);
    // create + delete versions should both survive
    expect(versions.length).toBeGreaterThanOrEqual(2);
  });

  it("rolls back a memory", () => {
    const client = new MemoryClient();
    const storeId = client.createMemoryStore("Test", "");
    const memId = client.storeMemory(storeId, "/test.md", "v1");
    client.updateMemory(storeId, memId, { content: "v2" });
    const versions = client.listVersions(storeId, { memory_id: memId, operation: "create" });
    const v1VersionId = versions[0]!.id;
    client.rollbackMemory(storeId, memId, v1VersionId);
    const mem = client.retrieveMemory(storeId, memId);
    expect(mem!.content).toBe("v1");
  });

  it("redacts a version", () => {
    const client = new MemoryClient();
    const storeId = client.createMemoryStore("Test", "");
    const memId = client.storeMemory(storeId, "/test.md", "sensitive");
    client.updateMemory(storeId, memId, { content: "safe" });
    const versions = client.listVersions(storeId, { memory_id: memId, operation: "create" });
    client.redactVersion(storeId, versions[0]!.id);
    const v = client.retrieveVersion(storeId, versions[0]!.id);
    expect(v!.content).toBe("[REDACTED]");
  });

  it("throws redacting head version", () => {
    const client = new MemoryClient();
    const storeId = client.createMemoryStore("Test", "");
    const memId = client.storeMemory(storeId, "/test.md", "content");
    const mem = client.retrieveMemory(storeId, memId);
    expect(() => client.redactVersion(storeId, mem!.memory_version_id)).toThrow(/current head/);
  });
});

// ---------------------------------------------------------------------------
// Dreaming
// ---------------------------------------------------------------------------

describe("Dreaming", () => {
  it("starts a dream", () => {
    const { client, storeId } = populatedClient();
    const result = client.startDream(storeId);
    expect(result.dream_id).toMatch(/^dream_/);
    expect(result.output_store_id).toMatch(/^memstore_/);
    expect(result.status).toBe("completed");
  });

  it("deduplicates content in dream output", () => {
    const client = new MemoryClient();
    const storeId = client.createMemoryStore("Test", "");
    client.storeMemory(storeId, "/a.md", "Same content");
    client.storeMemory(storeId, "/b.md", "Same content");
    client.storeMemory(storeId, "/c.md", "Different");
    const result = client.startDream(storeId);
    const outputMems = client.listMemories(result.output_store_id);
    expect(outputMems).toHaveLength(2);
  });

  it("throws for nonexistent source store", () => {
    const client = new MemoryClient();
    expect(() => client.startDream("nonexistent")).toThrow(/not found/);
  });

  it("does not modify the source store", () => {
    const { client, storeId } = populatedClient();
    const result = client.startDream(storeId);
    expect(result.output_store_id).not.toBe(storeId);
    const origMems = client.listMemories(storeId);
    expect(origMems.length).toBeGreaterThanOrEqual(3);
  });

  it("accepts session IDs and instructions", () => {
    const { client, storeId } = populatedClient();
    const result = client.startDream(storeId, {
      sessionIds: ["session_1", "session_2"],
      instructions: "Focus on code preferences",
    });
    expect(result.status).toBe("completed");
  });
});

// ---------------------------------------------------------------------------
// Memory Limits
// ---------------------------------------------------------------------------

describe("Memory Limits", () => {
  it("rejects content over 100 KB", () => {
    const client = new MemoryClient();
    const storeId = client.createMemoryStore("Test", "");
    const big = "x".repeat(100 * 1024 + 1);
    expect(() => client.storeMemory(storeId, "/big.md", big)).toThrow(/100 KB/);
  });

  it("accepts content at 100 KB limit", () => {
    const client = new MemoryClient();
    const storeId = client.createMemoryStore("Test", "");
    const exact = "x".repeat(100 * 1024);
    const memId = client.storeMemory(storeId, "/exact.md", exact);
    const mem = client.retrieveMemory(storeId, memId);
    expect(mem!.content_size_bytes).toBe(100 * 1024);
  });
});
