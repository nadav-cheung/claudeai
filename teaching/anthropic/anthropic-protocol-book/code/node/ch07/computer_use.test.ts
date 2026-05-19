/**
 * Tests for Chapter 7 Computer Use client (TypeScript / Vitest).
 */

import { describe, expect, it } from "vitest";
import {
  ActionValidator,
  ComputerUseAgentLoop,
  ComputerUseClient,
  ComputerUseToolSchema,
  getScaleFactor,
  scaleCoordinatesDown,
  scaleCoordinatesUp,
  validateCoordinates,
} from "./ComputerUseClient";

import type {
  ApiCallParams,
  ApiResponse,
  ContentBlock,
  ScreenshotResult,
  ToolActionResult,
} from "./ComputerUseClient";

// ---------------------------------------------------------------------------
// Coordinate scaling
// ---------------------------------------------------------------------------

describe("getScaleFactor", () => {
  it("returns 1.0 for small displays", () => {
    expect(getScaleFactor(1024, 768)).toBe(1.0);
  });

  it("returns a value < 1 for large displays", () => {
    const sf = getScaleFactor(2560, 1440);
    expect(sf).toBeGreaterThan(0);
    expect(sf).toBeLessThan(1);
  });

  it("returns significantly < 1 for 4K", () => {
    const sf = getScaleFactor(3840, 2160);
    expect(sf).toBeLessThan(0.5);
  });

  it("always returns in (0, 1]", () => {
    const sizes: Array<[number, number]> = [
      [800, 600], [1024, 768], [1512, 982], [1920, 1080],
      [2560, 1440], [3840, 2160],
    ];
    for (const [w, h] of sizes) {
      const sf = getScaleFactor(w, h);
      expect(sf).toBeGreaterThan(0);
      expect(sf).toBeLessThanOrEqual(1);
    }
  });

  it("throws on invalid dimensions", () => {
    expect(() => getScaleFactor(0, 768)).toThrow();
    expect(() => getScaleFactor(1024, -1)).toThrow();
  });
});

describe("scaleCoordinatesUp", () => {
  it("returns unchanged values when scale=1.0", () => {
    expect(scaleCoordinatesUp(100, 200, 1.0)).toEqual([100, 200]);
  });

  it("scales up correctly", () => {
    const [x, y] = scaleCoordinatesUp(665, 432, 0.5);
    expect(x).toBe(1330);
    expect(y).toBe(864);
  });

  it("throws on invalid scale", () => {
    expect(() => scaleCoordinatesUp(10, 10, 0)).toThrow();
    expect(() => scaleCoordinatesUp(10, 10, 1.5)).toThrow();
  });
});

describe("scaleCoordinatesDown", () => {
  it("scales down correctly", () => {
    const [x, y] = scaleCoordinatesDown(1330, 864, 0.5);
    expect(x).toBe(665);
    expect(y).toBe(432);
  });
});

describe("validateCoordinates", () => {
  it("accepts in-bounds coordinates", () => {
    const result = validateCoordinates(500, 300, 1024, 768);
    expect(result.valid).toBe(true);
  });

  it("accepts origin", () => {
    const result = validateCoordinates(0, 0, 1024, 768);
    expect(result.valid).toBe(true);
  });

  it("rejects out-of-bounds X", () => {
    const result = validateCoordinates(1024, 500, 1024, 768);
    expect(result.valid).toBe(false);
    if (!result.valid) expect(result.error).toContain("X coordinate");
  });

  it("rejects out-of-bounds Y", () => {
    const result = validateCoordinates(500, 768, 1024, 768);
    expect(result.valid).toBe(false);
    if (!result.valid) expect(result.error).toContain("Y coordinate");
  });

  it("rejects negative coordinates", () => {
    const result = validateCoordinates(-1, 500, 1024, 768);
    expect(result.valid).toBe(false);
  });
});

// ---------------------------------------------------------------------------
// ActionValidator
// ---------------------------------------------------------------------------

