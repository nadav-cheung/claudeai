"""
Tests for Chapter 7 Computer Use client.

Covers:
- Coordinate scaling math
- Action validation (all action types)
- Tool schema construction
- Action execution / dispatch
- Agent loop orchestration
- Error handling (bounds, missing params, unknown actions)
"""

from __future__ import annotations

import base64
import math
from typing import Any

import pytest

from computer_use import (
    MAX_LONG_EDGE,
    MAX_TOTAL_PIXELS,
    ActionValidator,
    ComputerUseAgentLoop,
    AgentLoopConfig,
    AgentLoopResult,
    ComputerUseClient,
    ComputerUseToolSchema,
    ScreenshotResult,
    ToolActionResult,
    get_scale_factor,
    scale_coordinates_down,
    scale_coordinates_up,
    validate_coordinates,
)


# ---------------------------------------------------------------------------
# Coordinate scaling tests
# ---------------------------------------------------------------------------

class TestScaleFactor:
    """Tests for ``get_scale_factor``."""

    def test_no_scaling_for_small_display(self) -> None:
        """1024x768 should not be scaled (well within API limits)."""
        sf = get_scale_factor(1024, 768)
        assert sf == 1.0

    def test_scaling_large_display(self) -> None:
        """A 2560x1440 display should trigger scaling."""
        sf = get_scale_factor(2560, 1440)
        assert 0.0 < sf < 1.0

    def test_very_large_display(self) -> None:
        """4K resolution should produce significant scaling."""
        sf = get_scale_factor(3840, 2160)
        assert sf < 0.5  # Both long-edge and pixel-count constraints apply.

    def test_scale_factor_range(self) -> None:
        """Scale factor must always be in (0, 1]."""
        for w, h in [(800, 600), (1024, 768), (1512, 982), (1920, 1080),
                      (2560, 1440), (3840, 2160)]:
            sf = get_scale_factor(w, h)
            assert 0.0 < sf <= 1.0, f"Scale factor {sf} out of range for {w}x{h}"

    def test_invalid_dimensions_raise(self) -> None:
        """Zero or negative dimensions should raise ValueError."""
        with pytest.raises(ValueError):
            get_scale_factor(0, 768)
        with pytest.raises(ValueError):
            get_scale_factor(1024, -1)


class TestCoordinateScaling:
    """Tests for up/down coordinate scaling."""

    def test_scale_up_noop(self) -> None:
        """With scale=1.0, coordinates should be unchanged."""
        assert scale_coordinates_up(100, 200, 1.0) == (100, 200)

    def test_scale_up(self) -> None:
        """Scaling up should map API-space to larger screen-space."""
        x, y = scale_coordinates_up(665, 432, 0.5)
        # round(665 / 0.5) = 1330, round(432 / 0.5) = 864
        assert x == 1330
        assert y == 864

    def test_scale_down(self) -> None:
        """Scaling down should map screen-space to smaller API-space."""
        x, y = scale_coordinates_down(1330, 864, 0.5)
        assert x == 665
        assert y == 432

    def test_scale_round_behavior(self) -> None:
        """Coordinates should round to nearest integer."""
        x, y = scale_coordinates_up(100, 100, 0.333)
        # 100 / 0.333 ≈ 300.3003 → round to 300
        assert isinstance(x, int)
        assert isinstance(y, int)

    def test_invalid_scale_raises(self) -> None:
        """Scale factors outside (0, 1] should raise."""
        with pytest.raises(ValueError):
            scale_coordinates_up(10, 10, 0)
        with pytest.raises(ValueError):
            scale_coordinates_up(10, 10, 1.5)
        with pytest.raises(ValueError):
            scale_coordinates_up(10, 10, -0.1)


class TestCoordinateValidation:
    """Tests for ``validate_coordinates``."""

    def test_in_bounds(self) -> None:
        valid, err = validate_coordinates(500, 300, 1024, 768)
        assert valid is True
        assert err is None

    def test_at_origin(self) -> None:
        valid, err = validate_coordinates(0, 0, 1024, 768)
        assert valid is True

    def test_at_edge(self) -> None:
        valid, err = validate_coordinates(1023, 767, 1024, 768)
        assert valid is True

    def test_x_out_of_bounds(self) -> None:
        valid, err = validate_coordinates(1024, 500, 1024, 768)
        assert valid is False
        assert err is not None
        assert "X coordinate" in err

    def test_y_out_of_bounds(self) -> None:
        valid, err = validate_coordinates(500, 768, 1024, 768)
        assert valid is False
        assert err is not None
        assert "Y coordinate" in err

    def test_negative_coordinates(self) -> None:
        valid, err = validate_coordinates(-1, 500, 1024, 768)
        assert valid is False


