"""The Test flow writes probe evidence into credentials ``route.evidence`` (via
merge) — the single source of truth (P7, R3.1/R3.4).

These drive the real endpoint/manual Test handlers through the FastAPI client and
assert the evidence lands on the route in credentials. The legacy probe catalog
(``llm_probe_catalog.json``) is retired (A1.3), so there is no parallel store to check.

Harness: third-party Test mocks ``_ping_provider`` (get-models) and
``_probe_model`` (generation) on the router (see test_llm_registry_api.py).
"""

from __future__ import annotations

from pathlib import Path

import pytest
from app.core import config
from app.models.llm_config import LLMCredentialsFile, ProviderEndpoint
from app.routers import llm as llm_router
from app.services.copilot_test import ModelProbeResult, PingResult
from app.services.llm_credentials import credentials_path, load_credentials, save_credentials
from fastapi.testclient import TestClient


def _seed_third_party_endpoint(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    *,
    endpoint_id: str = "tp",
) -> None:
    settings_dir = tmp_path / "settings"
    monkeypatch.setattr(config, "APP_SETTINGS_DIR", settings_dir)
    save_credentials(
        LLMCredentialsFile(
            provider_endpoints={
                endpoint_id: ProviderEndpoint(
                    endpoint_id=endpoint_id,
                    display_name=endpoint_id,
                    protocol="openai_compatible",
                    base_url="https://tp.example/v1",
                    api_key="secret",
                )
            },
        ),
        credentials_path(),
    )


def _mock_probes(
    monkeypatch: pytest.MonkeyPatch,
    *,
    model_ids: tuple[str, ...],
    probe_status: str = "ok",
) -> None:
    async def fake_ping(backend: str, api_key: str, base_url: str) -> PingResult:
        return PingResult(latency_ms=42, model_ids=model_ids)

    async def fake_probe(backend: str, api_key: str, base_url: str, model_id: str) -> ModelProbeResult:
        return ModelProbeResult(
            model_id=model_id,
            status=probe_status,
            latency_ms=21,
            message=None if probe_status == "ok" else "generation failed for this endpoint",
        )

    monkeypatch.setattr(llm_router, "_ping_provider", fake_ping)
    monkeypatch.setattr(llm_router, "_probe_model", fake_probe)


def _route_probe_states(creds: LLMCredentialsFile, route_id: str) -> list[str]:
    return [e.trust_state for e in creds.provider_routes[route_id].evidence if e.evidence_type == "probe"]


def test_third_party_endpoint_test_writes_probe_verified_to_route(
    client: TestClient,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Contract 1: endpoint Test success → probe-verified on route.evidence (R3.1-AC1).
    _seed_third_party_endpoint(monkeypatch, tmp_path)
    _mock_probes(monkeypatch, model_ids=("m1",), probe_status="ok")

    resp = client.post("/api/llm/endpoints/tp/test")
    assert resp.status_code == 200

    creds = load_credentials(credentials_path())
    assert "probe-verified" in _route_probe_states(creds, "tp:m1")

def test_third_party_failed_probe_writes_probe_failed_evidence_to_route(
    client: TestClient,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Contract 2 (codex-3): get-models ok but generation probe fails → the failed
    # model's route carries probe-failed evidence (R3.1-AC3).
    _seed_third_party_endpoint(monkeypatch, tmp_path)
    _mock_probes(monkeypatch, model_ids=("m1",), probe_status="invalid_model")

    resp = client.post("/api/llm/endpoints/tp/test")
    assert resp.status_code == 200

    creds = load_credentials(credentials_path())
    assert "probe-failed" in _route_probe_states(creds, "tp:m1")

def test_manual_third_party_model_test_merges_evidence_then_persists(
    client: TestClient,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Contract 3: manual single-model Test merges evidence into the route and the
    # one save persists it (R3.1-AC2).
    _seed_third_party_endpoint(monkeypatch, tmp_path)
    _mock_probes(monkeypatch, model_ids=(), probe_status="ok")

    resp = client.post("/api/llm/endpoints/tp/models/test", json={"model_ids": ["gpt-x"]})
    assert resp.status_code == 200

    creds = load_credentials(credentials_path())
    assert "probe-verified" in _route_probe_states(creds, "tp:gpt-x")

def test_model_list_dissolves_into_routes_without_observation_evidence(
    client: TestClient,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Contract 5: model-list truth = routes; no provider-list-observed evidence is
    # produced (R3.4-AC1).
    _seed_third_party_endpoint(monkeypatch, tmp_path)
    _mock_probes(monkeypatch, model_ids=("m1", "m2"), probe_status="ok")

    resp = client.post("/api/llm/endpoints/tp/test")
    assert resp.status_code == 200

    creds = load_credentials(credentials_path())
    # Discovered models become routes (the listing IS the truth).
    assert "tp:m1" in creds.provider_routes
    assert "tp:m2" in creds.provider_routes
    # No provider-list-observed evidence anywhere in credentials route.evidence.
    all_states = [e.trust_state for r in creds.provider_routes.values() for e in r.evidence]
    assert "provider-list-observed" not in all_states