describe("ActionValidator", () => {
  const validator = new ActionValidator(1280, 720);

  it("validates screenshot with no params", () => {
    const result = validator.validate("screenshot", {});
    expect(result.valid).toBe(true);
  });

  it("validates left_click with coordinate", () => {
    const result = validator.validate("left_click", { coordinate: [500, 300] });
    expect(result.valid).toBe(true);
  });

  it("rejects click without coordinate", () => {
    const result = validator.validate("left_click", {});
    expect(result.valid).toBe(false);
  });

  it("rejects click out of bounds", () => {
    const result = validator.validate("left_click", { coordinate: [1300, 300] });
    expect(result.valid).toBe(false);
  });

  it("validates right_click", () => {
    const result = validator.validate("right_click", { coordinate: [10, 10] });
    expect(result.valid).toBe(true);
  });

  it("validates middle_click", () => {
    const result = validator.validate("middle_click", { coordinate: [640, 360] });
    expect(result.valid).toBe(true);
  });

  it("validates double_click", () => {
    const result = validator.validate("double_click", { coordinate: [100, 200] });
    expect(result.valid).toBe(true);
  });

  it("validates mouse_move", () => {
    const result = validator.validate("mouse_move", { coordinate: [640, 360] });
    expect(result.valid).toBe(true);
  });

  it("validates left_click_drag", () => {
    const result = validator.validate("left_click_drag", { coordinate: [800, 600] });
    expect(result.valid).toBe(true);
  });

  it("validates type with text", () => {
    const result = validator.validate("type", { text: "hello" });
    expect(result.valid).toBe(true);
  });

  it("rejects type without text", () => {
    const result = validator.validate("type", {});
    expect(result.valid).toBe(false);
  });

  it("validates key with text", () => {
    const result = validator.validate("key", { text: "ctrl+s" });
    expect(result.valid).toBe(true);
  });

  it("validates scroll", () => {
    const result = validator.validate("scroll", {
      scroll_direction: "down",
      scroll_amount: 3,
    });
    expect(result.valid).toBe(true);
  });

  it("rejects scroll with bad direction", () => {
    const result = validator.validate("scroll", {
      scroll_direction: "diagonal",
      scroll_amount: 1,
    });
    expect(result.valid).toBe(false);
  });

  it("validates wait", () => {
    const result = validator.validate("wait", { duration: 0.5 });
    expect(result.valid).toBe(true);
  });

  it("validates left_mouse_down", () => {
    const result = validator.validate("left_mouse_down", {});
    expect(result.valid).toBe(true);
  });

  it("validates cursor_position", () => {
    const result = validator.validate("cursor_position", {});
    expect(result.valid).toBe(true);
  });

  it("validates zoom", () => {
    const result = validator.validate("zoom", { region: [100, 200, 400, 350] });
    expect(result.valid).toBe(true);
  });

  it("rejects zoom without region", () => {
    const result = validator.validate("zoom", {});
    expect(result.valid).toBe(false);
  });

  it("rejects unknown action", () => {
    const result = validator.validate("explode", {});
    expect(result.valid).toBe(false);
  });

  it("exposes known actions", () => {
    const actions = validator.knownActions;
    expect(actions.has("screenshot")).toBe(true);
    expect(actions.has("left_click")).toBe(true);
    expect(actions.has("scroll")).toBe(true);
    expect(actions.has("zoom")).toBe(true);
  });
});

// ---------------------------------------------------------------------------
// ComputerUseToolSchema
// ---------------------------------------------------------------------------

describe("ComputerUseToolSchema", () => {
  it("builds default schema", () => {
    const schema = new ComputerUseToolSchema();
    const d = schema.toDict();
    expect(d["type"]).toBe("computer_20251124");
    expect(d["name"]).toBe("computer");
    expect(d["display_width_px"]).toBe(1024);
    expect(d["display_height_px"]).toBe(768);
    expect(d["display_number"]).toBe(1);
  });

  it("builds custom dimensions", () => {
    const schema = new ComputerUseToolSchema(1920, 1080);
    const d = schema.toDict();
    expect(d["display_width_px"]).toBe(1920);
    expect(d["display_height_px"]).toBe(1080);
  });

  it("supports version 20250124", () => {
    const schema = new ComputerUseToolSchema(1024, 768, null, "20250124");
    expect(schema.toDict()["type"]).toBe("computer_20250124");
  });

  it("returns correct beta header", () => {
    const s1 = new ComputerUseToolSchema(1024, 768, null, "20250124");
    expect(s1.betaHeader).toBe("computer-use-2025-01-24");
    const s2 = new ComputerUseToolSchema(1024, 768, null, "20251124");
    expect(s2.betaHeader).toBe("computer-use-2025-11-24");
  });

  it("throws on invalid version", () => {
    expect(() => new ComputerUseToolSchema(1024, 768, null, "20241022")).toThrow();
  });

  it("enable_zoom only in 20251124", () => {
    const schema = new ComputerUseToolSchema(1024, 768, null, "20251124", true);
    expect(schema.toDict()["enable_zoom"]).toBe(true);

    const schemaOld = new ComputerUseToolSchema(1024, 768, null, "20250124", true);
    expect("enable_zoom" in schemaOld.toDict()).toBe(false);
  });
});

