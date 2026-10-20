from pathlib import Path

from ia_testing.adapters.task_file import TomlTaskFileSource
from ia_testing.app.task_file import validate_task_file
from ia_testing.domain.task_file import FieldError

_VALID = """\
type = "code-generation"
prompt = "Write it"

[[runners]]
id = "a"
runner = "claude"
model = "m"
"""


def test_validate_task_file_returns_errors_or_empty(tmp_path: Path) -> None:
    valid = tmp_path / "valid.toml"
    valid.write_text(_VALID, encoding="utf-8")
    invalid = tmp_path / "invalid.toml"
    invalid.write_text(_VALID.replace('"claude"', '"gemini"'), encoding="utf-8")
    missing = tmp_path / "missing.toml"
    names = ("claude", "codex")

    assert validate_task_file(TomlTaskFileSource(valid), names) == ()
    assert validate_task_file(TomlTaskFileSource(invalid), names) == (
        FieldError("runners[0].runner", "unknown runner: expected one of claude, codex"),
    )
    assert validate_task_file(TomlTaskFileSource(missing), names) == (
        FieldError(str(missing), "file not found"),
    )
