from __future__ import annotations

import json
import shutil
import subprocess
import threading
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class AgentRunInput:
    run_id: str
    step_id: str
    cwd: Path
    prompt: str
    mode: str
    expected_output: str
    output_path: Path
    raw_log_path: Path
    schema_path: Path | None
    config: dict[str, Any]
    on_output: Callable[[str], None] | None = None


@dataclass(frozen=True)
class AgentRunResult:
    ok: bool
    output_path: Path
    raw_log_path: Path
    exit_code: int


class AgentAdapter:
    def run(self, input: AgentRunInput) -> AgentRunResult:
        raise NotImplementedError


class CodexCliAdapter(AgentAdapter):
    def run(self, input: AgentRunInput) -> AgentRunResult:
        command = str(input.config.get("command", "codex"))
        _require_executable(command)
        args = [
            command,
            "exec",
            "--cd",
            str(input.cwd),
            "--sandbox",
            str(input.config.get("sandbox", "workspace-write")),
            "--output-last-message",
            str(input.output_path),
        ]
        # `codex exec` is non-interactive; approvals are governed by config, not a
        # flag. Keep an opt-in override for environments that need it explicitly.
        approval_policy = input.config.get("approval_policy")
        if approval_policy:
            args.extend(["-c", f"approval_policy={json.dumps(str(approval_policy))}"])
        if input.schema_path and input.schema_path.exists():
            args.extend(["--output-schema", str(input.schema_path)])
        args.append(input.prompt)
        return _run_process(args, input)


class ClaudeCodeAdapter(AgentAdapter):
    def run(self, input: AgentRunInput) -> AgentRunResult:
        command = str(input.config.get("command", "claude"))
        _require_executable(command)
        permission_mode = _claude_permission_mode(input.mode, input.config)
        output_format = str(input.config.get("output_format", "text"))
        args = [command, "-p", input.prompt, "--permission-mode", permission_mode]
        if output_format != "text":
            args.extend(["--output-format", output_format])
        result = _run_process(args, input)
        # Claude Code streams its final answer to stdout (captured in the raw log)
        # rather than to a dedicated output file, so derive the output ourselves.
        if not input.output_path.read_text(errors="replace").strip():
            raw = input.raw_log_path.read_text(errors="replace")
            input.output_path.write_text(_extract_claude_message(raw, output_format))
        return result


def adapter_for(config: dict[str, Any]) -> AgentAdapter:
    provider = str(config.get("provider", "")).lower()
    if provider == "codex-cli":
        return CodexCliAdapter()
    if provider == "claude-code":
        return ClaudeCodeAdapter()
    raise ValueError(f"Unsupported agent provider: {provider}")


def _extract_claude_message(raw: str, output_format: str) -> str:
    """Pull the assistant's final message out of captured Claude Code output.

    With `--output-format json` the CLI emits a result envelope; extract its
    `result` field. Anything else (including malformed JSON) falls back to the
    raw captured text so no output is ever silently dropped.
    """
    if output_format == "json":
        try:
            data = json.loads(raw.strip() or "{}")
        except json.JSONDecodeError:
            return raw
        if isinstance(data, dict) and isinstance(data.get("result"), str):
            return data["result"]
    return raw


def _claude_permission_mode(mode: str, config: dict[str, Any]) -> str:
    if mode in {"read_only", "review_only"}:
        return "plan"
    if mode == "write":
        return str(config.get("write_permission_mode", "acceptEdits"))
    return str(config.get("default_mode", "plan"))


def _run_process(args: list[str], input: AgentRunInput) -> AgentRunResult:
    timeout = int(input.config.get("timeout_seconds", 900))
    exit_code = stream_subprocess(
        args, input.cwd, input.raw_log_path, timeout, input.on_output
    )
    if not input.output_path.exists():
        input.output_path.write_text("")
    return AgentRunResult(
        ok=exit_code == 0,
        output_path=input.output_path,
        raw_log_path=input.raw_log_path,
        exit_code=exit_code,
    )


def stream_subprocess(
    args: list[str],
    cwd: Path,
    log_path: Path,
    timeout: int,
    on_output: Callable[[str], None] | None = None,
) -> int:
    """Run a process, teeing its combined output to a log file and an optional
    live sink. Returns the exit code (124 on timeout)."""
    proc = subprocess.Popen(
        args,
        cwd=cwd,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        bufsize=1,
    )
    timed_out = False

    def _kill_on_timeout() -> None:
        nonlocal timed_out
        timed_out = True
        proc.kill()

    timer = threading.Timer(timeout, _kill_on_timeout)
    timer.start()
    try:
        with proc, log_path.open("w") as log:
            assert proc.stdout is not None
            for line in proc.stdout:
                log.write(line)
                if on_output is not None:
                    on_output(line)
            proc.wait()
            if timed_out:
                log.write(f"\n[timeout after {timeout} seconds]\n")
                if on_output is not None:
                    on_output(f"[timeout after {timeout} seconds]\n")
    finally:
        timer.cancel()
    return 124 if timed_out else proc.returncode


def _require_executable(command: str) -> None:
    if shutil.which(command) is None:
        raise FileNotFoundError(f"Required agent command not found: {command}")
