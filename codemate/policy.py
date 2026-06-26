from __future__ import annotations

from fnmatch import fnmatch
from pathlib import PurePosixPath


class PolicyError(RuntimeError):
    pass


def enforce_path_policy(
    changed_files: list[str], allow_paths: list[str], deny_paths: list[str]
) -> None:
    violations: list[str] = []
    for path in changed_files:
        normalized = PurePosixPath(path).as_posix()
        if normalized.startswith(".team/runs/"):
            continue
        if not _matches_any(normalized, allow_paths or ["**"]):
            violations.append(f"{path} is not allowed by allow_paths")
        if _matches_any(normalized, deny_paths):
            violations.append(f"{path} is denied by deny_paths")
    if violations:
        joined = "\n".join(f"- {violation}" for violation in violations)
        raise PolicyError(f"Path policy violation:\n{joined}")


def _matches_any(path: str, patterns: list[str]) -> bool:
    for pattern in patterns:
        if fnmatch(path, pattern) or fnmatch("/" + path, pattern):
            return True
        if pattern.endswith("/**") and path.startswith(pattern[:-3]):
            return True
    return False
