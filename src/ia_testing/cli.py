"""Command-line entry point: parse arguments, wire adapters and delegate to app."""

import sys
from pathlib import Path

from cyclopts import App

from ia_testing.adapters.report.validation import print_validation
from ia_testing.adapters.runners.registry import RUNNER_NAMES
from ia_testing.adapters.task_file import TomlTaskFileSource
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


def main() -> None:
    sys.exit(cli_app())
