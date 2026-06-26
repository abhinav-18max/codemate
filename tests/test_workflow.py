from __future__ import annotations

import os
import stat
import subprocess
import tempfile
import textwrap
import unittest
from pathlib import Path

from codemate.config import load_config
from codemate.workflow import run_task


class WorkflowTests(unittest.TestCase):
    def test_run_task_with_fake_agents_reaches_done(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            fake_codex = root / "fake_codex.py"
            fake_claude = root / "fake_claude.py"
            _write_executable(
                fake_codex,
                """#!/usr/bin/env python3
import pathlib
import sys

args = sys.argv
cwd = pathlib.Path(args[args.index("--cd") + 1])
output = pathlib.Path(args[args.index("--output-last-message") + 1])
if "implementation" in output.name or "fix" in output.name:
    (cwd / "app.txt").write_text("done\\n")
output.write_text("implemented\\n")
""",
            )
            _write_executable(
                fake_claude,
                """#!/usr/bin/env python3
print("decision: pass")
""",
            )
            (root / "team.yml").write_text(
                textwrap.dedent(
                    f"""
                    version: 1
                    workflow:
                      default: plan_implement_review_test
                      flows:
                        plan_implement_review_test:
                          steps:
                            - id: plan
                              type: agent
                              agent: claude
                              mode: read_only
                              output: plan
                            - id: implement
                              type: agent
                              agent: codex
                              mode: write
                              input:
                                - plan
                              output: implementation
                            - id: review
                              type: agent
                              agent: claude
                              mode: review_only
                              output: review
                            - id: test
                              type: command
                              command_group: test
                    agents:
                      claude:
                        provider: claude-code
                        command: {fake_claude}
                      codex:
                        provider: codex-cli
                        command: {fake_codex}
                        sandbox: workspace-write
                        approval: never
                    commands:
                      test: []
                    git:
                      strategy: branch
                      branch_prefix: ai/team
                      require_clean_worktree: true
                    limits:
                      max_fix_retries: 1
                      max_changed_files: 5
                      max_diff_lines: 100
                    policies:
                      allow_paths:
                        - app.txt
                      deny_paths:
                        - .env
                        - .team/runs/**
                    """
                ).strip()
                + "\n"
            )
            _git(root, "init")
            _git(root, "config", "user.email", "test@example.com")
            _git(root, "config", "user.name", "Test User")
            _git(root, "add", "team.yml", "fake_codex.py", "fake_claude.py")
            _git(root, "commit", "-m", "init")

            state = run_task(load_config(root), "make app done")

            self.assertEqual(state.status, "DONE")
            self.assertEqual((root / "app.txt").read_text(), "done\n")
            self.assertTrue((root / ".team" / "runs" / state.run_id / "state.json").exists())

    def test_policy_failure_records_needs_human_state(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            fake_codex = root / "fake_codex.py"
            fake_claude = root / "fake_claude.py"
            _write_executable(
                fake_codex,
                """#!/usr/bin/env python3
import pathlib
import sys

args = sys.argv
cwd = pathlib.Path(args[args.index("--cd") + 1])
output = pathlib.Path(args[args.index("--output-last-message") + 1])
if "implementation" in output.name:
    (cwd / ".env").write_text("SECRET=value\\n")
output.write_text("implemented\\n")
""",
            )
            _write_executable(
                fake_claude,
                """#!/usr/bin/env python3
print("decision: pass")
""",
            )
            (root / "team.yml").write_text(
                textwrap.dedent(
                    f"""
                    version: 1
                    workflow:
                      default: plan_implement_review_test
                      flows:
                        plan_implement_review_test:
                          steps:
                            - id: plan
                              type: agent
                              agent: claude
                              mode: read_only
                              output: plan
                            - id: implement
                              type: agent
                              agent: codex
                              mode: write
                              output: implementation
                            - id: review
                              type: agent
                              agent: claude
                              mode: review_only
                              output: review
                            - id: test
                              type: command
                              command_group: test
                    agents:
                      claude:
                        provider: claude-code
                        command: {fake_claude}
                      codex:
                        provider: codex-cli
                        command: {fake_codex}
                        sandbox: workspace-write
                        approval: never
                    commands:
                      test: []
                    git:
                      strategy: branch
                      branch_prefix: ai/team
                      require_clean_worktree: true
                    limits:
                      max_fix_retries: 1
                      max_changed_files: 5
                      max_diff_lines: 100
                    policies:
                      allow_paths:
                        - app.txt
                      deny_paths:
                        - .env
                    """
                ).strip()
                + "\n"
            )
            _git(root, "init")
            _git(root, "config", "user.email", "test@example.com")
            _git(root, "config", "user.name", "Test User")
            _git(root, "add", "team.yml", "fake_codex.py", "fake_claude.py")
            _git(root, "commit", "-m", "init")

            with self.assertRaises(Exception):
                run_task(load_config(root), "write a denied file")

            state_files = list((root / ".team" / "runs").glob("*/state.json"))
            self.assertEqual(len(state_files), 1)
            state_text = state_files[0].read_text()
            self.assertIn('"status": "NEEDS_HUMAN"', state_text)
            self.assertIn(".env", state_text)


    def test_ambiguous_review_does_not_auto_pass(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            fake_codex = root / "fake_codex.py"
            fake_claude = root / "fake_claude.py"
            _write_executable(
                fake_codex,
                """#!/usr/bin/env python3
import pathlib
import sys

args = sys.argv
cwd = pathlib.Path(args[args.index("--cd") + 1])
output = pathlib.Path(args[args.index("--output-last-message") + 1])
if "implementation" in output.name or "fix" in output.name:
    (cwd / "app.txt").write_text("done\\n")
output.write_text("implemented\\n")
""",
            )
            # Review output never states a decision -> must fail closed.
            _write_executable(
                fake_claude,
                """#!/usr/bin/env python3
print("The implementation looks reasonable overall.")
""",
            )
            (root / "team.yml").write_text(
                textwrap.dedent(
                    f"""
                    version: 1
                    workflow:
                      default: plan_implement_review_test
                      flows:
                        plan_implement_review_test:
                          steps:
                            - id: plan
                              type: agent
                              agent: claude
                              mode: read_only
                              output: plan
                            - id: implement
                              type: agent
                              agent: codex
                              mode: write
                              output: implementation
                            - id: review
                              type: agent
                              agent: claude
                              mode: review_only
                              output: review
                            - id: test
                              type: command
                              command_group: test
                    agents:
                      claude:
                        provider: claude-code
                        command: {fake_claude}
                      codex:
                        provider: codex-cli
                        command: {fake_codex}
                        sandbox: workspace-write
                        approval: never
                    commands:
                      test: []
                    git:
                      strategy: branch
                      branch_prefix: ai/team
                      require_clean_worktree: true
                    limits:
                      max_fix_retries: 1
                      max_changed_files: 5
                      max_diff_lines: 100
                    policies:
                      allow_paths:
                        - app.txt
                      deny_paths:
                        - .env
                        - .team/runs/**
                    """
                ).strip()
                + "\n"
            )
            _git(root, "init")
            _git(root, "config", "user.email", "test@example.com")
            _git(root, "config", "user.name", "Test User")
            _git(root, "add", "team.yml", "fake_codex.py", "fake_claude.py")
            _git(root, "commit", "-m", "init")

            state = run_task(load_config(root), "make app done")

            self.assertEqual(state.status, "NEEDS_HUMAN")
            self.assertIn("could not be determined", str(state.reason))


def _write_executable(path: Path, content: str) -> None:
    path.write_text(content)
    path.chmod(path.stat().st_mode | stat.S_IXUSR)


def _git(root: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=root, check=True, stdout=subprocess.DEVNULL)


if __name__ == "__main__":
    unittest.main()
