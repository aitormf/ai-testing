"""Explicit registry of known runners (no dynamic discovery).

A runner is a name mapped to a factory, or to `None` while it is not implemented. Adding a runner
means one file in this package and replacing its `None` here.
"""

from collections.abc import Callable, Mapping

from ia_testing.adapters.runners.claude import ClaudeRunner
from ia_testing.domain.run import Runner

RUNNERS: Mapping[str, Callable[[], Runner] | None] = {
    "claude": ClaudeRunner,
    "codex": None,
    "opencode": None,
}

RUNNER_NAMES = tuple(RUNNERS)


def build_runners() -> dict[str, Runner | None]:
    """Instantiate the implemented runners; the rest stay `None`."""
    return {name: None if factory is None else factory() for name, factory in RUNNERS.items()}
