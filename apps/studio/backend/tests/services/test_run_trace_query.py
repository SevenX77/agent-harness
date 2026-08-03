"""Trace queries must answer what a session currently reconstructs by hand.

exp-b-round3 diagnosed a real defect by running `python3` over `trace.jsonl` and
`strings` over the checkpoint WAL. The numbers it reconstructed — per-phase
iterations, how many submissions the schema gate threw back, and what it said —
are exactly what these projections have to produce, so the shapes below are
modelled on that recorded trace rather than on an imagined one.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from app.core.adapters.engine import EventEnvelope
from app.services.run_trace_query import (
    MAX_EVENT_LIMIT,
    project_event,
    rejection_reason,
    slice_events,
    summarize_phases,
)

REJECTED_PARSED_SEGMENTS = (
    "[提交已被系统驳回] 当前任务尚未完成,请修正后重新提交。\n"
    "item parsed_segments: parsed_segments: Field required"
)
REJECTED_NO_BLOCKS = (
    "[提交已被系统驳回] 当前任务尚未完成,请修正后重新提交。\n"
    "未能在 business_data_md 中检测到任何 ## 块。"
)


def _event(seq: int, event_type: str, payload: dict[str, Any]) -> EventEnvelope:
    return EventEnvelope(
        stream_id="run-1",
        seq=seq,
        run_id="run-1",
        event_type=event_type,
        payload=payload,
        cursor=str(seq),
        timestamp=datetime(2026, 8, 3, 7, 21, seq % 60, tzinfo=UTC),
    )


def _recorded_trace() -> list[EventEnvelope]:
    """A trace shaped like the recorded one: a loop that gets thrown back, then lands."""
    return [
        _event(1, "run_started", {"initial_context": {"huge": "x" * 5000}}),
        _event(2, "phase_start", {"phase_name": "segment"}),
        _event(3, "agent_loop_iteration", {"phase_name": "segment", "iteration": 1}),
        _event(4, "llm_call", {"phase_name": "segment", "input_tokens": 10, "output_tokens": 20, "messages": ["x" * 5000]}),
        _event(5, "tool_call", {"phase_name": "segment", "tool_name": "finish_task", "result": REJECTED_NO_BLOCKS}),
        _event(6, "agent_loop_iteration", {"phase_name": "segment", "iteration": 2}),
        _event(7, "tool_call", {"phase_name": "segment", "tool_name": "finish_task", "result": REJECTED_PARSED_SEGMENTS}),
        _event(8, "tool_call", {"phase_name": "segment", "tool_name": "finish_task", "result": REJECTED_PARSED_SEGMENTS}),
        _event(9, "tool_call", {"phase_name": "segment", "tool_name": "finish_task", "result": ""}),
        _event(10, "tool_call", {"phase_name": "segment", "tool_name": "finish_task", "result": "PHASE_COMPLETE"}),
        _event(11, "phase_end", {"phase_name": "segment"}),
        _event(12, "phase_start", {"phase_name": "review"}),
        _event(13, "tool_call", {"phase_name": "review", "tool_name": "finish_task", "result": "PHASE_COMPLETE"}),
        _event(14, "run_ended", {"status": "completed", "wall_time_seconds": 256.5}),
    ]


def test_phase_summary_counts_the_loop_and_the_rejections() -> None:
    summary = summarize_phases(_recorded_trace())

    segment = summary["segment"]
    assert segment["iterations"] == 2
    assert segment["llm_calls"] == 1
    assert segment["tool_calls"] == 5
    assert segment["submissions"] == 5
    assert segment["rejections"] == 3
    assert segment["accepted"] == 1
    assert summary["review"]["accepted"] == 1
    assert summary["review"]["rejections"] == 0


def test_phase_summary_ranks_the_reasons_a_submission_was_thrown_back() -> None:
    summary = summarize_phases(_recorded_trace())

    reasons = summary["segment"]["top_rejection_reasons"]
    assert reasons[0]["count"] == 2
    assert "parsed_segments: Field required" in reasons[0]["reason"]
    assert {row["reason"] for row in reasons} == {
        "item parsed_segments: parsed_segments: Field required",
        "未能在 business_data_md 中检测到任何 ## 块。",
    }


def test_rejection_reason_drops_the_banner_but_keeps_a_single_line_whole() -> None:
    assert rejection_reason(REJECTED_NO_BLOCKS) == "未能在 business_data_md 中检测到任何 ## 块。"
    assert rejection_reason("only one line") == "only one line"


def test_projected_events_leave_the_prompt_and_context_behind() -> None:
    """A slice must stay reply-sized: prompts and contexts live in the artifacts."""
    projected = [project_event(event) for event in _recorded_trace()]

    serialized = str(projected)
    assert "x" * 5000 not in serialized
    llm = next(row for row in projected if row["event_type"] == "llm_call")
    assert llm["input_tokens"] == 10 and llm["output_tokens"] == 20
    assert "messages" not in llm
    ended = next(row for row in projected if row["event_type"] == "run_ended")
    assert ended["status"] == "completed"
    assert ended["wall_time_seconds"] == 256.5


def test_slice_filters_by_phase_and_event_type() -> None:
    result = slice_events(_recorded_trace(), phase="segment", event_types=["tool_call"])

    assert result["matched_total"] == 5
    assert {row["event_type"] for row in result["events"]} == {"tool_call"}
    assert {row["phase"] for row in result["events"]} == {"segment"}


def test_slice_pages_with_a_cursor_and_never_exceeds_the_cap() -> None:
    trace = _recorded_trace()

    first = slice_events(trace, limit=5)
    assert first["returned"] == 5
    assert first["next_seq"] == 5
    second = slice_events(trace, since_seq=first["next_seq"], limit=5)
    assert [row["seq"] for row in second["events"]][0] == 6

    assert slice_events(trace, limit=MAX_EVENT_LIMIT + 500)["returned"] == len(trace)


def test_slice_reports_no_cursor_once_the_page_covers_the_matches() -> None:
    result = slice_events(_recorded_trace(), phase="review")

    assert result["matched_total"] == result["returned"]
    assert result["next_seq"] is None
