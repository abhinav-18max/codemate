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
    return result.stdout.strip()


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
    files: list[str] = []
    for line in status_porcelain(root):
        path = line[3:].strip()
        if " -> " in path:
            path = path.split(" -> ", 1)[1]
        if line.startswith("??") and not include_untracked:
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