# ---------------------------------------------------------------------------
# ActionValidator tests
# ---------------------------------------------------------------------------

class TestActionValidator:
    """Tests for action parameter validation."""

    @pytest.fixture
    def validator(self) -> ActionValidator:
        return ActionValidator(display_width=1280, display_height=720)

    # -- screenshot --

    def test_screenshot_valid(self, validator: ActionValidator) -> None:
        valid, err = validator.validate("screenshot", {})
        assert valid is True

    # -- click actions --

    def test_left_click_valid(self, validator: ActionValidator) -> None:
        valid, err = validator.validate("left_click", {"coordinate": [500, 300]})
        assert valid is True

    def test_click_missing_coordinate(self, validator: ActionValidator) -> None:
        valid, err = validator.validate("left_click", {})
        assert valid is False
        assert "coordinate" in (err or "")

    def test_click_out_of_bounds(self, validator: ActionValidator) -> None:
        valid, err = validator.validate("left_click", {"coordinate": [1300, 300]})
        assert valid is False

    def test_right_click_valid(self, validator: ActionValidator) -> None:
        valid, err = validator.validate("right_click", {"coordinate": [10, 10]})
        assert valid is True

    def test_middle_click_valid(self, validator: ActionValidator) -> None:
        valid, err = validator.validate("middle_click", {"coordinate": [640, 360]})
        assert valid is True

    def test_double_click_valid(self, validator: ActionValidator) -> None:
        valid, err = validator.validate("double_click", {"coordinate": [100, 200]})
        assert valid is True

    def test_triple_click_valid(self, validator: ActionValidator) -> None:
        valid, err = validator.validate("triple_click", {"coordinate": [100, 200]})
        assert valid is True

    # -- mouse_move --

    def test_mouse_move_valid(self, validator: ActionValidator) -> None:
        valid, err = validator.validate("mouse_move", {"coordinate": [640, 360]})
        assert valid is True

    # -- drag --

    def test_left_click_drag_valid(self, validator: ActionValidator) -> None:
        valid, err = validator.validate(
            "left_click_drag", {"coordinate": [800, 600]}
        )
        assert valid is True

    # -- type / key / hold_key --

    def test_type_valid(self, validator: ActionValidator) -> None:
        valid, err = validator.validate("type", {"text": "hello"})
        assert valid is True

    def test_type_missing_text(self, validator: ActionValidator) -> None:
        valid, err = validator.validate("type", {})
        assert valid is False

    def test_key_valid(self, validator: ActionValidator) -> None:
        valid, err = validator.validate("key", {"text": "ctrl+s"})
        assert valid is True

    def test_hold_key_valid(self, validator: ActionValidator) -> None:
        valid, err = validator.validate("hold_key", {"text": "shift", "duration": 2.0})
        assert valid is True

    # -- scroll --

    def test_scroll_valid(self, validator: ActionValidator) -> None:
        valid, err = validator.validate(
            "scroll",
            {"coordinate": [500, 400], "scroll_direction": "down", "scroll_amount": 3},
        )
        assert valid is True

    def test_scroll_bad_direction(self, validator: ActionValidator) -> None:
        valid, err = validator.validate(
            "scroll",
            {"scroll_direction": "diagonal", "scroll_amount": 1},
        )
        assert valid is False

    def test_scroll_negative_amount(self, validator: ActionValidator) -> None:
        valid, err = validator.validate(
            "scroll",
            {"scroll_direction": "up", "scroll_amount": -1},
        )
        assert valid is False

    # -- wait --

    def test_wait_valid(self, validator: ActionValidator) -> None:
        valid, err = validator.validate("wait", {"duration": 0.5})
        assert valid is True

    def test_wait_invalid_duration(self, validator: ActionValidator) -> None:
        valid, err = validator.validate("wait", {"duration": -1})
        assert valid is False

    # -- mouse button state --
    def test_left_mouse_down_valid(self, validator: ActionValidator) -> None:
        valid, err = validator.validate("left_mouse_down", {})
        assert valid is True

    def test_left_mouse_up_valid(self, validator: ActionValidator) -> None:
        valid, err = validator.validate("left_mouse_up", {})
        assert valid is True

    # -- cursor_position --
    def test_cursor_position_valid(self, validator: ActionValidator) -> None:
        valid, err = validator.validate("cursor_position", {})
        assert valid is True

    # -- zoom (20251124) --
    def test_zoom_valid(self, validator: ActionValidator) -> None:
        valid, err = validator.validate("zoom", {"region": [100, 200, 400, 350]})
        assert valid is True

    def test_zoom_missing_region(self, validator: ActionValidator) -> None:
        valid, err = validator.validate("zoom", {})
        assert valid is False

    # -- unknown action --
    def test_unknown_action(self, validator: ActionValidator) -> None:
        valid, err = validator.validate("explode", {})
        assert valid is False

    # -- known_actions --
    def test_known_actions(self, validator: ActionValidator) -> None:
        actions = validator.known_actions()
        assert "screenshot" in actions
        assert "left_click" in actions
        assert "scroll" in actions
        assert "zoom" in actions
        assert "type" in actions
        assert "wait" in actions


