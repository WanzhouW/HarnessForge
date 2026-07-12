from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from typing import Sequence

from harness_forge.harness.budgets import BudgetConfig
from harness_forge.harness.runner import HarnessRunner
from harness_forge.harness.task import RunConfig, TaskSpec
from harness_forge.providers import (
    LLMProvider,
    ModelMessage,
    ModelResponse,
    ProviderConfig,
    ToolCall,
    ToolDefinition,
)


class _FakeProvider(LLMProvider):
    def __init__(self, responses: list[ModelResponse]) -> None:
        self.config = ProviderConfig(model_name="fake-provider-model")
        self._responses = list(responses)
        self.requests: list[
            tuple[tuple[ModelMessage, ...], tuple[ToolDefinition, ...]]
        ] = []

    def complete(
        self,
        messages: Sequence[ModelMessage],
        tools: Sequence[ToolDefinition] = (),
    ) -> ModelResponse:
        self.requests.append((tuple(messages), tuple(tools)))
        return self._responses.pop(0)


class ProviderLoopTests(unittest.TestCase):
    def test_fake_provider_can_call_tool_then_return_final_answer(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "notes.txt").write_text("provider loop\n", encoding="utf-8")
            provider = _FakeProvider(
                [
                    ModelResponse(
                        tool_calls=(
                            ToolCall(
                                call_id="call_read",
                                name="read_file",
                                arguments={"path": "notes.txt"},
                            ),
                        ),
                        model_name="served-fake-model",
                        input_tokens=10,
                        output_tokens=3,
                        total_tokens=13,
                    ),
                    ModelResponse(
                        content="Read notes.txt successfully.",
                        model_name="served-fake-model",
                        input_tokens=12,
                        output_tokens=5,
                        total_tokens=17,
                    ),
                ]
            )
            task = TaskSpec(
                task_id="provider-read",
                instruction="Read notes.txt.",
                workspace_root=root,
                enabled_tools=("read_file",),
            )
            config = RunConfig(
                model=provider,
                budget=BudgetConfig(
                    max_steps=3,
                    max_tool_calls=1,
                    wall_time_seconds=10,
                    max_model_calls=3,
                ),
                output_root=root / "runs",
            )

            result = HarnessRunner().run(task, config)

            self.assertTrue(result.harness_success)
            self.assertIsNone(result.benchmark_success)
            self.assertEqual(result.final_answer, "Read notes.txt successfully.")
            self.assertEqual(result.model_name, "served-fake-model")
            self.assertEqual(result.model_call_count, 2)
            self.assertEqual(result.input_tokens, 22)
            self.assertEqual(result.output_tokens, 8)
            self.assertEqual(result.total_tokens, 30)
            self.assertIsNone(result.cost)
            self.assertEqual(len(result.tool_calls), 1)

            first_messages, first_tools = provider.requests[0]
            self.assertEqual(first_messages[0].role, "system")
            self.assertEqual(first_tools[0].name, "read_file")
            self.assertEqual(
                first_tools[0].parameters["properties"]["path"],
                {"type": "string"},
            )
            self.assertEqual(first_tools[0].parameters["required"], ["path"])

            second_messages, _ = provider.requests[1]
            self.assertEqual(second_messages[-2].role, "assistant")
            self.assertEqual(second_messages[-1].role, "tool")
            tool_payload = json.loads(second_messages[-1].content)
            self.assertTrue(tool_payload["success"])
            self.assertIn("provider loop", tool_payload["output"]["content"])

    def test_multiple_provider_tool_calls_are_executed_one_per_step(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "first.txt").write_text("first\n", encoding="utf-8")
            (root / "second.txt").write_text("second\n", encoding="utf-8")
            provider = _FakeProvider(
                [
                    ModelResponse(
                        tool_calls=(
                            ToolCall(
                                call_id="call_first",
                                name="read_file",
                                arguments={"path": "first.txt"},
                            ),
                            ToolCall(
                                call_id="call_second",
                                name="read_file",
                                arguments={"path": "second.txt"},
                            ),
                        ),
                        input_tokens=10,
                        output_tokens=4,
                        total_tokens=14,
                    ),
                    ModelResponse(
                        content="Read both files.",
                        input_tokens=16,
                        output_tokens=4,
                        total_tokens=20,
                    ),
                ]
            )
            task = TaskSpec(
                task_id="provider-multiple-tools",
                instruction="Read both files.",
                workspace_root=root,
                enabled_tools=("read_file",),
            )
            result = HarnessRunner().run(
                task,
                RunConfig(
                    model=provider,
                    budget=BudgetConfig(
                        max_steps=3,
                        max_model_calls=2,
                        max_tool_calls=2,
                    ),
                    output_root=root / "runs",
                ),
            )

            self.assertTrue(result.harness_success)
            self.assertEqual(result.model_call_count, 2)
            self.assertEqual(result.tool_call_count, 2)
            self.assertEqual(
                [call.step_id for call in result.tool_calls], [1, 2]
            )
            self.assertEqual(len(provider.requests), 2)

            second_messages, _ = provider.requests[1]
            self.assertEqual(second_messages[-3].role, "assistant")
            self.assertEqual(len(second_messages[-3].tool_calls), 2)
            self.assertEqual(second_messages[-2].tool_call_id, "call_first")
            self.assertEqual(second_messages[-1].tool_call_id, "call_second")

    def test_provider_usage_budget_stops_before_action(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            provider = _FakeProvider(
                [
                    ModelResponse(
                        content="would have completed",
                        model_name="served-fake-model",
                        input_tokens=11,
                        output_tokens=2,
                        total_tokens=13,
                    )
                ]
            )
            task = TaskSpec(
                task_id="provider-budget",
                instruction="Finish.",
                workspace_root=root,
                enabled_tools=("list_dir",),
            )
            result = HarnessRunner().run(
                task,
                RunConfig(
                    model=provider,
                    budget=BudgetConfig(
                        max_steps=2,
                        max_model_calls=2,
                        max_input_tokens=10,
                    ),
                    output_root=root / "runs",
                ),
            )

            self.assertFalse(result.harness_success)
            self.assertEqual(result.stop_reason, "max_input_tokens")
            self.assertEqual(result.input_tokens, 11)


if __name__ == "__main__":
    unittest.main()
