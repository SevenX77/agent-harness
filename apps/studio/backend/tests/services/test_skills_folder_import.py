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


@pytest.mark.anyio
async def test_list_skill_ids_includes_folder_skills_without_graph(tmp_path: Path) -> None:
    root = tmp_path / "skills"
    (root / "v1-skill").mkdir(parents=True)
    (root / "v1-skill" / "SKILL.md").write_text("# V1\n", encoding="utf-8")
    _write_graph_skill(root / "v21-skill", "v21-skill")
    (root / ".hidden").mkdir()
    (root / "__pycache__").mkdir()

    storage = LocalFilesystemBackend(tmp_path)

    assert await skill_service._list_skill_ids(root, storage) == ["v1-skill", "v21-skill"]


@pytest.mark.anyio
async def test_create_new_skill_imports_existing_nonempty_directory_without_writing(
    tmp_path: Path,
    metadata_store: LocalJsonMetadataStore,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    skill_dir = tmp_path / "external" / "story-deconstruction-imported"
    skill_dir.mkdir(parents=True)
    skill_path = skill_dir / "SKILL.md"
    original_content = "# Story Deconstruction\n"
    skill_path.write_text(original_content, encoding="utf-8")

    def fail_write(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("write_skill_files_atomic must not run for pure imports")

    monkeypatch.setattr(skill_service, "write_skill_files_atomic", fail_write)
    storage = LocalFilesystemBackend(tmp_path)

    summary = await skill_service.create_new_skill(
        "default",
        "story-deconstruction-imported",
        {},
        storage,
        metadata_store,
        directory_path=str(skill_dir),
        import_existing=True,
    )

    assert summary.id == "story-deconstruction-imported"
    assert summary.directory_path == str(skill_dir)
    assert summary.description == ""
    assert summary.phase_count == 0
    assert skill_path.read_text(encoding="utf-8") == original_content
    assert not (skill_dir / "GRAPH.md").exists()
    assert not (skill_dir / ".git").exists()
    assert await metadata_store.get_skill_index_entry("story-deconstruction-imported") == {
        "absolute_path": str(skill_dir),
        "l2_remote_url": "",
    }
    # The legacy per-user summary registry is retired: the skill_index is the only
    # persisted truth and no skill_summary.json is written.
    assert not list(skill_dir.rglob("skill_summary.json"))


def test_create_skill_import_allows_non_skill_directory_into_repair_state(
    client: TestClient,
    tmp_path: Path,
) -> None:
    # WELCOME-2 / F2 / D2 (FROZEN): "Open folder" must not block on file shape.
    # A non-skill folder (no GRAPH.md/SKILL.md) imports into a repair state instead
    # of being hard-rejected — compile/copilot normalize it later.
    skill_dir = tmp_path / "external" / "not-a-skill"
    skill_dir.mkdir(parents=True)
    (skill_dir / "notes.txt").write_text("plain folder\n", encoding="utf-8")

    response = client.post(
        "/api/skills",
        json={
            "skill_id": "not-a-skill",
            "directory_path": str(skill_dir),
            "import_existing": True,
        },
    )

    assert response.status_code == 201
    body = response.json()
    assert body["id"] == "not-a-skill"
    assert body["directory_path"] == str(skill_dir)
    # Repair state: no manifest yet, so no phases and an empty description.
    assert body["phase_count"] == 0
    assert body["description"] == ""
    # Import must not scaffold a manifest behind the user's back.
    assert not (skill_dir / "GRAPH.md").exists()


def test_import_skill_allows_empty_directory_into_repair_state(
    client: TestClient,
    tmp_path: Path,
) -> None:
    # D2: opening ANY folder (including an empty one) must reach Workspace in a
    # repair state rather than being rejected for missing root docs.
    skill_dir = tmp_path / "external" / "empty-folder"
    skill_dir.mkdir(parents=True)

    response = client.post(
        "/api/skills",
        json={
            "skill_id": "empty-folder",
            "directory_path": str(skill_dir),
            "import_existing": True,
        },
    )

    assert response.status_code == 201
    body = response.json()
    assert body["id"] == "empty-folder"
    assert body["phase_count"] == 0
    assert not (skill_dir / "GRAPH.md").exists()


def test_import_skill_allows_invalid_graph_without_lint_gate(
    client: TestClient,
    tmp_path: Path,
) -> None:
    skill_dir = tmp_path / "external" / "bad-graph"
    (skill_dir / "phases" / "init").mkdir(parents=True)
    (skill_dir / "GRAPH.md").write_text(
        """---
schema_version: "v0.3.0"
name: bad-graph
io:
  inputs:
    type: object
    properties: {}
  outputs:
    type: object
    properties: {}
phases:
  - init
---
<phase depends_on="input" output>init</phase>
""",
        encoding="utf-8",
    )
    (skill_dir / "phases" / "init" / "LOGIC.md").write_text(
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

    response = client.post(
        "/api/skills",
        json={
            "skill_id": "bad-graph",
            "directory_path": str(skill_dir),
            "import_existing": True,
        },
    )

    assert response.status_code == 201
    body = response.json()
    assert body["id"] == "bad-graph"
    assert body["directory_path"] == str(skill_dir)


def test_create_skill_with_empty_directory_path_scaffolds(
    client: TestClient,
    tmp_path: Path,
) -> None:
    skill_dir = tmp_path / "external" / "blank-skill"
    skill_dir.mkdir(parents=True)

    response = client.post(
        "/api/skills",
        json={
            "skill_id": "blank-skill",
            "files": _valid_skill_files("blank-skill"),
            "directory_path": str(skill_dir),
        },
    )

    assert response.status_code == 201
    assert response.json()["directory_path"] == str(skill_dir)
    assert (skill_dir / "GRAPH.md").exists()
    assert (skill_dir / ".workspace").is_dir()
    assert (skill_dir / ".git").is_dir()


def test_create_skill_without_files_uses_valid_default_scaffold(
    client: TestClient,
    tmp_path: Path,
) -> None:
    skill_dir = tmp_path / "external" / "fresh-skill"
    skill_dir.parent.mkdir()

    response = client.post(
        "/api/skills",
        json={
            "skill_id": "fresh-skill",
            "directory_path": str(skill_dir),
        },
    )

    assert response.status_code == 201, response.json()
    assert response.json()["directory_path"] == str(skill_dir)
    assert (skill_dir / "GRAPH.md").exists()
    # D-1-4: the default scaffold is an empty agent phase (single SKILL.md the
    # engine routes to agent mode), not the old logic-phase LOGIC.md + actions.
    assert (skill_dir / "phases" / "init" / "SKILL.md").exists()
    assert not (skill_dir / "phases" / "init" / "LOGIC.md").exists()
    assert not (skill_dir / "phases" / "init" / "actions").exists()
    assert (skill_dir / ".workspace").is_dir()
    assert (skill_dir / ".git").is_dir()


def test_create_skill_without_directory_uses_settings_default_folder(
    client: TestClient,
    tmp_path: Path,
) -> None:
    parent_dir = tmp_path / "custom-skills"
    settings_response = client.put(
        "/api/settings",
        json={
            "user_id": "",
            "gitea_host": "",
            "default_skills_directory": str(parent_dir),
        },
    )
    assert settings_response.status_code == 200

    response = client.post(
        "/api/skills",
        json={
            "skill_id": "custom-default",
            "files": _valid_skill_files("custom-default"),
        },
    )

    skill_dir = parent_dir / "custom-default"
    assert response.status_code == 201, response.json()
    assert response.json()["directory_path"] == str(skill_dir)
    assert (skill_dir / "GRAPH.md").exists()
    assert (skill_dir / ".workspace").is_dir()
    assert (skill_dir / ".git").is_dir()


def test_create_skill_rejects_existing_public_v1_skill_id(
    client: TestClient,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    public_skill_dir = tmp_path / "public-skills" / "text-segmentation"
    public_skill_dir.mkdir(parents=True)
    (public_skill_dir / "SKILL.md").write_text("# Text segmentation\n", encoding="utf-8")
    monkeypatch.setattr(config, "SKILLS_DIR", tmp_path / "public-skills")

    parent_dir = tmp_path / "external"
    parent_dir.mkdir()
    response = client.post(
        "/api/skills",
        json={
            "skill_id": "text-segmentation",
            "directory_path": str(parent_dir / "text-segmentation"),
        },
    )

    assert response.status_code == 409
    assert response.json()["error_code"] == "SKILL_ALREADY_EXISTS"


def test_create_skill_with_missing_directory_path_scaffolds(
    client: TestClient,
    tmp_path: Path,
) -> None:
    parent_dir = tmp_path / "external"
    parent_dir.mkdir()
    skill_dir = parent_dir / "new-skill"

    response = client.post(
        "/api/skills",
        json={
            "skill_id": "new-skill",
            "files": _valid_skill_files("new-skill"),
            "directory_path": str(skill_dir),
        },
    )

    assert response.status_code == 201
    assert response.json()["directory_path"] == str(skill_dir)
    assert (skill_dir / "GRAPH.md").exists()
    assert (skill_dir / ".workspace").is_dir()
    assert (skill_dir / ".git").is_dir()


@pytest.mark.anyio
async def test_resolve_skill_dir_async_returns_v1_directory_without_graph(
    tmp_path: Path,
    metadata_store: LocalJsonMetadataStore,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    skills_root = tmp_path / "skills"
    skill_dir = skills_root / "story-deconstruction"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text("# Story Deconstruction\n", encoding="utf-8")
    monkeypatch.setattr(config, "SKILLS_DIR", skills_root)
    monkeypatch.setattr(config, "WORKSPACES_DIR", tmp_path / "workspaces")

    resolved = await skill_service.resolve_skill_dir_async(
        "default",
        "story-deconstruction",
        LocalFilesystemBackend(tmp_path),
        metadata_store,
    )

    assert resolved == skill_dir


def test_read_skill_files_returns_real_v1_tree_and_filters_noise(tmp_path: Path) -> None:
    skill_dir = tmp_path / "story-deconstruction"
    skill_dir.mkdir()
    (skill_dir / "SKILL.md").write_text("# Story Deconstruction\n", encoding="utf-8")
    (skill_dir / "nodes").mkdir()
    (skill_dir / "nodes" / "plot.md").write_text("# Plot\n", encoding="utf-8")
    (skill_dir / "script").mkdir()
    (skill_dir / "script" / "run.py").write_text("print('ok')\n", encoding="utf-8")
    (skill_dir / "data").mkdir()
    (skill_dir / "data" / "huge.txt").write_text("x" * (1024 * 1024 + 1), encoding="utf-8")
    (skill_dir / ".git").mkdir()
    (skill_dir / ".git" / "config").write_text("[core]\n", encoding="utf-8")
    (skill_dir / "__pycache__").mkdir()
    (skill_dir / "__pycache__" / "mod.pyc").write_bytes(b"cache")
    (skill_dir / ".DS_Store").write_text("noise", encoding="utf-8")
    (skill_dir / "binary.bin").write_bytes(b"\xff\xfe\x00")

    files = skill_service._read_skill_files(skill_dir)

    assert files["SKILL.md"] == "# Story Deconstruction\n"
    assert files["nodes/plot.md"] == "# Plot\n"
    assert files["script/run.py"] == "print('ok')\n"
    assert files["data/huge.txt"] == "(binary or too large)"
    assert ".git/config" not in files
    assert "__pycache__/mod.pyc" not in files
    assert ".DS_Store" not in files
    assert "binary.bin" not in files


@pytest.mark.anyio
async def test_get_skill_detail_returns_broken_detail_with_v1_files(
    tmp_path: Path,
    metadata_store: LocalJsonMetadataStore,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    skills_root = tmp_path / "skills"
    skill_dir = skills_root / "story-deconstruction"
    (skill_dir / "nodes").mkdir(parents=True)
    (skill_dir / "script").mkdir()
    (skill_dir / "SKILL.md").write_text("# Story Deconstruction\n", encoding="utf-8")
    (skill_dir / "nodes" / "plot.md").write_text("# Plot\n", encoding="utf-8")
    (skill_dir / "script" / "run.py").write_text("print('ok')\n", encoding="utf-8")
    monkeypatch.setattr(config, "SKILLS_DIR", skills_root)
    monkeypatch.setattr(config, "WORKSPACES_DIR", tmp_path / "workspaces")

    detail = await skill_service.get_skill_detail(
        "default",
        "story-deconstruction",
        LocalFilesystemBackend(tmp_path),
        metadata_store,
    )

    assert detail.manifest.name == "story-deconstruction"
    assert detail.lint_result is not None
    assert detail.lint_result.status == "failed"
    assert detail.files["SKILL.md"] == "# Story Deconstruction\n"
    assert detail.files["nodes/plot.md"] == "# Plot\n"
    assert detail.files["script/run.py"] == "print('ok')\n"


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


def _valid_skill_files(skill_id: str) -> dict[str, str]:
    return {
        "GRAPH.md": f"""---
schema_version: "v0.3.0"
name: {skill_id}
description: Test skill
io:
  inputs:
    type: object
    properties: {{}}
  outputs:
    type: object
    properties:
      prepared:
        type: boolean
phases:
  - setup
---
<phase depends_on="input" output>setup</phase>
""",
        "phases/setup/LOGIC.md": """---
io:
  inputs:
    type: object
    properties: {}
  outputs:
    type: object
    properties:
      prepared:
        type: boolean
---
<action>prepare</action>
""",
        "phases/setup/actions/prepare.py": """def prepare(inputs):
    return {"prepared": True}
""",
    }