# ---------------------------------------------------------------------------
# ComputerUseToolSchema tests
# ---------------------------------------------------------------------------

class TestComputerUseToolSchema:

    def test_default_schema(self) -> None:
        schema = ComputerUseToolSchema()
        d = schema.to_dict()
        assert d["type"] == "computer_20251124"
        assert d["name"] == "computer"
        assert d["display_width_px"] == 1024
        assert d["display_height_px"] == 768
        assert d["display_number"] == 1

    def test_custom_dimensions(self) -> None:
        schema = ComputerUseToolSchema(
            display_width_px=1920, display_height_px=1080,
        )
        d = schema.to_dict()
        assert d["display_width_px"] == 1920
        assert d["display_height_px"] == 1080

    def test_version_20250124(self) -> None:
        schema = ComputerUseToolSchema(tool_version="20250124")
        assert schema.to_dict()["type"] == "computer_20250124"

    def test_beta_header(self) -> None:
        s1 = ComputerUseToolSchema(tool_version="20250124")
        assert s1.beta_header == "computer-use-2025-01-24"
        s2 = ComputerUseToolSchema(tool_version="20251124")
        assert s2.beta_header == "computer-use-2025-11-24"

    def test_invalid_version_raises(self) -> None:
        with pytest.raises(ValueError):
            ComputerUseToolSchema(tool_version="20241022")

    def test_enable_zoom(self) -> None:
        schema = ComputerUseToolSchema(enable_zoom=True)
        d = schema.to_dict()
        assert d["enable_zoom"] is True

    def test_zoom_not_in_20250124(self) -> None:
        """enable_zoom should only appear in 20251124 schemas."""
        schema = ComputerUseToolSchema(tool_version="20250124", enable_zoom=True)
        d = schema.to_dict()
        assert "enable_zoom" not in d

    def test_display_number_none(self) -> None:
        schema = ComputerUseToolSchema(display_number=None)
        d = schema.to_dict()
        assert "display_number" not in d


# ---------------------------------------------------------------------------
# ComputerUseClient tests
# ---------------------------------------------------------------------------

