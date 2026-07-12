from __future__ import annotations

import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch

from harness_forge.cli import (
    EXIT_CONFIG_ERROR,
    EXIT_OK,
    main,
)
from harness_forge.providers import LLMProvider, ModelMessage, ModelResponse, ProviderConfig, ToolDefinition


class _FinalProvider(LLMProvider):
    def __init__(self, config: ProviderConfig) -> None:
        self.config = config

    def complete(
        self,
        messages: list[ModelMessage] | tuple[ModelMessage, ...],
        tools: list[ToolDefinition] | tuple[ToolDefinition, ...] = (),
    ) -> ModelResponse:
        return ModelResponse(
            content="CLI task complete.",
            model_name=self.config.model_name,
            input_tokens=5,
            output_tokens=3,
            total_tokens=8,
        )


class CliTests(unittest.TestCase):
    def test_help_is_available(self) -> None:
        output = io.StringIO()
        with redirect_stdout(output), self.assertRaises(SystemExit) as raised:
            main(["--help"])

        self.assertEqual(raised.exception.code, 0)
        self.assertIn("doctor", output.getvalue())
        self.assertIn("run", output.getvalue())

    def test_doctor_reports_configuration_without_exposing_key(self) -> None:
        output = io.StringIO()
        environment = {
            "MODEL_NAME": "doctor-model",
            "OPENAI_API_KEY": "super-secret-doctor-key",
            "OPENAI_BASE_URL": "https://api.openai.com/v1",
        }
        with (
            patch.dict(os.environ, environment, clear=True),
            patch("harness_forge.cli.sys.version_info", (3, 11, 9)),
            redirect_stdout(output),
        ):
            exit_code = main(
                ["doctor", "--dotenv-path", "missing.env"],
                provider_factory=lambda config: object(),
            )

        self.assertEqual(exit_code, EXIT_OK)
        self.assertIn("configured", output.getvalue())
        self.assertNotIn("super-secret-doctor-key", output.getvalue())
        self.assertIn("no request sent", output.getvalue())

    def test_doctor_rejects_missing_model(self) -> None:
        output = io.StringIO()
        with (
            patch.dict(os.environ, {}, clear=True),
            patch("harness_forge.cli.sys.version_info", (3, 11, 9)),
            redirect_stdout(output),
        ):
            exit_code = main(
                ["doctor", "--dotenv-path", "missing.env"],
                provider_factory=lambda config: object(),
            )

        self.assertEqual(exit_code, EXIT_CONFIG_ERROR)
        self.assertIn("model_name must be non-empty", output.getvalue())

    def test_doctor_reports_selected_chat_completions_protocol(self) -> None:
        output = io.StringIO()
        captured: list[ProviderConfig] = []

        def provider_factory(config: ProviderConfig) -> object:
            captured.append(config)
            return object()

        environment = {
            "MODEL_NAME": "deepseek-chat",
            "OPENAI_API_KEY": "test-key",
            "OPENAI_BASE_URL": "https://api.deepseek.com",
            "PROVIDER_API": "chat_completions",
        }
        with (
            patch.dict(os.environ, environment, clear=True),
            patch("harness_forge.cli.sys.version_info", (3, 11, 9)),
            redirect_stdout(output),
        ):
            exit_code = main(["doctor"], provider_factory=provider_factory)

        self.assertEqual(exit_code, EXIT_OK)
        self.assertEqual(captured[0].provider_api, "chat_completions")
        self.assertIn("PROVIDER_API: chat_completions", output.getvalue())

    def test_doctor_cli_protocol_overrides_environment(self) -> None:
        output = io.StringIO()
        captured: list[ProviderConfig] = []

        def provider_factory(config: ProviderConfig) -> object:
            captured.append(config)
            return object()

        environment = {
            "MODEL_NAME": "test-model",
            "OPENAI_API_KEY": "test-key",
            "OPENAI_BASE_URL": "https://api.openai.com/v1",
            "PROVIDER_API": "responses",
        }
        with (
            patch.dict(os.environ, environment, clear=True),
            patch("harness_forge.cli.sys.version_info", (3, 11, 9)),
            redirect_stdout(output),
        ):
            exit_code = main(
                ["doctor", "--provider-api", "chat_completions"],
                provider_factory=provider_factory,
            )

        self.assertEqual(exit_code, EXIT_OK)
        self.assertEqual(captured[0].provider_api, "chat_completions")

    def test_doctor_rejects_missing_key_for_remote_endpoint(self) -> None:
        output = io.StringIO()
        environment = {
            "MODEL_NAME": "deepseek-chat",
            "OPENAI_BASE_URL": "https://api.deepseek.com",
            "PROVIDER_API": "chat_completions",
        }
        with (
            patch.dict(os.environ, environment, clear=True),
            patch("harness_forge.cli.sys.version_info", (3, 11, 9)),
            redirect_stdout(output),
        ):
            exit_code = main(
                ["doctor", "--dotenv-path", "missing.env"],
                provider_factory=lambda config: object(),
            )

        self.assertEqual(exit_code, EXIT_CONFIG_ERROR)
        self.assertIn("[FAIL] OPENAI_API_KEY: not configured", output.getvalue())
        self.assertIn("remote endpoint requires API key", output.getvalue())
        self.assertNotIn("no request sent", output.getvalue())

    def test_run_executes_local_task_and_writes_outputs(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            output = io.StringIO()
            environment = {
                "MODEL_NAME": "cli-model",
                "OPENAI_API_KEY": "test-key",
            }
            with patch.dict(os.environ, environment, clear=True), redirect_stdout(output):
                exit_code = main(
                    [
                        "run",
                        "--task-id",
                        "cli-toy",
                        "--instruction",
                        "Finish without tools.",
                        "--workspace",
                        str(root),
                        "--tools",
                        "list_dir",
                        "--output-root",
                        str(root / "runs"),
                    ],
                    provider_factory=_FinalProvider,
                )

            self.assertEqual(exit_code, EXIT_OK)
            summary = json.loads(output.getvalue())
            self.assertTrue(summary["harness_success"])
            self.assertIsNone(summary["benchmark_success"])
            self.assertTrue(Path(summary["trajectory_path"]).is_file())
            self.assertTrue(Path(summary["result_path"]).is_file())
            result = json.loads(
                Path(summary["result_path"]).read_text(encoding="utf-8")
            )
            self.assertEqual(result["task_id"], "cli-toy")

    def test_run_rejects_missing_workspace(self) -> None:
        error = io.StringIO()
        with patch.dict(os.environ, {"MODEL_NAME": "cli-model"}, clear=True), redirect_stderr(error):
            exit_code = main(
                [
                    "run",
                    "--task-id",
                    "bad-workspace",
                    "--instruction",
                    "Do work.",
                    "--workspace",
                    "does-not-exist",
                ],
                provider_factory=_FinalProvider,
            )

        self.assertEqual(exit_code, EXIT_CONFIG_ERROR)
        self.assertIn("workspace is not a directory", error.getvalue())


if __name__ == "__main__":
    unittest.main()
