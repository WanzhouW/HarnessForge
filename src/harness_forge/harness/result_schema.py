from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(frozen=True)
class ToolCallRecord:
    step_id: int
    tool_name: str
    arguments: dict[str, Any]
    success: bool
    result: dict[str, Any]
    error: str | None = None
    error_type: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class StepRecord:
    step_id: int
    action_type: str
    model_content: str = ""
    tool_call: ToolCallRecord | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class AgentRunResult:
    run_id: str
    task_id: str
    attempt_id: str
    instruction: str
    workspace_root: str
    model_config: dict[str, Any]
    prompt_version: str
    enabled_tools: list[str]
    max_steps: int
    max_tool_calls: int
    wall_time_limit: float
    max_model_calls: int
    stop_reason: str
    harness_success: bool
    benchmark_success: bool | None
    official_score: float | None
    model_name: str | None
    model_call_count: int
    tool_call_count: int
    input_tokens: int | None
    output_tokens: int | None
    total_tokens: int | None
    cost: float | None
    final_answer: str
    trajectory: list[StepRecord] = field(default_factory=list)
    tool_calls: list[ToolCallRecord] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    duration_seconds: float = 0.0
    trajectory_path: str | None = None
    artifact_path: str | None = None
    result_path: str | None = None
    adapter_data: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["trajectory"] = [step.to_dict() for step in self.trajectory]
        payload["tool_calls"] = [call.to_dict() for call in self.tool_calls]
        return payload
