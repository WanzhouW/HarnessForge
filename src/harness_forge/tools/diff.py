from __future__ import annotations

import difflib
from pathlib import Path
from typing import Any

from harness_forge.safety.workspace import WorkspaceGuard, WorkspaceSecurityError

from .registry import ToolResult, ToolSpec


_DEFAULT_MAX_DIFF_CHARS = 40_000
_HARD_MAX_DIFF_CHARS = 200_000


class WorkspaceChangeTracker:
    """Track originals for files mutated through one task-scoped registry."""

    def __init__(self, guard: WorkspaceGuard) -> None:
        self.guard = guard
        self._originals: dict[Path, str | None] = {}

    def capture(self, path: str | Path) -> Path:
        target = self.guard.resolve_path(path, must_exist=False)
        if target in self._originals:
            return target
        if target.exists():
            if not target.is_file():
                raise WorkspaceSecurityError(f"path is not a file: {path}")
            try:
                original = target.read_text(encoding="utf-8")
            except (OSError, UnicodeError) as exc:
                raise WorkspaceSecurityError(
                    f"failed to snapshot editable text: {exc}"
                ) from exc
            self._originals[target] = original
        else:
            self._originals[target] = None
        return target

    def unified_diff(self) -> tuple[str, list[str]]:
        chunks: list[str] = []
        changed_files: list[str] = []
        for target, original in sorted(
            self._originals.items(), key=lambda item: self.guard.relative_label(item[0])
        ):
            if target.exists():
                if not target.is_file():
                    continue
                try:
                    current: str | None = target.read_text(encoding="utf-8")
                except (OSError, UnicodeError):
                    continue
            else:
                current = None
            if original == current:
                continue
            label = self.guard.relative_label(target)
            changed_files.append(label)
            chunks.append(
                "".join(
                    difflib.unified_diff(
                        (original or "").splitlines(keepends=True),
                        (current or "").splitlines(keepends=True),
                        fromfile="/dev/null" if original is None else f"a/{label}",
                        tofile="/dev/null" if current is None else f"b/{label}",
                    )
                )
            )
        return "".join(chunks), changed_files


def build_diff_tool(
    guard: WorkspaceGuard, tracker: WorkspaceChangeTracker
) -> ToolSpec:
    return ToolSpec(
        name="get_diff",
        description=(
            "Return a unified diff for files changed through this task's "
            "HarnessForge mutation tools."
        ),
        handler=lambda args: _get_diff(tracker, args),
        parameters={"max_chars": int},
    )


def _get_diff(
    tracker: WorkspaceChangeTracker, args: dict[str, Any]
) -> ToolResult:
    max_chars = args.get("max_chars", _DEFAULT_MAX_DIFF_CHARS)
    if max_chars < 1:
        return ToolResult.fail("max_chars must be at least 1", "INVALID_ARGUMENT")
    limit = min(max_chars, _HARD_MAX_DIFF_CHARS)
    diff, changed_files = tracker.unified_diff()
    return ToolResult.ok(
        diff=diff[:limit],
        changed_files=changed_files,
        changed_file_count=len(changed_files),
        total_chars=len(diff),
        max_chars=limit,
        truncated=len(diff) > limit,
    )
