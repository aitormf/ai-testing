import os
from pathlib import Path

import pytest

from ia_testing.adapters.task_file import TomlTaskFileSource
from ia_testing.domain.task_file import FieldError, InvalidTaskFile


def _read_error(path: Path) -> tuple[FieldError, ...]:
    with pytest.raises(InvalidTaskFile) as excinfo:
        TomlTaskFileSource(path).read()
    return excinfo.value.errors


def test_valid_file_is_parsed(tmp_path: Path) -> None:
    path = tmp_path / "task.toml"
    path.write_text('type = "code-review"\n', encoding="utf-8")

    assert TomlTaskFileSource(path).read() == {"type": "code-review"}


def test_missing_file(tmp_path: Path) -> None:
    path = tmp_path / "nope.toml"

    assert _read_error(path) == (FieldError(str(path), "file not found"),)


def test_directory(tmp_path: Path) -> None:
    assert _read_error(tmp_path) == (FieldError(str(tmp_path), "is a directory"),)


@pytest.mark.skipif(os.geteuid() == 0, reason="root can read any file")
def test_unreadable_file(tmp_path: Path) -> None:
    path = tmp_path / "task.toml"
    path.write_text('type = "code-review"\n', encoding="utf-8")
    path.chmod(0)

    assert _read_error(path) == (FieldError(str(path), "permission denied"),)


def test_not_a_directory(tmp_path: Path) -> None:
    regular = tmp_path / "file.txt"
    regular.write_text("x", encoding="utf-8")
    path = regular / "task.toml"

    assert _read_error(path) == (FieldError(str(path), "cannot read file"),)


def test_binary_file(tmp_path: Path) -> None:
    path = tmp_path / "task.toml"
    path.write_bytes(bytes(range(256)) * 80)

    assert _read_error(path) == (FieldError(str(path), "not valid UTF-8"),)


def test_malformed_toml_reports_line(tmp_path: Path) -> None:
    path = tmp_path / "task.toml"
    path.write_text('type = "code-review"\n\nprompt = = 1\n', encoding="utf-8")

    (error,) = _read_error(path)

    assert error.path == str(path)
    assert error.reason == "invalid TOML at line 3, column 10"


def test_malformed_toml_does_not_echo_content(tmp_path: Path) -> None:
    path = tmp_path / "task.toml"
    path.write_text('api_key = "s3cr3t-value\n[oops s3cr3t-key\n', encoding="utf-8")

    errors = _read_error(path)

    assert errors
    for error in errors:
        assert "s3cr3t" not in str(error)
        assert str(error).startswith(f"{path}: invalid TOML")


def test_empty_file(tmp_path: Path) -> None:
    path = tmp_path / "task.toml"
    path.write_bytes(b"")

    assert TomlTaskFileSource(path).read() == {}


def test_utf8_bom_is_accepted(tmp_path: Path) -> None:
    path = tmp_path / "task.toml"
    path.write_bytes(b"\xef\xbb\xbf" + b'type = "code-review"\n')

    assert TomlTaskFileSource(path).read() == {"type": "code-review"}
