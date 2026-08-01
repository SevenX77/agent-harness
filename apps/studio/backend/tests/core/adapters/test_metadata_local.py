from __future__ import annotations

import logging
import os
import stat
from datetime import UTC, datetime
from pathlib import Path

import pytest
from app.core.adapters.metadata_local import LocalJsonMetadataStore
from app.models.runs import RunMetadata
from app.models.settings import AppSettings


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture
def metadata_store(tmp_path: Path) -> LocalJsonMetadataStore:
    return LocalJsonMetadataStore(
        global_config_dir=tmp_path / "global-config",
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


def _run_metadata(run_id: str) -> RunMetadata:
    return RunMetadata(
        run_id=run_id,
        status="success",
        started_at=datetime(2026, 7, 31, 12, 0, 0, tzinfo=UTC),
    )


@pytest.mark.anyio
async def test_run_metadata_roundtrip_uses_indexed_skill_workspace(
    metadata_store: LocalJsonMetadataStore,
    tmp_path: Path,
) -> None:
    skill_dir = tmp_path / "opened-skill"
    skill_dir.mkdir()
    await metadata_store.save_skill_index_entry(
        "opened-skill",
        {"absolute_path": str(skill_dir), "l2_remote_url": ""},
    )

    await metadata_store.save_run_metadata("default", "opened-skill", _run_metadata("run-1"))

    assert (skill_dir / ".workspace" / "runs" / "run-1" / "run_metadata.json").is_file()
    assert [run.run_id for run in await metadata_store.list_runs("default", "opened-skill")] == [
        "run-1"
    ]


@pytest.mark.anyio
async def test_list_runs_returns_empty_for_unregistered_skill(
    metadata_store: LocalJsonMetadataStore,
) -> None:
    assert await metadata_store.list_runs("default", "unregistered-skill") == []


@pytest.mark.anyio
async def test_save_run_metadata_rejects_unregistered_skill(
    metadata_store: LocalJsonMetadataStore,
    tmp_path: Path,
) -> None:
    # The retired fallback silently persisted run metadata into the legacy
    # workspaces/{user}/skills/{skill_id} layout nothing reads anymore.
    with pytest.raises(LookupError, match="not registered"):
        await metadata_store.save_run_metadata(
            "default", "unregistered-skill", _run_metadata("run-1")
        )

    assert not list(tmp_path.rglob("run_metadata.json"))


@pytest.mark.anyio
@pytest.mark.skipif(os.name == "nt", reason="POSIX mode bits do not model Windows ACLs")
async def test_app_settings_file_permissions_0o600(
    metadata_store: LocalJsonMetadataStore,
    tmp_path: Path,
) -> None:
    await metadata_store.write_app_settings(AppSettings(user_id="studio-user"))

    settings_path = tmp_path / "global-config" / "app_settings.json"
    assert stat.S_IMODE(settings_path.stat().st_mode) == 0o600
