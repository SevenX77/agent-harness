from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient

from app.models.llm_config import LLMCredentialsFile, RolesData
from app.routers import llm as llm_router
from app.services.llm_credentials import save_credentials
from app.services.llm_roles import save_roles_file
from graph_agent_gateway.registry.schema import (
    ModelProfile,
    ProviderEndpoint,
    ProviderRoute,
    RoleEntry,
    RoleRouteEntry,
)


def _seed(
    tmp_path: Path,
    monkeypatch,
) -> tuple[Path, Path]:
    credentials_path = tmp_path / ".studio" / "llm_credentials.json"
    roles_path = tmp_path / "llm_roles.yaml"
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setattr(llm_router, "ROLES_PATH", roles_path)
    save_credentials(
        LLMCredentialsFile(
            provider_endpoints={
                "openai-direct": ProviderEndpoint(
                    endpoint_id="openai-direct",
                    display_name="OpenAI",
                    protocol="openai_compatible",
                    base_url="https://api.openai.example/v1",
                    api_key="secret",
                )
            },
            provider_routes={
                "openai-direct:gpt-5": ProviderRoute(
                    route_id="openai-direct:gpt-5",
                    endpoint_id="openai-direct",
                    route_slug="gpt-5",
                    provider_model_id="gpt-5",
                    canonical_id="gpt-5",
                    display_name="GPT-5",
                    status="verified",
                )
            },
        ),
        credentials_path,
    )
    save_roles_file(
        roles_path,
        RolesData(
            model_profiles={
                "GPT5": ModelProfile(
                    model_profile_id="GPT5",
                    display_name="GPT-5",
                    canonical_id="gpt-5",
                    fallback_chain=[RoleRouteEntry(route_id="openai-direct:gpt-5")],
                )
            },
            roles={
                "graph_agent": RoleEntry(
                    fallback_chain=[RoleRouteEntry(route_id="openai-direct:gpt-5")]
                )
            },
        ),
        known_route_ids={"openai-direct:gpt-5"},
    )
    return credentials_path, roles_path


def test_registry_read_and_endpoint_upsert_redacts_secret(
    client: TestClient,
    tmp_path: Path,
    monkeypatch,
) -> None:
    _seed(tmp_path, monkeypatch)

    response = client.get("/api/llm/registry")

    assert response.status_code == 200
    body = response.json()
    assert body["provider_endpoints"]["openai-direct"]["api_key"] == "**********"
    assert body["canonical_groups"][0]["canonical_id"] == "gpt-5"

    put_response = client.put(
        "/api/llm/registry/endpoints",
        json={
            "provider_endpoints": {
                "anthropic-official": {
                    "endpoint_id": "anthropic-official",
                    "display_name": "Anthropic",
                    "protocol": "anthropic_compatible",
                    "base_url": "https://api.anthropic.com",
                    "api_key": "anthropic-secret",
                }
            }
        },
    )

    assert put_response.status_code == 200
    assert set(put_response.json()["provider_endpoints"]) == {
        "openai-direct",
        "anthropic-official",
    }
    raw = json.loads((tmp_path / ".studio" / "llm_credentials.json").read_text())
    assert raw["provider_endpoints"]["anthropic-official"]["api_key"] == "anthropic-secret"


def test_route_and_endpoint_delete_conflicts(
    client: TestClient,
    tmp_path: Path,
    monkeypatch,
) -> None:
    _seed(tmp_path, monkeypatch)

    route_response = client.delete("/api/llm/routes/openai-direct:gpt-5")
    endpoint_response = client.delete("/api/llm/registry/endpoints/openai-direct")

    assert route_response.status_code == 409
    assert route_response.json()["error_code"] == "route_in_use"
    assert route_response.json()["details"]["roles"] == ["graph_agent.fallback_chain[0]"]
    assert endpoint_response.status_code == 409
    assert endpoint_response.json()["error_code"] == "endpoint_in_use"


def test_route_metadata_probe_and_profile_apply_conflict(
    client: TestClient,
    tmp_path: Path,
    monkeypatch,
) -> None:
    _seed(tmp_path, monkeypatch)

    probe_response = client.post(
        "/api/llm/routes/openai-direct:gpt-5/probe",
        json={"capabilities": ["tool_calling"]},
    )
    assert probe_response.status_code == 200
    assert probe_response.json()["capabilities"]["tool_protocol"]["source"] == "probed_verified"

    update_response = client.put(
        "/api/llm/routes/openai-direct:gpt-5",
        json={
            "display_name": "GPT-5 Updated",
            "canonical_id": "gpt-5",
            "status": "verified",
            "capabilities": {},
            "metadata": {"provider_brand": "openai"},
        },
    )
    assert update_response.status_code == 200
    assert update_response.json()["route_id"] == "openai-direct:gpt-5"
    assert update_response.json()["display_name"] == "GPT-5 Updated"

    client.put(
        "/api/llm/roles/graph_agent",
        json={
            "system_prompt_prefix": "",
            "source_profile_id": "GPT5",
            "source_profile_snapshot": {"route_ids": ["some-other:route"]},
            "fallback_chain": [{"route_id": "openai-direct:gpt-5"}],
            "lint_requirements": {},
        },
    )
    conflict = client.post(
        "/api/llm/roles/graph_agent/apply-profile",
        json={"model_profile_id": "GPT5"},
    )

    assert conflict.status_code == 409
    assert conflict.json()["error_code"] == "profile_apply_conflict"
    assert conflict.json()["details"]["role_name"] == "graph_agent"


def test_old_provider_endpoints_are_removed(client: TestClient) -> None:
    assert client.post("/api/llm/providers/test", json={}).status_code == 404
    assert client.post("/api/llm/providers/test-models", json={}).status_code == 404
    assert client.get("/api/llm/providers/notable-models").status_code == 404
