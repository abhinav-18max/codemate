from __future__ import annotations

import unittest

from codemate.workflow import _review_verdict


class ReviewVerdictTests(unittest.TestCase):
    def test_json_pass(self) -> None:
        passed, reason = _review_verdict('{"decision": "pass", "blocking_findings": []}')
        self.assertTrue(passed)
        self.assertIsNone(reason)

    def test_json_fail(self) -> None:
        passed, reason = _review_verdict('{"decision": "fail", "blocking_findings": ["x"]}')
        self.assertFalse(passed)
        self.assertIsNotNone(reason)

    def test_trailing_json_object_wins(self) -> None:
        output = (
            "Here is my review. The code looks reasonable.\n"
            'Final answer:\n{"decision": "pass"}\n'
        )
        passed, _ = _review_verdict(output)
        self.assertTrue(passed)

    def test_marker_line_pass(self) -> None:
        passed, _ = _review_verdict("Looks good to me.\ndecision: PASS\n")
        self.assertTrue(passed)

    def test_marker_line_fail(self) -> None:
        passed, _ = _review_verdict("status: changes_requested\n")
        self.assertFalse(passed)

    def test_empty_output_fails_closed(self) -> None:
        passed, reason = _review_verdict("")
        self.assertFalse(passed)
        self.assertIn("could not be determined", str(reason))

    def test_ambiguous_prose_fails_closed(self) -> None:
        # No explicit decision: must not silently approve.
        passed, reason = _review_verdict("The implementation seems fine overall.")
        self.assertFalse(passed)
        self.assertIn("could not be determined", str(reason))

    def test_prose_mentioning_blocking_without_decision_fails(self) -> None:
        passed, _ = _review_verdict("I found one blocking issue in the parser.")
        self.assertFalse(passed)


if __name__ == "__main__":
    unittest.main()
