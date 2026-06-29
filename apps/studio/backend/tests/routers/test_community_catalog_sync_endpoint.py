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


def test_verified_sync_merges_matching_evidence_into_credentials(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Phase 5: a verified sync MERGES matching community evidence straight into the
    credential route's ``evidence`` (no cache file, no metadata refs) and persists a
    tiny last-sync marker. historical_ready then projects from route.evidence."""
    from app.models.llm_config import (
        LLMCredentialsFile,
        ProviderEndpoint,
        ProviderRoute,
    )
    from app.services.community_catalog import parse_catalog_evidence
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
        # Phase 5: no cache_store; the verified records are RETURNED for merge.
        return SyncOutcome(
            status="updated",
            record_count=1,
            manifest_etag='"v2"',
            protocol_major=1,
            generated_at="2026-06-26T00:00:00Z",
            records=(record,),
        )

    monkeypatch.setattr(
        "app.services.community_catalog_runtime.sync_verified_catalog", fake_sync
    )

    body = client.post("/api/llm/catalog/sync-verified").json()
    assert body["status"] == "success"
    assert body["merged_route_count"] == 1

    creds = load_credentials(credentials_path())
    route = creds.provider_routes["deepseek-official:deepseek-v4-pro"]
    # Merged ONTO route.evidence (SSOT) with community provenance — not metadata refs.
    assert [e.evidence_id for e in route.evidence] == ["cat-deepseek-pro"]
    assert route.evidence[0].metadata.get("provenance") == "community-catalog"
    assert "evidence_refs" not in route.metadata
    # Tiny last-sync marker persisted (etag for status only); no cache file.
    assert creds.last_remote_catalog_sync is not None
    assert creds.last_remote_catalog_sync.etag == '"v2"'


def test_verified_sync_blues_a_route_added_after_an_earlier_sync(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Phase 5 (locked: no cache, no etag short-circuit). A route added AFTER an earlier
    sync must still go blue on the NEXT sync — even though the remote etag is unchanged.
    We keep no unmatched evidence, so every sync re-fetches and re-attempts the merge."""
    from app.models.llm_config import (
        LLMCredentialsFile,
        ProviderEndpoint,
        ProviderRoute,
    )
    from app.services.community_catalog import parse_catalog_evidence
    from app.services.llm_credentials import credentials_path, load_credentials, save_credentials

    # A verified endpoint with NO matching route yet.
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
                    status="verified",
                )
            },
        ),
        credentials_path(),
    )
    monkeypatch.setenv(
        "STUDIO_COMMUNITY_CATALOG_MANIFEST_URL", "https://cdn.example.org/catalog/manifest.json"
    )
    monkeypatch.setenv("STUDIO_COMMUNITY_CATALOG_SIGNING_PUBKEY", "ab" * 32)
    clear_backend_caches()

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

    async def fake_sync(**kwargs: object) -> SyncOutcome:
        # Always returns the records; reports "unchanged" once the marker etag matches.
        prev = kwargs.get("prev_etag")
        return SyncOutcome(
            status="unchanged" if prev == '"v2"' else "updated",
            record_count=1,
            manifest_etag='"v2"',
            protocol_major=1,
            generated_at="2026-06-26T00:00:00Z",
            records=(record,),
        )

    monkeypatch.setattr("app.services.community_catalog_runtime.sync_verified_catalog", fake_sync)

    # First sync: no matching route → nothing merged, no route created; marker set.
    body1 = client.post("/api/llm/catalog/sync-verified").json()
    assert body1["merged_route_count"] == 0
    creds1 = load_credentials(credentials_path())
    assert "anthropic-official:claude-opus-4-8" not in creds1.provider_routes
    assert creds1.last_remote_catalog_sync is not None
    assert creds1.last_remote_catalog_sync.etag == '"v2"'

    # Now the matching route is added (e.g. via endpoint Test).
    creds1.provider_routes["anthropic-official:claude-opus-4-8"] = ProviderRoute(
        route_id="anthropic-official:claude-opus-4-8",
        endpoint_id="anthropic-official",
        route_slug="claude-opus-4-8",
        provider_model_id="claude-opus-4-8",
        canonical_id="claude-opus-4-8",
        status="unverified_manual",
    )
    save_credentials(creds1, credentials_path())

    # Second sync: etag is UNCHANGED, but the sync still fetches + returns records and
    # merges → the late route goes blue. (Proves etag never short-circuits records.)
    body2 = client.post("/api/llm/catalog/sync-verified").json()
    assert body2["sync_status"] == "unchanged"
    assert body2["merged_route_count"] == 1
    route = load_credentials(credentials_path()).provider_routes["anthropic-official:claude-opus-4-8"]
    assert [e.evidence_id for e in route.evidence] == ["cat-anthropic-opus"]
    assert route.evidence[0].metadata.get("provenance") == "community-catalog"
