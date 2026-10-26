import json
import os
import shutil
import subprocess
import time
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path

import pytest
from fake_runner import SUCCESS, FakeRunner

from ia_testing.adapters.storage.json_store import JsonResultStore
from ia_testing.adapters.task_file import TomlTaskFileSource
from ia_testing.adapters.workspace.git import GitWorkspace
from ia_testing.app.run import RunOptions, RunOutcome, run_task
from ia_testing.domain.run import Execution, Runner, RunnerCheck, RunStatus

GIT = shutil.which("git") or "git"
NOW = datetime(2026, 10, 20, 12, 0, 0, tzinfo=UTC)
RUN_ID = "20261020-120000"
PROMPT = "Fix the bug; $(touch pwned)"


def git(repo: Path, *args: str) -> str:
    completed = subprocess.run(  # noqa: S603 security-reviewed: test helper, fixed git binary and literal test arguments, no shell
        [
            GIT,
            "-c",
            "user.name=Test",
            "-c",
            "user.email=test@example.com",
            "-c",
            "commit.gpgsign=false",
            *args,
        ],
        cwd=repo,
        capture_output=True,
        text=True,
        check=True,
        timeout=60,
    )
    return completed.stdout.strip()


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    root.mkdir()
    git(root, "init", "-b", "main")
    (root / "a.txt").write_text("one\n")
    git(root, "add", "a.txt")
    git(root, "commit", "-m", "first")
    return root.resolve()


def task_file(
    tmp_path: Path,
    configs: Sequence[tuple[str, str]] = (("a", "claude"), ("b", "claude")),
    *,
    task_type: str = "code-generation",
) -> TomlTaskFileSource:
    lines = [f'type = "{task_type}"', f"prompt = '{PROMPT}'", ""]
    for id_, runner in configs:
        lines += ["[[runners]]", f'id = "{id_}"', f'runner = "{runner}"', 'model = "haiku"', ""]
    path = tmp_path / "task.toml"
    path.write_text("\n".join(lines), encoding="utf-8")
    return TomlTaskFileSource(path)


def options(tmp_path: Path, **overrides: object) -> RunOptions:
    values: dict[str, object] = {"now": NOW, "output_dir": tmp_path / "out"}
    values.update(overrides)
    return RunOptions(**values)  # type: ignore[arg-type]


def execute(
    tmp_path: Path,
    repo: Path,
    runners: Mapping[str, Runner | None],
    *,
    source: TomlTaskFileSource | None = None,
    run_options: RunOptions | None = None,
    warnings: list[str] | None = None,
    workspace: GitWorkspace | None = None,
) -> RunOutcome:
    return run_task(
        source or task_file(tmp_path),
        runners,
        workspace or GitWorkspace(repo),
        JsonResultStore(),
        run_options or options(tmp_path),
        warnings.append if warnings is not None else (lambda _message: None),
    )


def test_runs_all_configs_from_same_commit(tmp_path: Path, repo: Path) -> None:
    fake = FakeRunner()
    head = git(repo, "rev-parse", "HEAD")

    outcome = execute(tmp_path, repo, {"claude": fake})

    assert outcome.errors == ()
    assert outcome.record is not None
    assert outcome.record.run_id == RUN_ID
    assert outcome.record.commit == head
    assert outcome.record.repo == repo
    assert outcome.record.ref == "HEAD"
    assert [r.id for r in outcome.record.results] == ["a", "b"]
    run_dir = tmp_path / "out" / RUN_ID
    assert outcome.results_path == run_dir / "results.json"
    assert json.loads((run_dir / "results.json").read_text())["commit"] == head
    for request, id_ in zip(fake.requests, ("a", "b"), strict=True):
        assert request.workdir == run_dir / "worktrees" / id_
        assert git(request.workdir, "rev-parse", "HEAD") == head
        assert git(request.workdir, "branch", "--show-current") == f"ia-testing/{RUN_ID}/{id_}"
        assert request.stdout_log == run_dir / "logs" / f"{id_}.jsonl"
        assert request.stderr_log == run_dir / "logs" / f"{id_}.stderr.log"
    first = outcome.record.results[0]
    assert first.worktree == run_dir / "worktrees" / "a"
    assert first.branch == f"ia-testing/{RUN_ID}/a"
    assert first.status is RunStatus.SUCCEEDED
    assert first.duration_s == SUCCESS.duration_s


