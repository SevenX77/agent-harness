from __future__ import annotations

import json
from pathlib import Path

from app.core import config
from app.models.llm_config import LLMCredentialsFile, RolesData
from app.routers import llm as llm_router
from app.services.copilot_test import PingResult, _Unauthorized
from app.services.llm_credentials import credentials_path, save_credentials
from app.services.llm_roles import roles_path as active_roles_path
from app.services.llm_roles import save_roles_file
from fastapi.testclient import TestClient
from graph_agent_gateway.registry.schema import (
    CapabilityValue,
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
    settings_dir = tmp_path / "settings"
    monkeypatch.setattr(config, "APP_SETTINGS_DIR", settings_dir)
    active_credentials_path = settings_dir / "llm" / "llm_credentials.json"
    roles_path = settings_dir / "llm" / "llm_roles.yaml"
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
        active_credentials_path,
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
    return active_credentials_path, roles_path


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
    raw = json.loads(credentials_path().read_text())
    assert raw["provider_endpoints"]["anthropic-official"]["api_key"] == "anthropic-secret"


def test_registry_includes_runtime_setting_metadata_for_frontend_controls(
    client: TestClient,
    tmp_path: Path,
    monkeypatch,
) -> None:
    _seed(tmp_path, monkeypatch)
    credentials = LLMCredentialsFile(
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
                capabilities={
                    "temperature": CapabilityValue(
                        value={"supported": True, "min": 0, "max": 2, "default": 1},
                        source="provider_doc",
                    ),
                    "seed": CapabilityValue(
                        value={"supported": False},
                        source="provider_doc",
                    ),
                    "reasoning_effort": CapabilityValue(
                        value={"supported": True, "values": ["low", "medium", "high"]},
                        source="provider_doc",
                    ),
                    "max_output_tokens": CapabilityValue(
                        value={"supported": True, "min": 1, "max": 8192, "default": 2048},
                        source="provider_doc",
                    ),
                },
            )
        },
    )
    save_credentials(credentials, credentials_path())
    save_roles_file(
        active_roles_path(),
        RolesData(
            roles={
                "graph_agent": RoleEntry(
                    fallback_chain=[
                        RoleRouteEntry(
                            route_id="openai-direct:gpt-5",
                            runtime_settings={
                                "temperature": 0.2,
                                "reasoning": {"effort": "medium"},
                            },
                        )
                    ]
                )
            }
        ),
        known_route_ids={"openai-direct:gpt-5"},
    )

    response = client.get("/api/llm/registry")

    assert response.status_code == 200
    body = response.json()
    route_settings = body["route_runtime_settings"]["openai-direct:gpt-5"]
    assert route_settings["temperature"] == {
        "key": "temperature",
        "value_type": "number",
        "supported": True,
        "min": 0.0,
        "max": 2.0,
        "default": 1,
        "allowed_values": [],
        "source": "provider_doc",
        "message": None,
    }
    assert route_settings["seed"]["supported"] is False
    assert route_settings["reasoning.effort"]["allowed_values"] == ["low", "medium", "high"]
    effective = body["role_effective_runtime_settings"]["graph_agent"]["openai-direct:gpt-5"]
    assert effective["temperature"] == {
        "value": 0.2,
        "source": "route_setting",
        "message": None,
    }
    assert effective["max_output_tokens"] == {
        "value": 2048,
        "source": "route_capability_default",
        "message": None,
    }
    assert effective["reasoning.effort"] == {
        "value": "medium",
        "source": "route_setting",
        "message": None,
    }


def test_registry_endpoint_secret_reveal_is_v4_scoped(
    client: TestClient,
    tmp_path: Path,
    monkeypatch,
) -> None:
    _seed(tmp_path, monkeypatch)

    registry_response = client.get("/api/llm/registry")
    secret_response = client.get("/api/llm/registry/endpoints/openai-direct/secret")
    missing_response = client.get("/api/llm/registry/endpoints/missing/secret")

    assert registry_response.status_code == 200
    assert registry_response.json()["provider_endpoints"]["openai-direct"]["api_key"] == "**********"
    assert secret_response.status_code == 200
    assert secret_response.json() == {"endpoint_id": "openai-direct", "api_key": "secret"}
    assert missing_response.status_code == 404


def test_registry_invalidates_legacy_fake_endpoint_test_status(
    client: TestClient,
    tmp_path: Path,
    monkeypatch,
) -> None:
    _seed(tmp_path, monkeypatch)
    raw = json.loads(credentials_path().read_text())
    raw["provider_endpoints"]["openai-direct"]["status"] = "verified"
    raw["provider_endpoints"]["openai-direct"]["last_test_message"] = "Credential present."
    credentials_path().write_text(json.dumps(raw), encoding="utf-8")

    response = client.get("/api/llm/registry")

    assert response.status_code == 200
    endpoint = response.json()["provider_endpoints"]["openai-direct"]
    assert endpoint["status"] == "unverified_manual"
    assert endpoint["last_test_message"] == "Needs retest after v4 provider probe upgrade."


