from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest
from pydantic import SecretStr

BACKEND_ROOT = next(
    parent for parent in Path(__file__).resolve().parents if (parent / "app").is_dir() and (parent / "tests").is_dir()
)

GATEWAY_OWNER_PATHS = (
    "app/core/adapters/gateway.py",
    "app/core/adapters/engine.py",
    "app/services/gateway_resolver.py",
)


def test_gateway_owner_paths_do_not_use_registry_snapshot_model_resolver_contract() -> None:
    offenders: list[str] = []
    for relative_path in GATEWAY_OWNER_PATHS:
        source = (BACKEND_ROOT / relative_path).read_text(encoding="utf-8")
        if "ModelResolver(registry_snapshot" in source:
            offenders.append(f"{relative_path} still constructs ModelResolver(registry_snapshot=...)")

    assert offenders == []


def test_llm_router_uses_gateway_adapter_for_copilot_settings_and_fallbacks() -> None:
    source = (BACKEND_ROOT / "app" / "routers" / "llm.py").read_text(encoding="utf-8")

    assert "build_gateway_adapter" in source
    assert "ModelResolver(" not in source
    assert "from app.services.llm_role_materializer import" not in source
    assert "from app.services.llm_state_projection import" not in source
    assert "project_provider_model_state(" not in source


def test_role_materializer_delegates_provider_projection_to_gateway_adapter() -> None:
    source = (BACKEND_ROOT / "app" / "services" / "llm_role_materializer.py").read_text(encoding="utf-8")

    assert "build_gateway_adapter" in source
    assert "from app.services.llm_state_projection import" not in source
    assert "project_provider_model_state" not in source


def test_gateway_adapter_projects_failed_state_as_gateway_owned_state() -> None:
    from app.core.adapters.gateway import GatewayAdapter
    from app.models.llm_config import ProviderEndpoint, ProviderRoute

    endpoint = ProviderEndpoint(
        endpoint_id="openai",
        display_name="OpenAI",
        protocol="openai_compatible",
        base_url="https://api.openai.example/v1",
        api_key=SecretStr("secret"),
        status="failed",
        metadata={"reason_code": "endpoint_unreachable"},
    )
    route = ProviderRoute(
        route_id="openai:gpt-5",
        endpoint_id="openai",
        route_slug="gpt-5",
        provider_model_id="gpt-5",
        canonical_id="gpt-5",
        status="verified",
    )

    projection = GatewayAdapter(transport="in_process").project_route_state(
        {
            "endpoint": endpoint,
            "route": route,
            "circuits": [],
            "now": datetime.now(UTC),
        }
    )

    assert projection.ui_state == "failed"
    assert projection.reason_code == "endpoint_unreachable"


def test_gateway_adapter_in_process_decides_fallback_route() -> None:
    from app.core.adapters.gateway import GatewayAdapter

    decision = GatewayAdapter(transport="in_process").decide_fallback(
        {
            "fallback_chain": [
                {"route_id": "openai:gpt-5"},
                {"route_id": "anthropic:claude"},
            ],
            "failed_route_ids": ["openai:gpt-5"],
            "error": {"status_code": 503, "message": "provider unavailable"},
        }
    )

    assert decision == {
        "decision": "switch_route",
        "route_id": "anthropic:claude",
        "retry_same": False,
        "give_up": False,
    }


def test_gateway_adapter_delegates_fallback_decision_to_gateway_owner(monkeypatch) -> None:
    import app.core.adapters.gateway as gateway_module
    from app.core.adapters.gateway import GatewayAdapter
    from graph_agent_gateway.fallback_decision import FallbackDecision

    captured: dict[str, object] = {}

    def _spy(request: object) -> FallbackDecision:
        captured["request"] = request
        return FallbackDecision(
            action="switch_route",
            reason_code="owner_decided",
            next_route_id="owner:sentinel",
        )

    monkeypatch.setattr(gateway_module, "gateway_decide_fallback", _spy, raising=False)

    decision = GatewayAdapter(transport="in_process").decide_fallback(
        {
            "fallback_chain": [
                {"route_id": "primary:gpt-5"},
                {"route_id": "fallback:gpt-5-mini"},
            ],
            "current_route_id": "primary:gpt-5",
            "failed_route_ids": ["primary:gpt-5"],
            "error": {"status_code": 503, "message": "provider unavailable"},
        }
    )

    assert captured["request"].route_ids == ["primary:gpt-5", "fallback:gpt-5-mini"]  # type: ignore[attr-defined]
    assert decision == {
        "decision": "switch_route",
        "route_id": "owner:sentinel",
        "retry_same": False,
        "give_up": False,
    }


