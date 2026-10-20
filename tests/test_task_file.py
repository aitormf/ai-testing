from collections.abc import Collection, Mapping

import pytest

from ia_testing.adapters.runners.registry import RUNNER_NAMES
from ia_testing.domain.task_file import (
    FieldError,
    InvalidTaskFile,
    RunnerConfig,
    TaskType,
    parse_task_file,
)


def runner(**overrides: object) -> dict[str, object]:
    base: dict[str, object] = {"id": "a", "runner": "claude", "model": "m"}
    base.update(overrides)
    return base


def document(*runners: Mapping[str, object], **root: object) -> dict[str, object]:
    data: dict[str, object] = {"type": "code-generation", "prompt": "common"}
    data.update(root)
    data["runners"] = list(runners)
    return data


def test_field_error_str_is_path_and_reason() -> None:
    assert str(FieldError("runners[1].model", "missing required field")) == (
        "runners[1].model: missing required field"
    )


def test_invalid_task_file_keeps_errors() -> None:
    errors = (FieldError("type", "missing required field"),)

    assert InvalidTaskFile(errors).errors == errors


def test_same_runner_twice_with_distinct_ids_is_valid() -> None:
    data = document(runner(id="a", model="m1"), runner(id="b", model="m2"))

    task_file = parse_task_file(data, RUNNER_NAMES)

    assert task_file.type is TaskType.CODE_GENERATION
    assert [(r.id, r.runner, r.model) for r in task_file.runners] == [
        ("a", "claude", "m1"),
        ("b", "claude", "m2"),
    ]


def test_local_defaults_to_false() -> None:
    task_file = parse_task_file(document(runner(), runner(id="b", local=True)), RUNNER_NAMES)

    assert [r.local for r in task_file.runners] == [False, True]


def test_own_prompt_overrides_common() -> None:
    task_file = parse_task_file(
        document(runner(id="a", prompt="own"), runner(id="b")), RUNNER_NAMES
    )

    assert task_file.runners == (
        RunnerConfig("a", "claude", "m", False, "own"),
        RunnerConfig("b", "claude", "m", False, "common"),
    )


def test_runner_names_are_injected() -> None:
    data = document(runner(runner="brand-new"))

    assert parse_task_file(data, ["brand-new"]).runners[0].runner == "brand-new"


def errors_of(data: Mapping[str, object], names: Collection[str] = RUNNER_NAMES) -> list[str]:
    with pytest.raises(InvalidTaskFile) as excinfo:
        parse_task_file(data, names)
    return [str(e) for e in excinfo.value.errors]


def test_unknown_root_key() -> None:
    data = document(runner(), colour="red")

    assert errors_of(data) == ["colour: unknown key"]


def test_unknown_type_lists_allowed_without_value() -> None:
    errors = errors_of(document(runner(), type="benchmark"))

    assert errors == ["type: unknown type: expected one of code-generation, code-review"]
    assert "benchmark" not in errors[0]


def test_empty_document_reports_type_and_runners() -> None:
    assert errors_of({}) == ["type: missing required field", "runners: missing required field"]


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ([], "runners: must contain at least one runner"),
        ({"id": "a"}, "runners: expected an array of tables"),
    ],
)
def test_runners_empty_or_table(value: object, expected: str) -> None:
    assert errors_of({"type": "code-review", "runners": value}) == [expected]


@pytest.mark.parametrize(
    ("root", "expected"),
    [
        ({"type": []}, "type: expected a string"),
        ({"prompt": 1}, "prompt: expected a string"),
    ],
)
def test_wrong_types_in_root(root: dict[str, object], expected: str) -> None:
    assert errors_of(document(runner(), **root)) == [expected]


def test_missing_model() -> None:
    data = document(runner(id="a"), {"id": "b", "runner": "claude"})

    assert errors_of(data) == ["runners[1].model: missing required field"]


