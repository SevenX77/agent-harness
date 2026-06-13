from __future__ import annotations

import importlib
from typing import Any

import httpx
import pytest

SCHEMA_VERSION = "studio.mvp1.v1"


def test_engine_adapter_exposes_artifact_primitives() -> None:
    EngineAdapter = _load_symbol("app.core.adapters.engine", "EngineAdapter")

    adapter = EngineAdapter(transport="in_process")

    for method_name in ("compile", "run_artifact", "predict_artifact", "resume"):
        method = getattr(adapter, method_name, None)
        assert callable(method), f"EngineAdapter must expose {method_name}()"


def test_gateway_adapter_exposes_gateway_primitives() -> None:
    GatewayAdapter = _load_symbol("app.core.adapters.gateway", "GatewayAdapter")

    adapter = GatewayAdapter(transport="in_process")

    for method_name in (
        "resolve_routes",
        "materialize_role",
        "project_route_state",
        "decide_fallback",
        "resolve_credential",
    ):
        method = getattr(adapter, method_name, None)
        assert callable(method), f"GatewayAdapter must expose {method_name}()"


@pytest.mark.parametrize(
    ("module_name", "class_name"),
    (
        ("app.core.adapters.engine", "EngineAdapter"),
        ("app.core.adapters.gateway", "GatewayAdapter"),
    ),
)
@pytest.mark.parametrize("transport", ("in_process", "http_loopback"))
def test_adapters_accept_in_process_and_http_loopback_transports(
    module_name: str,
    class_name: str,
    transport: str,
) -> None:
    Adapter = _load_symbol(module_name, class_name)

    adapter = Adapter(transport=transport)

    assert adapter.transport == transport


def test_http_transport_sends_idempotency_key_and_validates_schema_version() -> None:
    HttpTransport = _load_symbol("app.core.adapters.http_transport", "HttpTransport")
    seen: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["idempotency_key"] = request.headers.get("Idempotency-Key")
        seen["payload"] = request.read()
        return httpx.Response(
            200,
            json={
                "schema_version": SCHEMA_VERSION,
                "ok": True,
                "data": {"run_id": "run-123"},
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

    assert seen["idempotency_key"] == "idem-run-123"
    assert b"artifact-123" in seen["payload"]
    assert result == {"run_id": "run-123"}


def test_http_transport_rejects_response_schema_mismatch() -> None:
    HttpTransport = _load_symbol("app.core.adapters.http_transport", "HttpTransport")

    transport = HttpTransport(
        base_url="http://studio-loopback.test",
        http_client=httpx.Client(
            transport=httpx.MockTransport(
                lambda _request: httpx.Response(
                    200,
                    json={
                        "schema_version": "gateway.experimental.v0",
                        "ok": True,
                        "data": {"run_id": "run-123"},
                    },
                )
            )
        ),
        schema_version=SCHEMA_VERSION,
    )

    with pytest.raises(Exception) as exc_info:
        transport.post(
            "/engine/run_artifact",
            {"artifact_ref": {"artifact_id": "artifact-123"}},
            idempotency_key="idem-run-123",
        )

    assert _error_code(exc_info.value) == "transport.schema_mismatch"


def _load_symbol(module_name: str, symbol_name: str) -> Any:
    try:
        module = importlib.import_module(module_name)
    except ModuleNotFoundError as exc:
        pytest.fail(f"{module_name} is missing for the Studio MVP1 adapter contract: {exc}")
    try:
        return getattr(module, symbol_name)
    except AttributeError:
        pytest.fail(f"{module_name}.{symbol_name} is missing from the Studio MVP1 adapter contract")


def _error_code(exc: BaseException) -> str | None:
    return getattr(exc, "error_code", None) or getattr(exc, "code", None)
