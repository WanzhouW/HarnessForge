from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol

from harness_forge.harness.result_schema import ToolCallRecord


@dataclass(frozen=True)
class AgentAction:
    action_type: str
    tool_name: str | None = None
    arguments: dict[str, Any] = field(default_factory=dict)
    content: str = ""

    @classmethod
    def tool(cls, name: str, arguments: dict[str, Any] | None = None) -> "AgentAction":
        return cls(action_type="tool", tool_name=name, arguments=dict(arguments or {}))

    @classmethod
    def final(cls, answer: str) -> "AgentAction":
        return cls(action_type="final", content=answer)


@dataclass(frozen=True)
class ModelRequest:
    task_instruction: str
    rendered_prompt: str
    workspace_root: str
    enabled_tools: tuple[str, ...]
    step_id: int
    observations: tuple[ToolCallRecord, ...]


class ModelBackend(Protocol):
    def next_action(self, request: ModelRequest) -> AgentAction:
        """Return one tool call or a final answer."""


class ScriptedModel:
    """Deterministic backend for smoke tests and loop development."""

    model_name = "scripted"

    def __init__(self, actions: list[AgentAction]) -> None:
        self._actions = list(actions)
        self.requests: list[ModelRequest] = []

    def next_action(self, request: ModelRequest) -> AgentAction:
        self.requests.append(request)
        if not self._actions:
            return AgentAction.final("")
        return self._actions.pop(0)


@dataclass
class AgentRunState:
    step_count: int = 0
    model_call_count: int = 0
    tool_call_count: int = 0
    observations: list[ToolCallRecord] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
