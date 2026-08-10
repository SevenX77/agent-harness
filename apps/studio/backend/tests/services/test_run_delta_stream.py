"""Deltas travel their own road, and it is allowed to lose things.

A step frame is numbered so a reader who dropped off can ask for everything
after number N. That only works if every number exists: skip one and the reader
concludes it lost data and says so. A delta frame is explicitly droppable — it
may be merged with its neighbour or thrown away when a watcher falls behind —
so numbering it would turn every permitted drop into reported data loss.

Hence two roads. This file pins what each one is for: the numbered road stays
contiguous no matter how much text streams over the other, and the delta road
stays bounded no matter how slow the watcher is.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import Any

import pytest
from app.services.run_manager import (
    _delta_envelope_from_callback,
    _DeltaStream,
    _event_envelope_from_callback,
    _events_after_cursor,
    _queue_event_subscriber,
)
from graph_agent.callbacks.events import LLMCallEvent, LLMDeltaEvent, PromptCapturedEvent


class _Queue:
    def __init__(self) -> None:
        self.messages: list[dict[str, Any]] = []

    def put(self, message: dict[str, Any]) -> None:
        self.messages.append(message)


def _delta(text: str, *, step_id: str = "s1", channel: str = "text") -> LLMDeltaEvent:
    return LLMDeltaEvent(phase_name="draft", step_id=step_id, channel=channel, text=text)


def _frame(text: str, *, step_id: str = "s1", channel: str = "text", restarts: bool = False) -> Any:
    return _delta_envelope_from_callback(
        LLMDeltaEvent(
            phase_name="draft",
            step_id=step_id,
            channel=channel,
            text=text,
            restarts_step=restarts,
        ).model_dump(mode="json"),
        run_id="run-1",
    )


def test_a_delta_takes_the_other_road_out_of_the_run_process() -> None:
    """Sorting them at the source is what keeps the numbered road numbered."""
    queue = _Queue()
    emit = _queue_event_subscriber(queue)

    emit(PromptCapturedEvent(phase_name="draft", step_id="s1"))
    emit(_delta("Hel"))
    emit(_delta("lo"))
    emit(
        LLMCallEvent(
            phase_name="draft",
            step_id="s1",
            input_tokens=1,
            output_tokens=1,
            response_data={"content": "Hello"},
        )
    )

    assert [m["type"] for m in queue.messages] == ["event", "delta", "delta", "event"]


def test_the_numbered_road_stays_contiguous_however_much_text_streams() -> None:
    """Criterion 10/11: a reconnecting reader must not see a gap where deltas were."""
    events = [
        _event_envelope_from_callback({"event_type": "prompt_captured"}, run_id="run-1", seq=1),
        _event_envelope_from_callback({"event_type": "llm_call"}, run_id="run-1", seq=2),
    ]

    assert [e.seq for e in events] == [1, 2]
    # Whatever the reader already has, the rest arrives without a hole.
    after = _events_after_cursor(events, cursor="run:run-1:1")
    assert [e.seq for e in after] == [2]


def test_a_delta_frame_carries_no_sequence_number_at_all() -> None:
    """Not "its number is skipped" — it has none, so no reader can miss one."""
    frame = _frame("hi")

    assert not hasattr(frame, "seq") or frame.model_dump().get("seq") is None
    assert frame.model_dump().get("cursor") is None
    assert frame.step_id == "s1"
    assert frame.channel == "text"


def test_a_watcher_who_keeps_up_sees_every_piece_separately() -> None:
    """Merging is what backlog does; with no backlog there is nothing to merge."""
    stream = _DeltaStream()

    async def drive() -> list[str]:
        seen: list[str] = []

        async def read() -> None:
            async for frame in stream:
                seen.append(frame.text)
                if len(seen) == 3:
                    stream.close()

        task = asyncio.create_task(read())
        for piece in ("a", "b", "c"):
            stream.offer(_frame(piece))
            await asyncio.sleep(0)
        await asyncio.wait_for(task, timeout=1)
        return seen

    assert asyncio.run(drive()) == ["a", "b", "c"]


def test_a_watcher_who_falls_behind_gets_the_pieces_merged() -> None:
    """The time window is the backlog itself: no timer decides this."""
    stream = _DeltaStream()

    for piece in ("Hel", "lo, ", "world"):
        stream.offer(_frame(piece))

    assert [f.text for f in stream.pending] == ["Hello, world"]


def test_pieces_of_different_steps_are_never_merged_into_each_other() -> None:
    """Merging across steps would put one call's text inside another's row."""
    stream = _DeltaStream()

    stream.offer(_frame("one", step_id="s1"))
    stream.offer(_frame("two", step_id="s2"))
    stream.offer(_frame("three", step_id="s1"))

    assert [(f.step_id, f.text) for f in stream.pending] == [
        ("s1", "one"),
        ("s2", "two"),
        ("s1", "three"),
    ]


def test_thinking_is_never_merged_into_the_answer() -> None:
    stream = _DeltaStream()

    stream.offer(_frame("let me think", channel="thinking"))
    stream.offer(_frame("42", channel="text"))

    assert [(f.channel, f.text) for f in stream.pending] == [
        ("thinking", "let me think"),
        ("text", "42"),
    ]


def test_a_restart_is_not_swallowed_by_the_text_it_cancels() -> None:
    """Merging a restart into the text it discards would erase the discarding."""
    stream = _DeltaStream()

    stream.offer(_frame("half an ans"))
    stream.offer(_frame("", restarts=True))
    stream.offer(_frame("the whole answer"))

    assert [(f.text, f.restarts_step) for f in stream.pending] == [
        ("half an ans", False),
        ("", True),
        ("the whole answer", False),
    ]


def test_a_watcher_that_never_reads_costs_a_fixed_amount_of_memory() -> None:
    """A queue that grows with the run is how a long run takes the process down."""
    stream = _DeltaStream()

    for index in range(_DeltaStream.MAX_PENDING * 3):
        # Alternating steps so nothing merges: this is the worst case.
        stream.offer(_frame(f"p{index}", step_id=f"s{index % 2}"))

    assert len(stream.pending) == _DeltaStream.MAX_PENDING
    assert stream.dropped == _DeltaStream.MAX_PENDING * 2
    # The newest pieces are the ones a live view needs; the oldest go first.
    assert stream.pending[-1].text == f"p{_DeltaStream.MAX_PENDING * 3 - 1}"


def test_closing_the_stream_ends_the_watcher_rather_than_hanging_it() -> None:
    stream = _DeltaStream()
    stream.offer(_frame("last"))
    stream.close()

    async def drain() -> list[str]:
        return [frame.text async for frame in stream]

    assert asyncio.run(asyncio.wait_for(drain(), timeout=1)) == ["last"]


def test_a_delta_envelope_says_which_run_it_belongs_to() -> None:
    """Two runs can stream at once; a frame that cannot name its run is unusable."""
    frame = _frame("hi")
    assert frame.run_id == "run-1"
    assert frame.stream_id == "run:run-1"
    assert isinstance(frame.timestamp, datetime)
    assert frame.timestamp.tzinfo is not None


@pytest.mark.parametrize("channel", ["text", "thinking"])
def test_both_channels_survive_the_trip_from_engine_event_to_wire(channel: str) -> None:
    payload = LLMDeltaEvent(
        phase_name="draft", step_id="s9", channel=channel, text="x"
    ).model_dump(mode="json")

    frame = _delta_envelope_from_callback(payload, run_id="run-2")

    wire = frame.model_dump(mode="json")
    assert wire["channel"] == channel
    assert wire["step_id"] == "s9"
    assert wire["schema_version"] == "studio.delta.v1"
    assert datetime.fromisoformat(wire["timestamp"]).tzinfo is not None
    assert datetime.now(UTC) >= frame.timestamp
