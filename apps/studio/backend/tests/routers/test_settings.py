from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

import pytest
from app.core import config
from app.core.backends import clear_backend_caches
from app.main import create_app
from app.models.runs import RunMetadata
from app.models.settings import AppSettings
from app.routers import settings as settings_router
from app.services.event_bus import STUDIO_EVENTS_TOPIC, event_bus
from app.services.runtime_activity import load_runtime_activity
from fastapi.testclient import TestClient


class _SettingsMetadataStore:
    def __init__(self, settings: AppSettings) -> None:
        self.settings = settings
        self.write_count = 0

    async def list_skill_index(self) -> dict[str, dict[str, str]]:
        raise NotImplementedError

    async def get_skill_index_entry(self, skill_id: str) -> dict[str, str] | None:
        raise NotImplementedError

    async def save_skill_index_entry(self, skill_id: str, entry: dict[str, str]) -> None:
        raise NotImplementedError

    async def remove_skill_index_entry(self, skill_id: str) -> None:
        raise NotImplementedError

    async def read_app_settings(self) -> AppSettings:
        return self.settings

    async def write_app_settings(self, settings: AppSettings) -> None:
        self.write_count += 1
        self.settings = settings

    async def list_runs(self, user_id: str, skill_id: str) -> list[RunMetadata]:
        raise NotImplementedError

    async def save_run_metadata(
        self,
        user_id: str,
        skill_id: str,
        metadata: RunMetadata,
    ) -> None:
        raise NotImplementedError


class _DirectSubscriber:
    def __init__(self) -> None:
        self.queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()

    def __enter__(self) -> _DirectSubscriber:
        event_bus._subscribers.setdefault(STUDIO_EVENTS_TOPIC, set()).add(self.queue)
        return self

    def __exit__(self, *_exc: object) -> None:
        subscribers = event_bus._subscribers.get(STUDIO_EVENTS_TOPIC)
        if subscribers is not None:
            subscribers.discard(self.queue)
            if not subscribers:
                event_bus._subscribers.pop(STUDIO_EVENTS_TOPIC, None)

    async def receive(self) -> dict[str, Any]:
        return await asyncio.wait_for(self.queue.get(), timeout=1.0)


def test_get_settings_returns_defaults(client: TestClient) -> None:
    response = client.get("/api/settings")

    assert response.status_code == 200
    assert response.json() == {
        "user_id": "",
        "gitea_host": "",
        "default_skills_directory": str(config.DEFAULT_SKILLS_ROOT),
        "language": "en",
        "remote_model_catalog_enabled": True,
        "cli_sessions": {"claude": {"model": "", "effort": ""}, "codex": {"model": "", "effort": ""}, "agents": {}},
    }


def test_put_then_get_roundtrip(client: TestClient, tmp_path: Path) -> None:
    payload = {
        "user_id": "alice",
        "gitea_host": "https://gitea.example.com",
        "default_skills_directory": str(tmp_path / "graph-skills"),
        "language": "en",
        "remote_model_catalog_enabled": False,
        "cli_sessions": {"claude": {"model": "", "effort": ""}, "codex": {"model": "", "effort": ""}, "agents": {}},
    }

    put_response = client.put("/api/settings", json=payload)
    get_response = client.get("/api/settings")

    assert put_response.status_code == 200
    assert put_response.json() == payload
    assert get_response.status_code == 200
    assert get_response.json() == payload
    logs = load_runtime_activity(source_id="app_settings", limit=1)
    assert logs[0]["action"] == "update_app_settings"
    assert logs[0]["changes"]["user_id"]["to"] == "alice"
    assert logs[0]["changes"]["remote_model_catalog_enabled"]["to"] is False


