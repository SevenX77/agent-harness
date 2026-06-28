from __future__ import annotations

from types import SimpleNamespace

from app.main import create_app
from fastapi.testclient import TestClient


def test_lifespan_syncs_remote_probe_catalog_when_source_configured(monkeypatch) -> None:
    import app.main as main

    calls: list[str] = []

    def fake_source_metadata() -> SimpleNamespace:
        return SimpleNamespace(enabled=True, source_url="https://catalog.example/drafts.json")

    async def fake_sync_remote_probe_catalog() -> None:
        calls.append("sync")

    monkeypatch.setattr(main, "load_remote_catalog_source_metadata", fake_source_metadata, raising=False)
    monkeypatch.setattr(main, "sync_remote_probe_catalog", fake_sync_remote_probe_catalog, raising=False)

    with TestClient(create_app()) as client:
        response = client.get("/health")

    assert response.status_code == 200
    assert calls == ["sync"]


def test_lifespan_remote_probe_catalog_sync_failure_does_not_block_startup(monkeypatch) -> None:
    import app.main as main

    def fake_source_metadata() -> SimpleNamespace:
        return SimpleNamespace(enabled=True, source_url="https://catalog.example/drafts.json")

    async def fake_sync_remote_probe_catalog() -> None:
        raise RuntimeError("catalog unavailable")

    monkeypatch.setattr(main, "load_remote_catalog_source_metadata", fake_source_metadata, raising=False)
    monkeypatch.setattr(main, "sync_remote_probe_catalog", fake_sync_remote_probe_catalog, raising=False)

    with TestClient(create_app()) as client:
        response = client.get("/health")

    assert response.status_code == 200
