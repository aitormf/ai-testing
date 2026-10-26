"""Tests for the Claude Code runner: pure functions plus a fake `claude` executable."""

import json
import os
import signal
import threading
import time
from collections.abc import Iterator
from pathlib import Path

import pytest
from fakes import (
    DEADLINE_S,
    assert_dies,
    install_fake_claude,
    kill_if_alive,
    read_record,
    wait_for_pid,
    write_scenario,
)

from ia_testing.adapters.runners._summary import OutputSummary
from ia_testing.adapters.runners.claude import (
    ClaudeRunner,
    build_argv,
    build_env,
    parse_result,
)
from ia_testing.domain.run import RunRequest, RunStatus
from ia_testing.domain.task_file import RunnerConfig

REAL_CAPTURE = Path(__file__).parent / "data" / "claude-stream-2.1.303.jsonl"
API_KEY = "sk-test-0123456789"
ALLOWED_ENV = {"PATH", "HOME", "USER", "LANG", "LC_ALL", "TERM", "TMPDIR"}


def config(
    *, model: str = "haiku", prompt: str = "Do the thing", local: bool = False, id: str = "c1"
) -> RunnerConfig:
    return RunnerConfig(id=id, runner="claude", model=model, local=local, prompt=prompt)


@pytest.fixture
def workdir(tmp_path: Path) -> Path:
    path = tmp_path / "work"
    path.mkdir()
    return path


