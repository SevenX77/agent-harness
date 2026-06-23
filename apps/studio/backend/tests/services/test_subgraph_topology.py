from __future__ import annotations

from pathlib import Path

import pytest
from app.core.adapters.metadata_local import LocalJsonMetadataStore
from app.core.adapters.storage_local import LocalFilesystemBackend
from app.services import skills as skill_service
from fastapi.testclient import TestClient

from tests.conftest import copy_skill


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


def _write_child_graph(child_dir: Path, name: str) -> None:
    """Write a minimal two-phase child graph skill that compiles cleanly."""
    (child_dir / "phases" / "ingest" / "actions").mkdir(parents=True)
    (child_dir / "phases" / "ingest" / "actions" / "load.py").write_text(
        "def load(inputs):\n    return {'loaded': True}\n",
        encoding="utf-8",
    )
    (child_dir / "GRAPH.md").write_text(
        f"""---
schema_version: "v0.3.0"
name: {name}
description: Child graph for inline rendering
io:
  inputs:
    type: object
    required: [seed]
    properties:
      seed:
        type: string
  outputs:
    type: object
    required: [loaded]
    properties:
      loaded:
        type: boolean
phases:
  - ingest
---
<phase depends_on="input" output>ingest</phase>
""",
        encoding="utf-8",
    )
    (child_dir / "phases" / "ingest" / "LOGIC.md").write_text(
        """---
io:
  inputs:
    type: object
    properties:
      seed:
        type: string
  outputs:
    type: object
    properties:
      loaded:
        type: boolean
---
<action>load</action>
""",
        encoding="utf-8",
    )


def _add_subgraph_phase(parent_dir: Path, phase_name: str, child_path: str) -> None:
    """Add a subgraph phase to a parent graph that references a child by absolute path."""
    graph_md = parent_dir / "GRAPH.md"
    content = graph_md.read_text(encoding="utf-8")
    content = content.replace(
        "phases:\n  - setup\n",
        f"phases:\n  - setup\n  - {phase_name}\n",
    )
    content = content.replace(
        '<phase depends_on="input" output>setup</phase>\n',
        '<phase depends_on="input">setup</phase>\n'
        f'<phase depends_on="setup" output>{phase_name}</phase>\n',
    )
    graph_md.write_text(content, encoding="utf-8")
    phase_dir = parent_dir / "phases" / phase_name
    phase_dir.mkdir(parents=True)
    (phase_dir / "SUBGRAPH.md").write_text(
        f"""---
name: {phase_name}
path: {child_path}
io:
  inputs:
    type: object
    required: [input_text]
    properties:
      input_text:
        type: string
  outputs:
    type: object
    required: [loaded]
    properties:
      loaded:
        type: boolean
validator: false
---
""",
        encoding="utf-8",
    )


def test_subgraph_phase_topology_surfaces_absolute_path(
    client: TestClient,
    studio_roots: tuple[Path, Path],
    tmp_path: Path,
) -> None:
    skills_dir, workspaces_dir = studio_roots
    child_dir = tmp_path / "child_graphs" / "review_child"
    child_dir.mkdir(parents=True)
    _write_child_graph(child_dir, "review-child")

    parent_dir = copy_skill(skills_dir, workspaces_dir, "text-segmentation")
    _add_subgraph_phase(parent_dir, "review", str(child_dir))

    response = client.get("/api/skills/text-segmentation")

    assert response.status_code == 200
    topology = response.json()["graph_topology"]
    rows = {row["id"]: row for row in topology}
    assert rows["review"]["mode"] == "subgraph"
    # §2.1: the absolute child path is surfaced from the SUBGRAPH.md `path` field,
    # never the legacy `target_skill` field.
    assert rows["review"]["path"] == str(child_dir)


def test_subgraph_phase_topology_resolves_relative_path_to_absolute(
    client: TestClient,
    studio_roots: tuple[Path, Path],
) -> None:
    # The recommended in-skill form declares `path` relative to the skill root
    # (portable across machines / ephemeral relocation). The topology row must
    # still surface a RESOLVED ABSOLUTE path so the frontend's absolute-path
    # check renders the subgraph as resolved (green) instead of "missing".
    skills_dir, workspaces_dir = studio_roots
    parent_dir = copy_skill(skills_dir, workspaces_dir, "text-segmentation")
    child_dir = parent_dir / "subgraph" / "review_child"
    child_dir.mkdir(parents=True)
    _write_child_graph(child_dir, "review-child")
    _add_subgraph_phase(parent_dir, "review", "subgraph/review_child")

    response = client.get("/api/skills/text-segmentation")

    assert response.status_code == 200
    rows = {row["id"]: row for row in response.json()["graph_topology"]}
    assert rows["review"]["mode"] == "subgraph"
    assert rows["review"]["path"] == str(child_dir.resolve())


@pytest.mark.anyio
async def test_subgraph_path_for_phase_ignores_target_skill(tmp_path: Path) -> None:
    phase_dir = tmp_path / "skill" / "phases" / "review"
    phase_dir.mkdir(parents=True)
    (phase_dir / "SUBGRAPH.md").write_text(
        "---\ntarget_skill: legacy-child\nvalidator: false\n---\n",
        encoding="utf-8",
    )
    assert skill_service.read_subgraph_path(tmp_path / "skill", "review") is None


