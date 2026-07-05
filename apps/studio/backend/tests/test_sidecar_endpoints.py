from __future__ import annotations

import os
from pathlib import Path

import pytest
from app.core import config
from app.main import create_app, parse_main_args
from fastapi.testclient import TestClient


def test_health_endpoint_returns_ok(client: TestClient) -> None:
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_shutdown_requires_bearer_token(
    monkeypatch: pytest.MonkeyPatch,
    studio_roots: tuple[Path, Path],
) -> None:
    del studio_roots
    monkeypatch.setenv("STUDIO_API_TOKEN", "secret")

    with TestClient(create_app()) as client:
        response = client.post("/shutdown")

    assert response.status_code == 401
    assert response.json()["error_code"] == "UNAUTHORIZED"


def test_shutdown_accepts_global_bearer_token(
    monkeypatch: pytest.MonkeyPatch,
    studio_roots: tuple[Path, Path],
) -> None:
    del studio_roots
    monkeypatch.setenv("STUDIO_API_TOKEN", "secret")
    monkeypatch.setenv("STUDIO_DISABLE_PROCESS_SHUTDOWN", "1")

    with TestClient(create_app()) as client:
        response = client.post("/shutdown", headers={"Authorization": "Bearer secret"})

    assert response.status_code == 200
    assert response.json() == {"status": "shutting_down"}


def test_parse_main_args_accepts_dynamic_port() -> None:
    args = parse_main_args(["--port", "12345", "--host", "127.0.0.1"])

    assert args.port == 12345
    assert args.host == "127.0.0.1"


def test_resource_dir_env_controls_default_paths(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("STUDIO_RESOURCE_DIR", "/tmp/studio-resource")

    resource_dir = Path("/tmp/studio-resource").resolve()
    assert config.resource_dir_from_env(os.environ) == resource_dir
    assert not hasattr(config, "default_skills_dir")
    assert not hasattr(config, "SKILLS_DIR")
