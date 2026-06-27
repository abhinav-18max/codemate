from __future__ import annotations

import os
import sys
from typing import TextIO

_CODES = {
    "reset": "\033[0m",
    "dim": "\033[2m",
    "bold": "\033[1m",
    "red": "\033[31m",
    "green": "\033[32m",
    "yellow": "\033[33m",
    "blue": "\033[34m",
    "cyan": "\033[36m",
}


class Reporter:
    """Human-facing progress + streaming output for a run.

    Prints step banners and live, dimmed subprocess output so a run reads like
    an interactive session instead of going silent until the end. All output is
    best-effort and never affects run results.
    """

    def __init__(
        self,
        stream: TextIO | None = None,
        *,
        enabled: bool = True,
        color: bool | None = None,
    ) -> None:
        self.stream = stream or sys.stdout
        self.enabled = enabled
        if color is None:
            color = bool(getattr(self.stream, "isatty", lambda: False)()) and (
                os.environ.get("NO_COLOR") is None
            )
        self.color = color

    def _paint(self, name: str, text: str) -> str:
        if not self.color:
            return text
        return f"{_CODES[name]}{text}{_CODES['reset']}"

    def _write(self, text: str) -> None:
        if not self.enabled:
            return
        self.stream.write(text)
        self.stream.flush()

    def run_header(self, run_id: str, flow: str, task: str) -> None:
        self._write(self._paint("bold", f"codemate · {flow}") + "\n")
        self._write(self._paint("dim", f"run {run_id}") + "\n")
        self._write(f"{self._paint('cyan', 'task')} {task}\n")

    def step(self, label: str, detail: str = "") -> None:
        bullet = self._paint("cyan", "●")
        head = self._paint("bold", label)
        tail = self._paint("dim", f"  ({detail})") if detail else ""
        self._write(f"\n{bullet} {head}{tail}\n")

    def stream_line(self, line: str) -> None:
        for part in line.rstrip("\n").split("\n"):
            self._write(self._paint("dim", f"  │ {part}") + "\n")

    def info(self, message: str) -> None:
        self._write(f"  {message}\n")

    def success(self, message: str) -> None:
        self._write(self._paint("green", f"  ✓ {message}") + "\n")

    def failure(self, message: str) -> None:
        self._write(self._paint("red", f"  ✗ {message}") + "\n")

    def note(self, message: str) -> None:
        self._write(self._paint("yellow", f"  • {message}") + "\n")
