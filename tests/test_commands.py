from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from codemate.commands import run_command_group


class CommandRunnerTests(unittest.TestCase):
    def test_command_timeout_is_recorded_as_failure(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            log_path = root / "test.log"

            ok, failed_command, exit_code = run_command_group(
                root,
                ["python -c 'import time; time.sleep(1)'"],
                log_path,
                timeout_seconds=0,
            )

            self.assertFalse(ok)
            self.assertIsNotNone(failed_command)
            self.assertEqual(exit_code, 124)
            self.assertIn("timeout", log_path.read_text())


if __name__ == "__main__":
    unittest.main()
