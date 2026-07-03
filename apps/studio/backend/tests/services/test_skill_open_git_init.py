"""PR-A: opening a writable user skill makes it a standalone git repo.

Design: skill-repo-git-model (`docs/studio/mvp1/_proposal-skill-repo-git-model.md`).
Opening a skill (`get_skill_detail`, the GET /skills/{id} entry) auto-inits L1 git
when the resolved folder is a writable user skill with no `.git` yet, so Local
History reflects THAT skill's own history instead of bubbling up to an enclosing
repo. Read-only bundled skills (under SKILLS_DIR) are never touched, and a skill
that already has `.git` is left untouched (idempotent).
"""

from __future__ import annotations

from pathlib import Path

import pytest
from app.core import config
from app.core.adapters.metadata_local import LocalJsonMetadataStore
from app.core.adapters.storage_local import LocalFilesystemBackend
from app.services import skills as skill_service
from app.services.git_local import GitLocalService, initialize_skill_repository


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture
def metadata_store(tmp_path: Path) -> LocalJsonMetadataStore:
    return LocalJsonMetadataStore(
        global_config_dir=tmp_path / "global-config",
        workspaces_root=tmp_path / "workspaces",
    )


def _isolate_roots(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Point config at tmp roots; return the (empty) bundled SKILLS_DIR."""
    skills_root = tmp_path / "skills"
    skills_root.mkdir(exist_ok=True)
    monkeypatch.setattr(config, "SKILLS_DIR", skills_root)
    monkeypatch.setattr(config, "WORKSPACES_DIR", tmp_path / "workspaces")
    monkeypatch.setattr(config, "APP_SETTINGS_PATH", tmp_path / "global-config" / "app_settings.json")
    return skills_root


async def _register_user_skill(
    metadata_store: LocalJsonMetadataStore, skill_id: str, skill_dir: Path
) -> None:
    await metadata_store.save_skill_index_entry(
        skill_id, {"absolute_path": str(skill_dir), "l2_remote_url": ""}
    )


@pytest.mark.anyio
async def test_opening_user_skill_without_git_auto_inits_repo(
    tmp_path: Path,
    metadata_store: LocalJsonMetadataStore,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _isolate_roots(tmp_path, monkeypatch)
    # A user skill OUTSIDE the bundled SKILLS_DIR (as a coding/skill/ folder would be),
    # registered by absolute path in the index, with NO .git yet.
    skill_dir = tmp_path / "coding" / "skill" / "seg"
    _write_graph_skill(skill_dir, "seg")
    await _register_user_skill(metadata_store, "seg", skill_dir)
    assert not (skill_dir / ".git").exists()

    await skill_service.get_skill_detail(
        "default", "seg", LocalFilesystemBackend(tmp_path), metadata_store
    )

    # Opening it turned the folder into a standalone git repo.
    assert (skill_dir / ".git").is_dir()
    assert GitLocalService().log(skill_dir), "expected the initial-skill commit"


@pytest.mark.anyio
async def test_opening_bundled_skill_does_not_init_git(
    tmp_path: Path,
    metadata_store: LocalJsonMetadataStore,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    skills_root = _isolate_roots(tmp_path, monkeypatch)
    # Read-only bundled sample content lives UNDER SKILLS_DIR — never write a .git
    # into the app tree.
    skill_dir = skills_root / "text-segmentation"
    _write_graph_skill(skill_dir, "text-segmentation")

    await skill_service.get_skill_detail(
        "default", "text-segmentation", LocalFilesystemBackend(tmp_path), metadata_store
    )

    assert not (skill_dir / ".git").exists()


@pytest.mark.anyio
async def test_opening_skill_with_existing_git_is_idempotent(
    tmp_path: Path,
    metadata_store: LocalJsonMetadataStore,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _isolate_roots(tmp_path, monkeypatch)
    skill_dir = tmp_path / "coding" / "skill" / "seg"
    _write_graph_skill(skill_dir, "seg")
    initialize_skill_repository(skill_dir)
    await _register_user_skill(metadata_store, "seg", skill_dir)
    log_before = GitLocalService().log(skill_dir)

    await skill_service.get_skill_detail(
        "default", "seg", LocalFilesystemBackend(tmp_path), metadata_store
    )

    # Re-opening an already-initialized skill must not add another initial commit.
    assert GitLocalService().log(skill_dir) == log_before


def _write_graph_skill(skill_dir: Path, name: str) -> None:
    (skill_dir / "phases" / "setup").mkdir(parents=True)
    (skill_dir / "GRAPH.md").write_text(
        f"""---
schema_version: "v0.3.0"
name: {name}
description: Test skill
io:
  inputs:
    type: object
    properties: {{}}
  outputs:
    type: object
    properties: {{}}
phases:
  - setup
---
<phase depends_on="input" output>setup</phase>
""",
        encoding="utf-8",
    )
    (skill_dir / "phases" / "setup" / "LOGIC.md").write_text(
        """---
io:
  inputs:
    type: object
    properties: {}
  outputs:
    type: object
    properties: {}
---
""",
        encoding="utf-8",
    )
