from __future__ import annotations

import shutil
import subprocess
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
            "--ask-for-approval",
            str(input.config.get("approval", "never")),
            "--output-last-message",
            str(input.output_path),
        ]
        if input.schema_path and input.schema_path.exists():
            args.extend(["--output-schema", str(input.schema_path)])
        args.append(input.prompt)
        return _run_process(args, input)


class ClaudeCodeAdapter(AgentAdapter):
    def run(self, input: AgentRunInput) -> AgentRunResult:
        command = str(input.config.get("command", "claude"))
        _require_executable(command)
        permission_mode = _claude_permission_mode(input.mode, input.config)
        args = [command, "-p", input.prompt, "--permission-mode", permission_mode]
        result = _run_process(args, input)
        if not input.output_path.read_text(errors="replace").strip():
            input.output_path.write_text(input.raw_log_path.read_text(errors="replace"))
        return result


def adapter_for(config: dict[str, Any]) -> AgentAdapter:
    provider = str(config.get("provider", "")).lower()
    if provider == "codex-cli":
        return CodexCliAdapter()
    if provider == "claude-code":
        return ClaudeCodeAdapter()
    raise ValueError(f"Unsupported agent provider: {provider}")


def _claude_permission_mode(mode: str, config: dict[str, Any]) -> str:
    if mode in {"read_only", "review_only"}:
        return "plan"
    if mode == "write":
        return str(config.get("write_permission_mode", "acceptEdits"))
    return str(config.get("default_mode", "plan"))


def _run_process(args: list[str], input: AgentRunInput) -> AgentRunResult:
    timeout = int(input.config.get("timeout_seconds", 900))
    with input.raw_log_path.open("w") as raw_log:
        try:
            result = subprocess.run(
                args,
                cwd=input.cwd,
                text=True,
                stdout=raw_log,
                stderr=subprocess.STDOUT,
                timeout=timeout,
                check=False,
            )
            exit_code = result.returncode
        except subprocess.TimeoutExpired:
            raw_log.write(f"\n[timeout after {timeout} seconds]\n")
            exit_code = 124
    if not input.output_path.exists():
        input.output_path.write_text("")
    return AgentRunResult(
        ok=exit_code == 0,
        output_path=input.output_path,
        raw_log_path=input.raw_log_path,
        exit_code=exit_code,
    )


def _require_executable(command: str) -> None:
    if shutil.which(command) is None:
        raise FileNotFoundError(f"Required agent command not found: {command}")
