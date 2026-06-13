from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

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

    assert "GatewayAdapter" in source
    assert "ModelResolver(" not in source
    assert "from app.services.llm_role_materializer import" not in source
    assert "from app.services.llm_state_projection import" not in source
    assert "project_provider_model_state(" not in source


def test_role_materializer_delegates_provider_projection_to_gateway_adapter() -> None:
    source = (BACKEND_ROOT / "app" / "services" / "llm_role_materializer.py").read_text(encoding="utf-8")

    assert "GatewayAdapter" in source
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


def test_gateway_adapter_in_process_resolves_endpoint_credential() -> None:
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
            "now": datetime.now(UTC),
            "ttl_seconds": 60,
        }
    )

    assert resolved["credential_ref"] == "endpoint:openai"
    assert resolved["secret_handle"] == "secret"
    assert resolved["expires_at"] > datetime.now(UTC).isoformat()


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
