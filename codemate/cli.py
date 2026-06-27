from __future__ import annotations

import argparse
import shutil
import shlex
import subprocess
import sys
from pathlib import Path

from . import __version__, setup
from .artifacts import RunState, latest_run_dir
from .config import GITIGNORE_PATTERNS, init_project, load_config
from .git_tools import add_and_commit, changed_files, diff, ensure_repo, restore_paths
from .reporter import Reporter
from .workflow import run_task


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="codemate",
        description="Run codemate with no command to start an interactive session.",
    )
    parser.add_argument("--root", default=".", help="Project root")
    subparsers = parser.add_subparsers(dest="command")

    chat_parser = subparsers.add_parser("chat", help="Start an interactive session (default)")
    chat_parser.add_argument("--flow")
    chat_parser.add_argument("--quiet", action="store_true")
    chat_parser.add_argument("--no-color", action="store_true")

    init_parser = subparsers.add_parser("init", help="Create team.yml and .team files")
    init_parser.add_argument("--force", action="store_true")
    init_parser.add_argument(
        "--skip-setup", action="store_true", help="Skip the agent install/login check"
    )

    setup_parser = subparsers.add_parser(
        "setup", help="Check that agent CLIs are installed and logged in"
    )
    setup_parser.add_argument(
        "--yes", action="store_true", help="Run logins without prompting first"
    )

    doctor_parser = subparsers.add_parser("doctor", help="Check local harness dependencies")
    doctor_parser.add_argument("--flow")

    clean_parser = subparsers.add_parser("clean", help="Delete codemate run artifacts")
    clean_parser.add_argument(
        "--all",
        dest="all_files",
        action="store_true",
        help="Delete all codemate files (team.yml, .team/, generated docs, gitignore entries)",
    )
    clean_parser.add_argument("--yes", action="store_true", help="Skip the confirmation prompt")

    update_parser = subparsers.add_parser("update", help="Upgrade codemate to the latest version")
    update_parser.add_argument(
        "--check", action="store_true", help="Only report installed vs latest version"
    )

    run_parser = subparsers.add_parser("run", help="Run a task through the configured flow")
    run_parser.add_argument("task", nargs="?")
    run_parser.add_argument("--file")
    run_parser.add_argument("--flow")
    run_parser.add_argument(
        "--quiet", action="store_true", help="Suppress live progress and streamed output"
    )
    run_parser.add_argument(
        "--no-color", action="store_true", help="Disable ANSI color in live output"
    )

    status_parser = subparsers.add_parser("status", help="Show run status")
    status_parser.add_argument("--run-id")

    logs_parser = subparsers.add_parser("logs", help="Show run logs")
    logs_parser.add_argument("--run-id")
    logs_parser.add_argument("--step")

    subparsers.add_parser("diff", help="Show current git diff")

    accept_parser = subparsers.add_parser("accept", help="Accept current run changes")
    accept_parser.add_argument("--commit", action="store_true")
    accept_parser.add_argument("--message", default=None)

    reset_parser = subparsers.add_parser("reset", help="Reset files changed by latest run")
    reset_parser.add_argument("--run-id")

    args = parser.parse_args(argv)
    root = Path(args.root).resolve()

    try:
        if args.command is None or args.command == "chat":
            from .session import run_session

            return run_session(
                root,
                flow=getattr(args, "flow", None),
                quiet=getattr(args, "quiet", False),
                no_color=getattr(args, "no_color", False),
            )
        if args.command == "init":
            return _init(root, args.force, args.skip_setup)
        if args.command == "setup":
            return _setup(root, args.yes)
        if args.command == "doctor":
            return _doctor(root, args.flow)
        if args.command == "clean":
            return _clean(root, args.all_files, args.yes)
        if args.command == "update":
            return _update(args.check)
        if args.command == "run":
            task = _read_task(args)
            config = load_config(root)
            reporter = Reporter(
                enabled=not args.quiet,
                color=False if args.no_color else None,
            )
            state = run_task(config, task, args.flow, reporter=reporter)
            print()
            print(_format_state(state))
            print(f"Run artifacts: .team/runs/{state.run_id}")
            return 0 if state.status == "DONE" else 2
        if args.command == "status":
            state = _load_state(root, args.run_id)
            print(_format_state(state))
            return 0
        if args.command == "logs":
            return _logs(root, args.run_id, args.step)
        if args.command == "diff":
            ensure_repo(root)
            print(diff(root), end="")
            return 0
        if args.command == "accept":
            return _accept(root, args.commit, args.message)
        if args.command == "reset":
            return _reset(root, args.run_id)
    except Exception as exc:
        print(f"codemate: error: {exc}", file=sys.stderr)
        return 1
    return 1


