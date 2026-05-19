"""
Chapter 7: Computer Use — client-side protocol handler.

Implements the Computer Use tool schema, action dispatching, coordinate
scaling, and the agent loop pattern.  This module does *not* require a
real display or the Anthropic SDK — it demonstrates the protocol-level
contract and is fully testable without external dependencies.
"""

from __future__ import annotations

import base64
import math
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Literal

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Maximum image dimensions the API accepts before automatic resizing.
# Claude Opus 4.7 supports up to 2576 px on the long edge 1:1.
# Earlier models: 1568 px on the long edge, ~1.15 megapixels total.
MAX_LONG_EDGE = 1568
MAX_TOTAL_PIXELS = 1_150_000

# Recommended display resolutions from Anthropic documentation.
RECOMMENDED_RESOLUTIONS: dict[str, tuple[int, int]] = {
    "XGA": (1024, 768),       # 4:3, general desktop
    "WXGA": (1280, 800),      # 16:10, web applications
    "FWXGA": (1366, 768),     # ~16:9, web applications
    "FHD": (1920, 1080),      # 16:9, max recommended
}

# Beta headers by tool version.
BETA_HEADERS: dict[str, str] = {
    "20251124": "computer-use-2025-11-24",
    "20250124": "computer-use-2025-01-24",
}

# Tool definition token cost (Anthropic 4.x models).
TOOL_DEFINITION_TOKENS = 735

# System prompt token overhead for computer use beta.
SYSTEM_PROMPT_OVERHEAD_MIN = 466
SYSTEM_PROMPT_OVERHEAD_MAX = 499


# ---------------------------------------------------------------------------
# Type aliases
# ---------------------------------------------------------------------------

# Actions available in computer_20250124 and computer_20251124.
Action = Literal[
    "screenshot",
    "left_click",
    "right_click",
    "middle_click",
    "double_click",
    "triple_click",
    "left_click_drag",
    "left_mouse_down",
    "left_mouse_up",
    "mouse_move",
    "type",
    "key",
    "hold_key",
    "scroll",
    "wait",
    "cursor_position",
    "zoom",  # computer_20251124 only
]

ScrollDirection = Literal["up", "down", "left", "right"]
MouseButton = Literal["left", "right", "middle"]

Coordinate = tuple[int, int]


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class ScreenshotResult:
    """Result of a screenshot capture action."""
    base64_image: str
    media_type: str = "image/png"
    width: int = 0
    height: int = 0


@dataclass
class ToolActionResult:
    """Result of a computer use action execution."""
    success: bool
    output: str | None = None
    error: str | None = None
    screenshot: ScreenshotResult | None = None

    # Convenience for tool_result compatibility.
    @property
    def is_error(self) -> bool:
        return not self.success


# ---------------------------------------------------------------------------
# Coordinate scaling
# ---------------------------------------------------------------------------

def get_scale_factor(width: int, height: int) -> float:
    """Calculate scale factor to meet API image constraints.

    The API constrains images to a maximum of ``MAX_LONG_EDGE`` pixels on
    the longest edge and approximately ``MAX_TOTAL_PIXELS`` total.  Returns
    a factor in (0, 1] that should be applied to both dimensions.

    For Claude Opus 4.7 (supports up to 2576 px 1:1), no scaling is needed
    for most common resolutions; this function handles earlier models.
    """
    if width <= 0 or height <= 0:
        raise ValueError(f"Invalid dimensions: {width}x{height}")

    long_edge = max(width, height)
    total_pixels = width * height

    long_edge_scale = MAX_LONG_EDGE / long_edge
    total_pixels_scale = math.sqrt(MAX_TOTAL_PIXELS / total_pixels)

    return min(1.0, long_edge_scale, total_pixels_scale)


