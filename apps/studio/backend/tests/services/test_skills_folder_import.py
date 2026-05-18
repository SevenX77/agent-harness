from __future__ import annotations

import json
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
    skill_dir = tmp_path / "external" / "story-deconstruction"
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
        "story-deconstruction",
        {},
        storage,
        metadata_store,
        directory_path=str(skill_dir),
    )

    assert summary.id == "story-deconstruction"
    assert summary.directory_path == str(skill_dir)
    assert summary.description == ""
    assert summary.phase_count == 0
    assert skill_path.read_text(encoding="utf-8") == original_content
    assert not (skill_dir / "GRAPH.md").exists()
    assert not (skill_dir / ".git").exists()
    assert await metadata_store.get_skill_index_entry("story-deconstruction") == {
        "absolute_path": str(skill_dir),
        "l2_remote_url": "",
    }
    assert await metadata_store.get_skill_summary("default", "story-deconstruction") == summary


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
async def test_list_skill_summaries_returns_minimal_summary_for_v1_skill(
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

    summaries = await skill_service.list_skill_summaries(
        "default",
        LocalFilesystemBackend(tmp_path),
        metadata_store,
    )

    assert [summary.id for summary in summaries] == ["story-deconstruction"]
    assert summaries[0].name == "story-deconstruction"
    assert summaries[0].description == ""
    assert summaries[0].phase_count == 0


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
    (skill_dir / "io").mkdir()
    (skill_dir / "GRAPH.md").write_text(
        f"""---
schema_version: "2.1"
name: {name}
description: Test skill
---
<input src="io/inputs.json" />
<output src="io/outputs.json" />
<phase id="setup" src="phases/setup" depends_on="" />
""",
        encoding="utf-8",
    )
    (skill_dir / "io" / "inputs.json").write_text(json.dumps({}), encoding="utf-8")
    (skill_dir / "io" / "outputs.json").write_text(json.dumps({}), encoding="utf-8")
    (skill_dir / "phases" / "setup" / "LOGIC.md").write_text(
        """---
mode: logic
name: setup
---
""",
        encoding="utf-8",
    )


def _valid_skill_files(skill_id: str) -> dict[str, str]:
    return {
        "GRAPH.md": f"""---
schema_version: "2.1"
name: {skill_id}
description: Test skill
---
<input src="io/inputs.json" />
<output src="io/outputs.json" />
<phase id="setup" src="phases/setup" depends_on="" />
""",
        "io/inputs.json": json.dumps({}),
        "io/outputs.json": json.dumps({}),
        "phases/setup/LOGIC.md": """---
mode: logic
name: setup
---
<python_callable>
prepare
</python_callable>
""",
        "phases/setup/actions/prepare.py": """def prepare(context):
    context.set("prepared", True)
    return {"prepared": True}
""",
    }
