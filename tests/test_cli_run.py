"""CLI tests for `run`, with a fake `claude` executable and a real git repository."""

import inspect
import json
import os
import shutil
import signal
from collections.abc import Iterator
from pathlib import Path

import pytest
from fakes import install_fake_claude, read_record, write_scenario
from test_app_run import git

from ia_testing.cli import cli_app, install_signal_handlers, run

RESULT_LINE = json.dumps(
    {
        "type": "result",
        "is_error": False,
        "total_cost_usd": 0.5,
        "usage": {"input_tokens": 3, "output_tokens": 4},
    }
)

TASK = """\
type = "code-generation"
prompt = "Write it"

[[runners]]
id = "a"
runner = "claude"
model = "haiku"
{extra}"""


def task_text(*extra: str) -> str:
    return TASK.format(extra="".join(extra))


CODEX = '\n[[runners]]\nid = "b"\nrunner = "codex"\nmodel = "m"\n'
SECOND_CLAUDE = '\n[[runners]]\nid = "b"\nrunner = "claude"\nmodel = "sonnet"\n'


@pytest.fixture(autouse=True)
def clean_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ("ANTHROPIC_API_KEY", "CLAUDE_CODE_OAUTH_TOKEN"):
        monkeypatch.delenv(name, raising=False)


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    root.mkdir()
    git(root, "init", "-b", "main")
    write_scenario(root, stdout=[RESULT_LINE])
    git(root, "add", "fake-claude.json")
    git(root, "commit", "-m", "first")
    return root.resolve()


