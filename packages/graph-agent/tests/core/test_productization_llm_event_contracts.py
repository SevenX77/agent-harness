from __future__ import annotations

import builtins
import dataclasses
import importlib
import inspect
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

    assert callable(getattr(module.LLMProvider, "invoke", None))
    assert blocked_imports == []


def test_event_envelope_and_stream_cursor_expose_resume_and_gap_contract() -> None:
    event_contracts = importlib.import_module("graph_agent.core.event_contracts")

    EventEnvelope = event_contracts.EventEnvelope
    StreamCursor = event_contracts.StreamCursor

    assert {
        "stream_id",
        "seq",
        "run_id",
        "event_type",
        "payload",
        "cursor",
        "timestamp",
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
