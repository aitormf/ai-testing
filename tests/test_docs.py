import re
from pathlib import Path

from ia_testing.adapters.runners.registry import RUNNER_NAMES
from ia_testing.adapters.task_file import TomlTaskFileSource
from ia_testing.app.task_file import validate_task_file

_DOC = Path(__file__).parent.parent / "docs" / "config_file.md"
_TOML_BLOCK = re.compile(r"^```toml\n(.*?)^```", re.DOTALL | re.MULTILINE)


def test_config_file_examples_are_valid(tmp_path: Path) -> None:
    blocks = _TOML_BLOCK.findall(_DOC.read_text(encoding="utf-8"))

    assert blocks, "docs/config_file.md has no ```toml block"
    for index, block in enumerate(blocks):
        path = tmp_path / f"example-{index}.toml"
        path.write_text(block, encoding="utf-8")

        errors = validate_task_file(TomlTaskFileSource(path), RUNNER_NAMES)

        assert errors == (), f"toml block {index} is invalid: {[str(e) for e in errors]}"
