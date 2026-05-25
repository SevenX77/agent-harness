from __future__ import annotations

import shutil
from collections.abc import AsyncIterator
from pathlib import Path

import pytest
from app.models.copilot import CopilotEventDone
from app.models.llm_config import ModelInfo
from app.routers import copilot as copilot_router
from app.routers import llm as llm_router
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
                    "id": "provider-ds",
                    "name": "DeepSeek",
                    "provider_type": "openai_compatible",
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
    ds = next(provider for provider in data["providers"] if provider["id"] == "provider-ds")
    assert ds["api_key"] == "sk-test-123"
    assert ds["base_url"] == "https://api.deepseek.com/v1"
    assert ds["name"] == "DeepSeek"
    assert ds["provider_type"] == "openai_compatible"


def test_roles_edit_copilot_chat_fallback(
    client: TestClient,
    isolated_llm_config: Path,
) -> None:
    isolated_llm_config.write_text(
        """
models:
  CL46T:
    name: Claude 4.6 Thinking
    providers:
      WS_LLM: claude-4-thinking
      OC_CL_ANT: claude-4-thinking
      OC_CL: claude-4-thinking
providers:
  WS_LLM:
    name: WaveSpeed LLM
    type: openai_compatible
    api_key_env: WS_API_KEY
    base_url: https://api.example.com/v1
  OC_CL_ANT:
    name: OneChats Claude Anthropic
    type: anthropic_compatible
    api_key_env: OC_CL_ANT_API_KEY
    base_url: https://api.example.com/v1
  OC_CL:
    name: OneChats Claude
    type: openai_compatible
    api_key_env: OC_CL_API_KEY
    base_url: https://api.example.com/v1
roles:
  copilot_chat:
    active_model: CL46T
    models:
      CL46T:
        providers: [OC_CL]
""".strip()
        + "\n",
        encoding="utf-8",
    )

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

    async def fake_sdks(
        _vendor: str,
        _api_key: str,
        _base_url: str,
    ) -> list[str]:
        return ["openai_compatible"]

    async def fake_models(
        _vendor: str,
        _api_key: str,
        _base_url: str,
    ) -> list[ModelInfo]:
        return [ModelInfo(id="claude-sonnet-4-6")]

    monkeypatch.setattr(llm_router, "probe_compatible_sdks", fake_sdks)
    monkeypatch.setattr(llm_router, "probe_available_models", fake_models)

    response = client.post(
        "/api/llm/providers/test",
        json={
            "id": "provider-ds",
            "provider_type": "openai_compatible",
            "api_key": "sk-test",
            "base_url": "https://api.deepseek.com/v1",
            "model_id": "deepseek-reasoner",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert isinstance(body["latency_ms"], int)
    assert body["model_seen"] is None
    assert body["message"] is None
    assert body["error_code"] is None
    assert body["available_sdks"] == ["openai_compatible"]
    assert [model["id"] for model in body["available_models"]] == ["claude-sonnet-4-6"]


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
