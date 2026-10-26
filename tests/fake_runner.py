"""A fake Runner for the tests of `app`: the only test double allowed (AGENTS.md)."""

from collections.abc import Callable, Sequence

from ia_testing.domain.run import Execution, RunnerCheck, RunRequest, RunStatus
from ia_testing.domain.task_file import RunnerConfig

SUCCESS = Execution(status=RunStatus.SUCCEEDED, reason=None, duration_s=1.0)


class FakeRunner:
    """Implements the `Runner` Protocol without launching anything.

    `script` holds what each call to `run` does, in order: an `Execution` to return or a
    `KeyboardInterrupt` to raise. Once the script is exhausted, `run` returns `SUCCESS`.
    `check_result` may also be a `KeyboardInterrupt` to raise from `check`.
    `on_run` is called with every request before the scripted outcome is applied.
    """

    def __init__(
        self,
        script: Sequence[Execution | KeyboardInterrupt] = (),
        *,
        check_result: RunnerCheck | KeyboardInterrupt | None = None,
        on_run: Callable[[RunRequest], None] | None = None,
    ) -> None:
        self._script = list(script)
        self._check_result = check_result or RunnerCheck(error=None, warnings=())
        self._on_run = on_run
        self.checked: list[tuple[RunnerConfig, ...]] = []
        self.requests: list[RunRequest] = []

    def check(self, configs: Sequence[RunnerConfig]) -> RunnerCheck:
        self.checked.append(tuple(configs))
        if isinstance(self._check_result, KeyboardInterrupt):
            raise self._check_result
        return self._check_result

    def run(self, request: RunRequest) -> Execution:
        self.requests.append(request)
        if self._on_run is not None:
            self._on_run(request)
        outcome = self._script.pop(0) if self._script else SUCCESS
        if isinstance(outcome, KeyboardInterrupt):
            raise outcome
        return outcome