class TestComputerUseClient:
    """Tests for the ComputerUseClient action execution."""

    @pytest.fixture
    def client(self) -> ComputerUseClient:
        return ComputerUseClient(display_width_px=1280, display_height_px=720)

    # -- build_tool_schema --
    def test_build_tool_schema(self, client: ComputerUseClient) -> None:
        schema = client.build_tool_schema()
        assert schema["type"] == "computer_20251124"
        assert schema["display_width_px"] == 1280
        assert schema["display_height_px"] == 720

    # -- execute_action: success cases --
    def test_screenshot_action(self, client: ComputerUseClient) -> None:
        result = client.execute_action(action="screenshot")
        assert result.success is True

    def test_left_click_action(self, client: ComputerUseClient) -> None:
        result = client.execute_action(
            action="left_click", coordinate=[640, 360]
        )
        assert result.success is True
        assert "left_click" in (result.output or "")

    def test_mouse_move_action(self, client: ComputerUseClient) -> None:
        result = client.execute_action(
            action="mouse_move", coordinate=[100, 200]
        )
        assert result.success is True
        assert "100" in (result.output or "")
        assert "200" in (result.output or "")

    def test_type_action(self, client: ComputerUseClient) -> None:
        result = client.execute_action(action="type", text="Hello, World!")
        assert result.success is True
        assert "Hello, World!" in (result.output or "")

    def test_key_action(self, client: ComputerUseClient) -> None:
        result = client.execute_action(action="key", text="ctrl+s")
        assert result.success is True

    def test_scroll_action(self, client: ComputerUseClient) -> None:
        result = client.execute_action(
            action="scroll",
            coordinate=[500, 400],
            scroll_direction="down",
            scroll_amount=3,
        )
        assert result.success is True
        assert "down" in (result.output or "")

    def test_wait_action(self, client: ComputerUseClient) -> None:
        result = client.execute_action(action="wait", duration=0.01)
        assert result.success is True

    def test_hold_key_action(self, client: ComputerUseClient) -> None:
        result = client.execute_action(
            action="hold_key", text="shift", duration=1.0,
        )
        assert result.success is True

    # -- execute_action: error cases --
    def test_missing_action(self, client: ComputerUseClient) -> None:
        result = client.execute_action()
        assert result.success is False
        assert "action" in (result.error or "")

    def test_unknown_action(self, client: ComputerUseClient) -> None:
        result = client.execute_action(action="nuclear_launch")
        assert result.success is False

    def test_out_of_bounds_click(self, client: ComputerUseClient) -> None:
        result = client.execute_action(
            action="left_click", coordinate=[9999, 9999],
        )
        assert result.success is False

    # -- convenience methods --
    def test_capture_screenshot_default(self, client: ComputerUseClient) -> None:
        """Without a callback, returns empty string."""
        data = client.capture_screenshot()
        assert data == ""

    def test_move_mouse(self, client: ComputerUseClient) -> None:
        result = client.move_mouse(640, 360)
        assert result.success is True

    def test_click(self, client: ComputerUseClient) -> None:
        result = client.click(100, 200, button="right")
        assert result.success is True
        assert "right_click" in (result.output or "")

    def test_double_click(self, client: ComputerUseClient) -> None:
        result = client.double_click(300, 400)
        assert result.success is True

    def test_type_text(self, client: ComputerUseClient) -> None:
        result = client.type_text("hello world")
        assert result.success is True

    def test_key_combination(self, client: ComputerUseClient) -> None:
        result = client.key_combination(["ctrl", "shift", "t"])
        assert result.success is True
        assert "ctrl+shift+t" in (result.output or "")

    def test_scroll_vertical_only(self, client: ComputerUseClient) -> None:
        result = client.scroll(500, 400, 0, 5)
        assert result.success is True

    def test_scroll_horizontal_only(self, client: ComputerUseClient) -> None:
        result = client.scroll(500, 400, 3, 0)
        assert result.success is True

    def test_scroll_both_axes(self, client: ComputerUseClient) -> None:
        result = client.scroll(500, 400, 2, -3)
        assert result.success is True

    def test_scroll_no_movement(self, client: ComputerUseClient) -> None:
        result = client.scroll(500, 400, 0, 0)
        assert result.success is True

    def test_drag(self, client: ComputerUseClient) -> None:
        result = client.drag(100, 100, 500, 500)
        assert result.success is True
        assert "Dragged" in (result.output or "")

    # -- screenshot callback --
    def test_screenshot_callback(self) -> None:
        client = ComputerUseClient()
        captured: list[ScreenshotResult] = []

        def fake_screenshot() -> ScreenshotResult:
            sr = ScreenshotResult(
                base64_image=base64.b64encode(b"fake-png-data").decode(),
                width=1024,
                height=768,
            )
            captured.append(sr)
            return sr

        client.on_screenshot(fake_screenshot)
        result = client.execute_action(action="screenshot")
        assert result.success is True
        assert len(captured) == 1
        assert result.screenshot is not None
        assert result.screenshot.width == 1024

    # -- mouse callback --
    def test_mouse_callback(self) -> None:
        client = ComputerUseClient()
        calls: list[dict[str, Any]] = []

        def track_mouse(**kwargs: Any) -> None:
            calls.append(kwargs)

        client.on_mouse(track_mouse)
        client.execute_action(action="left_click", coordinate=[300, 200])
        assert len(calls) == 1
        assert calls[0]["action"] == "left_click"
        assert calls[0]["x"] == 300
        assert calls[0]["y"] == 200

    # -- keyboard callback --
    def test_keyboard_callback(self) -> None:
        client = ComputerUseClient()
        calls: list[dict[str, Any]] = []

        def track_kb(**kwargs: Any) -> None:
            calls.append(kwargs)

        client.on_keyboard(track_kb)
        client.execute_action(action="type", text="abc")
        assert len(calls) == 1
        assert calls[0]["text"] == "abc"

    # -- format_tool_result --
    def test_format_tool_result_success(self) -> None:
        result = ToolActionResult(success=True, output="done")
        formatted = ComputerUseClient.format_tool_result(
            result, "toolu_01X", include_screenshot=False,
        )
        assert formatted["type"] == "tool_result"
        assert formatted["tool_use_id"] == "toolu_01X"
        assert formatted["is_error"] is False
        assert len(formatted["content"]) == 1
        assert formatted["content"][0]["text"] == "done"

    def test_format_tool_result_error(self) -> None:
        result = ToolActionResult(success=False, error="boom")
        formatted = ComputerUseClient.format_tool_result(
            result, "toolu_01Y", include_screenshot=False,
        )
        assert formatted["is_error"] is True
        assert formatted["content"][0]["text"] == "boom"

    def test_format_tool_result_with_screenshot(self) -> None:
        sr = ScreenshotResult(
            base64_image="aW1hZ2U=", width=800, height=600,
        )
        result = ToolActionResult(success=True, output="ok", screenshot=sr)
        formatted = ComputerUseClient.format_tool_result(
            result, "toolu_01Z", include_screenshot=True,
        )
        # Should have text + image content blocks.
        assert len(formatted["content"]) == 2
        assert formatted["content"][1]["type"] == "image"
        assert formatted["content"][1]["source"]["data"] == "aW1hZ2U="

    def test_format_tool_result_exclude_screenshot(self) -> None:
        sr = ScreenshotResult(base64_image="aW1hZ2U=")
        result = ToolActionResult(success=True, output="ok", screenshot=sr)
        formatted = ComputerUseClient.format_tool_result(
            result, "toolu_01Z", include_screenshot=False,
        )
        assert len(formatted["content"]) == 1  # no image block


