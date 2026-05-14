from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock

import pytest
from app.routers import copilot as copilot_router
from app.services.copilot_credentials import read_credentials
from fastapi.testclient import TestClient


def default_payload() -> dict[str, object]:
    return {
        "active_provider_id": "default-claude",
        "providers": [
            {
                "id": "default-claude",
                "name": "Claude",
                "kind": "anthropic",
                "api_key": "claude-secret",
                "base_url": "",
                "active_model_id": "claude-sonnet-4-5",
            },
            {
                "id": "default-openai",
                "name": "OpenAI",
                "kind": "openai-compat",
                "api_key": "",
                "base_url": "https://openai.example/v1",
                "active_model_id": None,
            },
            {
                "id": "default-deepseek",
                "name": "DeepSeek",
                "kind": "openai-compat",
                "api_key": "deepseek-secret",
                "base_url": "",
                "active_model_id": None,
            },
            {
                "id": "default-gemini",
                "name": "Gemini",
                "kind": "google",
                "api_key": "",
                "base_url": "",
                "active_model_id": None,
            },
        ],
    }


def test_get_credentials_returns_default_plaintext_schema(
    client: TestClient,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))

    response = client.get("/api/copilot/credentials")

    assert response.status_code == 200
    body = response.json()
    assert body["active_provider_id"] == "default-claude"
    assert [provider["id"] for provider in body["providers"]] == [
        "default-claude",
        "default-openai",
        "default-deepseek",
        "default-gemini",
    ]
    assert [provider["kind"] for provider in body["providers"]] == [
        "anthropic",
        "openai-compat",
        "openai-compat",
        "google",
    ]
    assert all("api_key" in provider for provider in body["providers"])
    assert "has_key" not in str(body)
    assert "last4" not in str(body)
    assert "backends" not in str(body)


def test_put_credentials_replaces_full_config_and_get_returns_plaintext(
    client: TestClient,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    payload = default_payload()

    response = client.put("/api/copilot/credentials", json=payload)

    assert response.status_code == 200
    assert response.json() == payload
    body = client.get("/api/copilot/credentials").json()
    assert body == payload
    assert "claude-secret" in str(body)
    assert "deepseek-secret" in str(body)


def test_put_credentials_can_switch_active_provider(
    client: TestClient,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    payload = default_payload()
    payload["active_provider_id"] = "default-deepseek"

    response = client.put("/api/copilot/credentials", json=payload)

    assert response.status_code == 200
    assert response.json()["active_provider_id"] == "default-deepseek"
    assert read_credentials().active_provider_id == "default-deepseek"


def test_put_credentials_rejects_old_single_backend_patch_shape(
    client: TestClient,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))

    response = client.put(
        "/api/copilot/credentials",
        json={"backend": "claude", "api_key": "secret", "set_active": False},
    )

    assert response.status_code == 422


def test_put_credentials_calls_reset_session_for_all_backends(
    client: TestClient,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    reset_session = AsyncMock(return_value=1)
    monkeypatch.setattr(copilot_router, "reset_session", reset_session)

    response = client.put("/api/copilot/credentials", json=default_payload())

    assert response.status_code == 200
    reset_session.assert_awaited_once_with(None, None)


def test_put_credentials_persists_base_url_and_active_model(
    client: TestClient,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    payload = default_payload()
    providers = payload["providers"]
    assert isinstance(providers, list)
    providers[1]["base_url"] = "https://openai.example/custom/v1"
    providers[1]["active_model_id"] = "gpt-5-thinking-preview"

    response = client.put("/api/copilot/credentials", json=payload)

    assert response.status_code == 200
    body = client.get("/api/copilot/credentials").json()
    assert body["providers"][1]["base_url"] == "https://openai.example/custom/v1"
    assert body["providers"][1]["active_model_id"] == "gpt-5-thinking-preview"


def test_put_credentials_empty_strings_clear_key_and_base_url(
    client: TestClient,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    payload = default_payload()
    providers = payload["providers"]
    assert isinstance(providers, list)
    providers[0]["api_key"] = ""
    providers[1]["base_url"] = ""

    response = client.put("/api/copilot/credentials", json=payload)

    assert response.status_code == 200
    body = response.json()
    assert body["providers"][0]["api_key"] == ""
    assert body["providers"][1]["base_url"] == ""
