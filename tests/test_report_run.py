import io
from datetime import UTC, datetime
from pathlib import Path

from ia_testing.adapters.report.run import print_run
from ia_testing.app.run import RunOutcome
from ia_testing.domain.run import RunRecord, RunResult, RunStatus
from ia_testing.domain.task_file import TaskType

RESULTS_PATH = Path("/out/20261020-120000/results.json")


def result(
    id: str,
    status: RunStatus = RunStatus.SUCCEEDED,
    *,
    reason: str | None = None,
    duration_s: float = 12.34,
    cost_usd: float | None = 0.0123,
    worktree: Path | None = None,
) -> RunResult:
    return RunResult(
        id=id,
        runner="claude",
        model="haiku",
        local=False,
        status=status,
        reason=reason,
        duration_s=duration_s,
        worktree=worktree if worktree is not None else Path(f"/out/20261020-120000/worktrees/{id}"),
        branch=f"ia-testing/20261020-120000/{id}",
        cost_usd=cost_usd,
        input_tokens=None,
        output_tokens=None,
        stdout_log=None,
        stderr_log=None,
    )


def outcome(*results: RunResult, errors: tuple[str, ...] = ()) -> RunOutcome:
    record = RunRecord(
        run_id="20261020-120000",
        started_at=datetime(2026, 10, 20, 12, 0, tzinfo=UTC),
        task_type=TaskType.CODE_GENERATION,
        repo=Path("/repo"),
        ref="HEAD",
        commit="abc",
        results=tuple(results),
    )
    return RunOutcome(errors=errors, record=record, results_path=None if errors else RESULTS_PATH)


def test_summary_lines() -> None:
    out, err = io.StringIO(), io.StringIO()

    code = print_run(outcome(result("a"), result("b", cost_usd=None)), out, err)

    assert code == 0
    assert out.getvalue().splitlines() == [
        "a  succeeded  12.3s  $0.0123  /out/20261020-120000/worktrees/a",
        "b  succeeded  12.3s  -  /out/20261020-120000/worktrees/b",
        f"results: {RESULTS_PATH}",
    ]
    assert err.getvalue() == ""


def test_summary_shows_reason_and_missing_worktree() -> None:
    out, err = io.StringIO(), io.StringIO()
    failed = result(
        "c", RunStatus.FAILED, reason="runner not implemented yet", cost_usd=None, duration_s=0.0
    )
    no_worktree = RunResult(**{**failed.__dict__, "worktree": None, "branch": None})

    code = print_run(outcome(no_worktree), out, err)

    assert code == 1
    assert out.getvalue().splitlines()[0] == "c  failed (runner not implemented yet)  0.0s  -  -"


def test_errors_exit_2() -> None:
    out, err = io.StringIO(), io.StringIO()

    code = print_run(RunOutcome(errors=("not a git repository", "other")), out, err)

    assert code == 2
    assert out.getvalue() == ""
    assert err.getvalue() == "not a git repository\nother\n"


def test_any_failure_exit_1() -> None:
    out, err = io.StringIO(), io.StringIO()

    code = print_run(
        outcome(result("a"), result("b", RunStatus.FAILED, reason="timeout")), out, err
    )

    assert code == 1
    assert "b  failed (timeout)" in out.getvalue()


def test_cannot_write_results_exit_1() -> None:
    out, err = io.StringIO(), io.StringIO()

    code = print_run(outcome(result("a"), errors=("cannot write results",)), out, err)

    assert code == 1
    assert err.getvalue() == "cannot write results\n"
    assert "results:" not in out.getvalue()
