from __future__ import annotations

import fnmatch
import os
import re
from pathlib import Path
from typing import Any, Iterator

from harness_forge.safety.workspace import WorkspaceGuard, WorkspaceSecurityError

from .registry import ToolResult, ToolSpec


_IGNORED_DIRS = frozenset(
    {".git", "__pycache__", ".venv", "venv", "node_modules", ".pytest_cache"}
)
_MAX_RESULTS = 200
_MAX_FILE_BYTES = 1024 * 1024


def build_search_tool(guard: WorkspaceGuard) -> ToolSpec:
    return ToolSpec(
        name="search_text",
        description=(
            "Search workspace text with literal or regex matching and a path glob."
        ),
        handler=lambda args: _search_text(guard, args),
        parameters={
            "query": str,
            "path": str,
            "max_results": int,
            "case_sensitive": bool,
            "regex": bool,
            "glob": str,
        },
        required=frozenset({"query"}),
    )


def _search_text(guard: WorkspaceGuard, args: dict[str, Any]) -> ToolResult:
    query = args["query"]
    raw_path = args.get("path", ".")
    max_results = args.get("max_results", 20)
    case_sensitive = args.get("case_sensitive", False)
    use_regex = args.get("regex", False)
    glob_pattern = args.get("glob", "*")
    if not query:
        return ToolResult.fail("query must be non-empty", "INVALID_ARGUMENT")
    if max_results < 1:
        return ToolResult.fail("max_results must be at least 1", "INVALID_ARGUMENT")
    if not glob_pattern:
        return ToolResult.fail("glob must be non-empty", "INVALID_ARGUMENT")
    limit = min(max_results, _MAX_RESULTS)

    compiled: re.Pattern[str] | None = None
    if use_regex:
        try:
            compiled = re.compile(query, 0 if case_sensitive else re.IGNORECASE)
        except re.error as exc:
            return ToolResult.fail(f"invalid regex: {exc}", "INVALID_ARGUMENT")

    try:
        target = guard.resolve_path(raw_path, must_exist=True)
    except WorkspaceSecurityError as exc:
        return ToolResult.fail(str(exc), "PATH_BLOCKED")

    needle = query if case_sensitive else query.lower()
    matches: list[dict[str, Any]] = []
    scanned_files = 0

    for file_path in _iter_files(guard, target):
        if len(matches) >= limit:
            break
        relative_path = guard.relative_label(file_path)
        if not fnmatch.fnmatchcase(relative_path, glob_pattern):
            continue
        try:
            if file_path.stat().st_size > _MAX_FILE_BYTES or _is_binary_file(file_path):
                continue
            lines = file_path.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            continue
        scanned_files += 1
        for line_number, line in enumerate(lines, start=1):
            haystack = line if case_sensitive else line.lower()
            matched = compiled.search(line) is not None if compiled else needle in haystack
            if not matched:
                continue
            matches.append(
                {
                    "path": guard.relative_label(file_path),
                    "line": line_number,
                    "text": line[:300],
                }
            )
            if len(matches) >= limit:
                break

    return ToolResult.ok(
        query=query,
        path=guard.relative_label(target),
        glob=glob_pattern,
        regex=use_regex,
        case_sensitive=case_sensitive,
        matches=matches,
        match_count=len(matches),
        scanned_files=scanned_files,
        truncated=len(matches) >= limit,
    )


def _iter_files(guard: WorkspaceGuard, target: Path) -> Iterator[Path]:
    if target.is_file():
        if not guard.is_sensitive_path(target):
            yield target
        return

    for directory, dir_names, file_names in os.walk(target):
        directory_path = Path(directory)
        dir_names[:] = sorted(
            name
            for name in dir_names
            if name not in _IGNORED_DIRS
            and not guard.is_sensitive_path(directory_path / name)
        )
        for file_name in sorted(file_names):
            file_path = directory_path / file_name
            if not guard.is_sensitive_path(file_path):
                yield file_path


def _is_binary_file(path: Path) -> bool:
    try:
        with path.open("rb") as handle:
            return b"\x00" in handle.read(4096)
    except OSError:
        return True
