from __future__ import annotations

import unittest

from codemate.policy import PolicyError, enforce_path_policy


class PolicyTests(unittest.TestCase):
    def test_allows_matching_paths(self) -> None:
        enforce_path_policy(["src/app.py"], ["src/**"], [".env", "secrets/**"])

    def test_denies_secret_paths(self) -> None:
        with self.assertRaises(PolicyError):
            enforce_path_policy([".env"], ["**"], [".env", "secrets/**"])


if __name__ == "__main__":
    unittest.main()
