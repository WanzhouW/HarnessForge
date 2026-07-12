from __future__ import annotations

import json
import tempfile
import time
import unittest
from pathlib import Path

from harness_forge.agent.state import AgentAction, ModelRequest, ScriptedModel
from harness_forge.harness.budgets import BudgetConfig
from harness_forge.harness.runner import HarnessRunner
from harness_forge.harness.task import RunConfig, TaskSpec


class _SlowFinalModel:
    model_name = "slow-scripted"

    def next_action(self, request: ModelRequest) -> AgentAction:
        time.sleep(0.02)
        return AgentAction.final("too late")


class Phase2RunnerTests(unittest.TestCase):
    def _task(self, root: Path) -> TaskSpec:
        return TaskSpec(
            task_id="phase2-toy",
            instruction="Inspect the workspace and finish.",
            workspace_root=root,
            enabled_tools=("list_dir",),
        )

    def test_normal_run_writes_structured_result_and_trajectory(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            result = HarnessRunner().run(
                self._task(root),
                RunConfig(
                    model=ScriptedModel([AgentAction.final("done")]),
                    budget=BudgetConfig(max_steps=2, max_model_calls=2),
                    output_root=root / "runs",
                    prompt_version="test-prompt-v1",
                ),
            )

            self.assertTrue(result.harness_success)
            self.assertIsNone(result.benchmark_success)
            self.assertIsNone(result.official_score)
            self.assertEqual(result.stop_reason, "final_answer")
            self.assertEqual(result.prompt_version, "test-prompt-v1")
            self.assertTrue(result.run_id)
            self.assertTrue(result.attempt_id)
            self.assertEqual(result.model_call_count, 1)
            self.assertEqual(result.tool_call_count, 0)
            self.assertEqual(result.model_config["model_name"], "scripted")

            trajectory_path = Path(result.trajectory_path or "")
            result_path = Path(result.result_path or "")
            artifact_path = Path(result.artifact_path or "")
            self.assertTrue(trajectory_path.is_file())
            self.assertTrue(result_path.is_file())
            self.assertTrue(artifact_path.is_dir())
            self.assertGreater(trajectory_path.stat().st_size, 0)
            payload = json.loads(result_path.read_text(encoding="utf-8"))
            self.assertTrue(payload["harness_success"])
            self.assertIsNone(payload["benchmark_success"])
            self.assertEqual(payload["run_id"], result.run_id)

    def test_max_steps_stops_cleanly(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            model = ScriptedModel([AgentAction.tool("list_dir", {"path": "."})])
            result = HarnessRunner().run(
                self._task(root),
                RunConfig(
                    model=model,
                    budget=BudgetConfig(max_steps=1, max_model_calls=2),
                    output_root=root / "runs",
                ),
            )

            self.assertFalse(result.harness_success)
            self.assertEqual(result.stop_reason, "max_steps")
            self.assertEqual(result.model_call_count, 1)
            self.assertEqual(result.tool_call_count, 1)

    def test_max_tool_calls_stops_before_invoking_tool(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            result = HarnessRunner().run(
                self._task(root),
                RunConfig(
                    model=ScriptedModel(
                        [AgentAction.tool("list_dir", {"path": "."})]
                    ),
                    budget=BudgetConfig(
                        max_steps=2,
                        max_tool_calls=0,
                        max_model_calls=2,
                    ),
                    output_root=root / "runs",
                ),
            )

            self.assertFalse(result.harness_success)
            self.assertEqual(result.stop_reason, "max_tool_calls")
            self.assertEqual(result.tool_call_count, 0)

    def test_max_model_calls_stops_before_extra_model_request(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            model = ScriptedModel(
                [
                    AgentAction.tool("list_dir", {"path": "."}),
                    AgentAction.final("not reached"),
                ]
            )
            result = HarnessRunner().run(
                self._task(root),
                RunConfig(
                    model=model,
                    budget=BudgetConfig(max_steps=3, max_model_calls=1),
                    output_root=root / "runs",
                ),
            )

            self.assertFalse(result.harness_success)
            self.assertEqual(result.stop_reason, "max_model_calls")
            self.assertEqual(result.model_call_count, 1)
            self.assertEqual(len(model.requests), 1)

    def test_wall_time_stops_after_slow_model_call(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            result = HarnessRunner().run(
                self._task(root),
                RunConfig(
                    model=_SlowFinalModel(),
                    budget=BudgetConfig(
                        max_steps=2,
                        max_model_calls=2,
                        wall_time_seconds=0.001,
                    ),
                    output_root=root / "runs",
                ),
            )

            self.assertFalse(result.harness_success)
            self.assertEqual(result.stop_reason, "wall_time")
            self.assertEqual(result.model_call_count, 1)

    def test_each_attempt_gets_distinct_ids(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            runner = HarnessRunner()
            first = runner.run(
                self._task(root),
                RunConfig(
                    model=ScriptedModel([AgentAction.final("one")]),
                    output_root=root / "runs",
                ),
            )
            second = runner.run(
                self._task(root),
                RunConfig(
                    model=ScriptedModel([AgentAction.final("two")]),
                    output_root=root / "runs",
                ),
            )

            self.assertNotEqual(first.run_id, second.run_id)
            self.assertNotEqual(first.attempt_id, second.attempt_id)


if __name__ == "__main__":
    unittest.main()