# ---------------------------------------------------------------------------
# AgentLoop tests
# ---------------------------------------------------------------------------

class TestAgentLoop:
    """Tests for the computer use agent loop orchestration."""

    @pytest.fixture
    def computer_client(self) -> ComputerUseClient:
        return ComputerUseClient(display_width_px=1024, display_height_px=768)

    @pytest.fixture
    def config(self) -> AgentLoopConfig:
        return AgentLoopConfig(
            model="claude-sonnet-4-20250514",
            max_tokens=1024,
            max_iterations=5,
        )

    def test_runs_to_completion(
        self, computer_client: ComputerUseClient, config: AgentLoopConfig,
    ) -> None:
        """Agent loop should complete when Claude returns text only."""
        loop = ComputerUseAgentLoop(computer_client, config=config)

        call_count = 0

        def fake_api_call(**kwargs: Any) -> dict[str, Any]:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                # First call: request a screenshot.
                return {
                    "id": "msg_001",
                    "content": [
                        {
                            "type": "tool_use",
                            "id": "toolu_01A",
                            "name": "computer",
                            "input": {"action": "screenshot"},
                        }
                    ],
                    "stop_reason": "tool_use",
                }
            else:
                # Second call: text response (task complete).
                return {
                    "id": "msg_002",
                    "content": [
                        {"type": "text", "text": "Task completed successfully."}
                    ],
                    "stop_reason": "end_turn",
                }

        loop.on_api_call(fake_api_call)
        result = loop.run(
            [{"role": "user", "content": "Take a screenshot"}],
        )
        assert result.completed is True
        assert result.iterations == 2
        assert "completed" in (result.final_text or "")

    def test_stops_at_max_iterations(
        self, computer_client: ComputerUseClient, config: AgentLoopConfig,
    ) -> None:
        """Agent loop should stop when max_iterations is reached."""
        config.max_iterations = 2
        loop = ComputerUseAgentLoop(computer_client, config=config)

        def always_tool_use(**kwargs: Any) -> dict[str, Any]:
            return {
                "id": "msg_x",
                "content": [
                    {
                        "type": "tool_use",
                        "id": "toolu_01X",
                        "name": "computer",
                        "input": {"action": "screenshot"},
                    }
                ],
                "stop_reason": "tool_use",
            }

        loop.on_api_call(always_tool_use)
        result = loop.run(
            [{"role": "user", "content": "Loop forever..."}],
        )
        assert result.completed is False
        assert result.iterations == 2

    def test_no_api_callback_returns_error(
        self, computer_client: ComputerUseClient, config: AgentLoopConfig,
    ) -> None:
        """Without an api_call callback, the loop should return an error."""
        loop = ComputerUseAgentLoop(computer_client, config=config)
        # Intentionally do NOT register api_call.
        result = loop.run(
            [{"role": "user", "content": "Do something"}],
        )
        assert result.completed is False
        assert result.final_text is not None
        assert "no api_call" in result.final_text

    def test_multiple_tool_calls_in_one_response(
        self, computer_client: ComputerUseClient, config: AgentLoopConfig,
    ) -> None:
        """A single response with multiple tool_use blocks should all be executed."""
        loop = ComputerUseAgentLoop(computer_client, config=config)

        def multi_tool_response(**kwargs: Any) -> dict[str, Any]:
            return {
                "id": "msg_multi",
                "content": [
                    {
                        "type": "tool_use",
                        "id": "toolu_01",
                        "name": "computer",
                        "input": {"action": "left_click", "coordinate": [100, 200]},
                    },
                    {
                        "type": "tool_use",
                        "id": "toolu_02",
                        "name": "computer",
                        "input": {"action": "type", "text": "hello"},
                    },
                ],
                "stop_reason": "tool_use",
            }

        loop.on_api_call(multi_tool_response)
        result = loop.run(
            [{"role": "user", "content": "Click and type"}],
        )
        # Should have made 1 API call (then returned tool results),
        # but since mock always returns tool_use, it'll hit max_iterations.
        assert result.iterations == config.max_iterations

    def test_tool_use_then_text(
        self, computer_client: ComputerUseClient, config: AgentLoopConfig,
    ) -> None:
        """Screenshot, then text = completion."""
        loop = ComputerUseAgentLoop(computer_client, config=config)

        call_counter = [0]

        def two_step_response(**kwargs: Any) -> dict[str, Any]:
            call_counter[0] += 1
            if call_counter[0] == 1:
                return {
                    "id": "msg_1",
                    "content": [
                        {
                            "type": "tool_use",
                            "id": "toolu_ss",
                            "name": "computer",
                            "input": {"action": "screenshot"},
                        },
                        {
                            "type": "text",
                            "text": "Let me take a screenshot first.",
                        },
                    ],
                    "stop_reason": "tool_use",
                }
            else:
                return {
                    "id": "msg_2",
                    "content": [
                        {"type": "text", "text": "Done after screenshot."}
                    ],
                    "stop_reason": "end_turn",
                }

        loop.on_api_call(two_step_response)
        result = loop.run(
            [{"role": "user", "content": "Take a screenshot and confirm"}],
        )
        assert result.completed is True
        assert result.iterations == 2

    def test_final_text_captured(self) -> None:
        """The last text block should be captured as final_text."""
        client = ComputerUseClient()
        loop = ComputerUseAgentLoop(client, config=AgentLoopConfig(max_iterations=1))

        def text_only(**kwargs: Any) -> dict[str, Any]:
            return {
                "id": "msg_final",
                "content": [
                    {"type": "text", "text": "All done here."}
                ],
                "stop_reason": "end_turn",
            }

        loop.on_api_call(text_only)
        result = loop.run(
            [{"role": "user", "content": "Hello"}],
        )
        assert result.completed is True
        assert result.final_text == "All done here."


