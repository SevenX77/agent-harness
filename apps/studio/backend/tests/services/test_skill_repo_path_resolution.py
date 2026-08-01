from __future__ import annotations

from pathlib import Path

import pytest
from app.core import config
from app.core.adapters.engine import _PrivateStudioSkillResolver
from app.core.adapters.metadata_local import LocalJsonMetadataStore
from app.core.adapters.storage_local import LocalFilesystemBackend
from app.services.skill_resolver import StudioSkillResolver
from app.services.skills import resolve_skill_dir_async
from fastapi import HTTPException


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture
def isolated_paths(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    settings_dir = tmp_path / "settings"
    monkeypatch.setattr(config, "WORKSPACES_DIR", tmp_path / "workspaces")
    monkeypatch.setattr(config, "SKILL_INDEX_PATH", settings_dir / "skill_index.json")
    monkeypatch.setattr(config, "DEFAULT_SKILLS_ROOT", settings_dir / "Skills")
    return tmp_path / "workspaces" / config.DEFAULT_USER_ID / "skills"


def test_service_resolver_requires_indexed_absolute_path(isolated_paths: Path) -> None:
    _write_minimal_skill(isolated_paths / "legacy-workspace-skill")

    with pytest.raises(Exception, match="not registered in Studio"):
        StudioSkillResolver().resolve_skill("legacy-workspace-skill")


def test_engine_private_resolver_requires_indexed_absolute_path(isolated_paths: Path) -> None:
    _write_minimal_skill(isolated_paths / "legacy-workspace-skill")

    with pytest.raises(Exception, match="not registered in Studio"):
        _PrivateStudioSkillResolver().resolve_skill("legacy-workspace-skill")


@pytest.mark.anyio
async def test_resolve_skill_dir_async_requires_index_entry(
    tmp_path: Path,
    isolated_paths: Path,
) -> None:
    _write_minimal_skill(isolated_paths / "legacy-workspace-skill")
    metadata = LocalJsonMetadataStore(
        global_config_dir=tmp_path / "settings",
    )

    with pytest.raises(HTTPException) as exc_info:
        await resolve_skill_dir_async(
            "default",
            "legacy-workspace-skill",
            LocalFilesystemBackend(tmp_path),
            metadata,
        )

    assert exc_info.value.detail["error_code"] == "SKILL_NOT_FOUND"


def _write_minimal_skill(skill_dir: Path) -> None:
    skill_dir.mkdir(parents=True)
    (skill_dir / "GRAPH.md").write_text("placeholder\n", encoding="utf-8")