def scale_coordinates_up(
    x: int, y: int, scale: float
) -> tuple[int, int]:
    """Scale coordinates from API-space back to screen-space.

    When a screenshot has been downscaled for the API, Claude returns
    coordinates in the downscaled space.  This function scales them
    back to the original screen coordinate system.

    Args:
        x: X coordinate from Claude's response.
        y: Y coordinate from Claude's response.
        scale: The scale factor used when downscaling (0 < scale <= 1).

    Returns:
        Screen-space (x, y) as integers.
    """
    if scale <= 0 or scale > 1:
        raise ValueError(f"Scale factor must be in (0, 1], got {scale}")
    return round(x / scale), round(y / scale)


def scale_coordinates_down(
    x: int, y: int, scale: float
) -> tuple[int, int]:
    """Scale coordinates from screen-space to API-space."""
    if scale <= 0 or scale > 1:
        raise ValueError(f"Scale factor must be in (0, 1], got {scale}")
    return round(x * scale), round(y * scale)


def validate_coordinates(
    x: int,
    y: int,
    display_width: int,
    display_height: int,
) -> tuple[bool, str | None]:
    """Check whether coordinates are within display bounds.

    Returns:
        (valid, error_message).  ``error_message`` is None when valid.
    """
    if x < 0 or x >= display_width:
        return False, f"X coordinate {x} out of bounds [0, {display_width})"
    if y < 0 or y >= display_height:
        return False, f"Y coordinate {y} out of bounds [0, {display_height})"
    return True, None


# ---------------------------------------------------------------------------
# Action dispatcher (pure logic, no I/O)
# ---------------------------------------------------------------------------

class ActionValidator:
    """Validates computer use action parameters before execution.

    This class contains *only* validation logic — no side effects.
    It can be used independently of the client for unit testing.
    """

    def __init__(
        self,
        display_width: int = 1024,
        display_height: int = 768,
    ) -> None:
        self.display_width = display_width
        self.display_height = display_height

    def validate(
        self, action: str, params: dict[str, Any]
    ) -> tuple[bool, str | None]:
        """Validate that an action and its parameters are well-formed.

        Returns:
            (valid, error_message).  ``error_message`` is None when valid.
        """
        # --- screenshot: no params needed ---
        if action == "screenshot":
            return True, None

        # --- actions that require coordinates ---
        if action in (
            "left_click", "right_click", "middle_click",
            "double_click", "triple_click",
            "mouse_move", "left_click_drag",
        ):
            coord = params.get("coordinate")
            if coord is None:
                return False, f"Action '{action}' requires 'coordinate' parameter"
            if not isinstance(coord, (list, tuple)) or len(coord) != 2:
                return False, f"'coordinate' must be [x, y], got {coord!r}"
            x, y = coord
            if not (isinstance(x, int) and isinstance(y, int)):
                return False, f"Coordinates must be integers, got ({x!r}, {y!r})"
            valid, msg = validate_coordinates(
                x, y, self.display_width, self.display_height
            )
            if not valid:
                return False, msg
            return True, None

        # --- type / key / hold_key: require text ---
        if action in ("type", "key", "hold_key"):
            if "text" not in params:
                return False, f"Action '{action}' requires 'text' parameter"
            return True, None

        # --- scroll ---
        if action == "scroll":
            direction = params.get("scroll_direction")
            if direction not in ("up", "down", "left", "right"):
                return False, f"Invalid scroll_direction: {direction!r}"
            amount = params.get("scroll_amount", 1)
            if not isinstance(amount, int) or amount < 0:
                return False, f"scroll_amount must be a non-negative int"
            return True, None

        # --- wait ---
        if action == "wait":
            duration = params.get("duration", 1.0)
            if not isinstance(duration, (int, float)) or duration < 0:
                return False, f"duration must be a non-negative number"
            return True, None

        # --- left_mouse_down / left_mouse_up ---
        if action in ("left_mouse_down", "left_mouse_up"):
            return True, None

        # --- cursor_position ---
        if action == "cursor_position":
            return True, None

        # --- zoom (computer_20251124) ---
        if action == "zoom":
            region = params.get("region")
            if region is None:
                return False, f"Action 'zoom' requires 'region' parameter"
            if not isinstance(region, (list, tuple)) or len(region) != 4:
                return False, f"'region' must be [x1, y1, x2, y2]"
            return True, None

        return False, f"Unknown action: {action!r}"

    def known_actions(self) -> frozenset[str]:
        """Return the set of all known action names."""
        return frozenset({
            "screenshot", "left_click", "right_click", "middle_click",
            "double_click", "triple_click", "left_click_drag",
            "left_mouse_down", "left_mouse_up", "mouse_move",
            "type", "key", "hold_key", "scroll", "wait",
            "cursor_position", "zoom",
        })


