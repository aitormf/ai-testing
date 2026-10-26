from ia_testing.adapters.runners.claude import ClaudeRunner
from ia_testing.adapters.runners.registry import RUNNER_NAMES, RUNNERS, build_runners


def test_registered_runners() -> None:
    assert RUNNER_NAMES == ("claude", "codex", "opencode")


def test_build_runners_instantiates_implemented() -> None:
    runners = build_runners()

    assert tuple(runners) == RUNNER_NAMES == tuple(RUNNERS)
    assert isinstance(runners["claude"], ClaudeRunner)
    assert runners["codex"] is None
    assert runners["opencode"] is None
