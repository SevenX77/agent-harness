from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx
from app.core import config
from app.models.llm_config import (
    CapabilityValue,
    LLMCredentialsFile,
    ModelProfile,
    ProviderEndpoint,
    ProviderRoute,
    RoleEntry,
    RoleRouteEntry,
    RolesData,
)
from app.routers import llm as llm_router
from app.services import copilot_test
from app.services.copilot_test import ModelProbeResult, PingResult, _Unauthorized
from app.services.llm_credentials import credentials_path, save_credentials
from app.services.llm_roles import roles_path as active_roles_path
from app.services.llm_roles import save_roles_file
from fastapi.testclient import TestClient
from graph_agent_gateway.registry.schema import VerifiedProfile


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


def _health_store_path() -> Path:
    return Path(config.APP_SETTINGS_DIR) / "llm" / "llm_health.sqlite"


def _open_runtime_circuit(
    *,
    route_id: str = "openai-direct:gpt-5",
    endpoint_id: str = "openai-direct",
    rate_limit_bucket: str = "openai-direct",
    retry_at: datetime,
    reason_code: str = "timeout",
    message: str = "probe timed out",
):
    from app.services.llm_health_store import RuntimeCircuit, SqliteLlmHealthStore

    store = SqliteLlmHealthStore(_health_store_path())
    store.open_circuit(
        RuntimeCircuit(
            scope="route",
            scope_id=route_id,
            opened_at=retry_at - timedelta(seconds=60),
            retry_at=retry_at,
            ttl_seconds=60,
            reason_code=reason_code,
            failure_count=1,
            message=message,
        )
    )
    return store


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
                status="verified",
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


def test_registry_returns_model_groups_with_provider_ui_state_projection(
    client: TestClient,
    tmp_path: Path,
    monkeypatch,
) -> None:
    settings_dir = tmp_path / "settings"
    monkeypatch.setattr(config, "APP_SETTINGS_DIR", settings_dir)
    active_credentials_path = settings_dir / "llm" / "llm_credentials.json"
    roles_path = settings_dir / "llm" / "llm_roles.yaml"

    endpoints = {
        "ready-provider": ProviderEndpoint(
            endpoint_id="ready-provider",
            display_name="Ready Provider",
            protocol="openai_compatible",
            base_url="https://ready.example/v1",
            api_key="secret",
            status="verified",
        ),
        "untested-provider": ProviderEndpoint(
            endpoint_id="untested-provider",
            display_name="Untested Provider",
            protocol="openai_compatible",
            base_url="https://untested.example/v1",
            api_key="secret",
            status="unverified_manual",
        ),
        "missing-key-provider": ProviderEndpoint(
            endpoint_id="missing-key-provider",
            display_name="Missing Key Provider",
            protocol="openai_compatible",
            base_url="https://missing-key.example/v1",
            api_key=None,
            status="unverified_manual",
        ),
        "disabled-provider": ProviderEndpoint(
            endpoint_id="disabled-provider",
            display_name="Disabled Provider",
            protocol="openai_compatible",
            base_url="https://disabled.example/v1",
            api_key="secret",
            status="disabled",
        ),
        "failed-provider": ProviderEndpoint(
            endpoint_id="failed-provider",
            display_name="Failed Provider",
            protocol="openai_compatible",
            base_url="https://failed.example/v1",
            api_key="secret",
            status="verified",
        ),
    }
    routes = {
        "ready-provider:gpt-5": ProviderRoute(
            route_id="ready-provider:gpt-5",
            endpoint_id="ready-provider",
            route_slug="gpt-5",
            provider_model_id="gpt-5",
            canonical_id="gpt-5",
            display_name="GPT-5",
            status="verified",
        ),
        "untested-provider:gpt-5": ProviderRoute(
            route_id="untested-provider:gpt-5",
            endpoint_id="untested-provider",
            route_slug="gpt-5",
            provider_model_id="gpt-5",
            canonical_id="gpt-5",
            display_name="GPT-5",
            status="unverified_manual",
        ),
        "missing-key-provider:gpt-5": ProviderRoute(
            route_id="missing-key-provider:gpt-5",
            endpoint_id="missing-key-provider",
            route_slug="gpt-5",
            provider_model_id="gpt-5",
            canonical_id="gpt-5",
            display_name="GPT-5",
            status="verified",
        ),
        "disabled-provider:gpt-5": ProviderRoute(
            route_id="disabled-provider:gpt-5",
            endpoint_id="disabled-provider",
            route_slug="gpt-5",
            provider_model_id="gpt-5",
            canonical_id="gpt-5",
            display_name="GPT-5",
            status="verified",
        ),
        "failed-provider:gpt-5": ProviderRoute(
            route_id="failed-provider:gpt-5",
            endpoint_id="failed-provider",
            route_slug="gpt-5",
            provider_model_id="gpt-5",
            canonical_id="gpt-5",
            display_name="GPT-5",
            status="failed",
        ),
    }
    save_credentials(
        LLMCredentialsFile(provider_endpoints=endpoints, provider_routes=routes),
        active_credentials_path,
    )
    save_roles_file(roles_path, RolesData(), known_route_ids=set(routes))

    response = client.get("/api/llm/registry")

    assert response.status_code == 200
    model_group = response.json()["model_groups"][0]
    assert model_group["canonical_id"] == "gpt-5"
    assert model_group["display_name"] == "GPT 5"
    assert model_group["status_summary"] == {
        "ready": 1,
        "untested": 1,
        "cooling_down": 0,
        "needs_setup": 2,
        "off": 1,
    }
    provider_models = {option["route_id"]: option for option in model_group["provider_models"]}
    assert provider_models["ready-provider:gpt-5"]["ui_state"] == "ready"
    assert provider_models["untested-provider:gpt-5"]["ui_state"] == "untested"
    assert provider_models["missing-key-provider:gpt-5"]["ui_state"] == "needs_setup"
    assert provider_models["failed-provider:gpt-5"]["ui_state"] == "needs_setup"
    assert provider_models["disabled-provider:gpt-5"]["ui_state"] == "off"
    assert provider_models["ready-provider:gpt-5"]["endpoint_id"] == "ready-provider"
    assert provider_models["ready-provider:gpt-5"]["provider_kind"] == "third_party"
    assert provider_models["ready-provider:gpt-5"]["capability_state"] == "unknown"


