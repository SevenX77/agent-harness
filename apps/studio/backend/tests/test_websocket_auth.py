from __future__ import annotations

from pathlib import Path

import pytest
from app.main import create_app
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect


def test_run_events_ws_requires_query_token(
    monkeypatch: pytest.MonkeyPatch,
    studio_roots: tuple[Path, Path],
) -> None:
    client = _client(monkeypatch, studio_roots)

    _assert_ws_rejected(client, "/ws/runs/example")
    _assert_ws_rejected(client, "/ws/runs/example?token=wrong")


def test_events_ws_accepts_valid_query_token(
    monkeypatch: pytest.MonkeyPatch,
    studio_roots: tuple[Path, Path],
) -> None:
    client = _client(monkeypatch, studio_roots)

    with client.websocket_connect("/ws/events?token=dev-secret"):
        pass


def test_events_ws_rejects_invalid_query_token(
    monkeypatch: pytest.MonkeyPatch,
    studio_roots: tuple[Path, Path],
) -> None:
    client = _client(monkeypatch, studio_roots)

    _assert_ws_rejected(client, "/ws/events")
    _assert_ws_rejected(client, "/ws/events?token=wrong")


def test_copilot_ws_accepts_valid_query_token(
    monkeypatch: pytest.MonkeyPatch,
    studio_roots: tuple[Path, Path],
) -> None:
    client = _client(monkeypatch, studio_roots)

    with client.websocket_connect("/api/skills/text-segmentation/copilot/ws?token=dev-secret"):
        pass


def test_copilot_ws_rejects_invalid_query_token(
    monkeypatch: pytest.MonkeyPatch,
    studio_roots: tuple[Path, Path],
) -> None:
    client = _client(monkeypatch, studio_roots)

    _assert_ws_rejected(client, "/api/skills/text-segmentation/copilot/ws")
    _assert_ws_rejected(client, "/api/skills/text-segmentation/copilot/ws?token=wrong")


def _client(
    monkeypatch: pytest.MonkeyPatch,
    studio_roots: tuple[Path, Path],
) -> TestClient:
    del studio_roots
    monkeypatch.delenv("STUDIO_API_TOKEN", raising=False)
    monkeypatch.setenv("STUDIO_DEV_TUNNEL_TOKEN", "dev-secret")
    return TestClient(create_app())


def _assert_ws_rejected(client: TestClient, path: str) -> None:
    with pytest.raises(WebSocketDisconnect) as exc_info:
        with client.websocket_connect(path):
            pass

    assert exc_info.value.code == 4401