def test_gateway_adapter_surfaces_gateway_fail_fast_without_give_up_conflation(monkeypatch) -> None:
    import app.core.adapters.gateway as gateway_module
    from app.core.adapters.gateway import GatewayAdapter
    from app.core.adapters.http_transport import StudioAdapterError
    from graph_agent_gateway.fallback_decision import FallbackDecision

    def _fail_fast(_request: object) -> FallbackDecision:
        return FallbackDecision(
            action="fail_fast",
            reason_code="classification_fail_request",
            error_code="gateway.fail_fast",
            error_payload={
                "role": "graph_agent",
                "route_id": "primary:gpt-5",
                "classification": {"action": "fail_request", "status_code": 413},
            },
        )

    monkeypatch.setattr(gateway_module, "gateway_decide_fallback", _fail_fast, raising=False)

    with pytest.raises(StudioAdapterError) as exc_info:
        GatewayAdapter(transport="in_process").decide_fallback(
            {
                "role": "graph_agent",
                "fallback_chain": [
                    {"route_id": "primary:gpt-5"},
                    {"route_id": "fallback:gpt-5-mini"},
                ],
                "current_route_id": "primary:gpt-5",
            }
        )

    assert exc_info.value.error_code == "gateway.fail_fast"
    assert exc_info.value.error_payload["decision"] == "fail_fast"
    assert exc_info.value.error_payload["classification"]["action"] == "fail_request"


def test_gateway_adapter_delegates_role_materialization_to_gateway_owner(monkeypatch) -> None:
    import app.core.adapters.gateway as gateway_module
    from app.core.adapters.gateway import GatewayAdapter
    from app.models.llm_config import (
        LLMCredentialsFile,
        ProviderEndpoint,
        ProviderRoute,
        RoleEntry,
        RoleModelGroup,
        RoleRouteEntry,
    )

    class NoCircuits:
        def get_active_circuits(self, **kwargs: object) -> list[object]:
            return []

    captured: dict[str, object] = {}

    def _spy(request: object) -> SimpleNamespace:
        captured["role"] = request.role  # type: ignore[attr-defined]
        captured["credentials"] = request.credentials  # type: ignore[attr-defined]
        captured["health_store"] = request.health_store  # type: ignore[attr-defined]
        captured["evidence_records"] = request.evidence_records  # type: ignore[attr-defined]
        return SimpleNamespace(
            fallback_chain=[RoleRouteEntry(route_id="owner:sentinel")],
            materialization_report={
                "entries": [{"route_id": "owner:sentinel", "role_fit": "using"}],
                "warnings": [],
                "skipped_provider_details": [],
            },
        )

    monkeypatch.setattr(gateway_module, "gateway_materialize_role", _spy, raising=False)

    role = RoleEntry(
        model_groups=[
            RoleModelGroup(
                canonical_id="gpt-5",
                display_name="GPT-5",
                provider_models=[{"route_id": "openai:gpt-5"}],
            )
        ]
    )
    credentials = LLMCredentialsFile(
        provider_endpoints={
            "openai": ProviderEndpoint(
                endpoint_id="openai",
                display_name="OpenAI",
                protocol="openai_compatible",
                base_url="https://api.openai.example/v1",
                api_key=SecretStr("secret"),
                status="verified",
            )
        },
        provider_routes={
            "openai:gpt-5": ProviderRoute(
                route_id="openai:gpt-5",
                endpoint_id="openai",
                route_slug="gpt-5",
                provider_model_id="gpt-5",
                canonical_id="gpt-5",
                status="verified",
            )
        },
    )
    health_store = NoCircuits()
    evidence_records = [
        {
            "evidence_id": "probe-openai-gpt5",
            "evidence_type": "probe",
            "trust_state": "probe-verified",
            "endpoint_id": "openai",
            "route_id": "openai:gpt-5",
            "model_id": "gpt-5",
            "provider_model_id": "gpt-5",
            "probe_status": "ok",
        }
    ]

    materialized = GatewayAdapter(transport="in_process").materialize_role(
        {
            "role": role,
            "credentials": credentials,
            "health_store": health_store,
            "evidence_records": evidence_records,
        }
    )

    assert captured["role"] is role
    assert captured["credentials"] is credentials
    assert captured["health_store"] is health_store
    assert captured["evidence_records"] == evidence_records
    assert [entry.route_id for entry in materialized.fallback_chain] == ["owner:sentinel"]
    assert materialized.materialization_report["entries"] == [
        {"route_id": "owner:sentinel", "role_fit": "using"}
    ]


