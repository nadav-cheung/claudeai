"""
Chapter 6: Tool Registry.

Protocol-level implementation of Anthropic's Tool Use feature, managing
tool definitions, deferred loading strategies, allowed caller configuration,
and providing unified API format conversion for the Messages API.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional


@dataclass
class ToolDefinition:
    """Complete definition of a single tool.

    Mirrors the Anthropic Messages API tool object, with additional
    metadata for deferred loading, programmatic calling, and examples.
    """

    name: str
    description: str
    input_schema: Dict[str, Any]
    handler: Callable[..., Any]
    defer_loading: bool = False
    allowed_callers: Optional[List[str]] = None
    input_examples: Optional[List[Dict[str, Any]]] = None
    strict: bool = False

    def to_api_format(self) -> dict:
        """Convert to Anthropic API-compatible tool dictionary."""
        tool: Dict[str, Any] = {
            "name": self.name,
            "description": self.description,
            "input_schema": self.input_schema,
        }
        if self.defer_loading:
            tool["defer_loading"] = True
        if self.allowed_callers:
            tool["allowed_callers"] = self.allowed_callers
        if self.input_examples:
            tool["input_examples"] = self.input_examples
        if self.strict:
            tool["strict"] = True
        return tool


class ToolRegistry:
    """Registry for managing tool definitions, execution, and API formatting.

    Acts as the central authority for all tools available to Claude.
    Supports standard tool use, strict tool use, deferred loading
    (for Tool Search Tool), and programmatic tool calling.

    Usage::

        registry = ToolRegistry()
        registry.register(
            name="get_weather",
            description="Get current weather for a location",
            input_schema={
                "type": "object",
                "properties": {
                    "location": {"type": "string", "description": "City name"}
                },
                "required": ["location"],
            },
            handler=lambda location: f"Weather for {location}: 72F",
            defer_loading=False,
        )

        # Generate API-compatible tools list
        tools = registry.to_api_format()

        # Execute a tool
        result = registry.execute("get_weather", {"location": "SF"})
    """

    def __init__(self) -> None:
        self._tools: Dict[str, ToolDefinition] = {}
        self._search_tool_enabled: bool = False
        self._code_execution_enabled: bool = False

    # ------------------------------------------------------------------
    # Registration
    # ------------------------------------------------------------------

    def register(
        self,
        name: str,
        description: str,
        input_schema: Dict[str, Any],
        handler: Callable[..., Any],
        defer_loading: bool = False,
        allowed_callers: Optional[List[str]] = None,
        input_examples: Optional[List[Dict[str, Any]]] = None,
        strict: bool = False,
    ) -> None:
        """Register a tool.

        Args:
            name: Unique tool name. Use ``domain_action`` pattern.
            description: Detailed description including when to use and return format.
            input_schema: JSON Schema ``{"type": "object", "properties": {...}}``.
            handler: Function that receives ``**kwargs`` and returns the result.
            defer_loading: If True, tool is discoverable via Tool Search only.
            allowed_callers: ``["direct"]`` and/or ``["code_execution_20260120"]``.
            input_examples: Array of example input objects for Tool Use Examples.
            strict: If True, enables grammar-constrained sampling.

        Raises:
            ValueError: If tool name is already registered, handler is not callable,
                        or input_schema lacks proper structure.
        """
        if name in self._tools:
            raise ValueError(f"Tool '{name}' is already registered")
        if not callable(handler):
            raise ValueError(
                f"Handler for tool '{name}' must be callable"
            )
        if not isinstance(input_schema, dict) or input_schema.get("type") != "object":
            raise ValueError(
                "input_schema must be a JSON Schema object with type='object'"
            )

        self._tools[name] = ToolDefinition(
            name=name,
            description=description,
            input_schema=input_schema,
            handler=handler,
            defer_loading=defer_loading,
            allowed_callers=allowed_callers,
            input_examples=input_examples,
            strict=strict,
        )

    def unregister(self, name: str) -> None:
        """Remove a previously registered tool (no-op if not found)."""
        self._tools.pop(name, None)

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    def get(self, name: str) -> Optional[ToolDefinition]:
        """Retrieve a tool definition by name, or None."""
        return self._tools.get(name)

    def list_names(self) -> List[str]:
        """Return all registered tool names in insertion order."""
        return list(self._tools.keys())

    def get_deferred_tools(self) -> List[ToolDefinition]:
        """Return tools marked with ``defer_loading: True``."""
        return [t for t in self._tools.values() if t.defer_loading]

    def get_immediate_tools(self) -> List[ToolDefinition]:
        """Return tools that are NOT deferred (loaded into context immediately)."""
        return [t for t in self._tools.values() if not t.defer_loading]

    def get_programmatic_tools(self) -> List[ToolDefinition]:
        """Return tools callable from the code execution environment."""
        return [
            t
            for t in self._tools.values()
            if t.allowed_callers and "code_execution_20260120" in t.allowed_callers
        ]

    def get_strict_tools(self) -> List[ToolDefinition]:
        """Return tools with strict mode enabled."""
        return [t for t in self._tools.values() if t.strict]

    def count(self) -> int:
        """Total number of registered tools."""
        return len(self._tools)

    # ------------------------------------------------------------------
    # API format
    # ------------------------------------------------------------------

    def to_api_format(self) -> List[Dict[str, Any]]:
        """Generate the tools array for the Anthropic Messages API.

        Returns all tools (including deferred ones) because the API
        needs their full definitions to expand ``tool_reference`` blocks.
        """
        return [tool.to_api_format() for tool in self._tools.values()]

    def to_search_index_format(self) -> List[Dict[str, Any]]:
        """Generate tool metadata suitable for building a search index.

        Only includes deferred tools, as non-deferred tools are already
        in the context window.
        """
        result: List[Dict[str, Any]] = []
        for tool in self._tools.values():
            if tool.defer_loading:
                result.append(
                    {
                        "name": tool.name,
                        "description": tool.description,
                        "input_schema": tool.input_schema,
                    }
                )
        return result

    # ------------------------------------------------------------------
    # Execution
    # ------------------------------------------------------------------

    def execute(self, tool_name: str, input_data: Dict[str, Any]) -> Dict[str, Any]:
        """Execute a tool's handler function.

        Args:
            tool_name: Registered tool name.
            input_data: Keyword arguments to pass to the handler.

        Returns:
            ``{"success": True, "result": ...}`` or
            ``{"success": False, "error": "..."}``.

        Raises:
            KeyError: If tool_name is not registered.
        """
        tool = self._tools.get(tool_name)
        if tool is None:
            raise KeyError(f"Tool '{tool_name}' not found in registry")
        try:
            result = tool.handler(**input_data)
            return {"success": True, "result": result}
        except Exception as exc:
            return {"success": False, "error": str(exc)}

    def execute_many(
        self, calls: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Execute multiple tool calls (for parallel tool use support).

        Args:
            calls: List of ``{"tool_name": "...", "input": {...}}``.

        Returns:
            Results in the same order as the input calls.
        """
        return [self.execute(c["tool_name"], c["input"]) for c in calls]

    # ------------------------------------------------------------------
    # Feature toggles
    # ------------------------------------------------------------------

    def enable_tool_search(self) -> None:
        """Mark that Tool Search Tool is enabled."""
        self._search_tool_enabled = True

    def enable_code_execution(self) -> None:
        """Mark that Code Execution Tool is enabled."""
        self._code_execution_enabled = True

    @property
    def is_search_enabled(self) -> bool:
        return self._search_tool_enabled

    @property
    def is_code_execution_enabled(self) -> bool:
        return self._code_execution_enabled
