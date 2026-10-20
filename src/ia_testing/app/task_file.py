"""Use case: validate a task file."""

from collections.abc import Collection

from ia_testing.domain.task_file import (
    FieldError,
    InvalidTaskFile,
    TaskFileSource,
    parse_task_file,
)


def validate_task_file(
    source: TaskFileSource, runner_names: Collection[str]
) -> tuple[FieldError, ...]:
    """Return every error found in the task file; empty when it is valid."""
    try:
        parse_task_file(source.read(), runner_names)
    except InvalidTaskFile as exc:
        return exc.errors
    return ()