def test_gateway_credentials_filter_preserves_credential_ref_and_runtime_fields() -> None:
    from app.core.adapters.gateway import _filter_gateway_credentials

    filtered = _filter_gateway_credentials(
        {
            "schema_version": 3,
            "provider_endpoints": {
                "openai": {
                    "endpoint_id": "openai",
                    "display_name": "OpenAI",
                    "protocol": "openai_compatible",
                    "base_url": "https://api.openai.example/v1",
                    "credential_ref": "credential:openai-prod",
                    "api_key": None,
                    "status": "verified",
                    "last_test_at": "2026-06-18T00:00:00Z",
                    "rate_limit_bucket": "openai-prod",
                    "metadata": {"owner": "gateway"},
                }
            },
            "provider_routes": {
                "openai:gpt-5": {
                    "route_id": "openai:gpt-5",
                    "display_name": "GPT-5",
                    "endpoint_id": "openai",
                    "route_slug": "gpt-5",
                    "provider_model_id": "gpt-5",
                    "canonical_id": "gpt-5",
                    "status": "verified",
                    "metadata": {"runtime_owner": "gateway"},
                    "verified_profiles": [{"profile_id": "responses"}],
                }
            },
        }
    )

    endpoint = filtered["provider_endpoints"]["openai"]
    assert endpoint["credential_ref"] == "credential:openai-prod"
    assert endpoint["status"] == "verified"
    assert endpoint["rate_limit_bucket"] == "openai-prod"
    assert "display_name" not in endpoint

    route = filtered["provider_routes"]["openai:gpt-5"]
    assert route["metadata"] == {"runtime_owner": "gateway"}
    assert route["verified_profiles"] == [{"profile_id": "responses"}]
    assert "display_name" not in route


def test_gateway_adapter_in_process_resolves_endpoint_credential() -> None:
    from app.core.adapters.gateway import GatewayAdapter
    from app.models.llm_config import LLMCredentialsFile, ProviderEndpoint

    raw_secret = "sk-studio-secret"
    now = datetime.now(UTC)
    credentials = LLMCredentialsFile(
        provider_endpoints={
            "openai": ProviderEndpoint(
                endpoint_id="openai",
                display_name="OpenAI",
                protocol="openai_compatible",
                base_url="https://api.openai.example/v1",
                api_key=SecretStr(raw_secret),
                status="verified",
            )
        }
    )

    resolved = GatewayAdapter(transport="in_process").resolve_credential(
        {
            "credentials": credentials,
            "credential_ref": "endpoint:openai",
            "now": now,
            "ttl_seconds": 60,
        }
    )

    assert resolved["credential_ref"] == "endpoint:openai"
    assert resolved["secret_handle"].startswith("secret-handle://")
    assert raw_secret not in resolved["secret_handle"]
    assert resolved["expires_at"] == (now + timedelta(seconds=60)).isoformat()


def test_gateway_adapter_resolve_credential_never_returns_raw_secret_as_handle() -> None:
    from app.core.adapters.gateway import GatewayAdapter
    from app.models.llm_config import LLMCredentialsFile, ProviderEndpoint

    raw_secret = "sk-live-secret"
    now = datetime.now(UTC)
    credentials = LLMCredentialsFile(
        provider_endpoints={
            "openai": ProviderEndpoint(
                endpoint_id="openai",
                display_name="OpenAI",
                protocol="openai_compatible",
                base_url="https://api.openai.example/v1",
                api_key=SecretStr(raw_secret),
                status="verified",
            )
        }
    )

    resolved = GatewayAdapter(transport="in_process").resolve_credential(
        {
            "credentials": credentials,
            "credential_ref": "endpoint:openai",
            "now": now,
            "ttl_seconds": 300,
        }
    )

    assert raw_secret not in str(resolved)
    assert resolved["secret_handle"].startswith("secret-handle://")
    assert raw_secret not in resolved["secret_handle"]
    assert datetime.fromisoformat(resolved["expires_at"]) > now


