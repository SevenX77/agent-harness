from __future__ import annotations

import json
from pathlib import Path

import pytest
from app.core.adapters.metadata_local import LocalJsonMetadataStore


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
async def test_skill_index_starts_empty(metadata_store: LocalJsonMetadataStore) -> None:
    assert await metadata_store.list_skill_index() == {}
    assert await metadata_store.get_skill_index_entry("missing") is None


@pytest.mark.anyio
async def test_save_skill_index_entry_writes_json(
    metadata_store: LocalJsonMetadataStore,
    tmp_path: Path,
) -> None:
    skill_dir = tmp_path / "Skills" / "idea-generator"

    await metadata_store.save_skill_index_entry(
        "idea-generator",
        {"absolute_path": str(skill_dir), "l2_remote_url": ""},
    )

    assert await metadata_store.get_skill_index_entry("idea-generator") == {
        "absolute_path": str(skill_dir),
        "l2_remote_url": "",
    }
    index_path = tmp_path / "global-config" / "skill_index.json"
    assert json.loads(index_path.read_text(encoding="utf-8")) == {
        "idea-generator": {"absolute_path": str(skill_dir), "l2_remote_url": ""}
    }


@pytest.mark.anyio
async def test_save_skill_index_entry_overwrites_existing(
    metadata_store: LocalJsonMetadataStore,
    tmp_path: Path,
) -> None:
    first_dir = tmp_path / "one"
    second_dir = tmp_path / "two"

    await metadata_store.save_skill_index_entry(
        "idea-generator",
        {"absolute_path": str(first_dir), "l2_remote_url": ""},
    )
    await metadata_store.save_skill_index_entry(
        "idea-generator",
        {"absolute_path": str(second_dir), "l2_remote_url": "https://example.invalid/repo"},
    )

    assert await metadata_store.get_skill_index_entry("idea-generator") == {
        "absolute_path": str(second_dir),
        "l2_remote_url": "https://example.invalid/repo",
    }


@pytest.mark.anyio
async def test_remove_skill_index_entry(metadata_store: LocalJsonMetadataStore, tmp_path: Path) -> None:
    await metadata_store.save_skill_index_entry(
        "idea-generator",
        {"absolute_path": str(tmp_path / "skill"), "l2_remote_url": ""},
    )

    await metadata_store.remove_skill_index_entry("idea-generator")

    assert await metadata_store.list_skill_index() == {}


@pytest.mark.anyio
async def test_skill_index_bad_json_returns_empty(tmp_path: Path) -> None:
    global_config_dir = tmp_path / "global-config"
    global_config_dir.mkdir()
    (global_config_dir / "skill_index.json").write_text("{not json", encoding="utf-8")
    metadata_store = LocalJsonMetadataStore(
        global_config_dir=global_config_dir,
        workspaces_root=tmp_path / "workspaces",
    )

    assert await metadata_store.list_skill_index() == {}
