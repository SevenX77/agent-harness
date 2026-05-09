from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path
from unittest.mock import AsyncMock

import pytest
from app.models.copilot import (
    CopilotEventDone,
    CopilotEventError,
    CopilotEventText,
    CopilotEventToolUseStart,
)
from app.routers import copilot as copilot_router
from app.services.copilot_credentials import BackendCredentials, CredentialsData
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect


def test_copilot_ws_streams_normal_query(
    client: TestClient,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setattr(copilot_router, "read_credentials", lambda: _credentials("claude", "key"))
    monkeypatch.setattr(
        copilot_router,
        "stream_query",
        lambda *_args: _events(CopilotEventText(content="hello"), CopilotEventDone()),
    )

    with client.websocket_connect("/api/skills/text-segmentation/copilot/ws") as websocket:
        websocket.send_json({"user_message": "hi"})

        assert websocket.receive_json()["type"] == "text_delta"
        assert websocket.receive_json()["type"] == "done"


def test_copilot_ws_supports_multi_turn_queries(
    client: TestClient,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []

    def stream_query(_skill_id: str, _backend: str, _api_key: str, user_message: str) -> AsyncIterator[object]:
        calls.append(user_message)
        return _events(CopilotEventText(content=f"echo:{user_message}"), CopilotEventDone())

    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setattr(copilot_router, "read_credentials", lambda: _credentials("claude", "key"))
    monkeypatch.setattr(copilot_router, "stream_query", stream_query)

    with client.websocket_connect("/api/skills/text-segmentation/copilot/ws") as websocket:
        websocket.send_json({"user_message": "hi"})
        assert websocket.receive_json()["content"] == "echo:hi"
        assert websocket.receive_json()["type"] == "done"

        websocket.send_json({"user_message": "next"})
        assert websocket.receive_json()["content"] == "echo:next"
        assert websocket.receive_json()["type"] == "done"

    assert calls == ["hi", "next"]


def test_copilot_ws_without_active_backend_key_sends_error_and_closes(
    client: TestClient,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setattr(copilot_router, "read_credentials", lambda: _credentials("claude", ""))

    with client.websocket_connect("/api/skills/text-segmentation/copilot/ws") as websocket:
        assert websocket.receive_json() == {
            "type": "error",
            "message": "未配置 claude 的 API key",
        }
        with pytest.raises(WebSocketDisconnect):
            websocket.receive_json()


def test_copilot_ws_v1_5_backend_sends_error_and_closes(
    client: TestClient,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setattr(copilot_router, "read_credentials", lambda: _credentials("gemini", "key"))

    with client.websocket_connect("/api/skills/text-segmentation/copilot/ws") as websocket:
        assert websocket.receive_json() == {
            "type": "error",
            "message": "V1.5 backend (gemini) 暂不可用",
        }
        with pytest.raises(WebSocketDisconnect):
            websocket.receive_json()


def test_copilot_ws_disconnect_resets_session(
    client: TestClient,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    reset_session = AsyncMock(return_value=1)
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setattr(copilot_router, "read_credentials", lambda: _credentials("claude", "key"))
    monkeypatch.setattr(copilot_router, "reset_session", reset_session)
    monkeypatch.setattr(
        copilot_router,
        "stream_query",
        lambda *_args: _events(CopilotEventText(content="hello"), CopilotEventDone()),
    )

    with client.websocket_connect("/api/skills/text-segmentation/copilot/ws") as websocket:
        websocket.send_json({"user_message": "hi"})
        assert websocket.receive_json()["type"] == "text_delta"
        assert websocket.receive_json()["type"] == "done"

    reset_session.assert_awaited_once_with(skill_id="text-segmentation", backend="claude")


def test_copilot_ws_forwards_stream_query_error(
    client: TestClient,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setattr(copilot_router, "read_credentials", lambda: _credentials("claude", "key"))
    monkeypatch.setattr(
        copilot_router,
        "stream_query",
        lambda *_args: _events(CopilotEventError(message="boom")),
    )

    with client.websocket_connect("/api/skills/text-segmentation/copilot/ws") as websocket:
        websocket.send_json({"user_message": "hi"})

        assert websocket.receive_json() == {"type": "error", "message": "boom"}


def test_copilot_ws_serializes_copilot_event_discriminator(
    client: TestClient,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setattr(copilot_router, "read_credentials", lambda: _credentials("claude", "key"))
    monkeypatch.setattr(
        copilot_router,
        "stream_query",
        lambda *_args: _events(
            CopilotEventToolUseStart(tool_name="Read", tool_input={"file_path": "SKILL.md"}),
            CopilotEventDone(),
        ),
    )

    with client.websocket_connect("/api/skills/text-segmentation/copilot/ws") as websocket:
        websocket.send_json({"user_message": "hi"})

        assert websocket.receive_json() == {
            "type": "tool_use_start",
            "tool_name": "Read",
            "tool_input": {"file_path": "SKILL.md"},
        }


async def _events(*items: object) -> AsyncIterator[object]:
    for item in items:
        yield item


def _credentials(active_backend: str, active_key: str) -> CredentialsData:
    return CredentialsData(
        active_backend=active_backend,
        backends={
            "claude": BackendCredentials(api_key=active_key if active_backend == "claude" else "claude-key"),
            "deepseek": BackendCredentials(api_key=active_key if active_backend == "deepseek" else "deepseek-key"),
            "gemini": BackendCredentials(api_key=active_key if active_backend == "gemini" else ""),
            "openai": BackendCredentials(api_key=active_key if active_backend == "openai" else ""),
        },
    )
