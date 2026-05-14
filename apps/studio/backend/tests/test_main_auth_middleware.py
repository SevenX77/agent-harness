from __future__ import annotations

import logging
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

    with TestClient(create_app()) as client:
        response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_dev_mode_bypass_when_token_unset(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    studio_roots: tuple[Path, Path],
) -> None:
    del studio_roots
    monkeypatch.delenv("STUDIO_API_TOKEN", raising=False)
    caplog.set_level(logging.WARNING, logger="app.main")

    with TestClient(create_app()) as client:
        response = client.get("/api/skills")

    assert response.status_code == 200
    assert "STUDIO_API_TOKEN not set, running in DEV MODE without authentication" in caplog.text
