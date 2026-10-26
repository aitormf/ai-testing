"""Claude Code runner: launches `claude -p` in the worktree and reads its stream-json output."""

import json
import os
import shutil
import time
from collections.abc import Mapping, Sequence
from pathlib import Path

from ia_testing.adapters.runners._process import run_logged
from ia_testing.adapters.runners._summary import NO_OUTPUT, OutputSummary
from ia_testing.domain.run import Execution, RunnerCheck, RunRequest, RunStatus
from ia_testing.domain.task_file import RunnerConfig

_EXECUTABLE = "claude"

# RF-14: the agent gets only these variables, and only if they exist in the caller's environment.
_OPERATION_ENV = ("PATH", "HOME", "USER", "LANG", "LC_ALL", "TERM", "TMPDIR")
_CREDENTIAL_ENV = ("ANTHROPIC_API_KEY", "CLAUDE_CODE_OAUTH_TOKEN")

_BYPASS_WARNING = (
    "claude runs with bypassPermissions: the agent can read, write and run anything with your "
    "user's permissions; a worktree is not a sandbox"
)


def build_argv(exe: str, model: str) -> list[str]:
    """Arguments for a non-interactive run; the prompt goes through stdin, never in argv.

    `--model=<model>` keeps a model that starts with `-` from being read as an option. Neither
    `--setting-sources` nor `--bare` is passed: user and project settings load as usual (RF-13).
    """
    return [
        exe,
        "-p",
        f"--model={model}",
        "--output-format",
        "stream-json",
        "--verbose",
        "--permission-mode",
        "bypassPermissions",
    ]


def build_env(source_env: Mapping[str, str]) -> tuple[dict[str, str], tuple[str, ...]]:
    """Return the environment for the agent and the credential values to mask in its logs."""
    env = {
        name: source_env[name] for name in (*_OPERATION_ENV, *_CREDENTIAL_ENV) if name in source_env
    }
    secrets = tuple(env[name] for name in _CREDENTIAL_ENV if env.get(name))
    return env, secrets


def parse_result(jsonl_path: Path) -> OutputSummary:
    """Read cost, tokens and `is_error` from the last `result` event; tolerant of anything else."""
    last: dict[str, object] | None = None
    try:
        with jsonl_path.open(encoding="utf-8", errors="replace") as lines:
            for line in lines:
                event = _load_object(line)
                if event is not None and event.get("type") == "result":
                    last = event
    except OSError:
        return NO_OUTPUT
    if last is None:
        return NO_OUTPUT

    usage = last.get("usage")
    counts = usage if isinstance(usage, dict) else {}
    # Everything processed as input counts, cached or not.
    inputs = [
        _count(counts.get(name))
        for name in ("input_tokens", "cache_read_input_tokens", "cache_creation_input_tokens")
    ]
    present = [n for n in inputs if n is not None]
    cost = last.get("total_cost_usd")
    return OutputSummary(
        is_error=last.get("is_error") is True,
        cost_usd=_number(cost),
        input_tokens=sum(present) if present else None,
        output_tokens=_count(counts.get("output_tokens")),
    )


def _load_object(line: str) -> dict[str, object] | None:
    try:
        value = json.loads(line)
    except ValueError:
        return None
    return value if isinstance(value, dict) else None


def _number(value: object) -> float | None:
    if isinstance(value, int | float) and not isinstance(value, bool):
        return float(value)
    return None


def _count(value: object) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) else None


class ClaudeRunner:
    """Implements the `Runner` Protocol for Claude Code."""

    def check(self, configs: Sequence[RunnerConfig]) -> RunnerCheck:
        if shutil.which(_EXECUTABLE) is None:
            return RunnerCheck(error="claude executable not found in PATH", warnings=())
        warnings = [_BYPASS_WARNING]
        warnings += [
            f"config '{config.id}': the claude runner does not distinguish local models; "
            "it runs as with local = false"
            for config in configs
            if config.local
        ]
        return RunnerCheck(error=None, warnings=tuple(warnings))

    def run(self, request: RunRequest) -> Execution:
        started = time.monotonic()

        def failed(reason: str) -> Execution:
            return Execution(RunStatus.FAILED, reason, time.monotonic() - started)

        found = shutil.which(_EXECUTABLE)
        if found is None:
            return failed("cannot start claude")
        env, secrets = build_env(os.environ)
        try:
            process = run_logged(
                build_argv(os.path.abspath(found), request.config.model),
                request.workdir,
                env,
                request.config.prompt,
                request.timeout_s,
                request.stdout_log,
                request.stderr_log,
                secrets,
            )
        except ValueError:  # e.g. a NUL byte in an argument: nothing was started
            return failed("cannot start claude")
        if process.start_error is not None:
            return failed("cannot start claude")

        parsed = parse_result(request.stdout_log)
        reason = None
        if process.timed_out:
            reason = "timeout"
        elif process.returncode != 0:
            reason = f"claude exited with code {process.returncode}"
        elif parsed.is_error:
            reason = "claude reported an error"
        return Execution(
            status=RunStatus.SUCCEEDED if reason is None else RunStatus.FAILED,
            reason=reason,
            duration_s=time.monotonic() - started,
            cost_usd=parsed.cost_usd,
            input_tokens=parsed.input_tokens,
            output_tokens=parsed.output_tokens,
        )
