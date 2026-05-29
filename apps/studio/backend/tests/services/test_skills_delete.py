from __future__ import annotations

from pathlib import Path

import pytest
from app.core.adapters.metadata_local import LocalJsonMetadataStore
from app.core.adapters.storage_local import LocalFilesystemBackend
from app.models.skills import SkillSummary
from app.services.skills import delete_skill, list_skill_summaries
from fastapi import HTTPException


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.mark.anyio
async def test_delete_skill_unregisters_workspace_skill_without_removing_files(
    studio_roots: tuple[Path, Path],
    tmp_path: Path,
) -> None:
    _skills_dir, workspaces_dir = studio_roots
    user_id = "default"
    skill_id = "workspace-skill"
    skill_dir = workspaces_dir / user_id / "skills" / skill_id
    skill_dir.mkdir(parents=True)
    (skill_dir / "GRAPH.md").write_text("---\nname: workspace-skill\n---\n", encoding="utf-8")
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

    assert skill_dir.exists()
    assert (skill_dir / "GRAPH.md").exists()
    assert (skill_dir / ".workspace" / "runs").exists()
    assert await metadata.get_skill_index_entry(skill_id) is None
    assert await metadata.get_skill_summary(user_id, skill_id) is None
    summaries = await list_skill_summaries(user_id, storage, metadata)
    assert skill_id not in {summary.id for summary in summaries}


@pytest.mark.anyio
async def test_delete_skill_unregisters_builtin_public_skill_without_removing_files(
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

    await delete_skill("default", skill_id, storage, metadata)

    assert (skill_dir / "GRAPH.md").exists()
    assert skill_dir.exists()
    summaries = await list_skill_summaries("default", storage, metadata)
    assert skill_id not in {summary.id for summary in summaries}


@pytest.mark.anyio
async def test_delete_skill_rejects_path_traversal_without_removing_files(
    studio_roots: tuple[Path, Path],
    tmp_path: Path,
) -> None:
    skills_dir, workspaces_dir = studio_roots
    metadata = LocalJsonMetadataStore(
        global_config_dir=tmp_path / "global-config",
        workspaces_root=workspaces_dir,
    )
    storage = LocalFilesystemBackend(tmp_path)

    with pytest.raises(HTTPException) as exc_info:
        await delete_skill("default", "..", storage, metadata)

    assert exc_info.value.status_code == 400
    assert skills_dir.exists()
