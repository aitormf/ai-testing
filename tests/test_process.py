"""Tests for run_logged: real child processes, tiny Python scripts, no patching of subprocess."""

import contextlib
import json
import os
import signal
import sys
import textwrap
import threading
import time
from collections.abc import Iterator, Mapping, Sequence
from pathlib import Path

import pytest

from ia_testing.adapters.runners import _process
from ia_testing.adapters.runners._process import ProcessResult, run_logged

_DEADLINE_S = 15.0

_PRELUDE = """
import os, sys, time


def write_pid(path):
    tmp = path + ".tmp"
    with open(tmp, "w") as handle:
        handle.write(str(os.getpid()))
    os.replace(tmp, path)
"""

# Sleeps until it is killed; records its own pid.
_SLEEPER = (
    _PRELUDE
    + """
write_pid(sys.argv[1])
time.sleep(300)
"""
)

# Starts a sleeper child, waits until it is running, then runs `tail`.
_PARENT = (
    _PRELUDE
    + """
import subprocess

child_script, child_pid_file, own_pid_file = sys.argv[1:4]
write_pid(own_pid_file)
subprocess.Popen([sys.executable, child_script, child_pid_file])
while not os.path.exists(child_pid_file):
    time.sleep(0.02)
"""
)


@pytest.fixture
def tracked_pids() -> Iterator[list[int]]:
    """PIDs the test started; whatever is still alive at teardown is killed (no leaks)."""
    pids: list[int] = []
    yield pids
    for pid in pids:
        with contextlib.suppress(OSError):
            os.kill(pid, signal.SIGKILL)


def _write_script(tmp_path: Path, name: str, body: str) -> Path:
    path = tmp_path / name
    path.write_text(textwrap.dedent(body))
    return path


def _launch(
    tmp_path: Path,
    script: Path,
    *args: str,
    stdin: str = "",
    timeout_s: float = 30.0,
    secrets: Sequence[str] = (),
    env: Mapping[str, str] | None = None,
) -> ProcessResult:
    return run_logged(
        [sys.executable, str(script), *args],
        tmp_path,
        {} if env is None else env,
        stdin,
        timeout_s,
        tmp_path / "stdout.log",
        tmp_path / "stderr.log",
        secrets,
    )


def _stdout(tmp_path: Path) -> str:
    return (tmp_path / "stdout.log").read_text(encoding="utf-8")


def _stderr(tmp_path: Path) -> str:
    return (tmp_path / "stderr.log").read_text(encoding="utf-8")


def _wait_for_pid(path: Path, tracked: list[int]) -> int:
    deadline = time.monotonic() + _DEADLINE_S
    while time.monotonic() < deadline:
        if path.exists():
            pid = int(path.read_text())
            tracked.append(pid)
            return pid
        time.sleep(0.02)
    raise AssertionError(f"{path.name} was never written")


