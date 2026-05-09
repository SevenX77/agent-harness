from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock

import pytest
from app.routers import copilot as copilot_router
from app.services import copilot as copilot_service
from fastapi.testclient import TestClient


@pytest.fixture(autouse=True)
def clear_context_cache() -> None:
    copilot_service._view_contexts.clear()
    yield
    copilot_service._view_contexts.clear()


def test_post_context_accepts_new_view_context(client: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))

    response = client.post(
        "/api/skills/text-segmentation/copilot/context",
        json={"view": "Edit", "context": {"skill_md_text": "hello"}, "timestamp": 200},
    )

    assert response.status_code == 200
    assert response.json() == {
        "accepted": True,
        "reason": None,
        "summary": "Edit at 200",
    }
    cached = copilot_service.get_view_context("text-segmentation")
    assert cached is not None
    assert cached.context == {"skill_md_text": "hello"}


def test_post_context_rejects_out_of_order_timestamp(
    client: TestClient,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    client.post(
        "/api/skills/text-segmentation/copilot/context",
        json={"view": "Edit", "context": {"value": "new"}, "timestamp": 200},
    )

    response = client.post(
        "/api/skills/text-segmentation/copilot/context",
        json={"view": "Run", "context": {"value": "old"}, "timestamp": 100},
    )

    assert response.status_code == 200
    assert response.json() == {
        "accepted": False,
        "reason": "out_of_order",
        "summary": "Edit at 200",
    }
    cached = copilot_service.get_view_context("text-segmentation")
    assert cached is not None
    assert cached.context == {"value": "new"}


def test_post_context_rejects_equal_timestamp(client: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    client.post(
        "/api/skills/text-segmentation/copilot/context",
        json={"view": "Edit", "context": {"value": "first"}, "timestamp": 100},
    )

    response = client.post(
        "/api/skills/text-segmentation/copilot/context",
        json={"view": "Run", "context": {"value": "second"}, "timestamp": 100},
    )

    assert response.status_code == 200
    assert response.json()["accepted"] is False
    assert response.json()["reason"] == "out_of_order"


def test_post_context_requires_view_and_timestamp(client: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))

    missing_view = client.post(
        "/api/skills/text-segmentation/copilot/context",
        json={"context": {}, "timestamp": 100},
    )
    missing_timestamp = client.post(
        "/api/skills/text-segmentation/copilot/context",
        json={"view": "Edit", "context": {}},
    )

    assert missing_view.status_code == 422
    assert missing_timestamp.status_code == 422


def test_post_context_does_not_trigger_llm_or_reset_session(
    client: TestClient,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    stream_query = AsyncMock()
    reset_session = AsyncMock()
    monkeypatch.setattr(copilot_service, "stream_query", stream_query)
    monkeypatch.setattr(copilot_router, "reset_session", reset_session)

    response = client.post(
        "/api/skills/text-segmentation/copilot/context",
        json={"view": "Edit", "context": {}, "timestamp": 100},
    )

    assert response.status_code == 200
    stream_query.assert_not_called()
    reset_session.assert_not_called()
