from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from harness_forge.safety.workspace import WorkspaceGuard, WorkspaceSecurityError

from .diff import WorkspaceChangeTracker
from .registry import ToolResult, ToolSpec


_MAX_PATCH_CHARS = 500_000
_MAX_PATCH_FILES = 100
_HUNK_HEADER = re.compile(
    r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@"
)


class PatchError(ValueError):
    """Raised when a unified diff is malformed or does not match the workspace."""


@dataclass(frozen=True)
class _Hunk:
    old_start: int
    old_count: int
    new_start: int
    new_count: int
    lines: tuple[str, ...]


@dataclass(frozen=True)
class _FilePatch:
    old_path: str | None
    new_path: str | None
    hunks: tuple[_Hunk, ...]


@dataclass(frozen=True)
class _Operation:
    target: Path
    original: str | None
    updated: str | None
    status: str


def build_patch_tool(
    guard: WorkspaceGuard, tracker: WorkspaceChangeTracker
) -> ToolSpec:
    return ToolSpec(
        name="apply_patch",
        description=(
            "Apply a bounded unified diff atomically to UTF-8 files inside the workspace."
        ),
        handler=lambda args: _apply_patch(guard, tracker, args),
        parameters={"patch": str},
        required=frozenset({"patch"}),
    )


def _apply_patch(
    guard: WorkspaceGuard,
    tracker: WorkspaceChangeTracker,
    args: dict[str, Any],
) -> ToolResult:
    patch_text = args["patch"]
    if not patch_text.strip():
        return ToolResult.fail("patch must be non-empty", "INVALID_ARGUMENT")
    if len(patch_text) > _MAX_PATCH_CHARS:
        return ToolResult.fail(
            f"patch exceeds {_MAX_PATCH_CHARS} characters", "PATCH_TOO_LARGE"
        )
    try:
        file_patches = _parse_unified_diff(patch_text)
        if len(file_patches) > _MAX_PATCH_FILES:
            raise PatchError(f"patch contains more than {_MAX_PATCH_FILES} files")
        operations = [_plan_operation(guard, item) for item in file_patches]
    except WorkspaceSecurityError as exc:
        return ToolResult.fail(str(exc), "PATH_BLOCKED")
    except PatchError as exc:
        return ToolResult.fail(str(exc), "PATCH_INVALID")

    completed: list[_Operation] = []
    try:
        for operation in operations:
            tracker.capture(operation.target)
            completed.append(operation)
            if operation.updated is None:
                operation.target.unlink()
            else:
                operation.target.parent.mkdir(parents=True, exist_ok=True)
                operation.target.write_text(operation.updated, encoding="utf-8")
    except (OSError, WorkspaceSecurityError) as exc:
        _rollback(completed)
        return ToolResult.fail(f"failed to apply patch: {exc}", "FILESYSTEM_ERROR")

    return ToolResult.ok(
        applied=True,
        applied_files=[guard.relative_label(item.target) for item in operations],
        file_count=len(operations),
        created=[
            guard.relative_label(item.target)
            for item in operations
            if item.status == "created"
        ],
        modified=[
            guard.relative_label(item.target)
            for item in operations
            if item.status == "modified"
        ],
        deleted=[
            guard.relative_label(item.target)
            for item in operations
            if item.status == "deleted"
        ],
    )


def _parse_unified_diff(text: str) -> list[_FilePatch]:
    lines = text.splitlines(keepends=True)
    patches: list[_FilePatch] = []
    index = 0
    while index < len(lines):
        if not lines[index].startswith("--- "):
            index += 1
            continue
        old_path = _header_path(lines[index][4:])
        index += 1
        if index >= len(lines) or not lines[index].startswith("+++ "):
            raise PatchError("missing +++ file header")
        new_path = _header_path(lines[index][4:])
        index += 1
        hunks: list[_Hunk] = []
        while index < len(lines) and not lines[index].startswith("--- "):
            if not lines[index].startswith("@@ "):
                index += 1
                continue
            match = _HUNK_HEADER.match(lines[index])
            if match is None:
                raise PatchError(f"invalid hunk header: {lines[index].rstrip()}")
            old_start = int(match.group(1))
            old_count = int(match.group(2) or "1")
            new_start = int(match.group(3))
            new_count = int(match.group(4) or "1")
            index += 1
            hunk_lines: list[str] = []
            seen_old = 0
            seen_new = 0
            while index < len(lines):
                line = lines[index]
                if seen_old == old_count and seen_new == new_count:
                    break
                if line.startswith("\\ No newline at end of file"):
                    if hunk_lines:
                        hunk_lines[-1] = hunk_lines[-1].rstrip("\r\n")
                    index += 1
                    continue
                if not line or line[0] not in {" ", "+", "-"}:
                    raise PatchError(f"invalid hunk line: {line.rstrip()}")
                hunk_lines.append(line)
                if line[0] in {" ", "-"}:
                    seen_old += 1
                if line[0] in {" ", "+"}:
                    seen_new += 1
                if seen_old > old_count or seen_new > new_count:
                    raise PatchError("hunk contains more lines than its header declares")
                index += 1
            _validate_hunk_counts(hunk_lines, old_count, new_count)
            hunks.append(
                _Hunk(
                    old_start=old_start,
                    old_count=old_count,
                    new_start=new_start,
                    new_count=new_count,
                    lines=tuple(hunk_lines),
                )
            )
        if not hunks:
            raise PatchError("file patch does not contain a hunk")
        if old_path is None and new_path is None:
            raise PatchError("both file paths cannot be /dev/null")
        patches.append(_FilePatch(old_path, new_path, tuple(hunks)))
    if not patches:
        raise PatchError("no unified diff file headers were found")
    return patches


