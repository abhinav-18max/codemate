from __future__ import annotations

import subprocess
import tempfile
import unittest
from pathlib import Path

from codemate.git_tools import changed_files


class GitToolsTests(unittest.TestCase):
    def test_changed_files_preserves_unicode_and_spaces(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _git(root, "init")
            _git(root, "config", "user.email", "test@example.com")
            _git(root, "config", "user.name", "Test User")

            # Names that git would otherwise quote/escape in plain --porcelain.
            (root / "café menu.py").write_text("x\n")

            files = changed_files(root)

            self.assertIn("café menu.py", files)
            # No surrounding quotes or backslash escapes leaked through.
            self.assertTrue(all('"' not in path and "\\" not in path for path in files))

    def test_changed_files_can_exclude_untracked(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _git(root, "init")
            (root / "new.txt").write_text("x\n")

            self.assertEqual(changed_files(root, include_untracked=False), [])


def _git(root: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=root, check=True, stdout=subprocess.DEVNULL)


if __name__ == "__main__":
    unittest.main()
