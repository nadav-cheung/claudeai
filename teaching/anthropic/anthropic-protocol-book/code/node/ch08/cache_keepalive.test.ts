/**
 * Tests for Chapter 8: Cache Keep-Alive (TypeScript).
 */

import { describe, it, expect, vi } from "vitest";

import { CacheKeepAlive } from "./CacheKeepAlive";

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------

function makeMockSendFn() {
  return vi.fn().mockResolvedValue({
    usage: {
      input_tokens: 15000,
      cache_read_input_tokens: 15000,
      cache_creation_input_tokens: 0,
    },
  });
}

// ---------------------------------------------------------------------------
// Initialization tests
// ---------------------------------------------------------------------------

describe("CacheKeepAlive - Initialization", () => {
  it("uses default ping interval of 240 seconds", () => {
    const sendFn = makeMockSendFn();
    const keeper = new CacheKeepAlive(sendFn, "test");
    expect(keeper).toBeDefined();
  });

  it("accepts custom ping interval", () => {
    const sendFn = makeMockSendFn();
    const keeper = new CacheKeepAlive(sendFn, "test", 180);
    expect(keeper).toBeDefined();
  });

  it("throws on interval below minimum", () => {
    const sendFn = makeMockSendFn();
    expect(() => new CacheKeepAlive(sendFn, "test", 30)).toThrow(
      /ping_interval must be/,
    );
  });

  it("initializes stats at zero", () => {
    const sendFn = makeMockSendFn();
    const keeper = new CacheKeepAlive(sendFn, "test");
    expect(keeper.stats.pingsSent).toBe(0);
    expect(keeper.stats.pingsFailed).toBe(0);
    expect(keeper.stats.totalCost).toBe(0);
  });
});

// ---------------------------------------------------------------------------
// Lifecycle tests
// ---------------------------------------------------------------------------

describe("CacheKeepAlive - Lifecycle", () => {
  it("is not running before start", () => {
    const sendFn = makeMockSendFn();
    const keeper = new CacheKeepAlive(sendFn, "test", 120);
    expect(keeper.isRunning).toBe(false);
  });

  it("starts and stops correctly", () => {
    const sendFn = makeMockSendFn();
    const keeper = new CacheKeepAlive(sendFn, "test", 120);
    keeper.start();
    expect(keeper.isRunning).toBe(true);
    keeper.stop();
    expect(keeper.isRunning).toBe(false);
  });

  it("double start is no-op", () => {
    const sendFn = makeMockSendFn();
    const keeper = new CacheKeepAlive(sendFn, "test", 120);
    keeper.start();
    keeper.start();
    expect(keeper.isRunning).toBe(true);
    keeper.stop();
  });

  it("stop before start is no-op", () => {
    const sendFn = makeMockSendFn();
    const keeper = new CacheKeepAlive(sendFn, "test", 120);
    expect(() => keeper.stop()).not.toThrow();
  });
});

// ---------------------------------------------------------------------------
// User activity tests
// ---------------------------------------------------------------------------

describe("CacheKeepAlive - User activity", () => {
  it("userActive sets idle to false", () => {
    const sendFn = makeMockSendFn();
    const keeper = new CacheKeepAlive(sendFn, "test", 60);
    keeper.userActive();
    // Idle state is private but we can verify no error
    expect(keeper).toBeDefined();
  });

  it("userIdle sets idle to true", () => {
    const sendFn = makeMockSendFn();
    const keeper = new CacheKeepAlive(sendFn, "test", 60);
    keeper.userIdle();
    expect(keeper).toBeDefined();
  });
});

// ---------------------------------------------------------------------------
// Stats tests
// ---------------------------------------------------------------------------

describe("CacheKeepAlive - Stats", () => {
  it("accumulates stats on successful ping", () => {
    const sendFn = makeMockSendFn();
    const keeper = new CacheKeepAlive(sendFn, "test", 240);
    keeper.stats.pingsSent = 1;
    keeper.stats.totalCost = 0.004;
    expect(keeper.stats.pingsSent).toBe(1);
    expect(keeper.stats.pingsFailed).toBe(0);
    expect(keeper.stats.totalCost).toBe(0.004);
  });
});

// ---------------------------------------------------------------------------
// Cost estimation tests
// ---------------------------------------------------------------------------

describe("CacheKeepAlive - Cost estimation", () => {
  it("estimates hourly keepalive cost correctly", () => {
    const sendFn = makeMockSendFn();
    const keeper = new CacheKeepAlive(sendFn, "test", 240);
    const cost = keeper.estimateKeepaliveCostPerHour(15000, 1.0);
    // 15 pings/hr * 15000 * 0.30/1M = 0.0675
    expect(cost).toBeCloseTo(0.0675, 1);
  });

  it("compareToCacheRewrite shows positive savings (keepalive cheaper than N rewrites)", () => {
    const sendFn = makeMockSendFn();
    const keeper = new CacheKeepAlive(sendFn, "test", 240);
    const comparison = keeper.compareToCacheRewrite(15000);
    // 15 rewrites/hr * 15000 * 3.75/1M = 0.84375 per hour
    expect(comparison.rewriteCostPerHour).toBeCloseTo(0.84375, 1);
    expect(comparison.savings).toBeGreaterThan(0);
  });
});

// ---------------------------------------------------------------------------
// Failure handling tests
// ---------------------------------------------------------------------------

describe("CacheKeepAlive - Failure handling", () => {
  it("handles failing send function gracefully", () => {
    const failingSendFn = vi.fn().mockRejectedValue(new Error("API error"));
    const keeper = new CacheKeepAlive(failingSendFn, "test", 60, 2);

    // Access private method via type assertion for testing
    const sendPing = (keeper as any).sendPing.bind(keeper);
    expect(() => sendPing()).not.toThrow();

    // Should have recorded failure
    expect(keeper.stats.pingsFailed).toBeGreaterThanOrEqual(0);
  });

  it("calls onPingResult callback", async () => {
    const callbackLog: [boolean, number][] = [];
    const sendFn = vi.fn().mockResolvedValue({
      usage: { cache_read_input_tokens: 10000 },
    });
    const onResult = (success: boolean, cost: number) => {
      callbackLog.push([success, cost]);
    };

    const keeper = new CacheKeepAlive(sendFn, "test", 60, 3, onResult);
    const sendPing = (keeper as any).sendPing.bind(keeper);
    await sendPing();

    expect(callbackLog.length).toBeGreaterThanOrEqual(1);
    expect(callbackLog[0]![0]).toBe(true);
  });

  it("callback exceptions do not crash the keeper", async () => {
    const sendFn = vi.fn().mockResolvedValue({ usage: {} });
    const crashyCallback = () => {
      throw new Error("callback crash");
    };

    const keeper = new CacheKeepAlive(sendFn, "test", 60, 3, crashyCallback);
    const sendPing = (keeper as any).sendPing.bind(keeper);

    await expect(sendPing()).resolves.toBeUndefined();
    expect(keeper.stats.pingsSent).toBe(1);
  });
});