def test_gateway_adapter_delegates_credential_resolution_to_gateway_owner(monkeypatch) -> None:
    import app.core.adapters.gateway as gateway_module
    from app.core.adapters.gateway import GatewayAdapter
    from app.models.llm_config import LLMCredentialsFile, ProviderEndpoint

    owner_expires_at = datetime.now(UTC) + timedelta(seconds=300)
    captured: dict[str, object] = {}
    credentials = LLMCredentialsFile(
        provider_endpoints={
            "openai": ProviderEndpoint(
                endpoint_id="openai",
                display_name="OpenAI",
                protocol="openai_compatible",
                base_url="https://api.openai.example/v1",
                api_key=SecretStr("sk-owner-secret"),
                status="verified",
            )
        }
    )

    def fake_gateway_resolve_credential(request: object, *, credential_provider: object) -> dict[str, object]:
        captured["request"] = request
        captured["credential_provider"] = credential_provider
        return {
            "credential_ref": request.credential_ref,  # type: ignore[attr-defined]
            "secret_handle": "secret-handle://studio-local/0123456789abcdef0123456789abcdef",
            "expires_at": owner_expires_at.isoformat(),
            "fingerprint": "owner-fingerprint",
            "scope": "owner-scope",
        }

    monkeypatch.setattr(
        gateway_module,
        "gateway_resolve_credential",
        fake_gateway_resolve_credential,
        raising=False,
    )

    resolved = GatewayAdapter(transport="in_process").resolve_credential(
        {
            "credentials": credentials,
            "credential_ref": "endpoint:openai",
            "ttl_seconds": 300,
        }
    )

    assert captured["request"].credential_ref == "endpoint:openai"  # type: ignore[attr-defined]
    assert captured["request"].ttl_seconds == 300  # type: ignore[attr-defined]
    assert captured["credential_provider"] is not None
    assert resolved == {
        "credential_ref": "endpoint:openai",
        "secret_handle": "secret-handle://studio-local/0123456789abcdef0123456789abcdef",
        "expires_at": owner_expires_at.isoformat(),
        "fingerprint": "owner-fingerprint",
        "scope": "owner-scope",
    }


def test_gateway_adapter_resolve_credential_ignores_stale_supplied_now() -> None:
    from app.core.adapters.gateway import GatewayAdapter
    from app.models.llm_config import LLMCredentialsFile, ProviderEndpoint

    credentials = LLMCredentialsFile(
        provider_endpoints={
            "openai": ProviderEndpoint(
                endpoint_id="openai",
                display_name="OpenAI",
                protocol="openai_compatible",
                base_url="https://api.openai.example/v1",
                api_key=SecretStr("secret"),
                status="verified",
            )
        }
    )

    resolved = GatewayAdapter(transport="in_process").resolve_credential(
        {
            "credentials": credentials,
            "credential_ref": "endpoint:openai",
            "now": datetime(2000, 1, 1, tzinfo=UTC),
            "ttl_seconds": 300,
        }
    )

    assert datetime.fromisoformat(resolved["expires_at"]) > datetime.now(UTC)


def test_gateway_adapter_resolve_credential_missing_secret_raises_credential_missing() -> None:
    from app.core.adapters.gateway import GatewayAdapter
    from app.core.adapters.http_transport import StudioAdapterError
    from app.models.llm_config import LLMCredentialsFile, ProviderEndpoint

    credentials = LLMCredentialsFile(
        provider_endpoints={
            "openai": ProviderEndpoint(
                endpoint_id="openai",
                display_name="OpenAI",
                protocol="openai_compatible",
                base_url="https://api.openai.example/v1",
                api_key=None,
                status="verified",
            )
        }
    )

    with pytest.raises(StudioAdapterError) as exc_info:
        GatewayAdapter(transport="in_process").resolve_credential(
            {
                "credentials": credentials,
                "credential_ref": "endpoint:openai",
                "ttl_seconds": 300,
            }
        )

    assert exc_info.value.error_code == "credential.missing"
    assert exc_info.value.error_payload == {
        "credential_ref": "endpoint:openai",
        "status": "missing",
    }


@pytest.mark.parametrize("ttl_seconds", [0, -1])
def test_gateway_adapter_resolve_credential_rejects_non_positive_ttl(ttl_seconds: int) -> None:
    from app.core.adapters.gateway import GatewayAdapter
    from app.core.adapters.http_transport import StudioAdapterError
    from app.models.llm_config import LLMCredentialsFile, ProviderEndpoint

    credentials = LLMCredentialsFile(
        provider_endpoints={
            "openai": ProviderEndpoint(
                endpoint_id="openai",
                display_name="OpenAI",
                protocol="openai_compatible",
                base_url="https://api.openai.example/v1",
                api_key=SecretStr("secret"),
                status="verified",
            )
        }
    )

    with pytest.raises(StudioAdapterError) as exc_info:
        GatewayAdapter(transport="in_process").resolve_credential(
            {
                "credentials": credentials,
                "credential_ref": "endpoint:openai",
                "ttl_seconds": ttl_seconds,
            }
        )

    assert exc_info.value.error_code == "credential.invalid_ttl"


