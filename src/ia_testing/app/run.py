"""Use case: run a task file against its runners, one worktree per configuration."""

import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from ia_testing.domain.run import (
    Execution,
    ResultStore,
    RunLocation,
    Runner,
    RunRecord,
    RunRequest,
    RunResult,
    RunStatus,
    StoreError,
    Workspace,
    WorkspaceError,
    base_run_id,
    branch_name,
    default_output_dir,
    log_paths,
    worktree_path,
)
from ia_testing.domain.task_file import (
    InvalidTaskFile,
    RunnerConfig,
    TaskFile,
    TaskFileSource,
    parse_task_file,
)

NOT_IMPLEMENTED = "runner not implemented yet"
INTERRUPTED = "interrupted"


@dataclass(frozen=True)
class RunOptions:
    now: datetime  # local time with timezone; it names the run and stamps the record
    ref: str = "HEAD"
    timeout_minutes: int = 30
    output_dir: Path | None = None  # None: next to the repository (domain.default_output_dir)


@dataclass(frozen=True)
class RunOutcome:
    """What `run_task` produced.

    - `errors` and no `record`: the run could not start (exit code 2).
    - `errors` and a `record`: results.json could not be written (exit code 1).
    - no `errors`: `record` and `results_path` are set; the code is 1 if any result failed.
    """

    errors: tuple[str, ...] = ()
    record: RunRecord | None = None
    results_path: Path | None = None


@dataclass(frozen=True)
class _Prepared:
    task: TaskFile
    root: Path
    commit: str
    location: RunLocation


def _failed(
    config: RunnerConfig,
    location: RunLocation,
    *,
    reason: str,
    duration_s: float,
    implemented: bool,
    with_logs: bool,
) -> RunResult:
    """A failed result without an Execution: not implemented, or interrupted."""
    stdout_log, stderr_log = log_paths(location, config.id)
    return RunResult(
        id=config.id,
        runner=config.runner,
        model=config.model,
        local=config.local,
        status=RunStatus.FAILED,
        reason=reason,
        duration_s=duration_s,
        worktree=worktree_path(location, config.id) if implemented else None,
        branch=branch_name(location.run_id, config.id) if implemented else None,
        cost_usd=None,
        input_tokens=None,
        output_tokens=None,
        stdout_log=stdout_log if with_logs else None,
        stderr_log=stderr_log if with_logs else None,
    )


def _executed(config: RunnerConfig, execution: Execution, location: RunLocation) -> RunResult:
    stdout_log, stderr_log = log_paths(location, config.id)
    return RunResult(
        id=config.id,
        runner=config.runner,
        model=config.model,
        local=config.local,
        status=execution.status,
        reason=execution.reason,
        duration_s=execution.duration_s,
        worktree=worktree_path(location, config.id),
        branch=branch_name(location.run_id, config.id),
        cost_usd=execution.cost_usd,
        input_tokens=execution.input_tokens,
        output_tokens=execution.output_tokens,
        stdout_log=stdout_log,
        stderr_log=stderr_log,
    )


def _kept(created: list[Path]) -> str:
    return f"; worktrees created and kept: {', '.join(str(p) for p in created)}" if created else ""