# ---------------------------------------------------------------------------
# Tool schema builder
# ---------------------------------------------------------------------------

class ComputerUseToolSchema:
    """Builds the tool definition object for the Computer Use tool.

    This is the schema you pass in the ``tools`` array of a Messages API
    request.  It is a schema-less tool — the input schema is built into
    Claude's model and cannot be modified.
    """

    def __init__(
        self,
        display_width_px: int = 1024,
        display_height_px: int = 768,
        display_number: int | None = 1,
        tool_version: str = "20251124",
        enable_zoom: bool = False,
    ) -> None:
        if tool_version not in ("20250124", "20251124"):
            raise ValueError(
                f"tool_version must be '20250124' or '20251124', got {tool_version!r}"
            )
        self.display_width_px = display_width_px
        self.display_height_px = display_height_px
        self.display_number = display_number
        self.tool_version = tool_version
        self.enable_zoom = enable_zoom

    def to_dict(self) -> dict[str, Any]:
        """Return the tool definition as a dict for the API ``tools`` array."""
        tool: dict[str, Any] = {
            "type": f"computer_{self.tool_version}",
            "name": "computer",
            "display_width_px": self.display_width_px,
            "display_height_px": self.display_height_px,
        }
        if self.display_number is not None:
            tool["display_number"] = self.display_number
        if self.tool_version == "20251124" and self.enable_zoom:
            tool["enable_zoom"] = True
        return tool

    @property
    def beta_header(self) -> str:
        """Return the required beta header value for this tool version."""
        return BETA_HEADERS[self.tool_version]


# ---------------------------------------------------------------------------
# Computer Use Client
# ---------------------------------------------------------------------------

