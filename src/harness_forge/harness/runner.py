from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path
from uuid import uuid4

from harness_forge.agent.loop import run_agent
from harness_forge.safety.command_policy import CommandPolicy
from harness_forge.safety.workspace import WorkspaceGuard
from harness_forge.tools.edit import build_edit_tool
from harness_forge.tools.diff import WorkspaceChangeTracker, build_diff_tool
from harness_forge.tools.filesystem import build_filesystem_tools
from harness_forge.tools.patch import build_patch_tool
from harness_forge.tools.registry import ToolRegistry, ToolSpec
from harness_forge.tools.search import build_search_tool
from harness_forge.tools.terminal import build_terminal_tool

from .result_schema import AgentRunResult
from .task import RunConfig, TaskSpec


def build_task_registry(
    workspace_root: str | Path,
    enabled_tools: tuple[str, ...],
    *,
    command_policy: CommandPolicy | None = None,
    artifact_path: str | Path | None = None,
) -> ToolRegistry:
    guard = WorkspaceGuard(workspace_root)
    tracker = WorkspaceChangeTracker(guard)
    available: dict[str, ToolSpec] = {}
    for tool in build_filesystem_tools(guard, tracker):
        available[tool.name] = tool
    search_tool = build_search_tool(guard)
    edit_tool = build_edit_tool(guard, tracker)
    diff_tool = build_diff_tool(guard, tracker)
    patch_tool = build_patch_tool(guard, tracker)
    terminal_tool = build_terminal_tool(guard, command_policy, artifact_path)
    available[search_tool.name] = search_tool
    available[edit_tool.name] = edit_tool
    available[diff_tool.name] = diff_tool
    available[patch_tool.name] = patch_tool
    available[terminal_tool.name] = terminal_tool

    unknown = sorted(set(enabled_tools) - set(available))
    if unknown:
        raise ValueError("unknown enabled tools: " + ", ".join(unknown))

    registry = ToolRegistry()
    registry.register_many([available[name] for name in enabled_tools])
    return registry


class HarnessRunner:
    """Run one task with fresh task-scoped tools and no persistent state."""

    def __init__(self, command_policy: CommandPolicy | None = None) -> None:
        self.command_policy = command_policy

    def run(self, task: TaskSpec, config: RunConfig) -> AgentRunResult:
        run_id = config.run_id or uuid4().hex
        attempt_id = config.attempt_id or uuid4().hex
        output_root = Path(config.output_root).expanduser().resolve()
        run_dir = output_root / run_id
        trajectory_path = Path(config.trajectory_path) if config.trajectory_path else run_dir / "trajectory.jsonl"
        artifact_path = Path(config.artifact_path) if config.artifact_path else run_dir / "artifacts"
        result_path = Path(config.result_path) if config.result_path else run_dir / "result.json"
        trajectory_path = trajectory_path.expanduser().resolve()
        artifact_path = artifact_path.expanduser().resolve()
        result_path = result_path.expanduser().resolve()
        artifact_path.mkdir(parents=True, exist_ok=True)

        registry = build_task_registry(
            task.workspace_root,
            task.enabled_tools,
            command_policy=self.command_policy,
            artifact_path=artifact_path,
        )
        task_config = replace(
            config,
            task_id=task.task_id,
            run_id=run_id,
            attempt_id=attempt_id,
            enabled_tools=task.enabled_tools,
            trajectory_path=trajectory_path,
            artifact_path=artifact_path,
            result_path=result_path,
        )
        result = run_agent(
            task.instruction,
            task.workspace_root,
            registry,
            task_config,
        )
        result.adapter_data = dict(task.metadata)
        result_path.parent.mkdir(parents=True, exist_ok=True)
        result_path.write_text(
            json.dumps(result.to_dict(), ensure_ascii=False, indent=2, sort_keys=True)
            + "\n",
            encoding="utf-8",
        )
        return result
