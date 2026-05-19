/**
 * Chapter 10: Memory Client (TypeScript).
 *
 * Protocol-level implementation of Anthropic's Memory API for
 * Claude Managed Agents, providing Memory Store management,
 * Memory CRUD, Version audit trail, and Dreaming integration.
 */

// ---------------------------------------------------------------------------
// Data Models
// ---------------------------------------------------------------------------

export interface MemoryStoreData {
  id: string; // memstore_...
  name: string;
  description: string;
  created_at: string;
  archived_at: string | null;
}

export interface MemoryData {
  id: string; // mem_...
  memory_store_id: string;
  path: string;
  content: string;
  content_sha256: string;
  content_size_bytes: number;
  memory_version_id: string; // memver_...
  created_at: string;
  updated_at: string;
}

export interface MemoryVersionData {
  id: string; // memver_...
  memory_id: string;
  memory_store_id: string;
  content: string;
  operation: "create" | "update" | "delete";
  session_id: string;
  created_at: string;
}

export interface DreamResultData {
  dream_id: string;
  output_store_id: string;
  status: "running" | "completed" | "failed";
  merged_count: number;
  updated_count: number;
  deleted_count: number;
  patterns_found: string[];
}

export interface MemoryPrecondition {
  type: "content_sha256" | "not_exists";
  content_sha256?: string;
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function sha256(s: string): string {
  // In production, Node.js 22+ provides native crypto.createHash('sha256').
  // This deterministic hash is for illustration; real code should use crypto.
  let hash = 0;
  for (let i = 0; i < s.length; i++) {
    const char = s.charCodeAt(i);
    hash = ((hash << 5) - hash) + char;
    hash |= 0;
  }
  return Math.abs(hash).toString(16).padStart(8, "0");
}

// ---------------------------------------------------------------------------
// MemoryClient
// ---------------------------------------------------------------------------

/**
 * Client for Anthropic Memory API.
 *
 * Manages Memory Stores, Memories, Versions, and Dreaming operations.
 * This is a protocol-level implementation using in-memory storage
 * for illustration and testing purposes.
 *
 * Usage:
 * ```typescript
 * const client = new MemoryClient();
 * const storeId = client.createMemoryStore("User Preferences", "Per-user prefs");
 * const memId = client.storeMemory(storeId, "/formatting.md", "Use tabs");
 * const mems = client.searchMemories(storeId, "tabs");
 * client.deleteMemory(storeId, memId);
 * ```
 */
export class MemoryClient {
  private stores: Map<string, MemoryStoreData> = new Map();
  private memories: Map<string, Map<string, MemoryData>> = new Map();
  private versions: Map<string, MemoryVersionData[]> = new Map();
  private idCounter: number = 0;

  private nextId(prefix: string): string {
    this.idCounter += 1;
    return `${prefix}_${String(this.idCounter).padStart(4, "0")}`;
  }

  // ------------------------------------------------------------------
  // Memory Store CRUD
  // ------------------------------------------------------------------

  /**
   * Create a new Memory Store.
   *
   * Maps to: POST /v1/memory_stores
   * SDK: client.beta.memory_stores.create(name, description)
   */
  createMemoryStore(name: string, description: string = ""): string {
    const storeId = this.nextId("memstore");
    const now = new Date().toISOString();
    this.stores.set(storeId, {
      id: storeId,
      name,
      description,
      created_at: now,
      archived_at: null,
    });
    this.memories.set(storeId, new Map());
    this.versions.set(storeId, []);
    return storeId;
  }

  /**
   * List all Memory Stores in the workspace.
   *
   * Maps to: GET /v1/memory_stores
   */
  listMemoryStores(includeArchived: boolean = false): MemoryStoreData[] {
    const all = Array.from(this.stores.values());
    if (!includeArchived) {
      return all.filter((s) => s.archived_at === null);
    }
    return all;
  }

  /**
   * Retrieve a single Memory Store by ID.
   */
  getMemoryStore(storeId: string): MemoryStoreData | undefined {
    return this.stores.get(storeId);
  }

