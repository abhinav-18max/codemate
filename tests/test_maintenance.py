from __future__ import annotations

import io
import contextlib
import tempfile
import unittest
from pathlib import Path

from codemate import cli
from codemate.config import init_project


class CleanTests(unittest.TestCase):
    def test_clean_all_removes_generated_files_and_gitignore_entries(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            init_project(root)
            self.assertTrue((root / "team.yml").exists())
            self.assertTrue((root / ".team").exists())

            with contextlib.redirect_stdout(io.StringIO()):
                rc = cli._clean(root, remove_all=True, assume_yes=True)

            self.assertEqual(rc, 0)
            self.assertFalse((root / "team.yml").exists())
            self.assertFalse((root / ".team").exists())
            self.assertFalse((root / "docs" / "team.md").exists())
            gitignore = (root / ".gitignore").read_text()
            self.assertNotIn(".team/runs/", gitignore)
            self.assertNotIn(".team/lock.json", gitignore)

    def test_clean_default_removes_only_run_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            init_project(root)
            (root / ".team" / "runs" / "r1").mkdir(parents=True)
            (root / ".team" / "lock.json").write_text("{}")

            with contextlib.redirect_stdout(io.StringIO()):
                rc = cli._clean(root, remove_all=False, assume_yes=True)

            self.assertEqual(rc, 0)
            self.assertFalse((root / ".team" / "runs").exists())
            self.assertFalse((root / ".team" / "lock.json").exists())
            # Config and templates are untouched.
            self.assertTrue((root / "team.yml").exists())
            self.assertTrue((root / ".team" / "prompts").exists())

    def test_clean_nothing_to_do(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            with contextlib.redirect_stdout(io.StringIO()) as buf:
                rc = cli._clean(Path(tmp), remove_all=True, assume_yes=True)
            self.assertEqual(rc, 0)
            self.assertIn("Nothing to clean", buf.getvalue())


class UpdateTests(unittest.TestCase):
    def test_upgrade_command_targets_the_package(self) -> None:
        command = cli._upgrade_command()
        self.assertTrue(command)
        self.assertIn("codemate-team", command)

    def test_version_tuple_ordering(self) -> None:
        self.assertGreater(cli._version_tuple("0.2.0"), cli._version_tuple("0.1.0"))
        self.assertGreater(cli._version_tuple("0.10.0"), cli._version_tuple("0.2.0"))
        self.assertEqual(cli._version_tuple("1.0"), (1, 0))


if __name__ == "__main__":
    unittest.main()