// ---------------------------------------------------------------------------
// ComputerUseClient
// ---------------------------------------------------------------------------

describe("ComputerUseClient", () => {
  function makeClient(): ComputerUseClient {
    return new ComputerUseClient({ displayWidthPx: 1280, displayHeightPx: 720 });
  }

  // -- tool schema --
  it("builds tool schema", () => {
    const client = makeClient();
    const schema = client.buildToolSchema();
    expect(schema["type"]).toBe("computer_20251124");
    expect(schema["display_width_px"]).toBe(1280);
  });

  // -- properties --
  it("exposes display properties", () => {
    const client = new ComputerUseClient({
      displayWidthPx: 1920, displayHeightPx: 1080, toolVersion: "20250124",
    });
    expect(client.displayWidth).toBe(1920);
    expect(client.displayHeight).toBe(1080);
    expect(client.toolVersion).toBe("20250124");
    expect(client.betaHeader).toBe("computer-use-2025-01-24");
  });

  it("scale factor is 1.0 for small display", () => {
    const client = new ComputerUseClient({ displayWidthPx: 1024, displayHeightPx: 768 });
    expect(client.scaleFactor).toBe(1.0);
  });

  it("scale factor < 1 for large display", () => {
    const client = new ComputerUseClient({ displayWidthPx: 2560, displayHeightPx: 1440 });
    expect(client.scaleFactor).toBeLessThan(1);
  });

  // -- action execution (success) --
  it("executes screenshot action", async () => {
    const client = makeClient();
    const result = await client.executeAction({ action: "screenshot" });
    expect(result.success).toBe(true);
  });

  it("executes left_click", async () => {
    const client = makeClient();
    const result = await client.executeAction({
      action: "left_click", coordinate: [640, 360],
    });
    expect(result.success).toBe(true);
    expect(result.output).toContain("left_click");
  });

  it("executes mouse_move", async () => {
    const client = makeClient();
    const result = await client.executeAction({
      action: "mouse_move", coordinate: [100, 200],
    });
    expect(result.success).toBe(true);
    expect(result.output).toContain("100");
    expect(result.output).toContain("200");
  });

  it("executes type action", async () => {
    const client = makeClient();
    const result = await client.executeAction({
      action: "type", text: "Hello, World!",
    });
    expect(result.success).toBe(true);
    expect(result.output).toContain("Hello, World!");
  });

  it("executes scroll action", async () => {
    const client = makeClient();
    const result = await client.executeAction({
      action: "scroll",
      coordinate: [500, 400],
      scroll_direction: "down",
      scroll_amount: 3,
    });
    expect(result.success).toBe(true);
    expect(result.output).toContain("down");
  });

  it("executes hold_key", async () => {
    const client = makeClient();
    const result = await client.executeAction({
      action: "hold_key", text: "shift", duration: 1.0,
    });
    expect(result.success).toBe(true);
  });

  it("executes zoom", async () => {
    const client = makeClient();
    const result = await client.executeAction({
      action: "zoom", region: [100, 200, 400, 350],
    });
    expect(result.success).toBe(true);
  });

  // -- action execution (errors) --
  it("rejects missing action", async () => {
    const client = makeClient();
    const result = await client.executeAction({});
    expect(result.success).toBe(false);
    expect(result.error).toContain("action");
  });

  it("rejects unknown action", async () => {
    const client = makeClient();
    const result = await client.executeAction({ action: "nuclear_launch" });
    expect(result.success).toBe(false);
  });

  it("rejects out-of-bounds click", async () => {
    const client = makeClient();
    const result = await client.executeAction({
      action: "left_click", coordinate: [9999, 9999],
    });
    expect(result.success).toBe(false);
  });

  // -- convenience methods --
  it("captureScreenshot returns empty without callback", () => {
    const client = makeClient();
    expect(client.captureScreenshot()).toBe("");
  });

  it("click dispatches to correct action", async () => {
    const client = makeClient();
    const result = await client.click(100, 200, "right");
    expect(result.success).toBe(true);
    expect(result.output).toContain("right_click");
  });

  it("doubleClick works", async () => {
    const client = makeClient();
    const result = await client.doubleClick(300, 400);
    expect(result.success).toBe(true);
  });

  it("typeText works", async () => {
    const client = makeClient();
    const result = await client.typeText("hello world");
    expect(result.success).toBe(true);
  });

  it("keyCombination joins keys", async () => {
    const client = makeClient();
    const result = await client.keyCombination(["ctrl", "shift", "t"]);
    expect(result.success).toBe(true);
    expect(result.output).toContain("ctrl+shift+t");
  });

  it("scroll handles vertical only", async () => {
    const client = makeClient();
    const result = await client.scroll(500, 400, 0, 5);
    expect(result.success).toBe(true);
  });

  it("scroll handles both axes", async () => {
    const client = makeClient();
    const result = await client.scroll(500, 400, 2, -3);
    expect(result.success).toBe(true);
  });

  it("drag works", async () => {
    const client = makeClient();
    const result = await client.drag(100, 100, 500, 500);
    expect(result.success).toBe(true);
    expect(result.output).toContain("Dragged");
  });

  // -- callbacks --
  it("calls screenshot callback", async () => {
    const client = makeClient();
    const captured: ScreenshotResult[] = [];

    client.onScreenshot(() => {
      const sr: ScreenshotResult = {
        base64Image: Buffer.from("fake-png-data").toString("base64"),
        mediaType: "image/png",
        width: 1024,
        height: 768,
      };
      captured.push(sr);
      return sr;
    });

    const result = await client.executeAction({ action: "screenshot" });
    expect(result.success).toBe(true);
    expect(captured).toHaveLength(1);
    expect(result.screenshot?.width).toBe(1024);
  });

  it("calls mouse callback", async () => {
    const client = makeClient();
    const calls: Array<Record<string, unknown>> = [];

    client.onMouse((params) => {
      calls.push({ ...params });
    });

    await client.executeAction({ action: "left_click", coordinate: [300, 200] });
    expect(calls).toHaveLength(1);
    expect(calls[0]!["action"]).toBe("left_click");
    expect(calls[0]!["x"]).toBe(300);
    expect(calls[0]!["y"]).toBe(200);
  });

  it("calls keyboard callback", async () => {
    const client = makeClient();
    const calls: Array<Record<string, unknown>> = [];

    client.onKeyboard((params) => {
      calls.push({ ...params });
    });

    await client.executeAction({ action: "type", text: "abc" });
    expect(calls).toHaveLength(1);
    expect(calls[0]!["text"]).toBe("abc");
  });

  // -- formatToolResult --
  it("formats success tool result", () => {
    const result: ToolActionResult = {
      success: true, output: "done", error: null, screenshot: null,
    };
    const formatted = ComputerUseClient.formatToolResult(result, "toolu_01X");
    expect(formatted.type).toBe("tool_result");
    expect(formatted.tool_use_id).toBe("toolu_01X");
    expect(formatted.is_error).toBe(false);
    if (Array.isArray(formatted.content)) {
      const first = formatted.content[0] as { text?: string };
      expect(first?.text).toBe("done");
    }
  });

  it("formats error tool result", () => {
    const result: ToolActionResult = {
      success: false, output: null, error: "boom", screenshot: null,
    };
    const formatted = ComputerUseClient.formatToolResult(result, "toolu_01Y");
    expect(formatted.is_error).toBe(true);
    if (Array.isArray(formatted.content)) {
      const first = formatted.content[0] as { text?: string };
      expect(first?.text).toBe("boom");
    }
  });

  it("formats result with screenshot", () => {
    const sr: ScreenshotResult = {
      base64Image: "aW1hZ2U=",
      mediaType: "image/png",
      width: 800,
      height: 600,
    };
    const result: ToolActionResult = {
      success: true, output: "ok", error: null, screenshot: sr,
    };
    const formatted = ComputerUseClient.formatToolResult(result, "toolu_01Z");
    expect(formatted.content).toHaveLength(2);
    const imgBlock = formatted.content[1] as { type?: string; source?: { data?: string } };
    expect(imgBlock?.type).toBe("image");
    expect(imgBlock?.source?.data).toBe("aW1hZ2U=");
  });

  it("excludes screenshot when told", () => {
    const sr: ScreenshotResult = {
      base64Image: "aW1hZ2U=", mediaType: "image/png", width: 0, height: 0,
    };
    const result: ToolActionResult = {
      success: true, output: "ok", error: null, screenshot: sr,
    };
    const formatted = ComputerUseClient.formatToolResult(
      result, "toolu_01Z", { includeScreenshot: false },
    );
    expect(formatted.content).toHaveLength(1);
  });
});

