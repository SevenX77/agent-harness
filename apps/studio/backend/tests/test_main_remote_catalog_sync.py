from __future__ import annotations

from app.main import create_app
from fastapi.testclient import TestClient


def test_lifespan_does_not_sync_legacy_remote_probe_catalog() -> None:
    # R9.6: the legacy remote probe-catalog startup sync is retired — the function is
    # gone and startup never pulls llm_probe_catalog.json. Only the verified community
    # sync remains on startup (see below).
    import app.main as main

    assert not hasattr(main, "_sync_remote_probe_catalog_on_startup")

    with TestClient(create_app()) as client:
        response = client.get("/health")

    assert response.status_code == 200


def test_lifespan_syncs_verified_community_catalog_on_startup(monkeypatch) -> None:
    import app.main as main

    calls: list[str] = []

    async def fake_sync_verified_community_catalog_into_credentials(*, trigger: str) -> dict[str, object]:
        calls.append(trigger)
        return {"status": "success"}

    monkeypatch.setattr(
        main,
        "sync_verified_community_catalog_into_credentials",
        fake_sync_verified_community_catalog_into_credentials,
        raising=False,
    )

    with TestClient(create_app()) as client:
        response = client.get("/health")

    assert response.status_code == 200
    assert calls == ["startup"]
