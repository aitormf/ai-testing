"""Run an external tool with logs, secret masking, a timeout and guaranteed process cleanup.

Every runner that launches a CLI uses `run_logged`: it is the only place in the runners where a
process is started and where its whole process group is terminated.
"""

import contextlib
import os
import signal
import subprocess
import threading
import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import IO, cast

_MASK = b"***"
_POLL_S = 0.2
_GRACE_S = 5.0  # between SIGTERM and SIGKILL
_JOIN_S = 5.0  # maximum wait for each I/O thread
_START_ERROR = "cannot start process"


@dataclass(frozen=True)
class ProcessResult:
    """Outcome of `run_logged`. `returncode` is None only when the process never started."""

    returncode: int | None
    timed_out: bool
    start_error: str | None  # fixed reason, never the text of the OS error


def run_logged(
    argv: Sequence[str],
    cwd: Path,
    env: Mapping[str, str],
    stdin_text: str,
    timeout_s: float,
    stdout_path: Path,
    stderr_path: Path,
    secrets: Sequence[str],
) -> ProcessResult:
    """Run `argv` in its own process group, logging stdout and stderr to separate files.

    The process gets exactly `env`, no shell, and `stdin_text` on stdin. Every value of `secrets`
    is replaced by `***` in the logs. Whatever happens (normal exit, timeout or interrupt) the
    whole process group is terminated before returning, so no descendant survives. A
    `KeyboardInterrupt` is re-raised after that cleanup.
    """
    try:
        stdout_path.write_bytes(b"")
        stderr_path.write_bytes(b"")
        proc = subprocess.Popen(  # noqa: S603 security-reviewed: argument list without shell; callers pass an absolute executable and untrusted text only as arguments or stdin
            list(argv),
            cwd=cwd,
            env=dict(env),
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            start_new_session=True,
        )
    except OSError:
        return ProcessResult(returncode=None, timed_out=False, start_error=_START_ERROR)

    masks = tuple(sorted((s.encode() for s in secrets if s), key=len, reverse=True))
    threads = [
        threading.Thread(target=_feed, args=(cast(IO[bytes], proc.stdin), stdin_text), daemon=True),
        threading.Thread(
            target=_pump, args=(cast(IO[bytes], proc.stdout), stdout_path, masks), daemon=True
        ),
        threading.Thread(
            target=_pump, args=(cast(IO[bytes], proc.stderr), stderr_path, masks), daemon=True
        ),
    ]
    for thread in threads:
        thread.start()

    timed_out = False
    try:
        timed_out = not _wait(proc, timeout_s)
    finally:  # normal exit, timeout and KeyboardInterrupt all end here, which then propagates
        _terminate_group(proc)
        for thread in threads:
            thread.join(timeout=_JOIN_S)
    return ProcessResult(returncode=proc.returncode, timed_out=timed_out, start_error=None)


def _wait(proc: "subprocess.Popen[bytes]", timeout_s: float) -> bool:
    """Wait for the process; return False on timeout. Polls so a Ctrl-C is served promptly."""
    deadline = time.monotonic() + timeout_s
    while True:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return False
        try:
            proc.wait(timeout=min(_POLL_S, remaining))
        except subprocess.TimeoutExpired:
            continue
        return True


def _terminate_group(proc: "subprocess.Popen[bytes]") -> None:
    """SIGTERM the group, give it a grace period, then SIGKILL whatever is left."""
    pgid = proc.pid  # start_new_session makes the process its own group leader
    if _signal_group(pgid, signal.SIGTERM):
        deadline = time.monotonic() + _GRACE_S
        while time.monotonic() < deadline:
            proc.poll()  # reaps the leader so only real survivors keep the group alive
            if not _signal_group(pgid, 0):
                break
            time.sleep(0.02)
        _signal_group(pgid, signal.SIGKILL)
    with contextlib.suppress(subprocess.TimeoutExpired):
        proc.wait(timeout=_GRACE_S)


def _signal_group(pgid: int, sig: int) -> bool:
    """Send `sig` to the group; False if the group no longer exists."""
    try:
        os.killpg(pgid, sig)
    except OSError:
        return False
    return True


def _feed(stream: IO[bytes], text: str) -> None:
    """Write the prompt and close stdin; a process that stops reading is not an error."""
    with contextlib.suppress(OSError):
        try:
            stream.write(text.encode("utf-8"))
        finally:
            stream.close()


def _pump(stream: IO[bytes], path: Path, secrets: tuple[bytes, ...]) -> None:
    """Copy `stream` to `path` line by line in bytes: only the secrets change (RF-23, RF-24)."""
    try:
        with stream, path.open("ab") as out:
            for line in stream:
                for secret in secrets:
                    line = line.replace(secret, _MASK)
                out.write(line)
                out.flush()
    except (OSError, ValueError):
        pass
