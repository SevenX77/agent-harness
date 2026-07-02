from __future__ import annotations

import asyncio
import json
import threading
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest
from app.core import config
from app.models.llm_config import (
    CapabilityValue,
    LLMCredentialsFile,
    ModelBundle,
    ModelProfile,
    ProviderEndpoint,
    ProviderRoute,
    RoleEntry,
    RoleModelGroup,
    RoleProviderModel,
    RoleRouteEntry,
    RolesData,
)
from app.routers import llm as llm_router
from app.services.community_catalog import parse_catalog_evidence
from app.services.community_catalog_runtime import (
    promote_community_evidence_into_credentials,
)
from app.services.llm_credentials import credentials_path, load_credentials, save_credentials
from app.services.llm_roles import load_roles_file, save_roles_file
from app.services.llm_roles import roles_path as active_roles_path
from app.services.model_probe import ModelProbeResult
from fastapi.testclient import TestClient
from graph_agent_gateway.registry import provider_probe as gateway_provider_probe
from graph_agent_gateway.registry.provider_probe import EndpointProbeResult, RouteProbeResult
from graph_agent_gateway.registry.schema import EvidenceRecord, VerifiedProfile


def _endpoint_probe_ok(
    endpoint: ProviderEndpoint,
    *,
    latency_ms: int = 10,
    model_ids: tuple[str, ...] = (),
    model_capabilities: dict[str, dict[str, object]] | None = None,
) -> EndpointProbeResult:
    """Build the gateway EndpointProbeResult a successful endpoint Test returns."""
    return EndpointProbeResult(
        endpoint_id=endpoint.endpoint_id,
        provider_kind=endpoint.provider_kind,
        backend=llm_router._endpoint_probe_backend(endpoint),
        base_url=llm_router._endpoint_probe_base_url(endpoint),
        status="ok",
        latency_ms=latency_ms,
        model_ids=model_ids,
        model_capabilities=model_capabilities or {},
    )


def _endpoint_probe(
    endpoint: ProviderEndpoint,
    *,
    status: str,
    message: str | None = None,
    error_code: str | None = None,
    latency_ms: int | None = None,
    model_ids: tuple[str, ...] = (),
) -> EndpointProbeResult:
    """Build a gateway EndpointProbeResult with an explicit status/error."""
    return EndpointProbeResult(
        endpoint_id=endpoint.endpoint_id,
        provider_kind=endpoint.provider_kind,
        backend=llm_router._endpoint_probe_backend(endpoint),
        base_url=llm_router._endpoint_probe_base_url(endpoint),
        status=status,  # type: ignore[arg-type]
        latency_ms=latency_ms,
        model_ids=model_ids,
        message=message,
        error_code=error_code,
    )


def _route_probe(
    endpoint: ProviderEndpoint,
    route: ProviderRoute,
    *,
    status: str,
    latency_ms: int | None = None,
    message: str | None = None,
) -> RouteProbeResult:
    """Build the gateway RouteProbeResult a route generation probe returns."""
    return RouteProbeResult(
        endpoint_id=endpoint.endpoint_id,
        route_id=route.route_id,
        provider_kind=endpoint.provider_kind,
        backend=llm_router._endpoint_probe_backend(endpoint),
        base_url=llm_router._endpoint_probe_base_url(endpoint),
        model_id=route.provider_model_id,
        status=status,  # type: ignore[arg-type]
        latency_ms=latency_ms,
        message=message,
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


def test_role_effective_runtime_settings_uses_gateway_model_resolver(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.core.adapters.gateway import GatewayAdapter
    from graph_agent_gateway.resolver import ModelResolver

    route_id = "openai-direct:gpt-5"
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
            route_id: ProviderRoute(
                route_id=route_id,
                endpoint_id="openai-direct",
                route_slug="gpt-5",
                provider_model_id="gpt-5",
                canonical_id="gpt-5",
            )
        },
    )
    roles = RolesData(
        roles={
            "graph_agent": RoleEntry(
                fallback_chain=[RoleRouteEntry(route_id=route_id)],
            )
        }
    )
    calls: list[str] = []
    original_resolve_routes = ModelResolver.resolve_routes

    def recording_resolve_routes(
        self: ModelResolver,
        role_name: str,
        *,
        route_override: str | None = None,
    ):
        assert route_override is None
        calls.append(role_name)
        return original_resolve_routes(self, role_name, route_override=route_override)

    monkeypatch.setattr(ModelResolver, "resolve_routes", recording_resolve_routes)
    monkeypatch.setattr(
        llm_router,
        "build_gateway_adapter",
        lambda: GatewayAdapter(transport="in_process"),
    )

    result = llm_router._role_effective_runtime_settings(credentials, roles)

    assert calls == ["graph_agent"]
    assert route_id in result["graph_agent"]