def test_registry_merges_model_groups_by_projected_display_name(
    client: TestClient,
    tmp_path: Path,
    monkeypatch,
) -> None:
    settings_dir = tmp_path / "settings"
    monkeypatch.setattr(config, "APP_SETTINGS_DIR", settings_dir)
    active_credentials_path = settings_dir / "llm" / "llm_credentials.json"
    roles_path = settings_dir / "llm" / "llm_roles.yaml"

    endpoints = {
        "anthropic-official": ProviderEndpoint(
            endpoint_id="anthropic-official",
            display_name="Anthropic Official",
            protocol="anthropic_compatible",
            base_url="https://api.anthropic.com",
            api_key="secret",
            status="verified",
            provider_kind="official",
        ),
        "openrouter": ProviderEndpoint(
            endpoint_id="openrouter",
            display_name="OpenRouter",
            protocol="openai_compatible",
            base_url="https://openrouter.ai/api/v1",
            api_key="secret",
            status="verified",
            provider_kind="third_party",
        ),
    }
    routes = {
        "anthropic-official:claude-opus-4-7": ProviderRoute(
            route_id="anthropic-official:claude-opus-4-7",
            endpoint_id="anthropic-official",
            route_slug="claude-opus-4-7",
            provider_model_id="claude-opus-4-7",
            canonical_id="claude-opus-4-7",
            display_name="Claude Opus 4.7",
            status="verified",
        ),
        "openrouter:anthropic.claude-opus-4-7": ProviderRoute(
            route_id="openrouter:anthropic.claude-opus-4-7",
            endpoint_id="openrouter",
            route_slug="anthropic.claude-opus-4-7",
            provider_model_id="anthropic/claude-opus-4-7",
            canonical_id="anthropic.claude-opus-4-7",
            display_name="Claude Opus 4.7",
            status="verified",
        ),
    }
    save_credentials(
        LLMCredentialsFile(provider_endpoints=endpoints, provider_routes=routes),
        active_credentials_path,
    )
    save_roles_file(roles_path, RolesData(), known_route_ids=set(routes))

    response = client.get("/api/llm/registry")

    assert response.status_code == 200
    matching_groups = [
        group
        for group in response.json()["model_groups"]
        if group["display_name"] == "Claude Opus 4.7"
    ]
    assert len(matching_groups) == 1
    model_group = matching_groups[0]
    assert model_group["canonical_id"] == "claude-opus-4-7"
    assert model_group["section_label"] == "anthropic"
    assert {
        option["route_id"]
        for option in model_group["provider_models"]
    } == set(routes)


def test_registry_merges_same_display_name_across_provider_sections(
    client: TestClient,
    tmp_path: Path,
    monkeypatch,
) -> None:
    settings_dir = tmp_path / "settings"
    monkeypatch.setattr(config, "APP_SETTINGS_DIR", settings_dir)
    active_credentials_path = settings_dir / "llm" / "llm_credentials.json"
    roles_path = settings_dir / "llm" / "llm_roles.yaml"

    endpoints = {
        "qiniu-anthropic": ProviderEndpoint(
            endpoint_id="qiniu-anthropic",
            display_name="Qiniu Anthropic Proxy",
            protocol="anthropic_compatible",
            base_url="https://qiniu.example/anthropic",
            api_key="secret",
            status="verified",
            provider_kind="custom",
        ),
        "openrouter": ProviderEndpoint(
            endpoint_id="openrouter",
            display_name="OpenRouter",
            protocol="openai_compatible",
            base_url="https://openrouter.ai/api/v1",
            api_key="secret",
            status="verified",
            provider_kind="third_party",
        ),
    }
    routes = {
        "qiniu-anthropic:deepseek-r1": ProviderRoute(
            route_id="qiniu-anthropic:deepseek-r1",
            endpoint_id="qiniu-anthropic",
            route_slug="deepseek-r1",
            provider_model_id="deepseek-r1",
            canonical_id="deepseek-r1",
            display_name="DeepSeek R1",
            status="verified",
        ),
        "openrouter:deepseek.deepseek-r1": ProviderRoute(
            route_id="openrouter:deepseek.deepseek-r1",
            endpoint_id="openrouter",
            route_slug="deepseek.deepseek-r1",
            provider_model_id="deepseek/deepseek-r1",
            canonical_id="deepseek.deepseek-r1",
            display_name="DeepSeek R1",
            status="verified",
        ),
    }
    save_credentials(
        LLMCredentialsFile(provider_endpoints=endpoints, provider_routes=routes),
        active_credentials_path,
    )
    save_roles_file(roles_path, RolesData(), known_route_ids=set(routes))

    response = client.get("/api/llm/registry")

    assert response.status_code == 200
    matching_groups = [
        group
        for group in response.json()["model_groups"]
        if group["display_name"] == "DeepSeek R1"
    ]
    assert len(matching_groups) == 1
    assert {
        option["route_id"]
        for option in matching_groups[0]["provider_models"]
    } == set(routes)


def test_registry_returns_cooling_down_provider_when_route_circuit_is_active(
    client: TestClient,
    tmp_path: Path,
    monkeypatch,
) -> None:
    _seed(tmp_path, monkeypatch)
    retry_at = datetime.now(UTC) + timedelta(seconds=60)
    _open_runtime_circuit(
        route_id="openai-direct:gpt-5",
        retry_at=retry_at,
        reason_code="rate_limited",
        message="provider returned 429",
    )

    response = client.get("/api/llm/registry")

    assert response.status_code == 200
    model_group = response.json()["model_groups"][0]
    assert model_group["status_summary"]["cooling_down"] == 1
    provider_model = model_group["provider_models"][0]
    assert provider_model["route_id"] == "openai-direct:gpt-5"
    assert provider_model["ui_state"] == "cooling_down"
    assert provider_model["reason_code"] == "rate_limited"
    assert provider_model["retry_at"] == retry_at.isoformat()


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
        return PingResult(latency_ms=42, model_ids=("gpt-5", "gpt-5-mini"))

    async def fake_probe_model(
        backend: copilot_test.CopilotProvider,
        api_key: str,
        base_url: str,
        model_id: str,
    ) -> ModelProbeResult:
        raise AssertionError(
            f"endpoint test should only call /models, not probe {backend} {base_url} {model_id}"
        )

    monkeypatch.setattr(llm_router, "_ping_provider", fake_ping_provider)
    monkeypatch.setattr(llm_router, "_probe_model", fake_probe_model)

    response = client.post("/api/llm/endpoints/openai-direct/test")

    assert response.status_code == 200
    body = response.json()
    assert body["tested_endpoint_id"] == "openai-direct"
    assert body["discovered_model_count"] == 2
    endpoint = body["registry"]["provider_endpoints"]["openai-direct"]
    assert endpoint["status"] == "unverified_manual"
    assert "Connected" in endpoint["last_test_message"]
    assert "gpt-5" in endpoint["last_test_message"]
    routes = body["registry"]["provider_routes"]
    assert routes["openai-direct:gpt-5"]["status"] == "verified"
    assert routes["openai-direct:gpt-5"]["display_name"] == "GPT-5"
    assert routes["openai-direct:gpt-5-mini"]["provider_model_id"] == "gpt-5-mini"
    assert routes["openai-direct:gpt-5-mini"]["route_slug"] == "gpt-5-mini"
    assert routes["openai-direct:gpt-5-mini"]["status"] == "unverified_manual"
    assert calls == [("openai", "secret", "https://api.openai.example/v1")]


