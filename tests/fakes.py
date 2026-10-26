"""A fake `claude` executable for the tests of the Claude runner.

The test writes a script into `tmp_path` (shebang with `sys.executable`, executable bit) and puts
its directory first in `PATH`. The script reads its scenario from `fake-claude.json` in its
working directory, because `build_env` does not let control variables through, and records what it
received (argv, stdin, environment, cwd) in the file named by the scenario's `record` key.

Scenario keys, all optional:
- `record`: path where argv, stdin, environment and cwd are written as JSON;
- `pid_file`: path where the fake writes its own PID;
- `child`: `{"pid_file": path}`; starts a child that sleeps and writes its PID there. The child
  inherits stdout and stderr, so it keeps the pipes open if nobody kills it;
- `stdout`: lines printed to stdout;
- `stderr`: text printed to stderr;
- `echo_env`: names of environment variables whose value is printed to stdout (as a JSON line)
  and to stderr;
- `sleep_s`: seconds to sleep before exiting;
- `exit_code`: exit code (0 by default).
"""

import contextlib
import json
import os
import stat
import sys
import time
from pathlib import Path
from typing import Any

import pytest

SCENARIO_FILE = "fake-claude.json"
DEADLINE_S = 15.0

_SCRIPT = """
import json
import os
import subprocess
import sys
import time

_CHILD = (
    "import os, sys, time\\n"
    "open(sys.argv[1] + '.tmp', 'w').write(str(os.getpid()))\\n"
    "os.replace(sys.argv[1] + '.tmp', sys.argv[1])\\n"
    "time.sleep(300)\\n"
)


def write_pid(path):
    with open(path + ".tmp", "w") as handle:
        handle.write(str(os.getpid()))
    os.replace(path + ".tmp", path)


with open("fake-claude.json") as handle:
    scenario = json.load(handle)
stdin_text = sys.stdin.read()
if scenario.get("record"):
    with open(scenario["record"], "w") as handle:
        json.dump(
            {"argv": sys.argv, "stdin": stdin_text, "env": dict(os.environ), "cwd": os.getcwd()},
            handle,
        )
if scenario.get("pid_file"):
    write_pid(scenario["pid_file"])
child = scenario.get("child")
if child:
    subprocess.Popen([sys.executable, "-c", _CHILD, child["pid_file"]])
    while not os.path.exists(child["pid_file"]):
        time.sleep(0.02)
for line in scenario.get("stdout", []):
    print(line, flush=True)
for name in scenario.get("echo_env", []):
    print(json.dumps({"type": "leak", "value": os.environ.get(name, "")}), flush=True)
    print(os.environ.get(name, ""), file=sys.stderr, flush=True)
if scenario.get("stderr"):
    print(scenario["stderr"], file=sys.stderr, flush=True)
time.sleep(scenario.get("sleep_s", 0))
sys.exit(scenario.get("exit_code", 0))
"""


def install_fake_claude(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Create the fake `claude`, put it first in `PATH` and return its path."""
    bin_dir = tmp_path / "fake-bin"
    bin_dir.mkdir()
    executable = bin_dir / "claude"
    executable.write_text(f"#!{sys.executable}\n{_SCRIPT}")
    executable.chmod(executable.stat().st_mode | stat.S_IXUSR)
    monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ.get('PATH', '')}")
    return executable


def write_scenario(workdir: Path, **scenario: Any) -> None:
    (workdir / SCENARIO_FILE).write_text(json.dumps(scenario))


def read_record(path: Path) -> dict[str, Any]:
    recorded: dict[str, Any] = json.loads(path.read_text())
    return recorded


def wait_for_pid(path: Path) -> int:
    deadline = time.monotonic() + DEADLINE_S
    while time.monotonic() < deadline:
        if path.exists():
            return int(path.read_text())
        time.sleep(0.02)
    raise AssertionError(f"{path.name} was never written")


def kill_if_alive(pid: int) -> None:
    """Teardown helper: never leave a sleeper behind if an assertion failed."""
    with contextlib.suppress(OSError):
        os.kill(pid, 9)


def is_dead(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return True
    try:  # a zombie nobody reaped (e.g. a container without init) is dead for our purposes
        stat_line = Path(f"/proc/{pid}/stat").read_text()
    except OSError:
        return False
    return stat_line.rsplit(")", 1)[1].split()[0] == "Z"


def assert_dies(pid: int) -> None:
    deadline = time.monotonic() + DEADLINE_S
    while time.monotonic() < deadline:
        if is_dead(pid):
            return
        time.sleep(0.02)
    raise AssertionError(f"process {pid} is still alive")