@pytest.fixture
def fake_claude(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    return install_fake_claude(tmp_path, monkeypatch)


def write_task(tmp_path: Path, text: str) -> Path:
    path = tmp_path / "task.toml"
    path.write_text(text, encoding="utf-8")
    return path


def run_cli(capsys: pytest.CaptureFixture[str], tmp_path: Path, *args: str) -> tuple[int, str, str]:
    code = cli_app(["run", *args, "--output-dir", str(tmp_path / "out")])
    captured = capsys.readouterr()
    assert "Traceback" not in captured.err
    return code, captured.out, captured.err


def test_invalid_file_exit_2_creates_nothing(
    tmp_path: Path, repo: Path, fake_claude: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    path = write_task(tmp_path, task_text('modle = "leaked-value"\n'))

    code, out, err = run_cli(capsys, tmp_path, str(path), "--repo", str(repo))

    assert code == 2
    assert out == ""
    assert "runners[0].modle: unknown key" in err
    assert "leaked-value" not in err
    assert not (tmp_path / "out").exists()


def test_not_a_repo_exit_2(
    tmp_path: Path, fake_claude: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    path = write_task(tmp_path, task_text())
    not_a_repo = tmp_path / "plain"
    not_a_repo.mkdir()

    code, out, err = run_cli(capsys, tmp_path, str(path), "--repo", str(not_a_repo))

    assert code == 2
    assert out == ""
    assert "not a git repository" in err
    assert not (tmp_path / "out").exists()


def test_unknown_ref_exit_2(
    tmp_path: Path, repo: Path, fake_claude: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    path = write_task(tmp_path, task_text())

    code, _, err = run_cli(capsys, tmp_path, str(path), "--repo", str(repo), "--ref", "nope")

    assert code == 2
    assert "unknown ref" in err
    assert not (tmp_path / "out").exists()


def test_option_like_ref_exit_2(
    tmp_path: Path, repo: Path, fake_claude: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    path = write_task(tmp_path, task_text())

    code, _, err = run_cli(capsys, tmp_path, str(path), "--repo", str(repo), "--ref=--foo")

    assert code == 2
    assert "invalid ref" in err
    assert not (tmp_path / "out").exists()


def test_claude_missing_exit_2(
    tmp_path: Path, repo: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    git_only = tmp_path / "git-only"
    git_only.mkdir()
    (git_only / "git").symlink_to(shutil.which("git") or "git")
    monkeypatch.setenv("PATH", str(git_only))
    path = write_task(tmp_path, task_text())

    code, out, err = run_cli(capsys, tmp_path, str(path), "--repo", str(repo))

    assert code == 2
    assert out == ""
    assert "claude executable not found" in err
    assert not (tmp_path / "out").exists()


@pytest.mark.parametrize("value", ["0", "-5", "abc"])
def test_invalid_timeout(
    value: str,
    tmp_path: Path,
    repo: Path,
    fake_claude: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    path = write_task(tmp_path, task_text())

    with pytest.raises(SystemExit) as exit_info:
        cli_app(
            [
                "run",
                str(path),
                "--repo",
                str(repo),
                "--timeout",
                value,
                "--output-dir",
                str(tmp_path / "out"),
            ]
        )
    captured = capsys.readouterr()

    assert exit_info.value.code == 1
    assert captured.out == ""
    assert "--timeout" in captured.err
    assert "Traceback" not in captured.err
    assert not (tmp_path / "out").exists()


def test_default_timeout_parameter() -> None:
    parameters = inspect.signature(run).parameters

    assert parameters["timeout"].default == 30
    assert parameters["repo"].default is None
    assert parameters["ref"].default == "HEAD"
    assert parameters["output_dir"].default is None


def test_claude_and_codex(
    tmp_path: Path, repo: Path, fake_claude: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    path = write_task(tmp_path, task_text(CODEX))

    code, out, err = run_cli(capsys, tmp_path, str(path), "--repo", str(repo))

    assert code == 1
    lines = out.splitlines()
    assert lines[0].startswith("a  succeeded  ")
    assert "$0.5000" in lines[0]
    assert lines[1].startswith("b  failed (runner not implemented yet)  0.0s  -  -")
    run_dir = next((tmp_path / "out").iterdir())
    assert lines[2] == f"results: {run_dir / 'results.json'}"
    assert "bypassPermissions" in err
    saved = json.loads((run_dir / "results.json").read_text())
    assert [r["id"] for r in saved["results"]] == ["a", "b"]
    assert saved["results"][1]["worktree"] is None
    assert not (run_dir / "worktrees" / "b").exists()


def test_two_claude_configs_exit_0(
    tmp_path: Path, repo: Path, fake_claude: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    path = write_task(tmp_path, task_text(SECOND_CLAUDE))

    code, out, _ = run_cli(capsys, tmp_path, str(path), "--repo", str(repo), "--timeout", "2")

    assert code == 0
    assert [line.split()[1] for line in out.splitlines()[:2]] == ["succeeded", "succeeded"]


def test_secret_not_in_output(
    tmp_path: Path,
    repo: Path,
    fake_claude: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setenv("SECRET_X", "super-secret-value")
    write_scenario(repo, stdout=[RESULT_LINE], record=str(tmp_path / "seen.json"))
    git(repo, "add", "fake-claude.json")
    git(repo, "commit", "-m", "record")
    path = write_task(tmp_path, task_text())

    code, out, err = run_cli(capsys, tmp_path, str(path), "--repo", str(repo))

    assert code == 0
    assert "SECRET_X" not in read_record(tmp_path / "seen.json")["env"]
    run_dir = next((tmp_path / "out").iterdir())
    for text in (out, err, (run_dir / "results.json").read_text()):
        assert "super-secret-value" not in text
        assert "SECRET_X" not in text


@pytest.fixture
def restore_signals() -> Iterator[None]:
    saved = {sig: signal.getsignal(sig) for sig in (signal.SIGTERM, signal.SIGHUP)}
    yield
    for sig, handler in saved.items():
        signal.signal(sig, handler)


@pytest.mark.parametrize("sig", [signal.SIGTERM, signal.SIGHUP])
def test_sigterm_handler_raises_keyboard_interrupt(
    sig: signal.Signals, restore_signals: None
) -> None:
    install_signal_handlers()

    with pytest.raises(KeyboardInterrupt):
        os.kill(os.getpid(), sig)
        signal.pause()  # pragma: no cover - the handler raises before we get here
