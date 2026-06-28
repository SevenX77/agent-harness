from __future__ import annotations

import importlib

import pytest

from graph_agent.core.event_contracts import make_event_envelope


def _stream_buffer(*, capacity: int = 10):
    event_contracts = importlib.import_module("graph_agent.core.event_contracts")
    return event_contracts.EventStreamBuffer(stream_id="stream-run-1", capacity=capacity)


def test_event_stream_resumes_from_cursor_and_deduplicates_seq() -> None:
    stream = _stream_buffer()
    first = make_event_envelope(
        stream_id="stream-run-1",
        seq=1,
        run_id="run-1",
        event_type="phase_started",
        payload={"phase": "draft"},
    )
    duplicate = first.model_copy()
    second = make_event_envelope(
        stream_id="stream-run-1",
        seq=2,
        run_id="run-1",
        event_type="phase_finished",
        payload={"phase": "draft"},
    )

    stream.append(first)
    stream.append(duplicate)
    stream.append(second)

    resumed = stream.resume(cursor=first.cursor)

    assert [event.seq for event in resumed.events] == [2]
    assert resumed.next_cursor == second.cursor


def test_event_stream_gap_and_expired_cursor_are_explicit_errors() -> None:
    event_contracts = importlib.import_module("graph_agent.core.event_contracts")
    stream = _stream_buffer(capacity=2)
    stream.append(make_event_envelope(stream_id="stream-run-1", seq=1, run_id="run-1", event_type="a", payload={}))

    with pytest.raises(event_contracts.StreamCursorGapError) as gap_info:
        stream.append(make_event_envelope(stream_id="stream-run-1", seq=3, run_id="run-1", event_type="c", payload={}))

    assert getattr(gap_info.value, "error_code", None) == "stream.cursor_gap"

    stream.append(make_event_envelope(stream_id="stream-run-1", seq=2, run_id="run-1", event_type="b", payload={}))
    stream.append(make_event_envelope(stream_id="stream-run-1", seq=3, run_id="run-1", event_type="c", payload={}))

    with pytest.raises(event_contracts.StreamCursorExpiredError) as expired_info:
        stream.resume(cursor="stream-run-1:0")

    assert getattr(expired_info.value, "error_code", None) == "stream.cursor_expired"


def test_event_stream_backpressure_and_out_of_order_handling_are_explicit() -> None:
    event_contracts = importlib.import_module("graph_agent.core.event_contracts")
    stream = _stream_buffer(capacity=1)
    stream.append(make_event_envelope(stream_id="stream-run-1", seq=1, run_id="run-1", event_type="a", payload={}))

    with pytest.raises(event_contracts.StreamBackpressureError) as backpressure_info:
        stream.append(make_event_envelope(stream_id="stream-run-1", seq=2, run_id="run-1", event_type="b", payload={}))

    assert getattr(backpressure_info.value, "error_code", None) == "stream.backpressure"

    unordered = _stream_buffer()
    unordered.append(make_event_envelope(stream_id="stream-run-1", seq=2, run_id="run-1", event_type="b", payload={}))
    unordered.append(make_event_envelope(stream_id="stream-run-1", seq=1, run_id="run-1", event_type="a", payload={}))

    resumed = unordered.resume(cursor=None)

    assert [event.seq for event in resumed.events] == [1, 2]
