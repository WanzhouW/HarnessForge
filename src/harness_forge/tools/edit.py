from __future__ import annotations

import difflib
from typing import Any

from harness_forge.safety.workspace import WorkspaceGuard, WorkspaceSecurityError

from .diff import WorkspaceChangeTracker
from .registry import ToolResult, ToolSpec


_MAX_DIFF_CHARS = 20_000


def build_edit_tool(
    guard: WorkspaceGuard, tracker: WorkspaceChangeTracker | None = None
) -> ToolSpec:
    active_tracker = tracker or WorkspaceChangeTracker(guard)
    return ToolSpec(
        name="edit_file",
        description="Replace one exact, unique text occurrence in an existing workspace file.",
        handler=lambda args: _edit_file(guard, active_tracker, args),
        parameters={"path": str, "old_text": str, "new_text": str},
        required=frozenset({"path", "old_text", "new_text"}),
    )


def _edit_file(
    guard: WorkspaceGuard,
    tracker: WorkspaceChangeTracker,
    args: dict[str, Any],
) -> ToolResult:
    raw_path = args["path"]
    old_text = args["old_text"]
    new_text = args["new_text"]
    if not old_text:
        return ToolResult.fail("old_text must be non-empty", "INVALID_ARGUMENT")

    try:
        target = guard.resolve_path(raw_path, must_exist=True, expected_type="file")
    except WorkspaceSecurityError as exc:
        return ToolResult.fail(str(exc), "PATH_BLOCKED")

    try:
        original = target.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        return ToolResult.fail(f"failed to read editable text: {exc}", "FILESYSTEM_ERROR")

    occurrences = original.count(old_text)
    if occurrences == 0:
        return ToolResult.fail("old_text was not found", "EDIT_MISMATCH")
    if occurrences > 1:
        return ToolResult.fail(
            f"old_text matched {occurrences} locations; replacement must be unique",
            "EDIT_AMBIGUOUS",
            match_count=occurrences,
        )

    updated = original.replace(old_text, new_text, 1)
    if updated == original:
        return ToolResult.ok(
            path=guard.relative_label(target),
            changed=False,
            diff="",
        )

    try:
        tracker.capture(target)
        target.write_text(updated, encoding="utf-8")
    except (OSError, WorkspaceSecurityError) as exc:
        return ToolResult.fail(f"failed to write file: {exc}", "FILESYSTEM_ERROR")

    diff = "".join(
        difflib.unified_diff(
            original.splitlines(keepends=True),
            updated.splitlines(keepends=True),
            fromfile=f"a/{guard.relative_label(target)}",
            tofile=f"b/{guard.relative_label(target)}",
        )
    )
    return ToolResult.ok(
        path=guard.relative_label(target),
        changed=True,
        diff=diff[:_MAX_DIFF_CHARS],
        diff_truncated=len(diff) > _MAX_DIFF_CHARS,
    )
