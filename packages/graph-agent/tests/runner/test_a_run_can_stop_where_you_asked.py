"""A run can be told to stop before a phase, and say so when it does.

Two things were missing, and they are the same thing seen twice. A graph could
not be told "stop before this phase" at all, and a run that stopped for ANY
reason had no way to say so: the result carries ``success``, which answers
"did it produce its outputs" — so a stopped run came back as a finished one.
That is not hypothetical for the human-in-the-loop path, which has always
returned its result without a ``success`` key while the host treats an absent
one as success.

Design: run-execution/mvp1-alignment.md F10 + RUN_EXECUTION-16.
"""

from __future__ import annotations

import pytest

from graph_agent.callbacks.events import InterruptedEvent
from graph_agent.core.result import PausedRunPoint, RunResult


def test_a_paused_run_says_where_it_stopped_and_why() -> None:
    result = RunResult(
        success=False,
        run_id="run-1",
        skill_id="demo",
        paused_at=PausedRunPoint(phase_name="review", reason="breakpoint"),
    )

    assert result.paused_at is not None
    assert result.paused_at.phase_name == "review"
    assert result.paused_at.reason == "breakpoint"


def test_a_run_that_stopped_cannot_also_claim_it_finished() -> None:
    """``success`` means "it produced its declared outputs". A run stopped
    part-way did not, so the pair cannot both be true — and a shape that can
    express it would let a half-run trip the autocommit that follows success."""
    with pytest.raises(ValueError, match="paused"):
        RunResult(
            success=True,
            run_id="run-1",
            skill_id="demo",
            paused_at=PausedRunPoint(phase_name="review", reason="breakpoint"),
        )


def test_a_finished_run_names_no_pause_point() -> None:
    assert RunResult(success=True, run_id="run-1", skill_id="demo").paused_at is None


def test_an_interruption_says_which_kind_it_is() -> None:
    """A reader has to know whether to answer a question or just continue, and
    "the question came out empty" must not be the way that gets decided."""
    waiting = InterruptedEvent(
        phase_name="review",
        thread_id="run-1",
        reason="awaiting_human",
        question="Which one?",
    )
    stopped = InterruptedEvent(phase_name="review", thread_id="run-1", reason="breakpoint")

    assert waiting.reason == "awaiting_human"
    assert stopped.reason == "breakpoint"
    assert stopped.question is None
