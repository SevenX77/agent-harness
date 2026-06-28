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


def test_non_envelope_http_4xx_is_transport_error_not_serialization_failure() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, text="not found")

    transport = HttpTransport(
        base_url="http://studio-loopback.test",
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
        schema_version=SCHEMA_VERSION,
    )

    with pytest.raises(StudioAdapterError) as exc_info:
        transport.post("/engine/missing", {}, idempotency_key="idem-missing")

    assert exc_info.value.error_code == "transport.http_4xx"
    assert exc_info.value.error_payload == {"status_code": 404}


def test_http_4xx_response_envelope_preserves_owner_error_payload() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            403,
            json={
                "schema_version": SCHEMA_VERSION,
                "ok": False,
                "error_code": "LOOPBACK_FORBIDDEN",
                "error_payload": {"message": "internal token required"},
            },
        )

    transport = HttpTransport(
        base_url="http://studio-loopback.test",
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
        schema_version=SCHEMA_VERSION,
    )

    with pytest.raises(StudioAdapterError) as exc_info:
        transport.post("/gateway/decide_fallback", {}, idempotency_key="idem-forbidden")

    assert exc_info.value.error_code == "LOOPBACK_FORBIDDEN"
    assert exc_info.value.error_payload == {"message": "internal token required"}


def test_event_stream_5xx_preserves_response_envelope_error_payload() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "GET"
        assert str(request.url) == "http://studio-loopback.test/engine/runs/run-123/events?cursor=4"
        assert request.headers.get("Idempotency-Key") == "idem-run-123-events"
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
        list(
            transport.stream_events(
                "/engine/runs/run-123/events",
                cursor=4,
                idempotency_key="idem-run-123-events",
            )
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
