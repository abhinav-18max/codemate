from __future__ import annotations

import argparse
import shutil
import shlex
import sys
from pathlib import Path

from .artifacts import RunState, latest_run_dir
from .config import init_project, load_config
from .git_tools import add_and_commit, changed_files, diff, ensure_repo, restore_paths
from .workflow import run_task


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="codemate")
    parser.add_argument("--root", default=".", help="Project root")
    subparsers = parser.add_subparsers(dest="command", required=True)

    init_parser = subparsers.add_parser("init", help="Create team.yml and .team files")
    init_parser.add_argument("--force", action="store_true")

    doctor_parser = subparsers.add_parser("doctor", help="Check local harness dependencies")
    doctor_parser.add_argument("--flow")

    run_parser = subparsers.add_parser("run", help="Run a task through the configured flow")
    run_parser.add_argument("task", nargs="?")
    run_parser.add_argument("--file")
    run_parser.add_argument("--flow")

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
        if args.command == "init":
            return _init(root, args.force)
        if args.command == "doctor":
            return _doctor(root, args.flow)
        if args.command == "run":
            task = _read_task(args)
            config = load_config(root)
            state = run_task(config, task, args.flow)
            print(_format_state(state))
            print(f"Run artifacts: .team/runs/{state.run_id}")
            return 0
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


def _init(root: Path, force: bool) -> int:
    created = init_project(root, force=force)
    if not created:
        print("Team configuration is up to date.")
        return 0
    print("Created team configuration:")
    for path in created:
        print(f"- {path.relative_to(root)}")
    return 0


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
