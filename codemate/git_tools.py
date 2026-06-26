from __future__ import annotations

import subprocess
from pathlib import Path


class GitError(RuntimeError):
    pass


def run_git(root: Path, args: list[str], check: bool = True) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        ["git", *args],
        cwd=root,
        text=True,
        capture_output=True,
    )
    if check and result.returncode != 0:
        message = result.stderr.strip() or result.stdout.strip() or "git command failed"
        raise GitError(message)
    return result


def ensure_repo(root: Path) -> None:
    run_git(root, ["rev-parse", "--is-inside-work-tree"])


def current_branch(root: Path) -> str:
    result = run_git(root, ["branch", "--show-current"])
    name = result.stdout.strip()
    if name:
        return name
    # Detached HEAD: record a stable marker instead of an empty string so the
    # run state still identifies where it started from.
    rev = run_git(root, ["rev-parse", "--short", "HEAD"], check=False)
    return f"detached@{rev.stdout.strip()}" if rev.returncode == 0 else ""


def current_head(root: Path) -> str:
    result = run_git(root, ["rev-parse", "HEAD"], check=False)
    return result.stdout.strip() if result.returncode == 0 else ""


def status_porcelain(root: Path) -> list[str]:
    result = run_git(root, ["status", "--porcelain"], check=False)
    return [line for line in result.stdout.splitlines() if line.strip()]


def is_clean(root: Path) -> bool:
    return not status_porcelain(root)


def create_branch(root: Path, name: str) -> None:
    run_git(root, ["switch", "-c", name])


def diff(root: Path) -> str:
    result = run_git(root, ["diff"], check=False)
    return result.stdout


def diff_name_only(root: Path) -> list[str]:
    result = run_git(root, ["diff", "--name-only"], check=False)
    return [line.strip() for line in result.stdout.splitlines() if line.strip()]


def changed_files(root: Path, include_untracked: bool = True) -> list[str]:
    # `-z` emits NUL-separated, unquoted paths so filenames with spaces or
    # non-ASCII characters survive intact and never need shell-style unescaping.
    result = run_git(root, ["status", "--porcelain", "-z"], check=False)
    tokens = result.stdout.split("\0")
    files: list[str] = []
    index = 0
    while index < len(tokens):
        entry = tokens[index]
        if not entry:
            index += 1
            continue
        status = entry[:2]
        path = entry[3:]
        # Renames and copies record `XY <new>\0<old>\0`; skip the source token.
        if status and status[0] in ("R", "C"):
            index += 2
        else:
            index += 1
        if status == "??" and not include_untracked:
            continue
        files.append(path)
    return sorted(set(files))


def add_and_commit(root: Path, paths: list[str], message: str) -> None:
    if not paths:
        raise GitError("No paths to commit")
    run_git(root, ["add", "--", *paths])
    run_git(root, ["commit", "-m", message])


def restore_paths(root: Path, paths: list[str]) -> None:
    if not paths:
        return
    run_git(root, ["restore", "--", *paths], check=False)
