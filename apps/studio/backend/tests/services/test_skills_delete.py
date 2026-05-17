from __future__ import annotations

from pathlib import Path

import pytest
from fastapi import HTTPException

from app.core.adapters.metadata_local import LocalJsonMetadataStore
from app.core.adapters.storage_local import LocalFilesystemBackend
from app.models.skills import SkillSummary
from app.services.skills import delete_skill


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.mark.anyio
async def test_delete_skill_removes_workspace_skill(
    studio_roots: tuple[Path, Path],
    tmp_path: Path,
) -> None:
    _skills_dir, workspaces_dir = studio_roots
    user_id = "default"
    skill_id = "workspace-skill"
    skill_dir = workspaces_dir / user_id / "skills" / skill_id
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text("---\nname: workspace-skill\n---\n", encoding="utf-8")
    (skill_dir / ".workspace" / "runs").mkdir(parents=True)

    metadata = LocalJsonMetadataStore(
        global_config_dir=tmp_path / "global-config",
        workspaces_root=workspaces_dir,
    )
    storage = LocalFilesystemBackend(tmp_path)
    await metadata.save_skill_index_entry(
        skill_id,
        {"absolute_path": str(skill_dir), "l2_remote_url": ""},
    )
    await metadata.save_skill_summary(
        user_id,
        SkillSummary(
            id=skill_id,
            name="Workspace skill",
            description="",
            phase_count=0,
            has_golden=False,
            directory_path=str(skill_dir),
        ),
    )

    await delete_skill(user_id, skill_id, storage, metadata)

    assert not skill_dir.exists()
    assert await metadata.get_skill_index_entry(skill_id) is None
    assert await metadata.get_skill_summary(user_id, skill_id) is None


@pytest.mark.anyio
async def test_delete_skill_rejects_builtin_public_skill(
    studio_roots: tuple[Path, Path],
    tmp_path: Path,
) -> None:
    skills_dir, workspaces_dir = studio_roots
    skill_id = "text-segmentation"
    skill_dir = skills_dir / skill_id
    metadata = LocalJsonMetadataStore(
        global_config_dir=tmp_path / "global-config",
        workspaces_root=workspaces_dir,
    )
    storage = LocalFilesystemBackend(tmp_path)

    with pytest.raises(HTTPException) as exc_info:
        await delete_skill("default", skill_id, storage, metadata)

    assert exc_info.value.status_code == 403
    assert exc_info.value.detail["error_code"] == "SKILL_READ_ONLY"
    assert (skill_dir / "SKILL.md").exists()
    assert skill_dir.exists()
