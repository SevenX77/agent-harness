from __future__ import annotations

from pathlib import Path

from app.models.llm_config import LLMCredentialsFile, RolesData
from app.services import copilot
from app.services.llm_credentials import save_credentials
from app.services.llm_roles import save_roles_file
from graph_agent_gateway.registry.schema import (
    ProviderEndpoint,
    ProviderRoute,
    RoleEntry,
    RoleRouteEntry,
)


def test_copilot_route_resolution_uses_v4_registry_route_ids(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    repo_root = tmp_path / "repo"
    roles_path = repo_root / "config" / "llm_roles.yaml"
    monkeypatch.setattr(copilot.config, "REPO_ROOT", repo_root)
    save_credentials(
        LLMCredentialsFile(
            provider_endpoints={
                "anthropic-official": ProviderEndpoint(
                    endpoint_id="anthropic-official",
                    display_name="Anthropic",
                    protocol="anthropic_compatible",
                    base_url="https://api.anthropic.example",
                    api_key="secret",
                )
            },
            provider_routes={
                "anthropic-official:claude-sonnet": ProviderRoute(
                    route_id="anthropic-official:claude-sonnet",
                    endpoint_id="anthropic-official",
                    route_slug="claude-sonnet",
                    provider_model_id="claude-sonnet",
                    canonical_id="claude-sonnet",
                    display_name="Claude Sonnet",
                    status="verified",
                )
            },
        )
    )
    save_roles_file(
        roles_path,
        RolesData(
            roles={
                "copilot_chat": RoleEntry(
                    fallback_chain=[
                        RoleRouteEntry(route_id="anthropic-official:claude-sonnet")
                    ],
                )
            }
        ),
        known_route_ids={"anthropic-official:claude-sonnet"},
    )

    route = copilot._resolve_copilot_route("anthropic-official:claude-sonnet")

    assert route.endpoint_id == "anthropic-official"
    assert route.provider_model_id == "claude-sonnet"
    assert route.api_key.get_secret_value() == "secret"