def test_put_blank_default_skills_directory_uses_effective_default(client: TestClient) -> None:
    put_response = client.put(
        "/api/settings",
        json={
            "user_id": "alice",
            "gitea_host": "",
            "default_skills_directory": "",
            "remote_model_catalog_enabled": True,
            "cli_sessions": {"claude": {"model": "", "effort": ""}, "codex": {"model": "", "effort": ""}, "agents": {}},
        },
    )
    get_response = client.get("/api/settings")

    assert put_response.status_code == 200
    assert put_response.json()["default_skills_directory"] == str(config.DEFAULT_SKILLS_ROOT)
    assert get_response.json()["default_skills_directory"] == str(config.DEFAULT_SKILLS_ROOT)


def test_put_validates_strip(client: TestClient) -> None:
    put_response = client.put(
        "/api/settings",
        json={
            "user_id": "  bob  ",
            "gitea_host": "",
            "default_skills_directory": "  /tmp/studio-skills  ",
            "remote_model_catalog_enabled": True,
            "cli_sessions": {"claude": {"model": "", "effort": ""}, "codex": {"model": "", "effort": ""}, "agents": {}},
        },
    )
    get_response = client.get("/api/settings")

    assert put_response.status_code == 200
    assert put_response.json()["user_id"] == "bob"
    assert put_response.json()["default_skills_directory"] == "/tmp/studio-skills"
    assert get_response.json()["user_id"] == "bob"
    assert get_response.json()["default_skills_directory"] == "/tmp/studio-skills"


def test_get_defaults_language_when_omitted(client: TestClient, tmp_path: Path) -> None:
    """N0 i18n back-compat: a PUT without ``language`` defaults to English."""
    put_response = client.put(
        "/api/settings",
        json={
            "user_id": "dave",
            "gitea_host": "",
            "default_skills_directory": str(tmp_path / "skills"),
            "remote_model_catalog_enabled": True,
            "cli_sessions": {"claude": {"model": "", "effort": ""}, "codex": {"model": "", "effort": ""}, "agents": {}},
        },
    )
    get_response = client.get("/api/settings")

    assert put_response.status_code == 200
    assert put_response.json()["language"] == "en"
    assert get_response.json()["language"] == "en"


def test_put_language_roundtrips(client: TestClient, tmp_path: Path) -> None:
    """N0 i18n: the selected UI language survives PUT -> GET."""
    payload = {
        "user_id": "eve",
        "gitea_host": "",
        "default_skills_directory": str(tmp_path / "skills"),
        "language": "zh-CN",
        "remote_model_catalog_enabled": True,
        "cli_sessions": {"claude": {"model": "", "effort": ""}, "codex": {"model": "", "effort": ""}, "agents": {}},
    }

    put_response = client.put("/api/settings", json=payload)
    get_response = client.get("/api/settings")

    assert put_response.status_code == 200
    assert put_response.json()["language"] == "zh-CN"
    assert get_response.json()["language"] == "zh-CN"


def test_put_rejects_unsupported_language(client: TestClient, tmp_path: Path) -> None:
    response = client.put(
        "/api/settings",
        json={
            "user_id": "",
            "gitea_host": "",
            "default_skills_directory": str(tmp_path / "skills"),
            "language": "fr-FR",
            "remote_model_catalog_enabled": True,
            "cli_sessions": {"claude": {"model": "", "effort": ""}, "codex": {"model": "", "effort": ""}, "agents": {}},
        },
    )

    assert response.status_code == 422


def test_put_persists_across_app_restart(
    studio_roots: tuple[Path, Path],
    tmp_path: Path,
) -> None:
    del studio_roots
    payload = {
        "user_id": "carol",
        "gitea_host": "https://gitea.example.net",
        "default_skills_directory": str(tmp_path / "team-skills"),
        "language": "zh-CN",
        "remote_model_catalog_enabled": False,
        "cli_sessions": {"claude": {"model": "", "effort": ""}, "codex": {"model": "", "effort": ""}, "agents": {}},
    }

    first_client = TestClient(create_app())
    first_client.headers["Authorization"] = "Bearer studio-test-token"
    with first_client:
        response = first_client.put("/api/settings", json=payload)
        assert response.status_code == 200

    clear_backend_caches()
    fresh_client = TestClient(create_app())
    fresh_client.headers["Authorization"] = "Bearer studio-test-token"
    with fresh_client:
        fresh_response = fresh_client.get("/api/settings")

    assert fresh_response.status_code == 200
    assert fresh_response.json() == payload


