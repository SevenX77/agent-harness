from __future__ import annotations

import logging
from collections.abc import Callable

import httpx
import pytest
from app.services import copilot_test
from fastapi.testclient import TestClient


def install_mock_transport(
    monkeypatch: pytest.MonkeyPatch,
    handler: Callable[[httpx.Request], httpx.Response],
) -> None:
    async_client = httpx.AsyncClient

    def factory(*args: object, **kwargs: object) -> httpx.AsyncClient:
        kwargs["transport"] = httpx.MockTransport(handler)
        return async_client(*args, **kwargs)

    monkeypatch.setattr(copilot_test.httpx, "AsyncClient", factory)


def post_provider_test(
    client: TestClient,
    *,
    kind: str,
    base_url: str = "",
    api_key: str = "sk-secret-1234",
) -> httpx.Response:
    return client.post(
        "/api/copilot/providers/test",
        json={
            "id": f"provider-{kind}",
            "name": kind,
            "kind": kind,
            "api_key": api_key,
            "base_url": base_url,
        },
    )


def test_provider_test_anthropic_ok_discovers_models_and_logs_without_key(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert str(request.url) == "https://api.anthropic.com/v1/models"
        assert request.headers["x-api-key"] == "sk-secret-1234"
        return httpx.Response(
            200,
            json={
                "data": [
                    {"id": "claude-sonnet-4-5"},
                    {"id": "claude-3-haiku"},
                ]
            },
        )

    install_mock_transport(monkeypatch, handler)
    caplog.set_level(logging.INFO, logger="app.routers.copilot")

    response = post_provider_test(client, kind="anthropic")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["latency_ms"] >= 0
    assert body["models"] == [
        {"id": "claude-sonnet-4-5", "supports_thinking": True, "supports_vision": True},
        {"id": "claude-3-haiku", "supports_thinking": False, "supports_vision": True},
    ]
    assert "sk-secret-1234" not in response.text
    assert "provider_id=provider-anthropic" in caplog.text
    assert "sk-secret-1234" not in caplog.text


def test_provider_test_openai_compat_ok_uses_custom_v1_base_url(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert str(request.url) == "https://openai.example/v1/models"
        assert request.headers["authorization"] == "Bearer sk-secret-1234"
        return httpx.Response(
            200,
            json={
                "data": [
                    {"id": "o3-mini"},
                    {"id": "gpt-4o"},
                ]
            },
        )

    install_mock_transport(monkeypatch, handler)

    response = post_provider_test(
        client,
        kind="openai-compat",
        base_url="https://openai.example/v1",
    )

    assert response.status_code == 200
    assert response.json()["models"] == [
        {"id": "o3-mini", "supports_thinking": True, "supports_vision": False},
        {"id": "gpt-4o", "supports_thinking": False, "supports_vision": True},
    ]


def test_provider_test_google_ok_discovers_models_from_name_field(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert str(request.url) == "https://generativelanguage.googleapis.com/v1beta/models?key=sk-secret-1234"
        return httpx.Response(
            200,
            json={
                "models": [
                    {"name": "models/gemini-2.5-thinking-pro"},
                    {"name": "models/gemini-1.5-flash"},
                ]
            },
        )

    install_mock_transport(monkeypatch, handler)

    response = post_provider_test(client, kind="google")

    assert response.status_code == 200
    assert response.json()["models"] == [
        {"id": "gemini-2.5-thinking-pro", "supports_thinking": True, "supports_vision": True},
        {"id": "gemini-1.5-flash", "supports_thinking": False, "supports_vision": True},
    ]


def test_provider_test_invalid_key(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    install_mock_transport(monkeypatch, lambda _request: httpx.Response(401, json={"error": "bad key"}))

    response = post_provider_test(client, kind="anthropic", api_key="bad-key")

    assert response.status_code == 200
    assert response.json()["status"] == "invalid_key"


def test_provider_test_rate_limited(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    install_mock_transport(monkeypatch, lambda _request: httpx.Response(429, json={"error": "slow down"}))

    response = post_provider_test(client, kind="openai-compat")

    assert response.status_code == 200
    assert response.json()["status"] == "rate_limited"


def test_provider_test_timeout(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.TimeoutException("slow", request=request)

    install_mock_transport(monkeypatch, handler)

    response = post_provider_test(client, kind="google")

    assert response.status_code == 200
    assert response.json()["status"] == "timeout"


def test_provider_test_network_error(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("dns failure", request=request)

    install_mock_transport(monkeypatch, handler)

    response = post_provider_test(client, kind="anthropic")

    assert response.status_code == 200
    assert response.json()["status"] == "network_error"
    assert response.json()["message"] == "dns failure"