def test_endpoint_test_does_not_require_one_token_model_probe_after_models_list(
    client: TestClient,
    tmp_path: Path,
    monkeypatch,
) -> None:
    settings_dir = tmp_path / "settings"
    monkeypatch.setattr(config, "APP_SETTINGS_DIR", settings_dir)
    save_credentials(
        LLMCredentialsFile(
            provider_endpoints={
                "qiniu": ProviderEndpoint(
                    endpoint_id="qiniu",
                    display_name="Qiniu",
                    protocol="openai_compatible",
                    base_url="https://anthropic.qnaigc.com/v1",
                    api_key="secret",
                )
            },
        ),
        credentials_path(),
    )
    model_list_calls: list[tuple[str, str, str]] = []
    model_probe_calls: list[tuple[str, str, str, str]] = []

    async def fake_ping_provider(backend: str, api_key: str, base_url: str) -> PingResult:
        model_list_calls.append((backend, api_key, base_url))
        return PingResult(latency_ms=42, model_ids=("claude-qiniu",))

    async def fake_probe_model(
        backend: copilot_test.CopilotProvider,
        api_key: str,
        base_url: str,
        model_id: str,
    ) -> ModelProbeResult:
        model_probe_calls.append((backend, api_key, base_url, model_id))
        return ModelProbeResult(
            model_id=model_id,
            status="invalid_model",
            message="generation failed for endpoint protocol/base_url combination",
        )

    monkeypatch.setattr(llm_router, "_ping_provider", fake_ping_provider)
    monkeypatch.setattr(llm_router, "_probe_model", fake_probe_model)

    response = client.post("/api/llm/endpoints/qiniu/test")

    assert response.status_code == 200
    body = response.json()
    endpoint = body["registry"]["provider_endpoints"]["qiniu"]
    assert model_list_calls == [("openai", "secret", "https://anthropic.qnaigc.com/v1")]
    assert model_probe_calls == []
    assert endpoint["status"] == "unverified_manual"
    assert "Connected" in endpoint["last_test_message"]
    assert body["discovered_model_count"] == 1
    routes = body["registry"]["provider_routes"]
    assert routes["qiniu:claude-qiniu"]["status"] == "unverified_manual"


def test_endpoint_test_uses_endpoint_protocol_and_base_url_for_probe(
    client: TestClient,
    tmp_path: Path,
    monkeypatch,
) -> None:
    settings_dir = tmp_path / "settings"
    monkeypatch.setattr(config, "APP_SETTINGS_DIR", settings_dir)
    save_credentials(
        LLMCredentialsFile(
            provider_endpoints={
                "qiniu": ProviderEndpoint(
                    endpoint_id="qiniu",
                    display_name="Qiniu",
                    protocol="anthropic_compatible",
                    base_url="https://anthropic.qnaigc.com/v1",
                    api_key="secret",
                )
            },
        ),
        credentials_path(),
    )
    calls: list[tuple[str, str, str]] = []

    async def fake_ping_provider(backend: str, api_key: str, base_url: str) -> PingResult:
        calls.append((backend, api_key, base_url))
        return PingResult(latency_ms=42, model_ids=("claude-qiniu",))

    async def fake_probe_model(
        backend: copilot_test.CopilotProvider,
        api_key: str,
        base_url: str,
        model_id: str,
    ) -> ModelProbeResult:
        return ModelProbeResult(model_id=model_id, status="ok", latency_ms=21)

    monkeypatch.setattr(llm_router, "_ping_provider", fake_ping_provider)
    monkeypatch.setattr(llm_router, "_probe_model", fake_probe_model)

    response = client.post("/api/llm/endpoints/qiniu/test")

    assert response.status_code == 200
    assert calls == [("claude", "secret", "https://anthropic.qnaigc.com/v1")]
    routes = response.json()["registry"]["provider_routes"]
    assert list(routes) == ["qiniu:claude-qiniu"]


def test_endpoint_test_preserves_protocol_version_path_for_provider_probe(
    client: TestClient,
    tmp_path: Path,
    monkeypatch,
) -> None:
    settings_dir = tmp_path / "settings"
    monkeypatch.setattr(config, "APP_SETTINGS_DIR", settings_dir)
    save_credentials(
        LLMCredentialsFile(
            provider_endpoints={
                "qiniu": ProviderEndpoint(
                    endpoint_id="qiniu",
                    display_name="Qiniu",
                    protocol="anthropic_compatible",
                    base_url="https://anthropic.qnaigc.com/v1",
                    api_key="secret",
                )
            },
        ),
        credentials_path(),
    )
    requested_urls: list[str] = []

    async def fake_request_models(
        client: httpx.AsyncClient,
        backend: str,
        api_key: str,
        base_url: str,
    ) -> httpx.Response:
        del client, backend, api_key
        requested_urls.append(base_url)
        return httpx.Response(
            200,
            json={"data": [{"id": "claude-qiniu"}]},
            request=httpx.Request("GET", f"{base_url}/models"),
        )

    async def fake_probe_model(
        backend: copilot_test.CopilotProvider,
        api_key: str,
        base_url: str,
        model_id: str,
    ) -> ModelProbeResult:
        return ModelProbeResult(model_id=model_id, status="ok", latency_ms=21)

    monkeypatch.setattr(copilot_test, "_request_models", fake_request_models)
    monkeypatch.setattr(llm_router, "_probe_model", fake_probe_model)

    response = client.post("/api/llm/endpoints/qiniu/test")

    assert response.status_code == 200
    assert requested_urls == ["https://anthropic.qnaigc.com/v1"]
    assert list(response.json()["registry"]["provider_routes"]) == ["qiniu:claude-qiniu"]