def test_gateway_adapter_http_loopback_resolve_credential_rejects_raw_secret_handle() -> None:
    from app.core.adapters.gateway import GatewayAdapter
    from app.core.adapters.http_transport import StudioAdapterError

    raw_secret = "sk-live-secret"

    class FakeHttpTransport:
        def post(self, path: str, payload: dict[str, object]) -> dict[str, object]:
            assert path == "/gateway/resolve_credential"
            return {
                "credential_ref": "endpoint:openai",
                "secret_handle": raw_secret,
                "expires_at": (datetime.now(UTC) + timedelta(seconds=300)).isoformat(),
            }

    with pytest.raises(StudioAdapterError) as exc_info:
        GatewayAdapter(transport="http_loopback", http_transport=FakeHttpTransport()).resolve_credential(
            {"credential_ref": "endpoint:openai"}
        )

    assert exc_info.value.error_code == "credential.invalid_handle"


def test_gateway_adapter_http_loopback_resolve_credential_rejects_prefixed_raw_secret_handle() -> None:
    from app.core.adapters.gateway import GatewayAdapter
    from app.core.adapters.http_transport import StudioAdapterError

    class FakeHttpTransport:
        def post(self, path: str, payload: dict[str, object]) -> dict[str, object]:
            assert path == "/gateway/resolve_credential"
            return {
                "credential_ref": "endpoint:openai",
                "secret_handle": "secret-handle://studio-local/sk-live-secret",
                "expires_at": (datetime.now(UTC) + timedelta(seconds=300)).isoformat(),
            }

    with pytest.raises(StudioAdapterError) as exc_info:
        GatewayAdapter(transport="http_loopback", http_transport=FakeHttpTransport()).resolve_credential(
            {"credential_ref": "endpoint:openai"}
        )

    assert exc_info.value.error_code == "credential.invalid_handle"


def test_gateway_adapter_http_loopback_resolve_credential_requires_expires_at() -> None:
    from app.core.adapters.gateway import GatewayAdapter
    from app.core.adapters.http_transport import StudioAdapterError

    class FakeHttpTransport:
        def post(self, path: str, payload: dict[str, object]) -> dict[str, object]:
            assert path == "/gateway/resolve_credential"
            return {
                "credential_ref": "endpoint:openai",
                "secret_handle": "secret-handle://studio-local/abc123",
            }

    with pytest.raises(StudioAdapterError) as exc_info:
        GatewayAdapter(transport="http_loopback", http_transport=FakeHttpTransport()).resolve_credential(
            {"credential_ref": "endpoint:openai"}
        )

    assert exc_info.value.error_code == "credential.invalid_handle"


@pytest.mark.parametrize("expires_at", ["not-a-time", "2000-01-01T00:00:00+00:00"])
def test_gateway_adapter_http_loopback_resolve_credential_requires_future_expires_at(expires_at: str) -> None:
    from app.core.adapters.gateway import GatewayAdapter
    from app.core.adapters.http_transport import StudioAdapterError

    class FakeHttpTransport:
        def post(self, path: str, payload: dict[str, object]) -> dict[str, object]:
            assert path == "/gateway/resolve_credential"
            return {
                "credential_ref": "endpoint:openai",
                "secret_handle": "secret-handle://studio-local/0123456789abcdef0123456789abcdef",
                "expires_at": expires_at,
            }

    with pytest.raises(StudioAdapterError) as exc_info:
        GatewayAdapter(transport="http_loopback", http_transport=FakeHttpTransport()).resolve_credential(
            {"credential_ref": "endpoint:openai"}
        )

    assert exc_info.value.error_code == "credential.invalid_handle"


def test_gateway_adapter_http_loopback_resolve_credential_drops_unknown_fields() -> None:
    from app.core.adapters.gateway import GatewayAdapter

    raw_secret = "sk-live-secret"

    class FakeHttpTransport:
        def post(self, path: str, payload: dict[str, object]) -> dict[str, object]:
            assert path == "/gateway/resolve_credential"
            return {
                "credential_ref": "endpoint:openai",
                "secret_handle": "secret-handle://studio-local/0123456789abcdef0123456789abcdef",
                "expires_at": (datetime.now(UTC) + timedelta(seconds=300)).isoformat(),
                "debug_secret": raw_secret,
            }

    resolved = GatewayAdapter(transport="http_loopback", http_transport=FakeHttpTransport()).resolve_credential(
        {"credential_ref": "endpoint:openai"}
    )

    assert "debug_secret" not in resolved
    assert raw_secret not in str(resolved)


