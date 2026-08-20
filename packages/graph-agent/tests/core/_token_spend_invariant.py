"""The one thing every token-accounting fixture asserts.

A run's reported spend must equal the sum over the calls the run itself
reported making. Three fixtures now state it — batch, loop, parallel fan-out —
which is why it lives in one place instead of three.

Writing it as an equality between two of the run's own outputs, rather than
against a hardcoded number, is what makes it hold for topologies nobody has
written a fixture for: any path that drops a call from the count fails here
without anyone having had to predict that path. It is also exactly the equality
that was violated on disk — ``report.md`` sums the ``llm_call`` events while
``metrics.json`` quotes the run's totals, and run
``2026-08-20T11-30-38_df572662`` had them at 740965 and 571228 in the same
directory.
"""

from __future__ import annotations

from typing import Any


class CallRecorder:
    """The run's own account of every call it made, as the trace reports them."""

    def __init__(self) -> None:
        self.input_tokens = 0
        self.output_tokens = 0
        self.calls = 0

    def __call__(self, event: Any) -> None:
        if getattr(event, "event_type", None) != "llm_call":
            return
        self.calls += 1
        self.input_tokens += int(getattr(event, "input_tokens", 0) or 0)
        self.output_tokens += int(getattr(event, "output_tokens", 0) or 0)


def assert_totals_match_the_calls(metrics: dict[str, Any], recorder: CallRecorder) -> None:
    assert recorder.calls > 0, "no llm_call reached the trace; the fixture proved nothing"
    assert metrics["total_input_tokens"] == recorder.input_tokens, (
        f"run total {metrics['total_input_tokens']} != sum over "
        f"{recorder.calls} reported calls {recorder.input_tokens}"
    )
    assert metrics["total_output_tokens"] == recorder.output_tokens, (
        f"run total {metrics['total_output_tokens']} != sum over "
        f"{recorder.calls} reported calls {recorder.output_tokens}"
    )
