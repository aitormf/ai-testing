"""Write the outcome of `validate` and return the process exit code."""

from collections.abc import Sequence
from typing import TextIO

from ia_testing.domain.task_file import FieldError


def print_validation(errors: Sequence[FieldError], out: TextIO, err: TextIO) -> int:
    """Write `OK` to out (return 0) or one `<path>: <reason>` line per error to err (return 1)."""
    if not errors:
        out.write("OK\n")
        return 0
    for error in errors:
        err.write(f"{error}\n")
    return 1
