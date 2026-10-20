"""Task file model and validation: pure domain logic, no I/O."""

import re
from collections.abc import Collection, Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol


class TaskType(StrEnum):
    CODE_GENERATION = "code-generation"
    CODE_REVIEW = "code-review"


@dataclass(frozen=True)
class RunnerConfig:
    id: str
    runner: str
    model: str
    local: bool
    prompt: str  # effective prompt (own or common)


@dataclass(frozen=True)
class TaskFile:
    type: TaskType
    runners: tuple[RunnerConfig, ...]


@dataclass(frozen=True)
class FieldError:
    path: str
    reason: str

    def __str__(self) -> str:
        return f"{self.path}: {self.reason}"


class InvalidTaskFile(Exception):
    """Raised with every error found in a task file."""

    def __init__(self, errors: tuple[FieldError, ...]) -> None:
        super().__init__("; ".join(str(e) for e in errors))
        self.errors = errors


class TaskFileSource(Protocol):
    def read(self) -> Mapping[str, object]:
        """Return the parsed document; raise InvalidTaskFile if it cannot be read or parsed."""
        ...


_RUNNER_REQUIRED = ("id", "runner", "model")
_ID_PATTERN = re.compile(r"[a-z0-9-]+")


def _text(value: object, path: str, errors: list[FieldError]) -> str | None:
    """Return the value if it is a non-blank string; otherwise record why not."""
    if not isinstance(value, str):
        errors.append(FieldError(path, "expected a string"))
        return None
    if not value.strip():
        errors.append(FieldError(path, "must not be empty"))
        return None
    return value


def _parse_runner(
    entry: Mapping[str, object],
    path: str,
    common_prompt: str | None,
    common_declared: bool,
    seen_ids: set[str],
    runner_names: Collection[str],
    errors: list[FieldError],
) -> RunnerConfig | None:
    """Validate one runner table; return its config, or None if it has errors."""
    count = len(errors)
    id_: str | None = None
    runner: str | None = None
    model: str | None = None
    local = False
    prompt: str | None = None

    for key, value in entry.items():
        field = f"{path}.{key}"
        if key == "id":
            id_ = _text(value, field, errors)
            if id_ is not None:
                if _ID_PATTERN.fullmatch(id_) is None:
                    reason = "invalid id: use only lowercase letters, digits and '-'"
                    errors.append(FieldError(field, reason))
                elif id_ in seen_ids:
                    errors.append(FieldError(field, "duplicate id"))
                seen_ids.add(id_)
        elif key == "runner":
            runner = _text(value, field, errors)
            if runner is not None and runner not in runner_names:
                allowed = ", ".join(sorted(runner_names))
                errors.append(FieldError(field, f"unknown runner: expected one of {allowed}"))
        elif key == "model":
            model = _text(value, field, errors)
        elif key == "local":
            if isinstance(value, bool):
                local = value
            else:
                errors.append(FieldError(field, "expected a boolean"))
        elif key == "prompt":
            prompt = _text(value, field, errors)
        else:
            errors.append(FieldError(field, "unknown key"))

    for key in _RUNNER_REQUIRED:
        if key not in entry:
            errors.append(FieldError(f"{path}.{key}", "missing required field"))

    if "prompt" not in entry and common_prompt is None and not common_declared:
        reason = "missing prompt: set it here or at the top level"
        errors.append(FieldError(f"{path}.prompt", reason))

    effective_prompt = prompt if "prompt" in entry else common_prompt
    if len(errors) > count or id_ is None or runner is None or model is None:
        return None
    if effective_prompt is None:
        return None
    return RunnerConfig(id_, runner, model, local, effective_prompt)


def parse_task_file(data: Mapping[str, object], runner_names: Collection[str]) -> TaskFile:
    """Convert a parsed task file into a TaskFile; raise InvalidTaskFile with every error.

    Messages contain only paths, expected types and schema values, never received values.
    """
    errors: list[FieldError] = []
    task_type: TaskType | None = None
    configs: list[RunnerConfig] = []

    # Resolved up front, without recording errors: they are reported in document order below.
    raw_prompt = data.get("prompt")
    common_prompt = raw_prompt if isinstance(raw_prompt, str) and raw_prompt.strip() else None

    seen_ids: set[str] = set()

    for key, value in data.items():
        if key == "type":
            text = _text(value, "type", errors)
            if text is not None:
                try:
                    task_type = TaskType(text)
                except ValueError:
                    allowed = ", ".join(t.value for t in TaskType)
                    errors.append(FieldError("type", f"unknown type: expected one of {allowed}"))
        elif key == "prompt":
            _text(value, "prompt", errors)
        elif key == "runners":
            if not isinstance(value, list):
                errors.append(FieldError("runners", "expected an array of tables"))
            elif not value:
                errors.append(FieldError("runners", "must contain at least one runner"))
            else:
                for index, entry in enumerate(value):
                    path = f"runners[{index}]"
                    if not isinstance(entry, Mapping):
                        errors.append(FieldError(path, "expected a table"))
                        continue
                    config = _parse_runner(
                        entry, path, common_prompt, "prompt" in data, seen_ids, runner_names, errors
                    )
                    if config is not None:
                        configs.append(config)
        else:
            errors.append(FieldError(key, "unknown key"))

    for required in ("type", "runners"):
        if required not in data:
            errors.append(FieldError(required, "missing required field"))

    if errors or task_type is None:
        raise InvalidTaskFile(tuple(errors))
    return TaskFile(type=task_type, runners=tuple(configs))
