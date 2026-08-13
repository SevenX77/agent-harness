"""Media generation settings API: registry view, credential, probe, model settings."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from graph_agent_gateway.media import MediaProbeResult, MediaProviderCredential


@pytest.fixture()
def media_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    path = tmp_path / "media_generation.json"
    monkeypatch.setenv("STUDIO_MEDIA_GENERATION_PATH", str(path))
    return path


def test_registry_lists_catalog_and_empty_provider(client: TestClient, media_path: Path) -> None:
    response = client.get("/api/media/registry")
    assert response.status_code == 200
    payload = response.json()

    models = payload["models"]
    assert len(models) == 10
    assert {m["modality"] for m in models} == {"image", "video"}
    assert all("params" in m and "settings" in m for m in models)

    providers = payload["providers"]
    assert len(providers) == 1
    runninghub = providers[0]
    assert runninghub["id"] == "runninghub"
    assert runninghub["api_key_set"] is False
    assert runninghub["last_probe"] is None


def test_put_credential_persists_and_masks_key(client: TestClient, media_path: Path) -> None:
    response = client.put(
        "/api/media/providers/runninghub/credential",
        json={"api_key": "0123456789abcdef0123456789abcdef"},
    )
    assert response.status_code == 200
    provider = response.json()["providers"][0]
    assert provider["api_key_set"] is True
    assert "0123456789abcdef" not in response.text

    again = client.get("/api/media/registry")
    assert again.json()["providers"][0]["api_key_set"] is True
    assert media_path.exists()


def test_secret_reveal_returns_plaintext(client: TestClient, media_path: Path) -> None:
    client.put(
        "/api/media/providers/runninghub/credential",
        json={"api_key": "0123456789abcdef0123456789abcdef"},
    )
    response = client.get("/api/media/providers/runninghub/credential/secret")
    assert response.status_code == 200
    assert response.json()["api_key"] == "0123456789abcdef0123456789abcdef"


def test_probe_stores_result_in_snapshot(
    client: TestClient, media_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def fake_probe(credential: MediaProviderCredential, **_kwargs: object) -> MediaProbeResult:
        assert credential.api_key.get_secret_value() == "k" * 32
        return MediaProbeResult(
            status="ok",
            checked_at="2026-08-13T00:00:00+00:00",
            latency_ms=123,
            remain_coins="500",
            remain_money="10",
        )

    monkeypatch.setattr(
        "app.services.media_generation.probe_runninghub_account", fake_probe
    )

    client.put(
        "/api/media/providers/runninghub/credential", json={"api_key": "k" * 32}
    )
    response = client.post("/api/media/providers/runninghub/probe")
    assert response.status_code == 200
    probe = response.json()["providers"][0]["last_probe"]
    assert probe["status"] == "ok"
    assert probe["remain_coins"] == "500"

    again = client.get("/api/media/registry")
    assert again.json()["providers"][0]["last_probe"]["latency_ms"] == 123


def test_probe_without_key_is_rejected(client: TestClient, media_path: Path) -> None:
    response = client.post("/api/media/providers/runninghub/probe")
    assert response.status_code == 400


def test_patch_model_settings_persists_legal_defaults(
    client: TestClient, media_path: Path
) -> None:
    response = client.patch(
        "/api/media/models/rh-image-v2-t2i/settings",
        json={"enabled": False, "defaults": {"resolution": "2k", "aspectRatio": "16:9"}},
    )
    assert response.status_code == 200
    model = next(
        m for m in response.json()["models"] if m["id"] == "rh-image-v2-t2i"
    )
    assert model["settings"]["enabled"] is False
    assert model["settings"]["defaults"]["resolution"] == "2k"

    again = client.get("/api/media/registry")
    model_again = next(
        m for m in again.json()["models"] if m["id"] == "rh-image-v2-t2i"
    )
    assert model_again["settings"]["defaults"]["aspectRatio"] == "16:9"


def test_patch_model_settings_rejects_illegal_enum(
    client: TestClient, media_path: Path
) -> None:
    response = client.patch(
        "/api/media/models/rh-image-v2-t2i/settings",
        json={"defaults": {"resolution": "8k"}},
    )
    assert response.status_code == 400
    assert "resolution" in response.json()["message"]

    again = client.get("/api/media/registry")
    model = next(m for m in again.json()["models"] if m["id"] == "rh-image-v2-t2i")
    assert model["settings"]["defaults"] == {}


def test_patch_unknown_model_is_404(client: TestClient, media_path: Path) -> None:
    response = client.patch(
        "/api/media/models/no-such-model/settings", json={"enabled": False}
    )
    assert response.status_code == 404


def test_unknown_provider_is_404(client: TestClient, media_path: Path) -> None:
    response = client.put(
        "/api/media/providers/other/credential", json={"api_key": "x"}
    )
    assert response.status_code == 404
