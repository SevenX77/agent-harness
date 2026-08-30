"""J-01.I (批示轮三 R3-4) — a Test that CREATES routes merges the verified
community catalog in the SAME write transaction.

The fresh-machine journey this pins: startup sync ran while the credentials had
no routes (Phase 5 keeps no cache of unmatched evidence, so those records were
discarded); the user then configures a key and presses Test, which discovers
models and creates routes — and until this fix the community evidence for those
brand-new routes only arrived on the NEXT startup sync ("重启后才见社区蓝").
Acceptance (PROBLEM_LEDGER J-01.I): 「探测成功创建 route 的同一写事务里合并
已同步的社区 evidence…fresh 安装配 key+Test 后不重启即见社区蓝」.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from app.core import config
from app.core.adapters.gateway import parse_catalog_evidence
from app.core.backends import clear_backend_caches
from app.models.llm_config import LLMCredentialsFile, ProviderEndpoint
from app.routers import llm as llm_router
from app.services.community_catalog_sync import SyncOutcome
from app.services.llm_credentials import credentials_path, load_credentials, save_credentials
from fastapi.testclient import TestClient
from graph_agent_gateway.probing import EndpointProbeResult, RouteProbeResult

BASE_URL = "https://api.deepseek.example/v1"
CATALOG_HOST_URL = "https://api.deepseek.example"


def _seed_endpoint_without_routes(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Fresh-install shape: a configured endpoint, zero routes yet."""
    settings_dir = tmp_path / "settings"
    monkeypatch.setattr(config, "APP_SETTINGS_DIR", settings_dir)
    save_credentials(
        LLMCredentialsFile(
            provider_endpoints={
                "deepseek": ProviderEndpoint(
                    endpoint_id="deepseek",
                    display_name="DeepSeek",
                    protocol="openai_compatible",
                    base_url=BASE_URL,
                    api_key="secret",
                )
            },
        ),
        credentials_path(),
    )


