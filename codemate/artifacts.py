from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any


def new_run_id() -> str:
    return datetime.now().strftime("%Y-%m-%dT%H-%M-%S-%f")


def latest_run_dir(root: Path) -> Path:
    runs = root / ".team" / "runs"
    candidates = sorted([path for path in runs.glob("*") if path.is_dir()])
    if not candidates:
        raise FileNotFoundError("No runs found")
    return candidates[-1]


@dataclass
class RunState:
    run_id: str
    task: str
    flow: str
    status: str
    branch: str
    base_branch: str
    base_head: str
    current_step: str | None = None
    steps: list[dict[str, Any]] = field(default_factory=list)
    changed_files: list[str] = field(default_factory=list)
    reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "task": self.task,
            "flow": self.flow,
            "status": self.status,
            "branch": self.branch,
            "base_branch": self.base_branch,
            "base_head": self.base_head,
            "current_step": self.current_step,
            "steps": self.steps,
            "changed_files": self.changed_files,
            "reason": self.reason,
        }

    @classmethod
    def from_path(cls, path: Path) -> "RunState":
        data = json.loads(path.read_text())
        return cls(**data)


class RunArtifacts:
    def __init__(self, root: Path, run_id: str) -> None:
        self.root = root
        self.run_id = run_id
        self.dir = root / ".team" / "runs" / run_id
        self.dir.mkdir(parents=True, exist_ok=True)

    @property
    def state_path(self) -> Path:
        return self.dir / "state.json"

    def write_state(self, state: RunState) -> None:
        self.state_path.write_text(json.dumps(state.to_dict(), indent=2) + "\n")

    def write_text(self, name: str, content: str) -> Path:
        path = self.dir / name
        path.write_text(content)
        return path

    def read_text(self, name: str, default: str = "") -> str:
        path = self.dir / name
        return path.read_text() if path.exists() else default


class RunLock:
    def __init__(self, root: Path, run_id: str) -> None:
        self.path = root / ".team" / "lock.json"
        self.run_id = run_id

    def __enter__(self) -> "RunLock":
        if self.path.exists():
            if self._is_stale():
                self.path.unlink()
            else:
                raise RuntimeError(f"Another team run appears active: {self.path}")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            json.dumps(
                {
                    "run_id": self.run_id,
                    "pid": os.getpid(),
                    "created_at": datetime.now().isoformat(timespec="seconds"),
                },
                indent=2,
            )
            + "\n"
        )
        return self

    def _is_stale(self) -> bool:
        try:
            data = json.loads(self.path.read_text())
        except (OSError, json.JSONDecodeError):
            return False
        pid = data.get("pid")
        if not isinstance(pid, int) or pid <= 0:
            return False
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return True
        except PermissionError:
            return False
        return False

    def __exit__(self, _exc_type: object, _exc: object, _tb: object) -> None:
        if self.path.exists():
            self.path.unlink()
