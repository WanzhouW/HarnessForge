from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from harness_forge.agent.state import AgentAction, ScriptedModel
from harness_forge.harness.budgets import BudgetConfig
from harness_forge.harness.runner import HarnessRunner
from harness_forge.harness.task import RunConfig, TaskSpec


class HarnessSmokeTests(unittest.TestCase):
    def test_scripted_agent_completes_task_and_records_trajectory(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            target = root / "sample.txt"
            target.write_text("hello old value\n", encoding="utf-8")
            trajectory_path = root / "run.jsonl"
            model = ScriptedModel(
                [
                    AgentAction.tool("list_dir", {"path": "."}),
                    AgentAction.tool("read_file", {"path": "sample.txt"}),
                    AgentAction.tool("search_text", {"query": "old value"}),
                    AgentAction.tool(
                        "edit_file",
                        {
                            "path": "sample.txt",
                            "old_text": "old value",
                            "new_text": "new value",
                        },
                    ),
                    AgentAction.final("Updated sample.txt."),
                ]
            )
            task = TaskSpec(
                task_id="smoke-edit",
                instruction="Replace old value with new value in sample.txt.",
                workspace_root=root,
                enabled_tools=("list_dir", "read_file", "search_text", "edit_file"),
            )
            config = RunConfig(
                model=model,
                budget=BudgetConfig(
                    max_steps=6,
                    max_tool_calls=4,
                    wall_time_seconds=10,
                    max_model_calls=6,
                ),
                output_root=root / "runs",
                trajectory_path=trajectory_path,
            )

            result = HarnessRunner().run(task, config)

            self.assertTrue(result.harness_success)
            self.assertIsNone(result.benchmark_success)
            self.assertIsNone(result.official_score)
            self.assertEqual(result.stop_reason, "final_answer")
            self.assertEqual(result.task_id, "smoke-edit")
            self.assertEqual(result.model_name, "scripted")
            self.assertEqual(result.model_call_count, 5)
            self.assertEqual(result.tool_call_count, 4)
            self.assertIsNone(result.total_tokens)
            self.assertEqual(len(result.tool_calls), 4)
            self.assertGreaterEqual(len(result.trajectory), 5)
            self.assertIn("new value", target.read_text(encoding="utf-8"))
            self.assertTrue(trajectory_path.exists())

            events = [
                json.loads(line)
                for line in trajectory_path.read_text(encoding="utf-8").splitlines()
            ]
            self.assertGreaterEqual(len(events), 7)
            for event in events:
                self.assertEqual(event["task_id"], "smoke-edit")
                self.assertTrue(event["run_id"])
                self.assertIn("step_id", event)
                self.assertIn("event_type", event)
                self.assertIn("timestamp", event)


if __name__ == "__main__":
    unittest.main()
