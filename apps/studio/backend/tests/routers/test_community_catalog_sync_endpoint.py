"""Phase 2a R4: verified-sync endpoint is dormant unless manifest+key configured."""

from __future__ import annotations

import pytest
from app.core.backends import clear_backend_caches
from app.services.community_catalog_sync import SyncOutcome
from fastapi.testclient import TestClient


def test_verified_sync_endpoint_dormant_by_default(client: TestClient) -> None:
    response = client.post("/api/llm/catalog/sync-verified")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "disabled"
    assert body["verified_sync_enabled"] is False


def test_verified_sync_endpoint_runs_when_configured(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("STUDIO_COMMUNITY_CATALOG_MANIFEST_URL", "https://cdn.example.org/catalog/manifest.json")
    monkeypatch.setenv("STUDIO_COMMUNITY_CATALOG_SIGNING_PUBKEY", "ab" * 32)
    clear_backend_caches()

    async def fake_sync(**_kwargs: object) -> SyncOutcome:
        return SyncOutcome(status="updated", record_count=3, manifest_etag='"v2"', protocol_major=1)

    monkeypatch.setattr(
        "app.services.community_catalog_runtime.sync_verified_catalog", fake_sync
    )
    body = client.post("/api/llm/catalog/sync-verified").json()
    assert body["status"] == "success"
    assert body["sync_status"] == "updated"
    assert body["record_count"] == 3


def test_verified_sync_caches_without_promoting_credentials(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Page-load catalog sync only refreshes the disposable verified cache.
    Route evidence is written into credentials later, during endpoint Test."""
    from app.models.llm_config import (
        LLMCredentialsFile,
        ProviderEndpoint,
        ProviderRoute,
    )
    from app.services.community_catalog import parse_catalog_evidence
    from app.services.community_catalog_sync import CommunityCatalogCache
    from app.services.llm_credentials import (
        credentials_path,
        load_credentials,
        save_credentials,
    )
    from app.services.runtime_activity import load_runtime_activity

    save_credentials(
        LLMCredentialsFile(
            provider_endpoints={
                "deepseek-official": ProviderEndpoint(
                    endpoint_id="deepseek-official",
                    display_name="DeepSeek",
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
                    status="unverified_manual",
                )
            },
        ),
        credentials_path(),
    )
    monkeypatch.setenv(
        "STUDIO_COMMUNITY_CATALOG_MANIFEST_URL",
        "https://cdn.example.org/catalog/manifest.json",
    )
    monkeypatch.setenv("STUDIO_COMMUNITY_CATALOG_SIGNING_PUBKEY", "ab" * 32)
    clear_backend_caches()

    record = parse_catalog_evidence(
        {
            "evidence_type": "probe_result",
            "trust_state": "probe-verified",
            "evidence_id": "cat-deepseek-pro",
            "normalized_public_base_url": "https://api.deepseek.com",
            "provider_model_id": "deepseek-v4-pro",
            "model_id": "deepseek-v4-pro",
            "probe_status": "ok",
        }
    )

    async def fake_sync(**kwargs: object) -> SyncOutcome:
        store = kwargs["cache_store"]
        store.save(  # type: ignore[attr-defined]
            CommunityCatalogCache(
                generated_at="2026-06-26T00:00:00Z",
                protocol_major=1,
                records=[record],
            )
        )
        return SyncOutcome(
            status="updated", record_count=1, manifest_etag='"v2"', protocol_major=1
        )

    monkeypatch.setattr(
        "app.services.community_catalog_runtime.sync_verified_catalog", fake_sync
    )

    body = client.post("/api/llm/catalog/sync-verified").json()
    assert body["status"] == "success"
    assert body["promoted_route_count"] == 0
    assert body["cached_record_count"] == 1

    catalog_logs = load_runtime_activity(source_id="community_catalog_cache")
    assert catalog_logs
    latest_log = catalog_logs[0]
    assert latest_log["action"] == "sync_verified_catalog"
    assert latest_log["changes"]["cached_record_count"] == 1
    assert latest_log["changes"]["catalog_routes"] == [
        "https://api.deepseek.com | deepseek-v4-pro | (unknown capability)"
    ]

    route = load_credentials(credentials_path()).provider_routes[
        "deepseek-official:deepseek-v4-pro"
    ]
    assert route.metadata.get("evidence_refs", []) == []


def test_endpoint_test_carries_cached_community_evidence_for_new_routes(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """When an endpoint Test creates route rows after the verified catalog was
    already synced, the new routes must still receive matching community
    evidence before the registry response is returned."""
    from app.models.llm_config import LLMCredentialsFile, ProviderEndpoint
    from app.routers import llm as llm_router
    from app.services.community_catalog import parse_catalog_evidence
    from app.services.community_catalog_sync import (
        CommunityCatalogCache,
        DisposableCatalogCacheStore,
    )
    from app.services.llm_credentials import credentials_path, load_credentials, save_credentials
    from app.services.llm_paths import community_catalog_cache_path
    from graph_agent_gateway.registry.provider_probe import EndpointProbeResult

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
                    status="unverified_manual",
                )
            },
        ),
        credentials_path(),
    )
    record = parse_catalog_evidence(
        {
            "evidence_type": "probe_result",
            "trust_state": "probe-verified",
            "evidence_id": "cat-anthropic-opus",
            "normalized_public_base_url": "https://api.anthropic.com",
            "provider_model_id": "claude-opus-4-8",
            "model_id": "claude-opus-4-8",
            "method_id": "anthropic_messages",
            "probe_status": "ok",
        }
    )
    DisposableCatalogCacheStore(community_catalog_cache_path()).save(
        CommunityCatalogCache(
            generated_at="2026-06-26T00:00:00Z",
            protocol_major=1,
            records=[record],
        )
    )

    async def fake_endpoint_probe(endpoint: ProviderEndpoint) -> EndpointProbeResult:
        return EndpointProbeResult(
            endpoint_id=endpoint.endpoint_id,
            provider_kind=endpoint.provider_kind,
            backend="claude",
            base_url=endpoint.base_url,
            status="ok",
            latency_ms=11,
            model_ids=("claude-opus-4-8",),
        )

    monkeypatch.setattr(llm_router, "_gateway_test_provider_endpoint", fake_endpoint_probe)

    response = client.post("/api/llm/endpoints/anthropic-official/test")

    assert response.status_code == 200
    registry = response.json()["registry"]
    routes = registry["provider_routes"]
    route = next(
        item for item in routes.values() if item["provider_model_id"] == "claude-opus-4-8"
    )
    assert route["metadata"]["evidence_refs"] == ["cat-anthropic-opus"]
    assert route["ui_state"] == "historical_ready"

    saved_route = next(
        item
        for item in load_credentials(credentials_path()).provider_routes.values()
        if item.provider_model_id == "claude-opus-4-8"
    )
    assert saved_route.metadata["evidence_refs"] == ["cat-anthropic-opus"]
