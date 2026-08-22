"""A run's elapsed time is the run's, not its last segment's.

#993 and #994 walked the same shape down two layers: a resume knows how it
ended, what it spent and where it stopped, and nothing else about the run
belongs to it. `wall_time_sec` was the piece left behind — the runner's own
stopwatch, restarted by every continuation, so a run that ran for a minute,
waited overnight on a breakpoint and then ran for four seconds reported four
seconds.

Two readings of "how long did this run take" were both defensible, and the
choice is written down here because the number is meaningless without it:

*   **What it counts** — how long the run EXECUTED, summed over its segments.
    The wait on a breakpoint is a person thinking, not the run working, and a
    number that included it could not be compared between two runs of the same
    skill. The single-segment case is unchanged, which is what makes this the
    conservative reading rather than a new one.
*   **Where it comes from** — the run's own trace, exactly like its token
    ledger (`_RunSpendLedger.continuing`). Each segment's `run_ended` already
    carries the run's total as of that ending, so a continuation opens its
    clock with the last one and adds its own segment. A second persisted
    number is the drift those two PRs converged away from; there is no reason
    to reintroduce it for this one field.

Design: run-execution/mvp1-alignment.md F10 + RUN_EXECUTION-16.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from graph_agent.callbacks.emit import _TraceJsonlSink, elapsed_before
from graph_agent.callbacks.events import PhaseStartEvent, RunEndedEvent
from graph_agent.core.runner import resume_skill, runs_root


def test_a_run_that_is_only_now_starting_opens_its_clock_at_zero(tmp_path: Path) -> None:
    assert elapsed_before(tmp_path / "trace.jsonl") == 0.0


def test_a_run_still_in_its_first_segment_has_nothing_to_carry(tmp_path: Path) -> None:
    """Nothing has ended yet, so there is no earlier total to open with."""
    sink = _TraceJsonlSink(tmp_path)
    sink.emit(PhaseStartEvent(phase_name="alpha", phase_execution_id="alpha#1"))

    assert elapsed_before(sink.path) == 0.0


def test_a_continuation_opens_its_clock_with_what_the_run_already_ran(tmp_path: Path) -> None:
    sink = _TraceJsonlSink(tmp_path)
    sink.emit(
        RunEndedEvent(
            run_id="r1",
            thread_id="r1",
            status="interrupted",
            final_context={},
            wall_time_seconds=61.5,
        )
    )

    assert elapsed_before(sink.path) == 61.5


def test_the_latest_ending_is_the_running_total_not_one_more_term(tmp_path: Path) -> None:
    """Each `run_ended` carries the total AS OF that ending, so the answer is
    the last one — summing them would count the first segment twice."""
    sink = _TraceJsonlSink(tmp_path)
    for total in (61.5, 65.0):
        sink.emit(
            RunEndedEvent(
                run_id="r1",
                thread_id="r1",
                status="interrupted",
                final_context={},
                wall_time_seconds=total,
            )
        )

    assert elapsed_before(sink.path) == 65.0


def test_a_resume_reports_the_run_s_clock_even_when_it_dies(
    tmp_path: Path,
    mock_skill_resolver: Any,
) -> None:
    """The carry has to reach the RESULT, not just be computable.

    Every exit of ``resume_skill`` reports through the same clock, so the exit
    that reaches the fewest lines of it — a compile that fails before the graph
    is ever assembled — is the one worth pinning: if the carry survives here it
    was applied at the origin rather than remembered at each exit.
    """
    workspace_dir = tmp_path / "workspace"
    run_dir = runs_root(workspace_dir) / "run-that-already-ran"
    run_dir.mkdir(parents=True)
    _TraceJsonlSink(run_dir).emit(
        RunEndedEvent(
            run_id="run-that-already-ran",
            thread_id="run-that-already-ran",
            status="interrupted",
            final_context={},
            wall_time_seconds=61.5,
        )
    )
    not_a_v030_skill = tmp_path / "not_a_v030_skill"
    not_a_v030_skill.mkdir()

    result = resume_skill(
        not_a_v030_skill,
        workspace_dir=workspace_dir,
        run_id="run-that-already-ran",
        skill_resolver=mock_skill_resolver,
    )

    assert result.success is False
    assert result.wall_time_sec >= 61.5, "the resume reported its own segment, not the run"
    assert result.wall_time_sec < 91.5, "the carry was added to something other than this segment"
    assert result.metrics.wall_time_sec == result.wall_time_sec
