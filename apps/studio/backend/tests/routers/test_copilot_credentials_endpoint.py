from __future__ import annotations

import sys
import types
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


def test_get_credentials_returns_default_sanitized_schema(
    client: TestClient,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))

    response = client.get("/api/copilot/credentials")

    assert response.status_code == 200
    body = response.json()
    assert body["active_backend"] == "claude"
    assert set(body["backends"]) == {"claude", "deepseek", "gemini", "openai"}
    assert all(item["has_key"] is False for item in body["backends"].values())
    assert body["backends"]["gemini"]["V1_5_PLACEHOLDER"] is True
    assert body["backends"]["openai"]["V1_5_PLACEHOLDER"] is True
    assert "api_key" not in str(body)


def test_put_credentials_writes_key_and_get_remains_sanitized(
    client: TestClient,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))

    response = client.put(
        "/api/copilot/credentials",
        json={"backend": "claude", "api_key": "secret", "set_active": False},
    )

    assert response.status_code == 200
    body = client.get("/api/copilot/credentials").json()
    assert body["backends"]["claude"]["has_key"] is True
    assert "secret" not in str(body)
    assert "api_key" not in str(body)


def test_put_credentials_can_switch_active_backend(
    client: TestClient,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))

    response = client.put(
        "/api/copilot/credentials",
        json={"backend": "deepseek", "api_key": "deepseek-key", "set_active": True},
    )

    assert response.status_code == 200
    assert response.json()["active_backend"] == "deepseek"


def test_put_placeholder_key_is_allowed_but_set_active_is_rejected(
    client: TestClient,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))

    write_response = client.put(
        "/api/copilot/credentials",
        json={"backend": "gemini", "api_key": "future-key", "set_active": False},
    )
    active_response = client.put(
        "/api/copilot/credentials",
        json={"backend": "gemini", "api_key": "future-key", "set_active": True},
    )

    assert write_response.status_code == 200
    assert write_response.json()["backends"]["gemini"]["has_key"] is True
    assert active_response.status_code == 400
    assert active_response.json()["error_code"] == "COPILOT_BACKEND_DISABLED"


def test_put_credentials_rejects_extra_fields(client: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))

    response = client.put(
        "/api/copilot/credentials",
        json={
            "backend": "claude",
            "api_key": "secret",
            "set_active": False,
            "extra": "nope",
        },
    )

    assert response.status_code == 422


def test_put_credentials_calls_lazy_reset_session(
    client: TestClient,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    calls: list[tuple[object, object]] = []
    fake_module = types.ModuleType("app.services.copilot")

    def reset_session(skill_id: object, backend: object) -> None:
        calls.append((skill_id, backend))

    fake_module.reset_session = reset_session  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "app.services.copilot", fake_module)

    response = client.put(
        "/api/copilot/credentials",
        json={"backend": "claude", "api_key": "same-key", "set_active": False},
    )

    assert response.status_code == 200
    assert calls == [(None, "claude")]
