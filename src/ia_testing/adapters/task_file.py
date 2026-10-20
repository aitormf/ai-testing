"""Read a task file from disk as TOML, turning every failure into InvalidTaskFile."""

import re
import tomllib
from collections.abc import Mapping
from pathlib import Path

from ia_testing.domain.task_file import FieldError, InvalidTaskFile

_POSITION = re.compile(r"line (\d+), column (\d+)")


class TomlTaskFileSource:
    """TaskFileSource backed by a TOML file.

    Error reasons never include the exception text or any file content: only the path
    as given, a fixed reason and, for TOML errors, the line and column.
    """

    def __init__(self, path: Path) -> None:
        self._path = path

    def read(self) -> Mapping[str, object]:
        try:
            text = self._path.read_bytes().decode("utf-8-sig")
        except FileNotFoundError:
            raise self._invalid("file not found") from None
        except IsADirectoryError:
            raise self._invalid("is a directory") from None
        except PermissionError:
            raise self._invalid("permission denied") from None
        except OSError:
            raise self._invalid("cannot read file") from None
        except UnicodeDecodeError:
            raise self._invalid("not valid UTF-8") from None
        try:
            return tomllib.loads(text)
        except tomllib.TOMLDecodeError as exc:
            match = _POSITION.search(str(exc))
            reason = "invalid TOML"
            if match:
                reason += f" at line {match.group(1)}, column {match.group(2)}"
            raise self._invalid(reason) from None

    def _invalid(self, reason: str) -> InvalidTaskFile:
        return InvalidTaskFile((FieldError(str(self._path), reason),))