def _configure_manifest(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(
        "STUDIO_COMMUNITY_CATALOG_MANIFEST_URL",
        "https://cdn.example.org/catalog/manifest.json",
    )
    monkeypatch.setenv("STUDIO_COMMUNITY_CATALOG_SIGNING_PUBKEY", "ab" * 32)
    clear_backend_caches()


def _flash_record():
    return parse_catalog_evidence(
        {
            "evidence_type": "probe_result",
            "trust_state": "probe-verified",
            "evidence_id": "cat-deepseek-flash",
            "normalized_public_base_url": CATALOG_HOST_URL,
            "provider_model_id": "deepseek-v4-flash",
            "model_id": "deepseek-v4-flash",
            "probe_status": "ok",
        }
    )


def _fake_sync_returning(record) -> tuple[list[int], object]:
    calls: list[int] = []

    async def fake_sync(**_kwargs: object) -> SyncOutcome:
        calls.append(1)
        return SyncOutcome(
            status="updated",
            record_count=1,
            manifest_etag='"v7"',
            protocol_major=1,
            generated_at="2026-08-29T00:00:00Z",
            records=(record,),
        )

    return calls, fake_sync


def _fake_probes(
    monkeypatch: pytest.MonkeyPatch,
    *,
    model_ids: tuple[str, ...],
) -> None:
    """Endpoint get-models discovers `model_ids`; the generation probe verifies
    the FIRST model it tries (the batch loop stops there), leaving later models
    at unverified — the exact shape where community blue matters."""

    async def fake_test_endpoint(endpoint: ProviderEndpoint) -> EndpointProbeResult:
        return EndpointProbeResult(
            endpoint_id=endpoint.endpoint_id,
            provider_kind=endpoint.provider_kind,
            backend=llm_router._provider_backend_for_endpoint(endpoint),
            base_url=llm_router._endpoint_probe_base_url(endpoint),
            status="ok",
            latency_ms=12,
            model_ids=model_ids,
            model_capabilities={},
        )

    async def fake_test_route(
        endpoint: ProviderEndpoint,
        route,
        *,
        runtime_settings: dict[str, object] | None = None,
    ) -> RouteProbeResult:
        return RouteProbeResult(
            endpoint_id=endpoint.endpoint_id,
            route_id=route.route_id,
            provider_kind=endpoint.provider_kind,
            backend=llm_router._provider_backend_for_endpoint(endpoint),
            base_url=llm_router._endpoint_probe_base_url(endpoint),
            model_id=route.provider_model_id,
            status="ok",
            latency_ms=21,
        )

    monkeypatch.setattr(llm_router, "_gateway_test_provider_endpoint", fake_test_endpoint)
    monkeypatch.setattr(llm_router, "_gateway_test_provider_route", fake_test_route)


def test_endpoint_test_that_creates_routes_merges_community_evidence_in_same_save(
    client: TestClient,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _seed_endpoint_without_routes(tmp_path, monkeypatch)
    _configure_manifest(monkeypatch)
    calls, fake_sync = _fake_sync_returning(_flash_record())
    monkeypatch.setattr(
        "app.services.community_catalog_runtime.sync_verified_catalog", fake_sync
    )
    # v4-pro is probed (and verified) first; v4-flash stays unverified — its only
    # path to a non-gray chip WITHOUT a restart is the community merge under test.
    _fake_probes(monkeypatch, model_ids=("deepseek-v4-pro", "deepseek-v4-flash"))

    response = client.post("/api/llm/endpoints/deepseek/test")

    assert response.status_code == 200
    assert calls, "route creation must trigger the community catalog merge"
    registry = response.json()["registry"]
    flash = registry["provider_routes"]["deepseek:deepseek-v4-flash"]
    # The WRITE RESPONSE already projects Previously-Connected blue (no restart).
    assert flash["ui_state"] == "historical_ready"
    # Persisted in the same save: evidence with community provenance + sync marker.
    creds = load_credentials(credentials_path())
    saved = creds.provider_routes["deepseek:deepseek-v4-flash"]
    assert [e.evidence_id for e in saved.evidence] == ["cat-deepseek-flash"]
    assert saved.evidence[0].metadata.get("provenance") == "community-catalog"
    assert creds.last_remote_catalog_sync is not None
    assert creds.last_remote_catalog_sync.etag == '"v7"'


def test_endpoint_test_without_new_routes_does_not_fetch_the_catalog(
    client: TestClient,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Steady state: re-testing an endpoint whose models are all already routed
    must NOT pay a remote catalog fetch on every Test click."""
    _seed_endpoint_without_routes(tmp_path, monkeypatch)
    _configure_manifest(monkeypatch)
    calls, fake_sync = _fake_sync_returning(_flash_record())
    monkeypatch.setattr(
        "app.services.community_catalog_runtime.sync_verified_catalog", fake_sync
    )
    _fake_probes(monkeypatch, model_ids=("deepseek-v4-pro",))

    first = client.post("/api/llm/endpoints/deepseek/test")
    assert first.status_code == 200
    assert len(calls) == 1  # the creating Test fetched once

    second = client.post("/api/llm/endpoints/deepseek/test")
    assert second.status_code == 200
    assert len(calls) == 1, "a Test that created no routes must not refetch the catalog"


def test_catalog_fetch_failure_never_fails_the_endpoint_test(
    client: TestClient,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _seed_endpoint_without_routes(tmp_path, monkeypatch)
    _configure_manifest(monkeypatch)

    async def broken_sync(**_kwargs: object) -> SyncOutcome:
        raise RuntimeError("catalog CDN unreachable")

    monkeypatch.setattr(
        "app.services.community_catalog_runtime.sync_verified_catalog", broken_sync
    )
    _fake_probes(monkeypatch, model_ids=("deepseek-v4-pro", "deepseek-v4-flash"))

    response = client.post("/api/llm/endpoints/deepseek/test")

    assert response.status_code == 200
    registry = response.json()["registry"]
    # Routes were still created and persisted; only the enrichment is missing.
    assert "deepseek:deepseek-v4-flash" in registry["provider_routes"]
    saved = load_credentials(credentials_path()).provider_routes["deepseek:deepseek-v4-flash"]
    assert saved.evidence == []


def test_declined_sharing_choice_stops_the_route_creation_merge(
    client: TestClient,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _seed_endpoint_without_routes(tmp_path, monkeypatch)
    _configure_manifest(monkeypatch)
    settings_payload = client.get("/api/settings").json()
    settings_payload["community_sharing_choice"] = "declined"
    assert client.put("/api/settings", json=settings_payload).status_code == 200
    calls, fake_sync = _fake_sync_returning(_flash_record())
    monkeypatch.setattr(
        "app.services.community_catalog_runtime.sync_verified_catalog", fake_sync
    )
    _fake_probes(monkeypatch, model_ids=("deepseek-v4-flash",))

    response = client.post("/api/llm/endpoints/deepseek/test")

    assert response.status_code == 200
    assert calls == [], "declined stops the community read, route creation or not"


def test_manual_model_test_that_creates_a_route_merges_community_evidence(
    client: TestClient,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The journey's manual probe path (API Keys → model Test with a typed id)
    creates routes too and gets the same in-transaction merge."""
    _seed_endpoint_without_routes(tmp_path, monkeypatch)
    _configure_manifest(monkeypatch)
    calls, fake_sync = _fake_sync_returning(_flash_record())
    monkeypatch.setattr(
        "app.services.community_catalog_runtime.sync_verified_catalog", fake_sync
    )
    _fake_probes(monkeypatch, model_ids=("deepseek-v4-flash",))

    response = client.post(
        "/api/llm/endpoints/deepseek/models/test",
        json={"model_ids": ["deepseek-v4-flash"]},
    )

    assert response.status_code == 200
    assert calls, "manual model test that creates a route must merge community evidence"
    saved = load_credentials(credentials_path()).provider_routes["deepseek:deepseek-v4-flash"]
    assert "cat-deepseek-flash" in [e.evidence_id for e in saved.evidence]
