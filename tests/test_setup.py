from __future__ import annotations

import io
import unittest
from pathlib import Path

from codemate import setup
from codemate.config import TeamConfig


def _config(agents: dict) -> TeamConfig:
    return TeamConfig(root=Path("."), raw={"agents": agents})


class SetupTests(unittest.TestCase):
    def test_missing_command_is_not_installed(self) -> None:
        config = _config(
            {"codex": {"provider": "codex-cli", "command": "codemate-no-such-binary-xyz"}}
        )
        statuses = setup.agent_statuses(config)
        self.assertEqual(len(statuses), 1)
        self.assertFalse(statuses[0].installed)
        self.assertIsNone(statuses[0].logged_in)

    def test_run_setup_reports_install_hint_and_returns_false(self) -> None:
        config = _config(
            {"codex": {"provider": "codex-cli", "command": "codemate-no-such-binary-xyz"}}
        )
        buf = io.StringIO()
        ready = setup.run_setup(config, stream=buf)
        self.assertFalse(ready)
        out = buf.getvalue()
        self.assertIn("not installed", out)
        self.assertIn("npm install -g @openai/codex", out)

    def test_duplicate_commands_are_deduped(self) -> None:
        config = _config(
            {
                "a": {"provider": "claude-code", "command": "codemate-missing-xyz"},
                "b": {"provider": "claude-code", "command": "codemate-missing-xyz"},
            }
        )
        self.assertEqual(len(setup.agent_statuses(config)), 1)


if __name__ == "__main__":
    unittest.main()