@pytest.mark.anyio
async def test_resolve_child_graph_topology_returns_child_phases(
    tmp_path: Path,
    metadata_store: LocalJsonMetadataStore,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.core import config

    skills_dir = tmp_path / "skills"
    workspaces_dir = tmp_path / "workspaces"
    skills_dir.mkdir()
    monkeypatch.setattr(config, "SKILLS_DIR", skills_dir)
    monkeypatch.setattr(config, "WORKSPACES_DIR", workspaces_dir)

    parent_dir = skills_dir / "parent"
    parent_dir.mkdir()
    (parent_dir / "GRAPH.md").write_text("placeholder\n", encoding="utf-8")

    child_dir = skills_dir / "child"
    child_dir.mkdir()
    _write_child_graph(child_dir, "child-graph")

    storage = LocalFilesystemBackend(tmp_path)
    result = await skill_service.get_child_graph_topology(
        "default",
        "parent",
        str(child_dir),
        storage,
        metadata_store,
    )

    assert result.path == str(child_dir.resolve())
    assert result.name == "child-graph"
    assert result.phases == ["ingest"]
    rows = {row["id"]: row for row in result.graph_topology}
    assert rows["ingest"]["mode"] == "logic"
    assert rows["ingest"]["depends_on"] == ["input"]


@pytest.mark.anyio
async def test_resolve_child_graph_topology_rejects_relative_path(
    tmp_path: Path,
    metadata_store: LocalJsonMetadataStore,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.core import config
    from fastapi import HTTPException

    skills_dir = tmp_path / "skills"
    skills_dir.mkdir()
    monkeypatch.setattr(config, "SKILLS_DIR", skills_dir)
    monkeypatch.setattr(config, "WORKSPACES_DIR", tmp_path / "workspaces")
    parent_dir = skills_dir / "parent"
    parent_dir.mkdir()
    (parent_dir / "GRAPH.md").write_text("placeholder\n", encoding="utf-8")

    storage = LocalFilesystemBackend(tmp_path)
    with pytest.raises(HTTPException) as exc_info:
        await skill_service.get_child_graph_topology(
            "default",
            "parent",
            "relative/child",
            storage,
            metadata_store,
        )
    assert exc_info.value.status_code == 422
    assert exc_info.value.detail["error_code"] == "SUBGRAPH_PATH_INVALID"


@pytest.mark.anyio
async def test_resolve_child_graph_topology_rejects_path_outside_boundary(
    tmp_path: Path,
    metadata_store: LocalJsonMetadataStore,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.core import config
    from fastapi import HTTPException

    skills_dir = tmp_path / "skills"
    skills_dir.mkdir()
    monkeypatch.setattr(config, "SKILLS_DIR", skills_dir)
    monkeypatch.setattr(config, "WORKSPACES_DIR", tmp_path / "workspaces")
    parent_dir = skills_dir / "parent"
    parent_dir.mkdir()
    (parent_dir / "GRAPH.md").write_text("placeholder\n", encoding="utf-8")

    outside_dir = tmp_path / "outside" / "child"
    outside_dir.mkdir(parents=True)
    _write_child_graph(outside_dir, "outside-child")

    storage = LocalFilesystemBackend(tmp_path)
    with pytest.raises(HTTPException) as exc_info:
        await skill_service.get_child_graph_topology(
            "default",
            "parent",
            str(outside_dir),
            storage,
            metadata_store,
        )
    assert exc_info.value.status_code == 422
    assert exc_info.value.detail["error_code"] == "SUBGRAPH_PATH_INVALID"


@pytest.mark.anyio
async def test_resolve_child_graph_topology_missing_graph_md(
    tmp_path: Path,
    metadata_store: LocalJsonMetadataStore,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.core import config
    from fastapi import HTTPException

    skills_dir = tmp_path / "skills"
    skills_dir.mkdir()
    monkeypatch.setattr(config, "SKILLS_DIR", skills_dir)
    monkeypatch.setattr(config, "WORKSPACES_DIR", tmp_path / "workspaces")
    parent_dir = skills_dir / "parent"
    parent_dir.mkdir()
    (parent_dir / "GRAPH.md").write_text("placeholder\n", encoding="utf-8")

    empty_child = skills_dir / "empty-child"
    empty_child.mkdir()

    storage = LocalFilesystemBackend(tmp_path)
    with pytest.raises(HTTPException) as exc_info:
        await skill_service.get_child_graph_topology(
            "default",
            "parent",
            str(empty_child),
            storage,
            metadata_store,
        )
    assert exc_info.value.status_code == 404
    assert exc_info.value.detail["error_code"] == "SUBGRAPH_PATH_NOT_FOUND"


@pytest.fixture
def metadata_store(tmp_path: Path) -> LocalJsonMetadataStore:
    return LocalJsonMetadataStore(
        global_config_dir=tmp_path / "global-config",
        workspaces_root=tmp_path / "workspaces",
    )