def _prepare(
    source: TaskFileSource,
    runners: Mapping[str, Runner | None],
    workspace: Workspace,
    store: ResultStore,
    options: RunOptions,
    warn: Callable[[str], None],
    created: list[Path],
) -> _Prepared | tuple[str, ...]:
    """Steps 1 to 6. Return what step 7 needs, or the errors that stop the run."""
    try:
        task = parse_task_file(source.read(), runners.keys())
    except InvalidTaskFile as exc:
        return tuple(str(error) for error in exc.errors)
    try:
        root = workspace.open()
        commit = workspace.resolve(options.ref)
    except WorkspaceError as exc:
        return (str(exc),)

    check_errors: list[str] = []
    for name in dict.fromkeys(config.runner for config in task.runners):
        runner = runners[name]
        if runner is None:
            continue
        check = runner.check([config for config in task.runners if config.runner == name])
        for message in check.warnings:
            warn(message)
        if check.error is not None:
            check_errors.append(check.error)
    if check_errors:
        return tuple(check_errors)

    if workspace.is_dirty():
        warn(
            "the repository has uncommitted or untracked changes; they are not copied to the worktrees"
        )

    try:
        location = store.create_run(
            base_run_id(options.now), options.output_dir or default_output_dir(root)
        )
    except StoreError as exc:
        return (str(exc),)

    for config in task.runners:
        if runners[config.runner] is None:
            continue
        path = worktree_path(location, config.id)
        try:
            workspace.create(path, branch_name(location.run_id, config.id), commit)
        except WorkspaceError as exc:
            return (f"{exc} for '{config.id}'{_kept(created)}",)
        created.append(path)
    return _Prepared(task, root, commit, location)


def _save(
    store: ResultStore,
    options: RunOptions,
    prepared: _Prepared,
    results: list[RunResult],
) -> RunOutcome:
    record = RunRecord(
        run_id=prepared.location.run_id,
        started_at=options.now,
        task_type=prepared.task.type,
        repo=prepared.root,
        ref=options.ref,
        commit=prepared.commit,
        results=tuple(results),
    )
    try:
        path = store.save(prepared.location, record)
    except StoreError as exc:
        return RunOutcome(errors=(str(exc),), record=record)
    return RunOutcome(record=record, results_path=path)


def _run_all(
    runners: Mapping[str, Runner | None],
    store: ResultStore,
    options: RunOptions,
    prepared: _Prepared,
) -> RunOutcome:
    """Step 7: run the configurations in file order, saving after each one."""
    configs = prepared.task.runners
    location = prepared.location
    results: list[RunResult] = []
    outcome = RunOutcome()
    for index, config in enumerate(configs):
        runner = runners[config.runner]
        if runner is None:
            results.append(
                _failed(
                    config,
                    location,
                    reason=NOT_IMPLEMENTED,
                    duration_s=0.0,
                    implemented=False,
                    with_logs=False,
                )
            )
        else:
            stdout_log, stderr_log = log_paths(location, config.id)
            request = RunRequest(
                config=config,
                workdir=worktree_path(location, config.id),
                timeout_s=options.timeout_minutes * 60,
                stdout_log=stdout_log,
                stderr_log=stderr_log,
            )
            started = time.monotonic()
            try:
                results.append(_executed(config, runner.run(request), location))
            except KeyboardInterrupt:
                results.append(
                    _failed(
                        config,
                        location,
                        reason=INTERRUPTED,
                        duration_s=time.monotonic() - started,
                        implemented=True,
                        with_logs=True,
                    )
                )
                results.extend(
                    _failed(
                        pending,
                        location,
                        reason=INTERRUPTED,
                        duration_s=0.0,
                        implemented=runners[pending.runner] is not None,
                        with_logs=False,
                    )
                    for pending in configs[index + 1 :]
                )
                return _save(store, options, prepared, results)
        outcome = _save(store, options, prepared, results)
        if outcome.errors:
            return outcome
    return outcome


def run_task(
    source: TaskFileSource,
    runners: Mapping[str, Runner | None],
    workspace: Workspace,
    store: ResultStore,
    options: RunOptions,
    warn: Callable[[str], None],
) -> RunOutcome:
    """Validate, prepare every worktree, then run each configuration in file order."""
    created: list[Path] = []
    try:
        prepared = _prepare(source, runners, workspace, store, options, warn, created)
    except KeyboardInterrupt:
        return RunOutcome(errors=(f"interrupted before start{_kept(created)}",))
    if isinstance(prepared, tuple):
        return RunOutcome(errors=prepared)
    return _run_all(runners, store, options, prepared)
