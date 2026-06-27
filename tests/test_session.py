from __future__ import annotations

import contextlib
import io
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from codemate import session
from codemate.config import init_project, load_config


def _init_repo(root: Path) -> None:
    subprocess.run(["git", "init"], cwd=root, check=True, stdout=subprocess.DEVNULL)
    init_project(root)


class SessionLoopTests(unittest.TestCase):
    def test_help_then_exit(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _init_repo(root)
            inputs = iter(["/help", "/exit"])

            def fake_input(prompt: str = "") -> str:
                try:
                    return next(inputs)
                except StopIteration:  # pragma: no cover - safety
                    raise EOFError

            buf = io.StringIO()
            with mock.patch("builtins.input", fake_input), contextlib.redirect_stdout(buf):
                rc = session.run_session(root)

            out = buf.getvalue()
            self.assertEqual(rc, 0)
            self.assertIn("interactive session", out)
            self.assertIn("/status", out)
            self.assertIn("bye", out)

    def test_eof_exits_cleanly(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _init_repo(root)

            def fake_input(prompt: str = "") -> str:
                raise EOFError

            with mock.patch("builtins.input", fake_input), contextlib.redirect_stdout(io.StringIO()):
                rc = session.run_session(root)
            self.assertEqual(rc, 0)


class SessionCommandTests(unittest.TestCase):
    def test_flow_switch_and_unknown_command(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _init_repo(root)
            config = load_config(root)
            default = config.default_flow_name

            with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(
                io.StringIO()
            ):
                # Switching to a real flow updates the active flow name.
                stop, flow = session._handle_command(root, config, f"/flow {default}", "other")
                self.assertFalse(stop)
                self.assertEqual(flow, default)

                # An unknown flow is rejected and the active flow is unchanged.
                stop, flow = session._handle_command(root, config, "/flow nope", default)
                self.assertEqual(flow, default)

                # Unknown command does not stop the loop.
                stop, _ = session._handle_command(root, config, "/bogus", default)
                self.assertFalse(stop)

                # /exit stops the loop.
                stop, _ = session._handle_command(root, config, "/exit", default)
                self.assertTrue(stop)


class SessionConfigTests(unittest.TestCase):
    def _silent(self):
        return contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(
            io.StringIO()
        )

    def test_set_step_override_and_unset(self) -> None:
        from codemate.workflow import _agent_config_for_step

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _init_repo(root)
            config = load_config(root)
            flow = config.default_flow_name
            out, err = self._silent()
            with out, err:
                session._handle_command(root, config, "/set review model sonnet", flow)

            review = next(s for s in config.flow_steps(flow) if s.get("id") == "review")
            self.assertEqual(review["model"], "sonnet")
            # The merged config a run would use reflects the override.
            self.assertEqual(_agent_config_for_step(config, review)["model"], "sonnet")

            out, err = self._silent()
            with out, err:
                session._handle_command(root, config, "/unset review model", flow)
            self.assertNotIn("model", review)

    def test_set_agent_level(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _init_repo(root)
            config = load_config(root)
            flow = config.default_flow_name
            out, err = self._silent()
            with out, err:
                session._handle_command(root, config, "/set codex effort low", flow)
            self.assertEqual(config.raw["agents"]["codex"]["effort"], "low")

    def test_invalid_provider_is_rejected_and_reverted(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _init_repo(root)
            config = load_config(root)
            flow = config.default_flow_name
            out, err = self._silent()
            with out, err:
                session._handle_command(root, config, "/set codex provider bogus", flow)
            self.assertEqual(config.raw["agents"]["codex"]["provider"], "codex-cli")

    def test_unknown_key_and_unknown_target(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _init_repo(root)
            config = load_config(root)
            flow = config.default_flow_name
            out, err = self._silent()
            with out, err:
                session._handle_command(root, config, "/set codex banana 1", flow)
                session._handle_command(root, config, "/set nope model sonnet", flow)
            self.assertNotIn("banana", config.raw["agents"]["codex"])


if __name__ == "__main__":
    unittest.main()