  /**
   * Archive a Memory Store (one-way, irreversible).
   *
   * Maps to: POST /v1/memory_stores/{id}/archive
   *
   * After archiving, the store becomes read-only and cannot be
   * attached to new sessions.
   */
  archiveMemoryStore(storeId: string): void {
    const store = this.stores.get(storeId);
    if (!store) {
      throw new Error(`Memory store '${storeId}' not found`);
    }
    if (store.archived_at !== null) {
      throw new Error(`Memory store '${storeId}' is already archived`);
    }
    store.archived_at = new Date().toISOString();
  }

  /**
   * Permanently delete a Memory Store and all its memories and versions.
   *
   * Maps to: DELETE /v1/memory_stores/{id}
   */
  deleteMemoryStore(storeId: string): void {
    this.stores.delete(storeId);
    this.memories.delete(storeId);
    this.versions.delete(storeId);
  }

  // ------------------------------------------------------------------
  // Memory CRUD
  // ------------------------------------------------------------------

  /**
   * Create a new Memory in a Store. Does NOT overwrite existing.
   *
   * Maps to: POST /v1/memory_stores/{store_id}/memories
   */
  storeMemory(
    storeId: string,
    path: string,
    content: string,
    metadata?: Record<string, unknown>,
  ): string {
    this.ensureStoreActive(storeId);

    const existing = this.findByPath(storeId, path);
    if (existing) {
      throw new Error(`Memory already exists at path '${path}'. Use updateMemory() to modify.`);
    }

    return this.createMemoryInternal(storeId, path, content);
  }

  /**
   * Upsert a Memory: creates or overwrites at the given path.
   */
  writeMemory(
    storeId: string,
    path: string,
    content: string,
    precondition?: MemoryPrecondition,
  ): string {
    this.ensureStoreActive(storeId);

    if (precondition?.type === "not_exists") {
      const existing = this.findByPath(storeId, path);
      if (existing) {
        throw new Error(`Precondition 'not_exists' failed: path '${path}' already exists`);
      }
    }

    const existing = this.findByPath(storeId, path);
    if (existing) {
      return this.updateMemory(storeId, existing.id, { content });
    }
    return this.createMemoryInternal(storeId, path, content);
  }

  /**
   * Retrieve a single Memory by ID.
   */
  retrieveMemory(storeId: string, memoryId: string): MemoryData | undefined {
    const storeMems = this.memories.get(storeId);
    return storeMems?.get(memoryId);
  }

  /**
   * List memories in a store, optionally filtered by path_prefix.
   */
  listMemories(
    storeId: string,
    options: {
      path_prefix?: string;
      limit?: number;
      order_by?: "path" | "created_at";
      order?: "asc" | "desc";
    } = {},
  ): MemoryData[] {
    const storeMems = this.memories.get(storeId);
    if (!storeMems) return [];

    let memories = Array.from(storeMems.values());

    if (options.path_prefix) {
      memories = memories.filter((m) => m.path.startsWith(options.path_prefix!));
    }

    const orderBy = options.order_by ?? "path";
    const reverse = options.order === "desc";

    memories.sort((a, b) => {
      const va = orderBy === "created_at" ? a.created_at : a.path;
      const vb = orderBy === "created_at" ? b.created_at : b.path;
      const cmp = va < vb ? -1 : va > vb ? 1 : 0;
      return reverse ? -cmp : cmp;
    });

    return memories.slice(0, options.limit ?? 20);
  }

  /**
   * Update an existing Memory.
   */
  updateMemory(
    storeId: string,
    memoryId: string,
    options: {
      content?: string;
      path?: string;
      precondition?: MemoryPrecondition;
    },
  ): string {
    this.ensureStoreActive(storeId);

    const storeMems = this.memories.get(storeId);
    if (!storeMems) {
      throw new Error(`Memory store '${storeId}' not found`);
    }

    const mem = storeMems.get(memoryId);
    if (!mem) {
      throw new Error(`Memory '${memoryId}' not found in store '${storeId}'`);
    }

    // Check precondition
    if (options.precondition?.type === "content_sha256") {
      const expected = options.precondition.content_sha256 ?? "";
      if (mem.content_sha256 !== expected) {
        throw new Error(
          `Precondition failed: content_sha256 mismatch. ` +
            `Expected ${expected.slice(0, 12)}..., got ${mem.content_sha256.slice(0, 12)}...`,
        );
      }
    }

    const oldContent = mem.content;
    if (options.content !== undefined) {
      mem.content = options.content;
    }
    if (options.path !== undefined) {
      mem.path = options.path;
    }

    mem.content_sha256 = sha256(mem.content);
    mem.content_size_bytes = new TextEncoder().encode(mem.content).length;
    mem.updated_at = new Date().toISOString();

    const newVersionId = this.recordVersion(storeId, memoryId, oldContent, "update");
    mem.memory_version_id = newVersionId;

    return memoryId;
  }

