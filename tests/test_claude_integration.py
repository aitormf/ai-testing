"""End to end with the real Claude Code. Needs `claude` installed and authenticated."""

import json
import shutil
from pathlib import Path

import pytest

from ia_testing.adapters.runners.claude import ClaudeRunner
from ia_testing.domain.run import RunRequest, RunStatus
from ia_testing.domain.task_file import RunnerConfig

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(shutil.which("claude") is None, reason="claude is not installed"),
]


def test_real_claude_answers_a_trivial_prompt(tmp_path: Path) -> None:
    workdir = tmp_path / "repo"
    workdir.mkdir()
    (workdir / "hello.txt").write_text("hello\n")
    request = RunRequest(
        config=RunnerConfig(
            id="real",
            runner="claude",
            model="haiku",
            local=False,
            prompt="Reply with the single word ok. Do not use any tool.",
        ),
        workdir=workdir,
        timeout_s=120.0,
        stdout_log=tmp_path / "real.jsonl",
        stderr_log=tmp_path / "real.stderr.log",
    )

    execution = ClaudeRunner().run(request)

    assert execution.status is RunStatus.SUCCEEDED, execution.reason
    assert execution.cost_usd is not None
    assert execution.input_tokens is not None
    assert execution.output_tokens is not None
    events = [json.loads(line) for line in request.stdout_log.read_text().splitlines()]
    assert events[-1]["type"] == "result"
    assert [p.name for p in workdir.iterdir()] == ["hello.txt"]