def test_uses_given_ref(tmp_path: Path, repo: Path) -> None:
    git(repo, "switch", "-c", "other")
    (repo / "b.txt").write_text("two\n")
    git(repo, "add", "b.txt")
    git(repo, "commit", "-m", "second")
    other = git(repo, "rev-parse", "other")
    git(repo, "switch", "main")
    fake = FakeRunner()

    outcome = execute(tmp_path, repo, {"claude": fake}, run_options=options(tmp_path, ref="other"))

    assert outcome.record is not None
    assert outcome.record.ref == "other"
    assert outcome.record.commit == other
    assert (fake.requests[0].workdir / "b.txt").exists()


def test_output_dir_option(tmp_path: Path, repo: Path) -> None:
    custom = tmp_path / "somewhere" / "else"

    outcome = execute(
        tmp_path, repo, {"claude": FakeRunner()}, run_options=options(tmp_path, output_dir=custom)
    )

    assert outcome.results_path == custom / RUN_ID / "results.json"
    assert outcome.results_path.exists()


def test_default_output_dir_is_next_to_the_repo(tmp_path: Path, repo: Path) -> None:
    outcome = execute(
        tmp_path, repo, {"claude": FakeRunner()}, run_options=options(tmp_path, output_dir=None)
    )

    assert outcome.results_path == tmp_path / "repo.ia-testing" / RUN_ID / "results.json"


def test_task_type_is_recorded_and_prompt_unchanged(tmp_path: Path, repo: Path) -> None:
    fake = FakeRunner()

    outcome = execute(
        tmp_path, repo, {"claude": fake}, source=task_file(tmp_path, task_type="code-review")
    )

    assert outcome.record is not None
    assert outcome.record.task_type.value == "code-review"
    assert {request.config.prompt for request in fake.requests} == {PROMPT}


def test_results_saved_after_each_config(tmp_path: Path, repo: Path) -> None:
    results_file = tmp_path / "out" / RUN_ID / "results.json"
    seen: list[int] = []

    def on_run(_request: object) -> None:
        seen.append(
            len(json.loads(results_file.read_text())["results"]) if results_file.exists() else 0
        )

    execute(tmp_path, repo, {"claude": FakeRunner(on_run=on_run)})

    assert seen == [0, 1]
    assert len(json.loads(results_file.read_text())["results"]) == 2


def test_default_timeout_reaches_runner(tmp_path: Path, repo: Path) -> None:
    fake = FakeRunner()

    execute(tmp_path, repo, {"claude": fake})

    assert {request.timeout_s for request in fake.requests} == {1800}


def test_timeout_option_is_in_minutes(tmp_path: Path, repo: Path) -> None:
    fake = FakeRunner()

    execute(tmp_path, repo, {"claude": fake}, run_options=options(tmp_path, timeout_minutes=2))

    assert {request.timeout_s for request in fake.requests} == {120}


def test_runner_names_are_injected(tmp_path: Path, repo: Path) -> None:
    fake = FakeRunner()
    source = task_file(tmp_path, (("x", "made-up-runner"),))

    outcome = execute(tmp_path, repo, {"made-up-runner": fake}, source=source)

    assert outcome.errors == ()
    assert [request.config.id for request in fake.requests] == ["x"]


def test_invalid_file_returns_errors(tmp_path: Path, repo: Path) -> None:
    fake = FakeRunner()
    source = task_file(tmp_path, (("a", "gemini"),))

    outcome = execute(tmp_path, repo, {"claude": fake}, source=source)

    assert outcome.errors == ("runners[0].runner: unknown runner: expected one of claude",)
    assert outcome.record is None
    assert outcome.results_path is None
    assert fake.requests == []
    assert not (tmp_path / "out").exists()


def test_unreadable_file_returns_errors(tmp_path: Path, repo: Path) -> None:
    source = TomlTaskFileSource(tmp_path / "missing.toml")

    outcome = execute(tmp_path, repo, {"claude": FakeRunner()}, source=source)

    assert outcome.errors == (f"{tmp_path / 'missing.toml'}: file not found",)
    assert outcome.record is None


def test_not_a_repo_returns_error(tmp_path: Path, repo: Path) -> None:
    plain = tmp_path / "plain"
    plain.mkdir()
    fake = FakeRunner()

    outcome = execute(tmp_path, repo, {"claude": fake}, workspace=GitWorkspace(plain))

    assert outcome.errors == ("not a git repository",)
    assert outcome.record is None
    assert fake.requests == []
    assert not (tmp_path / "out").exists()


def test_unknown_ref_returns_error(tmp_path: Path, repo: Path) -> None:
    fake = FakeRunner()

    outcome = execute(tmp_path, repo, {"claude": fake}, run_options=options(tmp_path, ref="--foo"))

    assert outcome.errors == ("invalid ref",)
    assert fake.requests == []
    assert not (tmp_path / "out").exists()


