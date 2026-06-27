from __future__ import annotations

import atexit
import sys
from pathlib import Path

from .config import TeamConfig, load_config
from .git_tools import diff, ensure_repo
from .reporter import Reporter
from .workflow import WorkflowError, run_task

PROMPT = "\ncodemate› "

HELP = """commands:
  /help              show this help
  /status            show the latest run status
  /diff              show the current git diff
  /logs [step]       show logs for the latest run (optionally one step)
  /accept            keep changes in the working tree
  /accept commit msg commit the changes with a message
  /reset             revert files changed by the latest run
  /flow [name]       show or switch the active flow
  /clear             clear the screen
  /exit              quit the session

Type anything else and it runs as a task through the active flow."""


def run_session(
    root: Path,
    *,
    flow: str | None = None,
    quiet: bool = False,
    no_color: bool = False,
) -> int:
    config = load_config(root)
    ensure_repo(root)
    reporter = Reporter(enabled=not quiet, color=False if no_color else None)
    flow_name = flow or config.default_flow_name
    _enable_readline(root)
    _print_banner(root, flow_name)

    while True:
        try:
            line = input(PROMPT)
        except EOFError:
            print()
            return 0
        except KeyboardInterrupt:
            print("  (use /exit to quit)")
            continue
        line = line.strip()
        if not line:
            continue
        if line.startswith("/"):
            stop, flow_name = _handle_command(root, config, line, flow_name)
            if stop:
                return 0
            continue
        _run_one(config, line, flow_name, reporter)


def _run_one(config: TeamConfig, task: str, flow_name: str, reporter: Reporter) -> None:
    from .cli import _format_state

    try:
        state = run_task(config, task, flow_name, reporter=reporter)
        print()
        print(_format_state(state))
    except WorkflowError as exc:
        message = str(exc)
        # In-flow failures already streamed a failure line via the reporter; only
        # the pre-flight clean-worktree guard needs surfacing here.
        if "clean" in message.lower():
            reporter.failure(message)
            reporter.note('next: /accept commit "msg" or /reset, then retry')
    except Exception as exc:  # pragma: no cover - defensive
        print(f"codemate: error: {exc}", file=sys.stderr)


def _handle_command(
    root: Path, config: TeamConfig, line: str, flow_name: str
) -> tuple[bool, str]:
    from . import cli

    parts = line[1:].split()
    cmd = parts[0].lower() if parts else ""
    rest = parts[1:]

    if cmd in {"exit", "quit", "q"}:
        print("bye")
        return True, flow_name
    if cmd in {"help", "h", "?"}:
        print(HELP)
    elif cmd == "status":
        try:
            print(cli._format_state(cli._load_state(root, None)))
        except Exception as exc:
            print(f"codemate: error: {exc}", file=sys.stderr)
    elif cmd == "diff":
        print(diff(root), end="")
    elif cmd == "logs":
        cli._logs(root, None, rest[0] if rest else None)
    elif cmd == "accept":
        commit = bool(rest) and rest[0] == "commit"
        message = " ".join(rest[1:]) if commit and len(rest) > 1 else None
        cli._accept(root, commit, message)
    elif cmd == "reset":
        cli._reset(root, None)
    elif cmd == "flow":
        if rest:
            try:
                config.flow_steps(rest[0])
                flow_name = rest[0]
                print(f"flow set to {flow_name}")
            except Exception as exc:
                print(f"codemate: error: {exc}", file=sys.stderr)
        else:
            print(f"flow: {flow_name}")
    elif cmd == "clear":
        print("\033[2J\033[H", end="")
    else:
        print(f"unknown command: /{cmd} (try /help)")
    return False, flow_name


def _print_banner(root: Path, flow_name: str) -> None:
    print("codemate · interactive session")
    print(f"repo: {root.name}   flow: {flow_name}")
    print("type a task and press enter · /help for commands · /exit to quit")


def _enable_readline(root: Path) -> None:
    try:
        import readline
    except ImportError:  # pragma: no cover - platform dependent
        return
    histfile = root / ".team" / "history"
    try:
        histfile.parent.mkdir(parents=True, exist_ok=True)
        if histfile.exists():
            readline.read_history_file(str(histfile))
    except OSError:  # pragma: no cover - best effort
        pass

    def _save() -> None:
        try:
            readline.set_history_length(1000)
            readline.write_history_file(str(histfile))
        except OSError:  # pragma: no cover - best effort
            pass

    atexit.register(_save)
