from __future__ import annotations

import itertools
import json
import os
import shlex
import subprocess
import time
from pathlib import Path
from typing import Any

from harness_forge.safety.command_policy import CommandPolicy, CommandPolicyError
from harness_forge.safety.workspace import WorkspaceGuard, WorkspaceSecurityError

from .registry import ToolResult, ToolSpec


_DEFAULT_TIMEOUT_SECONDS = 20
_MAX_TIMEOUT_SECONDS = 120
_DEFAULT_MAX_OUTPUT_CHARS = 12_000
_HARD_MAX_OUTPUT_CHARS = 100_000


def build_terminal_tool(
    guard: WorkspaceGuard,
    policy: CommandPolicy | None = None,
    artifact_dir: str | Path | None = None,
) -> ToolSpec:
    active_policy = policy or CommandPolicy()
    active_artifact_dir = (
        Path(artifact_dir).expanduser().resolve() if artifact_dir is not None else None
    )
    command_ids = itertools.count(1)
    return ToolSpec(
        name="run_command",
        description=(
            "Run one command without a shell under the narrow baseline host policy. "
            "This policy is not sufficient for Terminal-Bench."
        ),
        handler=lambda args: _run_command(
            guard,
            active_policy,
            active_artifact_dir,
            next(command_ids),
            args,
        ),
        parameters={
            "command": (str, list, tuple),
            "cwd": str,
            "timeout": int,
            "max_output_chars": int,
            "save_artifact": bool,
        },
        required=frozenset({"command"}),
    )


def _run_command(
    guard: WorkspaceGuard,
    policy: CommandPolicy,
    artifact_dir: Path | None,
    command_id: int,
    args: dict[str, Any],
) -> ToolResult:
    try:
        argv = _parse_command(args["command"])
        argv = list(policy.validate(argv))
    except (ValueError, CommandPolicyError) as exc:
        return ToolResult.fail(str(exc), "COMMAND_BLOCKED", command=[])

    raw_cwd = args.get("cwd", ".")
    timeout = args.get("timeout", _DEFAULT_TIMEOUT_SECONDS)
    max_output_chars = args.get("max_output_chars", _DEFAULT_MAX_OUTPUT_CHARS)
    save_artifact = args.get("save_artifact", False)
    if timeout < 1:
        return ToolResult.fail("timeout must be at least 1 second", "INVALID_ARGUMENT")
    timeout = min(timeout, _MAX_TIMEOUT_SECONDS)
    if max_output_chars < 1:
        return ToolResult.fail(
            "max_output_chars must be at least 1", "INVALID_ARGUMENT"
        )
    output_limit = min(max_output_chars, _HARD_MAX_OUTPUT_CHARS)

    try:
        cwd = guard.resolve_path(raw_cwd, must_exist=True, expected_type="dir")
    except WorkspaceSecurityError as exc:
        return ToolResult.fail(str(exc), "PATH_BLOCKED", command=argv)

    started = time.perf_counter()
    try:
        completed = subprocess.run(
            argv,
            cwd=str(cwd),
            shell=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        duration = round(time.perf_counter() - started, 6)
        payload = _command_payload(
            artifact_dir=artifact_dir,
            command_id=command_id,
            command=argv,
            cwd=guard.relative_label(cwd),
            stdout=_as_text(exc.stdout),
            stderr=_as_text(exc.stderr),
            returncode=None,
            timed_out=True,
            duration_seconds=duration,
            output_limit=output_limit,
            save_artifact=save_artifact,
        )
        return ToolResult.fail(
            f"command timed out after {timeout} seconds",
            "COMMAND_TIMEOUT",
            **payload,
        )
    except OSError as exc:
        duration = round(time.perf_counter() - started, 6)
        payload = _command_payload(
            artifact_dir=artifact_dir,
            command_id=command_id,
            command=argv,
            cwd=guard.relative_label(cwd),
            stdout="",
            stderr=str(exc),
            returncode=None,
            timed_out=False,
            duration_seconds=duration,
            output_limit=output_limit,
            save_artifact=save_artifact,
        )
        return ToolResult.fail(
            f"command could not start: {exc}",
            "COMMAND_EXECUTION_ERROR",
            **payload,
        )

    payload = _command_payload(
        artifact_dir=artifact_dir,
        command_id=command_id,
        command=argv,
        cwd=guard.relative_label(cwd),
        stdout=completed.stdout,
        stderr=completed.stderr,
        returncode=completed.returncode,
        timed_out=False,
        duration_seconds=round(time.perf_counter() - started, 6),
        output_limit=output_limit,
        save_artifact=save_artifact,
    )
    if completed.returncode == 0:
        return ToolResult.ok(**payload)
    return ToolResult.fail(
        f"command exited with return code {completed.returncode}",
        "COMMAND_FAILED",
        **payload,
    )


def _parse_command(command: str | list[str] | tuple[str, ...]) -> list[str]:
    if isinstance(command, str):
        if not command.strip():
            raise ValueError("command must be non-empty")
        return shlex.split(command, posix=os.name != "nt")
    argv = [str(item) for item in command]
    if not argv or any(not item.strip() for item in argv):
        raise ValueError("command argv must contain non-empty values")
    return argv


def _as_text(value: str | bytes | None) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    return value.decode("utf-8", errors="replace")


def _command_payload(
    *,
    artifact_dir: Path | None,
    command_id: int,
    command: list[str],
    cwd: str,
    stdout: str,
    stderr: str,
    returncode: int | None,
    timed_out: bool,
    duration_seconds: float,
    output_limit: int,
    save_artifact: bool,
) -> dict[str, Any]:
    stdout_truncated = len(stdout) > output_limit
    stderr_truncated = len(stderr) > output_limit
    artifact_path: str | None = None
    artifact_error: str | None = None
    if save_artifact or stdout_truncated or stderr_truncated:
        if artifact_dir is None:
            artifact_error = "artifact directory is not configured"
        else:
            try:
                artifact_dir.mkdir(parents=True, exist_ok=True)
                target = artifact_dir / f"command-{command_id:06d}.json"
                target.write_text(
                    json.dumps(
                        {
                            "command": command,
                            "cwd": cwd,
                            "stdout": stdout,
                            "stderr": stderr,
                            "returncode": returncode,
                            "timed_out": timed_out,
                            "duration_seconds": duration_seconds,
                        },
                        ensure_ascii=False,
                        indent=2,
                        sort_keys=True,
                    )
                    + "\n",
                    encoding="utf-8",
                )
                artifact_path = str(target)
            except OSError as exc:
                artifact_error = str(exc)
    return {
        "command": command,
        "cwd": cwd,
        "stdout": stdout[:output_limit],
        "stderr": stderr[:output_limit],
        "stdout_total_chars": len(stdout),
        "stderr_total_chars": len(stderr),
        "stdout_truncated": stdout_truncated,
        "stderr_truncated": stderr_truncated,
        "max_output_chars": output_limit,
        "artifact_path": artifact_path,
        "artifact_error": artifact_error,
        "returncode": returncode,
        "timed_out": timed_out,
        "duration_seconds": duration_seconds,
    }
