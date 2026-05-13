from __future__ import annotations

from pathlib import Path

from app.core.backends import clear_backend_caches
from app.main import create_app
from fastapi.testclient import TestClient


def test_get_settings_returns_defaults(client: TestClient) -> None:
    response = client.get("/api/settings")

    assert response.status_code == 200
    assert response.json() == {"user_id": "", "gitea_host": ""}


def test_put_then_get_roundtrip(client: TestClient) -> None:
    payload = {"user_id": "alice", "gitea_host": "https://gitea.example.com"}

    put_response = client.put("/api/settings", json=payload)
    get_response = client.get("/api/settings")

    assert put_response.status_code == 200
    assert put_response.json() == payload
    assert get_response.status_code == 200
    assert get_response.json() == payload


def test_put_validates_strip(client: TestClient) -> None:
    put_response = client.put("/api/settings", json={"user_id": "  bob  ", "gitea_host": ""})
    get_response = client.get("/api/settings")

    assert put_response.status_code == 200
    assert put_response.json()["user_id"] == "bob"
    assert get_response.json()["user_id"] == "bob"


def test_put_persists_across_app_restart(
    studio_roots: tuple[Path, Path],
) -> None:
    del studio_roots
    payload = {"user_id": "carol", "gitea_host": "https://gitea.example.net"}

    with TestClient(create_app()) as first_client:
        response = first_client.put("/api/settings", json=payload)
        assert response.status_code == 200

    clear_backend_caches()
    with TestClient(create_app()) as fresh_client:
        fresh_response = fresh_client.get("/api/settings")

    assert fresh_response.status_code == 200
    assert fresh_response.json() == payload
