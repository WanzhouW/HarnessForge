from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from harness_forge.safety.workspace import WorkspaceGuard
from harness_forge.tools.edit import build_edit_tool
from harness_forge.tools.filesystem import build_filesystem_tools
from harness_forge.tools.registry import ToolRegistry
from harness_forge.tools.search import build_search_tool


class FilesystemToolTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        (self.root / "notes.txt").write_text("alpha\nunique old\nomega\n", encoding="utf-8")
        (self.root / "many.txt").write_text("repeat\nrepeat\n", encoding="utf-8")
        guard = WorkspaceGuard(self.root)
        self.registry = ToolRegistry()
        self.registry.register_many(build_filesystem_tools(guard))
        self.registry.register(build_search_tool(guard))
        self.registry.register(build_edit_tool(guard))

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_list_dir_lists_file(self) -> None:
        result = self.registry.invoke("list_dir", {"path": "."})

        self.assertTrue(result.success)
        self.assertIn("notes.txt", [entry["name"] for entry in result.output["entries"]])

    def test_read_file_reads_content(self) -> None:
        result = self.registry.invoke("read_file", {"path": "notes.txt"})

        self.assertTrue(result.success)
        self.assertIn("unique old", result.output["content"])
        self.assertFalse(result.output["truncated"])

    def test_search_text_finds_literal(self) -> None:
        result = self.registry.invoke("search_text", {"query": "alpha"})

        self.assertTrue(result.success)
        self.assertEqual(result.output["match_count"], 1)
        self.assertEqual(result.output["matches"][0]["path"], "notes.txt")

    def test_edit_file_replaces_unique_text(self) -> None:
        result = self.registry.invoke(
            "edit_file",
            {"path": "notes.txt", "old_text": "unique old", "new_text": "unique new"},
        )

        self.assertTrue(result.success)
        self.assertTrue(result.output["changed"])
        self.assertIn("unique new", (self.root / "notes.txt").read_text(encoding="utf-8"))

    def test_edit_file_rejects_multiple_matches(self) -> None:
        original = (self.root / "many.txt").read_text(encoding="utf-8")
        result = self.registry.invoke(
            "edit_file",
            {"path": "many.txt", "old_text": "repeat", "new_text": "changed"},
        )

        self.assertFalse(result.success)
        self.assertEqual(result.error_type, "EDIT_AMBIGUOUS")
        self.assertEqual((self.root / "many.txt").read_text(encoding="utf-8"), original)


if __name__ == "__main__":
    unittest.main()

