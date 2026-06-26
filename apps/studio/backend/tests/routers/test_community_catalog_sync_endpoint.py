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
