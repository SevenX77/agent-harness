from __future__ import annotations

import shutil
from collections.abc import AsyncIterator
from pathlib import Path

import pytest
from app.models.copilot import CopilotEventDone
from app.routers import copilot as copilot_router
from app.routers import llm as llm_router
from app.services.llm_provider_test import PingResultExtended
from fastapi.testclient import TestClient


@pytest.fixture
def isolated_llm_config(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> Path:
    monkeypatch.setenv("HOME", str(tmp_path))
    source = Path(__file__).resolve().parents[5] / "config" / "llm_roles.yaml"
    roles_path = tmp_path / "llm_roles.yaml"
    shutil.copyfile(source, roles_path)
    monkeypatch.setattr(llm_router, "ROLES_PATH", roles_path)
    return roles_path


def test_credentials_save_and_read_round_trip(
    client: TestClient,
    isolated_llm_config: Path,
) -> None:
    del isolated_llm_config

    initial = client.get("/api/llm/credentials")
    assert initial.status_code == 200
    assert initial.json() == {"providers": []}

    put_response = client.put(
        "/api/llm/credentials",
        json={
            "providers": [
                {
                    "provider_code": "DS",
                    "api_key": "sk-test-123",
                    "base_url": "https://api.deepseek.com/v1",
                }
            ]
        },
    )
    assert put_response.status_code == 200

    get_response = client.get("/api/llm/credentials?include_metadata=true")
    assert get_response.status_code == 200
    data = get_response.json()
    ds = next(provider for provider in data["providers"] if provider["provider_code"] == "DS")
    assert ds["has_key"] is True
    assert ds["base_url"] == "https://api.deepseek.com/v1"
    assert ds["name"]
    assert ds["provider_type"] == "openai_compatible"
    assert "sk-test-123" not in get_response.text


def test_roles_edit_copilot_chat_fallback(
    client: TestClient,
    isolated_llm_config: Path,
) -> None:
    roles = client.get("/api/llm/roles").json()
    roles["roles"]["copilot_chat"]["models"]["CL46T"]["providers"] = [
        "WS_LLM",
        "OC_CL_ANT",
        "OC_CL",
    ]

    put_response = client.put("/api/llm/roles", json=roles)
    assert put_response.status_code == 200

    get_response = client.get("/api/llm/roles/copilot_chat")
    assert get_response.status_code == 200
    assert get_response.json()["models"]["CL46T"]["providers"] == [
        "WS_LLM",
        "OC_CL_ANT",
        "OC_CL",
    ]
    assert "WS_LLM" in isolated_llm_config.read_text(encoding="utf-8")


def test_provider_test_endpoint_mocked(
    client: TestClient,
    isolated_llm_config: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    del isolated_llm_config

    async def fake_ping(
        _provider_code: str,
        _provider_type: str,
        _api_key: str,
        _base_url: str | None,
    ) -> PingResultExtended:
        return PingResultExtended(
            latency_ms=150,
            model_seen="claude-sonnet-4-6",
            model_ids=["claude-sonnet-4-6"],
            raw_payload={"data": [{"id": "claude-sonnet-4-6"}]},
        )

    monkeypatch.setattr(llm_router, "ping_provider_extended", fake_ping)

    response = client.post(
        "/api/llm/providers/test",
        json={
            "provider_code": "DS",
            "provider_type": "openai_compatible",
            "api_key": "sk-test",
            "base_url": "https://api.deepseek.com/v1",
            "model_id": "deepseek-reasoner",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["latency_ms"] == 150
    assert body["model_seen"] == "claude-sonnet-4-6"
    assert body["message"] is None
    assert body["error_code"] is None
    assert [m["id"] for m in body["available_models"]] == ["claude-sonnet-4-6"]


def test_websocket_forwards_model_override(
    client: TestClient,
    isolated_llm_config: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    del isolated_llm_config
    calls: list[dict[str, object]] = []

    def stream_query(**kwargs: object) -> AsyncIterator[object]:
        calls.append(kwargs)
        return _events(CopilotEventDone())

    monkeypatch.setattr(copilot_router, "stream_query", stream_query)

    with client.websocket_connect("/api/skills/text-segmentation/copilot/ws") as websocket:
        websocket.send_json({"user_message": "hello", "model_override": "CL46T"})
        assert websocket.receive_json()["type"] == "done"

    assert calls == [
        {
            "skill_id": "text-segmentation",
            "user_message": "hello",
            "model_override": "CL46T",
        }
    ]


async def _events(*items: object) -> AsyncIterator[object]:
    for item in items:
        yield item