class ComputerUseClient:
    """Client-side handler for Computer Use tool interactions.

    This class provides the protocol-level interface for Computer Use:
    it builds tool schemas, validates actions, handles coordinate scaling,
    and processes tool_result blocks.  The actual mouse/keyboard/screenshot
    operations are delegated to pluggable callbacks so the class can be
    tested without a real display.

    Usage::

        client = ComputerUseClient(display_width_px=1920, display_height_px=1080)
        client.capture_screenshot = my_screenshot_fn
        client.click = my_click_fn

        # Build the tool definition for the API request:
        tools = [client.build_tool_schema()]

        # Process a tool_use block from Claude's response:
        result = client.execute_action(action="left_click", coordinate=[500, 300])
    """

    SCREENSHOT_TOOL: dict[str, Any] = {
        "name": "computer",
        "display_width_px": 1920,
        "display_height_px": 1080,
    }

    def __init__(
        self,
        *,
        display_width_px: int = 1024,
        display_height_px: int = 768,
        display_number: int | None = 1,
        tool_version: str = "20251124",
        enable_zoom: bool = False,
        auto_scale: bool = True,
    ) -> None:
        self._schema = ComputerUseToolSchema(
            display_width_px=display_width_px,
            display_height_px=display_height_px,
            display_number=display_number,
            tool_version=tool_version,
            enable_zoom=enable_zoom,
        )
        self._validator = ActionValidator(display_width_px, display_height_px)
        self._auto_scale = auto_scale

        # Compute the scale factor once.
        self._scale = get_scale_factor(display_width_px, display_height_px)

        # Pluggable I/O callbacks — override these in subclasses or
        # assign at runtime.  They are stubbed for testing by default.
        self._screenshot_cb: Callable[[], ScreenshotResult] | None = None
        self._mouse_cb: Callable[..., None] | None = None
        self._keyboard_cb: Callable[..., None] | None = None

    # -- public properties ---------------------------------------------------

    @property
    def display_width(self) -> int:
        return self._schema.display_width_px

    @property
    def display_height(self) -> int:
        return self._schema.display_height_px

    @property
    def tool_version(self) -> str:
        return self._schema.tool_version

    @property
    def beta_header(self) -> str:
        return self._schema.beta_header

    @property
    def scale_factor(self) -> float:
        return self._scale

    # -- tool schema ---------------------------------------------------------

    def build_tool_schema(self) -> dict[str, Any]:
        """Return the computer use tool definition for the API ``tools`` array."""
        return self._schema.to_dict()

    # -- callback registration -----------------------------------------------

    def on_screenshot(self, cb: Callable[[], ScreenshotResult]) -> None:
        """Register a screenshot capture callback."""
        self._screenshot_cb = cb

    def on_mouse(self, cb: Callable[..., None]) -> None:
        """Register a mouse action callback.

        The callback receives keyword arguments matching the action
        parameters (action, coordinate, button, etc.).
        """
        self._mouse_cb = cb

    def on_keyboard(self, cb: Callable[..., None]) -> None:
        """Register a keyboard action callback."""
        self._keyboard_cb = cb

    # -- action execution ----------------------------------------------------

    def execute_action(self, **params: Any) -> ToolActionResult:
        """Execute a single Computer Use action.

        Args:
            **params: Action parameters as received from Claude's tool_use
                      input dict.  Must include ``action``.

        Returns:
            ToolActionResult with success/error and optional screenshot.
        """
        action = params.get("action")
        if not action:
            return ToolActionResult(
                success=False,
                error="Missing required 'action' parameter",
            )

        # Validate.
        valid, err = self._validator.validate(action, params)
        if not valid:
            return ToolActionResult(success=False, error=err)

        # Dispatch.
        try:
            return self._dispatch(action, params)
        except Exception as exc:
            return ToolActionResult(
                success=False,
                error=f"Action '{action}' failed: {exc}",
            )

    def _dispatch(self, action: str, params: dict[str, Any]) -> ToolActionResult:
        """Route action to the appropriate handler."""
        if action == "screenshot":
            return self._handle_screenshot()

        if action in (
            "left_click", "right_click", "middle_click",
            "double_click", "triple_click",
        ):
            x, y = self._resolve_coords(params.get("coordinate"))
            return self._handle_click(action, x, y, params.get("text"))

        if action == "mouse_move":
            x, y = self._resolve_coords(params.get("coordinate"))
            return self._handle_mouse_move(x, y)

        if action == "left_click_drag":
            x, y = self._resolve_coords(params.get("coordinate"))
            return self._handle_drag(x, y)

        if action in ("left_mouse_down", "left_mouse_up"):
            return self._handle_mouse_button(action)

        if action == "scroll":
            x, y = (0, 0)
            if params.get("coordinate"):
                x, y = self._resolve_coords(params["coordinate"])
            return self._handle_scroll(
                x, y,
                params.get("scroll_direction", "down"),
                params.get("scroll_amount", 1),
                params.get("text"),
            )

        if action in ("type", "key"):
            return self._handle_keyboard(action, params["text"])

        if action == "hold_key":
            return self._handle_hold_key(
                params["text"], params.get("duration", 1.0)
            )

        if action == "wait":
            return self._handle_wait(params.get("duration", 1.0))

        if action == "cursor_position":
            return self._handle_cursor_position()

        if action == "zoom":
            return self._handle_zoom(params["region"])

        return ToolActionResult(success=False, error=f"Unhandled action: {action}")

    def _resolve_coords(
        self, coordinate: list[int] | None
    ) -> tuple[int, int]:
        """Resolve and optionally scale coordinates."""
        if coordinate is None:
            return 0, 0
        x, y = coordinate[0], coordinate[1]
        if self._auto_scale and self._scale < 1.0:
            return scale_coordinates_up(x, y, self._scale)
        return x, y

    # -- individual action handlers ------------------------------------------

    def _handle_screenshot(self) -> ToolActionResult:
        if self._screenshot_cb is not None:
            result = self._screenshot_cb()
            return ToolActionResult(
                success=True,
                output=f"Screenshot captured: {result.width}x{result.height}",
                screenshot=result,
            )
        return ToolActionResult(
            success=True,
            output="[screenshot: no capture callback registered]",
        )

    def _handle_click(
        self, action: str, x: int, y: int, modifiers: str | None = None
    ) -> ToolActionResult:
        if self._mouse_cb is not None:
            self._mouse_cb(action=action, x=x, y=y, modifiers=modifiers)
        return ToolActionResult(
            success=True,
            output=f"{action} at ({x}, {y})"
            + (f" with {modifiers}" if modifiers else ""),
        )

    def _handle_mouse_move(self, x: int, y: int) -> ToolActionResult:
        if self._mouse_cb is not None:
            self._mouse_cb(action="mouse_move", x=x, y=y)
        return ToolActionResult(
            success=True, output=f"Mouse moved to ({x}, {y})"
        )

    def _handle_drag(self, end_x: int, end_y: int) -> ToolActionResult:
        """left_click_drag: press at current position, drag to target."""
        if self._mouse_cb is not None:
            self._mouse_cb(action="left_click_drag", end_x=end_x, end_y=end_y)
        return ToolActionResult(
            success=True, output=f"Dragged to ({end_x}, {end_y})"
        )

    def _handle_mouse_button(self, action: str) -> ToolActionResult:
        if self._mouse_cb is not None:
            self._mouse_cb(action=action)
        return ToolActionResult(success=True, output=action)

    def _handle_scroll(
        self,
        x: int,
        y: int,
        direction: str,
        amount: int,
        modifiers: str | None = None,
    ) -> ToolActionResult:
        if self._mouse_cb is not None:
            self._mouse_cb(
                action="scroll", x=x, y=y,
                direction=direction, amount=amount, modifiers=modifiers,
            )
        return ToolActionResult(
            success=True,
            output=f"Scrolled {direction} x{amount} at ({x}, {y})"
            + (f" with {modifiers}" if modifiers else ""),
        )

    def _handle_keyboard(self, action: str, text: str) -> ToolActionResult:
        if self._keyboard_cb is not None:
            self._keyboard_cb(action=action, text=text)
        return ToolActionResult(
            success=True, output=f"{action}: {text!r}"
        )

    def _handle_hold_key(self, text: str, duration: float) -> ToolActionResult:
        if self._keyboard_cb is not None:
            self._keyboard_cb(action="hold_key", text=text, duration=duration)
        return ToolActionResult(
            success=True, output=f"hold_key {text!r} for {duration}s"
        )

    def _handle_wait(self, duration: float) -> ToolActionResult:
        time.sleep(min(duration, 100.0))  # Cap at 100s for safety.
        return ToolActionResult(
            success=True, output=f"Waited {duration}s"
        )

    def _handle_cursor_position(self) -> ToolActionResult:
        return ToolActionResult(
            success=True, output="cursor_position: (not implemented in stub)"
        )

    def _handle_zoom(self, region: list[int]) -> ToolActionResult:
        x1, y1, x2, y2 = region
        return ToolActionResult(
            success=True,
            output=f"Zoom to region [{x1}, {y1}, {x2}, {y2}]",
        )

    # -- high-level helpers --------------------------------------------------

    def capture_screenshot(self) -> str:
        """Take a screenshot and return the base64-encoded PNG string.

        This is a convenience method that calls the registered screenshot
        callback.  In a real implementation this would use Xvfb + scrot
        or platform-specific APIs.
        """
        result = self.execute_action(action="screenshot")
        if result.screenshot is not None:
            return result.screenshot.base64_image
        return ""

    def move_mouse(self, x: int, y: int) -> ToolActionResult:
        """Move the mouse cursor to (x, y) in display coordinates."""
        return self.execute_action(action="mouse_move", coordinate=[x, y])

    def click(
        self, x: int, y: int, button: str = "left"
    ) -> ToolActionResult:
        """Click at (x, y) with the specified mouse button."""
        action_map = {
            "left": "left_click",
            "right": "right_click",
            "middle": "middle_click",
        }
        action = action_map.get(button, "left_click")
        return self.execute_action(action=action, coordinate=[x, y])

    def double_click(self, x: int, y: int) -> ToolActionResult:
        """Double-click at (x, y)."""
        return self.execute_action(action="double_click", coordinate=[x, y])

    def type_text(self, text: str) -> ToolActionResult:
        """Type a string of text."""
        return self.execute_action(action="type", text=text)

    def key_combination(self, keys: list[str]) -> ToolActionResult:
        """Press a key combination (e.g., ['ctrl', 's'])."""
        combo = "+".join(keys)
        return self.execute_action(action="key", text=combo)

    def scroll(
        self,
        x: int,
        y: int,
        scroll_x: int,
        scroll_y: int,
    ) -> ToolActionResult:
        """Scroll at position (x, y).

        Note:
            The Computer Use API supports directional scrolling
            (up/down/left/right) per call.  To achieve a 2D scroll
            we chain two calls when both axes are non-zero.
        """
        results = []
        if scroll_y != 0:
            direction = "down" if scroll_y > 0 else "up"
            results.append(
                self.execute_action(
                    action="scroll",
                    coordinate=[x, y],
                    scroll_direction=direction,
                    scroll_amount=abs(scroll_y),
                )
            )
        if scroll_x != 0:
            direction = "right" if scroll_x > 0 else "left"
            results.append(
                self.execute_action(
                    action="scroll",
                    coordinate=[x, y],
                    scroll_direction=direction,
                    scroll_amount=abs(scroll_x),
                )
            )
        if not results:
            return ToolActionResult(success=True, output="No scroll needed")
        return results[0] if len(results) == 1 else results[-1]

    def drag(
        self,
        start_x: int,
        start_y: int,
        end_x: int,
        end_y: int,
    ) -> ToolActionResult:
        """Press at (start_x, start_y), drag to (end_x, end_y), release."""
        # Move to start position first.
        self.execute_action(action="mouse_move", coordinate=[start_x, start_y])
        # Then drag to end position.
        return self.execute_action(
            action="left_click_drag", coordinate=[end_x, end_y]
        )

    # -- tool result formatting ----------------------------------------------

    @staticmethod
    def format_tool_result(
        result: ToolActionResult,
        tool_use_id: str,
        *,
        include_screenshot: bool = True,
    ) -> dict[str, Any]:
        """Format a ``ToolActionResult`` as an API-compatible ``tool_result`` block.

        This produces the content blob you send back to Claude in a
        ``user`` role message after executing an action.

        Args:
            result: The action result.
            tool_use_id: The ``id`` from Claude's ``tool_use`` block.
            include_screenshot: Whether to embed the screenshot (if any).

        Returns:
            A dict suitable for the ``content`` array of a user message.
        """
        content: list[dict[str, Any]] = []

        if result.error:
            content.append({
                "type": "text",
                "text": result.error,
            })
        elif result.output:
            content.append({
                "type": "text",
                "text": result.output,
            })

        if include_screenshot and result.screenshot is not None:
            content.append({
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": result.screenshot.media_type,
                    "data": result.screenshot.base64_image,
                },
            })

        return {
            "type": "tool_result",
            "tool_use_id": tool_use_id,
            "content": content,
            "is_error": result.is_error,
        }


