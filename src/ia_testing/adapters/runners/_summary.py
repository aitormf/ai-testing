"""What every runner extracts from the output of its agent, whatever the output format."""

from dataclasses import dataclass


@dataclass(frozen=True)
class OutputSummary:
    """Absent or malformed fields are None; `is_error` is what the agent itself reported."""

    is_error: bool
    cost_usd: float | None
    input_tokens: int | None
    output_tokens: int | None


NO_OUTPUT = OutputSummary(is_error=False, cost_usd=None, input_tokens=None, output_tokens=None)
