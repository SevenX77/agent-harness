from __future__ import annotations

import json
import logging
from pathlib import Path

from pydantic import TypeAdapter

from graph_agent.callbacks.base import Callback
from graph_agent.callbacks.events import (
    AmbiguityLoggedEvent,
    BuiltinSubagentEnterEvent,
    BuiltinSubagentExitEvent,
    BuiltinSubagentFallbackEvent,
    CallbackEvent,
)
from graph_agent.callbacks.tracing import TracingCallback


def test_builtin_subagent_trace_events_round_trip_through_callback_union() -> None:
    adapter = TypeAdapter(CallbackEvent)

    for event in [
        AmbiguityLoggedEvent(
            phase_name="main",
            ambiguity_type="ambiguous_requirement",
            question="Q",
            decision="D",
            reason="R",
        ),
        BuiltinSubagentEnterEvent(phase_name="main", builtin_name="reference_reader"),
        BuiltinSubagentExitEvent(phase_name="main", builtin_name="reference_reader"),
        BuiltinSubagentFallbackEvent(
            phase_name="main",
            builtin_name="reference_reader",
            fallback_reason="config_missing",
            fallback_strategy="raw_excerpt",
            excerpt_token_limit=3000,
            warning="[F-v3-reference-reader-failed] missing config",
        ),
    ]:
        parsed = adapter.validate_python(event.model_dump())
        assert parsed.event_type == event.event_type


def test_default_callback_accepts_v030_typed_only_events_without_warning(caplog) -> None:
    callback = Callback()
    events = [
        AmbiguityLoggedEvent(
            phase_name="main",
            ambiguity_type="ambiguous_requirement",
            question="Q",
            decision="D",
            reason="R",
        ),
        BuiltinSubagentEnterEvent(phase_name="main", builtin_name="reference_reader"),
        BuiltinSubagentExitEvent(phase_name="main", builtin_name="reference_reader"),
        BuiltinSubagentFallbackEvent(
            phase_name="main",
            builtin_name="reference_reader",
            fallback_reason="local_io_error",
            fallback_strategy="raw_excerpt_3000_tokens",
            excerpt_token_limit=3000,
            warning="[F-v3-reference-reader-failed] local fallback read failed",
        ),
    ]

    with caplog.at_level(logging.WARNING, logger="graph_agent.callbacks.base"):
        for event in events:
            callback.on_event(event)

    assert "unrecognised event type" not in caplog.text


def test_tracing_callback_writes_v030_typed_events(tmp_path: Path) -> None:
    tracer = TracingCallback(trace_dir=tmp_path)
    tracer.on_event(
        BuiltinSubagentFallbackEvent(
            phase_name="main",
            builtin_name="reference_reader",
            fallback_reason="remote_timeout",
            fallback_strategy="raw_excerpt",
        )
    )

    lines = (tmp_path / "trace.jsonl").read_text(encoding="utf-8").splitlines()
    payload = json.loads(lines[0])
    assert payload["event_type"] == "builtin_subagent_fallback"
    assert payload["fallback_reason"] == "remote_timeout"
