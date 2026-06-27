from __future__ import annotations

import io
import unittest

from codemate.reporter import Reporter


class ReporterTests(unittest.TestCase):
    def test_enabled_reporter_writes_banner_and_streams(self) -> None:
        buf = io.StringIO()
        reporter = Reporter(buf, enabled=True, color=False)
        reporter.step("implement", "codex · write")
        reporter.stream_line("changed app.py\n")
        reporter.success("done")
        out = buf.getvalue()
        self.assertIn("● implement", out)
        self.assertIn("(codex · write)", out)
        self.assertIn("│ changed app.py", out)
        self.assertIn("✓ done", out)

    def test_disabled_reporter_is_silent(self) -> None:
        buf = io.StringIO()
        reporter = Reporter(buf, enabled=False, color=False)
        reporter.step("plan")
        reporter.stream_line("noise\n")
        reporter.success("done")
        self.assertEqual(buf.getvalue(), "")

    def test_color_off_emits_no_ansi(self) -> None:
        buf = io.StringIO()
        reporter = Reporter(buf, enabled=True, color=False)
        reporter.failure("boom")
        self.assertNotIn("\033[", buf.getvalue())


if __name__ == "__main__":
    unittest.main()