def _init(root: Path, force: bool, skip_setup: bool = False) -> int:
    created = init_project(root, force=force)
    if not created:
        print("Team configuration is up to date.")
    else:
        print("Created team configuration:")
        for path in created:
            print(f"- {path.relative_to(root)}")
    if not skip_setup:
        try:
            print()
            setup.run_setup(load_config(root))
        except Exception as exc:  # pragma: no cover - setup is best-effort
            print(f"codemate: setup check skipped: {exc}", file=sys.stderr)
    return 0


def _setup(root: Path, assume_yes: bool) -> int:
    config = load_config(root)
    return 0 if setup.run_setup(config, assume_yes=assume_yes) else 1


def _clean(root: Path, remove_all: bool, assume_yes: bool) -> int:
    team_dir = root / ".team"
    if remove_all:
        targets = [
            path
            for path in (root / "team.yml", team_dir, root / "docs" / "team.md")
            if path.exists()
        ]
    else:
        targets = [
            path
            for path in (team_dir / "runs", team_dir / "lock.json", team_dir / "history")
            if path.exists()
        ]
    if not targets:
        print("Nothing to clean.")
        return 0

    print("Will delete:")
    for path in targets:
        print(f"  {path.relative_to(root)}")
    if remove_all:
        print("  (and codemate entries in .gitignore)")
    if not assume_yes:
        try:
            answer = input("Proceed? [y/N] ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            print()
            return 1
        if answer not in {"y", "yes"}:
            print("Aborted.")
            return 1

    for path in targets:
        if path.is_dir():
            shutil.rmtree(path)
        else:
            path.unlink()
    if remove_all:
        _strip_gitignore(root)
        docs = root / "docs"
        if docs.is_dir() and not any(docs.iterdir()):
            docs.rmdir()
    print("Cleaned.")
    return 0


def _strip_gitignore(root: Path) -> None:
    gitignore = root / ".gitignore"
    if not gitignore.exists():
        return
    kept = [line for line in gitignore.read_text().splitlines() if line.strip() not in GITIGNORE_PATTERNS]
    gitignore.write_text("\n".join(kept) + ("\n" if kept else ""))


def _update(check_only: bool) -> int:
    if check_only:
        latest = _pypi_latest("codemate-team")
        print(f"installed: {__version__}")
        print(f"latest:    {latest or 'unknown'}")
        if latest is None:
            pass
        elif _version_tuple(latest) > _version_tuple(__version__):
            print("run `codemate update` to upgrade")
        elif latest == __version__:
            print("up to date")
        else:
            print("(local build is ahead of the published release)")
        return 0
    command = _upgrade_command()
    print(f"$ {' '.join(command)}")
    try:
        returncode = subprocess.run(command).returncode
    except FileNotFoundError:
        returncode = 1
    if returncode != 0:
        print("Update failed. Try one of:", file=sys.stderr)
        print("  uv tool upgrade codemate-team", file=sys.stderr)
        print("  pipx upgrade codemate-team", file=sys.stderr)
        print("  pip install --upgrade codemate-team", file=sys.stderr)
        return 1
    print("Updated. Tip: run `codemate init --force` to refresh project templates.")
    return 0


def _upgrade_command() -> list[str]:
    location = str(Path(__file__).resolve())
    if "/uv/tools/" in location:
        return ["uv", "tool", "upgrade", "codemate-team"]
    if "pipx" in location:
        return ["pipx", "upgrade", "codemate-team"]
    return [sys.executable, "-m", "pip", "install", "--upgrade", "codemate-team"]


def _version_tuple(version: str) -> tuple[int, ...]:
    parts: list[int] = []
    for piece in version.split("."):
        digits = "".join(ch for ch in piece if ch.isdigit())
        parts.append(int(digits) if digits else 0)
    return tuple(parts)


def _pypi_latest(package: str) -> str | None:
    import json
    import urllib.request

    try:
        with urllib.request.urlopen(f"https://pypi.org/pypi/{package}/json", timeout=10) as response:
            return json.load(response)["info"]["version"]
    except Exception:
        return None


def _doctor(root: Path, flow: str | None) -> int:
    config = load_config(root)
    ensure_repo(root)
    missing: list[str] = []
    warnings: list[str] = []
    seen: set[str] = set()
    for step in config.flow_steps(flow):
        if step.get("type") != "agent":
            if step.get("type") == "command":
                group = str(step.get("command_group"))
                commands = config.command_group(group)
                if not commands:
                    warnings.append(f"command group `{group}` is empty")
                for command in commands:
                    executable = _first_command_token(command)
                    if executable and shutil.which(executable) is None:
                        missing.append(f"command group `{group}`: {executable}")
            continue
        agent_name = str(step.get("agent"))
        if agent_name in seen:
            continue
        seen.add(agent_name)
        command = str(config.agent(agent_name).get("command", agent_name))
        if shutil.which(command) is None:
            missing.append(f"{agent_name}: {command}")
    if missing:
        print("Missing agent commands:")
        for item in missing:
            print(f"- {item}")
        return 1
    if warnings:
        print("Doctor passed with warnings:")
        for item in warnings:
            print(f"- {item}")
        return 0
    print("Doctor passed")
    return 0


def _read_task(args: argparse.Namespace) -> str:
    if args.file:
        return Path(args.file).read_text().strip()
    if args.task:
        return args.task.strip()
    raise ValueError("Provide a task string or --file")


def _load_state(root: Path, run_id: str | None) -> RunState:
    run_dir = root / ".team" / "runs" / run_id if run_id else latest_run_dir(root)
    return RunState.from_path(run_dir / "state.json")


def _logs(root: Path, run_id: str | None, step: str | None) -> int:
    run_dir = root / ".team" / "runs" / run_id if run_id else latest_run_dir(root)
    state = RunState.from_path(run_dir / "state.json")
    matches = state.steps
    if step:
        matches = [item for item in matches if item.get("id") == step]
    if not matches:
        print("No matching logs")
        return 1
    for item in matches:
        path_value = item.get("raw_log") or item.get("log") or item.get("output")
        if not path_value:
            continue
        path = root / str(path_value)
        if not path.exists():
            print(f"Missing log artifact: {path.relative_to(root)}")
            continue
        print(f"==> {path.relative_to(root)} <==")
        content = path.read_text(errors="replace")
        print(content, end="")
        if not content.endswith("\n"):
            print()
    return 0


def _accept(root: Path, commit: bool, message: str | None) -> int:
    state = _load_state(root, None)
    if not commit:
        print(f"Run {state.run_id} accepted. Changes remain in the working tree.")
        return 0
    paths = [path for path in changed_files(root) if not path.startswith(".team/")]
    if not paths:
        print(f"Run {state.run_id} has no source changes to commit.")
        return 0
    add_and_commit(root, paths, message or f"team: accept run {state.run_id}")
    print(f"Committed run {state.run_id}")
    return 0


def _reset(root: Path, run_id: str | None) -> int:
    state = _load_state(root, run_id)
    paths = [path for path in state.changed_files if not path.startswith(".team/")]
    if not paths:
        print(f"Run {state.run_id} recorded no source files to reset.")
        return 0
    restore_paths(root, paths)
    for path in paths:
        full_path = root / path
        if full_path.exists() and path in changed_files(root):
            try:
                full_path.unlink()
            except IsADirectoryError:
                pass
    print(f"Reset files recorded for run {state.run_id}")
    return 0


def _first_command_token(command: str) -> str | None:
    try:
        parts = shlex.split(command)
    except ValueError:
        return None
    if not parts:
        return None
    if any(token in parts[0] for token in ("=", "/", "\\")):
        return None
    return parts[0]


def _format_state(state: RunState) -> str:
    changed = ", ".join(state.changed_files) if state.changed_files else "none"
    reason = f"\nReason: {state.reason}" if state.reason else ""
    return (
        f"Run: {state.run_id}\n"
        f"Flow: {state.flow}\n"
        f"Status: {state.status}\n"
        f"Branch: {state.branch}\n"
        f"Changed files: {changed}"
        f"{reason}"
    )


if __name__ == "__main__":
    raise SystemExit(main())
