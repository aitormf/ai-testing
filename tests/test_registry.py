from ia_testing.adapters.runners.registry import RUNNER_NAMES


def test_registered_runners() -> None:
    assert RUNNER_NAMES == ("claude", "codex", "opencode")