def test_role_effective_runtime_settings_projects_no_available_route(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class NoAvailableRouteError(Exception):
        error_code = "resource.no_available_route"
        error_payload = {"role": "graph_agent"}

    def raise_no_available_route(_self: object, _payload: dict[str, object]) -> object:
        raise NoAvailableRouteError()

    class FailingGatewayAdapter:
        resolve_routes = raise_no_available_route

    monkeypatch.setattr(
        llm_router,
        "build_gateway_adapter",
        lambda: FailingGatewayAdapter(),
    )

    result = llm_router._role_effective_runtime_settings(
        LLMCredentialsFile(),
        RolesData(
            roles={
                "graph_agent": RoleEntry(
                    fallback_chain=[RoleRouteEntry(route_id="missing:model")],
                )
            }
        ),
    )

    assert result == {"graph_agent": {}}


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
    # W3-B.4: the registry projection stamps the provider's registrable-domain id
    # (eTLD+1 of base_url) so the UI can show it under the display alias.
    assert body["provider_endpoints"]["openai-direct"]["registrable_provider_name"] == "openai"
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


def test_registry_community_summary_derives_from_credentials(
    client: TestClient,
    tmp_path: Path,
    monkeypatch,
) -> None:
    """Phase 5: the registry community summary derives from CREDENTIALS — ``synced`` and
    ``generated_at`` from the last-sync marker, ``record_count`` = community-provenance
    evidence merged into routes. Community evidence is advisory: it never inflates the
    LOCAL probe counts (it is downloaded, not locally probed)."""
    from app.models.llm_config import RemoteCatalogSyncMarker

    _seed(tmp_path, monkeypatch)
    creds = load_credentials(credentials_path())
    creds.provider_routes["openai-direct:gpt-5"] = creds.provider_routes["openai-direct:gpt-5"].model_copy(
        update={"evidence": [_community_probe_record(evidence_id="cat-x", model_id="gpt-5")]}
    )
    creds.last_remote_catalog_sync = RemoteCatalogSyncMarker(
        etag='"abc-1"',
        generated_at="2026-06-26T14:40:44Z",
        last_synced_at="2026-06-26T15:00:00Z",
    )
    save_credentials(creds, credentials_path())

    body = client.get("/api/llm/registry").json()

    community = body["probe_catalog"]["community_catalog"]
    assert community["synced"] is True
    assert community["record_count"] == 1
    assert community["generated_at"] == "2026-06-26T14:40:44Z"
    # Community evidence is advisory: it must NOT inflate the LOCAL probe counts.
    assert body["probe_catalog"]["local_verified_records_count"] == 0
    assert body["probe_catalog"]["local_evidence_records_count"] == 0


def test_registry_probe_catalog_community_absent_when_no_cache(
    client: TestClient,
    tmp_path: Path,
    monkeypatch,
) -> None:
    _seed(tmp_path, monkeypatch)

    body = client.get("/api/llm/registry").json()

    community = body["probe_catalog"]["community_catalog"]
    assert community["synced"] is False
    assert community["record_count"] == 0
    assert community["entries"] == []


def _seed_deepseek_verified_endpoint(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    route_status: str = "unverified_manual",
) -> Path:
    """A VERIFIED DeepSeek endpoint (api.deepseek.com/v1) with one not-yet-tested
    route — the exact shape of the screenshot the user reported."""
    settings_dir = tmp_path / "settings"
    monkeypatch.setattr(config, "APP_SETTINGS_DIR", settings_dir)
    creds_path = settings_dir / "llm" / "llm_credentials.json"
    roles_path = settings_dir / "llm" / "llm_roles.yaml"
    save_credentials(
        LLMCredentialsFile(
            provider_endpoints={
                "deepseek-official": ProviderEndpoint(
                    endpoint_id="deepseek-official",
                    display_name="DeepSeek Official",
                    protocol="openai_compatible",
                    base_url="https://api.deepseek.com/v1",
                    api_key="secret",
                    status="verified",
                )
            },
            provider_routes={
                "deepseek-official:deepseek-v4-pro": ProviderRoute(
                    route_id="deepseek-official:deepseek-v4-pro",
                    endpoint_id="deepseek-official",
                    route_slug="deepseek-v4-pro",
                    provider_model_id="deepseek-v4-pro",
                    canonical_id="deepseek-v4-pro",
                    display_name="DeepSeek V4 Pro",
                    status=route_status,
                )
            },
        ),
        creds_path,
    )
    save_roles_file(
        roles_path,
        RolesData(),
        known_route_ids={"deepseek-official:deepseek-v4-pro"},
    )
    return creds_path


def _community_probe_record(
    *,
    evidence_id: str = "cat-deepseek-pro",
    normalized_public_base_url: str = "https://api.deepseek.com",
    model_id: str = "deepseek-v4-pro",
    trust_state: str = "probe-verified",
    evidence_type: str = "probe_result",
) -> EvidenceRecord:
    return parse_catalog_evidence(
        {
            "evidence_type": evidence_type,
            "trust_state": trust_state,
            "evidence_id": evidence_id,
            "normalized_public_base_url": normalized_public_base_url,
            "provider_model_id": model_id,
            "model_id": model_id,
            "method_id": "deepseek_chat_completions",
            "capability_family": "language_reasoning",
            "observed_at": "2026-06-26T09:33:40+00:00",
            "probe_status": "ok",
            "input_modalities": ["text"],
            "output_modalities": ["text"],
        }
    )


def test_community_evidence_merges_matching_route_to_historical_ready(
    client: TestClient,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Phase 5: a probe-verified community record whose host + model match a route is
    MERGED onto that route's ``evidence`` (SSOT, via merge_route_evidence — not
    metadata refs), so the registry projects it historical_ready (blue) — host-tolerant
    across a /v1 suffix. Community provenance is preserved (never re-uploaded)."""
    creds_path = _seed_deepseek_verified_endpoint(tmp_path, monkeypatch)

    updated = promote_community_evidence_into_credentials(
        community_records=[_community_probe_record()]
    )
    assert updated == 1

    # The credential route now carries the community evidence ON route.evidence ...
    route = load_credentials(creds_path).provider_routes["deepseek-official:deepseek-v4-pro"]
    assert [e.evidence_id for e in route.evidence] == ["cat-deepseek-pro"]
    assert route.evidence[0].trust_state == "probe-verified"
    assert route.evidence[0].metadata.get("provenance") == "community-catalog"
    assert "evidence_refs" not in route.metadata  # no legacy metadata-refs path
    # ... but community evidence must NEVER promote a route to verified/green.
    assert route.status == "unverified_manual"

    # ... and the registry projects the route as historical_ready (blue).
    body = client.get("/api/llm/registry").json()
    provider_models = {
        opt["route_id"]: opt
        for group in body["model_groups"]
        for opt in group["provider_models"]
    }
    assert provider_models["deepseek-official:deepseek-v4-pro"]["ui_state"] == "historical_ready"


def test_registry_stamps_route_reason_code(
    client: TestClient,
    tmp_path: Path,
    monkeypatch,
) -> None:
    # W2-A: the registry stamps the authoritative ui_state AND reason_code onto each
    # route so the frontend reads them directly instead of re-deriving the failure
    # scope by matching message text. A failed route projects reason_code=model_failed.
    settings_dir = tmp_path / "settings"
    monkeypatch.setattr(config, "APP_SETTINGS_DIR", settings_dir)
    save_credentials(
        LLMCredentialsFile(
            provider_endpoints={
                "oai": ProviderEndpoint(
                    endpoint_id="oai",
                    display_name="OpenAI",
                    protocol="openai_compatible",
                    base_url="https://api.openai.example/v1",
                    api_key="secret",
                    status="verified",
                )
            },
            provider_routes={
                "oai:gpt-5": ProviderRoute(
                    route_id="oai:gpt-5",
                    endpoint_id="oai",
                    route_slug="gpt-5",
                    provider_model_id="gpt-5",
                    canonical_id="gpt-5",
                    display_name="GPT-5",
                    status="failed",
                )
            },
        ),
        credentials_path(),
    )

    routes = client.get("/api/llm/registry").json()["provider_routes"]
    assert routes["oai:gpt-5"]["ui_state"] == "failed"
    assert routes["oai:gpt-5"]["reason_code"] == "model_failed"


def test_community_evidence_skips_unmatched_host_and_observed_only(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """No write when host does not match, and observed-only (not probe-verified)
    community records never contribute to historical_ready."""
    creds_path = _seed_deepseek_verified_endpoint(tmp_path, monkeypatch)

    updated = promote_community_evidence_into_credentials(
        community_records=[
            # Wrong host — different provider, must not touch DeepSeek route.
            _community_probe_record(
                evidence_id="cat-other-host",
                normalized_public_base_url="https://api.openai.com",
            ),
            # Right host + model but only list-observed, not probe-verified.
            EvidenceRecord(
                evidence_id="cat-observed-only",
                evidence_type="model_list_observation",
                trust_state="provider-list-observed",
                model_id="deepseek-v4-pro",
                provider_model_id="deepseek-v4-pro",
                normalized_public_base_url="https://api.deepseek.com",
            ),
        ]
    )

    assert updated == 0
    route = load_credentials(creds_path).provider_routes["deepseek-official:deepseek-v4-pro"]
    assert route.evidence == []


def test_legacy_import_draft_routes_are_not_public_api(client: TestClient) -> None:
    response = client.post(
        "/api/llm/import-drafts",
        json={"draft_id": "legacy", "source": {"kind": "test"}, "status": "pending"},
    )

    assert response.status_code == 404


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


def test_registry_response_enriches_existing_official_route_capabilities(
    client: TestClient,
    tmp_path: Path,
    monkeypatch,
) -> None:
    settings_dir = tmp_path / "settings"
    monkeypatch.setattr(config, "APP_SETTINGS_DIR", settings_dir)
    save_credentials(
        LLMCredentialsFile(
            provider_endpoints={
                "anthropic-official": ProviderEndpoint(
                    endpoint_id="anthropic-official",
                    display_name="Anthropic Official",
                    protocol="anthropic_compatible",
                    base_url="https://api.anthropic.com",
                    api_key="secret",
                    provider_kind="official",
                ),
                "deepseek-official": ProviderEndpoint(
                    endpoint_id="deepseek-official",
                    display_name="DeepSeek Official",
                    protocol="openai_compatible",
                    base_url="https://api.deepseek.com",
                    api_key="secret",
                    provider_kind="official",
                ),
            },
            provider_routes={
                "anthropic-official:claude-opus-4.8": ProviderRoute(
                    route_id="anthropic-official:claude-opus-4.8",
                    endpoint_id="anthropic-official",
                    route_slug="claude-opus-4.8",
                    provider_model_id="claude-opus-4.8",
                    canonical_id="claude-opus-4.8",
                    status="verified",
                    capabilities={
                        "input_modalities": CapabilityValue(
                            value=["text"],
                            source="probed_verified",
                        ),
                        "output_modalities": CapabilityValue(
                            value=["text"],
                            source="probed_verified",
                        ),
                    },
                ),
                "deepseek-official:deepseek-v4-pro": ProviderRoute(
                    route_id="deepseek-official:deepseek-v4-pro",
                    endpoint_id="deepseek-official",
                    route_slug="deepseek-v4-pro",
                    provider_model_id="deepseek-v4-pro",
                    canonical_id="deepseek-v4-pro",
                    status="verified",
                ),
            },
        ),
        credentials_path(),
    )
    save_roles_file(active_roles_path(), RolesData(), known_route_ids=set())

    response = client.get("/api/llm/registry")

    assert response.status_code == 200
    body = response.json()
    claude_caps = body["provider_routes"]["anthropic-official:claude-opus-4.8"][
        "capabilities"
    ]
    assert claude_caps["input_modalities"] == {
        "value": ["text", "image", "pdf"],
        "source": "provider_doc",
        "observed_at": None,
        "message": None,
    }
    assert "https://docs.anthropic.com/en/docs/build-with-claude/vision" in claude_caps[
        "input_modalities_source_urls"
    ]["value"]
    assert "https://docs.anthropic.com/en/docs/build-with-claude/pdf-support" in claude_caps[
        "input_modalities_source_urls"
    ]["value"]
    assert claude_caps["output_modalities"]["value"] == ["text"]
    deepseek_caps = body["provider_routes"]["deepseek-official:deepseek-v4-pro"][
        "capabilities"
    ]
    assert deepseek_caps["max_input_tokens"]["value"] == 1_048_576
    assert deepseek_caps["max_output_tokens"]["value"] == 393_216
    assert deepseek_caps["max_input_tokens"]["source"] == "provider_doc"
    assert "https://api-docs.deepseek.com/quick_start/pricing" in deepseek_caps[
        "max_input_tokens_source_urls"
    ]["value"]


def test_official_catalog_capabilities_include_maintainable_source_urls() -> None:
    endpoints = {
        "claude": ProviderEndpoint(
            endpoint_id="anthropic-official",
            display_name="Anthropic Official",
            protocol="anthropic_compatible",
            base_url="https://api.anthropic.com",
            provider_kind="official",
        ),
        "openai": ProviderEndpoint(
            endpoint_id="openai-official",
            display_name="OpenAI Official",
            protocol="openai_compatible",
            base_url="https://api.openai.com/v1",
            provider_kind="official",
        ),
        "gemini": ProviderEndpoint(
            endpoint_id="gemini-official",
            display_name="Gemini Official",
            protocol="google_genai",
            base_url="https://generativelanguage.googleapis.com",
            provider_kind="official",
        ),
        "deepseek": ProviderEndpoint(
            endpoint_id="deepseek-official",
            display_name="DeepSeek Official",
            protocol="openai_compatible",
            base_url="https://api.deepseek.com",
            provider_kind="official",
        ),
        "ark": ProviderEndpoint(
            endpoint_id="ark-official",
            display_name="Ark Official",
            protocol="ark_runtime",
            base_url="https://ark.cn-beijing.volces.com/api/v3",
            provider_kind="official",
        ),
    }

    claude = llm_router._official_catalog_capabilities(
        endpoints["claude"],
        "claude-opus-4-8-20260501",
    )
    assert claude["input_modalities"] == ["text", "image", "pdf"]
    assert claude["max_input_tokens"] == 1_048_576
    assert claude["max_output_tokens"] == 128_000
    assert "https://docs.anthropic.com/en/docs/build-with-claude/pdf-support" in claude[
        "input_modalities_source_urls"
    ]

    openai = llm_router._official_catalog_capabilities(endpoints["openai"], "gpt-5")
    assert openai["input_modalities"] == ["text", "image", "file"]
    assert openai["max_input_tokens_source"] == "provider_doc"
    assert openai["max_output_tokens"] == 128_000
    assert "https://developers.openai.com/api/docs/models" in openai[
        "max_input_tokens_source_urls"
    ]
    openai_pro = llm_router._official_catalog_capabilities(endpoints["openai"], "gpt-5-pro")
    assert openai_pro["max_input_tokens"] == 400_000
    assert openai_pro["max_output_tokens"] == 272_000
    assert "https://developers.openai.com/api/docs/models/gpt-5-pro" in openai_pro[
        "max_output_tokens_source_urls"
    ]
    openai_54 = llm_router._official_catalog_capabilities(endpoints["openai"], "gpt-5.4")
    assert openai_54["max_input_tokens"] == 1_050_000
    assert openai_54["max_output_tokens"] == 128_000

    gemini = llm_router._official_catalog_capabilities(
        endpoints["gemini"],
        "gemini-3.1-pro-preview",
        {"inputTokenLimit": 1_048_576, "outputTokenLimit": 65_536},
    )
    assert gemini["max_input_tokens"] == 1_048_576
    assert gemini["max_input_tokens_source"] == "api_list"
    assert gemini["max_input_tokens_source_urls"] == ["https://ai.google.dev/api/models"]

    deepseek = llm_router._official_catalog_capabilities(
        endpoints["deepseek"],
        "deepseek-reasoner",
    )
    assert deepseek["max_input_tokens"] == 1_048_576
    assert deepseek["max_output_tokens"] == 393_216
    assert "https://api-docs.deepseek.com/quick_start/pricing" in deepseek[
        "max_output_tokens_source_urls"
    ]

    ark = llm_router._official_catalog_capabilities(
        endpoints["ark"],
        "doubao-seed-2-0-pro-260215",
        {
            "modalities": {
                "input_modalities": ["text", "image"],
                "output_modalities": ["text"],
            },
            "token_limits": {
                "context_window": 1_000_000,
                "max_output_token_length": 32_768,
            },
        },
    )
    assert ark["input_modalities"] == ["text", "image"]
    assert ark["input_modalities_source"] == "api_list"
    assert "https://www.volcengine.com/docs/82379/1330310" in ark[
        "input_modalities_source_urls"
    ]
    assert ark["max_input_tokens"] == 1_000_000


def test_openai_reasoning_candidates_escalate_effort_for_unknown_models() -> None:
    endpoint = ProviderEndpoint(
        endpoint_id="openai-official",
        display_name="OpenAI Official",
        protocol="openai_compatible",
        base_url="https://api.openai.com/v1",
        provider_kind="official",
    )

    candidates = llm_router._official_language_probe_candidates(endpoint, "gpt-5.9-new")
    response_efforts = [
        candidate.runtime_settings.get("reasoning", {}).get("effort")
        for candidate in candidates
        if candidate.profile_id.startswith("reasoning:openai_responses")
    ]

    assert response_efforts == ["low", "medium", "high"]


def test_openai_gpt5_pro_candidates_use_high_reasoning_directly() -> None:
    endpoint = ProviderEndpoint(
        endpoint_id="openai-official",
        display_name="OpenAI Official",
        protocol="openai_compatible",
        base_url="https://api.openai.com/v1",
        provider_kind="official",
    )

    candidates = llm_router._official_language_probe_candidates(endpoint, "gpt-5-pro-2025-10-06")
    efforts = [
        candidate.runtime_settings.get("reasoning", {}).get("effort")
        for candidate in candidates
        if candidate.capability == "reasoning"
    ]

    assert efforts == ["high"]


@pytest.mark.anyio
async def test_openai_reasoning_probe_stops_effort_escalation_after_success(
    monkeypatch,
) -> None:
    endpoint = ProviderEndpoint(
        endpoint_id="openai-official",
        display_name="OpenAI Official",
        protocol="openai_compatible",
        base_url="https://api.openai.com/v1",
        api_key="secret",
        provider_kind="official",
    )
    attempts: list[str | None] = []

    async def fake_probe(
        _endpoint: ProviderEndpoint,
        model_id: str,
        candidate: llm_router.OfficialLanguageProbeCandidate,
    ) -> ModelProbeResult:
        if candidate.capability != "reasoning":
            return ModelProbeResult(model_id=model_id, status="ok", latency_ms=1)
        effort = candidate.runtime_settings.get("reasoning", {}).get("effort")
        attempts.append(effort if isinstance(effort, str) else None)
        if effort == "medium":
            return ModelProbeResult(model_id=model_id, status="ok", latency_ms=2)
        return ModelProbeResult(
            model_id=model_id,
            status="invalid_model",
            latency_ms=1,
            message=f"{effort} unsupported",
        )

    monkeypatch.setattr(llm_router, "_probe_official_call_method", fake_probe)

    result = await llm_router._probe_official_model_profile_result(endpoint, "gpt-5.9-new")

    assert attempts == ["low", "medium"]
    reasoning_profiles = [profile for profile in result.profiles if profile.capability == "reasoning"]
    assert [profile.runtime_overrides["reasoning"]["effort"] for profile in reasoning_profiles] == [
        "medium"
    ]


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
        "historical_ready": 0,
        "untested": 1,
        "cooling_down": 0,
        "off": 1,
        "failed": 2,
    }
    provider_models = {option["route_id"]: option for option in model_group["provider_models"]}
    assert provider_models["ready-provider:gpt-5"]["ui_state"] == "ready"
    assert provider_models["untested-provider:gpt-5"]["ui_state"] == "untested"
    # Missing credential now converges to the canonical failed/missing_config (was needs_setup).
    assert provider_models["missing-key-provider:gpt-5"]["ui_state"] == "failed"
    assert provider_models["failed-provider:gpt-5"]["ui_state"] == "failed"
    assert provider_models["disabled-provider:gpt-5"]["ui_state"] == "off"
    assert provider_models["ready-provider:gpt-5"]["endpoint_id"] == "ready-provider"
    assert provider_models["ready-provider:gpt-5"]["provider_kind"] == "third_party"
    assert provider_models["ready-provider:gpt-5"]["capability_state"] == "unknown"


def test_registry_and_role_materialization_use_credentials_evidence_refs_for_historical_ready(
    client: TestClient,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import app.core.adapters.gateway as gateway_module

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
                    status="unverified_manual",
                    evidence=[
                        EvidenceRecord(
                            evidence_id="probe-openai-gpt5",
                            evidence_type="probe",
                            trust_state="probe-verified",
                            endpoint_id="openai-direct",
                            route_id="openai-direct:gpt-5",
                            model_id="gpt-5",
                            provider_model_id="gpt-5",
                            probe_status="ok",
                        )
                    ],
                )
            },
        ),
        active_credentials_path,
    )
    role = RoleEntry(
        model_groups=[
            RoleModelGroup(
                canonical_id="gpt-5",
                display_name="GPT-5",
                provider_models=[{"route_id": "openai-direct:gpt-5"}],
            )
        ]
    )
    save_roles_file(
        roles_path,
        RolesData(roles={"assistant": role}),
        known_route_ids={"openai-direct:gpt-5"},
    )

    registry_response = client.get("/api/llm/registry")

    assert registry_response.status_code == 200
    model_group = registry_response.json()["model_groups"][0]
    provider_model = model_group["provider_models"][0]
    assert provider_model["ui_state"] == "historical_ready"
    assert model_group["status_summary"]["historical_ready"] == 1
    assert model_group["status_summary"]["untested"] == 0

    captured: dict[str, object] = {}

    def _spy(request: object) -> SimpleNamespace:
        captured["has_evidence_records"] = hasattr(request, "evidence_records")
        return SimpleNamespace(
            fallback_chain=[RoleRouteEntry(route_id="openai-direct:gpt-5")],
            materialization_report={
                "entries": [{"route_id": "openai-direct:gpt-5", "role_fit": "using"}],
                "warnings": [],
                "skipped_provider_details": [],
            },
        )

    monkeypatch.setattr(gateway_module, "gateway_materialize_role", _spy, raising=False)

    role_response = client.get("/api/llm/roles/assistant")

    assert role_response.status_code == 200
    assert captured["has_evidence_records"] is False


def test_registry_model_group_exposes_thinking_capability_from_verified_profile(
    client: TestClient,
    tmp_path: Path,
    monkeypatch,
) -> None:
    _seed(tmp_path, monkeypatch)
    credentials = LLMCredentialsFile(
        provider_endpoints={
            "anthropic-official": ProviderEndpoint(
                endpoint_id="anthropic-official",
                display_name="Anthropic Official",
                protocol="anthropic_compatible",
                base_url="https://api.anthropic.example",
                api_key="secret",
                status="verified",
                provider_kind="official",
            )
        },
        provider_routes={
            "anthropic-official:claude-haiku": ProviderRoute(
                route_id="anthropic-official:claude-haiku",
                endpoint_id="anthropic-official",
                route_slug="claude-haiku",
                provider_model_id="claude-haiku",
                canonical_id="claude-haiku",
                display_name="Claude Haiku",
                status="verified",
                verified_profiles=[
                    VerifiedProfile(
                        profile_id="thinking:anthropic_messages:manual",
                        capability="thinking",
                        method_id="anthropic_messages",
                        request_mapper_id="anthropic_thinking_manual_budget",
                        status="ready",
                        default=True,
                        fallback_rank=1,
                    )
                ],
            )
        },
    )
    save_credentials(credentials, credentials_path())

    response = client.get("/api/llm/registry")

    assert response.status_code == 200
    provider_model = response.json()["model_groups"][0]["provider_models"][0]
    assert provider_model["route_id"] == "anthropic-official:claude-haiku"
    assert provider_model["capability_state"] == "known"
    assert provider_model["capabilities"]["thinking_protocol"] == {
        "value": True,
        "source": "probed_verified",
        "observed_at": None,
        "message": None,
    }


def test_registry_model_groups_include_unverified_language_routes_not_multimodal_candidates(
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
            "openai-official": ProviderEndpoint(
                endpoint_id="openai-official",
                display_name="OpenAI Official",
                protocol="openai_compatible",
                base_url="https://api.openai.com/v1",
                api_key="secret",
                status="verified",
                provider_kind="official",
            )
        },
        provider_routes={
            "openai-official:gpt-5": ProviderRoute(
                route_id="openai-official:gpt-5",
                endpoint_id="openai-official",
                route_slug="gpt-5",
                provider_model_id="gpt-5",
                canonical_id="gpt-5",
                display_name="GPT-5",
                status="unverified_manual",
                verified_profiles=[],
                capabilities={
                    "model_type": CapabilityValue(
                        value="language_reasoning",
                        source="provider_doc",
                    ),
                    "capability_family": CapabilityValue(
                        value="language_reasoning",
                        source="provider_doc",
                    ),
                    "input_modalities": CapabilityValue(
                        value=["text"],
                        source="provider_doc",
                    ),
                    "output_modalities": CapabilityValue(
                        value=["text"],
                        source="provider_doc",
                    ),
                },
            ),
            "openai-official:gpt-image-1": ProviderRoute(
                route_id="openai-official:gpt-image-1",
                endpoint_id="openai-official",
                route_slug="gpt-image-1",
                provider_model_id="gpt-image-1",
                canonical_id="gpt-image-1",
                display_name="GPT Image 1",
                status="unverified_manual",
                verified_profiles=[],
                capabilities={
                    "model_type": CapabilityValue(
                        value="image_generation",
                        source="provider_doc",
                    ),
                    "capability_family": CapabilityValue(
                        value="image_generation",
                        source="provider_doc",
                    ),
                    "input_modalities": CapabilityValue(
                        value=["text", "image"],
                        source="provider_doc",
                    ),
                    "output_modalities": CapabilityValue(
                        value=["image"],
                        source="provider_doc",
                    ),
                },
            )
        },
    )
    save_credentials(credentials, active_credentials_path)
    save_roles_file(roles_path, RolesData(), known_route_ids=set(credentials.provider_routes))

    response = client.get("/api/llm/registry")

    assert response.status_code == 200
    model_groups = response.json()["model_groups"]
    assert len(model_groups) == 1
    assert model_groups[0]["canonical_id"] == "gpt-5"
    assert [option["route_id"] for option in model_groups[0]["provider_models"]] == [
        "openai-official:gpt-5"
    ]
    provider_model = model_groups[0]["provider_models"][0]
    assert provider_model["ui_state"] == "untested"
    assert provider_model["model_type"] == "language_reasoning"
    assert provider_model["capability_family"] == "language_reasoning"
    assert "text" in provider_model["input_modalities"]
    assert provider_model["output_modalities"] == ["text"]


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
            verified_profiles=[
                VerifiedProfile(
                    profile_id="text:anthropic_messages",
                    capability="text_chat",
                    method_id="anthropic_messages",
                    request_mapper_id="anthropic_text",
                    status="ready",
                )
            ],
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


def test_registry_collapses_model_channel_suffixes_into_provider_routes(
    client: TestClient,
    tmp_path: Path,
    monkeypatch,
) -> None:
    settings_dir = tmp_path / "settings"
    monkeypatch.setattr(config, "APP_SETTINGS_DIR", settings_dir)
    active_credentials_path = settings_dir / "llm" / "llm_credentials.json"
    roles_path = settings_dir / "llm" / "llm_roles.yaml"

    endpoints = {
        "ark-official": ProviderEndpoint(
            endpoint_id="ark-official",
            display_name="Ark Official",
            protocol="ark_runtime",
            base_url="https://ark.example/api/v3",
            api_key="secret",
            status="verified",
            provider_kind="official",
        ),
        "openrouter": ProviderEndpoint(
            endpoint_id="openrouter",
            display_name="OpenRouter",
            protocol="openai_compatible",
            base_url="https://openrouter.example/api/v1",
            api_key="secret",
            status="verified",
            provider_kind="third_party",
        ),
        "qiniu-anthropic": ProviderEndpoint(
            endpoint_id="qiniu-anthropic",
            display_name="Qiniu-Anthropic",
            protocol="anthropic_compatible",
            base_url="https://qiniu.example/anthropic",
            api_key="secret",
            status="verified",
            provider_kind="third_party",
        ),
    }
    text_profile = VerifiedProfile(
        profile_id="text:chat",
        capability="text_chat",
        method_id="ark_chat",
        request_mapper_id="ark_chat_text",
        status="ready",
    )
    routes = {
        "openrouter:deepseek.deepseek-v3.2": ProviderRoute(
            route_id="openrouter:deepseek.deepseek-v3.2",
            endpoint_id="openrouter",
            route_slug="deepseek.deepseek-v3.2",
            provider_model_id="deepseek/deepseek-v3.2",
            canonical_id="deepseek.deepseek-v3.2",
            display_name="DeepSeek V3.2",
            status="verified",
        ),
        "ark-official:deepseek-v3-2-251201": ProviderRoute(
            route_id="ark-official:deepseek-v3-2-251201",
            endpoint_id="ark-official",
            route_slug="deepseek-v3-2-251201",
            provider_model_id="deepseek-v3-2-251201",
            canonical_id="deepseek-v3-2-251201",
            display_name="DeepSeek V3.2 251201",
            status="verified",
            verified_profiles=[text_profile],
        ),
        "openrouter:deepseek.deepseek-v3.2-exp": ProviderRoute(
            route_id="openrouter:deepseek.deepseek-v3.2-exp",
            endpoint_id="openrouter",
            route_slug="deepseek.deepseek-v3.2-exp",
            provider_model_id="deepseek/deepseek-v3.2-exp",
            canonical_id="deepseek.deepseek-v3.2-exp",
            display_name="DeepSeek V3.2 Exp",
            status="verified",
        ),
        "qiniu-anthropic:deepseek.deepseek-v3.2-exp-thinking": ProviderRoute(
            route_id="qiniu-anthropic:deepseek.deepseek-v3.2-exp-thinking",
            endpoint_id="qiniu-anthropic",
            route_slug="deepseek.deepseek-v3.2-exp-thinking",
            provider_model_id="deepseek/deepseek-v3.2-exp-thinking",
            canonical_id="deepseek.deepseek-v3.2-exp-thinking",
            display_name="DeepSeek V3.2 Exp Thinking",
            status="verified",
        ),
        "openrouter:deepseek.deepseek-v3.2-speciale": ProviderRoute(
            route_id="openrouter:deepseek.deepseek-v3.2-speciale",
            endpoint_id="openrouter",
            route_slug="deepseek.deepseek-v3.2-speciale",
            provider_model_id="deepseek/deepseek-v3.2-speciale",
            canonical_id="deepseek.deepseek-v3.2-speciale",
            display_name="DeepSeek V3.2 Speciale",
            status="verified",
        ),
        "qiniu-anthropic:deepseek.deepseek-v3.2-speciale-or": ProviderRoute(
            route_id="qiniu-anthropic:deepseek.deepseek-v3.2-speciale-or",
            endpoint_id="qiniu-anthropic",
            route_slug="deepseek.deepseek-v3.2-speciale-or",
            provider_model_id="deepseek/deepseek-v3.2-speciale-or",
            canonical_id="deepseek.deepseek-v3.2-speciale-or",
            display_name="DeepSeek V3.2 Speciale Or",
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
    groups = {group["display_name"]: group for group in response.json()["model_groups"]}
    assert "DeepSeek V3.2 251201" not in groups
    assert "DeepSeek V3.2 Exp Thinking" not in groups
    assert "DeepSeek V3.2 Speciale Or" not in groups
    assert {
        option["route_id"]
        for option in groups["DeepSeek V3.2"]["provider_models"]
    } == {
        "openrouter:deepseek.deepseek-v3.2",
        "ark-official:deepseek-v3-2-251201",
    }
    exp_options = {
        option["route_id"]: option
        for option in groups["DeepSeek V3.2 Exp"]["provider_models"]
    }
    assert set(exp_options) == {
        "openrouter:deepseek.deepseek-v3.2-exp",
        "qiniu-anthropic:deepseek.deepseek-v3.2-exp-thinking",
    }
    assert exp_options[
        "qiniu-anthropic:deepseek.deepseek-v3.2-exp-thinking"
    ]["capabilities"]["thinking_protocol"]["value"] is True
    assert groups["DeepSeek V3.2 Exp"]["capability_summary"]["thinking"] == "mixed"
    assert {
        option["route_id"]
        for option in groups["DeepSeek V3.2 Speciale"]["provider_models"]
    } == {
        "openrouter:deepseek.deepseek-v3.2-speciale",
        "qiniu-anthropic:deepseek.deepseek-v3.2-speciale-or",
    }


def test_registry_groups_release_aliases_by_projected_model_identity(
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
        "ark-official": ProviderEndpoint(
            endpoint_id="ark-official",
            display_name="Ark Official",
            protocol="ark_runtime",
            base_url="https://ark.example/api/v3",
            api_key="secret",
            status="verified",
            provider_kind="official",
        ),
        "openrouter": ProviderEndpoint(
            endpoint_id="openrouter",
            display_name="OpenRouter",
            protocol="openai_compatible",
            base_url="https://openrouter.example/api/v1",
            api_key="secret",
            status="verified",
            provider_kind="third_party",
        ),
    }
    ready_profile = VerifiedProfile(
        profile_id="text:chat",
        capability="text_chat",
        method_id="chat",
        request_mapper_id="chat_text",
        status="ready",
    )
    routes = {
        "openrouter:anthropic.claude-haiku-4-5": ProviderRoute(
            route_id="openrouter:anthropic.claude-haiku-4-5",
            endpoint_id="openrouter",
            route_slug="anthropic.claude-haiku-4-5",
            provider_model_id="anthropic/claude-haiku-4-5",
            canonical_id="anthropic.claude-haiku-4-5",
            display_name="Claude Haiku 4.5",
            status="verified",
        ),
        "anthropic-official:claude-haiku-4-5-20251001": ProviderRoute(
            route_id="anthropic-official:claude-haiku-4-5-20251001",
            endpoint_id="anthropic-official",
            route_slug="claude-haiku-4-5-20251001",
            provider_model_id="claude-haiku-4-5-20251001",
            canonical_id="claude-haiku-4-5-20251001",
            display_name="Claude Haiku 4.5 20251001",
            status="verified",
            verified_profiles=[ready_profile],
        ),
        "openrouter:deepseek.deepseek-v4-flash": ProviderRoute(
            route_id="openrouter:deepseek.deepseek-v4-flash",
            endpoint_id="openrouter",
            route_slug="deepseek.deepseek-v4-flash",
            provider_model_id="deepseek/deepseek-v4-flash",
            canonical_id="deepseek.deepseek-v4-flash",
            display_name="DeepSeek V4 Flash",
            status="verified",
        ),
        "ark-official:deepseek-v4-flash-260425": ProviderRoute(
            route_id="ark-official:deepseek-v4-flash-260425",
            endpoint_id="ark-official",
            route_slug="deepseek-v4-flash-260425",
            provider_model_id="deepseek-v4-flash-260425",
            canonical_id="deepseek-v4-flash-260425",
            display_name="DeepSeek V4 Flash 260425",
            status="verified",
            verified_profiles=[ready_profile],
        ),
        "openrouter:deepseek.deepseek-v4-flash-free": ProviderRoute(
            route_id="openrouter:deepseek.deepseek-v4-flash-free",
            endpoint_id="openrouter",
            route_slug="deepseek.deepseek-v4-flash-free",
            provider_model_id="deepseek/deepseek-v4-flash:free",
            canonical_id="deepseek.deepseek-v4-flash:free",
            display_name="DeepSeek V4 Flash Free",
            status="verified",
        ),
        "openrouter:deepseek.deepseek-v3": ProviderRoute(
            route_id="openrouter:deepseek.deepseek-v3",
            endpoint_id="openrouter",
            route_slug="deepseek.deepseek-v3",
            provider_model_id="deepseek/deepseek-v3",
            canonical_id="deepseek.deepseek-v3",
            display_name="DeepSeek V3",
            status="verified",
        ),
        "openrouter:deepseek.deepseek-v3-0324": ProviderRoute(
            route_id="openrouter:deepseek.deepseek-v3-0324",
            endpoint_id="openrouter",
            route_slug="deepseek.deepseek-v3-0324",
            provider_model_id="deepseek/deepseek-v3-0324",
            canonical_id="deepseek.deepseek-v3-0324",
            display_name="DeepSeek V3 0324",
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
    groups = {group["display_name"]: group for group in response.json()["model_groups"]}
    assert "Claude Haiku 4.5 20251001" not in groups
    assert "DeepSeek V4 Flash 260425" not in groups
    assert "DeepSeek V4 Flash Free" not in groups
    assert "DeepSeek V3 0324" not in groups
    assert {
        option["route_id"]
        for option in groups["Claude Haiku 4.5"]["provider_models"]
    } == {
        "openrouter:anthropic.claude-haiku-4-5",
        "anthropic-official:claude-haiku-4-5-20251001",
    }
    assert {
        option["route_id"]
        for option in groups["DeepSeek V4 Flash"]["provider_models"]
    } == {
        "openrouter:deepseek.deepseek-v4-flash",
        "ark-official:deepseek-v4-flash-260425",
        "openrouter:deepseek.deepseek-v4-flash-free",
    }
    assert {
        option["route_id"]
        for option in groups["DeepSeek V3"]["provider_models"]
    } == {
        "openrouter:deepseek.deepseek-v3",
        "openrouter:deepseek.deepseek-v3-0324",
    }


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


def test_registry_stamps_route_retry_at_on_cooling_down_route(
    client: TestClient,
    tmp_path: Path,
    monkeypatch,
) -> None:
    # W2-A / Part D status normalization: the route's normalized state must carry
    # ``retry_at`` alongside ``reason_code`` for a cooling_down route, so the frontend
    # can read it straight off the route (symmetric with reason_code) instead of only
    # via the aggregated provider_models view. The projection stamps it from the active
    # circuit; ``_gateway_route`` strips it from the gateway runtime route.
    _seed(tmp_path, monkeypatch)
    retry_at = datetime.now(UTC) + timedelta(seconds=60)
    _open_runtime_circuit(
        route_id="openai-direct:gpt-5",
        retry_at=retry_at,
        reason_code="rate_limited",
        message="provider returned 429",
    )

    routes = client.get("/api/llm/registry").json()["provider_routes"]

    assert routes["openai-direct:gpt-5"]["ui_state"] == "cooling_down"
    assert routes["openai-direct:gpt-5"]["reason_code"] == "rate_limited"
    assert routes["openai-direct:gpt-5"]["retry_at"] == retry_at.isoformat()


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


def test_endpoint_test_third_party_runs_inference_probe_to_verify(
    client: TestClient,
    tmp_path: Path,
    monkeypatch,
) -> None:
    # apikeys#25: a third-party endpoint Test discovers models via get-models,
    # then runs a real generation probe (protocol auto-detect + batch inference)
    # and only reaches `verified` when a generation probe actually succeeds.
    _seed(tmp_path, monkeypatch)
    endpoint_calls: list[ProviderEndpoint] = []
    route_calls: list[ProviderRoute] = []

    async def fake_test_endpoint(endpoint: ProviderEndpoint) -> EndpointProbeResult:
        endpoint_calls.append(endpoint)
        return _endpoint_probe_ok(endpoint, latency_ms=42, model_ids=("gpt-5", "gpt-5-mini"))

    async def fake_test_route(
        endpoint: ProviderEndpoint,
        route: ProviderRoute,
        *,
        runtime_settings: dict[str, object] | None = None,
    ) -> RouteProbeResult:
        route_calls.append(route)
        return _route_probe(endpoint, route, status="ok", latency_ms=21)

    monkeypatch.setattr(llm_router, "_gateway_test_provider_endpoint", fake_test_endpoint)
    monkeypatch.setattr(llm_router, "_gateway_test_provider_route", fake_test_route)

    response = client.post("/api/llm/endpoints/openai-direct/test")

    assert response.status_code == 200
    body = response.json()
    assert body["tested_endpoint_id"] == "openai-direct"
    assert body["discovered_model_count"] == 2
    endpoint = body["registry"]["provider_endpoints"]["openai-direct"]
    assert endpoint["status"] == "verified"
    assert "Generation verified" in endpoint["last_test_message"]
    assert "gpt-5" in endpoint["last_test_message"]
    routes = body["registry"]["provider_routes"]
    assert routes["openai-direct:gpt-5"]["status"] == "verified"
    assert routes["openai-direct:gpt-5"]["display_name"] == "GPT-5"
    assert routes["openai-direct:gpt-5-mini"]["provider_model_id"] == "gpt-5-mini"
    assert routes["openai-direct:gpt-5-mini"]["route_slug"] == "gpt-5-mini"
    # the endpoint is tested once; the first probed model (gpt-5) verified, so the
    # batch loop stops there and gpt-5-mini is never probed.
    assert [e.endpoint_id for e in endpoint_calls] == ["openai-direct"]
    assert [r.provider_model_id for r in route_calls] == ["gpt-5"]


def test_endpoint_test_third_party_failed_inference_probe_stays_failed(
    client: TestClient,
    tmp_path: Path,
    monkeypatch,
) -> None:
    # apikeys#25: get-models reachability alone never reaches verified for a
    # third-party endpoint that was NEVER verified before — if no model generates
    # and there is no prior verified route to fall back on, it stays failed.
    settings_dir = tmp_path / "settings"
    monkeypatch.setattr(config, "APP_SETTINGS_DIR", settings_dir)
    save_credentials(
        LLMCredentialsFile(
            provider_endpoints={
                "oai-fresh": ProviderEndpoint(
                    endpoint_id="oai-fresh",
                    display_name="Fresh OpenAI",
                    protocol="openai_compatible",
                    base_url="https://api.openai.example/v1",
                    api_key="secret",
                )
            },
        ),
        credentials_path(),
    )

    async def fake_test_endpoint(endpoint: ProviderEndpoint) -> EndpointProbeResult:
        return _endpoint_probe_ok(endpoint, latency_ms=42, model_ids=("gpt-5", "gpt-5-mini"))

    async def fake_test_route(
        endpoint: ProviderEndpoint,
        route: ProviderRoute,
        *,
        runtime_settings: dict[str, object] | None = None,
    ) -> RouteProbeResult:
        return _route_probe(
            endpoint,
            route,
            status="invalid_model",
            message="generation failed for endpoint protocol/base_url combination",
        )

    monkeypatch.setattr(llm_router, "_gateway_test_provider_endpoint", fake_test_endpoint)
    monkeypatch.setattr(llm_router, "_gateway_test_provider_route", fake_test_route)

    response = client.post("/api/llm/endpoints/oai-fresh/test")

    assert response.status_code == 200
    body = response.json()
    endpoint = body["registry"]["provider_endpoints"]["oai-fresh"]
    assert endpoint["status"] == "failed"


def test_endpoint_test_third_party_no_models_does_not_guess_notable_models(
    client: TestClient,
    tmp_path: Path,
    monkeypatch,
) -> None:
    # W2-D / R-E1: when get-models returns an EMPTY list and the endpoint has no
    # known routes, the Test must NOT fall back to doc-maintained notable model
    # ids (e.g. o3-mini) and probe a guessed phantom model. get-models reaching
    # the provider already proves key+URL connectivity, so with no real model to
    # verify, the endpoint stays reachable-but-untested (the user manually probes
    # a model id) and must NOT regress to "failed" on a guessed model.
    settings_dir = tmp_path / "settings"
    monkeypatch.setattr(config, "APP_SETTINGS_DIR", settings_dir)
    save_credentials(
        LLMCredentialsFile(
            provider_endpoints={
                "oai-empty": ProviderEndpoint(
                    endpoint_id="oai-empty",
                    display_name="Empty-list OpenAI",
                    protocol="openai_compatible",
                    base_url="https://api.openai.example/v1",
                    api_key="secret",
                )
            },
        ),
        credentials_path(),
    )

    async def fake_test_endpoint(endpoint: ProviderEndpoint) -> EndpointProbeResult:
        # Reachable + authenticated, but the provider lists no models.
        return _endpoint_probe_ok(endpoint, latency_ms=42)

    route_calls: list[ProviderRoute] = []

    async def fake_test_route(
        endpoint: ProviderEndpoint,
        route: ProviderRoute,
        *,
        runtime_settings: dict[str, object] | None = None,
    ) -> RouteProbeResult:
        route_calls.append(route)
        return _route_probe(
            endpoint,
            route,
            status="invalid_model",
            message="The model does not exist or you do not have access to it.",
        )

    monkeypatch.setattr(llm_router, "_gateway_test_provider_endpoint", fake_test_endpoint)
    monkeypatch.setattr(llm_router, "_gateway_test_provider_route", fake_test_route)

    response = client.post("/api/llm/endpoints/oai-empty/test")

    assert response.status_code == 200
    body = response.json()
    endpoint = body["registry"]["provider_endpoints"]["oai-empty"]
    # No guessed-notable model was probed.
    assert [r.provider_model_id for r in route_calls] == []
    # Reachable but unverifiable-without-a-model => untested, NOT failed.
    assert endpoint["status"] != "failed"
    assert endpoint["status"] == "unverified_manual"
    # W2-D.4: structured "no model" reason so the UI can warn + suggest manual test.
    assert endpoint["last_error_code"] == "no_model_available"


def test_endpoint_test_third_party_retains_verified_when_reachable_and_previously_verified(
    client: TestClient,
    tmp_path: Path,
    monkeypatch,
) -> None:
    # apikeys: an endpoint Test only needs to prove the *endpoint* connects. When
    # get-models proves the key+URL are live AND the endpoint already has a
    # verified route, a round where every catalog model probe fails (flaky /
    # phantom upstream models) must NOT regress the endpoint to failed — it keeps
    # its verified status by reusing the previously verified model.
    _seed(tmp_path, monkeypatch)  # seeds a verified openai-direct:gpt-5 route

    async def fake_test_endpoint(endpoint: ProviderEndpoint) -> EndpointProbeResult:
        return _endpoint_probe_ok(endpoint, latency_ms=42, model_ids=("gpt-5", "gpt-5-mini"))

    async def fake_test_route(
        endpoint: ProviderEndpoint,
        route: ProviderRoute,
        *,
        runtime_settings: dict[str, object] | None = None,
    ) -> RouteProbeResult:
        return _route_probe(
            endpoint,
            route,
            status="invalid_model",
            message="generation failed for endpoint protocol/base_url combination",
        )

    monkeypatch.setattr(llm_router, "_gateway_test_provider_endpoint", fake_test_endpoint)
    monkeypatch.setattr(llm_router, "_gateway_test_provider_route", fake_test_route)

    response = client.post("/api/llm/endpoints/openai-direct/test")

    assert response.status_code == 200
    body = response.json()
    endpoint = body["registry"]["provider_endpoints"]["openai-direct"]
    assert endpoint["status"] == "verified"
    assert "previously verified" in endpoint["last_test_message"].lower()
    # the previously verified route must remain verified
    routes = body["registry"]["provider_routes"]
    assert routes["openai-direct:gpt-5"]["status"] == "verified"


def test_endpoint_test_third_party_auto_detects_protocol_and_persists_it(
    client: TestClient,
    tmp_path: Path,
    monkeypatch,
) -> None:
    # apikeys#25: the third-party Test rotates candidate protocols (cloning the
    # endpoint per candidate) until a generation probe is accepted, then persists
    # the detected protocol on the endpoint — the user never hand-picks it.
    settings_dir = tmp_path / "settings"
    monkeypatch.setattr(config, "APP_SETTINGS_DIR", settings_dir)
    save_credentials(
        LLMCredentialsFile(
            provider_endpoints={
                "mystery": ProviderEndpoint(
                    endpoint_id="mystery",
                    display_name="Mystery",
                    # Stored protocol is wrong; auto-detect must rotate to anthropic.
                    protocol="openai_compatible",
                    base_url="https://anthropic.mystery.example/v1",
                    api_key="secret",
                )
            },
        ),
        credentials_path(),
    )
    probed_backends: list[str] = []

    async def fake_test_endpoint(endpoint: ProviderEndpoint) -> EndpointProbeResult:
        return _endpoint_probe_ok(endpoint, latency_ms=42, model_ids=("claude-x",))

    async def fake_test_route(
        endpoint: ProviderEndpoint,
        route: ProviderRoute,
        *,
        runtime_settings: dict[str, object] | None = None,
    ) -> RouteProbeResult:
        # Protocol rotation clones the endpoint per candidate, so the endpoint's
        # backend identifies the transport being tried.
        backend = llm_router._endpoint_probe_backend(endpoint)
        probed_backends.append(backend)
        # Only the anthropic (claude) transport is accepted by this endpoint.
        if backend == "claude":
            return _route_probe(endpoint, route, status="ok", latency_ms=21)
        return _route_probe(endpoint, route, status="error", message="protocol mismatch")

    monkeypatch.setattr(llm_router, "_gateway_test_provider_endpoint", fake_test_endpoint)
    monkeypatch.setattr(llm_router, "_gateway_test_provider_route", fake_test_route)

    response = client.post("/api/llm/endpoints/mystery/test")

    assert response.status_code == 200
    body = response.json()
    endpoint = body["registry"]["provider_endpoints"]["mystery"]
    assert endpoint["status"] == "verified"
    # Detected protocol persisted (openai was tried first and rejected, claude won).
    assert endpoint["protocol"] == "anthropic_compatible"
    assert "openai" in probed_backends and "claude" in probed_backends


def test_endpoint_test_third_party_invalid_key_short_circuits_protocol_detect(
    client: TestClient,
    tmp_path: Path,
    monkeypatch,
) -> None:
    # apikeys#25: a structural error (invalid_key) cannot be fixed by rotating the
    # protocol, so the auto-detect loop stops after the first candidate instead of
    # burning a probe per protocol.
    _seed(tmp_path, monkeypatch)
    probe_count = {"n": 0}

    async def fake_test_endpoint(endpoint: ProviderEndpoint) -> EndpointProbeResult:
        return _endpoint_probe_ok(endpoint, latency_ms=42, model_ids=("gpt-5",))

    async def fake_test_route(
        endpoint: ProviderEndpoint,
        route: ProviderRoute,
        *,
        runtime_settings: dict[str, object] | None = None,
    ) -> RouteProbeResult:
        probe_count["n"] += 1
        return _route_probe(endpoint, route, status="invalid_key", message="bad key")

    monkeypatch.setattr(llm_router, "_gateway_test_provider_endpoint", fake_test_endpoint)
    monkeypatch.setattr(llm_router, "_gateway_test_provider_route", fake_test_route)

    response = client.post("/api/llm/endpoints/openai-direct/test")

    assert response.status_code == 200
    endpoint = response.json()["registry"]["provider_endpoints"]["openai-direct"]
    assert endpoint["status"] == "failed"
    # Only the first candidate protocol was probed; invalid_key short-circuited.
    assert probe_count["n"] == 1


def test_third_party_models_test_capabilities_come_from_list_models_not_hardcoded(
    client: TestClient,
    tmp_path: Path,
    monkeypatch,
) -> None:
    # apikeys#27: the third-party manual-model probe derives route capabilities
    # from the endpoint's list-models rich fields (symmetric with the official
    # side), not the old hard-coded text-only default.
    _seed(tmp_path, monkeypatch)

    async def fake_gateway_test_provider_endpoint(
        endpoint: ProviderEndpoint,
    ) -> EndpointProbeResult:
        return EndpointProbeResult(
            endpoint_id=endpoint.endpoint_id,
            provider_kind=endpoint.provider_kind,
            backend="openai",
            base_url="https://api.openai.example/v1",
            status="ok",
            latency_ms=42,
            model_ids=("vision-pro",),
            model_capabilities={
                "vision-pro": {
                    "input_modalities": ["text", "image"],
                    "output_modalities": ["text"],
                }
            },
        )

    async def fake_test_route(
        endpoint: ProviderEndpoint,
        route: ProviderRoute,
        *,
        runtime_settings: dict[str, object] | None = None,
    ) -> RouteProbeResult:
        return _route_probe(endpoint, route, status="ok", latency_ms=33)

    monkeypatch.setattr(
        llm_router,
        "_gateway_test_provider_endpoint",
        fake_gateway_test_provider_endpoint,
        raising=False,
    )
    monkeypatch.setattr(llm_router, "_gateway_test_provider_route", fake_test_route)

    response = client.post(
        "/api/llm/endpoints/openai-direct/models/test",
        json={"model_ids": ["vision-pro"]},
    )

    assert response.status_code == 200
    body = response.json()
    route = body["registry"]["provider_routes"]["openai-direct:vision-pro"]
    assert route["status"] == "verified"
    # image input came from list-models rich fields — NOT the text-only hardcode.
    assert route["capabilities"]["input_modalities"]["value"] == ["text", "image"]


def test_endpoint_test_preserves_route_evidence_and_projects_historical_ready(
    client: TestClient,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # No backward compat (catalog draft promote retired): blue historical_ready comes
    # ONLY from probe-verified evidence embedded ON the route (SSOT). A re-run official
    # endpoint Test (get-models) must PRESERVE that route.evidence and keep projecting
    # historical_ready from route.evidence alone (no parallel probe-catalog store).
    settings_dir = tmp_path / "settings"
    monkeypatch.setattr(config, "APP_SETTINGS_DIR", settings_dir)
    save_credentials(
        LLMCredentialsFile(
            provider_endpoints={
                "openai-official": ProviderEndpoint(
                    endpoint_id="openai-official",
                    display_name="OpenAI",
                    protocol="openai_compatible",
                    base_url="https://api.openai.example/v1",
                    api_key="secret",
                    provider_kind="official",
                )
            },
            provider_routes={
                "openai-official:gpt-5": ProviderRoute(
                    route_id="openai-official:gpt-5",
                    endpoint_id="openai-official",
                    route_slug="gpt-5",
                    provider_model_id="gpt-5",
                    canonical_id="gpt-5",
                    display_name="GPT-5",
                    status="unverified_manual",
                    evidence=[
                        EvidenceRecord(
                            evidence_id="probe-openai-gpt5",
                            evidence_type="probe",
                            trust_state="probe-verified",
                            endpoint_id="openai-official",
                            route_id="openai-official:gpt-5",
                            model_id="gpt-5",
                            provider_model_id="gpt-5",
                            probe_status="ok",
                        )
                    ],
                )
            },
        ),
        credentials_path(),
    )

    async def fake_gateway_test_provider_endpoint(
        endpoint: ProviderEndpoint,
    ) -> EndpointProbeResult:
        return EndpointProbeResult(
            endpoint_id=endpoint.endpoint_id,
            provider_kind=endpoint.provider_kind,
            backend="openai",
            base_url=endpoint.base_url,
            status="ok",
            latency_ms=42,
            model_ids=("gpt-5",),
            model_capabilities={"gpt-5": {}},
        )

    async def fake_test_route(
        endpoint: ProviderEndpoint,
        route: ProviderRoute,
        *,
        runtime_settings: dict[str, object] | None = None,
    ) -> RouteProbeResult:
        return _route_probe(endpoint, route, status="ok", latency_ms=21)

    monkeypatch.setattr(
        llm_router,
        "_gateway_test_provider_endpoint",
        fake_gateway_test_provider_endpoint,
        raising=False,
    )
    monkeypatch.setattr(llm_router, "_gateway_test_provider_route", fake_test_route)

    response = client.post("/api/llm/endpoints/openai-official/test")

    assert response.status_code == 200
    route = response.json()["registry"]["provider_routes"]["openai-official:gpt-5"]
    assert route["status"] == "unverified_manual"
    assert route["ui_state"] == "historical_ready"
    # Evidence survived the re-run Test (SSOT); the probe catalog stays untouched.
    persisted = load_credentials(credentials_path())
    persisted_route = persisted.provider_routes["openai-official:gpt-5"]
    assert "probe-verified" in [e.trust_state for e in persisted_route.evidence]
    assert all(e.trust_state == "probe-verified" for e in persisted_route.evidence)

def test_third_party_probe_model_ids_fall_back_to_draft_known_models(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings_dir = tmp_path / "settings"
    monkeypatch.setattr(config, "APP_SETTINGS_DIR", settings_dir)
    endpoint = ProviderEndpoint(
        endpoint_id="openai-direct",
        display_name="OpenAI",
        protocol="openai_compatible",
        base_url="https://api.openai.example/v1",
        api_key="secret",
    )
    # With no discovered models, the candidate fallback is the endpoint's KNOWN
    # routes (model-list truth = routes, R3.4) — derived from credentials, not catalog.
    save_credentials(
        LLMCredentialsFile(
            provider_endpoints={"openai-direct": endpoint},
            provider_routes={
                "openai-direct:draft-known-model": ProviderRoute(
                    route_id="openai-direct:draft-known-model",
                    endpoint_id="openai-direct",
                    route_slug="draft-known-model",
                    provider_model_id="draft-known-model",
                    canonical_id="draft-known-model",
                    status="unverified_manual",
                )
            },
        ),
        credentials_path(),
    )

    assert llm_router._endpoint_generation_probe_model_ids(endpoint, ()) == ["draft-known-model"]


def test_third_party_probe_model_ids_leads_with_verified_then_unknown_then_failed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # apikeys: an endpoint Test proves the *endpoint* connects with the fewest
    # attempts, so it must LEAD with a model that connected before (known-ok),
    # then untried models, then known-failed last. It must NOT skip the known-good
    # model — skipping it forces the probe onto flaky/phantom catalog models.
    settings_dir = tmp_path / "settings"
    monkeypatch.setattr(config, "APP_SETTINGS_DIR", settings_dir)
    endpoint = ProviderEndpoint(
        endpoint_id="openai-direct",
        display_name="OpenAI",
        protocol="openai_compatible",
        base_url="https://api.openai.example/v1",
        api_key="secret",
    )
    # Routes carry their own probe history (SSOT): known-ok has probe-verified
    # evidence (historical/blue), known-fail has probe-failed evidence.
    save_credentials(
        LLMCredentialsFile(
            provider_endpoints={"openai-direct": endpoint},
            provider_routes={
                "openai-direct:known-ok": ProviderRoute(
                    route_id="openai-direct:known-ok",
                    endpoint_id="openai-direct",
                    route_slug="known-ok",
                    provider_model_id="known-ok",
                    canonical_id="known-ok",
                    status="unverified_manual",
                    evidence=[
                        EvidenceRecord(
                            evidence_id="probe-known-ok",
                            evidence_type="probe",
                            trust_state="probe-verified",
                            endpoint_id="openai-direct",
                            model_id="known-ok",
                            provider_model_id="known-ok",
                        )
                    ],
                ),
                "openai-direct:known-fail": ProviderRoute(
                    route_id="openai-direct:known-fail",
                    endpoint_id="openai-direct",
                    route_slug="known-fail",
                    provider_model_id="known-fail",
                    canonical_id="known-fail",
                    status="unverified_manual",
                    evidence=[
                        EvidenceRecord(
                            evidence_id="probe-known-fail",
                            evidence_type="probe",
                            trust_state="probe-failed",
                            endpoint_id="openai-direct",
                            model_id="known-fail",
                            provider_model_id="known-fail",
                        )
                    ],
                ),
            },
        ),
        credentials_path(),
    )

    model_ids = llm_router._endpoint_generation_probe_model_ids(
        endpoint,
        ("known-fail", "fresh", "known-ok"),
    )

    assert model_ids == ["known-ok", "fresh", "known-fail"]


def test_third_party_probe_model_ids_puts_currently_verified_routes_first(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # apikeys: a model with a currently-verified route (green) is the surest bet,
    # so it leads ahead of a model that merely connected in the past (blue).
    settings_dir = tmp_path / "settings"
    monkeypatch.setattr(config, "APP_SETTINGS_DIR", settings_dir)
    endpoint = ProviderEndpoint(
        endpoint_id="openai-direct",
        display_name="OpenAI",
        protocol="openai_compatible",
        base_url="https://api.openai.example/v1",
        api_key="secret",
    )
    # Both models connected before (historical / blue), but only green-ok has a
    # currently-verified route (green) — derived from route.status — so it leads.
    save_credentials(
        LLMCredentialsFile(
            provider_endpoints={"openai-direct": endpoint},
            provider_routes={
                "openai-direct:green-ok": ProviderRoute(
                    route_id="openai-direct:green-ok",
                    endpoint_id="openai-direct",
                    route_slug="green-ok",
                    provider_model_id="green-ok",
                    canonical_id="green-ok",
                    status="verified",
                ),
                "openai-direct:hist-ok": ProviderRoute(
                    route_id="openai-direct:hist-ok",
                    endpoint_id="openai-direct",
                    route_slug="hist-ok",
                    provider_model_id="hist-ok",
                    canonical_id="hist-ok",
                    status="unverified_manual",
                    evidence=[
                        EvidenceRecord(
                            evidence_id="probe-hist-ok",
                            evidence_type="probe",
                            trust_state="probe-verified",
                            endpoint_id="openai-direct",
                            model_id="hist-ok",
                            provider_model_id="hist-ok",
                        )
                    ],
                ),
            },
        ),
        credentials_path(),
    )

    model_ids = llm_router._endpoint_generation_probe_model_ids(
        endpoint,
        ("hist-ok", "green-ok"),
    )

    assert model_ids == ["green-ok", "hist-ok"]


def test_endpoint_test_reprobes_all_listed_models(
    client: TestClient,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _seed(tmp_path, monkeypatch)

    async def fake_gateway_test_provider_endpoint(
        endpoint: ProviderEndpoint,
    ) -> EndpointProbeResult:
        return EndpointProbeResult(
            endpoint_id=endpoint.endpoint_id,
            provider_kind=endpoint.provider_kind,
            backend="openai",
            base_url=endpoint.base_url,
            status="ok",
            latency_ms=42,
            model_ids=("known-ok",),
        )

    async def fake_gateway_test_provider_route(
        endpoint: ProviderEndpoint,
        route: ProviderRoute,
        *,
        runtime_settings: dict[str, object] | None = None,
    ) -> RouteProbeResult:
        del runtime_settings
        return RouteProbeResult(
            endpoint_id=endpoint.endpoint_id,
            route_id=route.route_id,
            provider_kind=endpoint.provider_kind,
            backend="openai",
            base_url=endpoint.base_url,
            model_id=route.provider_model_id,
            status="ok",
            latency_ms=33,
        )

    monkeypatch.setattr(
        llm_router,
        "_gateway_test_provider_endpoint",
        fake_gateway_test_provider_endpoint,
        raising=False,
    )
    monkeypatch.setattr(
        llm_router,
        "_gateway_test_provider_route",
        fake_gateway_test_provider_route,
        raising=False,
    )

    response = client.post("/api/llm/endpoints/openai-direct/test")

    assert response.status_code == 200
    endpoint = response.json()["registry"]["provider_endpoints"]["openai-direct"]
    assert endpoint["status"] == "verified"
    assert endpoint["last_test_message"] != "Endpoint reachable but no model ids were available to probe."
    assert "known-ok" in endpoint["last_test_message"]


def test_registry_response_projects_six_state_ui_state_onto_routes(
    client: TestClient,
    tmp_path: Path,
    monkeypatch,
) -> None:
    # apikeys#30: the registry snapshot stamps each route's 6-state ui_state so the
    # API Keys cards render the authoritative state inline.
    settings_dir = tmp_path / "settings"
    monkeypatch.setattr(config, "APP_SETTINGS_DIR", settings_dir)
    save_credentials(
        LLMCredentialsFile(
            provider_endpoints={
                "ready-ep": ProviderEndpoint(
                    endpoint_id="ready-ep",
                    display_name="Ready",
                    protocol="openai_compatible",
                    base_url="https://api.ready.example/v1",
                    api_key="secret",
                    status="verified",
                ),
                "nokey-ep": ProviderEndpoint(
                    endpoint_id="nokey-ep",
                    display_name="No Key",
                    protocol="openai_compatible",
                    base_url="https://api.nokey.example/v1",
                    status="unverified_manual",
                ),
            },
            provider_routes={
                "ready-ep:gpt-5": ProviderRoute(
                    route_id="ready-ep:gpt-5",
                    endpoint_id="ready-ep",
                    route_slug="gpt-5",
                    provider_model_id="gpt-5",
                    canonical_id="gpt-5",
                    status="verified",
                ),
                "nokey-ep:gpt-5": ProviderRoute(
                    route_id="nokey-ep:gpt-5",
                    endpoint_id="nokey-ep",
                    route_slug="gpt-5",
                    provider_model_id="gpt-5",
                    canonical_id="gpt-5",
                    status="unverified_manual",
                ),
            },
        ),
        credentials_path(),
    )

    response = client.get("/api/llm/registry")

    assert response.status_code == 200
    routes = response.json()["provider_routes"]
    # verified endpoint + verified route -> ready (green).
    assert routes["ready-ep:gpt-5"]["ui_state"] == "ready"
    # endpoint with no credential -> failed (missing config).
    assert routes["nokey-ep:gpt-5"]["ui_state"] == "failed"


def test_endpoint_test_delegates_unified_provider_probe_to_gateway(
    client: TestClient,
    tmp_path: Path,
    monkeypatch,
) -> None:
    _seed(tmp_path, monkeypatch)
    gateway_calls: list[str] = []

    async def fake_gateway_test_provider_endpoint(
        endpoint: ProviderEndpoint,
    ) -> EndpointProbeResult:
        gateway_calls.append(endpoint.endpoint_id)
        return EndpointProbeResult(
            endpoint_id=endpoint.endpoint_id,
            provider_kind=endpoint.provider_kind,
            backend="openai",
            base_url="https://api.openai.example/v1",
            status="ok",
            latency_ms=42,
            model_ids=("gpt-5",),
        )

    monkeypatch.setattr(
        llm_router,
        "_gateway_test_provider_endpoint",
        fake_gateway_test_provider_endpoint,
        raising=False,
    )

    response = client.post("/api/llm/endpoints/openai-direct/test")

    assert response.status_code == 200
    assert gateway_calls == ["openai-direct"]
    body = response.json()
    assert body["tested_endpoint_id"] == "openai-direct"
    assert body["discovered_model_count"] == 1


def test_endpoint_test_third_party_probes_discovered_models_after_models_list(
    client: TestClient,
    tmp_path: Path,
    monkeypatch,
) -> None:
    # apikeys#25: after get-models discovers ids, the third-party Test runs a real
    # inference probe over the discovered models (get-models proves only key+URL
    # reachability, not that the endpoint can actually generate).
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
    model_list_calls: list[ProviderEndpoint] = []
    model_probe_calls: list[ProviderRoute] = []

    async def fake_test_endpoint(endpoint: ProviderEndpoint) -> EndpointProbeResult:
        model_list_calls.append(endpoint)
        return _endpoint_probe_ok(endpoint, latency_ms=42, model_ids=("claude-qiniu",))

    async def fake_test_route(
        endpoint: ProviderEndpoint,
        route: ProviderRoute,
        *,
        runtime_settings: dict[str, object] | None = None,
    ) -> RouteProbeResult:
        model_probe_calls.append(route)
        return _route_probe(endpoint, route, status="ok", latency_ms=21)

    monkeypatch.setattr(llm_router, "_gateway_test_provider_endpoint", fake_test_endpoint)
    monkeypatch.setattr(llm_router, "_gateway_test_provider_route", fake_test_route)

    response = client.post("/api/llm/endpoints/qiniu/test")

    assert response.status_code == 200
    body = response.json()
    endpoint = body["registry"]["provider_endpoints"]["qiniu"]
    # One list-models against the endpoint's base_url, one generation probe of the
    # discovered model — backend/key resolution is now the gateway's job.
    assert [e.base_url for e in model_list_calls] == ["https://anthropic.qnaigc.com/v1"]
    assert [r.provider_model_id for r in model_probe_calls] == ["claude-qiniu"]
    assert endpoint["status"] == "verified"
    assert "Generation verified" in endpoint["last_test_message"]
    assert body["discovered_model_count"] == 1
    routes = body["registry"]["provider_routes"]
    assert routes["qiniu:claude-qiniu"]["status"] == "verified"


def test_third_party_protocol_auto_detect_excludes_ark_runtime() -> None:
    assert llm_router._THIRD_PARTY_PROTOCOL_CANDIDATES == (
        "openai_compatible",
        "anthropic_compatible",
        "google_genai",
    )


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
    endpoint_calls: list[ProviderEndpoint] = []

    async def fake_test_endpoint(endpoint: ProviderEndpoint) -> EndpointProbeResult:
        endpoint_calls.append(endpoint)
        return _endpoint_probe_ok(endpoint, latency_ms=42, model_ids=("claude-qiniu",))

    async def fake_probe_official_call_method(endpoint, model_id: str, candidate):
        del endpoint, candidate
        return ModelProbeResult(model_id=model_id, status="ok", latency_ms=21)

    monkeypatch.setattr(llm_router, "_gateway_test_provider_endpoint", fake_test_endpoint)
    monkeypatch.setattr(llm_router, "_probe_official_call_method", fake_probe_official_call_method)

    response = client.post("/api/llm/endpoints/qiniu/test")

    assert response.status_code == 200
    # The endpoint's declared anthropic protocol (→ claude backend) and base_url are
    # used for the probe; backend/key resolution is the gateway's job.
    assert [llm_router._endpoint_probe_backend(e) for e in endpoint_calls] == ["claude"]
    assert [e.base_url for e in endpoint_calls] == ["https://anthropic.qnaigc.com/v1"]
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

    async def fake_test_route(
        endpoint: ProviderEndpoint,
        route: ProviderRoute,
        *,
        runtime_settings: dict[str, object] | None = None,
    ) -> RouteProbeResult:
        return _route_probe(endpoint, route, status="ok", latency_ms=21)

    monkeypatch.setattr(gateway_provider_probe, "_request_models", fake_request_models)
    monkeypatch.setattr(llm_router, "_gateway_test_provider_route", fake_test_route)

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
    endpoint_calls: list[ProviderEndpoint] = []

    async def fake_test_endpoint(endpoint: ProviderEndpoint) -> EndpointProbeResult:
        endpoint_calls.append(endpoint)
        return _endpoint_probe_ok(endpoint, latency_ms=42, model_ids=("ep-20260316142940-b74bm",))

    async def fake_probe_official_call_method(endpoint, model_id: str, candidate):
        del endpoint, candidate
        return ModelProbeResult(model_id=model_id, status="ok", latency_ms=21)

    async def fake_test_route(
        endpoint: ProviderEndpoint,
        route: ProviderRoute,
        *,
        runtime_settings: dict[str, object] | None = None,
    ) -> RouteProbeResult:
        return _route_probe(endpoint, route, status="ok", latency_ms=21)

    monkeypatch.setattr(llm_router, "_gateway_test_provider_endpoint", fake_test_endpoint)
    monkeypatch.setattr(llm_router, "_probe_official_call_method", fake_probe_official_call_method)
    monkeypatch.setattr(llm_router, "_gateway_test_provider_route", fake_test_route)

    response = client.post("/api/llm/endpoints/ark-official/test")

    assert response.status_code == 200
    # The ark_runtime endpoint (→ ark backend) and its base_url drive the probe.
    assert [llm_router._endpoint_probe_backend(e) for e in endpoint_calls] == ["ark"]
    assert [e.base_url for e in endpoint_calls] == ["https://ark.cn-beijing.volces.com/api/v3"]
    assert "ark-official:ep-20260316142940-b74bm" in response.json()["registry"]["provider_routes"]


def test_endpoint_test_ark_official_verifies_via_generation_probe_not_profile_probe(
    client: TestClient,
    tmp_path: Path,
    monkeypatch,
) -> None:
    # apikeys#24 (revised 2026-07-01): official endpoints verify via ONE minimal
    # generation probe; the heavy per-model official call-method probes stay out
    # of the endpoint-level Test.
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

    async def fake_test_endpoint(endpoint: ProviderEndpoint) -> EndpointProbeResult:
        assert llm_router._endpoint_probe_backend(endpoint) == "ark"
        assert endpoint.base_url == "https://ark.cn-beijing.volces.com/api/v3"
        return _endpoint_probe_ok(
            endpoint,
            latency_ms=42,
            model_ids=(
                "doubao-lite-128k-240428",
                "doubao-seed-2-0-pro-260215",
            ),
        )

    async def fake_probe_official_call_method(endpoint, model_id: str, candidate):
        del endpoint, model_id, candidate
        raise AssertionError("Provider-level Test must not profile-probe catalog models.")

    route_calls: list[ProviderRoute] = []

    async def fake_test_route(
        endpoint: ProviderEndpoint,
        route: ProviderRoute,
        *,
        runtime_settings: dict[str, object] | None = None,
    ) -> RouteProbeResult:
        route_calls.append(route)
        return _route_probe(endpoint, route, status="ok", latency_ms=21)

    monkeypatch.setattr(llm_router, "_gateway_test_provider_endpoint", fake_test_endpoint)
    monkeypatch.setattr(llm_router, "_probe_official_call_method", fake_probe_official_call_method)
    monkeypatch.setattr(llm_router, "_gateway_test_provider_route", fake_test_route)

    response = client.post("/api/llm/endpoints/ark-official/test")

    assert response.status_code == 200
    body = response.json()
    endpoint = body["registry"]["provider_endpoints"]["ark-official"]
    assert endpoint["status"] == "verified"
    assert "Generation verified" in endpoint["last_test_message"]
    # One minimal generation probe verified the endpoint; the batch stops there.
    assert len(route_calls) == 1
    routes = body["registry"]["provider_routes"]
    assert routes["ark-official:doubao-seed-2-0-pro-260215"]["status"] == "unverified_manual"
    assert routes["ark-official:doubao-seed-2-0-pro-260215"]["verified_profiles"] == []
    assert routes["ark-official:doubao-lite-128k-240428"]["status"] == "unverified_manual"
    # model-list dissolves into routes (R3.4): no provider-list-observed evidence.

def test_endpoint_test_preserves_existing_routes_and_adds_discovered_models(
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

    async def fake_test_endpoint(endpoint: ProviderEndpoint) -> EndpointProbeResult:
        return _endpoint_probe_ok(endpoint, latency_ms=42, model_ids=("new-anthropic-model",))

    async def fake_test_route(
        endpoint: ProviderEndpoint,
        route: ProviderRoute,
        *,
        runtime_settings: dict[str, object] | None = None,
    ) -> RouteProbeResult:
        return _route_probe(endpoint, route, status="ok", latency_ms=21)

    monkeypatch.setattr(llm_router, "_gateway_test_provider_endpoint", fake_test_endpoint)
    monkeypatch.setattr(llm_router, "_gateway_test_provider_route", fake_test_route)

    response = client.post("/api/llm/endpoints/qiniu/test")

    assert response.status_code == 200
    routes = response.json()["registry"]["provider_routes"]
    assert routes["qiniu:old-openai-model"]["provider_model_id"] == "old-openai-model"
    assert routes["qiniu:new-anthropic-model"]["provider_model_id"] == "new-anthropic-model"
    assert routes["other:gpt-5"]["provider_model_id"] == "gpt-5"


def test_endpoint_test_rejects_invalid_api_key(
    client: TestClient,
    tmp_path: Path,
    monkeypatch,
) -> None:
    _seed(tmp_path, monkeypatch)

    async def fake_test_endpoint(endpoint: ProviderEndpoint) -> EndpointProbeResult:
        return _endpoint_probe(
            endpoint,
            status="invalid_key",
            message="bad key",
            error_code="invalid_api_key",
        )

    monkeypatch.setattr(llm_router, "_gateway_test_provider_endpoint", fake_test_endpoint)

    response = client.post("/api/llm/endpoints/openai-direct/test")

    assert response.status_code == 200
    body = response.json()
    endpoint = body["registry"]["provider_endpoints"]["openai-direct"]
    assert body["tested_endpoint_id"] == "openai-direct"
    assert body["discovered_model_count"] == 0
    # R-E2: an invalid API key makes the endpoint unusable => disabled (not a
    # transient "failed"), and its routes are disabled too (cascade).
    assert endpoint["status"] == "disabled"
    assert "Invalid API key" in endpoint["last_test_message"]
    assert "invalid_api_key" in endpoint["last_test_message"]
    # W2-B.3: the STRUCTURED error code is persisted so the frontend reads it directly.
    assert endpoint["last_error_code"] == "invalid_api_key"
    assert body["registry"]["provider_routes"]["openai-direct:gpt-5"]["status"] == "disabled"


def test_endpoint_test_invalid_key_disable_revives_on_successful_retest(
    client: TestClient,
    tmp_path: Path,
    monkeypatch,
) -> None:
    # R-E2: an invalid key disables the endpoint + its routes, but that is NOT a
    # terminal lock — fixing the key and re-testing successfully revives them.
    _seed(tmp_path, monkeypatch)

    async def bad_key(endpoint: ProviderEndpoint) -> EndpointProbeResult:
        return _endpoint_probe(
            endpoint,
            status="invalid_key",
            message="bad key",
            error_code="invalid_api_key",
        )

    monkeypatch.setattr(llm_router, "_gateway_test_provider_endpoint", bad_key)
    first = client.post("/api/llm/endpoints/openai-direct/test")
    assert first.status_code == 200
    first_body = first.json()
    assert first_body["registry"]["provider_endpoints"]["openai-direct"]["status"] == "disabled"
    assert first_body["registry"]["provider_routes"]["openai-direct:gpt-5"]["status"] == "disabled"

    async def good_key(endpoint: ProviderEndpoint) -> EndpointProbeResult:
        return _endpoint_probe_ok(endpoint, latency_ms=42, model_ids=("gpt-5",))

    async def ok_probe(
        endpoint: ProviderEndpoint,
        route: ProviderRoute,
        *,
        runtime_settings: dict[str, object] | None = None,
    ) -> RouteProbeResult:
        return _route_probe(endpoint, route, status="ok", latency_ms=21)

    monkeypatch.setattr(llm_router, "_gateway_test_provider_endpoint", good_key)
    monkeypatch.setattr(llm_router, "_gateway_test_provider_route", ok_probe)
    second = client.post("/api/llm/endpoints/openai-direct/test")
    assert second.status_code == 200
    second_body = second.json()
    assert second_body["registry"]["provider_endpoints"]["openai-direct"]["status"] == "verified"
    # the previously-disabled route is revived (here re-verified via the probe).
    assert second_body["registry"]["provider_routes"]["openai-direct:gpt-5"]["status"] == "verified"


def test_endpoint_test_logs_discovered_models_and_reachability(
    client: TestClient,
    tmp_path: Path,
    monkeypatch,
) -> None:
    # W2-E diagnostics: the endpoint_test runtime-activity record carries the actual
    # discovered model ids and whether get-models reached the provider — not just a
    # count — so General settings can show what the Test actually saw.
    from app.services.runtime_activity import load_runtime_activity

    _seed(tmp_path, monkeypatch)

    async def fake_test_endpoint(endpoint: ProviderEndpoint) -> EndpointProbeResult:
        return _endpoint_probe_ok(endpoint, latency_ms=42, model_ids=("gpt-5", "gpt-5-mini"))

    async def fake_test_route(
        endpoint: ProviderEndpoint,
        route: ProviderRoute,
        *,
        runtime_settings: dict[str, object] | None = None,
    ) -> RouteProbeResult:
        return _route_probe(endpoint, route, status="ok", latency_ms=21)

    monkeypatch.setattr(llm_router, "_gateway_test_provider_endpoint", fake_test_endpoint)
    monkeypatch.setattr(llm_router, "_gateway_test_provider_route", fake_test_route)

    assert client.post("/api/llm/endpoints/openai-direct/test").status_code == 200

    records = load_runtime_activity(source_id="llm_credentials", limit=50)
    test_rec = next(r for r in records if r["action"] == "endpoint_test")
    assert test_rec["changes"]["reachable"] is True
    assert test_rec["changes"]["discovered_model_ids"] == ["gpt-5", "gpt-5-mini"]


def test_endpoint_test_logs_probe_attempts(
    client: TestClient,
    tmp_path: Path,
    monkeypatch,
) -> None:
    # W2-E.1b: the endpoint_test record lists every protocol×model generation probe
    # attempted and its status, so the user can see what the Test actually exercised.
    from app.services.runtime_activity import load_runtime_activity

    _seed(tmp_path, monkeypatch)

    async def fake_test_endpoint(endpoint: ProviderEndpoint) -> EndpointProbeResult:
        return _endpoint_probe_ok(endpoint, latency_ms=42, model_ids=("gpt-5", "gpt-5-mini"))

    async def fake_test_route(
        endpoint: ProviderEndpoint,
        route: ProviderRoute,
        *,
        runtime_settings: dict[str, object] | None = None,
    ) -> RouteProbeResult:
        return _route_probe(endpoint, route, status="ok", latency_ms=21)

    monkeypatch.setattr(llm_router, "_gateway_test_provider_endpoint", fake_test_endpoint)
    monkeypatch.setattr(llm_router, "_gateway_test_provider_route", fake_test_route)

    assert client.post("/api/llm/endpoints/openai-direct/test").status_code == 200

    records = load_runtime_activity(source_id="llm_credentials", limit=50)
    test_rec = next(r for r in records if r["action"] == "endpoint_test")
    attempts = test_rec["changes"]["probe_attempts"]
    assert isinstance(attempts, list) and len(attempts) >= 1
    assert any(
        a["model"] == "gpt-5" and a["status"] == "ok" and a["protocol"] == "openai_compatible"
        for a in attempts
    )


def test_official_endpoint_test_verifies_via_one_generation_probe(
    client: TestClient,
    tmp_path: Path,
    monkeypatch,
) -> None:
    # apikeys#24 (revised 2026-07-01): a reachable official endpoint can still be
    # unable to generate (an exhausted credit balance keeps get-models working),
    # so verified now requires ONE minimal generation probe on a language model —
    # never the heavy per-model profile probes, and never non-language models.
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
            provider_routes={
                "openai-official:gpt-5-old": ProviderRoute(
                    route_id="openai-official:gpt-5-old",
                    endpoint_id="openai-official",
                    route_slug="gpt-5-old",
                    provider_model_id="gpt-5-old",
                    canonical_id="gpt-5-old",
                    status="verified",
                    verified_profiles=[
                        VerifiedProfile(
                            profile_id="text_responses",
                            capability="text_chat",
                            method_id="openai_responses",
                            request_mapper_id="openai_responses_text",
                            status="ready",
                            default=True,
                            fallback_rank=1,
                        )
                    ],
                )
            },
        ),
        credentials_path(),
    )

    async def fake_test_endpoint(endpoint: ProviderEndpoint) -> EndpointProbeResult:
        assert llm_router._endpoint_probe_backend(endpoint) == "openai"
        assert endpoint.base_url == "https://api.openai.com/v1"
        return _endpoint_probe_ok(
            endpoint,
            latency_ms=42,
            model_ids=("gpt-5", "gpt-image-1"),
            model_capabilities={
                "gpt-5": {
                    "id": "gpt-5",
                    "max_context_tokens": 400_000,
                    "max_output_tokens": 128_000,
                },
                "gpt-image-1": {
                    "id": "gpt-image-1",
                    "max_output_tokens": 4_096,
                },
            },
        )

    async def fail_profile_probe(endpoint, model_id: str):
        del endpoint, model_id
        raise AssertionError("Provider-level Test must not profile-probe every model.")

    route_calls: list[ProviderRoute] = []

    async def fake_test_route(
        endpoint: ProviderEndpoint,
        route: ProviderRoute,
        *,
        runtime_settings: dict[str, object] | None = None,
    ) -> RouteProbeResult:
        route_calls.append(route)
        return _route_probe(endpoint, route, status="ok", latency_ms=21)

    monkeypatch.setattr(llm_router, "_gateway_test_provider_endpoint", fake_test_endpoint)
    monkeypatch.setattr(llm_router, "_gateway_test_provider_route", fake_test_route)
    monkeypatch.setattr(
        llm_router,
        "_probe_official_model_profile_result",
        fail_profile_probe,
    )

    response = client.post("/api/llm/endpoints/openai-official/test")

    assert response.status_code == 200
    body = response.json()
    endpoint = body["registry"]["provider_endpoints"]["openai-official"]
    assert endpoint["status"] == "verified"
    assert "Generation verified" in endpoint["last_test_message"]
    # Exactly one generation probe ran, on a language model — gpt-image-1 is not
    # a text-generation candidate.
    assert [r.provider_model_id for r in route_calls] == ["gpt-5"]
    routes = body["registry"]["provider_routes"]
    assert list(routes) == [
        "openai-official:gpt-5-old",
        "openai-official:gpt-5",
        "openai-official:gpt-image-1",
    ]
    route = routes["openai-official:gpt-5"]
    # Official route status/profiles stay owned by the per-model profile probes;
    # the endpoint test only records generation evidence on the probed route.
    assert route["status"] == "unverified_manual"
    assert route["verified_profiles"] == []
    assert route["capabilities"]["model_type"]["value"] == "language_reasoning"
    assert route["capabilities"]["max_input_tokens"]["value"] == 400000
    image_route = routes["openai-official:gpt-image-1"]
    assert image_route["status"] == "unverified_manual"
    assert image_route["verified_profiles"] == []
    assert image_route["capabilities"]["model_type"]["value"] == "image_generation"
    # model-list dissolves into routes (R3.4): the discovered models ARE the routes
    # asserted above; no provider-list-observed evidence is written.


def test_official_endpoint_test_billing_failure_fails_endpoint(
    client: TestClient,
    tmp_path: Path,
    monkeypatch,
) -> None:
    # The user-facing gap this revision closes: an Anthropic account with an
    # exhausted credit balance still lists models (old design => "verified"),
    # but every generation call fails. The endpoint Test must surface that as a
    # structural failure — even when a previously verified route exists.
    settings_dir = tmp_path / "settings"
    monkeypatch.setattr(config, "APP_SETTINGS_DIR", settings_dir)
    save_credentials(
        LLMCredentialsFile(
            provider_endpoints={
                "anthropic-official": ProviderEndpoint(
                    endpoint_id="anthropic-official",
                    display_name="Anthropic Official",
                    protocol="anthropic_compatible",
                    base_url="https://api.anthropic.com",
                    api_key="secret",
                    provider_kind="official",
                )
            },
            provider_routes={
                "anthropic-official:claude-opus-4.8": ProviderRoute(
                    route_id="anthropic-official:claude-opus-4.8",
                    endpoint_id="anthropic-official",
                    route_slug="claude-opus-4.8",
                    provider_model_id="claude-opus-4.8",
                    canonical_id="claude-opus-4.8",
                    status="verified",
                )
            },
        ),
        credentials_path(),
    )
    billing_message = (
        "Provider returned HTTP 400 (invalid_request_error). Your credit balance is "
        "too low to access the Anthropic API."
    )
    route_calls: list[ProviderRoute] = []

    async def fake_test_endpoint(endpoint: ProviderEndpoint) -> EndpointProbeResult:
        return _endpoint_probe_ok(
            endpoint,
            latency_ms=42,
            model_ids=("claude-opus-4.8", "claude-fable-5"),
        )

    async def fake_test_route(
        endpoint: ProviderEndpoint,
        route: ProviderRoute,
        *,
        runtime_settings: dict[str, object] | None = None,
    ) -> RouteProbeResult:
        route_calls.append(route)
        return _route_probe(endpoint, route, status="quota_exceeded", message=billing_message)

    monkeypatch.setattr(llm_router, "_gateway_test_provider_endpoint", fake_test_endpoint)
    monkeypatch.setattr(llm_router, "_gateway_test_provider_route", fake_test_route)

    response = client.post("/api/llm/endpoints/anthropic-official/test")

    assert response.status_code == 200
    body = response.json()
    endpoint = body["registry"]["provider_endpoints"]["anthropic-official"]
    # Structural failure: no reuse of the previously verified route.
    assert endpoint["status"] == "failed"
    assert "credit balance" in endpoint["last_test_message"]
    # quota_exceeded short-circuits the batch after the first probe.
    assert len(route_calls) == 1

def test_official_profile_probe_skips_reasoning_fallback_methods_after_success(
    monkeypatch,
) -> None:
    endpoint = ProviderEndpoint(
        endpoint_id="openai-official",
        display_name="OpenAI Official",
        protocol="openai_compatible",
        base_url="https://api.openai.com/v1",
        api_key="secret",
        provider_kind="official",
    )
    calls: list[tuple[str, str]] = []

    async def fake_probe_official_call_method(endpoint, model_id: str, candidate):
        del endpoint
        calls.append((model_id, candidate.method_id))
        if candidate.method_id == "openai_chat_completions":
            return ModelProbeResult(model_id=model_id, status="ok", latency_ms=12)
        if candidate.request_mapper_id == "openai_responses_reasoning":
            return ModelProbeResult(model_id=model_id, status="ok", latency_ms=15)
        return ModelProbeResult(
            model_id=model_id,
            status="invalid_model",
            message="wrong API family",
        )

    monkeypatch.setattr(
        llm_router,
        "_probe_official_call_method",
        fake_probe_official_call_method,
    )

    profiles = asyncio.run(llm_router._probe_official_model_profiles(endpoint, "gpt-5.2"))

    assert calls == [
        ("gpt-5.2", "openai_responses"),
        ("gpt-5.2", "openai_chat_completions"),
        ("gpt-5.2", "openai_responses"),
    ]
    assert [
        (profile.capability, profile.method_id, profile.request_mapper_id, profile.default)
        for profile in profiles
    ] == [
        ("text_chat", "openai_chat_completions", "openai_chat_completions_text", False),
        ("reasoning", "openai_responses", "openai_responses_reasoning", True),
    ]


def test_official_profile_probe_keeps_per_method_failure_attempts(monkeypatch) -> None:
    endpoint = ProviderEndpoint(
        endpoint_id="openai-official",
        display_name="OpenAI Official",
        protocol="openai_compatible",
        base_url="https://api.openai.com/v1",
        api_key="secret",
        provider_kind="official",
    )

    async def fake_probe_official_call_method(endpoint, model_id: str, candidate):
        del endpoint
        return ModelProbeResult(
            model_id=model_id,
            status="invalid_model",
            latency_ms=7,
            message=f"{candidate.request_mapper_id} rejected",
        )

    monkeypatch.setattr(
        llm_router,
        "_probe_official_call_method",
        fake_probe_official_call_method,
    )

    result = asyncio.run(
        llm_router._probe_official_model_profile_result(endpoint, "gpt-5.2")
    )

    assert result.profiles == []
    assert result.last_probe_message == (
        "Endpoint model probe failed (invalid_model). openai_responses_text rejected"
    )
    assert result.probe_attempts[0] == {
        "profile_id": "text:openai_responses",
        "capability": "text_chat",
        "method_id": "openai_responses",
        "request_mapper_id": "openai_responses_text",
        "status": "invalid_model",
        "latency_ms": 7,
        "message": "Endpoint model probe failed (invalid_model). openai_responses_text rejected",
        "input_modalities": ["text"],
        "output_modalities": ["text"],
        "runtime_overrides": {"max_output_tokens": 16},
    }


def test_official_probe_candidates_cover_all_current_official_providers() -> None:
    cases = [
        (
            ProviderEndpoint(
                endpoint_id="anthropic-official",
                display_name="Anthropic Official",
                protocol="anthropic_compatible",
                base_url="https://api.anthropic.com",
                api_key="secret",
                provider_kind="official",
            ),
            "claude-opus-4-7",
            {"anthropic_messages"},
        ),
        (
            ProviderEndpoint(
                endpoint_id="gemini-official",
                display_name="Gemini Official",
                protocol="google_genai",
                base_url="https://generativelanguage.googleapis.com",
                api_key="secret",
                provider_kind="official",
            ),
            "gemini-3.1-pro-preview",
            {"gemini_generate_content"},
        ),
        (
            ProviderEndpoint(
                endpoint_id="deepseek-official",
                display_name="DeepSeek Official",
                protocol="openai_compatible",
                base_url="https://api.deepseek.com",
                api_key="secret",
                provider_kind="official",
            ),
            "deepseek-v4-pro",
            {"deepseek_chat_completions", "deepseek_anthropic_messages"},
        ),
        (
            ProviderEndpoint(
                endpoint_id="ark-official",
                display_name="Ark Official",
                protocol="ark_runtime",
                base_url="https://ark.cn-beijing.volces.com/api/v3",
                api_key="secret",
                provider_kind="official",
            ),
            "doubao-seed-2-0-pro-260215",
            {"ark_chat", "ark_responses", "ark_anthropic_messages"},
        ),
    ]

    for endpoint, model_id, expected_methods in cases:
        candidates = llm_router._official_language_probe_candidates(endpoint, model_id)
        assert {candidate.method_id for candidate in candidates} >= expected_methods


def test_openai_instruct_models_use_legacy_completions_probe() -> None:
    endpoint = ProviderEndpoint(
        endpoint_id="openai-official",
        display_name="OpenAI Official",
        protocol="openai_compatible",
        base_url="https://api.openai.com/v1",
        api_key="secret",
        provider_kind="official",
    )

    candidates = llm_router._official_language_probe_candidates(
        endpoint,
        "gpt-3.5-turbo-instruct",
    )

    assert [(candidate.method_id, candidate.request_mapper_id) for candidate in candidates] == [
        ("openai_completions", "openai_completions_text")
    ]


def test_openai_pro_reasoning_uses_supported_effort_values() -> None:
    endpoint = ProviderEndpoint(
        endpoint_id="openai-official",
        display_name="OpenAI Official",
        protocol="openai_compatible",
        base_url="https://api.openai.com/v1",
        api_key="secret",
        provider_kind="official",
    )

    legacy_pro = llm_router._official_language_probe_candidates(
        endpoint,
        "gpt-5-pro-2025-10-06",
    )
    next_pro = llm_router._official_language_probe_candidates(endpoint, "gpt-5.2-pro")

    assert {candidate.method_id for candidate in legacy_pro} == {"openai_responses"}
    assert [
        candidate.runtime_settings["reasoning"]["effort"]
        for candidate in legacy_pro
        if candidate.method_id == "openai_responses"
    ] == ["high", "high"]
    assert [
        candidate.runtime_settings["reasoning"]["effort"]
        for candidate in next_pro
        if candidate.method_id == "openai_responses" and "reasoning" in candidate.runtime_settings
    ] == ["low", "medium", "high"]


def test_ark_language_candidate_filter_includes_text_catalog_families() -> None:
    endpoint = ProviderEndpoint(
        endpoint_id="ark-official",
        display_name="Ark Official",
        protocol="ark_runtime",
        base_url="https://ark.cn-beijing.volces.com/api/v3",
        api_key="secret",
        provider_kind="official",
    )

    for model_id in ("qwen3-32b-20250429", "kimi-k2-250711", "mistral-7b-instruct-v0.2"):
        assert llm_router._is_official_language_model_candidate(endpoint, model_id) is True
        assert {
            candidate.method_id
            for candidate in llm_router._official_language_probe_candidates(endpoint, model_id)
        } == {"ark_chat", "ark_responses", "ark_anthropic_messages"}


def test_official_catalog_candidate_methods_cover_capability_library_models() -> None:
    endpoints = {
        "openai": ProviderEndpoint(
            endpoint_id="openai-official",
            display_name="OpenAI Official",
            protocol="openai_compatible",
            base_url="https://api.openai.com/v1",
            api_key="secret",
            provider_kind="official",
        ),
        "gemini": ProviderEndpoint(
            endpoint_id="gemini-official",
            display_name="Gemini Official",
            protocol="google_genai",
            base_url="https://generativelanguage.googleapis.com",
            api_key="secret",
            provider_kind="official",
        ),
        "ark": ProviderEndpoint(
            endpoint_id="ark-official",
            display_name="Ark Official",
            protocol="ark_runtime",
            base_url="https://ark.cn-beijing.volces.com/api/v3",
            api_key="secret",
            provider_kind="official",
        ),
    }
    cases = [
        (endpoints["openai"], "gpt-image-1", ["openai_images"]),
        (endpoints["openai"], "text-embedding-3-large", ["openai_embeddings"]),
        (endpoints["openai"], "gpt-4o-realtime-preview", ["openai_realtime"]),
        (endpoints["gemini"], "imagen-4.0-generate-001", ["gemini_generate_images"]),
        (endpoints["gemini"], "veo-3.1-generate-preview", ["gemini_generate_videos"]),
        (endpoints["gemini"], "gemini-embedding-001", ["gemini_embed_content"]),
        (endpoints["ark"], "doubao-seedream-5-0-260128", ["ark_images"]),
        (endpoints["ark"], "doubao-seedance-2-0-260128", ["ark_video"]),
        (endpoints["ark"], "doubao-embedding-vision-251215", ["ark_embeddings"]),
        (endpoints["ark"], "doubao-seed-translation-250915", ["ark_translation"]),
        (endpoints["ark"], "doubao-seed3d-2-0-260328", ["ark_3d"]),
    ]

    for endpoint, model_id, expected_methods in cases:
        assert (
            llm_router._official_catalog_capabilities(endpoint, model_id)["candidate_methods"]
            == expected_methods
        )


def test_gemini_official_classifies_generation_models_outside_language_routes() -> None:
    endpoint = ProviderEndpoint(
        endpoint_id="gemini-official",
        display_name="Gemini Official",
        protocol="google_genai",
        base_url="https://generativelanguage.googleapis.com",
        api_key="secret",
        provider_kind="official",
    )

    assert llm_router._official_language_probe_candidates(endpoint, "gemini-3-pro-preview")
    assert llm_router._official_language_probe_candidates(endpoint, "gemma-4-31b-it")

    excluded = {
        "gemini-3-pro-image": ("image_generation", "Image generation model"),
        "gemini-3-pro-image-preview": ("image_generation", "Image generation model"),
        "nano-banana-pro-preview": ("image_generation", "Image generation model"),
        "imagen-4.0-generate-001": ("image_generation", "Image generation model"),
        "veo-3.1-generate-preview": ("video_generation", "Video generation model"),
        "lyria-3-pro-preview": ("audio", "Audio/realtime model"),
        "gemini-2.5-flash-preview-tts": ("audio", "Audio/realtime model"),
        "gemini-embedding-001": ("embedding", "Embedding model"),
    }
    for model_id, (model_type, label) in excluded.items():
        assert llm_router._official_language_probe_candidates(endpoint, model_id) == []
        assert llm_router._official_catalog_capabilities(endpoint, model_id) == {
            "model_type": model_type,
            "model_type_label": label,
            "capability_library": True,
            "candidate_methods": llm_router._official_catalog_candidate_methods(
                endpoint,
                model_id,
                model_type,
            ),
            "input_modalities": list(
                llm_router._official_catalog_modalities(endpoint, model_id, model_type)[0]
            ),
            "output_modalities": list(
                llm_router._official_catalog_modalities(endpoint, model_id, model_type)[1]
            ),
            "input_modalities_source": "provider_doc",
            "output_modalities_source": "provider_doc",
            "input_modalities_source_urls": llm_router._official_catalog_capabilities(
                endpoint,
                model_id,
            )["input_modalities_source_urls"],
            "output_modalities_source_urls": llm_router._official_catalog_capabilities(
                endpoint,
                model_id,
            )["output_modalities_source_urls"],
        }


def test_gemini_3_reasoning_probe_uses_thinking_level_not_budget() -> None:
    endpoint = ProviderEndpoint(
        endpoint_id="gemini-official",
        display_name="Gemini Official",
        protocol="google_genai",
        base_url="https://generativelanguage.googleapis.com",
        api_key="secret",
        provider_kind="official",
    )

    candidates = llm_router._official_language_probe_candidates(
        endpoint,
        "gemini-3.1-pro-preview",
    )
    thinking_settings = [
        candidate.runtime_settings["reasoning"]
        for candidate in candidates
        if candidate.capability == "thinking"
    ]

    assert {"enabled": True, "effort": "low"} in thinking_settings
    assert all("budget_tokens" not in settings for settings in thinking_settings)


def test_gemini_interactions_only_models_are_catalog_agents_not_failed_language_routes() -> None:
    endpoint = ProviderEndpoint(
        endpoint_id="gemini-official",
        display_name="Gemini Official",
        protocol="google_genai",
        base_url="https://generativelanguage.googleapis.com",
        api_key="secret",
        provider_kind="official",
    )

    for model_id in (
        "antigravity-preview-05-2026",
        "deep-research-preview-04-2026",
        "deep-research-pro-preview-12-2025",
        "aqa",
    ):
        assert llm_router._is_official_language_model_candidate(endpoint, model_id) is False
        assert llm_router._official_language_probe_candidates(endpoint, model_id) == []
        assert llm_router._official_catalog_capabilities(endpoint, model_id) == {
            "model_type": "interactions_agent",
            "model_type_label": "Interactions API agent",
            "capability_library": True,
            "candidate_methods": ["gemini_interactions"],
            "input_modalities": [],
            "output_modalities": [],
            "input_modalities_source": "provider_doc",
            "output_modalities_source": "provider_doc",
            "input_modalities_source_urls": ["https://ai.google.dev/gemini-api/docs/models"],
            "output_modalities_source_urls": ["https://ai.google.dev/gemini-api/docs/models"],
        }


def test_registry_normalizes_stale_gemini_interactions_failed_metadata(
    client: TestClient,
    tmp_path: Path,
    monkeypatch,
) -> None:
    settings_dir = tmp_path / "settings"
    monkeypatch.setattr(config, "APP_SETTINGS_DIR", settings_dir)
    save_credentials(
        LLMCredentialsFile(
            provider_endpoints={
                "gemini-official": ProviderEndpoint(
                    endpoint_id="gemini-official",
                    display_name="Gemini Official",
                    protocol="google_genai",
                    base_url="https://generativelanguage.googleapis.com",
                    api_key="secret",
                    provider_kind="official",
                    status="verified",
                    metadata={
                        "capability_library": [
                            {
                                "model_id": "deep-research-preview-04-2026",
                                "status": "probe_failed",
                                "route_status": "failed",
                                "last_probe_message": "No official language call method passed for this model.",
                                "model_type": "language_reasoning",
                                "model_type_label": "Language/reasoning model",
                                "candidate_methods": ["gemini_generate_content"],
                            }
                        ]
                    },
                )
            },
        ),
        credentials_path(),
    )

    response = client.get("/api/llm/registry")

    assert response.status_code == 200
    entry = response.json()["provider_endpoints"]["gemini-official"]["metadata"]["capability_library"][0]
    assert entry == {
        "model_id": "deep-research-preview-04-2026",
        "status": "catalog_candidate",
        "route_status": "unverified_manual",
        "last_probe_message": "No verified language route profile.",
        "model_type": "interactions_agent",
        "model_type_label": "Interactions API agent",
        "candidate_methods": ["gemini_interactions"],
        "input_modalities": [],
        "output_modalities": [],
    }


def test_endpoint_scoped_manual_model_test_verifies_only_successful_models(
    client: TestClient,
    tmp_path: Path,
    monkeypatch,
) -> None:
    _seed(tmp_path, monkeypatch)
    route_calls: list[ProviderRoute] = []

    async def fake_test_route(
        endpoint: ProviderEndpoint,
        route: ProviderRoute,
        *,
        runtime_settings: dict[str, object] | None = None,
    ) -> RouteProbeResult:
        route_calls.append(route)
        if route.provider_model_id == "gpt-5-mini":
            return _route_probe(endpoint, route, status="ok", latency_ms=33)
        return _route_probe(
            endpoint,
            route,
            status="invalid_model",
            latency_ms=34,
            message="Provider rejected model.",
        )

    monkeypatch.setattr(llm_router, "_gateway_test_provider_route", fake_test_route)

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
            "route_id": "openai-direct:missing-model",
            "message": "Provider rejected model.",
        },
    ]
    routes = body["registry"]["provider_routes"]
    endpoint = body["registry"]["provider_endpoints"]["openai-direct"]
    assert endpoint["status"] == "verified"
    assert "gpt-5-mini" in endpoint["last_test_message"]
    assert routes["openai-direct:gpt-5-mini"]["status"] == "verified"
    assert routes["openai-direct:gpt-5-mini"]["provider_model_id"] == "gpt-5-mini"
    assert routes["openai-direct:missing-model"]["status"] == "failed"
    assert routes["openai-direct:missing-model"]["provider_model_id"] == "missing-model"
    # Only gpt-5-mini + missing-model were probed, in that order — the duplicate
    # gpt-5-mini and the empty id were skipped. Backend/key resolution is the gateway's job.
    assert [r.provider_model_id for r in route_calls] == ["gpt-5-mini", "missing-model"]
    # Evidence now lives on the credentials routes (SSOT), not the probe catalog.
    persisted = load_credentials(credentials_path())
    ok_evidence = [
        e for e in persisted.provider_routes["openai-direct:gpt-5-mini"].evidence if e.evidence_type == "probe"
    ]
    assert [e.trust_state for e in ok_evidence] == ["probe-verified"]
    assert ok_evidence[0].model_id == "gpt-5-mini"
    assert ok_evidence[0].probe_status == "ok"
    failed_evidence = [
        e for e in persisted.provider_routes["openai-direct:missing-model"].evidence if e.evidence_type == "probe"
    ]
    assert [e.trust_state for e in failed_evidence] == ["probe-failed"]
    assert failed_evidence[0].model_id == "missing-model"
    assert failed_evidence[0].probe_status == "invalid_model"
    assert "Provider rejected model." in (failed_evidence[0].reason or "")

def test_official_manual_model_test_uses_profile_probe_and_persists_attempts(
    client: TestClient,
    tmp_path: Path,
    monkeypatch,
) -> None:
    _seed(tmp_path, monkeypatch)
    save_credentials(
        LLMCredentialsFile(
            provider_endpoints={
                "openai-official": ProviderEndpoint(
                    endpoint_id="openai-official",
                    display_name="OpenAI Official",
                    protocol="openai_compatible",
                    base_url="https://api.openai.example/v1",
                    api_key="secret",
                    provider_kind="official",
                    status="verified",
                )
            }
        ),
        credentials_path(),
    )

    async def unexpected_generic_probe(*_args, **_kwargs) -> ModelProbeResult:
        raise AssertionError("official manual tests should use official profile probes")

    async def fake_profile_probe(
        endpoint: ProviderEndpoint,
        model_id: str,
    ) -> llm_router.OfficialModelProfileProbeResult:
        assert endpoint.endpoint_id == "openai-official"
        if model_id == "gpt-5-pro":
            return llm_router.OfficialModelProfileProbeResult(
                model_id=model_id,
                profiles=[
                    VerifiedProfile(
                        profile_id="reasoning:openai_responses:gpt5_pro",
                        capability="reasoning",
                        method_id="openai_responses",
                        request_mapper_id="openai_responses_reasoning",
                        status="ready",
                        default=True,
                        fallback_rank=1,
                        input_modalities=["text"],
                        output_modalities=["text"],
                    )
                ],
                probe_attempts=[
                    {
                        "profile_id": "reasoning:openai_responses:gpt5_pro",
                        "method_id": "openai_responses",
                        "request_mapper_id": "openai_responses_reasoning",
                        "status": "ok",
                    }
                ],
            )
        return llm_router.OfficialModelProfileProbeResult(
            model_id=model_id,
            last_probe_message="Responses API rejected reasoning.effort low.",
            probe_attempts=[
                {
                    "profile_id": "reasoning:openai_responses:gpt5_pro",
                    "method_id": "openai_responses",
                    "request_mapper_id": "openai_responses_reasoning",
                    "status": "error",
                    "message": "Responses API rejected reasoning.effort low.",
                }
            ],
        )

    monkeypatch.setattr(llm_router, "_gateway_test_provider_route", unexpected_generic_probe)
    monkeypatch.setattr(llm_router, "_probe_official_model_profile_result", fake_profile_probe)

    response = client.post(
        "/api/llm/endpoints/openai-official/models/test",
        json={"model_ids": ["gpt-5-pro", "bad-pro"]},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["results"] == [
        {
            "model_id": "gpt-5-pro",
            "status": "ok",
            "route_id": "openai-official:gpt-5-pro",
            "message": None,
        },
        {
            "model_id": "bad-pro",
            "status": "error",
            "route_id": "openai-official:bad-pro",
            "message": "Responses API rejected reasoning.effort low.",
        },
    ]
    route = body["registry"]["provider_routes"]["openai-official:gpt-5-pro"]
    assert route["status"] == "verified"
    assert route["verified_profiles"][0]["method_id"] == "openai_responses"
    assert route["metadata"]["probe_attempts"][0]["status"] == "ok"
    failed_route = body["registry"]["provider_routes"]["openai-official:bad-pro"]
    assert failed_route["status"] == "failed"
    assert failed_route["ui_state"] == "failed"
    assert failed_route["metadata"]["reason_code"] == "profile_probe_failed"
    assert failed_route["metadata"]["last_probe_message"] == "Responses API rejected reasoning.effort low."
    assert failed_route["metadata"]["probe_attempts"][0]["status"] == "error"
    # Profile-probe evidence now lives ON the credentials routes (SSOT), not the catalog.
    persisted = load_credentials(credentials_path())
    verified_ev = [
        e for e in persisted.provider_routes["openai-official:gpt-5-pro"].evidence if e.evidence_type == "probe"
    ]
    assert [e.trust_state for e in verified_ev] == ["probe-verified"]
    assert verified_ev[0].model_id == "gpt-5-pro"
    assert verified_ev[0].probe_attempts[0]["status"] == "ok"
    assert verified_ev[0].successful_probe == {"profile_count": 1}
    failed_ev = [
        e for e in persisted.provider_routes["openai-official:bad-pro"].evidence if e.evidence_type == "probe"
    ]
    assert [e.trust_state for e in failed_ev] == ["probe-failed"]
    assert failed_ev[0].model_id == "bad-pro"
    assert failed_ev[0].reason == "Responses API rejected reasoning.effort low."

def test_endpoint_test_does_not_resurrect_secret_cleared_during_probe(
    client: TestClient,
    tmp_path: Path,
    monkeypatch,
) -> None:
    _seed(tmp_path, monkeypatch)

    async def fake_test_endpoint(endpoint: ProviderEndpoint) -> EndpointProbeResult:
        raw = json.loads(credentials_path().read_text(encoding="utf-8"))
        raw["provider_endpoints"]["openai-direct"]["api_key"] = None
        credentials_path().write_text(json.dumps(raw), encoding="utf-8")
        return _endpoint_probe_ok(endpoint, latency_ms=42, model_ids=("gpt-5-mini",))

    monkeypatch.setattr(llm_router, "_gateway_test_provider_endpoint", fake_test_endpoint)

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

    async def fake_test_route(
        endpoint: ProviderEndpoint,
        route: ProviderRoute,
        *,
        runtime_settings: dict[str, object] | None = None,
    ) -> RouteProbeResult:
        raw = json.loads(credentials_path().read_text(encoding="utf-8"))
        raw["provider_endpoints"]["openai-direct"]["api_key"] = None
        credentials_path().write_text(json.dumps(raw), encoding="utf-8")
        return _route_probe(endpoint, route, status="ok", latency_ms=33)

    monkeypatch.setattr(llm_router, "_gateway_test_provider_route", fake_test_route)

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


def test_manual_model_failed_probe_does_not_mark_changed_endpoint_failed(
    client: TestClient,
    tmp_path: Path,
    monkeypatch,
) -> None:
    _seed(tmp_path, monkeypatch)

    async def fake_test_route(
        endpoint: ProviderEndpoint,
        route: ProviderRoute,
        *,
        runtime_settings: dict[str, object] | None = None,
    ) -> RouteProbeResult:
        raw = json.loads(credentials_path().read_text(encoding="utf-8"))
        stored = raw["provider_endpoints"]["openai-direct"]
        stored["api_key"] = None
        stored["base_url"] = "https://changed.example/v1"
        credentials_path().write_text(json.dumps(raw), encoding="utf-8")
        return _route_probe(
            endpoint,
            route,
            status="invalid_model",
            latency_ms=33,
            message="old endpoint rejected this model",
        )

    monkeypatch.setattr(llm_router, "_gateway_test_provider_route", fake_test_route)

    response = client.post(
        "/api/llm/endpoints/openai-direct/models/test",
        json={"model_ids": ["gpt-5-mini"]},
    )

    assert response.status_code == 200
    raw = json.loads(credentials_path().read_text(encoding="utf-8"))
    endpoint = raw["provider_endpoints"]["openai-direct"]
    assert endpoint["api_key"] is None
    assert endpoint["base_url"] == "https://changed.example/v1"
    assert endpoint["status"] == "unverified_manual"
    assert response.json()["results"] == [
        {
            "model_id": "gpt-5-mini",
            "status": "error",
            "route_id": None,
            "message": "Endpoint changed while model test was running.",
        }
    ]


def test_discovered_route_slug_collision_uses_deterministic_suffix(
    client: TestClient,
    tmp_path: Path,
    monkeypatch,
) -> None:
    _seed(tmp_path, monkeypatch)

    async def fake_test_endpoint(endpoint: ProviderEndpoint) -> EndpointProbeResult:
        return _endpoint_probe_ok(endpoint, latency_ms=42, model_ids=("foo/bar", "foo.bar"))

    async def fake_test_route(
        endpoint: ProviderEndpoint,
        route: ProviderRoute,
        *,
        runtime_settings: dict[str, object] | None = None,
    ) -> RouteProbeResult:
        return _route_probe(endpoint, route, status="ok", latency_ms=21)

    monkeypatch.setattr(llm_router, "_gateway_test_provider_endpoint", fake_test_endpoint)
    monkeypatch.setattr(llm_router, "_gateway_test_provider_route", fake_test_route)

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


def test_route_delete_conflicts_but_endpoint_delete_cascades_references(
    client: TestClient,
    tmp_path: Path,
    monkeypatch,
) -> None:
    _active_credentials_path, roles_path = _seed(tmp_path, monkeypatch)

    route_response = client.delete("/api/llm/routes/openai-direct:gpt-5")
    endpoint_response = client.delete("/api/llm/registry/endpoints/openai-direct")

    assert route_response.status_code == 409
    assert route_response.json()["error_code"] == "route_in_use"
    assert route_response.json()["details"]["roles"] == ["graph_agent.fallback_chain[0]"]
    assert endpoint_response.status_code == 200
    assert endpoint_response.json()["provider_endpoints"] == {}
    assert endpoint_response.json()["provider_routes"] == {}
    saved_roles = load_roles_file(roles_path)
    assert saved_roles.roles["graph_agent"].fallback_chain == []
    assert saved_roles.model_profiles["GPT5"].fallback_chain == []


def test_route_delete_conflicts_with_role_model_group_references(
    client: TestClient,
    tmp_path: Path,
    monkeypatch,
) -> None:
    _active_credentials_path, roles_path = _seed(tmp_path, monkeypatch)
    save_roles_file(
        roles_path,
        RolesData.model_validate(
            {
                "schema_version": 3,
                "roles": {
                    "analyst": {
                        "role_kind": "graph_agent",
                        "system_prompt_prefix": "",
                        "model_fallback_enabled": True,
                        "intent": {"provider_preference": "manual_order"},
                        "model_groups": [
                            {
                                "canonical_id": "gpt-5",
                                "display_name": "GPT-5",
                                "provider_models": [{"route_id": "openai-direct:gpt-5"}],
                            }
                        ],
                        "fallback_chain": [],
                    }
                },
            }
        ),
        known_route_ids={"openai-direct:gpt-5"},
    )

    route_response = client.delete("/api/llm/routes/openai-direct:gpt-5")
    endpoint_response = client.delete("/api/llm/registry/endpoints/openai-direct")

    assert route_response.status_code == 409
    assert route_response.json()["details"]["roles"] == [
        "analyst.model_groups[0].provider_models[0]"
    ]
    assert endpoint_response.status_code == 200
    assert endpoint_response.json()["provider_endpoints"] == {}
    assert endpoint_response.json()["provider_routes"] == {}
    saved_roles = load_roles_file(roles_path)
    assert saved_roles.roles["analyst"].model_groups[0].provider_models == []


def test_endpoint_delete_cascades_owned_routes_without_active_references(
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
    )
    save_credentials(credentials, active_credentials_path)
    save_roles_file(roles_path, RolesData(), known_route_ids={"openai-direct:gpt-5"})

    response = client.delete("/api/llm/registry/endpoints/openai-direct")

    assert response.status_code == 200
    assert response.json()["provider_endpoints"] == {}
    assert response.json()["provider_routes"] == {}


def test_endpoint_delete_cascades_owned_route_references(
    client: TestClient,
    tmp_path: Path,
    monkeypatch,
) -> None:
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
    model_group = RoleModelGroup(
        canonical_id="gpt-5",
        display_name="GPT-5",
        provider_models=[RoleProviderModel(route_id="openai-direct:gpt-5")],
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
            model_bundles={
                "bundle-gpt5": ModelBundle(
                    model_profile_id="bundle-gpt5",
                    display_name="GPT-5 Bundle",
                    canonical_id="bundle:gpt-5",
                    fallback_chain=[RoleRouteEntry(route_id="openai-direct:gpt-5")],
                    model_groups=[model_group],
                )
            },
            roles={
                "analyst": RoleEntry(
                    fallback_chain=[RoleRouteEntry(route_id="openai-direct:gpt-5")],
                    model_groups=[model_group],
                )
            },
        ),
        known_route_ids={"openai-direct:gpt-5"},
    )

    response = client.delete("/api/llm/registry/endpoints/openai-direct")

    assert response.status_code == 200
    body = response.json()
    assert body["provider_endpoints"] == {}
    assert body["provider_routes"] == {}
    saved_roles = load_roles_file(roles_path)
    assert saved_roles.roles["analyst"].fallback_chain == []
    assert saved_roles.roles["analyst"].model_groups[0].provider_models == []
    assert saved_roles.model_profiles["GPT5"].fallback_chain == []
    assert saved_roles.model_bundles["bundle-gpt5"].fallback_chain == []
    assert saved_roles.model_bundles["bundle-gpt5"].model_groups[0].provider_models == []


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

    async def fake_test_route(
        endpoint: ProviderEndpoint,
        route: ProviderRoute,
        *,
        runtime_settings: dict[str, object] | None = None,
    ) -> RouteProbeResult:
        calls.append(
            {
                "endpoint_id": endpoint.endpoint_id,
                "base_url": endpoint.base_url,
                "model_id": route.provider_model_id,
            }
        )
        return _route_probe(endpoint, route, status="ok")

    monkeypatch.setattr(llm_router, "_gateway_test_provider_route", fake_test_route)

    response = client.post("/api/llm/routes/openai-direct:gpt-5/probe?force=true", json={})

    assert response.status_code == 200
    # force=true probes the specific route against its endpoint's base_url + model;
    # backend/key resolution is the gateway's job.
    assert calls == [
        {
            "endpoint_id": "openai-direct",
            "base_url": "https://api.openai.example/v1",
            "model_id": "gpt-5",
        }
    ]
    assert response.json()["status"] == "verified"


def test_route_probe_force_true_delegates_scoped_route_probe_to_gateway(
    client: TestClient,
    tmp_path: Path,
    monkeypatch,
) -> None:
    _seed(tmp_path, monkeypatch)
    gateway_calls: list[tuple[str, str]] = []

    async def fake_gateway_test_provider_route(
        endpoint: ProviderEndpoint,
        route: ProviderRoute,
        **_kwargs: object,
    ) -> RouteProbeResult:
        gateway_calls.append((endpoint.endpoint_id, route.route_id))
        return RouteProbeResult(
            endpoint_id=endpoint.endpoint_id,
            route_id=route.route_id,
            provider_kind=endpoint.provider_kind,
            backend="openai",
            base_url="https://api.openai.example/v1",
            model_id=route.provider_model_id,
            status="ok",
            latency_ms=12,
        )

    monkeypatch.setattr(
        llm_router,
        "_gateway_test_provider_route",
        fake_gateway_test_provider_route,
        raising=False,
    )

    response = client.post("/api/llm/routes/openai-direct:gpt-5/probe?force=true", json={})

    assert response.status_code == 200
    assert gateway_calls == [("openai-direct", "openai-direct:gpt-5")]
    assert response.json()["status"] == "verified"


def test_route_probe_force_true_success_closes_active_route_circuit(
    client: TestClient,
    tmp_path: Path,
    monkeypatch,
) -> None:
    _seed(tmp_path, monkeypatch)
    retry_at = datetime.now(UTC) + timedelta(seconds=60)
    _open_runtime_circuit(route_id="openai-direct:gpt-5", retry_at=retry_at)

    async def fake_test_route(
        endpoint: ProviderEndpoint,
        route: ProviderRoute,
        *,
        runtime_settings: dict[str, object] | None = None,
    ) -> RouteProbeResult:
        return _route_probe(endpoint, route, status="ok", latency_ms=12)

    monkeypatch.setattr(llm_router, "_gateway_test_provider_route", fake_test_route)

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

    async def fake_test_route(
        endpoint: ProviderEndpoint,
        route: ProviderRoute,
        *,
        runtime_settings: dict[str, object] | None = None,
    ) -> RouteProbeResult:
        return _route_probe(
            endpoint,
            route,
            status="timeout",
            message="forced probe timed out",
        )

    monkeypatch.setattr(llm_router, "_gateway_test_provider_route", fake_test_route)

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

    async def fake_test_route(
        endpoint: ProviderEndpoint,
        route: ProviderRoute,
        *,
        runtime_settings: dict[str, object] | None = None,
    ) -> RouteProbeResult:
        return _route_probe(
            endpoint,
            route,
            status="invalid_model",
            message="provider rejected model",
        )

    monkeypatch.setattr(llm_router, "_gateway_test_provider_route", fake_test_route)

    response = client.post("/api/llm/routes/openai-direct:gpt-5/probe?force=true", json={})

    assert response.status_code == 200
    assert response.json()["status"] == "failed"

    registry = client.get("/api/llm/registry").json()
    provider_model = registry["model_groups"][0]["provider_models"][0]
    assert provider_model["route_id"] == "openai-direct:gpt-5"
    assert provider_model["ui_state"] == "failed"
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

    async def fake_test_route(
        endpoint: ProviderEndpoint,
        route: ProviderRoute,
        *,
        runtime_settings: dict[str, object] | None = None,
    ) -> RouteProbeResult:
        del runtime_settings
        calls.append(route.provider_model_id)
        return _route_probe(endpoint, route, status="ok")

    monkeypatch.setattr(llm_router, "_gateway_test_provider_route", fake_test_route)

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


def test_role_test_job_reports_active_route_progress(
    client: TestClient,
    tmp_path: Path,
    monkeypatch,
) -> None:
    _seed(tmp_path, monkeypatch)
    started = threading.Event()
    release = threading.Event()

    async def fake_test_route(
        endpoint: ProviderEndpoint,
        route: ProviderRoute,
        *,
        runtime_settings: dict[str, object] | None = None,
    ) -> RouteProbeResult:
        del runtime_settings
        started.set()
        await asyncio.to_thread(release.wait)
        return _route_probe(endpoint, route, status="ok")

    monkeypatch.setattr(llm_router, "_gateway_test_provider_route", fake_test_route)

    start = client.post("/api/llm/roles/graph_agent/test-jobs")
    assert start.status_code == 200
    job_id = start.json()["job_id"]

    try:
        assert started.wait(timeout=2), "role probe did not start"
        running = client.get(f"/api/llm/role-test-jobs/{job_id}")
        assert running.status_code == 200
        running_body = running.json()
        assert running_body["status"] == "running"
        # R-F21: provider_statuses now carries retry_after_seconds alongside
        # status so a cooling_down route can drive the FE Test Button countdown.
        # The field is None for non-cooldown progress entries.
        assert running_body["provider_statuses"] == [
            {
                "canonical_id": "gpt-5",
                "route_id": "openai-direct:gpt-5",
                "status": "testing",
                "message": None,
                "retry_after_seconds": None,
            }
        ]
    finally:
        release.set()

    for _ in range(20):
        finished = client.get(f"/api/llm/role-test-jobs/{job_id}").json()
        if finished["status"] == "completed":
            break
        time.sleep(0.01)
    assert finished["status"] == "completed"
    assert finished["result"]["status"] == "ok"
    assert finished["provider_statuses"][0]["status"] == "ok"


def test_put_roles_preserves_advanced_model_bundles(
    client: TestClient,
    tmp_path: Path,
    monkeypatch,
) -> None:
    _seed(tmp_path, monkeypatch)

    response = client.put(
        "/api/llm/roles",
        json={
            "schema_version": 3,
            "model_profiles": {},
            "model_bundles": {
                "premium_stack": {
                    "model_profile_id": "premium_stack",
                    "display_name": "Premium Stack",
                    "canonical_id": "gpt-5",
                    "fallback_chain": [{"route_id": "openai-direct:gpt-5"}],
                }
            },
            "roles": {},
        },
    )

    assert response.status_code == 200
    assert response.json()["model_bundles"]["premium_stack"]["display_name"] == "Premium Stack"
    assert "premium_stack" in load_roles_file(active_roles_path()).model_bundles


def test_put_roles_materializes_model_bundle_groups_to_flat_route_chain(
    client: TestClient,
    tmp_path: Path,
    monkeypatch,
) -> None:
    _seed(tmp_path, monkeypatch)

    response = client.put(
        "/api/llm/roles",
        json={
            "schema_version": 3,
            "model_profiles": {},
            "model_bundles": {
                "premium_stack": {
                    "model_profile_id": "premium_stack",
                    "display_name": "Premium Stack",
                    "canonical_id": "bundle:premium_stack",
                    "model_fallback_enabled": True,
                    "intent": {"provider_preference": "manual_order"},
                    "model_groups": [
                        {
                            "canonical_id": "gpt-5",
                            "display_name": "GPT-5",
                            "provider_models": [{"route_id": "openai-direct:gpt-5"}],
                        }
                    ],
                    "fallback_chain": [],
                }
            },
            "roles": {},
        },
    )

    assert response.status_code == 200
    bundle = response.json()["model_bundles"]["premium_stack"]
    assert [entry["route_id"] for entry in bundle["fallback_chain"]] == ["openai-direct:gpt-5"]
    saved = load_roles_file(active_roles_path()).model_bundles["premium_stack"]
    assert [entry.route_id for entry in saved.fallback_chain] == ["openai-direct:gpt-5"]


def test_delete_model_bundle_removes_persisted_bundle(
    client: TestClient,
    tmp_path: Path,
    monkeypatch,
) -> None:
    _seed(tmp_path, monkeypatch)
    create = client.put(
        "/api/llm/roles",
        json={
            "schema_version": 3,
            "model_profiles": {},
            "model_bundles": {
                "premium_stack": {
                    "model_profile_id": "premium_stack",
                    "display_name": "Premium Stack",
                    "canonical_id": "bundle:premium_stack",
                    "fallback_chain": [{"route_id": "openai-direct:gpt-5"}],
                }
            },
            "roles": {},
        },
    )
    assert create.status_code == 200

    response = client.delete("/api/llm/model-bundles/premium_stack")

    assert response.status_code == 200
    assert "premium_stack" not in response.json()["model_bundles"]
    assert "premium_stack" not in load_roles_file(active_roles_path()).model_bundles


def test_role_test_probes_role_routes_concurrently(
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
            ),
            "openrouter-prod": ProviderEndpoint(
                endpoint_id="openrouter-prod",
                display_name="OpenRouter",
                protocol="openai_compatible",
                base_url="https://openrouter.ai/api/v1",
                api_key="secret",
                status="verified",
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
            "openrouter-prod:gpt-5": ProviderRoute(
                route_id="openrouter-prod:gpt-5",
                endpoint_id="openrouter-prod",
                route_slug="gpt-5",
                provider_model_id="openai/gpt-5",
                canonical_id="gpt-5",
                display_name="GPT-5",
                status="verified",
            ),
        },
    )
    save_credentials(credentials, active_credentials_path)
    save_roles_file(
        roles_path,
        RolesData(
            roles={
                "analyst": RoleEntry(
                    fallback_chain=[
                        RoleRouteEntry(route_id="openai-direct:gpt-5"),
                        RoleRouteEntry(route_id="openrouter-prod:gpt-5"),
                    ]
                )
            }
        ),
        known_route_ids=set(credentials.provider_routes),
    )
    inflight = 0
    max_inflight = 0

    async def fake_test_route(
        endpoint: ProviderEndpoint,
        route: ProviderRoute,
        *,
        runtime_settings: dict[str, object] | None = None,
    ) -> RouteProbeResult:
        nonlocal inflight, max_inflight
        del runtime_settings
        inflight += 1
        max_inflight = max(max_inflight, inflight)
        await asyncio.sleep(0.01)
        inflight -= 1
        return _route_probe(endpoint, route, status="ok")

    monkeypatch.setattr(llm_router, "_gateway_test_provider_route", fake_test_route)

    response = client.post("/api/llm/roles/analyst/test", json={})

    assert response.status_code == 200
    assert max_inflight == 2
    assert [
        provider["status"]
        for provider in response.json()["model_groups"][0]["provider_results"]
    ] == ["ok", "ok"]


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

    async def fake_test_route(
        endpoint: ProviderEndpoint,
        route: ProviderRoute,
        *,
        runtime_settings: dict[str, object] | None = None,
    ) -> RouteProbeResult:
        del runtime_settings
        calls.append(route.provider_model_id)
        return _route_probe(endpoint, route, status="ok")

    monkeypatch.setattr(llm_router, "_gateway_test_provider_route", fake_test_route)

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


def test_role_test_probes_needs_test_provider_at_click_time(
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
                capabilities={},
            )
        },
    )
    save_credentials(credentials, active_credentials_path)
    save_roles_file(roles_path, RolesData(), known_route_ids=set(credentials.provider_routes))
    calls: list[str] = []

    async def fake_test_route(
        endpoint: ProviderEndpoint,
        route: ProviderRoute,
        *,
        runtime_settings: dict[str, object] | None = None,
    ) -> RouteProbeResult:
        assert runtime_settings == {"reasoning": {"enabled": True}}
        calls.append(route.provider_model_id)
        return _route_probe(endpoint, route, status="ok")

    monkeypatch.setattr(llm_router, "_gateway_test_provider_route", fake_test_route)

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
    assert put_response.json()["materialization_report"]["entries"][0]["role_fit"] == "needs_test"

    response = client.post("/api/llm/roles/analyst/test", json={})

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "warning"
    assert calls == ["gpt-5"]
    provider_result = body["model_groups"][0]["provider_results"][0]
    assert provider_result["route_id"] == "openai-direct:gpt-5"
    assert provider_result["provider_ui_state"] == "ready"
    assert provider_result["role_fit"] == "needs_test"
    assert provider_result["admission_decision"] == "admit"
    assert provider_result["status"] == "ok"
    assert provider_result["warnings"][0]["code"] == "thinking_capability_unknown"
    assert provider_result["resolved_settings"]["reasoning"]["enabled"] is True


def test_official_role_test_profile_ensure_writes_evidence_to_route_not_catalog(
    client: TestClient,
    tmp_path: Path,
    monkeypatch,
) -> None:
    # T4b contract 4: role-test profile-ensure persists the probed profile AND its
    # probe evidence into the SAME credentials route (route.evidence), in one save —
    # NOT the probe catalog (R3.1 / R3.3-AC2). Orchestration is unchanged.
    settings_dir = tmp_path / "settings"
    monkeypatch.setattr(config, "APP_SETTINGS_DIR", settings_dir)
    active_credentials_path = settings_dir / "llm" / "llm_credentials.json"
    roles_path = settings_dir / "llm" / "llm_roles.yaml"
    credentials = LLMCredentialsFile(
        provider_endpoints={
            "anthropic-official": ProviderEndpoint(
                endpoint_id="anthropic-official",
                display_name="Anthropic Official",
                protocol="anthropic_compatible",
                base_url="https://api.anthropic.example",
                api_key="secret",
                status="verified",
                provider_kind="official",
            )
        },
        provider_routes={
            "anthropic-official:claude-haiku": ProviderRoute(
                route_id="anthropic-official:claude-haiku",
                endpoint_id="anthropic-official",
                route_slug="claude-haiku",
                provider_model_id="claude-haiku",
                canonical_id="claude-haiku",
                display_name="Claude Haiku",
                status="verified",
                verified_profiles=[],  # empty → triggers profile-ensure during role test
            )
        },
    )
    save_credentials(credentials, active_credentials_path)
    save_roles_file(
        roles_path,
        RolesData(
            roles={
                "analyst": RoleEntry(
                    fallback_chain=[RoleRouteEntry(route_id="anthropic-official:claude-haiku")]
                )
            }
        ),
        known_route_ids=set(credentials.provider_routes),
    )

    async def fake_profile_probe(
        endpoint: ProviderEndpoint,
        model_id: str,
    ) -> llm_router.OfficialModelProfileProbeResult:
        return llm_router.OfficialModelProfileProbeResult(
            model_id=model_id,
            profiles=[
                VerifiedProfile(
                    profile_id="text",
                    capability="text_chat",
                    method_id="anthropic_messages",
                    request_mapper_id="anthropic_text",
                    status="ready",
                    default=True,
                    fallback_rank=1,
                )
            ],
            probe_attempts=[
                {
                    "profile_id": "text",
                    "method_id": "anthropic_messages",
                    "request_mapper_id": "anthropic_text",
                    "status": "ok",
                }
            ],
        )

    async def fake_official_call_method(
        method_id: str,
        api_key: str,
        base_url: str,
        model_id: str,
        runtime_settings: dict[str, object] | None = None,
    ) -> ModelProbeResult:
        return ModelProbeResult(model_id=model_id, status="ok")

    monkeypatch.setattr(llm_router, "_probe_official_model_profile_result", fake_profile_probe)
    monkeypatch.setattr(llm_router, "_gateway_probe_official_call_method", fake_official_call_method)

    response = client.post("/api/llm/roles/analyst/test", json={})

    assert response.status_code == 200
    persisted = load_credentials(credentials_path())
    route = persisted.provider_routes["anthropic-official:claude-haiku"]
    # Profile persisted (orchestration unchanged) ...
    assert route.verified_profiles[0].method_id == "anthropic_messages"
    # ... AND its probe evidence lives ON the route (SSOT), not the probe catalog.
    assert any(e.evidence_type == "probe" and e.trust_state == "probe-verified" for e in route.evidence)

def test_role_test_uses_verified_profile_call_method_for_official_routes(
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
            "anthropic-official": ProviderEndpoint(
                endpoint_id="anthropic-official",
                display_name="Anthropic Official",
                protocol="anthropic_compatible",
                base_url="https://api.anthropic.example",
                api_key="secret",
                status="verified",
                provider_kind="official",
            )
        },
        provider_routes={
            "anthropic-official:claude-opus": ProviderRoute(
                route_id="anthropic-official:claude-opus",
                endpoint_id="anthropic-official",
                route_slug="claude-opus",
                provider_model_id="claude-opus",
                canonical_id="claude-opus",
                display_name="Claude Opus",
                status="verified",
                verified_profiles=[
                    VerifiedProfile(
                        profile_id="text",
                        capability="text_chat",
                        method_id="anthropic_messages",
                        request_mapper_id="anthropic_text",
                        status="ready",
                        default=True,
                        fallback_rank=1,
                    ),
                    VerifiedProfile(
                        profile_id="reasoning",
                        capability="reasoning",
                        method_id="anthropic_messages",
                        request_mapper_id="anthropic_thinking",
                        status="ready",
                        fallback_rank=1,
                        runtime_overrides={
                            "max_output_tokens": 1025,
                            "reasoning": {
                                "enabled": True,
                                "budget_tokens": 1024,
                            },
                        },
                    ),
                ],
            )
        },
    )
    save_credentials(credentials, active_credentials_path)
    save_roles_file(
        roles_path,
        RolesData(
            roles={
                "analyst": RoleEntry(
                    fallback_chain=[
                        RoleRouteEntry(
                            route_id="anthropic-official:claude-opus",
                            runtime_settings={"reasoning": {"enabled": True}},
                        )
                    ]
                )
            }
        ),
        known_route_ids=set(credentials.provider_routes),
    )
    calls: list[dict[str, object]] = []

    async def fake_official_call_method(
        method_id: str,
        api_key: str,
        base_url: str,
        model_id: str,
        runtime_settings: dict[str, object] | None = None,
    ) -> ModelProbeResult:
        calls.append(
            {
                "method_id": method_id,
                "api_key": api_key,
                "base_url": base_url,
                "model_id": model_id,
                "runtime_settings": runtime_settings,
            }
        )
        return ModelProbeResult(model_id=model_id, status="ok")

    async def fail_generic_probe(
        endpoint: ProviderEndpoint,
        route: ProviderRoute,
        *,
        runtime_settings: dict[str, object] | None = None,
    ) -> RouteProbeResult:
        del endpoint, route, runtime_settings
        raise AssertionError("Role Test must use the verified official call method.")

    monkeypatch.setattr(llm_router, "_gateway_probe_official_call_method", fake_official_call_method)
    monkeypatch.setattr(llm_router, "_gateway_test_provider_route", fail_generic_probe)

    response = client.post("/api/llm/roles/analyst/test", json={})

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert calls == [
        {
            "method_id": "anthropic_messages",
            "api_key": "secret",
            "base_url": "https://api.anthropic.example",
            "model_id": "claude-opus",
            "runtime_settings": {
                "max_output_tokens": 1025,
                "reasoning": {
                    "enabled": True,
                    "budget_tokens": 1024,
                },
            },
        }
    ]
    provider_result = body["model_groups"][0]["provider_results"][0]
    assert provider_result["route_id"] == "anthropic-official:claude-opus"
    assert provider_result["status"] == "ok"


def test_role_test_probes_missing_official_verified_profile_and_persists_route(
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
            "anthropic-official": ProviderEndpoint(
                endpoint_id="anthropic-official",
                display_name="Anthropic Official",
                protocol="anthropic_compatible",
                base_url="https://api.anthropic.example",
                api_key="secret",
                status="verified",
                provider_kind="official",
            )
        },
        provider_routes={
            "anthropic-official:claude-haiku": ProviderRoute(
                route_id="anthropic-official:claude-haiku",
                endpoint_id="anthropic-official",
                route_slug="claude-haiku",
                provider_model_id="claude-haiku",
                canonical_id="claude-haiku",
                display_name="Claude Haiku",
                status="verified",
                verified_profiles=[],
            )
        },
    )
    save_credentials(credentials, active_credentials_path)
    save_roles_file(
        roles_path,
        RolesData(
            roles={
                "analyst": RoleEntry(
                    fallback_chain=[
                        RoleRouteEntry(route_id="anthropic-official:claude-haiku")
                    ]
                )
            }
        ),
        known_route_ids=set(credentials.provider_routes),
    )
    profile_probe_calls: list[str] = []
    official_calls: list[dict[str, object]] = []

    async def fake_profile_probe(
        endpoint: ProviderEndpoint,
        model_id: str,
    ) -> llm_router.OfficialModelProfileProbeResult:
        assert endpoint.endpoint_id == "anthropic-official"
        profile_probe_calls.append(model_id)
        return llm_router.OfficialModelProfileProbeResult(
            model_id=model_id,
            profiles=[
                VerifiedProfile(
                    profile_id="text",
                    capability="text_chat",
                    method_id="anthropic_messages",
                    request_mapper_id="anthropic_text",
                    status="ready",
                    default=True,
                    fallback_rank=1,
                    input_modalities=["text"],
                    output_modalities=["text"],
                )
            ],
            probe_attempts=[
                {
                    "profile_id": "text",
                    "method_id": "anthropic_messages",
                    "request_mapper_id": "anthropic_text",
                    "status": "ok",
                }
            ],
        )

    async def fake_official_call_method(
        method_id: str,
        api_key: str,
        base_url: str,
        model_id: str,
        runtime_settings: dict[str, object] | None = None,
    ) -> ModelProbeResult:
        official_calls.append(
            {
                "method_id": method_id,
                "api_key": api_key,
                "base_url": base_url,
                "model_id": model_id,
                "runtime_settings": runtime_settings,
            }
        )
        return ModelProbeResult(model_id=model_id, status="ok")

    async def fail_generic_probe(*_args, **_kwargs) -> RouteProbeResult:
        raise AssertionError("Official role tests must not use the generic probe.")

    monkeypatch.setattr(llm_router, "_probe_official_model_profile_result", fake_profile_probe)
    monkeypatch.setattr(llm_router, "_gateway_probe_official_call_method", fake_official_call_method)
    monkeypatch.setattr(llm_router, "_gateway_test_provider_route", fail_generic_probe)

    response = client.post("/api/llm/roles/analyst/test", json={})

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert profile_probe_calls == ["claude-haiku"]
    assert official_calls == [
        {
            "method_id": "anthropic_messages",
            "api_key": "secret",
            "base_url": "https://api.anthropic.example",
            "model_id": "claude-haiku",
            "runtime_settings": {"reasoning": {}},
        }
    ]
    provider_result = body["model_groups"][0]["provider_results"][0]
    assert provider_result["route_id"] == "anthropic-official:claude-haiku"
    assert provider_result["status"] == "ok"
    route = json.loads(credentials_path().read_text(encoding="utf-8"))["provider_routes"][
        "anthropic-official:claude-haiku"
    ]
    assert route["status"] == "verified"
    assert route["verified_profiles"][0]["method_id"] == "anthropic_messages"
    assert route["metadata"]["probe_attempts"][0]["status"] == "ok"
    assert route["capabilities"]["verified_methods"]["value"] == ["anthropic_messages"]
    # Profile-probe evidence lives ON the route (SSOT), not the catalog.
    persisted = load_credentials(credentials_path())
    route_ev = [
        e for e in persisted.provider_routes["anthropic-official:claude-haiku"].evidence if e.evidence_type == "probe"
    ]
    assert len(route_ev) == 1
    assert route_ev[0].trust_state == "probe-verified"
    assert route_ev[0].model_id == "claude-haiku"
    assert route_ev[0].method_id == "anthropic_messages"
    assert route_ev[0].probe_attempts[0]["status"] == "ok"

def test_role_test_reports_missing_official_verified_profile_probe_failure(
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
            "anthropic-official": ProviderEndpoint(
                endpoint_id="anthropic-official",
                display_name="Anthropic Official",
                protocol="anthropic_compatible",
                base_url="https://api.anthropic.example",
                api_key="secret",
                status="verified",
                provider_kind="official",
            )
        },
        provider_routes={
            "anthropic-official:claude-missing": ProviderRoute(
                route_id="anthropic-official:claude-missing",
                endpoint_id="anthropic-official",
                route_slug="claude-missing",
                provider_model_id="claude-missing",
                canonical_id="claude-missing",
                display_name="Claude Missing",
                status="verified",
                verified_profiles=[],
            )
        },
    )
    save_credentials(credentials, active_credentials_path)
    save_roles_file(
        roles_path,
        RolesData(
            roles={
                "analyst": RoleEntry(
                    fallback_chain=[
                        RoleRouteEntry(route_id="anthropic-official:claude-missing")
                    ]
                )
            }
        ),
        known_route_ids=set(credentials.provider_routes),
    )
    official_calls: list[str] = []

    async def fake_profile_probe(
        endpoint: ProviderEndpoint,
        model_id: str,
    ) -> llm_router.OfficialModelProfileProbeResult:
        assert endpoint.endpoint_id == "anthropic-official"
        return llm_router.OfficialModelProfileProbeResult(
            model_id=model_id,
            last_probe_message="Messages API returned 404 for this model.",
            probe_attempts=[
                {
                    "profile_id": "text",
                    "method_id": "anthropic_messages",
                    "request_mapper_id": "anthropic_text",
                    "status": "error",
                    "message": "Messages API returned 404 for this model.",
                }
            ],
        )

    async def fail_official_call_method(*_args, **_kwargs) -> ModelProbeResult:
        official_calls.append("called")
        raise AssertionError("Role Test should stop when profile probing fails.")

    monkeypatch.setattr(llm_router, "_probe_official_model_profile_result", fake_profile_probe)
    monkeypatch.setattr(llm_router, "_gateway_probe_official_call_method", fail_official_call_method)

    response = client.post("/api/llm/roles/analyst/test", json={})

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "failed"
    assert official_calls == []
    provider_result = body["model_groups"][0]["provider_results"][0]
    assert provider_result["route_id"] == "anthropic-official:claude-missing"
    assert provider_result["status"] == "failed"
    assert provider_result["message"] == "Messages API returned 404 for this model."
    assert "API Keys" not in provider_result["message"]
    route = json.loads(credentials_path().read_text(encoding="utf-8"))["provider_routes"][
        "anthropic-official:claude-missing"
    ]
    assert route["verified_profiles"] == []
    assert route["metadata"]["reason_code"] == "profile_probe_failed"
    assert route["metadata"]["last_probe_message"] == "Messages API returned 404 for this model."
    assert route["metadata"]["probe_attempts"][0]["status"] == "error"
    # Probe-failed evidence lives ON the route (SSOT), not the catalog.
    persisted = load_credentials(credentials_path())
    route_ev = [
        e for e in persisted.provider_routes["anthropic-official:claude-missing"].evidence if e.evidence_type == "probe"
    ]
    assert len(route_ev) == 1
    assert route_ev[0].trust_state == "probe-failed"
    assert route_ev[0].model_id == "claude-missing"
    assert route_ev[0].reason == "Messages API returned 404 for this model."
    assert route_ev[0].probe_attempts[0]["status"] == "error"

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


def test_provider_notable_models_are_doc_driven_for_manual_probe_placeholders(
    client: TestClient,
) -> None:
    qiniu_response = client.get(
        "/api/llm/providers/notable-models",
        params={"provider_key": "qiniu"},
    )
    wavespeed_response = client.get(
        "/api/llm/providers/notable-models",
        params={"provider_key": "wavespeed"},
    )

    assert qiniu_response.status_code == 200
    assert qiniu_response.json()["notable_models"][:2] == ["deepseek-r1", "deepseek-v3"]
    assert qiniu_response.json()["notable_models"] != ["gpt-5"]
    assert wavespeed_response.status_code == 200
    assert wavespeed_response.json()["notable_models"][:2] == [
        "openai/gpt-5",
        "anthropic/claude-opus-4",
    ]


def test_endpoint_notable_provider_key_matches_registered_domains_by_hostname() -> None:
    endpoint = ProviderEndpoint(
        endpoint_id="third-party",
        display_name="Third Party",
        protocol="openai_compatible",
        base_url="https://openrouter.ai.evil.example/v1",
        api_key="secret",
    )

    assert llm_router._endpoint_notable_provider_key(endpoint) == "openai"


def test_endpoint_notable_provider_key_accepts_qiniu_registered_host() -> None:
    endpoint = ProviderEndpoint(
        endpoint_id="third-party",
        display_name="Third Party",
        protocol="openai_compatible",
        base_url="https://api.qnaigc.com/v1",
        api_key="secret",
    )

    assert llm_router._endpoint_notable_provider_key(endpoint) == "qiniu"


def test_sync_catalog_endpoint_is_retired_and_disabled(
    client: TestClient, tmp_path: Path, monkeypatch
) -> None:
    # R9.6: the legacy /catalog/sync remote probe-catalog entry is retired — a no-op
    # that projects no remote source.
    _seed(tmp_path, monkeypatch)

    response = client.post("/api/llm/catalog/sync")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "disabled"
    assert body["catalog_source"] is None
    assert body["new_records_count"] == 0


def test_registry_does_not_project_legacy_remote_catalog_source(
    client: TestClient,
    tmp_path: Path,
    monkeypatch,
) -> None:
    # R9.6 + A1.3: the legacy remote-catalog "source" mechanism is retired, so the registry
    # never projects one. Counts still derive from credentials route.evidence (R9.2).
    _seed(tmp_path, monkeypatch)
    # Counts derive from credentials route.evidence (SSOT, R9.2), not the probe catalog.
    creds = load_credentials(credentials_path())
    creds.provider_routes["openai-direct:gpt-5"] = creds.provider_routes["openai-direct:gpt-5"].model_copy(
        update={
            "evidence": [
                EvidenceRecord(
                    evidence_id="probe-local-ok",
                    evidence_type="probe",
                    trust_state="probe-verified",
                    endpoint_id="openai-direct",
                    model_id="gpt-5",
                    provider_model_id="gpt-5",
                )
            ]
        }
    )
    creds.provider_routes["openai-direct:missing-model"] = ProviderRoute(
        route_id="openai-direct:missing-model",
        endpoint_id="openai-direct",
        route_slug="missing-model",
        provider_model_id="missing-model",
        canonical_id="missing-model",
        status="unverified_manual",
        evidence=[
            EvidenceRecord(
                evidence_id="probe-local-failed",
                evidence_type="probe",
                trust_state="probe-failed",
                endpoint_id="openai-direct",
                model_id="missing-model",
                provider_model_id="missing-model",
            )
        ],
    )
    save_credentials(creds, credentials_path())

    import app.routers.llm as llm_router

    monkeypatch.setattr(llm_router, "_role_effective_runtime_settings", lambda *_args, **_kwargs: {})
    response = client.get("/api/llm/registry")
    assert response.status_code == 200
    body = response.json()
    # A1.3: the legacy remote-catalog "source" mechanism is retired; the registry never
    # projects a remote catalog source.
    assert body["catalog_source"] is None
    assert body["probe_catalog"]["remote_catalog_source"] is None
    # Counts reflect credentials route.evidence (SSOT, R9.2).
    assert body["probe_catalog"]["local_evidence_records_count"] == 2
    assert body["probe_catalog"]["local_verified_records_count"] == 1
    assert body["probe_catalog"]["local_failed_records_count"] == 1
    assert body["probe_catalog"]["local_route_candidates_count"] == 2


def test_share_catalog_endpoint(client: TestClient, tmp_path: Path, monkeypatch) -> None:
    _seed(tmp_path, monkeypatch)
    
    response = client.post("/api/llm/catalog/share")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "success"
    assert body["sharing_mode"] == "local_export_only"
    assert body["auto_upload_enabled"] is False
    assert "Local verified catalog evidence exported successfully" in body["message"]
    assert "does not upload" in body["export_instructions"]
    assert "Pull Request" not in body["export_instructions"]


def test_ensure_catalog_repository_endpoint_is_retired(client: TestClient, tmp_path: Path, monkeypatch) -> None:
    # Phase 9: the legacy GitHub-repo probe-catalog concept is retired. The endpoint is a
    # no-op — it never reaches GitHub and never creates an llm_probe_catalog.json repo.
    _seed(tmp_path, monkeypatch)

    response = client.post("/api/llm/catalog/repository/ensure")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "disabled"
    assert body.get("repository_created") is None
    assert "ghp-" not in response.text
