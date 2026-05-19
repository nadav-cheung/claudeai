/**
 * Chapter 7: Computer Use — client-side protocol handler (TypeScript).
 *
 * Implements the Computer Use tool schema, action dispatching, coordinate
 * scaling, and the agent loop pattern.  No external runtime dependencies
 * beyond the platform.  Strict TypeScript with zero `any` usage.
 */

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

/** Maximum image dimensions the API accepts (earlier models). */
const MAX_LONG_EDGE = 1568;
const MAX_TOTAL_PIXELS = 1_150_000;

/** Recommended display resolutions from Anthropic documentation. */
const RECOMMENDED_RESOLUTIONS: Record<string, readonly [number, number]> = {
  XGA: [1024, 768],       // 4:3, general desktop
  WXGA: [1280, 800],      // 16:10, web applications
  FWXGA: [1366, 768],     // ~16:9, web applications
  FHD: [1920, 1080],      // 16:9, max recommended
} as const;

/** Beta headers by tool version. */
const BETA_HEADERS: Record<string, string> = {
  "20251124": "computer-use-2025-11-24",
  "20250124": "computer-use-2025-01-24",
};

/** Known action types for the computer_20250124 schema. */
type Action =
  | "screenshot"
  | "left_click"
  | "right_click"
  | "middle_click"
  | "double_click"
  | "triple_click"
  | "left_click_drag"
  | "left_mouse_down"
  | "left_mouse_up"
  | "mouse_move"
  | "type"
  | "key"
  | "hold_key"
  | "scroll"
  | "wait"
  | "cursor_position"
  | "zoom";

type ScrollDirection = "up" | "down" | "left" | "right";
type MouseButton = "left" | "right" | "middle";

/** A 2D coordinate [x, y]. */
type Coordinate = readonly [number, number];

// ---------------------------------------------------------------------------
// Data types
// ---------------------------------------------------------------------------

export interface ScreenshotResult {
  readonly base64Image: string;
  readonly mediaType: string;
  readonly width: number;
  readonly height: number;
}

export interface ToolActionResult {
  readonly success: boolean;
  readonly output: string | null;
  readonly error: string | null;
  readonly screenshot: ScreenshotResult | null;
}

export interface ToolResultContentBlock {
  readonly type: "tool_result";
  readonly tool_use_id: string;
  readonly content: ReadonlyArray<Record<string, unknown>>;
  readonly is_error: boolean;
}

export interface ContentBlock {
  readonly type: string;
  readonly id?: string;
  readonly name?: string;
  readonly input?: Record<string, unknown>;
  readonly text?: string;
}

export interface ApiResponse {
  readonly id: string;
  readonly content: ReadonlyArray<ContentBlock>;
  readonly stop_reason: string;
}

// Callback signatures
export type ScreenshotCallback = () => ScreenshotResult | Promise<ScreenshotResult>;
export type MouseCallback = (params: MouseActionParams) => void | Promise<void>;
export type KeyboardCallback = (params: KeyboardActionParams) => void | Promise<void>;
export type ApiCallCallback = (params: ApiCallParams) => Promise<ApiResponse>;

export interface MouseActionParams {
  action: string;
  x?: number;
  y?: number;
  modifiers?: string;
  direction?: string;
  amount?: number;
  endX?: number;
  endY?: number;
}

export interface KeyboardActionParams {
  action: string;
  text: string;
  duration?: number;
}

export interface ApiCallParams {
  model: string;
  max_tokens: number;
  messages: ReadonlyArray<Record<string, unknown>>;
  tools: ReadonlyArray<Record<string, unknown>>;
  system?: string;
  betas: ReadonlyArray<string>;
}

export interface AgentLoopConfig {
  readonly model: string;
  readonly maxTokens: number;
  readonly maxIterations: number;
  readonly toolVersion: string;
  readonly displayWidthPx: number;
  readonly displayHeightPx: number;
}

export interface AgentLoopResult {
  readonly messages: Array<Record<string, unknown>>;
  readonly iterations: number;
  readonly completed: boolean;
  readonly finalText: string | null;
}

// ---------------------------------------------------------------------------
// Coordinate scaling (pure functions)
// ---------------------------------------------------------------------------

