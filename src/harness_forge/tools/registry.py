from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Mapping


JsonObject = dict[str, Any]
ToolHandler = Callable[[JsonObject], "ToolResult"]


@dataclass(frozen=True)
class ToolResult:
    success: bool
    output: JsonObject = field(default_factory=dict)
    error: str | None = None
    error_type: str | None = None

    @classmethod
    def ok(cls, **output: Any) -> "ToolResult":
        return cls(success=True, output=dict(output))

    @classmethod
    def fail(cls, error: str, error_type: str = "TOOL_ERROR", **output: Any) -> "ToolResult":
        return cls(
            success=False,
            output=dict(output),
            error=error,
            error_type=error_type,
        )

    def to_dict(self) -> JsonObject:
        return {
            "success": self.success,
            "output": self.output,
            "error": self.error,
            "error_type": self.error_type,
        }


@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str
    handler: ToolHandler
    parameters: Mapping[str, type | tuple[type, ...]] = field(default_factory=dict)
    required: frozenset[str] = frozenset()
    allow_extra: bool = False


class ToolRegistryError(ValueError):
    """Base error for registry configuration."""


class DuplicateToolError(ToolRegistryError):
    """Raised when a tool name is registered twice."""


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, ToolSpec] = {}

    def register(self, tool: ToolSpec) -> None:
        if not tool.name or not tool.name.strip():
            raise ToolRegistryError("tool name must be non-empty")
        if tool.name in self._tools:
            raise DuplicateToolError(f"tool already registered: {tool.name}")
        self._tools[tool.name] = tool

    def register_many(self, tools: list[ToolSpec]) -> None:
        for tool in tools:
            self.register(tool)

    def names(self) -> tuple[str, ...]:
        return tuple(self._tools)

    def get(self, name: str) -> ToolSpec | None:
        return self._tools.get(name)

    def invoke(self, name: str, arguments: Mapping[str, Any] | None = None) -> ToolResult:
        tool = self.get(name)
        if tool is None:
            return ToolResult.fail(
                f"unknown tool: {name}",
                error_type="TOOL_NOT_FOUND",
            )

        args = dict(arguments or {})
        validation_error = self._validate(tool, args)
        if validation_error:
            return ToolResult.fail(
                validation_error,
                error_type="TOOL_VALIDATION_ERROR",
            )

        try:
            result = tool.handler(args)
        except Exception as exc:  # defensive tool boundary
            return ToolResult.fail(
                f"tool execution failed: {type(exc).__name__}: {exc}",
                error_type="TOOL_EXECUTION_ERROR",
            )
        if not isinstance(result, ToolResult):
            return ToolResult.fail(
                f"tool returned unsupported result type: {type(result).__name__}",
                error_type="TOOL_PROTOCOL_ERROR",
            )
        return result

    @staticmethod
    def _validate(tool: ToolSpec, args: JsonObject) -> str | None:
        missing = sorted(name for name in tool.required if name not in args)
        if missing:
            return "missing required arguments: " + ", ".join(missing)

        if not tool.allow_extra:
            extra = sorted(name for name in args if name not in tool.parameters)
            if extra:
                return "unexpected arguments: " + ", ".join(extra)

        for name, value in args.items():
            expected = tool.parameters.get(name)
            if expected is None or value is None:
                continue
            if not isinstance(value, expected):
                if isinstance(expected, tuple):
                    label = " or ".join(item.__name__ for item in expected)
                else:
                    label = expected.__name__
                return f"argument '{name}' must be {label}"
        return None

