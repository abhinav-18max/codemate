from __future__ import annotations

import unittest

from codemate.config import DEFAULT_TEAM_YML
from codemate.yaml_lite import loads_yaml


class YamlLiteTests(unittest.TestCase):
    def test_parses_default_team_config(self) -> None:
        data = loads_yaml(DEFAULT_TEAM_YML)

        self.assertEqual(data["version"], 1)
        self.assertEqual(data["workflow"]["default"], "plan_implement_review_test")
        steps = data["workflow"]["flows"]["plan_implement_review_test"]["steps"]
        self.assertEqual([step["id"] for step in steps], [
            "plan",
            "implement",
            "review",
            "test",
            "fix_if_needed",
        ])
        self.assertEqual(data["commands"]["test"], [])


if __name__ == "__main__":
    unittest.main()