// ---------------------------------------------------------------------------
// AgentLoop
// ---------------------------------------------------------------------------

describe("ComputerUseAgentLoop", () => {
  function makeClient(): ComputerUseClient {
    return new ComputerUseClient({ displayWidthPx: 1024, displayHeightPx: 768 });
  }

  it("completes when Claude returns text", async () => {
    const client = makeClient();
    const loop = new ComputerUseAgentLoop(client, {
      model: "claude-sonnet-4-20250514",
      maxTokens: 1024,
      maxIterations: 5,
      toolVersion: "20251124",
      displayWidthPx: 1024,
      displayHeightPx: 768,
    });

    let callCount = 0;

    loop.onApiCall(async (_params: ApiCallParams): Promise<ApiResponse> => {
      callCount++;
      if (callCount === 1) {
        const content: ContentBlock[] = [
          {
            type: "tool_use",
            id: "toolu_01A",
            name: "computer",
            input: { action: "screenshot" },
          },
        ];
        return { id: "msg_001", content, stop_reason: "tool_use" };
      }
      const content: ContentBlock[] = [
        { type: "text", text: "Task completed." },
      ];
      return { id: "msg_002", content, stop_reason: "end_turn" };
    });

    const result = await loop.run([
      { role: "user", content: "Take a screenshot" },
    ]);
    expect(result.completed).toBe(true);
    expect(result.iterations).toBe(2);
    expect(result.finalText).toContain("completed");
  });

  it("stops at max iterations", async () => {
    const client = makeClient();
    const loop = new ComputerUseAgentLoop(client, {
      model: "claude-sonnet-4-20250514",
      maxTokens: 1024,
      maxIterations: 2,
      toolVersion: "20251124",
      displayWidthPx: 1024,
      displayHeightPx: 768,
    });

    loop.onApiCall(async (_params: ApiCallParams): Promise<ApiResponse> => {
      const content: ContentBlock[] = [
        {
          type: "tool_use",
          id: "toolu_01X",
          name: "computer",
          input: { action: "screenshot" },
        },
      ];
      return { id: "msg_x", content, stop_reason: "tool_use" };
    });

    const result = await loop.run([
      { role: "user", content: "Loop forever..." },
    ]);
    expect(result.completed).toBe(false);
    expect(result.iterations).toBe(2);
  });

  it("returns error without api_call registered", async () => {
    const client = makeClient();
    const loop = new ComputerUseAgentLoop(client);
    // Intentionally no onApiCall.

    const result = await loop.run([
      { role: "user", content: "Do something" },
    ]);
    expect(result.completed).toBe(false);
    expect(result.finalText).toContain("no api_call");
  });

  it("captures final text from text block", async () => {
    const client = makeClient();
    const loop = new ComputerUseAgentLoop(client, {
      model: "claude-opus-4-7-20251101",
      maxTokens: 1024,
      maxIterations: 1,
      toolVersion: "20251124",
      displayWidthPx: 1024,
      displayHeightPx: 768,
    });

    loop.onApiCall(async (_params: ApiCallParams): Promise<ApiResponse> => {
      const content: ContentBlock[] = [
        { type: "text", text: "All done here." },
      ];
      return { id: "msg_final", content, stop_reason: "end_turn" };
    });

    const result = await loop.run([
      { role: "user", content: "Hello" },
    ]);
    expect(result.completed).toBe(true);
    expect(result.finalText).toBe("All done here.");
  });

  it("handles multiple tool calls in one response", async () => {
    const client = makeClient();
    const loop = new ComputerUseAgentLoop(client, {
      model: "claude-opus-4-7-20251101",
      maxTokens: 1024,
      maxIterations: 3,
      toolVersion: "20251124",
      displayWidthPx: 1024,
      displayHeightPx: 768,
    });

    let callCount = 0;

    loop.onApiCall(async (_params: ApiCallParams): Promise<ApiResponse> => {
      callCount++;
      if (callCount === 1) {
        const content: ContentBlock[] = [
          {
            type: "tool_use", id: "toolu_01", name: "computer",
            input: { action: "left_click", coordinate: [100, 200] },
          },
          {
            type: "tool_use", id: "toolu_02", name: "computer",
            input: { action: "type", text: "hello" },
          },
        ];
        return { id: "msg_multi", content, stop_reason: "tool_use" };
      }
      const content: ContentBlock[] = [
        { type: "text", text: "Done." },
      ];
      return { id: "msg_done", content, stop_reason: "end_turn" };
    });

    const result = await loop.run([
      { role: "user", content: "Click and type" },
    ]);
    expect(result.completed).toBe(true);
    // Two calls: one for multi-tool, then text response.
    expect(callCount).toBe(2);
  });
});
