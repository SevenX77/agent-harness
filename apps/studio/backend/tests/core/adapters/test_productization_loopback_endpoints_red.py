from __future__ import annotations

from typing import Any

import httpx
import pytest
from app.core.adapters.http_transport import SCHEMA_VERSION, HttpTransport, StudioAdapterError
from app.core.adapters.loopback_host import LOOPBACK_TOKEN_HEADER
from app.core.backends import clear_backend_caches, get_backend_config
from app.main import create_app
from fastapi.testclient import TestClient
from pydantic import BaseModel, ValidationError


def _fallback_route_error(route_id: str) -> dict[str, Any]:
    return {
        "classification": {
            "action": "fallback_route",
            "scope": "endpoint",
            "error_class": "ProviderStatusError",
            "status_code": 401,
            "route_id": route_id,
            "message": "classified by Gateway error-classification SSOT",
            "retryable": False,
            "fallback_eligible": True,
        }
    }


def test_engine_loopback_endpoints_return_response_envelopes(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.core.adapters import engine as engine_module

    monkeypatch.setattr(
        engine_module.EngineAdapter,
        "compile",
        lambda _self, payload: {"artifact_id": payload["skill_id"], "content_hash": "hash-123"},
    )
    monkeypatch.setattr(engine_module.EngineAdapter, "run_artifact", lambda _self, payload: {"run_id": "run-123"})
    monkeypatch.setattr(
        engine_module.EngineAdapter,
        "predict_artifact",
        lambda _self, payload: {"prediction": "ok", "artifact_id": payload["artifact_ref"]["artifact_id"]},
    )
    monkeypatch.setattr(engine_module.EngineAdapter, "resume", lambda _self, payload: {"run_id": payload["run_id"]})

    client = _client()

    engine_cases = [
        ("/engine/compile", {"skill_dir": "/tmp/demo", "skill_id": "demo.skill"}),
        ("/engine/run_artifact", {"artifact_ref": {"artifact_id": "artifact-123"}}),
        ("/engine/predict_artifact", {"artifact_ref": {"artifact_id": "artifact-123"}}),
        ("/engine/resume", {"skill_id": "demo.skill", "run_id": "run-123"}),
    ]

    for path, payload in engine_cases:
        response = client.post(path, json=payload)
        assert response.status_code == 200
        envelope = response.json()
        assert envelope["schema_version"] == SCHEMA_VERSION
        assert envelope["ok"] is True
        assert isinstance(envelope["data"], dict)


def test_gateway_loopback_endpoints_return_response_envelopes(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.core.adapters import gateway as gateway_module

    monkeypatch.setattr(gateway_module.GatewayAdapter, "resolve_routes", lambda _self, _payload: {"routes": []})
    monkeypatch.setattr(gateway_module.GatewayAdapter, "materialize_role", lambda _self, payload: payload["role"])
    monkeypatch.setattr(
        gateway_module.GatewayAdapter,
        "project_route_state",
        lambda _self, _payload: {"ui_state": "ready", "reason_code": None, "retry_at": None, "ui_detail": None},
    )
    monkeypatch.setattr(
        gateway_module.GatewayAdapter,
        "decide_fallback",
        lambda _self, _payload: {"decision": "retry_same"},
    )
    monkeypatch.setattr(
        gateway_module.GatewayAdapter,
        "resolve_credential",
        lambda _self, _payload: {"secret_handle": "secret-handle://studio-local/" + ("a" * 32)},
    )

    client = _client()

    gateway_cases = [
        ("/gateway/resolve_routes", {"role_name": "graph_agent"}),
        ("/gateway/materialize_role", {"role": {"system_prompt_prefix": ""}, "credentials": {"schema_version": 4}}),
        (
            "/gateway/materialize_model_bundle",
            {
                "bundle": {
                    "model_profile_id": "fast",
                    "display_name": "Fast",
                    "canonical_id": "fast",
                    "model_groups": [],
                },
                "credentials": {"schema_version": 4},
            },
        ),
        (
            "/gateway/project_route_state",
            {"endpoint": {}, "route": {}, "circuits": [], "now": "2026-06-17T00:00:00+00:00"},
        ),
        ("/gateway/decide_fallback", {"fallback_chain": [{"route_id": "openai:gpt-5"}]}),
        (
            "/gateway/resolve_credential",
            {"credentials": {"schema_version": 4}, "credential_ref": "openai"},
        ),
    ]

    for path, payload in gateway_cases:
        response = client.post(path, json=payload)
        assert response.status_code == 200
        envelope = response.json()
        assert envelope["schema_version"] == SCHEMA_VERSION
        assert envelope["ok"] is True
        assert isinstance(envelope["data"], dict)


@pytest.mark.parametrize(
    ("path", "adapter_module_name", "adapter_class_name", "method_name", "payload"),
    (
        ("/engine/compile", "engine", "EngineAdapter", "compile", {"skill_id": "demo.skill", "skill_dir": "/tmp/demo"}),
        ("/engine/run_artifact", "engine", "EngineAdapter", "run_artifact", {"artifact_ref": {"artifact_id": "a"}}),
        (
            "/engine/predict_artifact",
            "engine",
            "EngineAdapter",
            "predict_artifact",
            {"artifact_ref": {"artifact_id": "a"}},
        ),
        ("/engine/resume", "engine", "EngineAdapter", "resume", {"skill_id": "demo.skill", "run_id": "run-123"}),
        ("/gateway/resolve_routes", "gateway", "GatewayAdapter", "resolve_routes", {"role_name": "graph_agent"}),
        (
            "/gateway/materialize_role",
            "gateway",
            "GatewayAdapter",
            "materialize_role",
            {"role": {}, "credentials": {"schema_version": 4}},
        ),
        (
            "/gateway/materialize_model_bundle",
            "gateway",
            "GatewayAdapter",
            "materialize_model_bundle",
            {
                "bundle": {
                    "model_profile_id": "fast",
                    "display_name": "Fast",
                    "canonical_id": "fast",
                    "model_groups": [],
                },
                "credentials": {"schema_version": 4},
            },
        ),
        (
            "/gateway/project_route_state",
            "gateway",
            "GatewayAdapter",
            "project_route_state",
            {"endpoint": {}, "route": {}, "circuits": []},
        ),
        ("/gateway/decide_fallback", "gateway", "GatewayAdapter", "decide_fallback", {"fallback_chain": []}),
        (
            "/gateway/resolve_credential",
            "gateway",
            "GatewayAdapter",
            "resolve_credential",
            {"credentials": {"schema_version": 4}, "credential_ref": "openai"},
        ),
    ),
)
def test_loopback_endpoints_map_owner_errors_to_response_envelopes(
    monkeypatch: pytest.MonkeyPatch,
    path: str,
    adapter_module_name: str,
    adapter_class_name: str,
    method_name: str,
    payload: dict[str, Any],
) -> None:
    adapter_module = __import__(f"app.core.adapters.{adapter_module_name}", fromlist=[adapter_class_name])
    adapter_class = getattr(adapter_module, adapter_class_name)

    def fail_with_owner_error(_self: object, _payload: dict[str, Any]) -> Any:
        raise StudioAdapterError("owner.test_failure", {"path": path, "owner": adapter_module_name})

    monkeypatch.setattr(adapter_class, method_name, fail_with_owner_error)

    response = _client().post(path, json=payload)

    assert response.status_code == 200
    assert response.json() == {
        "schema_version": SCHEMA_VERSION,
        "ok": False,
        "error_code": "owner.test_failure",
        "error_payload": {"path": path, "owner": adapter_module_name},
    }


@pytest.mark.parametrize(
    ("exc_factory", "expected_error_code"),
    (
        (lambda: KeyError("fallback_chain"), "loopback.owner_key_error"),
        (lambda: ValueError("invalid fallback attempt"), "loopback.validation_failed"),
    ),
)
def test_loopback_endpoints_map_owner_validation_errors_to_response_envelopes(
    monkeypatch: pytest.MonkeyPatch,
    exc_factory: Any,
    expected_error_code: str,
) -> None:
    from app.core.adapters import gateway as gateway_module

    def fail_with_validation_error(_self: object, _payload: dict[str, Any]) -> Any:
        raise exc_factory()

    monkeypatch.setattr(gateway_module.GatewayAdapter, "decide_fallback", fail_with_validation_error)

    response = _client().post("/gateway/decide_fallback", json={"fallback_chain": []})

    assert response.status_code == 200
    envelope = response.json()
    assert envelope["schema_version"] == SCHEMA_VERSION
    assert envelope["ok"] is False
    assert envelope["error_code"] == expected_error_code
    assert isinstance(envelope["error_payload"], dict)


def test_loopback_endpoints_map_pydantic_validation_errors_to_response_envelopes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.core.adapters import gateway as gateway_module

    class RequiredPayload(BaseModel):
        required: str

    def fail_with_pydantic_validation_error(_self: object, _payload: dict[str, Any]) -> Any:
        try:
            RequiredPayload.model_validate({})
        except ValidationError as exc:
            raise exc
        raise AssertionError("expected validation error")

    monkeypatch.setattr(
        gateway_module.GatewayAdapter,
        "decide_fallback",
        fail_with_pydantic_validation_error,
    )

    response = _client().post("/gateway/decide_fallback", json={"fallback_chain": []})

    assert response.status_code == 200
    assert response.json()["schema_version"] == SCHEMA_VERSION
    assert response.json()["ok"] is False
    assert response.json()["error_code"] == "loopback.validation_failed"
    assert "errors" in response.json()["error_payload"]


def test_loopback_endpoints_map_unknown_owner_errors_to_safe_5xx_envelopes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.core.adapters import gateway as gateway_module

    def fail_with_unknown_error(_self: object, _payload: dict[str, Any]) -> Any:
        raise RuntimeError("database details must not leak")

    monkeypatch.setattr(gateway_module.GatewayAdapter, "decide_fallback", fail_with_unknown_error)

    response = _client().post("/gateway/decide_fallback", json={"fallback_chain": []})

    assert response.status_code == 500
    assert response.json() == {
        "schema_version": SCHEMA_VERSION,
        "ok": False,
        "error_code": "loopback.internal_error",
        "error_payload": {"detail": "Loopback owner failed"},
    }


def test_loopback_endpoints_reject_authenticated_non_internal_callers() -> None:
    client = TestClient(create_app())

    response = client.post(
        "/gateway/decide_fallback",
        json={"fallback_chain": []},
        headers={"Authorization": "Bearer studio-test-token"},
    )

    assert response.status_code == 403
    assert response.json() == {
        "schema_version": SCHEMA_VERSION,
        "ok": False,
        "error_code": "LOOPBACK_FORBIDDEN",
        "error_payload": {
            "http_status": 403,
            "message": "Loopback endpoints require an internal loopback token",
            "retry_strategy": "not_retryable",
        },
    }


def test_gateway_factory_http_loopback_decide_fallback_uses_internal_auth_headers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.core.adapters import http_transport as http_transport_module
    from app.core.adapters.transport_factory import build_gateway_adapter

    monkeypatch.setenv("STUDIO_GATEWAY_TRANSPORT", "http_loopback")
    monkeypatch.setenv("STUDIO_GATEWAY_LOOPBACK_BASE_URL", "http://studio-loopback.test")
    monkeypatch.setenv("STUDIO_LOOPBACK_TOKEN", "loopback-secret")
    clear_backend_caches()

    client = TestClient(create_app())
    real_httpx_client = httpx.Client

    def handler(request: httpx.Request) -> httpx.Response:
        response = client.request(
            request.method,
            request.url.path,
            content=request.content,
            headers=dict(request.headers),
        )
        return httpx.Response(
            status_code=response.status_code,
            headers=dict(response.headers),
            content=response.content,
            request=request,
        )

    monkeypatch.setattr(
        http_transport_module.httpx,
        "Client",
        lambda: real_httpx_client(transport=httpx.MockTransport(handler)),
    )

    result = build_gateway_adapter().decide_fallback(
        {
            "fallback_chain": [{"route_id": "openai:gpt-5"}, {"route_id": "anthropic:claude-sonnet"}],
            "failed_route_ids": ["openai:gpt-5"],
            "attempt": 1,
            "error": _fallback_route_error("openai:gpt-5"),
        }
    )

    assert result["decision"] == "switch_route"
    assert result["route_id"] == "anthropic:claude-sonnet"


def test_http_loopback_adapter_path_matches_in_process_gateway_decide_fallback() -> None:
    from app.core.adapters.gateway import GatewayAdapter

    payload = {
        "fallback_chain": [{"route_id": "openai:gpt-5"}, {"route_id": "anthropic:claude-sonnet"}],
        "failed_route_ids": ["openai:gpt-5"],
        "attempt": 1,
        "error": _fallback_route_error("openai:gpt-5"),
    }

    in_process = GatewayAdapter(transport="in_process").decide_fallback(payload)
    loopback = GatewayAdapter(
        transport="http_loopback",
        http_transport=_test_client_http_transport(),
    ).decide_fallback(payload)

    assert loopback == in_process


def test_http_loopback_adapter_path_maps_gateway_owner_error_like_in_process() -> None:
    from app.core.adapters.gateway import GatewayAdapter

    payload = {
        "fallback_chain": [{"route_id": "openai:gpt-5"}],
        "failed_route_ids": ["openai:gpt-5"],
        "attempt": 1,
        "role": "graph_agent",
    }

    with pytest.raises(StudioAdapterError) as in_process_exc:
        GatewayAdapter(transport="in_process").decide_fallback(payload)

    with pytest.raises(StudioAdapterError) as exc_info:
        GatewayAdapter(transport="http_loopback", http_transport=_test_client_http_transport()).decide_fallback(payload)

    assert exc_info.value.error_code == in_process_exc.value.error_code
    assert exc_info.value.error_payload == in_process_exc.value.error_payload


def _client() -> TestClient:
    client = TestClient(create_app())
    client.headers["Authorization"] = "Bearer studio-test-token"
    client.headers[LOOPBACK_TOKEN_HEADER] = get_backend_config().loopback_token
    return client


def _test_client_http_transport() -> HttpTransport:
    client = _client()

    def handler(request: httpx.Request) -> httpx.Response:
        response = client.request(
            request.method,
            request.url.path,
            content=request.content,
            headers=dict(request.headers),
        )
        return httpx.Response(
            status_code=response.status_code,
            headers=dict(response.headers),
            content=response.content,
            request=request,
        )

    return HttpTransport(
        base_url="http://studio-loopback.test",
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
        headers={
            "Authorization": "Bearer studio-test-token",
            LOOPBACK_TOKEN_HEADER: get_backend_config().loopback_token,
        },
    )
