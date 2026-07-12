from __future__ import annotations

from pathlib import Path
from typing import Any

from harness_forge.safety.workspace import WorkspaceGuard, WorkspaceSecurityError

from .diff import WorkspaceChangeTracker
from .registry import ToolResult, ToolSpec


_DEFAULT_MAX_READ_CHARS = 12_000
_HARD_MAX_READ_CHARS = 100_000
_DEFAULT_MAX_ENTRIES = 500
_HARD_MAX_ENTRIES = 2_000
_DEFAULT_LINE_COUNT = 200
_HARD_LINE_COUNT = 5_000


def build_filesystem_tools(
    guard: WorkspaceGuard, tracker: WorkspaceChangeTracker | None = None
) -> list[ToolSpec]:
    active_tracker = tracker or WorkspaceChangeTracker(guard)
    return [
        ToolSpec(
            name="list_dir",
            description="List direct children of a directory inside the task workspace.",
            handler=lambda args: _list_dir(guard, args),
            parameters={"path": str, "max_entries": int},
        ),
        ToolSpec(
            name="read_file",
            description=(
                "Read a bounded line range from a UTF-8 file inside the task workspace."
            ),
            handler=lambda args: _read_file(guard, args),
            parameters={
                "path": str,
                "start_line": int,
                "line_count": int,
                "max_chars": int,
            },
            required=frozenset({"path"}),
        ),
        ToolSpec(
            name="write_file",
            description="Create or overwrite one UTF-8 text file in the workspace.",
            handler=lambda args: _write_file(guard, active_tracker, args),
            parameters={
                "path": str,
                "content": str,
                "overwrite": bool,
                "create_parents": bool,
            },
            required=frozenset({"path", "content"}),
        ),
    ]


def _list_dir(guard: WorkspaceGuard, args: dict[str, Any]) -> ToolResult:
    raw_path = args.get("path", ".")
    max_entries = args.get("max_entries", _DEFAULT_MAX_ENTRIES)
    if max_entries < 1:
        return ToolResult.fail("max_entries must be at least 1", "INVALID_ARGUMENT")
    limit = min(max_entries, _HARD_MAX_ENTRIES)

    try:
        directory = guard.resolve_path(raw_path, must_exist=True, expected_type="dir")
    except WorkspaceSecurityError as exc:
        return ToolResult.fail(str(exc), "PATH_BLOCKED")

    entries: list[dict[str, Any]] = []
    try:
        children = sorted(directory.iterdir(), key=lambda item: (not item.is_dir(), item.name.lower()))
        for child in children:
            if len(entries) >= limit:
                break
            if guard.is_sensitive_path(child):
                continue
            entries.append(
                {
                    "name": child.name,
                    "path": guard.relative_label(child),
                    "type": "directory" if child.is_dir() else "file",
                    "size": child.stat().st_size if child.is_file() else None,
                }
            )
    except OSError as exc:
        return ToolResult.fail(f"failed to list directory: {exc}", "FILESYSTEM_ERROR")

    visible_count = sum(1 for child in children if not guard.is_sensitive_path(child))
    return ToolResult.ok(
        path=guard.relative_label(directory),
        entries=entries,
        total_entries=visible_count,
        returned_entries=len(entries),
        remaining_entries=max(visible_count - len(entries), 0),
        truncated=visible_count > len(entries),
        max_entries=limit,
    )


def _read_file(guard: WorkspaceGuard, args: dict[str, Any]) -> ToolResult:
    raw_path = args["path"]
    start_line = args.get("start_line", 1)
    line_count = args.get("line_count", _DEFAULT_LINE_COUNT)
    max_chars = args.get("max_chars", _DEFAULT_MAX_READ_CHARS)
    if start_line < 1:
        return ToolResult.fail("start_line must be at least 1", "INVALID_ARGUMENT")
    if line_count < 1:
        return ToolResult.fail("line_count must be at least 1", "INVALID_ARGUMENT")
    if max_chars < 1:
        return ToolResult.fail("max_chars must be at least 1", "INVALID_ARGUMENT")
    char_limit = min(max_chars, _HARD_MAX_READ_CHARS)
    line_limit = min(line_count, _HARD_LINE_COUNT)

    try:
        target = guard.resolve_path(raw_path, must_exist=True, expected_type="file")
    except WorkspaceSecurityError as exc:
        return ToolResult.fail(str(exc), "PATH_BLOCKED")
    if _is_binary_file(target):
        return ToolResult.fail("binary files are not supported", "BINARY_FILE")

    try:
        content = target.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        return ToolResult.fail(f"failed to read file: {exc}", "FILESYSTEM_ERROR")

    lines = content.splitlines(keepends=True)
    total_lines = len(lines)
    if total_lines and start_line > total_lines:
        return ToolResult.fail(
            f"start_line exceeds total lines ({total_lines})", "INVALID_ARGUMENT"
        )
    selected = lines[start_line - 1 : start_line - 1 + line_limit]
    selected_text = "".join(selected)
    returned = selected_text[:char_limit]
    end_line = start_line + len(selected) - 1 if selected else 0
    truncated_by_chars = len(selected_text) > char_limit
    has_more = truncated_by_chars or end_line < total_lines
    return ToolResult.ok(
        path=guard.relative_label(target),
        content=returned,
        total_chars=len(content),
        total_lines=total_lines,
        start_line=start_line,
        end_line=end_line,
        requested_line_count=line_count,
        returned_line_count=len(selected),
        has_more=has_more,
        truncated=has_more,
        max_chars=char_limit,
    )


def _write_file(
    guard: WorkspaceGuard,
    tracker: WorkspaceChangeTracker,
    args: dict[str, Any],
) -> ToolResult:
    raw_path = args["path"]
    content = args["content"]
    overwrite = args.get("overwrite", False)
    create_parents = args.get("create_parents", False)
    try:
        target = guard.resolve_path(raw_path, must_exist=False)
        if target.exists() and not target.is_file():
            return ToolResult.fail("path is not a file", "INVALID_ARGUMENT")
        if target.exists() and not overwrite:
            return ToolResult.fail(
                "file already exists; set overwrite=true to replace it",
                "FILE_EXISTS",
            )
        if not target.parent.exists():
            if not create_parents:
                return ToolResult.fail(
                    "parent directory does not exist; set create_parents=true",
                    "PARENT_NOT_FOUND",
                )
            target.parent.mkdir(parents=True, exist_ok=True)
        tracker.capture(target)
    except WorkspaceSecurityError as exc:
        return ToolResult.fail(str(exc), "PATH_BLOCKED")
    existed = target.exists()
    try:
        target.write_text(content, encoding="utf-8")
    except OSError as exc:
        return ToolResult.fail(f"failed to write file: {exc}", "FILESYSTEM_ERROR")
    return ToolResult.ok(
        path=guard.relative_label(target),
        created=not existed,
        overwritten=existed,
        chars_written=len(content),
    )


def _is_binary_file(path: Path) -> bool:
    try:
        with path.open("rb") as handle:
            return b"\x00" in handle.read(4096)
    except OSError:
        return True
