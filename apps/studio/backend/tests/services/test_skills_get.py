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
