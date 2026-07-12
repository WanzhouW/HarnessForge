from __future__ import annotations

import argparse
import importlib.metadata
import json
import os
import sys
from pathlib import Path
from typing import Any, Callable, Sequence
from urllib.parse import urlparse


EXIT_OK = 0
EXIT_HARNESS_FAILURE = 1
EXIT_CONFIG_ERROR = 2
EXIT_PROVIDER_ERROR = 3


ProviderFactory = Callable[[Any], object]
RunnerFactory = Callable[[], object]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="harnessforge",
        description="Run the HarnessForge local benchmark-facing agent harness.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    doctor = subparsers.add_parser(
        "doctor", help="Check local runtime and provider configuration without a request."
    )
    doctor.add_argument("--model")
    doctor.add_argument("--base-url")
    doctor.add_argument(
        "--provider-api",
        choices=("responses", "chat_completions"),
        help="Provider protocol; overrides PROVIDER_API from the environment.",
    )
    doctor.add_argument("--dotenv-path", type=Path, default=Path.cwd() / ".env")

    run = subparsers.add_parser("run", help="Run one local task.")
    run.add_argument("--task-id", required=True)
    run.add_argument("--instruction", required=True)
    run.add_argument("--workspace", required=True, type=Path)
    run.add_argument(
        "--tools",
        default=(
            "list_dir,read_file,search_text,edit_file,write_file,get_diff,apply_patch"
        ),
        help="Comma-separated enabled tool names.",
    )
    run.add_argument("--model")
    run.add_argument("--base-url")
    run.add_argument(
        "--provider-api",
        choices=("responses", "chat_completions"),
        help="Provider protocol; overrides PROVIDER_API from the environment.",
    )
    run.add_argument("--temperature", type=float)
    run.add_argument("--max-tokens", type=_positive_int)
    run.add_argument("--api-timeout", type=_positive_float, default=60.0)
    run.add_argument("--max-retries", type=_non_negative_int, default=2)
    run.add_argument("--max-steps", type=_positive_int, default=20)
    run.add_argument("--max-model-calls", type=_positive_int, default=20)
    run.add_argument("--max-tool-calls", type=_non_negative_int, default=15)
    run.add_argument("--wall-time", type=_positive_float, default=300.0)
    run.add_argument("--max-input-tokens", type=_positive_int)
    run.add_argument("--max-output-tokens", type=_positive_int)
    run.add_argument("--max-cost", type=_positive_float)
    run.add_argument("--prompt-version", default="baseline-v1")
    run.add_argument("--output-root", type=Path, default=Path("runs"))
    run.add_argument("--trajectory-path", type=Path)
    run.add_argument("--artifact-path", type=Path)
    run.add_argument("--result-path", type=Path)
    run.add_argument("--dotenv-path", type=Path, default=Path.cwd() / ".env")
    return parser


def main(
    argv: Sequence[str] | None = None,
    *,
    provider_factory: ProviderFactory | None = None,
    runner_factory: RunnerFactory | None = None,
) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "doctor":
        return _doctor(args, provider_factory)
    if args.command == "run":
        return _run(args, provider_factory, runner_factory)
    return EXIT_CONFIG_ERROR


def _doctor(args: argparse.Namespace, provider_factory: ProviderFactory | None) -> int:
    checks: list[tuple[str, str, str]] = []
    python_ok = sys.version_info >= (3, 11)
    checks.append(
        (
            "OK" if python_ok else "FAIL",
            "Python",
            ".".join(str(item) for item in sys.version_info[:3]),
        )
    )

    dependencies_ok = True
    for distribution in ("openai", "python-dotenv"):
        try:
            version = importlib.metadata.version(distribution)
            checks.append(("OK", distribution, version))
        except importlib.metadata.PackageNotFoundError:
            dependencies_ok = False
            checks.append(("FAIL", distribution, "not installed"))

    dotenv_path = args.dotenv_path.expanduser().resolve()
    checks.append(
        ("OK" if dotenv_path.is_file() else "INFO", ".env", str(dotenv_path))
    )

    if not dependencies_ok:
        _print_checks(checks)
        return EXIT_CONFIG_ERROR

    try:
        from harness_forge.providers import (
            ProviderConfig,
            ProviderConfigurationError,
            create_provider,
        )

        config = ProviderConfig.from_env(
            dotenv_path=dotenv_path,
            model_name=args.model,
            provider_api=args.provider_api,
            base_url=args.base_url,
        )
        checks.append(("OK", "MODEL_NAME", config.model_name))
        checks.append(("OK", "PROVIDER_API", config.provider_api))
        checks.append(("OK", "OPENAI_BASE_URL", config.base_url))
        key_required = _api_key_required(config.base_url)
        key_ok = config.api_key is not None or not key_required
        checks.append(
            (
                "OK" if key_ok else "FAIL",
                "OPENAI_API_KEY",
                "configured" if config.api_key else "not configured",
            )
        )
        if not key_ok:
            checks.append(
                (
                    "FAIL",
                    "Provider",
                    "not initialized: remote endpoint requires API key",
                )
            )
            _print_checks(checks)
            return EXIT_CONFIG_ERROR
        factory = provider_factory or create_provider
        provider = factory(config)
        checks.append(
            (
                "OK",
                "Provider",
                f"{type(provider).__name__} initialized; no request sent",
            )
        )
    except ProviderConfigurationError as exc:
        checks.append(("FAIL", "Provider config", str(exc)))
        _print_checks(checks)
        return EXIT_CONFIG_ERROR
    except Exception as exc:
        checks.append(("FAIL", "Provider", f"{type(exc).__name__}: {exc}"))
        _print_checks(checks)
        return EXIT_PROVIDER_ERROR

    _print_checks(checks)
    return EXIT_OK if python_ok and key_ok else EXIT_CONFIG_ERROR


