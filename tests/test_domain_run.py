import dataclasses
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from ia_testing.domain.run import (
    Execution,
    RunLocation,
    RunnerCheck,
    RunRecord,
    RunRequest,
    RunResult,
    RunStatus,
    StoreError,
    WorkspaceError,
    base_run_id,
    branch_name,
    default_output_dir,
    log_paths,
    worktree_path,
)
from ia_testing.domain.task_file import RunnerConfig, TaskType


def _config() -> RunnerConfig:
    return RunnerConfig(id="a", runner="claude", model="haiku", local=False, prompt="p")


def _result() -> RunResult:
    return RunResult(
        id="a",
        runner="claude",
        model="haiku",
        local=False,
        status=RunStatus.SUCCEEDED,
        reason=None,
        duration_s=1.0,
        worktree=None,
        branch=None,
        cost_usd=None,
        input_tokens=None,
        output_tokens=None,
        stdout_log=None,
        stderr_log=None,
    )


def test_dataclasses_are_frozen() -> None:
    record = RunRecord(
        run_id="20261020-101500",
        started_at=datetime(2026, 10, 20, 10, 15, tzinfo=UTC),
        task_type=TaskType.CODE_REVIEW,
        repo=Path("/repo"),
        ref="HEAD",
        commit="abc123",
        results=(_result(),),
    )
    instances: list[Any] = [
        Execution(status=RunStatus.FAILED, reason="timeout", duration_s=1.0),
        RunRequest(
            config=_config(),
            workdir=Path("/w"),
            timeout_s=10,
            stdout_log=Path("/o"),
            stderr_log=Path("/e"),
        ),
        _result(),
        record,
        RunLocation(run_id="r", dir=Path("/d")),
        RunnerCheck(error=None, warnings=()),
    ]

    for instance in instances:
        field = dataclasses.fields(instance)[0].name
        with pytest.raises(dataclasses.FrozenInstanceError):
            setattr(instance, field, None)


def test_execution_optional_metrics_default_to_none() -> None:
    execution = Execution(status=RunStatus.SUCCEEDED, reason=None, duration_s=2.5)

    assert execution.cost_usd is None
    assert execution.input_tokens is None
    assert execution.output_tokens is None


def test_status_values() -> None:
    assert RunStatus.SUCCEEDED.value == "succeeded"
    assert RunStatus.FAILED.value == "failed"


def test_errors_are_exceptions() -> None:
    assert issubclass(WorkspaceError, Exception)
    assert issubclass(StoreError, Exception)


def test_base_run_id_format() -> None:
    now = datetime(2026, 1, 2, 3, 4, 5, tzinfo=UTC)

    assert base_run_id(now) == "20260102-030405"


def test_default_output_dir() -> None:
    assert default_output_dir(Path("/home/me/projects/my-repo")) == Path(
        "/home/me/projects/my-repo.ia-testing"
    )


def test_worktree_and_log_paths() -> None:
    location = RunLocation(run_id="20261020-101500", dir=Path("/out/20261020-101500"))

    assert branch_name(location.run_id, "claude-haiku") == "ia-testing/20261020-101500/claude-haiku"
    assert worktree_path(location, "a") == Path("/out/20261020-101500/worktrees/a")
    assert log_paths(location, "a") == (
        Path("/out/20261020-101500/logs/a.jsonl"),
        Path("/out/20261020-101500/logs/a.stderr.log"),
    )
    # An id called "logs" does not collide: logs and worktrees live in separate directories.
    assert worktree_path(location, "logs") == Path("/out/20261020-101500/worktrees/logs")
    assert worktree_path(location, "logs") != location.dir / "logs"
    assert log_paths(location, "logs")[0] == Path("/out/20261020-101500/logs/logs.jsonl")