def test_gateway_adapter_resolve_routes_returns_route_chain_not_resolved_role() -> None:
    from app.core.adapters.gateway import GatewayAdapter
    from app.models.llm_config import (
        LLMCredentialsFile,
        ProviderEndpoint,
        ProviderRoute,
        RoleEntry,
        RoleRouteEntry,
        RolesData,
    )
    from graph_agent_gateway.route_handoff import ResolvedRouteChain, RouteSkipDiagnostic

    credentials = LLMCredentialsFile(
        provider_endpoints={
            "openai": ProviderEndpoint(
                endpoint_id="openai",
                display_name="OpenAI",
                protocol="openai_compatible",
                base_url="https://api.openai.example/v1",
                api_key=SecretStr("secret"),
                status="verified",
            )
        },
        provider_routes={
            "openai:gpt-5": ProviderRoute(
                route_id="openai:gpt-5",
                endpoint_id="openai",
                route_slug="gpt-5",
                provider_model_id="gpt-5",
                canonical_id="gpt-5",
                status="verified",
            )
        },
    )
    roles = RolesData(
        roles={
            "graph_agent": RoleEntry(
                fallback_chain=[
                    RoleRouteEntry(route_id="missing:gpt-5"),
                    RoleRouteEntry(route_id="openai:gpt-5"),
                ]
            )
        }
    )

    chain = GatewayAdapter(transport="in_process").resolve_routes(
        {
            "role_name": "graph_agent",
            "credentials": credentials,
            "roles": roles,
        }
    )

    assert isinstance(chain, ResolvedRouteChain)
    assert chain.role == "graph_agent"
    assert [route.route_id for route in chain.routes] == ["openai:gpt-5"]
    assert chain.skipped
    assert isinstance(chain.skipped[0], RouteSkipDiagnostic)
    assert chain.skipped[0].reason_code == "route_missing"
    assert not hasattr(chain, "role_name")
    assert not hasattr(chain, "lint_results")


def test_gateway_adapter_resolve_routes_forwards_route_override() -> None:
    from app.core.adapters.gateway import GatewayAdapter
    from app.models.llm_config import (
        LLMCredentialsFile,
        ProviderEndpoint,
        ProviderRoute,
        RoleEntry,
        RoleRouteEntry,
        RolesData,
    )

    credentials = LLMCredentialsFile(
        provider_endpoints={
            "openai": ProviderEndpoint(
                endpoint_id="openai",
                display_name="OpenAI",
                protocol="openai_compatible",
                base_url="https://api.openai.example/v1",
                api_key=SecretStr("secret"),
                status="verified",
            )
        },
        provider_routes={
            "openai:gpt-5": ProviderRoute(
                route_id="openai:gpt-5",
                endpoint_id="openai",
                route_slug="gpt-5",
                provider_model_id="gpt-5",
                canonical_id="gpt-5",
                status="verified",
            ),
            "openai:gpt-5-mini": ProviderRoute(
                route_id="openai:gpt-5-mini",
                endpoint_id="openai",
                route_slug="gpt-5-mini",
                provider_model_id="gpt-5-mini",
                canonical_id="gpt-5-mini",
                status="verified",
            ),
        },
    )
    roles = RolesData(
        roles={
            "graph_agent": RoleEntry(
                fallback_chain=[
                    RoleRouteEntry(route_id="openai:gpt-5"),
                    RoleRouteEntry(route_id="openai:gpt-5-mini"),
                ]
            )
        }
    )

    chain = GatewayAdapter(transport="in_process").resolve_routes(
        {
            "role_name": "graph_agent",
            "route_override": "openai:gpt-5-mini",
            "credentials": credentials,
            "roles": roles,
        }
    )

    assert [route.route_id for route in chain.routes] == ["openai:gpt-5-mini"]


def test_gateway_adapter_http_loopback_resolve_routes_validates_route_chain_response() -> None:
    from app.core.adapters.gateway import GatewayAdapter
    from graph_agent_gateway.route_handoff import ResolvedRouteChain

    class FakeHttpTransport:
        def post(self, path: str, payload: dict[str, object]) -> dict[str, object]:
            assert path == "/gateway/resolve_routes"
            assert payload["role_name"] == "graph_agent"
            return {
                "role": "graph_agent",
                "routes": [],
                "skipped": [],
                "error_code": "resource.no_available_route",
                "error_payload": {"role": "graph_agent"},
            }

    chain = GatewayAdapter(transport="http_loopback", http_transport=FakeHttpTransport()).resolve_routes(
        {"role_name": "graph_agent"}
    )

    assert isinstance(chain, ResolvedRouteChain)
    assert chain.error_code == "resource.no_available_route"


