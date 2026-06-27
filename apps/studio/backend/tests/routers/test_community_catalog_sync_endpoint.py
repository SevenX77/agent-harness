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

    monkeypatch.setattr("app.routers.llm.sync_verified_catalog", fake_sync)
    body = client.post("/api/llm/catalog/sync-verified").json()
    assert body["status"] == "success"
    assert body["sync_status"] == "updated"
    assert body["record_count"] == 3


def test_verified_sync_carries_evidence_into_credentials(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The verified-sync endpoint is the moment the catalog data is carried INTO
    credentials: a freshly synced probe-verified record matching a verified
    endpoint's route writes evidence onto that route so it projects blue."""
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

    monkeypatch.setattr("app.routers.llm.sync_verified_catalog", fake_sync)

    body = client.post("/api/llm/catalog/sync-verified").json()
    assert body["status"] == "success"
    assert body["promoted_route_count"] == 1

    route = load_credentials(credentials_path()).provider_routes[
        "deepseek-official:deepseek-v4-pro"
    ]
    assert "cat-deepseek-pro" in route.metadata.get("evidence_refs", [])
