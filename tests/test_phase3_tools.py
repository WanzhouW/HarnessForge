from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

from harness_forge.safety.command_policy import CommandPolicy
from harness_forge.safety.workspace import WorkspaceGuard
from harness_forge.tools.diff import WorkspaceChangeTracker, build_diff_tool
from harness_forge.tools.edit import build_edit_tool
from harness_forge.tools.filesystem import build_filesystem_tools
from harness_forge.tools.patch import build_patch_tool
from harness_forge.tools.registry import ToolRegistry
from harness_forge.tools.search import build_search_tool
from harness_forge.tools.terminal import build_terminal_tool


class Phase3WorkspaceToolTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        (self.root / "notes.txt").write_text(
            "alpha\nold value\nomega\nlast\n", encoding="utf-8"
        )
        (self.root / "src").mkdir()
        (self.root / "src" / "sample.py").write_text(
            "value123\nVALUE456\n", encoding="utf-8"
        )
        (self.root / "docs").mkdir()
        (self.root / "docs" / "sample.txt").write_text(
            "value999\n", encoding="utf-8"
        )
        guard = WorkspaceGuard(self.root)
        tracker = WorkspaceChangeTracker(guard)
        self.registry = ToolRegistry()
        self.registry.register_many(build_filesystem_tools(guard, tracker))
        self.registry.register(build_search_tool(guard))
        self.registry.register(build_edit_tool(guard, tracker))
        self.registry.register(build_diff_tool(guard, tracker))
        self.registry.register(build_patch_tool(guard, tracker))

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_write_file_creates_file_and_get_diff_reports_it(self) -> None:
        write_result = self.registry.invoke(
            "write_file", {"path": "created.txt", "content": "created\n"}
        )
        diff_result = self.registry.invoke("get_diff")

        self.assertTrue(write_result.success)
        self.assertTrue(write_result.output["created"])
        self.assertEqual(
            (self.root / "created.txt").read_text(encoding="utf-8"), "created\n"
        )
        self.assertTrue(diff_result.success)
        self.assertIn("created.txt", diff_result.output["changed_files"])
        self.assertIn("+created", diff_result.output["diff"])

    def test_write_file_requires_explicit_overwrite(self) -> None:
        rejected = self.registry.invoke(
            "write_file", {"path": "notes.txt", "content": "replacement\n"}
        )
        replaced = self.registry.invoke(
            "write_file",
            {
                "path": "notes.txt",
                "content": "replacement\n",
                "overwrite": True,
            },
        )

        self.assertFalse(rejected.success)
        self.assertEqual(rejected.error_type, "FILE_EXISTS")
        self.assertTrue(replaced.success)
        self.assertTrue(replaced.output["overwritten"])
        self.assertEqual(
            (self.root / "notes.txt").read_text(encoding="utf-8"),
            "replacement\n",
        )

    def test_read_file_returns_requested_line_range(self) -> None:
        result = self.registry.invoke(
            "read_file",
            {"path": "notes.txt", "start_line": 2, "line_count": 2},
        )

        self.assertTrue(result.success)
        self.assertEqual(result.output["content"], "old value\nomega\n")
        self.assertEqual(result.output["start_line"], 2)
        self.assertEqual(result.output["end_line"], 3)
        self.assertEqual(result.output["total_lines"], 4)
        self.assertTrue(result.output["has_more"])

    def test_search_text_supports_regex_glob_and_case_setting(self) -> None:
        result = self.registry.invoke(
            "search_text",
            {
                "query": r"value\d+",
                "regex": True,
                "glob": "src/*.py",
                "case_sensitive": False,
            },
        )

        self.assertTrue(result.success)
        self.assertEqual(result.output["match_count"], 2)
        self.assertEqual(
            {item["path"] for item in result.output["matches"]}, {"src/sample.py"}
        )

    def test_list_dir_reports_explicit_truncation_counts(self) -> None:
        result = self.registry.invoke("list_dir", {"path": ".", "max_entries": 1})

        self.assertTrue(result.success)
        self.assertTrue(result.output["truncated"])
        self.assertEqual(result.output["returned_entries"], 1)
        self.assertGreater(result.output["remaining_entries"], 0)
        self.assertGreater(result.output["total_entries"], 1)

    def test_apply_patch_modifies_file_and_is_visible_in_diff(self) -> None:
        patch = (
            "--- a/notes.txt\n"
            "+++ b/notes.txt\n"
            "@@ -1,3 +1,3 @@\n"
            " alpha\n"
            "-old value\n"
            "+new value\n"
            " omega\n"
        )
        result = self.registry.invoke("apply_patch", {"patch": patch})
        diff_result = self.registry.invoke("get_diff")

        self.assertTrue(result.success)
        self.assertEqual(result.output["modified"], ["notes.txt"])
        self.assertIn(
            "new value", (self.root / "notes.txt").read_text(encoding="utf-8")
        )
        self.assertIn("-old value", diff_result.output["diff"])
        self.assertIn("+new value", diff_result.output["diff"])

    def test_apply_patch_can_create_new_file(self) -> None:
        patch = (
            "--- /dev/null\n"
            "+++ b/new_file.txt\n"
            "@@ -0,0 +1,2 @@\n"
            "+first\n"
            "+second\n"
        )
        result = self.registry.invoke("apply_patch", {"patch": patch})

        self.assertTrue(result.success)
        self.assertEqual(result.output["created"], ["new_file.txt"])
        self.assertEqual(
            (self.root / "new_file.txt").read_text(encoding="utf-8"),
            "first\nsecond\n",
        )

    def test_apply_patch_rejects_path_escape_without_changes(self) -> None:
        outside = self.root.parent / "outside.txt"
        patch = (
            "--- /dev/null\n"
            "+++ b/../outside.txt\n"
            "@@ -0,0 +1 @@\n"
            "+blocked\n"
        )
        result = self.registry.invoke("apply_patch", {"patch": patch})

        self.assertFalse(result.success)
        self.assertEqual(result.error_type, "PATH_BLOCKED")
        self.assertFalse(outside.exists())

    def test_apply_patch_rejects_context_mismatch_without_changes(self) -> None:
        original = (self.root / "notes.txt").read_text(encoding="utf-8")
        patch = (
            "--- a/notes.txt\n"
            "+++ b/notes.txt\n"
            "@@ -1,1 +1,1 @@\n"
            "-does not match\n"
            "+replacement\n"
        )
        result = self.registry.invoke("apply_patch", {"patch": patch})

        self.assertFalse(result.success)
        self.assertEqual(result.error_type, "PATCH_INVALID")
        self.assertEqual(
            (self.root / "notes.txt").read_text(encoding="utf-8"), original
        )