def test_gateway_adapter_http_loopback_resolve_routes_sends_json_dto_payload() -> None:
    from app.core.adapters.gateway import GatewayAdapter
    from app.models.llm_config import LLMCredentialsFile, ProviderEndpoint, ProviderRoute, RoleEntry, RolesData

    class FakeHttpTransport:
        def post(self, path: str, payload: dict[str, object]) -> dict[str, object]:
            assert path == "/gateway/resolve_routes"
            json.dumps(payload)
            assert isinstance(payload["credentials"], dict)
            assert isinstance(payload["roles"], dict)
            return {
                "role": "graph_agent",
                "routes": [],
                "skipped": [],
                "error_code": "resource.no_available_route",
                "error_payload": {"role": "graph_agent"},
            }

    credentials = LLMCredentialsFile(
        provider_endpoints={
            "openai": ProviderEndpoint(
                endpoint_id="openai",
                display_name="OpenAI",
                protocol="openai_compatible",
                base_url="https://api.openai.example/v1",
                api_key=SecretStr("secret"),
                status="verified",
            )
        },
        provider_routes={
            "openai:gpt-5": ProviderRoute(
                route_id="openai:gpt-5",
                endpoint_id="openai",
                route_slug="gpt-5",
                provider_model_id="gpt-5",
                canonical_id="gpt-5",
                status="verified",
            )
        },
    )

    chain = GatewayAdapter(transport="http_loopback", http_transport=FakeHttpTransport()).resolve_routes(
        {
            "role_name": "graph_agent",
            "credentials": credentials,
            "roles": RolesData(roles={"graph_agent": RoleEntry()}),
        }
    )

    assert chain.error_code == "resource.no_available_route"


def test_gateway_adapter_http_loopback_materialize_role_sends_json_dto_payload_and_validates_response() -> None:
    from app.core.adapters.gateway import GatewayAdapter
    from app.models.llm_config import LLMCredentialsFile, ProviderEndpoint, RoleEntry, RoleRouteEntry

    class FakeHttpTransport:
        def post(self, path: str, payload: dict[str, object]) -> dict[str, object]:
            assert path == "/gateway/materialize_role"
            json.dumps(payload)
            assert "health_store" not in payload
            assert isinstance(payload["role"], dict)
            assert isinstance(payload["credentials"], dict)
            return RoleEntry(
                fallback_chain=[RoleRouteEntry(route_id="openai:gpt-5")],
                materialization_report={
                    "entries": [{"route_id": "openai:gpt-5", "role_fit": "using"}],
                    "warnings": [],
                    "skipped_provider_details": [],
                },
            ).model_dump(mode="json")

    credentials = LLMCredentialsFile(
        provider_endpoints={
            "openai": ProviderEndpoint(
                endpoint_id="openai",
                display_name="OpenAI",
                protocol="openai_compatible",
                base_url="https://api.openai.example/v1",
                api_key=SecretStr("secret"),
                status="verified",
            )
        }
    )

    materialized = GatewayAdapter(transport="http_loopback", http_transport=FakeHttpTransport()).materialize_role(
        {
            "role": RoleEntry(),
            "credentials": credentials,
            "health_store": object(),
        }
    )

    assert isinstance(materialized, RoleEntry)
    assert materialized.fallback_chain[0].route_id == "openai:gpt-5"


def test_gateway_adapter_http_loopback_materialize_model_bundle_sends_json_dto_payload_and_validates_response() -> None:
    from app.core.adapters.gateway import GatewayAdapter
    from app.models.llm_config import LLMCredentialsFile, ModelBundle, ProviderEndpoint, RoleRouteEntry

    class FakeHttpTransport:
        def post(self, path: str, payload: dict[str, object]) -> dict[str, object]:
            assert path == "/gateway/materialize_model_bundle"
            json.dumps(payload)
            assert "health_store" not in payload
            assert isinstance(payload["bundle"], dict)
            assert isinstance(payload["credentials"], dict)
            return ModelBundle(
                model_profile_id="bundle",
                display_name="Bundle",
                canonical_id="gpt-5",
                fallback_chain=[RoleRouteEntry(route_id="openai:gpt-5")],
            ).model_dump(mode="json")

    credentials = LLMCredentialsFile(
        provider_endpoints={
            "openai": ProviderEndpoint(
                endpoint_id="openai",
                display_name="OpenAI",
                protocol="openai_compatible",
                base_url="https://api.openai.example/v1",
                api_key=SecretStr("secret"),
                status="verified",
            )
        }
    )

    materialized = GatewayAdapter(
        transport="http_loopback",
        http_transport=FakeHttpTransport(),
    ).materialize_model_bundle(
        {
            "bundle": ModelBundle(model_profile_id="bundle", display_name="Bundle", canonical_id="gpt-5"),
            "credentials": credentials,
            "health_store": object(),
        }
    )

    assert isinstance(materialized, ModelBundle)
    assert materialized.fallback_chain[0].route_id == "openai:gpt-5"


