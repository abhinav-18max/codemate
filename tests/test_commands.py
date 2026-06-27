from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from codemate.commands import run_command_group


class CommandRunnerTests(unittest.TestCase):
    def test_output_streams_to_sink_and_log(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            log_path = root / "test.log"
            streamed: list[str] = []

            ok, failed_command, exit_code = run_command_group(
                root,
                ["printf 'line-one\\nline-two\\n'"],
                log_path,
                on_output=streamed.append,
            )

            self.assertTrue(ok)
            self.assertIsNone(failed_command)
            self.assertEqual(exit_code, 0)
            joined = "".join(streamed)
            # The live sink saw both the command header and its output...
            self.assertIn("$ printf", joined)
            self.assertIn("line-one", joined)
            self.assertIn("line-two", joined)
            # ...and the same content was persisted to the log file.
            self.assertIn("line-one", log_path.read_text())

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