# ---------------------------------------------------------------------------
# Property and constant tests
# ---------------------------------------------------------------------------

class TestClientProperties:

    def test_properties(self) -> None:
        client = ComputerUseClient(
            display_width_px=1920,
            display_height_px=1080,
            tool_version="20250124",
        )
        assert client.display_width == 1920
        assert client.display_height == 1080
        assert client.tool_version == "20250124"
        assert client.beta_header == "computer-use-2025-01-24"

    def test_scale_factor_for_default_resolution(self) -> None:
        client = ComputerUseClient(display_width_px=1024, display_height_px=768)
        assert client.scale_factor == 1.0

    def test_scale_factor_for_large_resolution(self) -> None:
        client = ComputerUseClient(display_width_px=2560, display_height_px=1440)
        assert client.scale_factor < 1.0

    def test_auto_scale_disabled(self) -> None:
        """When auto_scale=False, coordinates pass through unchanged."""
        client = ComputerUseClient(
            display_width_px=2560, display_height_px=1440,
            auto_scale=False,
        )
        # With auto_scale off, _resolve_coords returns values unchanged.
        # dispatch uses _resolve_coords, so the output should show
        # unscaled coordinates.
        result = client.execute_action(
            action="mouse_move", coordinate=[1000, 500]
        )
        assert "1000" in (result.output or "")
        assert "500" in (result.output or "")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