def _is_dead(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return True
    try:  # a zombie nobody reaped (e.g. a container without init) is dead for our purposes
        stat = Path(f"/proc/{pid}/stat").read_text()
    except OSError:
        return False
    return stat.rsplit(")", 1)[1].split()[0] == "Z"


def _assert_dies(pid: int) -> None:
    deadline = time.monotonic() + _DEADLINE_S
    while time.monotonic() < deadline:
        if _is_dead(pid):
            return
        time.sleep(0.02)
    raise AssertionError(f"process {pid} is still alive")


def test_stdout_and_stderr_go_to_separate_files(tmp_path: Path) -> None:
    script = _write_script(
        tmp_path,
        "s.py",
        """
        import sys
        print("to-out")
        print("to-err", file=sys.stderr)
        sys.exit(3)
        """,
    )

    result = _launch(tmp_path, script)

    assert result == ProcessResult(returncode=3, timed_out=False, start_error=None)
    assert _stdout(tmp_path) == "to-out\n"
    assert _stderr(tmp_path) == "to-err\n"


def test_stdin_text_is_delivered_and_env_is_exact(tmp_path: Path) -> None:
    script = _write_script(
        tmp_path,
        "s.py",
        """
        import os, sys
        print(sys.stdin.read())
        print(os.environ.get("ONLY_THIS"), "HOME" in os.environ, "PATH" in os.environ)
        """,
    )

    result = _launch(tmp_path, script, stdin="héllo", env={"ONLY_THIS": "1"})

    assert result.returncode == 0
    assert _stdout(tmp_path).splitlines()[0] == "héllo"
    assert _stdout(tmp_path).splitlines()[1] == "1 False False"


def test_secrets_masked_in_stdout_and_stderr(tmp_path: Path) -> None:
    script = _write_script(
        tmp_path,
        "s.py",
        """
        import sys
        print("key=sk-secret-1 and again sk-secret-1")
        print("token=tok-secret-2", file=sys.stderr)
        """,
    )

    _launch(tmp_path, script, secrets=["sk-secret-1", "tok-secret-2", ""])

    assert _stdout(tmp_path) == "key=*** and again ***\n"
    assert _stderr(tmp_path) == "token=***\n"


def test_non_utf8_output_is_logged(tmp_path: Path) -> None:
    script = _write_script(
        tmp_path,
        "s.py",
        """
        import sys
        sys.stdout.buffer.write(b"before \\xff\\xfe after\\n")
        sys.stdout.buffer.flush()
        sys.stderr.buffer.write(b"bad \\xc3\\x28\\n")
        sys.stderr.buffer.write(b"still-read\\n")
        """,
    )

    result = _launch(tmp_path, script)

    assert result.returncode == 0
    # RF-23: the log keeps the exact bytes; only secrets are masked.
    assert (tmp_path / "stdout.log").read_bytes() == b"before \xff\xfe after\n"
    assert (tmp_path / "stderr.log").read_bytes() == b"bad \xc3\x28\nstill-read\n"


def test_large_stdin_not_read_does_not_hang(tmp_path: Path) -> None:
    script = _write_script(tmp_path, "s.py", "import sys\nsys.exit(0)\n")

    started = time.monotonic()
    result = _launch(tmp_path, script, stdin="x" * 1_000_000, timeout_s=_DEADLINE_S * 2)

    assert result == ProcessResult(returncode=0, timed_out=False, start_error=None)
    assert time.monotonic() - started < _DEADLINE_S


def test_large_stdin_to_process_that_never_reads_times_out(
    tmp_path: Path, tracked_pids: list[int]
) -> None:
    script = _write_script(tmp_path, "s.py", _SLEEPER)
    pid_file = tmp_path / "pid"

    started = time.monotonic()
    result = _launch(tmp_path, script, str(pid_file), stdin="x" * 1_000_000, timeout_s=1.0)

    assert result.timed_out
    assert time.monotonic() - started < _DEADLINE_S
    if pid_file.exists():
        _assert_dies(_wait_for_pid(pid_file, tracked_pids))


def test_start_error(tmp_path: Path) -> None:
    result = run_logged(
        [str(tmp_path / "does-not-exist")],
        tmp_path,
        {},
        "",
        5.0,
        tmp_path / "stdout.log",
        tmp_path / "stderr.log",
        (),
    )

    assert result.start_error is not None
    assert result.returncode is None
    assert not result.timed_out
    assert str(tmp_path) not in result.start_error


def test_start_error_when_log_cannot_be_created(tmp_path: Path) -> None:
    script = _write_script(tmp_path, "s.py", "pass\n")

    result = run_logged(
        [sys.executable, str(script)],
        tmp_path,
        {},
        "",
        5.0,
        tmp_path / "missing-dir" / "stdout.log",
        tmp_path / "stderr.log",
        (),
    )

    assert result.start_error is not None
    assert result.returncode is None


def test_no_shell_interpretation(tmp_path: Path) -> None:
    script = _write_script(
        tmp_path,
        "s.py",
        """
        import json, sys
        print(json.dumps(sys.argv[1:]))
        """,
    )
    hostile = [f"-x; touch {tmp_path}/pwned $(touch {tmp_path}/pwned2) `id` | cat", "*", "$HOME"]

    result = _launch(tmp_path, script, *hostile, stdin="; touch pwned3")

    assert result.returncode == 0
    assert _stdout(tmp_path) == json.dumps(hostile) + "\n"
    assert not any(tmp_path.glob("pwned*"))


def test_timeout_kills_process_group(tmp_path: Path, tracked_pids: list[int]) -> None:
    parent = _write_script(tmp_path, "parent.py", _PARENT + "time.sleep(300)\n")
    child = _write_script(tmp_path, "child.py", _SLEEPER)
    child_pid_file, own_pid_file = tmp_path / "child.pid", tmp_path / "own.pid"

    started = time.monotonic()
    result = _launch(
        tmp_path, parent, str(child), str(child_pid_file), str(own_pid_file), timeout_s=3.0
    )

    assert result.timed_out
    assert result.start_error is None
    assert time.monotonic() - started < _DEADLINE_S
    _assert_dies(_wait_for_pid(child_pid_file, tracked_pids))
    _assert_dies(_wait_for_pid(own_pid_file, tracked_pids))


def test_process_ignoring_sigterm_is_killed_after_grace(
    tmp_path: Path, tracked_pids: list[int], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(_process, "_GRACE_S", 0.5)
    script = _write_script(
        tmp_path,
        "s.py",
        _PRELUDE
        + """
import signal

signal.signal(signal.SIGTERM, signal.SIG_IGN)
write_pid(sys.argv[1])
time.sleep(300)
""",
    )
    pid_file = tmp_path / "pid"

    result = _launch(tmp_path, script, str(pid_file), timeout_s=3.0)

    assert result.timed_out
    _assert_dies(_wait_for_pid(pid_file, tracked_pids))


def test_orphan_child_killed_after_normal_exit(tmp_path: Path, tracked_pids: list[int]) -> None:
    # The child inherits stdout and stderr, so the readers see no EOF until it dies.
    parent = _write_script(tmp_path, "parent.py", _PARENT)
    child = _write_script(tmp_path, "child.py", _SLEEPER)
    child_pid_file, own_pid_file = tmp_path / "child.pid", tmp_path / "own.pid"

    started = time.monotonic()
    result = _launch(
        tmp_path, parent, str(child), str(child_pid_file), str(own_pid_file), timeout_s=60.0
    )

    assert result == ProcessResult(returncode=0, timed_out=False, start_error=None)
    assert time.monotonic() - started < _DEADLINE_S
    _assert_dies(_wait_for_pid(child_pid_file, tracked_pids))


def test_escaped_child_holding_pipes_does_not_hang(
    tmp_path: Path, tracked_pids: list[int], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(_process, "_JOIN_S", 0.5)
    parent = _write_script(
        tmp_path,
        "parent.py",
        _PRELUDE
        + """
import subprocess

child_script, child_pid_file = sys.argv[1:3]
subprocess.Popen([sys.executable, child_script, child_pid_file], start_new_session=True)
while not os.path.exists(child_pid_file):
    time.sleep(0.02)
""",
    )
    child = _write_script(tmp_path, "child.py", _SLEEPER)
    child_pid_file = tmp_path / "child.pid"

    started = time.monotonic()
    try:
        result = _launch(tmp_path, parent, str(child), str(child_pid_file), timeout_s=60.0)
    finally:
        if child_pid_file.exists():
            _wait_for_pid(child_pid_file, tracked_pids)

    assert result.returncode == 0
    assert time.monotonic() - started < _DEADLINE_S


def test_interrupt_kills_group_and_reraises(tmp_path: Path, tracked_pids: list[int]) -> None:
    parent = _write_script(tmp_path, "parent.py", _PARENT + "time.sleep(300)\n")
    child = _write_script(tmp_path, "child.py", _SLEEPER)
    child_pid_file, own_pid_file = tmp_path / "child.pid", tmp_path / "own.pid"
    runner_thread = threading.get_ident()

    def interrupt_when_child_runs() -> None:
        deadline = time.monotonic() + _DEADLINE_S
        while not child_pid_file.exists() and time.monotonic() < deadline:
            time.sleep(0.02)
        signal.pthread_kill(runner_thread, signal.SIGINT)

    interrupter = threading.Thread(target=interrupt_when_child_runs, daemon=True)
    interrupter.start()
    try:
        with pytest.raises(KeyboardInterrupt):
            _launch(
                tmp_path,
                parent,
                str(child),
                str(child_pid_file),
                str(own_pid_file),
                timeout_s=60.0,
            )
    finally:
        interrupter.join()

    _assert_dies(_wait_for_pid(child_pid_file, tracked_pids))
    _assert_dies(_wait_for_pid(own_pid_file, tracked_pids))
