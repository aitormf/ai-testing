import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from ia_testing.adapters.storage.json_store import JsonResultStore
from ia_testing.domain.run import (
    RunLocation,
    RunRecord,
    RunResult,
    RunStatus,
    StoreError,
)
from ia_testing.domain.task_file import TaskType


def _result(id_: str = "a", *, status: RunStatus = RunStatus.SUCCEEDED) -> RunResult:
    return RunResult(
        id=id_,
        runner="claude",
        model="haiku",
        local=False,
        status=status,
        reason=None if status is RunStatus.SUCCEEDED else "timeout",
        duration_s=12.5,
        worktree=Path("/out/run/worktrees") / id_,
        branch=f"ia-testing/run/{id_}",
        cost_usd=0.25,
        input_tokens=100,
        output_tokens=20,
        stdout_log=Path(f"/out/run/logs/{id_}.jsonl"),
        stderr_log=Path(f"/out/run/logs/{id_}.stderr.log"),
    )


def _record(*results: RunResult) -> RunRecord:
    return RunRecord(
        run_id="20261020-101500",
        started_at=datetime(2026, 10, 20, 10, 15, tzinfo=timezone(timedelta(hours=2))),
        task_type=TaskType.CODE_REVIEW,
        repo=Path("/repos/my-repo"),
        ref="HEAD",
        commit="abc123",
        results=results,
    )


def test_create_run_creates_logs_and_worktrees(tmp_path: Path) -> None:
    base = tmp_path / "deep" / "out"

    location = JsonResultStore().create_run("20261020-101500", base)

    assert location == RunLocation(run_id="20261020-101500", dir=base / "20261020-101500")
    assert (location.dir / "logs").is_dir()
    assert (location.dir / "worktrees").is_dir()


def test_create_run_adds_suffix_when_exists(tmp_path: Path) -> None:
    store = JsonResultStore()

    first = store.create_run("20261020-101500", tmp_path)
    second = store.create_run("20261020-101500", tmp_path)
    third = store.create_run("20261020-101500", tmp_path)

    assert [first.run_id, second.run_id, third.run_id] == [
        "20261020-101500",
        "20261020-101500-2",
        "20261020-101500-3",
    ]
    assert second.dir == tmp_path / "20261020-101500-2"
    assert second.dir.is_dir()


@pytest.mark.skipif(os.geteuid() == 0, reason="root can write anywhere")
def test_create_run_unwritable_raises(tmp_path: Path) -> None:
    base = tmp_path / "out"
    base.mkdir()
    base.chmod(0o500)
    try:
        with pytest.raises(StoreError) as excinfo:
            JsonResultStore().create_run("20261020-101500", base)
    finally:
        base.chmod(0o700)

    assert str(excinfo.value) == "cannot create run directory"


def test_create_run_base_dir_is_a_file_raises(tmp_path: Path) -> None:
    base = tmp_path / "out"
    base.write_text("not a directory", encoding="utf-8")

    with pytest.raises(StoreError):
        JsonResultStore().create_run("20261020-101500", base)


def test_save_writes_schema_v1(tmp_path: Path) -> None:
    store = JsonResultStore()
    location = store.create_run("20261020-101500", tmp_path)
    failed = RunResult(
        id="b",
        runner="codex",
        model="gpt",
        local=True,
        status=RunStatus.FAILED,
        reason="runner not implemented yet",
        duration_s=0,
        worktree=None,
        branch=None,
        cost_usd=None,
        input_tokens=None,
        output_tokens=None,
        stdout_log=None,
        stderr_log=None,
    )

    path = store.save(location, _record(_result("a"), failed))

    assert path == location.dir / "results.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data == {
        "schema_version": 1,
        "run_id": "20261020-101500",
        "started_at": "2026-10-20T10:15:00+02:00",
        "task_type": "code-review",
        "repo": "/repos/my-repo",
        "ref": "HEAD",
        "commit": "abc123",
        "results": [
            {
                "id": "a",
                "runner": "claude",
                "model": "haiku",
                "local": False,
                "status": "succeeded",
                "reason": None,
                "duration_s": 12.5,
                "worktree": "/out/run/worktrees/a",
                "branch": "ia-testing/run/a",
                "cost_usd": 0.25,
                "input_tokens": 100,
                "output_tokens": 20,
                "stdout_log": "/out/run/logs/a.jsonl",
                "stderr_log": "/out/run/logs/a.stderr.log",
            },
            {
                "id": "b",
                "runner": "codex",
                "model": "gpt",
                "local": True,
                "status": "failed",
                "reason": "runner not implemented yet",
                "duration_s": 0,
                "worktree": None,
                "branch": None,
                "cost_usd": None,
                "input_tokens": None,
                "output_tokens": None,
                "stdout_log": None,
                "stderr_log": None,
            },
        ],
    }
    # started_at keeps its time zone offset
    assert datetime.fromisoformat(data["started_at"]).utcoffset() == timedelta(hours=2)


def test_save_is_atomic_rewrite(tmp_path: Path) -> None:
    store = JsonResultStore()
    location = store.create_run("20261020-101500", tmp_path)

    store.save(location, _record(_result("a")))
    path = store.save(location, _record(_result("a"), _result("b", status=RunStatus.FAILED)))

    data = json.loads(path.read_text(encoding="utf-8"))
    assert [r["id"] for r in data["results"]] == ["a", "b"]
    # no temporary file is left behind
    assert sorted(p.name for p in location.dir.iterdir()) == ["logs", "results.json", "worktrees"]


def test_save_failure_raises_store_error(tmp_path: Path) -> None:
    location = RunLocation(run_id="r", dir=tmp_path / "missing")

    with pytest.raises(StoreError) as excinfo:
        JsonResultStore().save(location, _record(_result()))

    assert str(excinfo.value) == "cannot write results"


def test_results_do_not_contain_env_values(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SECRET_X", "s3cr3t-value-123")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-should-not-leak")
    store = JsonResultStore()
    location = store.create_run("20261020-101500", tmp_path)

    path = store.save(location, _record(_result()))

    text = path.read_text(encoding="utf-8")
    assert "s3cr3t-value-123" not in text
    assert "sk-ant-should-not-leak" not in text
