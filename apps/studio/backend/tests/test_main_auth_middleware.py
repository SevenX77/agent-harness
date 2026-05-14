from __future__ import annotations

from pathlib import Path

import pytest
from app.main import create_app
from fastapi.testclient import TestClient


def test_missing_token_returns_401(
    monkeypatch: pytest.MonkeyPatch,
    studio_roots: tuple[Path, Path],
) -> None:
    del studio_roots
    monkeypatch.setenv("STUDIO_API_TOKEN", "secret")
    monkeypatch.delenv("STUDIO_DEV_TUNNEL_TOKEN", raising=False)

    with TestClient(create_app()) as client:
        response = client.get("/api/skills")

    assert response.status_code == 401
    assert response.json()["error_code"] == "UNAUTHORIZED"


def test_wrong_token_returns_401(
    monkeypatch: pytest.MonkeyPatch,
    studio_roots: tuple[Path, Path],
) -> None:
    del studio_roots
    monkeypatch.setenv("STUDIO_API_TOKEN", "secret")
    monkeypatch.delenv("STUDIO_DEV_TUNNEL_TOKEN", raising=False)

    with TestClient(create_app()) as client:
        response = client.get("/api/skills", headers={"Authorization": "Bearer wrong"})

    assert response.status_code == 401
    assert response.json()["error_code"] == "INVALID_TOKEN"


def test_correct_token_passes(
    monkeypatch: pytest.MonkeyPatch,
    studio_roots: tuple[Path, Path],
) -> None:
    del studio_roots
    monkeypatch.setenv("STUDIO_API_TOKEN", "secret")
    monkeypatch.delenv("STUDIO_DEV_TUNNEL_TOKEN", raising=False)

    with TestClient(create_app()) as client:
        response = client.get("/api/skills", headers={"Authorization": "Bearer secret"})

    assert response.status_code == 200
    assert response.json()


def test_health_endpoint_bypass(
    monkeypatch: pytest.MonkeyPatch,
    studio_roots: tuple[Path, Path],
) -> None:
    del studio_roots
    monkeypatch.setenv("STUDIO_API_TOKEN", "secret")
    monkeypatch.delenv("STUDIO_DEV_TUNNEL_TOKEN", raising=False)

    with TestClient(create_app()) as client:
        response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_dev_mode_bypass_when_token_unset(
    monkeypatch: pytest.MonkeyPatch,
    studio_roots: tuple[Path, Path],
) -> None:
    del studio_roots
    monkeypatch.delenv("STUDIO_API_TOKEN", raising=False)
    monkeypatch.setenv("STUDIO_DEV_TUNNEL_TOKEN", "dev-secret")

    with TestClient(create_app()) as client:
        missing_response = client.get("/api/skills")
        wrong_response = client.get("/api/skills", headers={"Authorization": "Bearer wrong"})
        correct_response = client.get(
            "/api/skills",
            headers={"Authorization": "Bearer dev-secret"},
        )

    assert missing_response.status_code == 401
    assert missing_response.json()["error_code"] == "UNAUTHORIZED"
    assert wrong_response.status_code == 401
    assert wrong_response.json()["error_code"] == "INVALID_TOKEN"
    assert correct_response.status_code == 200
    assert correct_response.json()


def test_api_and_dev_tunnel_tokens_both_pass(
    monkeypatch: pytest.MonkeyPatch,
    studio_roots: tuple[Path, Path],
) -> None:
    del studio_roots
    monkeypatch.setenv("STUDIO_API_TOKEN", "api-secret")
    monkeypatch.setenv("STUDIO_DEV_TUNNEL_TOKEN", "dev-secret")

    with TestClient(create_app()) as client:
        api_response = client.get("/api/skills", headers={"Authorization": "Bearer api-secret"})
        dev_response = client.get("/api/skills", headers={"Authorization": "Bearer dev-secret"})

    assert api_response.status_code == 200
    assert dev_response.status_code == 200


def test_create_app_rejects_empty_tokens(
    monkeypatch: pytest.MonkeyPatch,
    studio_roots: tuple[Path, Path],
) -> None:
    del studio_roots
    monkeypatch.delenv("STUDIO_API_TOKEN", raising=False)
    monkeypatch.delenv("STUDIO_DEV_TUNNEL_TOKEN", raising=False)

    with pytest.raises(RuntimeError, match="Refusing to start"):
        create_app()
