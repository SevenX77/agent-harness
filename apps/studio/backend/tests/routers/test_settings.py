from __future__ import annotations

from pathlib import Path

from app.core import config
from app.core.backends import clear_backend_caches
from app.main import create_app
from fastapi.testclient import TestClient


def test_get_settings_returns_defaults(client: TestClient) -> None:
    response = client.get("/api/settings")

    assert response.status_code == 200
    assert response.json() == {
        "user_id": "",
        "gitea_host": "",
        "default_skills_directory": str(config.DEFAULT_SKILLS_ROOT),
    }


def test_put_then_get_roundtrip(client: TestClient, tmp_path: Path) -> None:
    payload = {
        "user_id": "alice",
        "gitea_host": "https://gitea.example.com",
        "default_skills_directory": str(tmp_path / "graph-skills"),
    }

    put_response = client.put("/api/settings", json=payload)
    get_response = client.get("/api/settings")

    assert put_response.status_code == 200
    assert put_response.json() == payload
    assert get_response.status_code == 200
    assert get_response.json() == payload


def test_put_blank_default_skills_directory_uses_effective_default(client: TestClient) -> None:
    put_response = client.put(
        "/api/settings",
        json={
            "user_id": "alice",
            "gitea_host": "",
            "default_skills_directory": "",
        },
    )
    get_response = client.get("/api/settings")

    assert put_response.status_code == 200
    assert put_response.json()["default_skills_directory"] == str(config.DEFAULT_SKILLS_ROOT)
    assert get_response.json()["default_skills_directory"] == str(config.DEFAULT_SKILLS_ROOT)


def test_put_validates_strip(client: TestClient) -> None:
    put_response = client.put(
        "/api/settings",
        json={
            "user_id": "  bob  ",
            "gitea_host": "",
            "default_skills_directory": "  /tmp/studio-skills  ",
        },
    )
    get_response = client.get("/api/settings")

    assert put_response.status_code == 200
    assert put_response.json()["user_id"] == "bob"
    assert put_response.json()["default_skills_directory"] == "/tmp/studio-skills"
    assert get_response.json()["user_id"] == "bob"
    assert get_response.json()["default_skills_directory"] == "/tmp/studio-skills"


def test_put_persists_across_app_restart(
    studio_roots: tuple[Path, Path],
    tmp_path: Path,
) -> None:
    del studio_roots
    payload = {
        "user_id": "carol",
        "gitea_host": "https://gitea.example.net",
        "default_skills_directory": str(tmp_path / "team-skills"),
    }

    first_client = TestClient(create_app())
    first_client.headers["Authorization"] = "Bearer studio-test-token"
    with first_client:
        response = first_client.put("/api/settings", json=payload)
        assert response.status_code == 200

    clear_backend_caches()
    fresh_client = TestClient(create_app())
    fresh_client.headers["Authorization"] = "Bearer studio-test-token"
    with fresh_client:
        fresh_response = fresh_client.get("/api/settings")

    assert fresh_response.status_code == 200
    assert fresh_response.json() == payload
