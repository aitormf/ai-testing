"""Write the outcome of `run` and return the process exit code."""

from typing import TextIO

from ia_testing.app.run import RunOutcome
from ia_testing.domain.run import RunResult, RunStatus


def _line(result: RunResult) -> str:
    status = result.status.value
    if result.reason is not None:
        status = f"{status} ({result.reason})"
    cost = "-" if result.cost_usd is None else f"${result.cost_usd:.4f}"
    worktree = "-" if result.worktree is None else str(result.worktree)
    return f"{result.id}  {status}  {result.duration_s:.1f}s  {cost}  {worktree}"


def print_run(outcome: RunOutcome, out: TextIO, err: TextIO) -> int:
    """Write the summary to out and errors to err; return 0, 1 or 2.

    - errors and no record: the run could not start (2).
    - errors and a record: results.json could not be written (1).
    - otherwise 0 if every result succeeded, else 1.
    """
    for error in outcome.errors:
        err.write(f"{error}\n")
    if outcome.record is None:
        return 2
    for result in outcome.record.results:
        out.write(f"{_line(result)}\n")
    if outcome.results_path is not None:
        out.write(f"results: {outcome.results_path}\n")
    failed = any(result.status is not RunStatus.SUCCEEDED for result in outcome.record.results)
    return 1 if outcome.errors or failed else 0