def test_check_error_aborts(tmp_path: Path, repo: Path) -> None:
    broken = FakeRunner(check_result=RunnerCheck(error="claude is not installed", warnings=()))
    other = FakeRunner()
    source = task_file(tmp_path, (("a", "claude"), ("b", "other")))

    outcome = execute(tmp_path, repo, {"claude": broken, "other": other}, source=source)

    assert outcome.errors == ("claude is not installed",)
    assert outcome.record is None
    assert broken.requests == other.requests == []
    assert not (tmp_path / "out").exists()


def test_create_run_failure_aborts(tmp_path: Path, repo: Path) -> None:
    blocker = tmp_path / "blocker"
    blocker.write_text("a file, not a directory")
    fake = FakeRunner()

    outcome = execute(
        tmp_path, repo, {"claude": fake}, run_options=options(tmp_path, output_dir=blocker / "out")
    )

    assert outcome.errors == ("cannot create run directory",)
    assert outcome.record is None
    assert fake.requests == []


def test_worktree_failure_aborts_before_running(tmp_path: Path, repo: Path) -> None:
    git(repo, "branch", f"ia-testing/{RUN_ID}/b")
    fake = FakeRunner()

    outcome = execute(tmp_path, repo, {"claude": fake})

    assert len(outcome.errors) == 1
    assert "cannot create worktree" in outcome.errors[0]
    assert "'b'" in outcome.errors[0]
    assert str(tmp_path / "out" / RUN_ID / "worktrees" / "a") in outcome.errors[0]
    assert outcome.record is None
    assert fake.requests == []
    assert not (tmp_path / "out" / RUN_ID / "results.json").exists()


def test_dirty_repo_warns(tmp_path: Path, repo: Path) -> None:
    clean: list[str] = []
    execute(tmp_path, repo, {"claude": FakeRunner()}, warnings=clean)
    (repo / "untracked.txt").write_text("new\n")
    dirty: list[str] = []
    fake = FakeRunner()

    outcome = execute(
        tmp_path,
        repo,
        {"claude": fake},
        run_options=options(tmp_path, now=NOW.replace(second=1)),
        warnings=dirty,
    )

    assert clean == []
    assert len(dirty) == 1
    assert "uncommitted or untracked changes" in dirty[0]
    assert len(fake.requests) == 2
    assert outcome.errors == ()
    assert not (fake.requests[0].workdir / "untracked.txt").exists()


def test_warnings_are_emitted(tmp_path: Path, repo: Path) -> None:
    warnings: list[str] = []
    seen_when_running: list[list[str]] = []
    fake = FakeRunner(
        check_result=RunnerCheck(error=None, warnings=("runs without permission limits",)),
        on_run=lambda _request: seen_when_running.append(list(warnings)),
    )

    execute(tmp_path, repo, {"claude": fake}, warnings=warnings)

    assert warnings == ["runs without permission limits"]
    assert seen_when_running[0] == ["runs without permission limits"]


def test_check_receives_only_its_own_configs(tmp_path: Path, repo: Path) -> None:
    claude, other = FakeRunner(), FakeRunner()
    source = task_file(tmp_path, (("a", "claude"), ("b", "other"), ("c", "claude")))

    execute(tmp_path, repo, {"claude": claude, "other": other}, source=source)

    assert [[c.id for c in configs] for configs in claude.checked] == [["a", "c"]]
    assert [[c.id for c in configs] for configs in other.checked] == [["b"]]


def test_unimplemented_runner_fails_without_worktree(tmp_path: Path, repo: Path) -> None:
    fake = FakeRunner()
    source = task_file(tmp_path, (("a", "claude"), ("b", "codex")))

    outcome = execute(tmp_path, repo, {"claude": fake, "codex": None}, source=source)

    assert outcome.errors == ()
    assert outcome.record is not None
    ok, missing = outcome.record.results
    assert ok.status is RunStatus.SUCCEEDED
    assert missing.id == "b"
    assert missing.status is RunStatus.FAILED
    assert missing.reason == "runner not implemented yet"
    assert missing.duration_s == 0
    assert missing.worktree is None
    assert missing.branch is None
    assert missing.stdout_log is None
    assert [request.config.id for request in fake.requests] == ["a"]
    worktrees = tmp_path / "out" / RUN_ID / "worktrees"
    assert [path.name for path in worktrees.iterdir()] == ["a"]
    assert "ia-testing/" + RUN_ID + "/b" not in git(repo, "branch", "--list", "ia-testing/*/*")


