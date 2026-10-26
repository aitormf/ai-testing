"""Run model and ports: pure domain logic, no I/O."""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from pathlib import Path
from typing import Protocol

from ia_testing.domain.task_file import RunnerConfig, TaskType


class RunStatus(StrEnum):
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class WorkspaceError(Exception):
    """Raised by a Workspace; the message is a fixed reason, never tool output."""


class StoreError(Exception):
    """Raised by a ResultStore; the message is a fixed reason, never tool output."""


@dataclass(frozen=True)
class Execution:
    """What a Runner returns for one request."""

    status: RunStatus
    reason: str | None
    duration_s: float
    cost_usd: float | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None


@dataclass(frozen=True)
class RunRequest:
    config: RunnerConfig
    workdir: Path
    timeout_s: float
    stdout_log: Path
    stderr_log: Path


@dataclass(frozen=True)
class RunResult:
    id: str
    runner: str
    model: str
    local: bool
    status: RunStatus
    reason: str | None
    duration_s: float
    worktree: Path | None
    branch: str | None
    cost_usd: float | None
    input_tokens: int | None
    output_tokens: int | None
    stdout_log: Path | None
    stderr_log: Path | None


@dataclass(frozen=True)
class RunRecord:
    """Everything persisted in results.json."""

    run_id: str
    started_at: datetime  # timezone-aware
    task_type: TaskType
    repo: Path
    ref: str
    commit: str
    results: tuple[RunResult, ...]


@dataclass(frozen=True)
class RunLocation:
    run_id: str
    dir: Path  # worktrees in dir/worktrees/<id>, logs in dir/logs/


@dataclass(frozen=True)
class RunnerCheck:
    error: str | None
    warnings: tuple[str, ...]


class Runner(Protocol):
    def check(self, configs: Sequence[RunnerConfig]) -> RunnerCheck:
        """Check that the tool is usable for these configs; report warnings."""
        ...

    def run(self, request: RunRequest) -> Execution:
        """Run the task, applying the timeout and terminating its process group.

        On KeyboardInterrupt, terminate the group and re-raise it. Never raise anything else.
        """
        ...


class Workspace(Protocol):
    def open(self) -> Path:
        """Return the repository root; raise WorkspaceError."""
        ...

    def resolve(self, ref: str) -> str:
        """Return the commit a ref points to; raise WorkspaceError."""
        ...

    def is_dirty(self) -> bool:
        """Whether the working tree has uncommitted or untracked changes."""
        ...

    def create(self, path: Path, branch: str, commit: str) -> None:
        """Create a worktree at path on a new branch; raise WorkspaceError."""
        ...


class ResultStore(Protocol):
    def create_run(self, base_id: str, base_dir: Path) -> RunLocation:
        """Create the run directory exclusively; raise StoreError."""
        ...

    def save(self, location: RunLocation, record: RunRecord) -> Path:
        """Write results.json and return its path; raise StoreError."""
        ...


def base_run_id(now: datetime) -> str:
    """Run id before any collision suffix; `now` is expected in local time."""
    return now.strftime("%Y%m%d-%H%M%S")


def default_output_dir(repo_root: Path) -> Path:
    """`<parent of the repo>/<repo name>.ia-testing`."""
    return repo_root.parent / f"{repo_root.name}.ia-testing"


def branch_name(run_id: str, id: str) -> str:
    return f"ia-testing/{run_id}/{id}"


def worktree_path(location: RunLocation, id: str) -> Path:
    return location.dir / "worktrees" / id


def log_paths(location: RunLocation, id: str) -> tuple[Path, Path]:
    """Return (stdout log, stderr log) for a runner config."""
    logs = location.dir / "logs"
    return logs / f"{id}.jsonl", logs / f"{id}.stderr.log"