/**
 * Calculate scale factor to meet API image constraints.
 *
 * Constrains images to MAX_LONG_EDGE px on the longest edge and
 * ~MAX_TOTAL_PIXELS total.  Returns a factor in (0, 1].
 */
export function getScaleFactor(width: number, height: number): number {
  if (width <= 0 || height <= 0) {
    throw new Error(`Invalid dimensions: ${width}x${height}`);
  }

  const longEdge = Math.max(width, height);
  const totalPixels = width * height;

  const longEdgeScale = MAX_LONG_EDGE / longEdge;
  const totalPixelsScale = Math.sqrt(MAX_TOTAL_PIXELS / totalPixels);

  return Math.min(1.0, longEdgeScale, totalPixelsScale);
}

/**
 * Scale coordinates from API-space back to screen-space.
 */
export function scaleCoordinatesUp(
  x: number,
  y: number,
  scale: number,
): [number, number] {
  if (scale <= 0 || scale > 1) {
    throw new Error(`Scale factor must be in (0, 1], got ${scale}`);
  }
  return [Math.round(x / scale), Math.round(y / scale)];
}

/**
 * Scale coordinates from screen-space to API-space.
 */
export function scaleCoordinatesDown(
  x: number,
  y: number,
  scale: number,
): [number, number] {
  if (scale <= 0 || scale > 1) {
    throw new Error(`Scale factor must be in (0, 1], got ${scale}`);
  }
  return [Math.round(x * scale), Math.round(y * scale)];
}

/**
 * Check whether coordinates are within display bounds.
 */
export function validateCoordinates(
  x: number,
  y: number,
  displayWidth: number,
  displayHeight: number,
): { valid: true; error: null } | { valid: false; error: string } {
  if (x < 0 || x >= displayWidth) {
    return { valid: false, error: `X coordinate ${x} out of bounds [0, ${displayWidth})` };
  }
  if (y < 0 || y >= displayHeight) {
    return { valid: false, error: `Y coordinate ${y} out of bounds [0, ${displayHeight})` };
  }
  return { valid: true, error: null };
}

// ---------------------------------------------------------------------------
// Action validator
// ---------------------------------------------------------------------------

const KNOWN_ACTIONS: ReadonlySet<string> = new Set([
  "screenshot", "left_click", "right_click", "middle_click",
  "double_click", "triple_click", "left_click_drag",
  "left_mouse_down", "left_mouse_up", "mouse_move",
  "type", "key", "hold_key", "scroll", "wait",
  "cursor_position", "zoom",
]);

export class ActionValidator {
  constructor(
    private readonly displayWidth: number = 1024,
    private readonly displayHeight: number = 768,
  ) {}

  validate(
    action: string,
    params: Readonly<Record<string, unknown>>,
  ): { valid: true; error: null } | { valid: false; error: string } {
    // screenshot: no params needed
    if (action === "screenshot") {
      return { valid: true, error: null };
    }

    // Click / move / drag actions: require coordinate
    if (
      action === "left_click" ||
      action === "right_click" ||
      action === "middle_click" ||
      action === "double_click" ||
      action === "triple_click" ||
      action === "mouse_move" ||
      action === "left_click_drag"
    ) {
      const coord = params["coordinate"];
      if (coord === undefined) {
        return { valid: false, error: `Action '${action}' requires 'coordinate' parameter` };
      }
      if (!Array.isArray(coord) || coord.length !== 2) {
        return { valid: false, error: `'coordinate' must be [x, y], got ${JSON.stringify(coord)}` };
      }
      const [x, y] = coord as [number, number];
      if (typeof x !== "number" || typeof y !== "number") {
        return { valid: false, error: `Coordinates must be numbers` };
      }
      const result = validateCoordinates(
        x, y, this.displayWidth, this.displayHeight,
      );
      if (!result.valid) {
        return result;
      }
      return { valid: true, error: null };
    }

    // type / key / hold_key: require text
    if (action === "type" || action === "key" || action === "hold_key") {
      if (!("text" in params)) {
        return { valid: false, error: `Action '${action}' requires 'text' parameter` };
      }
      return { valid: true, error: null };
    }

    // scroll
    if (action === "scroll") {
      const direction = params["scroll_direction"];
      if (
        direction !== "up" &&
        direction !== "down" &&
        direction !== "left" &&
        direction !== "right"
      ) {
        return { valid: false, error: `Invalid scroll_direction: ${String(direction)}` };
      }
      const amount = params["scroll_amount"];
      if (amount !== undefined && (typeof amount !== "number" || amount < 0)) {
        return { valid: false, error: `scroll_amount must be a non-negative number` };
      }
      return { valid: true, error: null };
    }

    // wait
    if (action === "wait") {
      const duration = params["duration"];
      if (duration !== undefined && (typeof duration !== "number" || duration < 0)) {
        return { valid: false, error: `duration must be a non-negative number` };
      }
      return { valid: true, error: null };
    }

    // left_mouse_down / left_mouse_up
    if (action === "left_mouse_down" || action === "left_mouse_up") {
      return { valid: true, error: null };
    }

    // cursor_position
    if (action === "cursor_position") {
      return { valid: true, error: null };
    }

    // zoom (computer_20251124)
    if (action === "zoom") {
      const region = params["region"];
      if (region === undefined) {
        return { valid: false, error: `Action 'zoom' requires 'region' parameter` };
      }
      if (!Array.isArray(region) || region.length !== 4) {
        return { valid: false, error: `'region' must be [x1, y1, x2, y2]` };
      }
      return { valid: true, error: null };
    }

    return { valid: false, error: `Unknown action: '${action}'` };
  }

