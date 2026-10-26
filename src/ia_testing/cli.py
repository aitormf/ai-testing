"""Command-line entry point: parse arguments, wire adapters and delegate to app."""

import signal
import sys
from datetime import datetime
from pathlib import Path
from types import FrameType
from typing import Annotated

from cyclopts import App, Parameter, validators

from ia_testing.adapters.report.run import print_run
from ia_testing.adapters.report.validation import print_validation
from ia_testing.adapters.runners.registry import RUNNER_NAMES, build_runners
from ia_testing.adapters.storage.json_store import JsonResultStore
from ia_testing.adapters.task_file import TomlTaskFileSource
from ia_testing.adapters.workspace.git import GitWorkspace
from ia_testing.app.run import RunOptions, run_task
from ia_testing.app.task_file import validate_task_file

cli_app = App(name="ia-testing", result_action="return_value")


@cli_app.command
def validate(file: Path) -> int:
    """Validate a task file.

    Parameters
    ----------
    file
        Path to the TOML task file.
    """
    errors = validate_task_file(TomlTaskFileSource(file), RUNNER_NAMES)
    return print_validation(errors, sys.stdout, sys.stderr)


def _warn(message: str) -> None:
    sys.stderr.write(f"warning: {message}\n")


@cli_app.command
def run(
    file: Path,
    *,
    repo: Path | None = None,
    ref: str = "HEAD",
    timeout: Annotated[int, Parameter(validator=validators.Number(gt=0))] = 30,
    output_dir: Path | None = None,
) -> int:
    """Run a task file: one git worktree and one agent run per runner configuration.

    The agents run without permission restrictions (see docs/run.md).

    Parameters
    ----------
    file
        Path to the TOML task file.
    repo
        Repository to evaluate; its root is used. Defaults to the current directory.
    ref
        Commit, branch or tag every worktree starts from.
    timeout
        Timeout of each runner configuration, in minutes (greater than 0).
    output_dir
        Base directory for the run directory. Defaults to a directory named after the repository plus '.ia-testing', next to it.
    """
    options = RunOptions(
        now=datetime.now().astimezone(), ref=ref, timeout_minutes=timeout, output_dir=output_dir
    )
    outcome = run_task(
        TomlTaskFileSource(file),
        build_runners(),
        GitWorkspace(repo),
        JsonResultStore(),
        options,
        _warn,
    )
    return print_run(outcome, sys.stdout, sys.stderr)


def _interrupt(signum: int, frame: FrameType | None) -> None:
    raise KeyboardInterrupt


def install_signal_handlers() -> None:
    """Treat SIGTERM and SIGHUP like Ctrl-C so the agent's process group is terminated."""
    signal.signal(signal.SIGTERM, _interrupt)
    signal.signal(signal.SIGHUP, _interrupt)


def main() -> None:
    install_signal_handlers()
    sys.exit(cli_app())