class Phase3TerminalToolTests(unittest.TestCase):
    def test_truncated_output_is_preserved_in_artifact(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            artifact_dir = root / "artifacts"
            script = "print('x' * 200)"
            command = (sys.executable, "-c", script)
            policy = CommandPolicy(allowed_commands=(command,))
            tool = build_terminal_tool(
                WorkspaceGuard(root), policy=policy, artifact_dir=artifact_dir
            )
            registry = ToolRegistry()
            registry.register(tool)

            result = registry.invoke(
                "run_command",
                {
                    "command": list(command),
                    "max_output_chars": 20,
                },
            )

            self.assertTrue(result.success)
            self.assertTrue(result.output["stdout_truncated"])
            self.assertEqual(len(result.output["stdout"]), 20)
            artifact_path = Path(result.output["artifact_path"])
            self.assertTrue(artifact_path.is_file())
            artifact = json.loads(artifact_path.read_text(encoding="utf-8"))
            self.assertGreater(len(artifact["stdout"]), 200)
            self.assertIn("xxx", artifact["stdout"])

    def test_default_host_policy_still_rejects_arbitrary_python(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            registry = ToolRegistry()
            registry.register(build_terminal_tool(WorkspaceGuard(root)))

            result = registry.invoke(
                "run_command", {"command": [sys.executable, "-c", "print('no')"]}
            )

            self.assertFalse(result.success)
            self.assertEqual(result.error_type, "COMMAND_BLOCKED")


if __name__ == "__main__":
    unittest.main()
