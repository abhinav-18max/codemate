from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from codemate.config import ConfigError, init_project, load_config, validate_config


class ConfigTests(unittest.TestCase):
    def test_init_project_creates_docs_and_gitignore_entries(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)

            init_project(root)

            self.assertTrue((root / "docs" / "team.md").exists())
            gitignore = (root / ".gitignore").read_text()
            self.assertIn(".team/runs/", gitignore)
            self.assertIn(".team/lock.json", gitignore)
            config = load_config(root)
            self.assertEqual(config.default_flow_name, "plan_implement_review_test")

    def test_init_project_is_idempotent_without_force(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            init_project(root)
            (root / "team.yml").write_text("custom: true\n")

            created = init_project(root)

            self.assertEqual(created, [])
            self.assertEqual((root / "team.yml").read_text(), "custom: true\n")

    def test_validate_config_rejects_unknown_agent(self) -> None:
        with self.assertRaises(ConfigError):
            validate_config(
                {
                    "workflow": {
                        "default": "main",
                        "flows": {
                            "main": {
                                "steps": [
                                    {
                                        "id": "plan",
                                        "type": "agent",
                                        "agent": "missing",
                                    }
                                ]
                            }
                        },
                    },
                    "agents": {
                        "codex": {
                            "provider": "codex-cli",
                            "command": "codex",
                        }
                    },
                }
            )


if __name__ == "__main__":
    unittest.main()