  /**
   * Delete a Memory.
   */
  deleteMemory(
    storeId: string,
    memoryId: string,
    expectedContentSha256?: string,
  ): void {
    const storeMems = this.memories.get(storeId);
    if (!storeMems) {
      throw new Error(`Memory store '${storeId}' not found`);
    }

    const mem = storeMems.get(memoryId);
    if (!mem) {
      throw new Error(`Memory '${memoryId}' not found in store '${storeId}'`);
    }

    if (expectedContentSha256 && mem.content_sha256 !== expectedContentSha256) {
      throw new Error("Conditional deletion failed: content_sha256 mismatch");
    }

    this.recordVersion(storeId, memoryId, mem.content, "delete");
    storeMems.delete(memoryId);
  }

  /**
   * Full-text search across memories in a store.
   *
   * Simple substring match implementation. Memories are ranked with
   * path matches scoring higher than content matches.
   */
  searchMemories(storeId: string, query: string): MemoryData[] {
    const storeMems = this.memories.get(storeId);
    if (!storeMems) return [];

    const queryLower = query.toLowerCase();
    const scored: Array<{ score: number; mem: MemoryData }> = [];

    for (const mem of storeMems.values()) {
      let score = 0;
      if (mem.path.toLowerCase().includes(queryLower)) {
        score += 10;
      }
      if (mem.content.toLowerCase().includes(queryLower)) {
        score += 5;
      }
      if (score > 0) {
        scored.push({ score, mem });
      }
    }

    scored.sort((a, b) => b.score - a.score);
    return scored.map((s) => s.mem);
  }

  // ------------------------------------------------------------------
  // Memory Version Audit
  // ------------------------------------------------------------------

  /**
   * List memory versions for audit purposes.
   */
  listVersions(
    storeId: string,
    options: {
      memory_id?: string;
      operation?: "create" | "update" | "delete";
    } = {},
  ): MemoryVersionData[] {
    let versions = this.versions.get(storeId) ?? [];

    if (options.memory_id) {
      versions = versions.filter((v) => v.memory_id === options.memory_id);
    }
    if (options.operation) {
      versions = versions.filter((v) => v.operation === options.operation);
    }

    return versions.sort((a, b) => b.created_at.localeCompare(a.created_at));
  }

  /**
   * Retrieve a specific version's full content.
   */
  retrieveVersion(storeId: string, versionId: string): MemoryVersionData | undefined {
    const versions = this.versions.get(storeId) ?? [];
    return versions.find((v) => v.id === versionId);
  }

  /**
   * Redact content from a historical version while keeping audit metadata.
   *
   * A version that is the current head of a live memory cannot be redacted.
   */
  redactVersion(storeId: string, versionId: string): void {
    const versions = this.versions.get(storeId) ?? [];
    const version = versions.find((v) => v.id === versionId);

    if (!version) {
      throw new Error(`Version '${versionId}' not found in store '${storeId}'`);
    }

    // Check if this is the current head
    const storeMems = this.memories.get(storeId);
    if (storeMems) {
      const mem = storeMems.get(version.memory_id);
      if (mem && mem.memory_version_id === versionId) {
        throw new Error(
          `Cannot redact version '${versionId}': it is the current head ` +
            `of memory '${version.memory_id}'. Write a new version first.`,
        );
      }
    }

    version.content = "[REDACTED]";
  }

  /**
   * Rollback a memory to a previous version.
   */
  rollbackMemory(storeId: string, memoryId: string, versionId: string): string {
    const version = this.retrieveVersion(storeId, versionId);
    if (!version) {
      throw new Error(`Version '${versionId}' not found`);
    }
    if (version.memory_id !== memoryId) {
      throw new Error(
        `Version '${versionId}' belongs to memory '${version.memory_id}', not '${memoryId}'`,
      );
    }
    return this.updateMemory(storeId, memoryId, { content: version.content });
  }