def test_gateway_adapter_http_loopback_project_route_state_sends_json_dto_payload_and_validates_response() -> None:
    from app.core.adapters.gateway import GatewayAdapter, ProviderModelStateProjection
    from app.models.llm_config import ProviderEndpoint, ProviderRoute

    now = datetime.now(UTC)

    class FakeHttpTransport:
        def post(self, path: str, payload: dict[str, object]) -> dict[str, object]:
            assert path == "/gateway/project_route_state"
            json.dumps(payload)
            assert isinstance(payload["endpoint"], dict)
            assert isinstance(payload["route"], dict)
            assert payload["now"] == now.isoformat()
            return {"ui_state": "ready", "reason_code": None, "retry_at": None, "ui_detail": None}

    projection = GatewayAdapter(
        transport="http_loopback",
        http_transport=FakeHttpTransport(),
    ).project_route_state(
        {
            "endpoint": ProviderEndpoint(
                endpoint_id="openai",
                display_name="OpenAI",
                protocol="openai_compatible",
                base_url="https://api.openai.example/v1",
                api_key=SecretStr("secret"),
                status="verified",
            ),
            "route": ProviderRoute(
                route_id="openai:gpt-5",
                endpoint_id="openai",
                route_slug="gpt-5",
                provider_model_id="gpt-5",
                canonical_id="gpt-5",
                status="verified",
            ),
            "circuits": [
                SimpleNamespace(
                    scope="route",
                    scope_id="openai:gpt-5",
                    retry_at=now + timedelta(seconds=60),
                    reason_code="rate_limited",
                    message="cooling",
                )
            ],
            "now": now,
        }
    )

    assert isinstance(projection, ProviderModelStateProjection)
    assert projection.ui_state == "ready"


class _Circuit:
    def __init__(self, retry_at: datetime) -> None:
        self.scope = "route"
        self.scope_id = "openai:gpt-5"
        self.retry_at = retry_at
        self.reason_code = "rate_limited"
        self.message = "rate limited"


def test_gateway_adapter_keeps_cooling_down_state_before_ready() -> None:
    from app.core.adapters.gateway import GatewayAdapter
    from app.models.llm_config import ProviderEndpoint, ProviderRoute

    endpoint = ProviderEndpoint(
        endpoint_id="openai",
        display_name="OpenAI",
        protocol="openai_compatible",
        base_url="https://api.openai.example/v1",
        api_key=SecretStr("secret"),
        status="verified",
    )
    route = ProviderRoute(
        route_id="openai:gpt-5",
        endpoint_id="openai",
        route_slug="gpt-5",
        provider_model_id="gpt-5",
        canonical_id="gpt-5",
        status="verified",
    )
    now = datetime.now(UTC)

    projection = GatewayAdapter(transport="in_process").project_route_state(
        {
            "endpoint": endpoint,
            "route": route,
            "circuits": [_Circuit(now + timedelta(seconds=30))],
            "now": now,
        }
    )

    assert projection.ui_state == "cooling_down"
    assert projection.reason_code == "rate_limited"


def test_gateway_adapter_projects_probe_evidence_as_historical_ready_without_metadata() -> None:
    from app.core.adapters.gateway import GatewayAdapter
    from app.models.llm_config import ProviderEndpoint, ProviderRoute
    from graph_agent_gateway.registry.schema import EvidenceRecord

    endpoint = ProviderEndpoint(
        endpoint_id="openai",
        display_name="OpenAI",
        protocol="openai_compatible",
        base_url="https://api.openai.example/v1",
        api_key=SecretStr("secret"),
        status="verified",
    )
    route = ProviderRoute(
        route_id="openai:gpt-5",
        endpoint_id="openai",
        route_slug="gpt-5",
        provider_model_id="gpt-5",
        canonical_id="gpt-5",
        status="unverified_manual",
        metadata={},
    )

    projection = GatewayAdapter(transport="in_process").project_route_state(
        {
            "endpoint": endpoint,
            "route": route,
            "circuits": [],
            "now": datetime.now(UTC),
            "evidence_records": [
                EvidenceRecord(
                    evidence_id="probe-openai-gpt5",
                    evidence_type="probe",
                    trust_state="probe-verified",
                    route_id="openai:gpt-5",
                    endpoint_id="openai",
                    model_id="gpt-5",
                    provider_model_id="gpt-5",
                    probe_status="ok",
                )
            ],
        }
    )

    assert projection.ui_state == "historical_ready"