def test_endpoint_test_uses_ark_runtime_for_ark_official(
    client: TestClient,
    tmp_path: Path,
    monkeypatch,
) -> None:
    settings_dir = tmp_path / "settings"
    monkeypatch.setattr(config, "APP_SETTINGS_DIR", settings_dir)
    save_credentials(
        LLMCredentialsFile(
            provider_endpoints={
                "ark-official": ProviderEndpoint(
                    endpoint_id="ark-official",
                    display_name="Ark Official",
                    protocol="ark_runtime",
                    base_url="https://ark.cn-beijing.volces.com/api/v3",
                    api_key="secret",
                )
            },
        ),
        credentials_path(),
    )
    calls: list[tuple[str, str, str]] = []

    async def fake_ping_provider(backend: str, api_key: str, base_url: str) -> PingResult:
        calls.append((backend, api_key, base_url))
        return PingResult(latency_ms=42, model_ids=("ep-20260316142940-b74bm",))

    async def fake_probe_model(
        backend: copilot_test.CopilotProvider,
        api_key: str,
        base_url: str,
        model_id: str,
    ) -> ModelProbeResult:
        return ModelProbeResult(model_id=model_id, status="ok", latency_ms=21)

    monkeypatch.setattr(llm_router, "_ping_provider", fake_ping_provider)
    monkeypatch.setattr(llm_router, "_probe_model", fake_probe_model)

    response = client.post("/api/llm/endpoints/ark-official/test")

    assert response.status_code == 200
    assert calls == [("ark", "secret", "https://ark.cn-beijing.volces.com/api/v3")]
    assert "ark-official:ep-20260316142940-b74bm" in response.json()["registry"]["provider_routes"]


def test_endpoint_test_only_uses_ark_models_list_for_ark_official(
    client: TestClient,
    tmp_path: Path,
    monkeypatch,
) -> None:
    settings_dir = tmp_path / "settings"
    monkeypatch.setattr(config, "APP_SETTINGS_DIR", settings_dir)
    save_credentials(
        LLMCredentialsFile(
            provider_endpoints={
                "ark-official": ProviderEndpoint(
                    endpoint_id="ark-official",
                    display_name="Ark Official",
                    protocol="ark_runtime",
                    base_url="https://ark.cn-beijing.volces.com/api/v3",
                    api_key="secret",
                )
            },
        ),
        credentials_path(),
    )
    probe_calls: list[str] = []

    async def fake_ping_provider(backend: str, api_key: str, base_url: str) -> PingResult:
        assert (backend, api_key, base_url) == (
            "ark",
            "secret",
            "https://ark.cn-beijing.volces.com/api/v3",
        )
        return PingResult(
            latency_ms=42,
            model_ids=(
                "doubao-lite-128k-240428",
                "doubao-seed-2-0-pro-260215",
            ),
        )

    async def fake_probe_model(
        backend: copilot_test.CopilotProvider,
        api_key: str,
        base_url: str,
        model_id: str,
    ) -> ModelProbeResult:
        del backend, api_key, base_url
        probe_calls.append(model_id)
        if model_id == "doubao-seed-2-0-pro-260215":
            return ModelProbeResult(model_id=model_id, status="ok", latency_ms=21)
        return ModelProbeResult(model_id=model_id, status="invalid_model", message="HTTP 404")

    monkeypatch.setattr(llm_router, "_ping_provider", fake_ping_provider)
    monkeypatch.setattr(llm_router, "_probe_model", fake_probe_model)

    response = client.post("/api/llm/endpoints/ark-official/test")

    assert response.status_code == 200
    body = response.json()
    endpoint = body["registry"]["provider_endpoints"]["ark-official"]
    assert endpoint["status"] == "unverified_manual"
    assert "doubao-lite-128k-240428" in endpoint["last_test_message"]
    assert probe_calls == []
    routes = body["registry"]["provider_routes"]
    assert routes["ark-official:doubao-seed-2-0-pro-260215"]["status"] == "unverified_manual"
    assert routes["ark-official:doubao-lite-128k-240428"]["status"] == "unverified_manual"


def test_endpoint_test_replaces_stale_routes_for_changed_endpoint(
    client: TestClient,
    tmp_path: Path,
    monkeypatch,
) -> None:
    settings_dir = tmp_path / "settings"
    monkeypatch.setattr(config, "APP_SETTINGS_DIR", settings_dir)
    save_credentials(
        LLMCredentialsFile(
            provider_endpoints={
                "qiniu": ProviderEndpoint(
                    endpoint_id="qiniu",
                    display_name="Qiniu",
                    protocol="openai_compatible",
                    base_url="https://api.qnaigc.com/v1",
                    api_key="secret",
                )
            },
            provider_routes={
                "qiniu:old-openai-model": ProviderRoute(
                    route_id="qiniu:old-openai-model",
                    endpoint_id="qiniu",
                    route_slug="old-openai-model",
                    provider_model_id="old-openai-model",
                    canonical_id="old-openai-model",
                    display_name="old-openai-model",
                    status="unverified_manual",
                ),
                "other:gpt-5": ProviderRoute(
                    route_id="other:gpt-5",
                    endpoint_id="other",
                    route_slug="gpt-5",
                    provider_model_id="gpt-5",
                    canonical_id="gpt-5",
                    display_name="GPT-5",
                    status="verified",
                ),
            },
        ),
        credentials_path(),
    )

    async def fake_ping_provider(backend: str, api_key: str, base_url: str) -> PingResult:
        return PingResult(latency_ms=42, model_ids=("new-anthropic-model",))

    async def fake_probe_model(
        backend: copilot_test.CopilotProvider,
        api_key: str,
        base_url: str,
        model_id: str,
    ) -> ModelProbeResult:
        return ModelProbeResult(model_id=model_id, status="ok", latency_ms=21)

    monkeypatch.setattr(llm_router, "_ping_provider", fake_ping_provider)
    monkeypatch.setattr(llm_router, "_probe_model", fake_probe_model)

    response = client.post("/api/llm/endpoints/qiniu/test")

    assert response.status_code == 200
    routes = response.json()["registry"]["provider_routes"]
    assert "qiniu:old-openai-model" not in routes
    assert routes["qiniu:new-anthropic-model"]["provider_model_id"] == "new-anthropic-model"
    assert routes["other:gpt-5"]["provider_model_id"] == "gpt-5"


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
    endpoint = body["registry"]["provider_endpoints"]["openai-direct"]
    assert body["tested_endpoint_id"] == "openai-direct"
    assert body["discovered_model_count"] == 0
    assert endpoint["status"] == "failed"
    assert "Invalid API key" in endpoint["last_test_message"]
    assert "invalid_api_key" in endpoint["last_test_message"]