  // ------------------------------------------------------------------
  // Dreaming
  // ------------------------------------------------------------------

  /**
   * Start a Dreaming consolidation job.
   *
   * Maps to: POST /v1/dreams (requires dreaming-2026-04-21 beta header)
   *
   * Dreaming reads the source store and up to 100 session transcripts,
   * then produces a NEW store with merged facts, removed contradictions,
   * and surfaced patterns. The source store is never modified.
   */
  startDream(
    sourceStoreId: string,
    options: {
      sessionIds?: string[];
      instructions?: string;
    } = {},
  ): DreamResultData {
    if (!this.stores.has(sourceStoreId)) {
      throw new Error(`Source store '${sourceStoreId}' not found`);
    }

    if ((options.instructions?.length ?? 0) > 4096) {
      throw new Error("Instructions must be 4,096 characters or fewer");
    }

    const dreamId = this.nextId("dream");
    const outputStoreId = this.createMemoryStore(
      `Dream Output (${dreamId})`,
      `Optimized memory from ${sourceStoreId}`,
    );

    const sourceMems = this.memories.get(sourceStoreId);
    const seenHashes = new Map<string, string>();
    let dupesRemoved = 0;

    if (sourceMems) {
      for (const mem of sourceMems.values()) {
        if (seenHashes.has(mem.content_sha256)) {
          dupesRemoved += 1;
          continue;
        }
        seenHashes.set(mem.content_sha256, mem.id);
        this.createMemoryInternal(outputStoreId, mem.path, mem.content);
      }
    }

    return {
      dream_id: dreamId,
      output_store_id: outputStoreId,
      status: "completed",
      merged_count: dupesRemoved,
      updated_count: 0,
      deleted_count: 0,
      patterns_found: ["Consolidated duplicate memories"],
    };
  }

  // ------------------------------------------------------------------
  // Internal helpers
  // ------------------------------------------------------------------

  private ensureStoreActive(storeId: string): void {
    const store = this.stores.get(storeId);
    if (!store) {
      throw new Error(`Memory store '${storeId}' not found`);
    }
    if (store.archived_at !== null) {
      throw new Error(`Memory store '${storeId}' is archived (read-only)`);
    }
  }

  private findByPath(storeId: string, path: string): MemoryData | undefined {
    const storeMems = this.memories.get(storeId);
    if (!storeMems) return undefined;
    for (const mem of storeMems.values()) {
      if (mem.path === path) {
        return mem;
      }
    }
    return undefined;
  }

  private createMemoryInternal(storeId: string, path: string, content: string): string {
    const encoded = new TextEncoder().encode(content);
    if (encoded.length > 100 * 1024) {
      throw new Error("Memory content exceeds 100 KB limit");
    }

    const memoryId = this.nextId("mem");
    const hash = sha256(content);
    const now = new Date().toISOString();

    // Record version first so memory_version_id matches the actual version
    const versionId = this.recordVersion(storeId, memoryId, content, "create");

    const mem: MemoryData = {
      id: memoryId,
      memory_store_id: storeId,
      path,
      content,
      content_sha256: hash,
      content_size_bytes: encoded.length,
      memory_version_id: versionId,
      created_at: now,
      updated_at: now,
    };

    const storeMems = this.memories.get(storeId);
    if (storeMems) {
      storeMems.set(memoryId, mem);
    }

    return memoryId;
  }

  private recordVersion(
    storeId: string,
    memoryId: string,
    content: string,
    operation: "create" | "update" | "delete",
  ): string {
    const versionId = this.nextId("memver");
    const now = new Date().toISOString();
    const version: MemoryVersionData = {
      id: versionId,
      memory_id: memoryId,
      memory_store_id: storeId,
      content,
      operation,
      session_id: "",
      created_at: now,
    };

    const storeVersions = this.versions.get(storeId);
    if (storeVersions) {
      storeVersions.push(version);
    } else {
      this.versions.set(storeId, [version]);
    }

    return versionId;
  }
}
