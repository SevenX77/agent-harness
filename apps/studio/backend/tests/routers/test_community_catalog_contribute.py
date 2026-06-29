"""Phase 2a R1: contribute endpoint — clean open API (no token), on by default.

The shipped default contributes with zero config (baked gate URL, on-by-default
flag, no token). Tests neutralize that default to stay off the network; the
"active by default" test clears the neutralization to exercise the real default.
"""

from __future__ import annotations

import pytest
from app.core.backends import clear_backend_caches
from app.models.llm_config import LLMCredentialsFile, ProviderEndpoint, ProviderRoute
from app.services.community_catalog_upload import CommunityUploadError, UploadAck
from app.services.llm_credentials import save_credentials
from fastapi.testclient import TestClient

from tests.helpers_community_catalog import probe_record  # type: ignore[import-not-found]


def test_contribute_endpoint_dormant_when_write_disabled(client: TestClient) -> None:
    # The test default neutralizes the write path (prod ships it ON); contribute
    # then reports disabled and never reaches the network.
    response = client.post("/api/llm/catalog/contribute")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "disabled"
    assert body["auto_upload_enabled"] is False
    assert body["sharing_mode"] == "local_export_only"


def test_contribute_endpoint_does_not_upload_when_dormant(client: TestClient) -> None:
    # Dormant path must never reach out; absence of a receipt token proves it.
    body = client.post("/api/llm/catalog/contribute").json()
    assert body.get("receipt_token") is None
    assert body.get("accepted", 0) == 0


def _enable_gate(monkeypatch: pytest.MonkeyPatch) -> None:
    # Opt back in over the neutralized test default (clean open API — no token).
    monkeypatch.setenv("STUDIO_COMMUNITY_UPLOAD_ENABLED", "true")
    monkeypatch.setenv("STUDIO_COMMUNITY_GATE_URL", "https://gate.example.org")
    clear_backend_caches()


def _seed_one_verified_probe() -> None:
    endpoint = ProviderEndpoint.model_validate(
        {
            "endpoint_id": "openai-main",
            "protocol": "openai_compatible",
            "base_url": "https://api.openai.com/v1",
            "display_name": "OpenAI",
        }
    )
    # Upload candidates derive from credentials route.evidence (SSOT, R9.1) — put the
    # probe-verified record on a route, not the probe catalog.
    record = probe_record(endpoint_id="openai-main", provider_id="openai", provider_model_id="gpt-4o")
    save_credentials(
        LLMCredentialsFile(
            provider_endpoints={"openai-main": endpoint},
            provider_routes={
                "openai-main:gpt-4o": ProviderRoute(
                    route_id="openai-main:gpt-4o",
                    endpoint_id="openai-main",
                    route_slug="gpt-4o",
                    provider_model_id="gpt-4o",
                    canonical_id="gpt-4o",
                    status="unverified_manual",
                    evidence=[record],
                )
            },
        )
    )


class _FakeClient:
    def __init__(self, **_kwargs: object) -> None:
        pass

    async def upload_batch(self, records: list[object], *, idempotency_key: str) -> UploadAck:
        del idempotency_key
        return UploadAck(accepted=len(records), rejected=0, receipt_token="rcpt-1")


class _FailingClient:
    def __init__(self, **_kwargs: object) -> None:
        pass

    async def upload_batch(self, records: list[object], *, idempotency_key: str) -> UploadAck:
        del records
        raise CommunityUploadError(f"gate unreachable: {idempotency_key}")


def test_contribute_endpoint_uploads_when_configured(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _enable_gate(monkeypatch)
    _seed_one_verified_probe()
    monkeypatch.setattr("app.routers.llm.CommunityUploadClient", _FakeClient)
    body = client.post("/api/llm/catalog/contribute").json()
    assert body["status"] == "success"
    assert body["accepted"] == 1
    assert body["receipt_token"] == "rcpt-1"


def test_contribute_endpoint_reports_failed_when_gate_unreachable(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Phase 6: no offline queue. A gate failure reports "failed" (not "deferred"),
    # never claims a local queue, and truthfully says it will retry by re-deriving
    # from credentials next time. The content-derived key keeps the retry idempotent.
    _enable_gate(monkeypatch)
    _seed_one_verified_probe()
    monkeypatch.setattr("app.routers.llm.CommunityUploadClient", _FailingClient)
    body = client.post("/api/llm/catalog/contribute").json()
    assert body["status"] == "failed"
    assert body.get("queued") in (None, False)
    assert "queue" not in body["message"].lower()
    assert "credential" in body["message"].lower()


def test_contribute_active_by_default_with_baked_gate(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Zero-config proof: with NO STUDIO_COMMUNITY_* env at all, the baked gate URL
    # + on-by-default flag make contribute active — no token, nothing to set up.
    # Clear the test neutralization to exercise the real shipped default; the
    # client is stubbed so the proof needs no real network.
    monkeypatch.delenv("STUDIO_COMMUNITY_UPLOAD_ENABLED", raising=False)
    monkeypatch.delenv("STUDIO_COMMUNITY_GATE_URL", raising=False)
    clear_backend_caches()
    _seed_one_verified_probe()
    monkeypatch.setattr("app.routers.llm.CommunityUploadClient", _FakeClient)
    body = client.post("/api/llm/catalog/contribute").json()
    assert body["status"] == "success"
    assert body["accepted"] == 1
    assert body["receipt_token"] == "rcpt-1"