# ---------------------------------------------------------------------------
# Agent loop
# ---------------------------------------------------------------------------

@dataclass
class AgentLoopConfig:
    """Configuration for the computer use agent loop."""
    model: str = "claude-opus-4-7-20251101"
    max_tokens: int = 4096
    max_iterations: int = 10
    tool_version: str = "20251124"
    display_width_px: int = 1024
    display_height_px: int = 768


@dataclass
class AgentLoopResult:
    """Result of running the computer use agent loop."""
    messages: list[dict[str, Any]]
    iterations: int
    completed: bool  # False if max_iterations was reached.
    final_text: str | None = None


class ComputerUseAgentLoop:
    """Agent loop that drives Claude <-> Computer Use interaction.

    This is the orchestrator that:
    1. Sends messages to Claude with the computer use tool.
    2. Receives tool_use blocks from Claude's response.
    3. Executes actions via ``ComputerUseClient``.
    4. Returns tool_results to Claude.
    5. Repeats until Claude responds with text (no more tool use).

    The actual Messages API call is delegated to an ``api_call`` callback
    so the loop can be tested without a live API connection.
    """

    def __init__(
        self,
        computer_client: ComputerUseClient,
        *,
        config: AgentLoopConfig | None = None,
    ) -> None:
        self._client = computer_client
        self._config = config or AgentLoopConfig()
        self._api_call: Callable[..., dict[str, Any]] | None = None

    def on_api_call(
        self, cb: Callable[..., dict[str, Any]]
    ) -> None:
        """Register a callback for making Messages API calls."""
        self._api_call = cb

    def run(
        self,
        messages: list[dict[str, Any]],
        *,
        system: str | None = None,
    ) -> AgentLoopResult:
        """Run the agent loop until completion or iteration limit.

        Args:
            messages: Initial message list (must include at least one
                      user message with the task).
            system: Optional system prompt.

        Returns:
            AgentLoopResult with final messages and completion status.
        """
        tools = [self._client.build_tool_schema()]
        iterations = 0
        final_text: str | None = None

        while iterations < self._config.max_iterations:
            iterations += 1

            if self._api_call is None:
                return AgentLoopResult(
                    messages=messages,
                    iterations=iterations,
                    completed=False,
                    final_text="Error: no api_call callback registered",
                )

            # Call the API.
            response = self._api_call(
                model=self._config.model,
                max_tokens=self._config.max_tokens,
                messages=messages,
                tools=tools,
                system=system,
                betas=[self._client.beta_header],
            )

            # Append assistant message.
            assistant_content = response.get("content", [])
            messages.append({
                "role": "assistant",
                "content": assistant_content,
            })

            # Collect tool results.
            tool_results: list[dict[str, Any]] = []
            for block in assistant_content:
                if isinstance(block, dict) and block.get("type") == "tool_use":
                    tool_input = block.get("input", {})
                    result = self._client.execute_action(**tool_input)
                    tool_results.append(
                        self._client.format_tool_result(
                            result, block["id"],
                            include_screenshot=True,
                        )
                    )
                elif isinstance(block, dict) and block.get("type") == "text":
                    # Capture the last text response as final output.
                    final_text = block.get("text", "")

            if not tool_results:
                # Claude responded with text only — task complete.
                return AgentLoopResult(
                    messages=messages,
                    iterations=iterations,
                    completed=True,
                    final_text=final_text,
                )

            # Send tool results back.
            messages.append({"role": "user", "content": tool_results})

        return AgentLoopResult(
            messages=messages,
            iterations=iterations,
            completed=False,
            final_text=final_text,
        )
