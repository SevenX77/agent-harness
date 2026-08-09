from __future__ import annotations

import builtins
import dataclasses
import importlib
import inspect
import json
from datetime import UTC, datetime
from typing import Any

import pytest


def _fields(cls: type[Any]) -> set[str]:
    if hasattr(cls, "model_fields"):
        return set(cls.model_fields)
    if dataclasses.is_dataclass(cls):
        return {field.name for field in dataclasses.fields(cls)}
    try:
        return {
            name
            for name in inspect.signature(cls).parameters
            if name != "self"
        }
    except (TypeError, ValueError):
        return set(getattr(cls, "__annotations__", {}))


def test_llm_provider_contract_import_does_not_pull_gateway_concrete_module(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    real_import = builtins.__import__
    blocked_imports: list[str] = []

    def guarded_import(name: str, *args: Any, **kwargs: Any) -> Any:
        if name.startswith("graph_agent_gateway"):
            blocked_imports.append(name)
            raise AssertionError(f"engine SPI import must not import {name}")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", guarded_import)
    module = importlib.import_module("graph_agent.core.llm_provider")

    assert callable(getattr(module.LLMProvider, "stream", None))
    assert blocked_imports == []


def test_event_envelope_and_stream_cursor_expose_resume_and_gap_contract() -> None:
    event_contracts = importlib.import_module("graph_agent.core.event_contracts")

    EventEnvelope = event_contracts.EventEnvelope
    StreamCursor = event_contracts.StreamCursor

    assert {
        "schema_version",
        "stream_id",
        "seq",
        "run_id",
        "event_type",
        "payload",
        "cursor",
        "timestamp",
        "error_code",
        "error_payload",
    } <= _fields(EventEnvelope)
    assert {
        "stream_id",
        "cursor",
        "next_seq",
        "window_start_seq",
    } <= _fields(StreamCursor)

    cursor = StreamCursor(
        stream_id="stream-run-1",
        cursor="stream-run-1:41",
        next_seq=42,
        window_start_seq=1,
    )
    event = EventEnvelope(
        schema_version="studio.event.v1",
        stream_id="stream-run-1",
        seq=42,
        run_id="run-1",
        event_type="phase_started",
        payload={"phase": "draft"},
        cursor=cursor.cursor,
        timestamp=datetime.now(UTC),
    )

    assert event.seq == cursor.next_seq
    assert event.cursor == "stream-run-1:41"
    assert event.schema_version == "studio.event.v1"


def test_event_error_payload_is_structured_and_sanitized() -> None:
    event_contracts = importlib.import_module("graph_agent.core.event_contracts")

    TransportErrorPayload = event_contracts.TransportErrorPayload
    make_event_envelope = event_contracts.make_event_envelope

    event = make_event_envelope(
        stream_id="stream-run-1",
        seq=7,
        run_id="run-1",
        event_type="stream.error",
        payload={},
        error_code="stream.cursor_gap",
        error_payload=TransportErrorPayload(
            error_code="stream.cursor_gap",
            message="cursor gap sk-live-secret Traceback (most recent call last)",
            details={
                "api_key": "sk-live-secret",
                "traceback": "Traceback (most recent call last):\nboom",
                "safe": "visible",
            },
            retryable=True,
        ),
    )

    dumped = json.dumps(event.model_dump(mode="json"), sort_keys=True)

    assert event.error_payload is not None
    assert event.error_payload.message == "[redacted]"
    assert event.error_payload.details["api_key"] == "[redacted]"
    assert event.error_payload.details["traceback"] == "[redacted]"
    assert event.error_payload.details["safe"] == "visible"
    assert "sk-live-secret" not in dumped
    assert "Traceback (most recent call last)" not in dumped


def test_response_envelope_has_schema_version_and_structured_error_payload() -> None:
    event_contracts = importlib.import_module("graph_agent.core.event_contracts")

    ResponseEnvelope = event_contracts.ResponseEnvelope
    TransportErrorPayload = event_contracts.TransportErrorPayload

    assert {
        "schema_version",
        "ok",
        "data",
        "error_code",
        "error_payload",
    } <= _fields(ResponseEnvelope)
    assert {
        "error_code",
        "message",
        "details",
        "retryable",
    } <= _fields(TransportErrorPayload)

    error_payload = TransportErrorPayload(
        error_code="artifact.sealed_write",
        message="run is sealed",
        details={"run_id": "run-1"},
        retryable=False,
    )
    envelope = ResponseEnvelope(
        schema_version="engine.response.v1",
        ok=False,
        data=None,
        error_code="artifact.sealed_write",
        error_payload=error_payload,
    )

    assert envelope.schema_version == "engine.response.v1"
    assert envelope.ok is False
    assert envelope.error_code == "artifact.sealed_write"
    assert envelope.error_payload.details == {"run_id": "run-1"}


def test_response_envelope_rejects_unstructured_error_payload() -> None:
    event_contracts = importlib.import_module("graph_agent.core.event_contracts")
    ResponseEnvelope = event_contracts.ResponseEnvelope

    with pytest.raises((TypeError, ValueError)):
        ResponseEnvelope(
            schema_version="engine.response.v1",
            ok=False,
            data=None,
            error_code="artifact.sealed_write",
            error_payload="sealed",
        )
