from __future__ import annotations

import hashlib
from pathlib import Path

from fastapi.testclient import TestClient


def _files_from_skill_dir(skill_dir: Path) -> dict[str, str]:
    return {
        path.relative_to(skill_dir).as_posix(): path.read_text(encoding="utf-8")
        for path in sorted(skill_dir.rglob("*"))
        if path.is_file()
    }


def _graph_hash(graph_text: str) -> str:
    return hashlib.sha256(graph_text.encode("utf-8")).hexdigest()


def test_update_skill_expected_hash_match_writes_files(
    client: TestClient,
    studio_roots: tuple[Path, Path],
) -> None:
    skills_dir, workspaces_dir = studio_roots
    files = _files_from_skill_dir(skills_dir / "text-segmentation")
    files["phases/setup/LOGIC.md"] = files["phases/setup/LOGIC.md"].replace(
        "name: setup",
        "name: hash matched setup",
    )

    response = client.put(
        "/api/skills/text-segmentation",
        json={"files": files, "expected_hash": _graph_hash(files["GRAPH.md"])},
    )

    assert response.status_code == 200
    assert "hash matched setup" in (
        workspaces_dir / "default" / "skills" / "text-segmentation" / "phases" / "setup" / "LOGIC.md"
    ).read_text(encoding="utf-8")


def test_update_skill_expected_hash_mismatch_returns_409_without_write(
    client: TestClient,
    studio_roots: tuple[Path, Path],
) -> None:
    skills_dir, workspaces_dir = studio_roots
    skill_dir = skills_dir / "text-segmentation"
    files = _files_from_skill_dir(skill_dir)
    original_hash = _graph_hash(files["GRAPH.md"])
    graph_path = skill_dir / "GRAPH.md"
    current_markdown = graph_path.read_text(encoding="utf-8") + "\n<!-- external edit -->\n"
    graph_path.write_text(current_markdown, encoding="utf-8")

    response = client.put(
        "/api/skills/text-segmentation",
        json={"files": files, "expected_hash": original_hash},
    )

    assert response.status_code == 409
    assert response.json() == {
        "code": "snapshot_conflict",
        "current_hash": _graph_hash(current_markdown),
        "current_markdown_content": current_markdown,
    }
    assert not (workspaces_dir / "default" / "skills" / "text-segmentation").exists()


def test_update_skill_without_expected_hash_remains_backward_compatible(
    client: TestClient,
    studio_roots: tuple[Path, Path],
) -> None:
    skills_dir, workspaces_dir = studio_roots
    files = _files_from_skill_dir(skills_dir / "text-segmentation")
    files["phases/setup/LOGIC.md"] = files["phases/setup/LOGIC.md"].replace(
        "name: setup",
        "name: legacy client setup",
    )

    response = client.put("/api/skills/text-segmentation", json={"files": files})

    assert response.status_code == 200
    assert "legacy client setup" in (
        workspaces_dir / "default" / "skills" / "text-segmentation" / "phases" / "setup" / "LOGIC.md"
    ).read_text(encoding="utf-8")


def test_update_skill_retry_with_returned_current_hash_succeeds(
    client: TestClient,
    studio_roots: tuple[Path, Path],
) -> None:
    skills_dir, workspaces_dir = studio_roots
    skill_dir = skills_dir / "text-segmentation"
    files = _files_from_skill_dir(skill_dir)
    graph_path = skill_dir / "GRAPH.md"
    graph_path.write_text(graph_path.read_text(encoding="utf-8") + "\n<!-- reload me -->\n", encoding="utf-8")
    files["phases/setup/LOGIC.md"] = files["phases/setup/LOGIC.md"].replace(
        "name: setup",
        "name: retried setup",
    )

    conflict = client.put(
        "/api/skills/text-segmentation",
        json={"files": files, "expected_hash": "stale"},
    )
    retry = client.put(
        "/api/skills/text-segmentation",
        json={"files": files, "expected_hash": conflict.json()["current_hash"]},
    )

    assert conflict.status_code == 409
    assert retry.status_code == 200
    assert "retried setup" in (
        workspaces_dir / "default" / "skills" / "text-segmentation" / "phases" / "setup" / "LOGIC.md"
    ).read_text(encoding="utf-8")