def test_endpoint_test_uses_real_provider_probe(
    client: TestClient,
    tmp_path: Path,
    monkeypatch,
) -> None:
    _seed(tmp_path, monkeypatch)
    calls: list[tuple[str, str, str]] = []

    async def fake_ping_provider(backend: str, api_key: str, base_url: str) -> PingResult:
        calls.append((backend, api_key, base_url))
        return PingResult(latency_ms=42, model_seen="gpt-5")

    monkeypatch.setattr(llm_router, "_ping_provider", fake_ping_provider)

    response = client.post("/api/llm/endpoints/openai-direct/test")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "verified"
    assert "Connected" in body["last_test_message"]
    assert "gpt-5" in body["last_test_message"]
    assert calls == [("openai", "secret", "https://api.openai.example")]


def test_endpoint_test_rejects_invalid_api_key(
    client: TestClient,
    tmp_path: Path,
    monkeypatch,
) -> None:
    _seed(tmp_path, monkeypatch)

    async def fake_ping_provider(backend: str, api_key: str, base_url: str) -> PingResult:
        raise _Unauthorized("bad key", error_code="invalid_api_key")

    monkeypatch.setattr(llm_router, "_ping_provider", fake_ping_provider)

    response = client.post("/api/llm/endpoints/openai-direct/test")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "failed"
    assert "Invalid API key" in body["last_test_message"]
    assert "invalid_api_key" in body["last_test_message"]


def test_registry_missing_credentials_returns_setup_required_status(
    client: TestClient,
    tmp_path: Path,
    monkeypatch,
) -> None:
    settings_dir = tmp_path / "settings"
    monkeypatch.setattr(config, "APP_SETTINGS_DIR", settings_dir)

    response = client.get("/api/llm/registry")

    assert response.status_code == 200
    body = response.json()
    assert body["setup_required"] is True
    assert body["provider_endpoints"] == {}
    assert body["provider_routes"] == {}


def test_registry_legacy_credentials_returns_bootstrap_schema_error(
    client: TestClient,
    tmp_path: Path,
    monkeypatch,
) -> None:
    settings_dir = tmp_path / "settings"
    monkeypatch.setattr(config, "APP_SETTINGS_DIR", settings_dir)
    active_credentials_path = credentials_path()
    active_credentials_path.parent.mkdir(parents=True)
    active_credentials_path.write_text(
        json.dumps({"schema_version": 3, "providers": [{"id": "old"}]}),
        encoding="utf-8",
    )

    response = client.get("/api/llm/registry")

    assert response.status_code == 422
    body = response.json()
    assert body["error_code"] == "LLM_CREDENTIALS_SCHEMA"
    assert "schema_version 4" in body["message"]
    assert body["details"]["docs_path"] == "docs/development/CREDENTIALS_V4_BOOTSTRAP.md"


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


def test_route_probe_accepts_runtime_setting_capability_metadata(
    client: TestClient,
    tmp_path: Path,
    monkeypatch,
) -> None:
    _seed(tmp_path, monkeypatch)

    response = client.post(
        "/api/llm/routes/openai-direct:gpt-5/probe",
        json={
            "runtime_settings": {
                "temperature": {"supported": True, "min": 0, "max": 2, "default": 1},
                "seed": {"supported": False},
                "max_output_tokens": {"supported": True, "min": 1, "max": 8192, "default": 2048},
            }
        },
    )

    assert response.status_code == 200
    capabilities = response.json()["capabilities"]
    assert capabilities["temperature"]["source"] == "probed_verified"
    assert capabilities["temperature"]["value"] == {
        "supported": True,
        "min": 0,
        "max": 2,
        "default": 1,
    }
    assert capabilities["seed"]["value"] == {"supported": False}
    assert capabilities["max_output_tokens"]["value"] == {
        "supported": True,
        "min": 1,
        "max": 8192,
        "default": 2048,
    }


def test_apply_model_profile_marks_runtime_settings_as_profile_default(
    client: TestClient,
    tmp_path: Path,
    monkeypatch,
) -> None:
    _seed(tmp_path, monkeypatch)

    profiles_response = client.put(
        "/api/llm/model-profiles",
        json={
            "GPT5": {
                "model_profile_id": "GPT5",
                "display_name": "GPT-5",
                "canonical_id": "gpt-5",
                "fallback_chain": [
                    {
                        "route_id": "openai-direct:gpt-5",
                        "runtime_settings": {
                            "temperature": 0.2,
                            "max_output_tokens": 1200,
                        },
                    }
                ],
                "lint_requirements": {},
            }
        },
    )
    assert profiles_response.status_code == 200

    apply_response = client.post(
        "/api/llm/roles/graph_agent/apply-profile",
        json={"model_profile_id": "GPT5"},
    )

    assert apply_response.status_code == 200
    entry = apply_response.json()["fallback_chain"][0]
    assert entry["route_id"] == "openai-direct:gpt-5"
    assert entry["runtime_settings_source"] == "profile_default"
    assert entry["runtime_settings"]["temperature"] == 0.2
    assert entry["runtime_settings"]["max_output_tokens"] == 1200


def test_old_provider_endpoints_are_removed(client: TestClient) -> None:
    assert client.post("/api/llm/providers/test", json={}).status_code == 404
    assert client.post("/api/llm/providers/test-models", json={}).status_code == 404
    assert client.get("/api/llm/providers/notable-models").status_code == 404
