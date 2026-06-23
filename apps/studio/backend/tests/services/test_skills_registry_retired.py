"""The legacy per-user skill registry is retired; skill_index is the only truth.

These tests pin the end state of N14: `create_new_skill` / `delete_skill` /
`resolve_skill_dir_async` operate purely on the path-based skill_index, no
`skill_summary.json` is persisted anywhere, and the seven retired
`MetadataStore` registry methods are gone from the local adapter.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from app.core.adapters.metadata_local import LocalJsonMetadataStore
from app.core.adapters.storage_local import LocalFilesystemBackend
from app.services.skills import create_new_skill, delete_skill, resolve_skill_dir_async
from fastapi import HTTPException


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


def _make_metadata(tmp_path: Path, workspaces_dir: Path) -> LocalJsonMetadataStore:
    return LocalJsonMetadataStore(
        global_config_dir=tmp_path / "global-config",
        workspaces_root=workspaces_dir,
    )


@pytest.mark.anyio
async def test_create_new_skill_indexes_without_persisting_summary(
    studio_roots: tuple[Path, Path],
    tmp_path: Path,
) -> None:
    _skills_dir, workspaces_dir = studio_roots
    user_id = "default"
    skill_id = "indexed-skill"
    directory_path = tmp_path / "external" / skill_id
    directory_path.mkdir(parents=True)

    metadata = _make_metadata(tmp_path, workspaces_dir)
    storage = LocalFilesystemBackend(tmp_path)

    summary = await create_new_skill(
        user_id,
        skill_id,
        {},
        storage,
        metadata,
        directory_path=str(directory_path),
    )

    # The skill_index is the single truth.
    entry = await metadata.get_skill_index_entry(skill_id)
    assert entry is not None
    assert entry["absolute_path"] == str(directory_path)

    # The summary is still computed and returned as the HTTP DTO.
    assert summary.id == skill_id
    assert summary.directory_path == str(directory_path)

    # resolve_skill_dir_async finds the skill via the index.
    resolved = await resolve_skill_dir_async(user_id, skill_id, storage, metadata)
    assert resolved == directory_path

    # No skill_summary.json is persisted anywhere under the workspaces root.
    assert not list(workspaces_dir.rglob("skill_summary.json"))


@pytest.mark.anyio
async def test_delete_skill_removes_index_entry_keeping_source(
    studio_roots: tuple[Path, Path],
    tmp_path: Path,
) -> None:
    _skills_dir, workspaces_dir = studio_roots
    user_id = "default"
    skill_id = "deletable-skill"
    directory_path = tmp_path / "external" / skill_id
    directory_path.mkdir(parents=True)

    metadata = _make_metadata(tmp_path, workspaces_dir)
    storage = LocalFilesystemBackend(tmp_path)

    await create_new_skill(
        user_id,
        skill_id,
        {},
        storage,
        metadata,
        directory_path=str(directory_path),
    )
    assert await metadata.get_skill_index_entry(skill_id) is not None

    await delete_skill(user_id, skill_id, storage, metadata)

    assert await metadata.get_skill_index_entry(skill_id) is None
    # Source dir + files survive — delete only un-indexes.
    assert directory_path.exists()
    assert (directory_path / "GRAPH.md").exists()


@pytest.mark.anyio
async def test_second_skill_on_same_directory_conflicts_via_index_guard(
    studio_roots: tuple[Path, Path],
    tmp_path: Path,
) -> None:
    _skills_dir, workspaces_dir = studio_roots
    user_id = "default"
    directory_path = tmp_path / "external" / "shared-folder"
    directory_path.mkdir(parents=True)

    metadata = _make_metadata(tmp_path, workspaces_dir)
    storage = LocalFilesystemBackend(tmp_path)

    await create_new_skill(
        user_id,
        "first-skill",
        {},
        storage,
        metadata,
        directory_path=str(directory_path),
    )

    with pytest.raises(HTTPException) as exc_info:
        await create_new_skill(
            user_id,
            "second-skill",
            {},
            storage,
            metadata,
            directory_path=str(directory_path),
        )

    assert exc_info.value.status_code == 409
    assert exc_info.value.detail["error_code"] == "SKILL_ALREADY_EXISTS"


def test_retired_registry_methods_are_gone() -> None:
    for name in (
        "list_unregistered_skill_ids",
        "unregister_skill",
        "register_skill",
        "list_skills",
        "get_skill_summary",
        "save_skill_summary",
        "remove_skill_summary",
    ):
        assert not hasattr(LocalJsonMetadataStore, name), f"{name} must be retired"
