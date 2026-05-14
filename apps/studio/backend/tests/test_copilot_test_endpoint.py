from __future__ import annotations

import logging

import pytest
from app.routers import copilot as copilot_router
from app.services.copilot_test import (
    PingResult,
    _NetworkError,
    _RateLimited,
    _Unauthorized,
)
from fastapi.testclient import TestClient


def test_credentials_test_ok_masks_key_in_response_and_logs(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    async def ping_provider(_backend: str, _api_key: str, _base_url: str) -> PingResult:
        return PingResult(latency_ms=12, model_seen="claude-3-5-sonnet")

    monkeypatch.setattr(copilot_router, "_ping_provider", ping_provider)
    caplog.set_level(logging.INFO, logger="app.routers.copilot")

    response = client.post(
        "/api/copilot/credentials/test",
        json={"backend": "claude", "api_key": "sk-secret-1234", "base_url": ""},
    )

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "latency_ms": 12,
        "model_seen": "claude-3-5-sonnet",
        "message": None,
    }
    assert "sk-secret-1234" not in response.text
    assert "last4=1234" in caplog.text
    assert "sk-secret-1234" not in caplog.text


def test_credentials_test_invalid_key(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def ping_provider(_backend: str, _api_key: str, _base_url: str) -> PingResult:
        raise _Unauthorized

    monkeypatch.setattr(copilot_router, "_ping_provider", ping_provider)

    response = client.post(
        "/api/copilot/credentials/test",
        json={"backend": "openai", "api_key": "bad-key"},
    )

    assert response.status_code == 200
    assert response.json()["status"] == "invalid_key"


def test_credentials_test_rate_limited(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def ping_provider(_backend: str, _api_key: str, _base_url: str) -> PingResult:
        raise _RateLimited

    monkeypatch.setattr(copilot_router, "_ping_provider", ping_provider)

    response = client.post(
        "/api/copilot/credentials/test",
        json={"backend": "deepseek", "api_key": "rate-limited-key"},
    )

    assert response.status_code == 200
    assert response.json()["status"] == "rate_limited"


def test_credentials_test_timeout(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def ping_provider(_backend: str, _api_key: str, _base_url: str) -> PingResult:
        raise TimeoutError

    monkeypatch.setattr(copilot_router, "_ping_provider", ping_provider)

    response = client.post(
        "/api/copilot/credentials/test",
        json={"backend": "gemini", "api_key": "slow-key"},
    )

    assert response.status_code == 200
    assert response.json()["status"] == "timeout"


def test_credentials_test_network_error(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def ping_provider(_backend: str, _api_key: str, _base_url: str) -> PingResult:
        raise _NetworkError("dns failure")

    monkeypatch.setattr(copilot_router, "_ping_provider", ping_provider)

    response = client.post(
        "/api/copilot/credentials/test",
        json={"backend": "claude", "api_key": "network-key"},
    )

    assert response.status_code == 200
    assert response.json()["status"] == "network_error"
    assert response.json()["message"] == "dns failure"
