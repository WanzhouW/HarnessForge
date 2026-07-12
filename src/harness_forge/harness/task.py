from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .budgets import BudgetConfig


@dataclass(frozen=True)
class TaskSpec:
    task_id: str
    instruction: str
    workspace_root: str | Path
    enabled_tools: tuple[str, ...] = (
        "list_dir",
        "read_file",
        "search_text",
        "edit_file",
        "write_file",
        "get_diff",
        "apply_patch",
    )
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.task_id.strip():
            raise ValueError("task_id must be non-empty")
        if not self.instruction.strip():
            raise ValueError("instruction must be non-empty")
        if not self.enabled_tools:
            raise ValueError("enabled_tools must not be empty")


@dataclass(frozen=True)
class RunConfig:
    model: object
    budget: BudgetConfig = field(default_factory=BudgetConfig)
    system_prompt: str = ""
    prompt_version: str = "baseline-v1"
    task_id: str = "adhoc"
    run_id: str | None = None
    attempt_id: str | None = None
    enabled_tools: tuple[str, ...] = ()
    output_root: str | Path = Path("runs")
    trajectory_path: str | Path | None = None
    artifact_path: str | Path | None = None
    result_path: str | Path | None = None