@pytest.fixture
def fake_claude(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    for name in ("ANTHROPIC_API_KEY", "CLAUDE_CODE_OAUTH_TOKEN"):
        monkeypatch.delenv(name, raising=False)
    return install_fake_claude(tmp_path, monkeypatch)


@pytest.fixture
def tracked_pids() -> Iterator[list[int]]:
    pids: list[int] = []
    yield pids
    for pid in pids:
        kill_if_alive(pid)


def request(
    tmp_path: Path, workdir: Path, cfg: RunnerConfig, timeout_s: float = 30.0
) -> RunRequest:
    return RunRequest(
        config=cfg,
        workdir=workdir,
        timeout_s=timeout_s,
        stdout_log=tmp_path / "out.jsonl",
        stderr_log=tmp_path / "err.log",
    )


def result_event(**fields: object) -> str:
    return json.dumps({"type": "result", **fields})


# --- pure functions -----------------------------------------------------------------------


def test_argv_does_not_restrict_settings() -> None:
    argv = build_argv("/usr/bin/claude", "haiku")

    assert argv == [
        "/usr/bin/claude",
        "-p",
        "--model=haiku",
        "--output-format",
        "stream-json",
        "--verbose",
        "--permission-mode",
        "bypassPermissions",
    ]
    assert not any(a.startswith(("--setting-sources", "--bare")) for a in argv)  # RF-13


def test_argv_keeps_option_like_model_attached_to_its_flag() -> None:
    assert build_argv("/x/claude", "--help")[2] == "--model=--help"


def test_build_env_keeps_only_allowed_vars() -> None:
    source = {
        "PATH": "/bin",
        "HOME": "/home/u",
        "LANG": "C",
        "SECRET_X": "hunter2",
        "AWS_SECRET_ACCESS_KEY": "aws",
        "ANTHROPIC_API_KEY": API_KEY,
        "CLAUDE_CODE_OAUTH_TOKEN": "",
    }

    env, secrets = build_env(source)

    assert env == {
        "PATH": "/bin",
        "HOME": "/home/u",
        "LANG": "C",
        "ANTHROPIC_API_KEY": API_KEY,
        "CLAUDE_CODE_OAUTH_TOKEN": "",
    }
    assert secrets == (API_KEY,)  # empty values are not secrets (masking "" would corrupt logs)


def test_build_env_with_nothing_set() -> None:
    assert build_env({"SECRET_X": "x"}) == ({}, ())


def test_parse_result_real_capture() -> None:
    parsed = parse_result(REAL_CAPTURE)

    assert parsed == OutputSummary(
        is_error=False, cost_usd=0.00251437, input_tokens=2 + 11976 + 11697, output_tokens=4
    )


def test_parse_result_sums_cache_tokens(tmp_path: Path) -> None:
    path = tmp_path / "s.jsonl"
    path.write_text(
        result_event(
            is_error=True,
            total_cost_usd=1.5,
            usage={
                "input_tokens": 10,
                "cache_read_input_tokens": 200,
                "cache_creation_input_tokens": 3000,
                "output_tokens": 40,
            },
        )
        + "\n"
    )

    assert parse_result(path) == OutputSummary(
        is_error=True, cost_usd=1.5, input_tokens=3210, output_tokens=40
    )


def test_parse_result_uses_the_last_result_event(tmp_path: Path) -> None:
    path = tmp_path / "s.jsonl"
    path.write_text(
        "\n".join(
            [
                result_event(is_error=True, total_cost_usd=1.0),
                json.dumps({"type": "assistant"}),
                result_event(is_error=False, total_cost_usd=2.0),
            ]
        )
    )

    assert parse_result(path) == OutputSummary(
        is_error=False, cost_usd=2.0, input_tokens=None, output_tokens=None
    )


@pytest.mark.parametrize(
    "content",
    [
        "",
        "not json at all\n{broken\n",
        '[1, 2]\n"text"\n42\nnull\n',
        json.dumps({"type": "assistant", "message": {}}) + "\n",
        result_event() + "\n",
        result_event(usage="oops", total_cost_usd="1.0", is_error="yes") + "\n",
        result_event(usage={"input_tokens": True, "output_tokens": "4"}) + "\n",
    ],
)
def test_parse_result_tolerates_missing_fields(tmp_path: Path, content: str) -> None:
    path = tmp_path / "s.jsonl"
    path.write_text(content)

    assert parse_result(path) == OutputSummary(
        is_error=False, cost_usd=None, input_tokens=None, output_tokens=None
    )


def test_parse_result_partial_usage(tmp_path: Path) -> None:
    path = tmp_path / "s.jsonl"
    path.write_text(result_event(usage={"output_tokens": 7, "input_tokens": 5}) + "\n")

    assert parse_result(path) == OutputSummary(
        is_error=False, cost_usd=None, input_tokens=5, output_tokens=7
    )


def test_parse_result_ignores_invalid_utf8_and_missing_file(tmp_path: Path) -> None:
    path = tmp_path / "s.jsonl"
    path.write_bytes(b"\xff\xfe garbage\n" + result_event(is_error=True).encode() + b"\n")
    empty = OutputSummary(is_error=False, cost_usd=None, input_tokens=None, output_tokens=None)

    assert parse_result(path).is_error is True
    assert parse_result(tmp_path / "missing.jsonl") == empty


# --- check ---------------------------------------------------------------------------------


def test_check_missing_claude_errors(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    empty_dir = tmp_path / "empty"
    empty_dir.mkdir()
    monkeypatch.setenv("PATH", str(empty_dir))

    check = ClaudeRunner().check([config()])

    assert check.error is not None
    assert "claude" in check.error


def test_check_warns_bypass(fake_claude: Path) -> None:
    check = ClaudeRunner().check([config()])  # RF-12

    assert check.error is None
    assert len(check.warnings) == 1
    assert "bypassPermissions" in check.warnings[0]


def test_check_warns_on_local(fake_claude: Path) -> None:
    check = ClaudeRunner().check([config(id="a"), config(id="b", local=True)])  # RF-15

    assert check.error is None
    local_warnings = [w for w in check.warnings if "local" in w]
    assert len(local_warnings) == 1
    assert "'b'" in local_warnings[0]


# --- run, with the fake claude -------------------------------------------------------------


def test_successful_run_with_real_capture(tmp_path: Path, workdir: Path, fake_claude: Path) -> None:
    lines = REAL_CAPTURE.read_text().splitlines()
    write_scenario(workdir, stdout=lines)

    execution = ClaudeRunner().run(request(tmp_path, workdir, config()))

    assert execution.status is RunStatus.SUCCEEDED
    assert execution.reason is None
    assert execution.cost_usd == 0.00251437
    assert execution.input_tokens == 23675
    assert execution.output_tokens == 4
    assert execution.duration_s > 0


def test_nonzero_exit_fails(tmp_path: Path, workdir: Path, fake_claude: Path) -> None:
    write_scenario(workdir, exit_code=3, stderr="Not logged in")

    execution = ClaudeRunner().run(request(tmp_path, workdir, config()))

    assert execution.status is RunStatus.FAILED
    assert execution.reason == "claude exited with code 3"
    assert "Not logged in" not in (execution.reason or "")  # never agent output in the reason


def test_exit_0_with_is_error_fails(tmp_path: Path, workdir: Path, fake_claude: Path) -> None:
    write_scenario(workdir, stdout=[result_event(is_error=True, subtype="success")])

    execution = ClaudeRunner().run(request(tmp_path, workdir, config()))

    assert execution.status is RunStatus.FAILED
    assert execution.reason == "claude reported an error"


def test_nonzero_exit_takes_precedence_over_is_error(
    tmp_path: Path, workdir: Path, fake_claude: Path
) -> None:
    write_scenario(workdir, exit_code=1, stdout=[result_event(is_error=True)])

    execution = ClaudeRunner().run(request(tmp_path, workdir, config()))

    assert execution.reason == "claude exited with code 1"


def test_exit_0_without_result_event_succeeds_without_cost(
    tmp_path: Path, workdir: Path, fake_claude: Path
) -> None:
    write_scenario(workdir, stdout=["not json", json.dumps({"type": "assistant"})])

    execution = ClaudeRunner().run(request(tmp_path, workdir, config()))

    assert execution.status is RunStatus.SUCCEEDED
    assert (execution.cost_usd, execution.input_tokens, execution.output_tokens) == (None,) * 3


def test_claude_missing_at_run_time_fails(
    tmp_path: Path, workdir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    empty_dir = tmp_path / "empty"
    empty_dir.mkdir()
    monkeypatch.setenv("PATH", str(empty_dir))

    execution = ClaudeRunner().run(request(tmp_path, workdir, config()))

    assert execution.status is RunStatus.FAILED
    assert execution.reason == "cannot start claude"


def test_missing_workdir_fails_without_raising(tmp_path: Path, fake_claude: Path) -> None:
    execution = ClaudeRunner().run(request(tmp_path, tmp_path / "nope", config()))

    assert execution.status is RunStatus.FAILED
    assert execution.reason == "cannot start claude"


def test_argument_with_nul_byte_fails_without_raising(
    tmp_path: Path, workdir: Path, fake_claude: Path
) -> None:
    execution = ClaudeRunner().run(request(tmp_path, workdir, config(model="a\x00b")))

    assert execution.status is RunStatus.FAILED
    assert execution.reason == "cannot start claude"


def test_timeout_kills_process_group(
    tmp_path: Path, workdir: Path, fake_claude: Path, tracked_pids: list[int]
) -> None:
    child_pid_file, own_pid_file = tmp_path / "child.pid", tmp_path / "own.pid"
    write_scenario(
        workdir,
        pid_file=str(own_pid_file),
        child={"pid_file": str(child_pid_file)},
        sleep_s=300,
    )

    started = time.monotonic()
    execution = ClaudeRunner().run(request(tmp_path, workdir, config(), timeout_s=3.0))

    assert execution.status is RunStatus.FAILED
    assert execution.reason == "timeout"
    assert time.monotonic() - started < DEADLINE_S
    tracked_pids += [wait_for_pid(child_pid_file), wait_for_pid(own_pid_file)]
    for pid in tracked_pids:
        assert_dies(pid)


def test_interrupt_kills_group_and_reraises(
    tmp_path: Path, workdir: Path, fake_claude: Path, tracked_pids: list[int]
) -> None:
    child_pid_file, own_pid_file = tmp_path / "child.pid", tmp_path / "own.pid"
    write_scenario(
        workdir,
        pid_file=str(own_pid_file),
        child={"pid_file": str(child_pid_file)},
        sleep_s=300,
    )
    runner_thread = threading.get_ident()

    def interrupt_when_child_runs() -> None:
        deadline = time.monotonic() + DEADLINE_S
        while not child_pid_file.exists() and time.monotonic() < deadline:
            time.sleep(0.02)
        signal.pthread_kill(runner_thread, signal.SIGINT)

    interrupter = threading.Thread(target=interrupt_when_child_runs, daemon=True)
    interrupter.start()
    try:
        with pytest.raises(KeyboardInterrupt):
            ClaudeRunner().run(request(tmp_path, workdir, config(), timeout_s=60.0))
    finally:
        interrupter.join()

    tracked_pids += [wait_for_pid(child_pid_file), wait_for_pid(own_pid_file)]
    for pid in tracked_pids:
        assert_dies(pid)


def test_secret_env_not_passed(
    tmp_path: Path, workdir: Path, fake_claude: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("SECRET_X", "hunter2-do-not-leak")
    monkeypatch.setenv("ANTHROPIC_API_KEY", API_KEY)
    record = tmp_path / "record.json"
    write_scenario(workdir, record=str(record))

    ClaudeRunner().run(request(tmp_path, workdir, config()))

    received = read_record(record)["env"]
    assert "SECRET_X" not in received
    assert "hunter2-do-not-leak" not in json.dumps(received)
    assert set(received) <= ALLOWED_ENV | {"ANTHROPIC_API_KEY", "CLAUDE_CODE_OAUTH_TOKEN"}
    assert received["ANTHROPIC_API_KEY"] == API_KEY  # credentials of RF-14 do reach the agent
    assert received["PATH"] == os.environ["PATH"]


def test_credential_masked_in_logs(
    tmp_path: Path, workdir: Path, fake_claude: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", API_KEY)
    write_scenario(workdir, echo_env=["ANTHROPIC_API_KEY"])
    req = request(tmp_path, workdir, config())

    ClaudeRunner().run(req)

    stdout, stderr = req.stdout_log.read_text(), req.stderr_log.read_text()
    assert API_KEY not in stdout
    assert API_KEY not in stderr
    assert json.loads(stdout.splitlines()[0]) == {"type": "leak", "value": "***"}
    assert stderr.strip() == "***"


def test_stdout_and_stderr_logs(tmp_path: Path, workdir: Path, fake_claude: Path) -> None:
    lines = REAL_CAPTURE.read_text().splitlines()
    write_scenario(workdir, stdout=lines, stderr="a warning")
    req = request(tmp_path, workdir, config())

    ClaudeRunner().run(req)

    logged = req.stdout_log.read_text().splitlines()
    assert logged == lines
    assert all(isinstance(json.loads(line), dict) for line in logged)
    assert req.stderr_log.read_text() == "a warning\n"


def test_argv_and_stdin_are_literal(tmp_path: Path, workdir: Path, fake_claude: Path) -> None:
    model = "-x; touch pwned-model $(touch pwned-model-2)"
    prompt = "--help; touch pwned-prompt\n$(touch pwned-prompt-2) `touch pwned-prompt-3`"
    record = tmp_path / "record.json"
    write_scenario(workdir, record=str(record))

    ClaudeRunner().run(request(tmp_path, workdir, config(model=model, prompt=prompt)))

    received = read_record(record)
    assert received["argv"][1:] == build_argv("claude", model)[1:]
    assert received["argv"][2] == f"--model={model}"
    assert prompt not in received["argv"]
    assert received["stdin"] == prompt
    assert received["cwd"] == str(workdir.resolve())
    assert sorted(p.name for p in workdir.iterdir()) == ["fake-claude.json"]