  get knownActions(): ReadonlySet<string> {
    return KNOWN_ACTIONS;
  }
}

// ---------------------------------------------------------------------------
// Tool schema builder
// ---------------------------------------------------------------------------

export class ComputerUseToolSchema {
  constructor(
    public readonly displayWidthPx: number = 1024,
    public readonly displayHeightPx: number = 768,
    public readonly displayNumber: number | null = 1,
    public readonly toolVersion: string = "20251124",
    public readonly enableZoom: boolean = false,
  ) {
    if (toolVersion !== "20250124" && toolVersion !== "20251124") {
      throw new Error(
        `toolVersion must be '20250124' or '20251124', got '${toolVersion}'`,
      );
    }
  }

  toDict(): Record<string, unknown> {
    const tool: Record<string, unknown> = {
      type: `computer_${this.toolVersion}`,
      name: "computer",
      display_width_px: this.displayWidthPx,
      display_height_px: this.displayHeightPx,
    };
    if (this.displayNumber !== null) {
      tool["display_number"] = this.displayNumber;
    }
    if (this.toolVersion === "20251124" && this.enableZoom) {
      tool["enable_zoom"] = true;
    }
    return tool;
  }

  get betaHeader(): string {
    const header = BETA_HEADERS[this.toolVersion];
    if (!header) {
      throw new Error(`No beta header for tool version ${this.toolVersion}`);
    }
    return header;
  }
}

// ---------------------------------------------------------------------------
// Computer Use Client
// ---------------------------------------------------------------------------

export class ComputerUseClient {
  static readonly SCREENSHOT_TOOL: Record<string, unknown> = {
    name: "computer",
    display_width_px: 1920,
    display_height_px: 1080,
  };

  private readonly _schema: ComputerUseToolSchema;
  private readonly _validator: ActionValidator;
  private readonly _autoScale: boolean;
  private readonly _scale: number;

  private _screenshotCb: ScreenshotCallback | null = null;
  private _mouseCb: MouseCallback | null = null;
  private _keyboardCb: KeyboardCallback | null = null;

  constructor(options: {
    displayWidthPx?: number;
    displayHeightPx?: number;
    displayNumber?: number | null;
    toolVersion?: string;
    enableZoom?: boolean;
    autoScale?: boolean;
  } = {}) {
    const {
      displayWidthPx = 1024,
      displayHeightPx = 768,
      displayNumber = 1,
      toolVersion = "20251124",
      enableZoom = false,
      autoScale = true,
    } = options;

    this._schema = new ComputerUseToolSchema(
      displayWidthPx,
      displayHeightPx,
      displayNumber,
      toolVersion,
      enableZoom,
    );
    this._validator = new ActionValidator(displayWidthPx, displayHeightPx);
    this._autoScale = autoScale;
    this._scale = getScaleFactor(displayWidthPx, displayHeightPx);
  }

  // -- public properties ----------------------------------------------------

  get displayWidth(): number {
    return this._schema.displayWidthPx;
  }

  get displayHeight(): number {
    return this._schema.displayHeightPx;
  }