def test_endpoint_test_treats_empty_model_list_as_reachable(
    client: TestClient,
    tmp_path: Path,
    monkeypatch,
) -> None:
    _seed(tmp_path, monkeypatch)

    async def fake_ping_provider(backend: str, api_key: str, base_url: str) -> PingResult:
        return PingResult(latency_ms=42, model_ids=())

    monkeypatch.setattr(llm_router, "_ping_provider", fake_ping_provider)

    response = client.post("/api/llm/endpoints/openai-direct/test")

    assert response.status_code == 200
    body = response.json()
    endpoint = body["registry"]["provider_endpoints"]["openai-direct"]
    assert body["discovered_model_count"] == 0
    assert endpoint["status"] == "unverified_manual"
    assert endpoint["last_test_message"] == "Endpoint reachable but returned no models."
    assert body["registry"]["provider_routes"] == {}


def test_official_endpoint_test_persists_verified_profiles_and_excludes_catalog_only_models(
    client: TestClient,
    tmp_path: Path,
    monkeypatch,
) -> None:
    settings_dir = tmp_path / "settings"
    monkeypatch.setattr(config, "APP_SETTINGS_DIR", settings_dir)
    save_credentials(
        LLMCredentialsFile(
            provider_endpoints={
                "openai-official": ProviderEndpoint(
                    endpoint_id="openai-official",
                    display_name="OpenAI Official",
                    protocol="openai_compatible",
                    base_url="https://api.openai.com/v1",
                    api_key="secret",
                    provider_kind="official",
                )
            },
        ),
        credentials_path(),
    )
    profile_probe_calls: list[str] = []

    async def fake_ping_provider(backend: str, api_key: str, base_url: str) -> PingResult:
        assert (backend, api_key, base_url) == ("openai", "secret", "https://api.openai.com/v1")
        return PingResult(latency_ms=42, model_ids=("gpt-5", "gpt-image-1"))

    async def fake_probe_official_model_profiles(endpoint, model_id: str):
        del endpoint
        profile_probe_calls.append(model_id)
        if model_id != "gpt-5":
            return []
        return [
            VerifiedProfile(
                profile_id="text_responses",
                capability="text_chat",
                method_id="openai_responses",
                request_mapper_id="openai_responses_text",
                status="ready",
                default=True,
                fallback_rank=1,
            ),
            VerifiedProfile(
                profile_id="reasoning_responses",
                capability="reasoning",
                method_id="openai_responses",
                request_mapper_id="openai_responses_reasoning",
                status="ready",
                fallback_rank=1,
                runtime_overrides={"reasoning": {"enabled": True, "effort": "low"}},
            ),
        ]

    monkeypatch.setattr(llm_router, "_ping_provider", fake_ping_provider)
    monkeypatch.setattr(
        llm_router,
        "_probe_official_model_profiles",
        fake_probe_official_model_profiles,
    )

    response = client.post("/api/llm/endpoints/openai-official/test")

    assert response.status_code == 200
    body = response.json()
    routes = body["registry"]["provider_routes"]
    assert profile_probe_calls == ["gpt-5", "gpt-image-1"]
    assert list(routes) == ["openai-official:gpt-5"]
    route = routes["openai-official:gpt-5"]
    assert route["status"] == "verified"
    assert route["verified_profiles"] == [
        {
            "profile_id": "text_responses",
            "capability": "text_chat",
            "method_id": "openai_responses",
            "request_mapper_id": "openai_responses_text",
            "status": "ready",
            "default": True,
            "fallback_rank": 1,
            "input_modalities": ["text"],
            "output_modalities": ["text"],
            "runtime_overrides": {},
            "metadata": {},
        },
        {
            "profile_id": "reasoning_responses",
            "capability": "reasoning",
            "method_id": "openai_responses",
            "request_mapper_id": "openai_responses_reasoning",
            "status": "ready",
            "default": False,
            "fallback_rank": 1,
            "input_modalities": ["text"],
            "output_modalities": ["text"],
            "runtime_overrides": {"reasoning": {"enabled": True, "effort": "low"}},
            "metadata": {},
        },
    ]
    capability_library = body["registry"]["provider_endpoints"]["openai-official"]["metadata"][
        "capability_library"
    ]
    assert capability_library == [
        {"model_id": "gpt-image-1", "status": "catalog_candidate"}
    ]


