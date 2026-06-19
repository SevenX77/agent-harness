"""Home list de-registration: truth = opened/imported-folder index, not a /skills registry scan.

Design authority:
- docs/studio/mvp1/02_capabilities/skill-workspace/mvp1-alignment.md §F1/§3/§8
- docs/studio/mvp1/02_capabilities/skill-workspace/baseline.md L37
- docs/studio/mvp1/01_workflows/01_init.md D11 (锁 IDE/workspace 模型, 无注册表) / D1

Home is an IDE workspace switcher, not a registry browser: it lists only the
folders the user explicitly opened/imported/created (recorded in the native-fs
skill index + saved summaries), never an auto-scan of the bundled SKILLS_DIR.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from app.core import config
from app.core.adapters.metadata_local import LocalJsonMetadataStore
from app.core.adapters.storage_local import LocalFilesystemBackend
from app.services import skills as skill_service
from fastapi.testclient import TestClient


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture
def metadata_store(tmp_path: Path) -> LocalJsonMetadataStore:
    return LocalJsonMetadataStore(
        global_config_dir=tmp_path / "global-config",
        workspaces_root=tmp_path / "workspaces",
    )


def _write_graph_skill(skill_dir: Path, name: str) -> None:
    (skill_dir / "phases" / "setup").mkdir(parents=True)
    (skill_dir / "GRAPH.md").write_text(
        f"""---
schema_version: "v0.3.0"
name: {name}
description: Bundled skill
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


@pytest.mark.anyio
async def test_home_does_not_auto_list_unopened_bundled_skill(
    tmp_path: Path,
    metadata_store: LocalJsonMetadataStore,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # D11/D1: Home is an IDE switcher, not a registry browser. A skill that lives
    # under the bundled SKILLS_DIR but was never opened/imported must NOT appear.
    skills_root = tmp_path / "skills"
    _write_graph_skill(skills_root / "bundled-never-opened", "bundled-never-opened")
    monkeypatch.setattr(config, "SKILLS_DIR", skills_root)
    monkeypatch.setattr(config, "WORKSPACES_DIR", tmp_path / "workspaces")

    summaries = await skill_service.list_skill_summaries(
        "default",
        LocalFilesystemBackend(tmp_path),
        metadata_store,
    )

    assert "bundled-never-opened" not in {summary.id for summary in summaries}


@pytest.mark.anyio
async def test_home_lists_folder_recorded_in_skill_index(
    tmp_path: Path,
    metadata_store: LocalJsonMetadataStore,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Native-fs opens a folder by recording it in the skill index (Rust-owned MRU).
    # Home truth source is that index — the folder must surface even with no saved
    # summary JSON yet.
    monkeypatch.setattr(config, "SKILLS_DIR", tmp_path / "skills")
    monkeypatch.setattr(config, "WORKSPACES_DIR", tmp_path / "workspaces")
    opened_dir = tmp_path / "external" / "opened-folder"
    _write_graph_skill(opened_dir, "opened-folder")
    await metadata_store.save_skill_index_entry(
        "opened-folder",
        {"absolute_path": str(opened_dir), "l2_remote_url": ""},
    )

    summaries = await skill_service.list_skill_summaries(
        "default",
        LocalFilesystemBackend(tmp_path),
        metadata_store,
    )

    matched = [summary for summary in summaries if summary.id == "opened-folder"]
    assert matched, "folder recorded in the skill index must appear on Home"
    assert matched[0].directory_path == str(opened_dir)


@pytest.mark.anyio
async def test_home_lists_imported_manifestless_folder_from_index(
    tmp_path: Path,
    metadata_store: LocalJsonMetadataStore,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # A manifest-less folder imported into repair state (D2) is recorded in the
    # index without a GRAPH.md; Home still lists it as a repairable workspace entry.
    monkeypatch.setattr(config, "SKILLS_DIR", tmp_path / "skills")
    monkeypatch.setattr(config, "WORKSPACES_DIR", tmp_path / "workspaces")
    imported_dir = tmp_path / "external" / "repairable"
    imported_dir.mkdir(parents=True)
    (imported_dir / "notes.txt").write_text("plain folder\n", encoding="utf-8")
    await metadata_store.save_skill_index_entry(
        "repairable",
        {"absolute_path": str(imported_dir), "l2_remote_url": ""},
    )

    summaries = await skill_service.list_skill_summaries(
        "default",
        LocalFilesystemBackend(tmp_path),
        metadata_store,
    )

    matched = [summary for summary in summaries if summary.id == "repairable"]
    assert matched, "imported repair-state folder must appear on Home"
    assert matched[0].phase_count == 0
    assert matched[0].description == ""


def test_api_skills_omits_unopened_bundled_skill_lists_opened(
    client: TestClient,
    studio_roots: tuple[Path, Path],
    tmp_path: Path,
) -> None:
    # Router layer: GET /api/skills returns only opened/imported folders. The
    # studio_roots fixture seeds bundled skills into SKILLS_DIR — none are opened,
    # so the list starts empty. Importing a folder makes exactly that one appear.
    skills_dir, _workspaces_dir = studio_roots

    before = client.get("/api/skills")
    assert before.status_code == 200
    bundled_ids = {entry.name for entry in skills_dir.iterdir() if entry.is_dir()}
    listed_before = {item["id"] for item in before.json()}
    assert not (bundled_ids & listed_before), "unopened bundled skills must not auto-list"

    imported_dir = tmp_path / "external" / "imported-via-api"
    imported_dir.mkdir(parents=True)
    (imported_dir / "notes.txt").write_text("plain\n", encoding="utf-8")
    create = client.post(
        "/api/skills",
        json={
            "skill_id": "imported-via-api",
            "directory_path": str(imported_dir),
            "import_existing": True,
        },
    )
    assert create.status_code == 201, create.json()

    after = client.get("/api/skills")
    assert after.status_code == 200
    assert "imported-via-api" in {item["id"] for item in after.json()}