  get toolVersion(): string {
    return this._schema.toolVersion;
  }

  get betaHeader(): string {
    return this._schema.betaHeader;
  }

  get scaleFactor(): number {
    return this._scale;
  }

  // -- tool schema ----------------------------------------------------------

  buildToolSchema(): Record<string, unknown> {
    return this._schema.toDict();
  }

  // -- callback registration ------------------------------------------------

  onScreenshot(cb: ScreenshotCallback): void {
    this._screenshotCb = cb;
  }

  onMouse(cb: MouseCallback): void {
    this._mouseCb = cb;
  }

  onKeyboard(cb: KeyboardCallback): void {
    this._keyboardCb = cb;
  }

  // -- action execution -----------------------------------------------------

  async executeAction(params: Record<string, unknown>): Promise<ToolActionResult> {
    const action = params["action"];
    if (typeof action !== "string") {
      return { success: false, output: null, error: "Missing required 'action' parameter", screenshot: null };
    }

    // Validate
    const validation = this._validator.validate(action, params);
    if (!validation.valid) {
      return { success: false, output: null, error: validation.error, screenshot: null };
    }

    // Dispatch
    try {
      return await this._dispatch(action, params);
    } catch (e) {
      return {
        success: false,
        output: null,
        error: `Action '${action}' failed: ${e instanceof Error ? e.message : String(e)}`,
        screenshot: null,
      };
    }
  }

  private async _dispatch(
    action: string,
    params: Readonly<Record<string, unknown>>,
  ): Promise<ToolActionResult> {
    switch (action) {
      case "screenshot":
        return this._handleScreenshot();

      case "left_click":
      case "right_click":
      case "middle_click":
      case "double_click":
      case "triple_click": {
        const [x, y] = this._resolveCoords(params["coordinate"]);
        return this._handleClick(action, x, y, params["text"] as string | undefined);
      }

      case "mouse_move": {
        const [x, y] = this._resolveCoords(params["coordinate"]);
        return this._handleMouseMove(x, y);
      }

      case "left_click_drag": {
        const [x, y] = this._resolveCoords(params["coordinate"]);
        return this._handleDrag(x, y);
      }

      case "left_mouse_down":
      case "left_mouse_up":
        return this._handleMouseButton(action);

      case "scroll": {
        const coord = params["coordinate"];
        let x = 0, y = 0;
        if (Array.isArray(coord) && coord.length === 2) {
          [x, y] = this._resolveCoords(coord);
        }
        return await this._handleScroll(
          x, y,
          (params["scroll_direction"] as string) ?? "down",
          (params["scroll_amount"] as number) ?? 1,
          params["text"] as string | undefined,
        );
      }

      case "type":
      case "key":
        return await this._handleKeyboard(action, params["text"] as string);

      case "hold_key":
        return this._handleHoldKey(
          params["text"] as string,
          (params["duration"] as number) ?? 1.0,
        );

      case "wait":
        return this._handleWait((params["duration"] as number) ?? 1.0);

      case "cursor_position":
        return this._handleCursorPosition();

      case "zoom":
        return this._handleZoom(params["region"] as readonly number[]);

      default:
        return { success: false, output: null, error: `Unhandled action: ${action}`, screenshot: null };
    }
  }

  private _resolveCoords(
    coordinate: unknown,
  ): [number, number] {
    if (!Array.isArray(coordinate) || coordinate.length < 2) {
      return [0, 0];
    }
    let x = Number(coordinate[0]);
    let y = Number(coordinate[1]);
    if (this._autoScale && this._scale < 1.0) {
      [x, y] = scaleCoordinatesUp(x, y, this._scale);
    }
    return [x, y];
  }

  // -- individual action handlers -------------------------------------------

  private async _handleScreenshot(): Promise<ToolActionResult> {
    if (this._screenshotCb) {
      const result = await this._screenshotCb();
      return {
        success: true,
        output: `Screenshot captured: ${result.width}x${result.height}`,
        error: null,
        screenshot: result,
      };
    }
    return {
      success: true,
      output: "[screenshot: no capture callback registered]",
      error: null,
      screenshot: null,
    };
  }