def test_only_unimplemented_runners_launch_nothing(tmp_path: Path, repo: Path) -> None:
    source = task_file(tmp_path, (("a", "codex"),))

    outcome = execute(tmp_path, repo, {"codex": None}, source=source)

    assert outcome.errors == ()
    assert outcome.record is not None
    assert [r.reason for r in outcome.record.results] == ["runner not implemented yet"]
    assert outcome.results_path is not None
    assert list((tmp_path / "out" / RUN_ID / "worktrees").iterdir()) == []


def test_failed_run_continues(tmp_path: Path, repo: Path) -> None:
    failure = Execution(status=RunStatus.FAILED, reason="timeout", duration_s=3.0)
    fake = FakeRunner([failure])

    outcome = execute(tmp_path, repo, {"claude": fake})

    assert outcome.errors == ()
    assert outcome.record is not None
    first, second = outcome.record.results
    assert (first.status, first.reason, first.duration_s) == (RunStatus.FAILED, "timeout", 3.0)
    assert second.status is RunStatus.SUCCEEDED
    assert len(fake.requests) == 2


def test_interrupt_marks_current_and_pending(tmp_path: Path, repo: Path) -> None:
    fake = FakeRunner([SUCCESS, KeyboardInterrupt()], on_run=lambda _request: time.sleep(0.01))
    source = task_file(tmp_path, (("a", "claude"), ("b", "claude"), ("c", "claude")))

    outcome = execute(tmp_path, repo, {"claude": fake}, source=source)

    assert outcome.errors == ()
    assert outcome.record is not None
    first, current, pending = outcome.record.results
    assert first.status is RunStatus.SUCCEEDED
    assert (current.status, current.reason) == (RunStatus.FAILED, "interrupted")
    assert current.duration_s > 0
    assert current.stdout_log is not None
    assert (pending.status, pending.reason) == (RunStatus.FAILED, "interrupted")
    assert pending.duration_s == 0
    assert pending.worktree == tmp_path / "out" / RUN_ID / "worktrees" / "c"
    assert [request.config.id for request in fake.requests] == ["a", "b"]
    assert outcome.results_path is not None
    saved = json.loads(outcome.results_path.read_text())["results"]
    assert [(r["id"], r["reason"]) for r in saved] == [
        ("a", None),
        ("b", "interrupted"),
        ("c", "interrupted"),
    ]


def test_interrupt_marks_pending_unimplemented_runner_without_worktree(
    tmp_path: Path, repo: Path
) -> None:
    fake = FakeRunner([KeyboardInterrupt()])
    source = task_file(tmp_path, (("a", "claude"), ("b", "codex")))

    outcome = execute(tmp_path, repo, {"claude": fake, "codex": None}, source=source)

    assert outcome.record is not None
    pending = outcome.record.results[1]
    assert pending.reason == "interrupted"
    assert pending.worktree is None


class InterruptingWorkspace(GitWorkspace):
    """Real git, but Ctrl-C arrives while creating the second worktree."""

    def __init__(self, path: Path) -> None:
        super().__init__(path)
        self._calls = 0

    def create(self, path: Path, branch: str, commit: str) -> None:
        self._calls += 1
        if self._calls == 2:
            raise KeyboardInterrupt
        super().create(path, branch, commit)


def test_interrupt_before_start_lists_worktrees(tmp_path: Path, repo: Path) -> None:
    fake = FakeRunner()

    outcome = execute(tmp_path, repo, {"claude": fake}, workspace=InterruptingWorkspace(repo))

    created = tmp_path / "out" / RUN_ID / "worktrees" / "a"
    assert outcome.errors == (f"interrupted before start; worktrees created and kept: {created}",)
    assert outcome.record is None
    assert outcome.results_path is None
    assert fake.requests == []
    assert not (tmp_path / "out" / RUN_ID / "results.json").exists()


def test_interrupt_before_start_without_worktrees(tmp_path: Path, repo: Path) -> None:
    fake = FakeRunner(check_result=KeyboardInterrupt())

    outcome = execute(tmp_path, repo, {"claude": fake})

    assert outcome.errors == ("interrupted before start",)
    assert outcome.record is None


@pytest.mark.skipif(os.geteuid() == 0, reason="root ignores directory permissions")
def test_save_failure_stops_with_exit_1(tmp_path: Path, repo: Path) -> None:
    run_dir = tmp_path / "out" / RUN_ID

    def lock_run_dir(_request: object) -> None:
        run_dir.chmod(0o500)

    fake = FakeRunner(on_run=lock_run_dir)
    try:
        outcome = execute(tmp_path, repo, {"claude": fake})
    finally:
        run_dir.chmod(0o700)

    assert outcome.errors == ("cannot write results",)
    assert outcome.results_path is None
    assert outcome.record is not None
    assert [r.id for r in outcome.record.results] == ["a"]
    assert [request.config.id for request in fake.requests] == ["a"]