def test_endpoint_scoped_manual_model_test_verifies_only_successful_models(
    client: TestClient,
    tmp_path: Path,
    monkeypatch,
) -> None:
    _seed(tmp_path, monkeypatch)
    calls: list[tuple[str, str, str, str]] = []

    async def fake_probe_model(
        backend: str,
        api_key: str,
        base_url: str,
        model_id: str,
    ) -> ModelProbeResult:
        calls.append((backend, api_key, base_url, model_id))
        if model_id == "gpt-5-mini":
            return ModelProbeResult(model_id=model_id, status="ok", latency_ms=33)
        return ModelProbeResult(
            model_id=model_id,
            status="invalid_model",
            latency_ms=34,
            message="Provider rejected model.",
        )

    monkeypatch.setattr(llm_router, "_probe_model", fake_probe_model)

    response = client.post(
        "/api/llm/endpoints/openai-direct/models/test",
        json={"model_ids": ["gpt-5-mini", "missing-model", "gpt-5-mini", ""]},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["results"] == [
        {
            "model_id": "gpt-5-mini",
            "status": "ok",
            "route_id": "openai-direct:gpt-5-mini",
            "message": None,
        },
        {
            "model_id": "missing-model",
            "status": "invalid_model",
            "route_id": None,
            "message": "Provider rejected model.",
        },
    ]
    routes = body["registry"]["provider_routes"]
    endpoint = body["registry"]["provider_endpoints"]["openai-direct"]
    assert endpoint["status"] == "verified"
    assert "gpt-5-mini" in endpoint["last_test_message"]
    assert routes["openai-direct:gpt-5-mini"]["status"] == "verified"
    assert routes["openai-direct:gpt-5-mini"]["provider_model_id"] == "gpt-5-mini"
    assert "openai-direct:missing-model" not in routes
    assert calls == [
        ("openai", "secret", "https://api.openai.example/v1", "gpt-5-mini"),
        ("openai", "secret", "https://api.openai.example/v1", "missing-model"),
    ]


def test_endpoint_test_does_not_resurrect_secret_cleared_during_probe(
    client: TestClient,
    tmp_path: Path,
    monkeypatch,
) -> None:
    _seed(tmp_path, monkeypatch)

    async def fake_ping_provider(backend: str, api_key: str, base_url: str) -> PingResult:
        raw = json.loads(credentials_path().read_text(encoding="utf-8"))
        raw["provider_endpoints"]["openai-direct"]["api_key"] = None
        credentials_path().write_text(json.dumps(raw), encoding="utf-8")
        return PingResult(latency_ms=42, model_ids=("gpt-5-mini",))

    monkeypatch.setattr(llm_router, "_ping_provider", fake_ping_provider)

    response = client.post("/api/llm/endpoints/openai-direct/test")

    assert response.status_code == 200
    raw = json.loads(credentials_path().read_text(encoding="utf-8"))
    assert raw["provider_endpoints"]["openai-direct"]["api_key"] is None
    endpoint = response.json()["registry"]["provider_endpoints"]["openai-direct"]
    assert endpoint["status"] == "unverified_manual"
    assert "changed while endpoint test was running" in endpoint["last_test_message"]
    assert "openai-direct:gpt-5-mini" not in response.json()["registry"]["provider_routes"]


def test_manual_model_test_does_not_resurrect_secret_cleared_during_probe(
    client: TestClient,
    tmp_path: Path,
    monkeypatch,
) -> None:
    _seed(tmp_path, monkeypatch)

    async def fake_probe_model(
        backend: str,
        api_key: str,
        base_url: str,
        model_id: str,
    ) -> ModelProbeResult:
        raw = json.loads(credentials_path().read_text(encoding="utf-8"))
        raw["provider_endpoints"]["openai-direct"]["api_key"] = None
        credentials_path().write_text(json.dumps(raw), encoding="utf-8")
        return ModelProbeResult(model_id=model_id, status="ok", latency_ms=33)

    monkeypatch.setattr(llm_router, "_probe_model", fake_probe_model)

    response = client.post(
        "/api/llm/endpoints/openai-direct/models/test",
        json={"model_ids": ["gpt-5-mini"]},
    )

    assert response.status_code == 200
    raw = json.loads(credentials_path().read_text(encoding="utf-8"))
    assert raw["provider_endpoints"]["openai-direct"]["api_key"] is None
    assert response.json()["results"] == [
        {
            "model_id": "gpt-5-mini",
            "status": "error",
            "route_id": None,
            "message": "Endpoint changed while model test was running.",
        }
    ]
    assert "openai-direct:gpt-5-mini" not in response.json()["registry"]["provider_routes"]


def test_discovered_route_slug_collision_uses_deterministic_suffix(
    client: TestClient,
    tmp_path: Path,
    monkeypatch,
) -> None:
    _seed(tmp_path, monkeypatch)

    async def fake_ping_provider(backend: str, api_key: str, base_url: str) -> PingResult:
        return PingResult(latency_ms=42, model_ids=("foo/bar", "foo.bar"))

    async def fake_probe_model(
        backend: copilot_test.CopilotProvider,
        api_key: str,
        base_url: str,
        model_id: str,
    ) -> ModelProbeResult:
        return ModelProbeResult(model_id=model_id, status="ok", latency_ms=21)

    monkeypatch.setattr(llm_router, "_ping_provider", fake_ping_provider)
    monkeypatch.setattr(llm_router, "_probe_model", fake_probe_model)

    response = client.post("/api/llm/endpoints/openai-direct/test")

    assert response.status_code == 200
    routes = response.json()["registry"]["provider_routes"]
    discovered = [
        route for route in routes.values() if route["provider_model_id"] in {"foo/bar", "foo.bar"}
    ]
    assert len(discovered) == 2
    assert {route["provider_model_id"] for route in discovered} == {"foo/bar", "foo.bar"}
    assert len([route_id for route_id, route in routes.items() if route["provider_model_id"] in {"foo/bar", "foo.bar"}]) == 2


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


def test_route_probe_force_true_calls_real_provider_probe(
    client: TestClient,
    tmp_path: Path,
    monkeypatch,
) -> None:
    _seed(tmp_path, monkeypatch)
    calls: list[dict[str, str]] = []

    async def fake_probe_model(
        backend: copilot_test.CopilotProvider,
        api_key: str,
        base_url: str,
        model_id: str,
    ) -> ModelProbeResult:
        calls.append(
            {
                "backend": backend,
                "api_key": api_key,
                "base_url": base_url,
                "model_id": model_id,
            }
        )
        return ModelProbeResult(model_id=model_id, status="ok")

    monkeypatch.setattr(llm_router, "_probe_model", fake_probe_model)

    response = client.post("/api/llm/routes/openai-direct:gpt-5/probe?force=true", json={})

    assert response.status_code == 200
    assert calls == [
        {
            "backend": "openai",
            "api_key": "secret",
            "base_url": "https://api.openai.example/v1",
            "model_id": "gpt-5",
        }
    ]
    assert response.json()["status"] == "verified"


def test_route_probe_force_true_success_closes_active_route_circuit(
    client: TestClient,
    tmp_path: Path,
    monkeypatch,
) -> None:
    _seed(tmp_path, monkeypatch)
    retry_at = datetime.now(UTC) + timedelta(seconds=60)
    _open_runtime_circuit(route_id="openai-direct:gpt-5", retry_at=retry_at)

    async def fake_probe_model(
        backend: copilot_test.CopilotProvider,
        api_key: str,
        base_url: str,
        model_id: str,
    ) -> ModelProbeResult:
        del backend, api_key, base_url
        return ModelProbeResult(model_id=model_id, status="ok", latency_ms=12)

    monkeypatch.setattr(llm_router, "_probe_model", fake_probe_model)

    response = client.post("/api/llm/routes/openai-direct:gpt-5/probe?force=true", json={})

    assert response.status_code == 200
    assert response.json()["status"] == "verified"

    from app.services.llm_health_store import SqliteLlmHealthStore

    active = SqliteLlmHealthStore(_health_store_path()).get_active_circuits(
        route_id="openai-direct:gpt-5",
        endpoint_id="openai-direct",
        rate_limit_bucket="openai-direct",
        now=datetime.now(UTC),
    )
    assert active == []


def test_route_probe_force_true_transient_failure_refreshes_route_circuit(
    client: TestClient,
    tmp_path: Path,
    monkeypatch,
) -> None:
    _seed(tmp_path, monkeypatch)
    previous_retry_at = datetime.now(UTC) + timedelta(seconds=10)
    _open_runtime_circuit(
        route_id="openai-direct:gpt-5",
        retry_at=previous_retry_at,
        reason_code="timeout",
        message="previous timeout",
    )

    async def fake_probe_model(
        backend: copilot_test.CopilotProvider,
        api_key: str,
        base_url: str,
        model_id: str,
    ) -> ModelProbeResult:
        del backend, api_key, base_url
        return ModelProbeResult(
            model_id=model_id,
            status="timeout",
            message="forced probe timed out",
        )

    monkeypatch.setattr(llm_router, "_probe_model", fake_probe_model)

    response = client.post("/api/llm/routes/openai-direct:gpt-5/probe?force=true", json={})

    assert response.status_code == 200

    from app.services.llm_health_store import SqliteLlmHealthStore

    active = SqliteLlmHealthStore(_health_store_path()).get_active_circuits(
        route_id="openai-direct:gpt-5",
        endpoint_id="openai-direct",
        rate_limit_bucket="openai-direct",
        now=datetime.now(UTC),
    )
    assert len(active) == 1
    assert active[0].scope == "route"
    assert active[0].scope_id == "openai-direct:gpt-5"
    assert active[0].retry_at > previous_retry_at
    assert active[0].reason_code == "timeout"
    assert active[0].message == "forced probe timed out"

    registry = client.get("/api/llm/registry").json()
    provider_model = registry["model_groups"][0]["provider_models"][0]
    assert provider_model["ui_state"] == "cooling_down"
    assert provider_model["retry_at"] == active[0].retry_at.isoformat()


def test_route_probe_force_true_hard_failure_projects_needs_setup(
    client: TestClient,
    tmp_path: Path,
    monkeypatch,
) -> None:
    _seed(tmp_path, monkeypatch)

    async def fake_probe_model(
        backend: copilot_test.CopilotProvider,
        api_key: str,
        base_url: str,
        model_id: str,
    ) -> ModelProbeResult:
        del backend, api_key, base_url
        return ModelProbeResult(
            model_id=model_id,
            status="invalid_model",
            message="provider rejected model",
        )

    monkeypatch.setattr(llm_router, "_probe_model", fake_probe_model)

    response = client.post("/api/llm/routes/openai-direct:gpt-5/probe?force=true", json={})

    assert response.status_code == 200
    assert response.json()["status"] == "failed"

    registry = client.get("/api/llm/registry").json()
    provider_model = registry["model_groups"][0]["provider_models"][0]
    assert provider_model["route_id"] == "openai-direct:gpt-5"
    assert provider_model["ui_state"] == "needs_setup"
    assert provider_model["reason_code"] == "invalid_model"


def test_put_role_v3_materializes_model_groups_to_gateway_fallback_chain(
    client: TestClient,
    tmp_path: Path,
    monkeypatch,
) -> None:
    settings_dir = tmp_path / "settings"
    monkeypatch.setattr(config, "APP_SETTINGS_DIR", settings_dir)
    active_credentials_path = settings_dir / "llm" / "llm_credentials.json"
    roles_path = settings_dir / "llm" / "llm_roles.yaml"
    credentials = LLMCredentialsFile(
        provider_endpoints={
            "openai-direct": ProviderEndpoint(
                endpoint_id="openai-direct",
                display_name="OpenAI",
                protocol="openai_compatible",
                base_url="https://api.openai.example/v1",
                api_key="secret",
            ),
            "openrouter-prod": ProviderEndpoint(
                endpoint_id="openrouter-prod",
                display_name="OpenRouter",
                protocol="openai_compatible",
                base_url="https://openrouter.ai/api/v1",
                api_key="secret",
            ),
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
            ),
            "openrouter-prod:openai.gpt-5": ProviderRoute(
                route_id="openrouter-prod:openai.gpt-5",
                endpoint_id="openrouter-prod",
                route_slug="openai.gpt-5",
                provider_model_id="openai/gpt-5",
                canonical_id="gpt-5",
                display_name="GPT-5",
                status="verified",
            ),
            "openai-direct:gpt-4o": ProviderRoute(
                route_id="openai-direct:gpt-4o",
                endpoint_id="openai-direct",
                route_slug="gpt-4o",
                provider_model_id="gpt-4o",
                canonical_id="gpt-4o",
                display_name="GPT-4o",
                status="verified",
            ),
        },
    )
    save_credentials(credentials, active_credentials_path)
    save_roles_file(roles_path, RolesData(), known_route_ids=set(credentials.provider_routes))

    response = client.put(
        "/api/llm/roles/analyst",
        json={
            "role_kind": "graph_agent",
            "system_prompt_prefix": "",
            "model_fallback_enabled": True,
            "intent": {"provider_preference": "manual_order"},
            "model_groups": [
                {
                    "canonical_id": "gpt-5",
                    "display_name": "GPT-5",
                    "provider_models": [
                        {"route_id": "openai-direct:gpt-5"},
                        {"route_id": "openrouter-prod:openai.gpt-5"},
                    ],
                },
                {
                    "canonical_id": "gpt-4o",
                    "display_name": "GPT-4o",
                    "provider_models": [{"route_id": "openai-direct:gpt-4o"}],
                },
            ],
        },
    )

    assert response.status_code == 200
    assert [entry["route_id"] for entry in response.json()["fallback_chain"]] == [
        "openai-direct:gpt-5",
        "openrouter-prod:openai.gpt-5",
        "openai-direct:gpt-4o",
    ]
    assert response.json()["materialization_report"]["warnings"] == []