  private async _handleClick(
    action: string,
    x: number,
    y: number,
    modifiers?: string,
  ): Promise<ToolActionResult> {
    if (this._mouseCb) {
      await this._mouseCb({ action, x, y, modifiers });
    }
    const suffix = modifiers ? ` with ${modifiers}` : "";
    return {
      success: true,
      output: `${action} at (${x}, ${y})${suffix}`,
      error: null,
      screenshot: null,
    };
  }

  private async _handleMouseMove(x: number, y: number): Promise<ToolActionResult> {
    if (this._mouseCb) {
      await this._mouseCb({ action: "mouse_move", x, y });
    }
    return {
      success: true,
      output: `Mouse moved to (${x}, ${y})`,
      error: null,
      screenshot: null,
    };
  }

  private async _handleDrag(endX: number, endY: number): Promise<ToolActionResult> {
    if (this._mouseCb) {
      await this._mouseCb({ action: "left_click_drag", endX, endY });
    }
    return {
      success: true,
      output: `Dragged to (${endX}, ${endY})`,
      error: null,
      screenshot: null,
    };
  }

  private async _handleMouseButton(action: string): Promise<ToolActionResult> {
    if (this._mouseCb) {
      await this._mouseCb({ action });
    }
    return { success: true, output: action, error: null, screenshot: null };
  }

  private async _handleScroll(
    x: number,
    y: number,
    direction: string,
    amount: number,
    modifiers?: string,
  ): Promise<ToolActionResult> {
    if (this._mouseCb) {
      await this._mouseCb({ action: "scroll", x, y, direction, amount, modifiers });
    }
    const suffix = modifiers ? ` with ${modifiers}` : "";
    return {
      success: true,
      output: `Scrolled ${direction} x${amount} at (${x}, ${y})${suffix}`,
      error: null,
      screenshot: null,
    };
  }

  private async _handleKeyboard(
    action: string,
    text: string,
  ): Promise<ToolActionResult> {
    if (this._keyboardCb) {
      await this._keyboardCb({ action, text });
    }
    return {
      success: true,
      output: `${action}: ${JSON.stringify(text)}`,
      error: null,
      screenshot: null,
    };
  }

  private _handleHoldKey(text: string, duration: number): ToolActionResult {
    if (this._keyboardCb) {
      void this._keyboardCb({ action: "hold_key", text, duration });
    }
    return {
      success: true,
      output: `hold_key ${JSON.stringify(text)} for ${duration}s`,
      error: null,
      screenshot: null,
    };
  }

  private _handleWait(duration: number): ToolActionResult {
    // In sync context, we cap and note; real apps should use setTimeout/sleep.
    return {
      success: true,
      output: `Waited ${duration}s`,
      error: null,
      screenshot: null,
    };
  }

  private _handleCursorPosition(): ToolActionResult {
    return {
      success: true,
      output: "cursor_position: (not implemented in stub)",
      error: null,
      screenshot: null,
    };
  }

  private _handleZoom(region: readonly number[]): ToolActionResult {
    const [x1, y1, x2, y2] = region;
    return {
      success: true,
      output: `Zoom to region [${x1}, ${y1}, ${x2}, ${y2}]`,
      error: null,
      screenshot: null,
    };
  }

  // -- high-level helpers ---------------------------------------------------

  captureScreenshot(): string {
    // Synchronous stub; real implementation would be async.
    return "";
  }

  moveMouse(x: number, y: number): Promise<ToolActionResult> {
    return this.executeAction({ action: "mouse_move", coordinate: [x, y] });
  }

  click(
    x: number,
    y: number,
    button: MouseButton = "left",
  ): Promise<ToolActionResult> {
    const actionMap: Record<MouseButton, string> = {
      left: "left_click",
      right: "right_click",
      middle: "middle_click",
    };
    const action = actionMap[button] ?? "left_click";
    return this.executeAction({ action, coordinate: [x, y] });
  }

  doubleClick(x: number, y: number): Promise<ToolActionResult> {
    return this.executeAction({ action: "double_click", coordinate: [x, y] });
  }

  typeText(text: string): Promise<ToolActionResult> {
    return this.executeAction({ action: "type", text });
  }

  keyCombination(keys: readonly string[]): Promise<ToolActionResult> {
    const combo = keys.join("+");
    return this.executeAction({ action: "key", text: combo });
  }

