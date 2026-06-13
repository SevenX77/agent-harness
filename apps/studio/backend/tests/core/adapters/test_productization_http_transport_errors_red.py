from __future__ import annotations

import json
from collections.abc import Iterator
from typing import Any

import httpx
import pytest
from app.core.adapters.http_transport import (
    SCHEMA_VERSION,
    HttpTransport,
    StudioAdapterError,
)


def test_http_5xx_preserves_response_envelope_error_payload() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            503,
            json={
                "schema_version": SCHEMA_VERSION,
                "ok": False,
                "error_code": "engine.overloaded",
                "error_payload": {"retry_after_ms": 250, "worker": "engine-a"},
            },
        )

    transport = HttpTransport(
        base_url="http://studio-loopback.test",
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
        schema_version=SCHEMA_VERSION,
    )

    with pytest.raises(StudioAdapterError) as exc_info:
        transport.post(
            "/engine/run_artifact",
            {"artifact_ref": {"artifact_id": "artifact-123"}},
            idempotency_key="idem-run-123",
        )

    assert exc_info.value.error_code == "engine.overloaded"
    assert exc_info.value.error_payload == {"retry_after_ms": 250, "worker": "engine-a"}


def test_timeout_retry_reuses_idempotency_key_without_duplicate_execution() -> None:
    attempts: list[str | None] = []
    executions = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal executions
        attempts.append(request.headers.get("Idempotency-Key"))
        if len(attempts) == 1:
            raise httpx.TimeoutException("engine did not answer before deadline")
        executions += 1
        return httpx.Response(
            200,
            json={
                "schema_version": SCHEMA_VERSION,
                "ok": True,
                "data": {"run_id": "run-123", "executions": executions},
            },
        )

    transport = HttpTransport(
        base_url="http://studio-loopback.test",
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
        schema_version=SCHEMA_VERSION,
    )

    result = transport.post(
        "/engine/run_artifact",
        {"artifact_ref": {"artifact_id": "artifact-123"}},
        idempotency_key="idem-run-123",
    )

    assert result == {"run_id": "run-123", "executions": 1}
    assert attempts == ["idem-run-123", "idem-run-123"]


def test_event_stream_resume_deduplicates_repeated_sequence() -> None:
    def events_after_disconnect() -> Iterator[dict[str, Any]]:
        yield {"seq": 4, "event": {"type": "token", "value": "already-seen"}}
        yield {"seq": 5, "event": {"type": "token", "value": "next"}}

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.params.get("cursor") == "4"
        lines = [
            {
                "schema_version": SCHEMA_VERSION,
                "ok": True,
                "data": event,
            }
            for event in events_after_disconnect()
        ]
        body = "\n".join(json.dumps(line) for line in lines)
        return httpx.Response(200, content=body)

    transport = HttpTransport(
        base_url="http://studio-loopback.test",
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
        schema_version=SCHEMA_VERSION,
    )

    resumed = list(
        transport.stream_events(
            "/engine/runs/run-123/events",
            cursor=4,
            idempotency_key="idem-run-123-events",
        )
    )

    assert resumed == [{"seq": 5, "event": {"type": "token", "value": "next"}}]
