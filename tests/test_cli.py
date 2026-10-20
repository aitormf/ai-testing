from collections.abc import Callable
from pathlib import Path

import pytest

from ia_testing.cli import cli_app

_VALID = """\
type = "code-generation"
prompt = "Write it"

[[runners]]
id = "a"
runner = "claude"
model = "m1"

[[runners]]
id = "b"
runner = "codex"
model = "m2"
local = true
"""


def test_validate_valid_file_prints_ok(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    path = tmp_path / "task.toml"
    path.write_text(_VALID, encoding="utf-8")

    code = cli_app(["validate", str(path)])

    captured = capsys.readouterr()
    assert code == 0
    assert captured.out == "OK\n"
    assert captured.err == ""


def test_validate_invalid_file_reports_all_errors_in_order(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    path = tmp_path / "task.toml"
    path.write_text(
        _VALID.replace('model = "m1"', 'modle = "leaked-value"\nmodel = "m1"').replace(
            '"codex"', '"gemini"'
        ),
        encoding="utf-8",
    )

    code = cli_app(["validate", str(path)])

    captured = capsys.readouterr()
    assert code == 1
    assert captured.out == ""
    assert captured.err.splitlines() == [
        "runners[0].modle: unknown key",
        "runners[1].runner: unknown runner: expected one of claude, codex, opencode",
    ]
    assert "Traceback" not in captured.err
    assert "leaked-value" not in captured.err
    assert "gemini" not in captured.err


def test_validate_credential_value_is_not_printed(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    path = tmp_path / "task.toml"
    path.write_text(_VALID.replace('model = "m1"', 'model = "m1"\napi_key = "s3cr3t"'), "utf-8")

    code = cli_app(["validate", str(path)])

    captured = capsys.readouterr()
    assert code == 1
    assert "runners[0].api_key: unknown key" in captured.err
    assert "s3cr3t" not in captured.err
    assert captured.out == ""


def _make_missing(tmp_path: Path) -> Path:
    return tmp_path / "missing.toml"


def _make_directory(tmp_path: Path) -> Path:
    return tmp_path


def _make_binary(tmp_path: Path) -> Path:
    path = tmp_path / "binary.toml"
    path.write_bytes(bytes(range(256)) * 80)
    return path


def _make_malformed(tmp_path: Path) -> Path:
    path = tmp_path / "bad.toml"
    path.write_text('type = "code-review"\n\nprompt = = 1\n', encoding="utf-8")
    return path


@pytest.mark.parametrize("make", [_make_missing, _make_directory, _make_binary, _make_malformed])
def test_validate_unreadable_or_malformed_file_fails(
    make: Callable[[Path], Path], tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    path = make(tmp_path)

    code = cli_app(["validate", str(path)])

    captured = capsys.readouterr()
    assert code == 1
    assert captured.out == ""
    assert captured.err.startswith(f"{path}: ")
    assert "Traceback" not in captured.err