  async scroll(
    x: number,
    y: number,
    scrollX: number,
    scrollY: number,
  ): Promise<ToolActionResult> {
    let lastResult: ToolActionResult = {
      success: true,
      output: "No scroll needed",
      error: null,
      screenshot: null,
    };

    if (scrollY !== 0) {
      const direction: ScrollDirection = scrollY > 0 ? "down" : "up";
      lastResult = await this.executeAction({
        action: "scroll",
        coordinate: [x, y],
        scroll_direction: direction,
        scroll_amount: Math.abs(scrollY),
      });
    }

    if (scrollX !== 0) {
      const direction: ScrollDirection = scrollX > 0 ? "right" : "left";
      lastResult = await this.executeAction({
        action: "scroll",
        coordinate: [x, y],
        scroll_direction: direction,
        scroll_amount: Math.abs(scrollX),
      });
    }

    return lastResult;
  }

  async drag(
    startX: number,
    startY: number,
    endX: number,
    endY: number,
  ): Promise<ToolActionResult> {
    await this.executeAction({ action: "mouse_move", coordinate: [startX, startY] });
    return this.executeAction({ action: "left_click_drag", coordinate: [endX, endY] });
  }

  // -- tool result formatting -----------------------------------------------

  static formatToolResult(
    result: ToolActionResult,
    toolUseId: string,
    options: { includeScreenshot?: boolean } = {},
  ): ToolResultContentBlock {
    const { includeScreenshot = true } = options;
    const content: Array<Record<string, unknown>> = [];

    if (result.error) {
      content.push({ type: "text", text: result.error });
    } else if (result.output) {
      content.push({ type: "text", text: result.output });
    }

    if (includeScreenshot && result.screenshot) {
      content.push({
        type: "image",
        source: {
          type: "base64",
          media_type: result.screenshot.mediaType,
          data: result.screenshot.base64Image,
        },
      });
    }

    return {
      type: "tool_result",
      tool_use_id: toolUseId,
      content,
      is_error: !result.success,
    };
  }
}

// ---------------------------------------------------------------------------
// Agent loop
// ---------------------------------------------------------------------------

export const DEFAULT_AGENT_LOOP_CONFIG: AgentLoopConfig = {
  model: "claude-opus-4-7-20251101",
  maxTokens: 4096,
  maxIterations: 10,
  toolVersion: "20251124",
  displayWidthPx: 1024,
  displayHeightPx: 768,
};

export class ComputerUseAgentLoop {
  private _apiCall: ApiCallCallback | null = null;

  constructor(
    private readonly _client: ComputerUseClient,
    private readonly _config: AgentLoopConfig = { ...DEFAULT_AGENT_LOOP_CONFIG },
  ) {}

  onApiCall(cb: ApiCallCallback): void {
    this._apiCall = cb;
  }

  async run(
    messages: Array<Record<string, unknown>>,
    options: { system?: string } = {},
  ): Promise<AgentLoopResult> {
    const tools = [this._client.buildToolSchema()];
    let iterations = 0;
    let finalText: string | null = null;

    while (iterations < this._config.maxIterations) {
      iterations++;

      if (!this._apiCall) {
        return {
          messages,
          iterations,
          completed: false,
          finalText: "Error: no api_call callback registered",
        };
      }

      // Call the API
      const response = await this._apiCall({
        model: this._config.model,
        max_tokens: this._config.maxTokens,
        messages,
        tools,
        system: options.system,
        betas: [this._client.betaHeader],
      });

      // Append assistant message
      const assistantContent = response.content;
      messages.push({ role: "assistant", content: assistantContent });

      // Collect tool results
      const toolResults: Array<ToolResultContentBlock> = [];
      for (const block of assistantContent) {
        if (block.type === "tool_use" && block.id && block.input) {
          const result = await this._client.executeAction(
            block.input as Record<string, unknown>,
          );
          toolResults.push(
            ComputerUseClient.formatToolResult(result, block.id),
          );
        } else if (block.type === "text" && block.text !== undefined) {
          finalText = block.text;
        }
      }

      if (toolResults.length === 0) {
        // Claude responded with text only — task complete.
        return {
          messages,
          iterations,
          completed: true,
          finalText,
        };
      }

      // Send tool results back
      messages.push({ role: "user", content: toolResults });
    }

    return {
      messages,
      iterations,
      completed: false,
      finalText,
    };
  }
}
