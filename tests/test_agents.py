from __future__ import annotations

import unittest
from pathlib import Path

from codemate.agents import AgentRunInput, claude_args, codex_args


def _input(config: dict, *, mode: str = "write") -> AgentRunInput:
    return AgentRunInput(
        run_id="r",
        step_id="implement",
        cwd=Path("/repo"),
        prompt="do the thing",
        mode=mode,
        expected_output="implementation",
        output_path=Path("/repo/out.md"),
        raw_log_path=Path("/repo/raw.log"),
        schema_path=None,
        config=config,
    )


class CodexArgsTests(unittest.TestCase):
    def test_model_and_effort_are_passed(self) -> None:
        args = codex_args(
            _input({"command": "codex", "model": "gpt-5-codex", "reasoning_effort": "high"})
        )
        self.assertIn("-m", args)
        self.assertEqual(args[args.index("-m") + 1], "gpt-5-codex")
        self.assertIn('model_reasoning_effort="high"', args)
        self.assertEqual(args[-1], "do the thing")

    def test_effort_alias_and_extra_args(self) -> None:
        args = codex_args(
            _input({"command": "codex", "effort": "low", "extra_args": ["-c", "x=1"]})
        )
        self.assertIn('model_reasoning_effort="low"', args)
        self.assertIn("x=1", args)

    def test_no_model_means_no_flag(self) -> None:
        args = codex_args(_input({"command": "codex"}))
        self.assertNotIn("-m", args)
        self.assertFalse(any("model_reasoning_effort" in a for a in args))


class ClaudeArgsTests(unittest.TestCase):
    def test_model_and_effort_map_to_flags(self) -> None:
        args = claude_args(
            _input({"command": "claude", "model": "opus", "effort": "max"}, mode="read_only")
        )
        self.assertEqual(args[args.index("--model") + 1], "opus")
        self.assertEqual(args[args.index("--effort") + 1], "max")
        # read_only maps to the plan permission mode.
        self.assertEqual(args[args.index("--permission-mode") + 1], "plan")

    def test_extra_args_and_output_format(self) -> None:
        args = claude_args(
            _input({"command": "claude", "output_format": "json", "extra_args": "--verbose"})
        )
        self.assertEqual(args[args.index("--output-format") + 1], "json")
        self.assertIn("--verbose", args)

    def test_defaults_have_no_model_flag(self) -> None:
        args = claude_args(_input({"command": "claude"}))
        self.assertNotIn("--model", args)
        self.assertNotIn("--effort", args)


if __name__ == "__main__":
    unittest.main()
