from __future__ import annotations

import subprocess
import threading
from collections.abc import Callable
from pathlib import Path


def run_command_group(
    root: Path,
    commands: list[str],
    log_path: Path,
    timeout_seconds: int = 900,
    on_output: Callable[[str], None] | None = None,
) -> tuple[bool, str | None, int]:
    if not commands:
        log_path.write_text("No commands configured.\n")
        if on_output is not None:
            on_output("No commands configured.\n")
        return True, None, 0

    with log_path.open("w") as log:
        for command in commands:
            header = f"$ {command}\n"
            log.write(header)
            log.flush()
            if on_output is not None:
                on_output(header)
            exit_code = _stream_command(root, command, log, timeout_seconds, on_output)
            footer = f"\n[exit_code={exit_code}]\n"
            log.write(footer)
            if on_output is not None:
                on_output(footer)
            if exit_code != 0:
                return False, command, exit_code
    return True, None, 0


def _stream_command(
    root: Path,
    command: str,
    log,
    timeout_seconds: int,
    on_output: Callable[[str], None] | None,
) -> int:
    proc = subprocess.Popen(
        command,
        cwd=root,
        shell=True,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        bufsize=1,
    )
    timed_out = False

    def _kill() -> None:
        nonlocal timed_out
        timed_out = True
        proc.kill()

    timer = threading.Timer(timeout_seconds, _kill)
    timer.start()
    try:
        with proc:
            assert proc.stdout is not None
            for line in proc.stdout:
                log.write(line)
                if on_output is not None:
                    on_output(line)
            proc.wait()
            if timed_out:
                message = f"\n[timeout after {timeout_seconds} seconds]\n"
                log.write(message)
                if on_output is not None:
                    on_output(message)
    finally:
        timer.cancel()
    return 124 if timed_out else proc.returncode
