from __future__ import annotations

import shutil
import subprocess
import sys
from dataclasses import dataclass
from typing import TextIO

from .config import TeamConfig

PROVIDER_META = {
    "claude-code": {
        "label": "Claude Code",
        "install_hint": "npm install -g @anthropic-ai/claude-code",
        "status": ["auth", "status"],
        "login": ["auth", "login"],
    },
    "codex-cli": {
        "label": "Codex CLI",
        "install_hint": "npm install -g @openai/codex",
        "status": ["login", "status"],
        "login": ["login"],
    },
}


@dataclass
class AgentStatus:
    name: str
    provider: str
    command: str
    installed: bool
    logged_in: bool | None  # None when login could not be determined


def agent_statuses(config: TeamConfig) -> list[AgentStatus]:
    seen: set[tuple[str, str]] = set()
    out: list[AgentStatus] = []
    for name, agent in config.raw.get("agents", {}).items():
        if not isinstance(agent, dict):
            continue
        provider = str(agent.get("provider", ""))
        command = str(agent.get("command", name))
        key = (provider, command)
        if key in seen:
            continue
        seen.add(key)
        installed = shutil.which(command) is not None
        logged_in = _check_login(provider, command) if installed else None
        out.append(AgentStatus(name, provider, command, installed, logged_in))
    return out


def _check_login(provider: str, command: str) -> bool | None:
    meta = PROVIDER_META.get(provider)
    if not meta:
        return None
    try:
        result = subprocess.run(
            [command, *meta["status"]],
            capture_output=True,
            text=True,
            timeout=20,
        )
        return result.returncode == 0
    except Exception:
        return None


def run_setup(config: TeamConfig, *, assume_yes: bool = False, stream: TextIO | None = None) -> bool:
    out = stream or sys.stdout
    statuses = agent_statuses(config)
    if not statuses:
        return True

    print("Checking agent CLIs:", file=out)
    ready = True
    for status in statuses:
        meta = PROVIDER_META.get(status.provider, {})
        label = meta.get("label", status.provider or status.name)
        if not status.installed:
            ready = False
            print(f"  ✗ {label} ({status.command}) is not installed", file=out)
            hint = meta.get("install_hint")
            if hint:
                print(f"      install: {hint}", file=out)
            continue
        if status.logged_in is True:
            print(f"  ✓ {label} — installed and logged in", file=out)
            continue
        if status.logged_in is None:
            print(f"  ? {label} — installed (login status unknown)", file=out)
            continue
        # Installed but not logged in.
        print(f"  ! {label} — installed but not logged in", file=out)
        if _attempt_login(status, meta, assume_yes, out) and _check_login(
            status.provider, status.command
        ):
            print(f"  ✓ {label} — logged in", file=out)
        else:
            ready = False
    return ready


def _attempt_login(status: AgentStatus, meta: dict, assume_yes: bool, out: TextIO) -> bool:
    login = meta.get("login")
    if not login:
        return False
    command = [status.command, *login]
    if not sys.stdin.isatty():
        print(f"      log in with: {' '.join(command)}", file=out)
        return False
    if not assume_yes:
        try:
            answer = input(f"      Log in to {meta.get('label')} now? [Y/n] ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            print(file=out)
            return False
        if answer in {"n", "no"}:
            print(f"      later: {' '.join(command)}", file=out)
            return False
    try:
        subprocess.run(command, check=False)
        return True
    except Exception as exc:  # pragma: no cover - depends on external CLI
        print(f"      login failed: {exc}", file=out)
        return False
