from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Any

import pytest
from app.main import create_app
from app.routers import llm as llm_router
from app.services.copilot_test import (
    PingResult,
    _NetworkError,
    _QuotaExceeded,
    _RateLimited,
    _Unauthorized,
)
from app.services.llm_provider_test import ProviderType, ping_provider
from fastapi.testclient import TestClient


def test_get_credentials_returns_has_key_without_api_key(
    client: TestClient,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    client.put(
        "/api/llm/credentials",
        json={
            "providers": [
                {
                    "provider_code": "OC_CL",
                    "api_key": "sk-secret",
                    "base_url": "https://base.test",
                }
            ]
        },
    )

    response = client.get("/api/llm/credentials")

    assert response.status_code == 200
    body = response.json()
    assert body == {
        "providers": [
            {
                "provider_code": "OC_CL",
                "has_key": True,
                "base_url": "https://base.test",
            }
        ]
    }
    assert "sk-secret" not in response.text
    assert "api_key" not in response.text


def test_put_credentials_requires_bearer_token(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    with TestClient(create_app()) as unauthenticated:
        response = unauthenticated.put(
            "/api/llm/credentials",
            json={"providers": [{"provider_code": "OC_CL", "api_key": "secret"}]},
        )

    assert response.status_code == 401


def test_put_credentials_writes_and_get_reads_sanitized(
    client: TestClient,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))

    response = client.put(
        "/api/llm/credentials",
        json={"providers": [{"provider_code": "OC_CL", "api_key": "secret"}]},
    )

    assert response.status_code == 200
    assert response.json()["providers"][0]["has_key"] is True
    assert client.get("/api/llm/credentials").json()["providers"][0]["has_key"] is True
    assert "secret" not in response.text


@pytest.mark.parametrize(
    ("provider_type", "expected_kind"),
    [
        ("anthropic_compatible", "anthropic"),
        ("openai_compatible", "openai"),
        ("wavespeed_any_llm", "openai"),
        ("gemini_official", "gemini"),
    ],
)
def test_provider_test_uses_provider_type_to_select_client(
    provider_type: ProviderType,
    expected_kind: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[str, dict[str, str], dict[str, str] | None]] = []

    class FakeResponse:
        status_code = 200

        def json(self) -> dict[str, Any]:
            return {"data": [{"id": "seen-model"}]}

        def raise_for_status(self) -> None:
            return None

    class FakeClient:
        def __init__(self, timeout: float) -> None:
            assert timeout == 8.0

        async def __aenter__(self) -> FakeClient:
            return self

        async def __aexit__(self, *args: object) -> None:
            return None

        async def get(
            self,
            url: str,
            *,
            headers: dict[str, str] | None = None,
            params: dict[str, str] | None = None,
        ) -> FakeResponse:
            calls.append((url, headers or {}, params))
            return FakeResponse()

    monkeypatch.setattr("app.services.llm_provider_test.httpx.AsyncClient", FakeClient)

    result = asyncio.run(
        ping_provider(
            "PROV",
            provider_type,
            "secret",
            "https://base.test",
        )
    )

    url, headers, params = calls[0]
    assert result.model_seen == "seen-model"
    if expected_kind == "anthropic":
        assert url == "https://base.test/v1/models"
        assert headers["x-api-key"] == "secret"
        assert "anthropic-version" in headers
    elif expected_kind == "openai":
        assert url == "https://base.test/v1/models"
        assert headers["Authorization"] == "Bearer secret"
    else:
        assert url == "https://base.test/v1beta/models"
        assert params == {"key": "secret"}


@pytest.mark.parametrize(
    ("exc", "status"),
    [
        (_Unauthorized, "invalid_key"),
        (_RateLimited, "rate_limited"),
        (_QuotaExceeded, "quota_exceeded"),
        (_NetworkError("dns failure"), "network_error"),
        (TimeoutError(), "timeout"),
    ],
)
def test_provider_test_maps_errors(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    exc: Exception | type[Exception],
    status: str,
) -> None:
    async def fake_ping(
        _provider_code: str,
        _provider_type: ProviderType,
        _api_key: str,
        _base_url: str | None,
    ) -> PingResult:
        raise exc

    monkeypatch.setattr(llm_router, "ping_provider", fake_ping)

    response = client.post(
        "/api/llm/providers/test",
        json={
            "provider_code": "OC_CL",
            "provider_type": "anthropic_compatible",
            "api_key": "secret",
        },
    )

    assert response.status_code == 200
    assert response.json()["status"] == status


def test_provider_test_requires_token() -> None:
    with TestClient(create_app()) as unauthenticated:
        response = unauthenticated.post(
            "/api/llm/providers/test",
            json={
                "provider_code": "OC_CL",
                "provider_type": "anthropic_compatible",
                "api_key": "secret",
            },
        )

    assert response.status_code == 401


def test_provider_test_masks_key_in_response_and_logs(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    async def fake_ping(
        _provider_code: str,
        _provider_type: ProviderType,
        _api_key: str,
        _base_url: str | None,
    ) -> PingResult:
        return PingResult(latency_ms=12, model_seen="seen-model")

    monkeypatch.setattr(llm_router, "ping_provider", fake_ping)
    caplog.set_level(logging.INFO, logger="app.routers.llm")

    response = client.post(
        "/api/llm/providers/test",
        json={
            "provider_code": "OC_CL",
            "provider_type": "anthropic_compatible",
            "api_key": "sk-secret-1234",
        },
    )

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "latency_ms": 12,
        "model_seen": "seen-model",
        "message": None,
    }
    assert "sk-secret-1234" not in response.text
    assert "sk-secret-1234" not in caplog.text
    assert "last4=1234" in caplog.text
