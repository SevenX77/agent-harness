"""``tool_call_id`` is an invariant of a tool call, not an optional extra.

Every tool call has an identity, so the type system carries it: a
``ToolCallEvent`` without one cannot be constructed. Traces recorded before
this field existed no longer deserialize — that is the intended cost, not a
case to soften with a default.
"""

from __future__ import annotations

import pytest
from pydantic import TypeAdapter, ValidationError

from graph_agent.callbacks.events import CallbackEvent, ToolCallEvent, ToolCallStartedEvent


def test_tool_call_event_requires_a_tool_call_id() -> None:
    with pytest.raises(ValidationError) as exc_info:
        ToolCallEvent(phase_name="draft", tool_name="lookup", result="ok")  # type: ignore[call-arg]

    assert "tool_call_id" in str(exc_info.value)


def test_tool_call_started_event_requires_a_tool_call_id() -> None:
    with pytest.raises(ValidationError) as exc_info:
        ToolCallStartedEvent(phase_name="draft", tool_name="lookup")  # type: ignore[call-arg]

    assert "tool_call_id" in str(exc_info.value)


def test_started_event_round_trips_through_the_discriminated_union() -> None:
    adapter: TypeAdapter[CallbackEvent] = TypeAdapter(CallbackEvent)
    event = ToolCallStartedEvent(
        phase_name="draft",
        tool_call_id="call-1",
        tool_name="lookup",
        args={"topic": "identity"},
        parent_node_id="draft",
        node_type="tool",
    )

    restored = adapter.validate_json(event.model_dump_json())

    assert isinstance(restored, ToolCallStartedEvent)
    assert restored == event
    assert restored.event_type == "tool_call_started"