def test_put_role_v3_model_fallback_disabled_keeps_provider_fallback_only(
    client: TestClient,
    tmp_path: Path,
    monkeypatch,
) -> None:
    settings_dir = tmp_path / "settings"
    monkeypatch.setattr(config, "APP_SETTINGS_DIR", settings_dir)
    active_credentials_path = settings_dir / "llm" / "llm_credentials.json"
    roles_path = settings_dir / "llm" / "llm_roles.yaml"
    credentials = LLMCredentialsFile(
        provider_endpoints={
            "openai-direct": ProviderEndpoint(
                endpoint_id="openai-direct",
                display_name="OpenAI",
                protocol="openai_compatible",
                base_url="https://api.openai.example/v1",
                api_key="secret",
            ),
            "openrouter-prod": ProviderEndpoint(
                endpoint_id="openrouter-prod",
                display_name="OpenRouter",
                protocol="openai_compatible",
                base_url="https://openrouter.ai/api/v1",
                api_key="secret",
            ),
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
            ),
            "openrouter-prod:openai.gpt-5": ProviderRoute(
                route_id="openrouter-prod:openai.gpt-5",
                endpoint_id="openrouter-prod",
                route_slug="openai.gpt-5",
                provider_model_id="openai/gpt-5",
                canonical_id="gpt-5",
                display_name="GPT-5",
                status="verified",
            ),
            "openai-direct:gpt-4o": ProviderRoute(
                route_id="openai-direct:gpt-4o",
                endpoint_id="openai-direct",
                route_slug="gpt-4o",
                provider_model_id="gpt-4o",
                canonical_id="gpt-4o",
                display_name="GPT-4o",
                status="verified",
            ),
        },
    )
    save_credentials(credentials, active_credentials_path)
    save_roles_file(roles_path, RolesData(), known_route_ids=set(credentials.provider_routes))

    response = client.put(
        "/api/llm/roles/analyst",
        json={
            "role_kind": "graph_agent",
            "system_prompt_prefix": "",
            "model_fallback_enabled": False,
            "intent": {"provider_preference": "manual_order"},
            "model_groups": [
                {
                    "canonical_id": "gpt-5",
                    "display_name": "GPT-5",
                    "provider_models": [
                        {"route_id": "openai-direct:gpt-5"},
                        {"route_id": "openrouter-prod:openai.gpt-5"},
                    ],
                },
                {
                    "canonical_id": "gpt-4o",
                    "display_name": "GPT-4o",
                    "provider_models": [{"route_id": "openai-direct:gpt-4o"}],
                },
            ],
        },
    )

    assert response.status_code == 200
    assert [entry["route_id"] for entry in response.json()["fallback_chain"]] == [
        "openai-direct:gpt-5",
        "openrouter-prod:openai.gpt-5",
    ]


