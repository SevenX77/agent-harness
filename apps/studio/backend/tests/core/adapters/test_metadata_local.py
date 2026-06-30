from __future__ import annotations

import logging
import os
import stat
from pathlib import Path

import pytest
from app.core.adapters.metadata_local import LocalJsonMetadataStore
from app.models.settings import AppSettings


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture
def metadata_store(tmp_path: Path) -> LocalJsonMetadataStore:
    return LocalJsonMetadataStore(
        global_config_dir=tmp_path / "global-config",
        workspaces_root=tmp_path / "workspaces",
    )


@pytest.mark.anyio
async def test_app_settings_returns_defaults_when_file_missing(
    metadata_store: LocalJsonMetadataStore,
) -> None:
    assert await metadata_store.read_app_settings() == AppSettings()


@pytest.mark.anyio
async def test_app_settings_roundtrip(metadata_store: LocalJsonMetadataStore) -> None:
    settings = AppSettings(
        user_id="studio-user",
        gitea_host="https://gitea.example.test",
        default_skills_directory="/Users/studio/Skills",
    )

    await metadata_store.write_app_settings(settings)

    assert await metadata_store.read_app_settings() == settings


@pytest.mark.anyio
async def test_app_settings_recovers_from_corrupt_json(
    metadata_store: LocalJsonMetadataStore,
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    settings_path = tmp_path / "global-config" / "app_settings.json"
    settings_path.parent.mkdir(parents=True)
    settings_path.write_text("{not json", encoding="utf-8")

    with caplog.at_level(logging.WARNING, logger="app.core.adapters.metadata_local"):
        settings = await metadata_store.read_app_settings()

    assert settings == AppSettings()
    assert "Invalid app settings JSON" in caplog.text


@pytest.mark.anyio
@pytest.mark.skipif(os.name == "nt", reason="POSIX mode bits do not model Windows ACLs")
async def test_app_settings_file_permissions_0o600(
    metadata_store: LocalJsonMetadataStore,
    tmp_path: Path,
) -> None:
    await metadata_store.write_app_settings(AppSettings(user_id="studio-user"))

    settings_path = tmp_path / "global-config" / "app_settings.json"
    assert stat.S_IMODE(settings_path.stat().st_mode) == 0o600