def test_missing_required_fields_follow_schema_order() -> None:
    assert errors_of(document({})) == [
        "runners[0].id: missing required field",
        "runners[0].runner: missing required field",
        "runners[0].model: missing required field",
    ]


def test_unknown_runner_key_is_reported_before_missing_fields() -> None:
    data = document({"modle": "x", "id": "a", "runner": "claude"})

    assert errors_of(data) == [
        "runners[0].modle: unknown key",
        "runners[0].model: missing required field",
    ]


@pytest.mark.parametrize(
    ("entry", "expected"),
    [
        ({"model": " "}, "runners[0].model: must not be empty"),
        ({"prompt": "\t\n"}, "runners[0].prompt: must not be empty"),
        ({"id": ""}, "runners[0].id: must not be empty"),
    ],
)
def test_blank_text_fields_are_errors(entry: dict[str, object], expected: str) -> None:
    assert errors_of(document(runner(**entry))) == [expected]


def test_blank_common_prompt_is_a_single_error() -> None:
    data = document(runner(id="a"), runner(id="b", prompt="own"), runner(id="c"), prompt="  ")

    assert errors_of(data) == ["prompt: must not be empty"]


def test_common_prompt_after_runners_is_still_used() -> None:
    data = {"runners": [runner()], "type": "code-review", "prompt": "common"}

    assert parse_task_file(data, RUNNER_NAMES).runners[0].prompt == "common"


@pytest.mark.parametrize(
    ("entry", "expected"),
    [
        ({"local": "yes"}, "runners[0].local: expected a boolean"),
        ({"model": 1}, "runners[0].model: expected a string"),
        ({"id": 3}, "runners[0].id: expected a string"),
        ({"runner": ["claude"]}, "runners[0].runner: expected a string"),
        ({"prompt": 1}, "runners[0].prompt: expected a string"),
    ],
)
def test_wrong_types(entry: dict[str, object], expected: str) -> None:
    assert errors_of(document(runner(**entry))) == [expected]


@pytest.mark.parametrize("value", [1, "a"])
def test_runner_entries_that_are_not_tables(value: object) -> None:
    data = {"type": "code-review", "prompt": "p", "runners": [value, runner()]}

    assert errors_of(data) == ["runners[0]: expected a table"]


def test_unknown_runner_lists_allowed_sorted() -> None:
    errors = errors_of(document(runner(runner="gemini")), {"opencode", "claude", "codex"})

    assert errors == ["runners[0].runner: unknown runner: expected one of claude, codex, opencode"]
    assert "gemini" not in errors[0]


def test_credential_key_rejected_without_value() -> None:
    errors = errors_of(document(runner(api_key="sk-secret-123")))

    assert errors == ["runners[0].api_key: unknown key"]
    assert "sk-secret-123" not in errors[0]


@pytest.mark.parametrize("bad_id", ["Upper", "snake_case", "has space", "a/b", "..", "a\n", "a.b"])
def test_invalid_id_format(bad_id: str) -> None:
    errors = errors_of(document(runner(id=bad_id)))

    assert errors == ["runners[0].id: invalid id: use only lowercase letters, digits and '-'"]


def test_duplicate_id_reported_on_later_entry_without_value() -> None:
    data = document(runner(id="same"), runner(id="other"), runner(id="same"), runner(id="same"))

    errors = errors_of(data)

    assert errors == ["runners[2].id: duplicate id", "runners[3].id: duplicate id"]
    assert all("same" not in e for e in errors)


def test_missing_effective_prompt() -> None:
    data = {"type": "code-review", "runners": [runner(id="a", prompt="own"), runner(id="b")]}

    assert errors_of(data) == ["runners[1].prompt: missing prompt: set it here or at the top level"]


def test_karajan_is_not_a_known_runner() -> None:
    errors = errors_of(document(runner(runner="karajan")), RUNNER_NAMES)

    assert errors == ["runners[0].runner: unknown runner: expected one of claude, codex, opencode"]