def _run(
    args: argparse.Namespace,
    provider_factory: ProviderFactory | None,
    runner_factory: RunnerFactory | None,
) -> int:
    try:
        from harness_forge.harness.budgets import BudgetConfig
        from harness_forge.harness.runner import HarnessRunner
        from harness_forge.harness.task import RunConfig, TaskSpec
        from harness_forge.providers import (
            ProviderConfig,
            ProviderConfigurationError,
            ProviderError,
            create_provider,
        )
    except ImportError as exc:
        print(f"configuration error: missing dependency: {exc}", file=sys.stderr)
        return EXIT_CONFIG_ERROR

    try:
        workspace = args.workspace.expanduser().resolve()
        if not workspace.is_dir():
            raise ValueError(f"workspace is not a directory: {workspace}")
        enabled_tools = tuple(
            item.strip() for item in args.tools.split(",") if item.strip()
        )
        if not enabled_tools:
            raise ValueError("--tools must contain at least one tool name")

        provider_config = ProviderConfig.from_env(
            dotenv_path=args.dotenv_path,
            model_name=args.model,
            provider_api=args.provider_api,
            base_url=args.base_url,
            temperature=args.temperature,
            max_tokens=args.max_tokens,
            timeout_seconds=args.api_timeout,
            max_retries=args.max_retries,
        )
        provider = (provider_factory or create_provider)(provider_config)
        task = TaskSpec(
            task_id=args.task_id,
            instruction=args.instruction,
            workspace_root=workspace,
            enabled_tools=enabled_tools,
        )
        config = RunConfig(
            model=provider,
            budget=BudgetConfig(
                max_steps=args.max_steps,
                max_model_calls=args.max_model_calls,
                max_tool_calls=args.max_tool_calls,
                wall_time_seconds=args.wall_time,
                max_input_tokens=args.max_input_tokens,
                max_output_tokens=args.max_output_tokens,
                max_cost=args.max_cost,
            ),
            prompt_version=args.prompt_version,
            output_root=args.output_root,
            trajectory_path=args.trajectory_path,
            artifact_path=args.artifact_path,
            result_path=args.result_path,
        )
        runner = (runner_factory or HarnessRunner)()
        result = runner.run(task, config)  # type: ignore[attr-defined]
    except ProviderConfigurationError as exc:
        print(f"configuration error: {exc}", file=sys.stderr)
        return EXIT_CONFIG_ERROR
    except ProviderError as exc:
        print(f"provider error: {exc}", file=sys.stderr)
        return EXIT_PROVIDER_ERROR
    except ValueError as exc:
        print(f"configuration error: {exc}", file=sys.stderr)
        return EXIT_CONFIG_ERROR
    except Exception as exc:
        print(f"harness error: {type(exc).__name__}: {exc}", file=sys.stderr)
        return EXIT_HARNESS_FAILURE

    summary = {
        "run_id": result.run_id,
        "task_id": result.task_id,
        "attempt_id": result.attempt_id,
        "harness_success": result.harness_success,
        "benchmark_success": result.benchmark_success,
        "official_score": result.official_score,
        "stop_reason": result.stop_reason,
        "trajectory_path": result.trajectory_path,
        "artifact_path": result.artifact_path,
        "result_path": result.result_path,
    }
    print(json.dumps(summary, ensure_ascii=False, sort_keys=True))
    if result.stop_reason == "provider_error":
        return EXIT_PROVIDER_ERROR
    return EXIT_OK if result.harness_success else EXIT_HARNESS_FAILURE


def _print_checks(checks: Sequence[tuple[str, str, str]]) -> None:
    for status, name, detail in checks:
        print(f"[{status}] {name}: {detail}")


def _api_key_required(base_url: str) -> bool:
    hostname = (urlparse(base_url).hostname or "").lower()
    return hostname not in {"localhost", "127.0.0.1", "::1"}


def _positive_int(value: str) -> int:
    parsed = int(value)
    if parsed < 1:
        raise argparse.ArgumentTypeError("must be at least 1")
    return parsed


def _non_negative_int(value: str) -> int:
    parsed = int(value)
    if parsed < 0:
        raise argparse.ArgumentTypeError("must be non-negative")
    return parsed


def _positive_float(value: str) -> float:
    parsed = float(value)
    if parsed <= 0:
        raise argparse.ArgumentTypeError("must be positive")
    return parsed
