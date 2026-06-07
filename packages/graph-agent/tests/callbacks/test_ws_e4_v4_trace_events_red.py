from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

import pytest
from pydantic import TypeAdapter, ValidationError

import graph_agent.callbacks.events as events
from graph_agent.callbacks.base import Callback
from graph_agent.callbacks.emit import _TraceJsonlSink
from graph_agent.callbacks.events import CallbackEvent, LLMCallEvent, ToolCallEvent


def _event_class(name: str) -> type[Any]:
    cls = getattr(events, name, None)
    assert cls is not None, f"{name} must be defined in graph_agent.callbacks.events"
    return cls


def test_v4_micro_topology_fields_are_available_on_llm_and_tool_events() -> None:
    llm = LLMCallEvent(
        phase_name="draft",
        input_tokens=10,
        output_tokens=3,
        parent_node_id="draft",
        node_type="llm_call",
    )
    tool = ToolCallEvent(
        phase_name="draft",
        tool_name="lookup",
        result="ok",
        parent_node_id="draft",
        node_type="tool_call",
    )

    assert llm.model_dump()["parent_node_id"] == "draft"
    assert llm.model_dump()["node_type"] == "llm_call"
    assert tool.model_dump()["parent_node_id"] == "draft"
    assert tool.model_dump()["node_type"] == "tool_call"


def test_v4_micro_topology_fields_default_to_none_for_legacy_construction() -> None:
    llm = LLMCallEvent(phase_name="draft", input_tokens=10, output_tokens=3)
    tool = ToolCallEvent(phase_name="draft", tool_name="lookup", result="ok")

    assert llm.model_dump()["parent_node_id"] is None
    assert llm.model_dump()["node_type"] is None
    assert tool.model_dump()["parent_node_id"] is None
    assert tool.model_dump()["node_type"] is None


def test_v4_edge_operation_events_are_publicly_exported() -> None:
    expected_exports = {
        "BlackboardReduceEvent",
        "InputDispatchEvent",
        "InputFileInjectedEvent",
    }

    assert expected_exports.issubset(set(events.__all__))


def test_v4_edge_operation_events_round_trip_through_union_and_jsonl(tmp_path: Path) -> None:
    blackboard_reduce_cls = _event_class("BlackboardReduceEvent")
    input_dispatch_cls = _event_class("InputDispatchEvent")
    input_file_injected_cls = _event_class("InputFileInjectedEvent")
    adapter = TypeAdapter(CallbackEvent)
    sink = _TraceJsonlSink(tmp_path)

    event_payloads = [
        blackboard_reduce_cls(
            from_phase="draft",
            to_phase="review",
            changed_keys=["summary"],
            blackboard_snapshot={"summary": "ok"},
            reducer="merge",
        ),
        input_dispatch_cls(
            from_phase="draft",
            to_phase="review",
            changed_keys=["summary"],
            blackboard_snapshot={"summary": "ok"},
            dispatched_keys=["summary"],
            branch_index=2,
        ),
        input_file_injected_cls(
            from_phase=None,
            to_phase="draft",
            changed_keys=["brief"],
            blackboard_snapshot={"brief": "file body"},
            file_ref="inputs/brief.md",
            target_field="brief",
        ),
    ]

    for event in event_payloads:
        parsed = adapter.validate_python(event.model_dump())
        assert parsed.event_type == event.event_type
        with pytest.raises(ValidationError):
            type(event)(**{**event.model_dump(), "unexpected": "forbidden"})
        sink.emit(event)

    lines = (tmp_path / "trace.jsonl").read_text(encoding="utf-8").splitlines()
    assert [json.loads(line)["event_type"] for line in lines] == [
        "blackboard_reduce",
        "input_dispatch",
        "input_file_injected",
    ]


def test_default_callback_accepts_v4_trace_events_without_warning(caplog: pytest.LogCaptureFixture) -> None:
    blackboard_reduce_cls = _event_class("BlackboardReduceEvent")
    input_dispatch_cls = _event_class("InputDispatchEvent")
    input_file_injected_cls = _event_class("InputFileInjectedEvent")
    callback = Callback()
    v4_events = [
        blackboard_reduce_cls(
            from_phase="draft",
            to_phase="review",
            changed_keys=["summary"],
            blackboard_snapshot={"summary": "ok"},
            reducer="merge",
        ),
        input_dispatch_cls(
            from_phase="draft",
            to_phase="review",
            changed_keys=["summary"],
            blackboard_snapshot={"summary": "ok"},
            dispatched_keys=["summary"],
            branch_index=None,
        ),
        input_file_injected_cls(
            from_phase=None,
            to_phase="draft",
            changed_keys=["brief"],
            blackboard_snapshot={"brief": "file body"},
            file_ref="inputs/brief.md",
            target_field="brief",
        ),
    ]

    with caplog.at_level(logging.WARNING, logger="graph_agent.callbacks.base"):
        for event in v4_events:
            callback.on_event(event)

    assert "unrecognised event type" not in caplog.text
