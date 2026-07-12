from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from harness_forge.safety.workspace import WorkspaceGuard, WorkspaceSecurityError


class WorkspaceGuardTests(unittest.TestCase):
    def test_allows_path_inside_workspace(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            target = root / "src" / "example.py"
            target.parent.mkdir()
            target.write_text("VALUE = 1\n", encoding="utf-8")

            guard = WorkspaceGuard(root)

            self.assertEqual(guard.resolve_path("src/example.py"), target.resolve())

    def test_rejects_parent_traversal(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            guard = WorkspaceGuard(temp_dir)

            with self.assertRaises(WorkspaceSecurityError):
                guard.resolve_path("../outside.txt")

    def test_rejects_sensitive_paths(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            guard = WorkspaceGuard(temp_dir)

            for path in (".env", "config/service_secret.txt", "keys/private.pem"):
                with self.subTest(path=path):
                    with self.assertRaises(WorkspaceSecurityError):
                        guard.resolve_path(path)


if __name__ == "__main__":
    unittest.main()

