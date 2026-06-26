from __future__ import annotations

import subprocess
from pathlib import Path


def run_command_group(
    root: Path, commands: list[str], log_path: Path, timeout_seconds: int = 900
) -> tuple[bool, str | None, int]:
    if not commands:
        log_path.write_text("No commands configured.\n")
        return True, None, 0

    with log_path.open("w") as log:
        for command in commands:
            log.write(f"$ {command}\n")
            log.flush()
            try:
                result = subprocess.run(
                    command,
                    cwd=root,
                    shell=True,
                    text=True,
                    stdout=log,
                    stderr=subprocess.STDOUT,
                    timeout=timeout_seconds,
                    check=False,
                )
                exit_code = result.returncode
            except subprocess.TimeoutExpired:
                exit_code = 124
                log.write(f"\n[timeout after {timeout_seconds} seconds]\n")
            log.write(f"\n[exit_code={exit_code}]\n")
            if exit_code != 0:
                return False, command, exit_code
    return True, None, 0