def _header_path(value: str) -> str | None:
    raw = value.rstrip("\r\n").split("\t", 1)[0]
    if raw == "/dev/null":
        return None
    if raw.startswith(("a/", "b/")):
        raw = raw[2:]
    if not raw:
        raise PatchError("patch file path must be non-empty")
    return raw


def _validate_hunk_counts(lines: list[str], old_count: int, new_count: int) -> None:
    actual_old = sum(1 for line in lines if line[0] in {" ", "-"})
    actual_new = sum(1 for line in lines if line[0] in {" ", "+"})
    if actual_old != old_count or actual_new != new_count:
        raise PatchError(
            "hunk line counts do not match header: "
            f"old {actual_old}/{old_count}, new {actual_new}/{new_count}"
        )


def _plan_operation(guard: WorkspaceGuard, patch: _FilePatch) -> _Operation:
    label = patch.new_path or patch.old_path
    if label is None:
        raise PatchError("patch file path is missing")
    target = guard.resolve_path(label, must_exist=False)
    if patch.old_path and patch.new_path and patch.old_path != patch.new_path:
        raise PatchError("file renames are not supported")

    if patch.old_path is None:
        if target.exists():
            raise PatchError(f"new file already exists: {label}")
        original: str | None = None
        original_lines: list[str] = []
        status = "created"
    else:
        old_target = guard.resolve_path(patch.old_path, must_exist=True, expected_type="file")
        if old_target != target:
            raise PatchError("file renames are not supported")
        try:
            original = target.read_text(encoding="utf-8")
        except (OSError, UnicodeError) as exc:
            raise PatchError(f"failed to read patch target {label}: {exc}") from exc
        original_lines = original.splitlines(keepends=True)
        status = "deleted" if patch.new_path is None else "modified"

    updated_lines = _apply_hunks(original_lines, patch.hunks, label)
    updated = None if patch.new_path is None else "".join(updated_lines)
    return _Operation(target=target, original=original, updated=updated, status=status)


def _apply_hunks(
    original: list[str], hunks: tuple[_Hunk, ...], label: str
) -> list[str]:
    output: list[str] = []
    cursor = 0
    for hunk in hunks:
        target_index = max(hunk.old_start - 1, 0)
        if target_index < cursor or target_index > len(original):
            raise PatchError(f"hunk position is invalid for {label}")
        output.extend(original[cursor:target_index])
        cursor = target_index
        for line in hunk.lines:
            prefix, content = line[0], line[1:]
            if prefix in {" ", "-"}:
                if cursor >= len(original) or original[cursor] != content:
                    raise PatchError(
                        f"patch context does not match {label} at line {cursor + 1}"
                    )
                if prefix == " ":
                    output.append(content)
                cursor += 1
            elif prefix == "+":
                output.append(content)
        expected_cursor = target_index + hunk.old_count
        if cursor != expected_cursor:
            raise PatchError(f"hunk did not consume expected lines for {label}")
    output.extend(original[cursor:])
    return output


def _rollback(operations: list[_Operation]) -> None:
    for operation in reversed(operations):
        try:
            if operation.original is None:
                if operation.target.exists():
                    operation.target.unlink()
            else:
                operation.target.parent.mkdir(parents=True, exist_ok=True)
                operation.target.write_text(operation.original, encoding="utf-8")
        except OSError:
            pass
