from __future__ import annotations

import asyncio
from pathlib import Path

from app.core.adapters.metadata_local import LocalJsonMetadataStore
from app.core.adapters.storage_local import LocalFilesystemBackend
from app.services.skills import get_skill_detail


def test_get_skill_returns_files_map(studio_roots: tuple[Path, Path]) -> None:
    _skills_dir, workspaces_dir = studio_roots
    storage = LocalFilesystemBackend(workspaces_dir)
    metadata = LocalJsonMetadataStore(workspaces_dir)

    detail = asyncio.run(get_skill_detail("default", "text-segmentation", storage, metadata))

    assert "GRAPH.md" in detail.files
    assert "io/inputs.json" in detail.files
    assert "io/outputs.json" in detail.files
    assert "phases/setup/LOGIC.md" in detail.files
    assert "phases/setup/actions/prepare.py" in detail.files
    assert "__init__.py" not in detail.files


def test_get_skill_lenient_on_broken_manifest(studio_roots: tuple[Path, Path]) -> None:
    _skills_dir, workspaces_dir = studio_roots
    skill_dir = workspaces_dir / "default" / "skills" / "broken-manifest"
    (skill_dir / "io").mkdir(parents=True)
    (skill_dir / "phases" / "init").mkdir(parents=True)
    (skill_dir / "GRAPH.md").write_text("not yaml frontmatter\n", encoding="utf-8")
    (skill_dir / "io" / "inputs.json").write_text("{}\n", encoding="utf-8")
    (skill_dir / "io" / "outputs.json").write_text("{}\n", encoding="utf-8")
    (skill_dir / "phases" / "init" / "LOGIC.md").write_text(
        """---
mode: logic
name: init
---
# init
""",
        encoding="utf-8",
    )
    storage = LocalFilesystemBackend(workspaces_dir)
    metadata = LocalJsonMetadataStore(workspaces_dir)

    detail = asyncio.run(get_skill_detail("default", "broken-manifest", storage, metadata))

    assert detail.manifest.name == "broken-manifest"
    assert detail.files["GRAPH.md"] == "not yaml frontmatter\n"
    assert detail.files["io/inputs.json"] == "{}\n"
    assert detail.files["io/outputs.json"] == "{}\n"
    assert detail.files["phases/init/LOGIC.md"].startswith("---")
    assert detail.graph_topology == []
    assert detail.io_schema == {}
    assert detail.lint_result is not None
    assert detail.lint_result.status == "failed"
    assert detail.manifest_errors