def test_role_test_uses_persisted_role_and_ignores_draft_payload(
    client: TestClient,
    tmp_path: Path,
    monkeypatch,
) -> None:
    _seed(tmp_path, monkeypatch)
    calls: list[str] = []

    async def fake_probe_model(
        backend: copilot_test.CopilotProvider,
        api_key: str,
        base_url: str,
        model_id: str,
    ) -> ModelProbeResult:
        del backend, api_key, base_url
        calls.append(model_id)
        return ModelProbeResult(model_id=model_id, status="ok")

    monkeypatch.setattr(llm_router, "_probe_model", fake_probe_model)

    response = client.post(
        "/api/llm/roles/graph_agent/test",
        json={"fallback_chain": []},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["role_name"] == "graph_agent"
    assert body["status"] in {"ok", "warning", "blocked", "failed"}
    assert body["warnings"] == []
    assert calls == ["gpt-5"]
    provider_result = body["model_groups"][0]["provider_results"][0]
    assert provider_result["route_id"] == "openai-direct:gpt-5"
    assert provider_result["provider_ui_state"] == "ready"
    assert provider_result["role_fit"] == "using"
    assert provider_result["admission_decision"] == "admit"
    assert provider_result["status"] == "ok"
    assert provider_result["warnings"] == []
    assert "resolved_settings" in provider_result


def test_role_test_reports_materialized_not_fit_provider_diagnostics(
    client: TestClient,
    tmp_path: Path,
    monkeypatch,
) -> None:
    settings_dir = tmp_path / "settings"
    monkeypatch.setattr(config, "APP_SETTINGS_DIR", settings_dir)
    active_credentials_path = settings_dir / "llm" / "llm_credentials.json"
    roles_path = settings_dir / "llm" / "llm_roles.yaml"
    credentials = LLMCredentialsFile(
        provider_endpoints={
            "openai-direct": ProviderEndpoint(
                endpoint_id="openai-direct",
                display_name="OpenAI",
                protocol="openai_compatible",
                base_url="https://api.openai.example/v1",
                api_key="secret",
                status="verified",
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
                    "thinking_protocol": CapabilityValue(
                        value=False,
                        source="provider_doc",
                    )
                },
            )
        },
    )
    save_credentials(credentials, active_credentials_path)
    save_roles_file(roles_path, RolesData(), known_route_ids=set(credentials.provider_routes))
    calls: list[str] = []

    async def fake_probe_model(
        backend: copilot_test.CopilotProvider,
        api_key: str,
        base_url: str,
        model_id: str,
    ) -> ModelProbeResult:
        del backend, api_key, base_url
        calls.append(model_id)
        return ModelProbeResult(model_id=model_id, status="ok")

    monkeypatch.setattr(llm_router, "_probe_model", fake_probe_model)

    put_response = client.put(
        "/api/llm/roles/analyst",
        json={
            "role_kind": "graph_agent",
            "system_prompt_prefix": "",
            "model_fallback_enabled": True,
            "intent": {
                "provider_preference": "manual_order",
                "thinking": "required",
            },
            "model_groups": [
                {
                    "canonical_id": "gpt-5",
                    "display_name": "GPT-5",
                    "provider_models": [{"route_id": "openai-direct:gpt-5"}],
                }
            ],
        },
    )
    assert put_response.status_code == 200
    assert put_response.json()["fallback_chain"] == []
    assert put_response.json()["materialization_report"]["entries"][0]["role_fit"] == "not_fit"

    response = client.post("/api/llm/roles/analyst/test", json={})

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "blocked"
    assert calls == []
    provider_result = body["model_groups"][0]["provider_results"][0]
    assert provider_result["route_id"] == "openai-direct:gpt-5"
    assert provider_result["provider_ui_state"] == "ready"
    assert provider_result["role_fit"] == "not_fit"
    assert provider_result["admission_decision"] == "block"
    assert provider_result["status"] == "blocked"
    assert provider_result["warnings"][0]["code"] == "thinking_unsupported"


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
