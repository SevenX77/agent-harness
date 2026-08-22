"""A run's trace is the run's, and it survives being continued.

Found on the real machine (problem ledger C1 ③), reading the trace of a run
that had been stopped at a breakpoint and continued: it held the SECOND
segment's events only. Everything the run did before the breakpoint was gone —
the phase that produced the very context the continuation ran on had no record
that it ever ran.

``_TraceJsonlSink`` truncated the file when it opened it, and ``resume_skill``
opens a sink for the same run directory. Truncating is the behaviour of
something that believes it is starting a run. A continuation is not a new run:
same run id, same directory, same readers. This is the same mistake as the run
record being rebuilt from a resume's answer, one layer down.

The file cannot be holding anything else. ``trace.jsonl`` lives in
``runs/<run_id>/``, so whatever is already in it was written by this same run —
there is no stale-other-run case for the truncation to defend against.

Design: run-execution/mvp1-alignment.md F10 + RUN_EXECUTION-16.
"""

from __future__ import annotations

import json
from pathlib import Path

from graph_agent.callbacks.emit import _RunSpendLedger, _TraceJsonlSink
from graph_agent.callbacks.events import LLMCallEvent, PhaseStartEvent


def _lines(path: Path) -> list[dict[str, object]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def test_continuing_a_run_keeps_what_it_already_did(tmp_path: Path) -> None:
    first = _TraceJsonlSink(tmp_path)
    first.emit(PhaseStartEvent(phase_name="alpha", phase_execution_id="alpha#1"))

    # The run stops at a breakpoint; the continuation opens the trace again.
    second = _TraceJsonlSink(tmp_path)
    second.emit(PhaseStartEvent(phase_name="beta", phase_execution_id="beta#1"))

    phases = [entry.get("phase_name") for entry in _lines(second.path)]
    assert phases == ["alpha", "beta"], "the run's first segment was erased by its second"


def test_a_run_that_has_written_nothing_still_leaves_a_trace_file(tmp_path: Path) -> None:
    """The file's presence is what says a sink was opened for this run, so it
    is created on open rather than on the first event."""
    sink = _TraceJsonlSink(tmp_path)

    assert sink.path.exists()
    assert _lines(sink.path) == []


def test_a_continued_run_counts_what_the_whole_run_spent(tmp_path: Path) -> None:
    """`metrics.json` quotes the ledger and `report.md` re-aggregates the same
    events, so a ledger that restarted at zero on a resume made the two
    disagree the moment the trace stopped being erased."""
    first = _TraceJsonlSink(tmp_path)
    first.emit(
        LLMCallEvent(
            phase_name="alpha",
            step_id="alpha#1",
            input_tokens=100,
            output_tokens=20,
            response_data={},
        )
    )

    ledger = _RunSpendLedger.continuing(first.path)
    ledger.emit(
        LLMCallEvent(
            phase_name="beta",
            step_id="beta#1",
            input_tokens=7,
            output_tokens=3,
            response_data={},
        )
    )

    assert ledger.totals() == {"total_input_tokens": 107, "total_output_tokens": 23}


def test_a_run_that_is_only_now_starting_opens_its_ledger_at_zero(tmp_path: Path) -> None:
    assert _RunSpendLedger.continuing(tmp_path / "trace.jsonl").totals() == {
        "total_input_tokens": 0,
        "total_output_tokens": 0,
    }