def test_put_settings_unchanged_snapshot_has_no_update_side_effect() -> None:
    existing = AppSettings(
        user_id="alice",
        gitea_host="https://gitea.example.com",
        default_skills_directory=str(config.DEFAULT_SKILLS_ROOT),
        language="en",
        remote_model_catalog_enabled=False,
    )
    metadata = _SettingsMetadataStore(existing)

    async def _put() -> AppSettings:
        with _DirectSubscriber() as sub:
            result = await settings_router.put_settings(existing, metadata)
            assert sub.queue.empty()
            return result

    result = asyncio.run(_put())

    assert result == existing
    assert metadata.write_count == 0


def test_put_settings_changed_snapshot_publishes_precise_event() -> None:
    previous = AppSettings(
        user_id="alice",
        gitea_host="https://gitea.example.com",
        default_skills_directory=str(config.DEFAULT_SKILLS_ROOT),
        language="en",
        remote_model_catalog_enabled=True,
    )
    updated = previous.model_copy(update={"language": "zh-CN", "remote_model_catalog_enabled": False})
    metadata = _SettingsMetadataStore(previous)

    async def _put() -> tuple[AppSettings, dict[str, Any]]:
        with _DirectSubscriber() as sub:
            result = await settings_router.put_settings(updated, metadata)
            return result, await sub.receive()

    result, event = asyncio.run(_put())

    assert result == updated
    assert metadata.write_count == 1
    assert event["type"] == "settings_changed"
    assert event["source"] == "http_api"
    assert event["source_id"] == "app_settings"
    assert event["changed_fields"] == ["language", "remote_model_catalog_enabled"]


def test_put_settings_event_publish_failure_does_not_break_save(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    previous = AppSettings(
        user_id="alice",
        gitea_host="https://gitea.example.com",
        default_skills_directory=str(config.DEFAULT_SKILLS_ROOT),
        language="en",
        remote_model_catalog_enabled=True,
    )
    updated = previous.model_copy(update={"language": "zh-CN"})
    metadata = _SettingsMetadataStore(previous)

    async def _boom(*_args: object, **_kwargs: object) -> None:
        raise RuntimeError("event bus offline")

    monkeypatch.setattr(settings_router.event_bus, "publish", _boom)

    with caplog.at_level("ERROR"):
        result = asyncio.run(settings_router.put_settings(updated, metadata))

    assert result == updated
    assert metadata.write_count == 1
    assert metadata.settings == updated
    assert any("publish_settings_changed" in record.getMessage() for record in caplog.records)


def test_cli_session_settings_roundtrip(client, tmp_path, monkeypatch):
    """CLI 会话配置(提案 2026-08-06 PR-3/4):claude/codex 默认 + MoirAI 分角色覆盖,
    随 app_settings.json 持久化;省缺值为全空(= 跟随 CLI 自身默认)。"""
    resp = client.get("/api/settings")
    assert resp.status_code == 200
    body = resp.json()
    assert body["cli_sessions"] == {
        "claude": {"model": "", "effort": ""},
        "codex": {"model": "", "effort": ""},
        "agents": {},
    }

    body["cli_sessions"] = {
        "claude": {"model": "claude-opus-4-8", "effort": "high"},
        "codex": {"model": "gpt-5.3-codex-spark", "effort": "low"},
        "agents": {"clotho": {"model": "claude-haiku-4-5", "effort": ""}},
    }
    resp = client.put("/api/settings", json=body)
    assert resp.status_code == 200
    resp = client.get("/api/settings")
    assert resp.json()["cli_sessions"]["claude"]["effort"] == "high"
    assert resp.json()["cli_sessions"]["agents"]["clotho"]["model"] == "claude-haiku-4-5"
