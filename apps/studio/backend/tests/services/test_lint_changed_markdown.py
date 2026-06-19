"""Service-layer tests for linting unsaved changed-markdown.

The lint kernel stays engine-owned (compile-lint F1/F5). These tests pin the
Studio backend shell behavior: feed the editor's *unsaved* GRAPH.md body to the
engine compiler, surface diagnostics, and — critically — never persist the body
to the skill store on disk (persistence is Autosave / native-fs's job, not
lint's).
"""

from __future__ import annotations

from pathlib import Path

import pytest
from app.services import skills as skill_service


@pytest.fixture(autouse=True)
def _roots(studio_roots: tuple[Path, Path]) -> tuple[Path, Path]:
    return studio_roots


def _disk_graph_text(skills_dir: Path, skill_id: str) -> str:
    return (skills_dir / skill_id / "GRAPH.md").read_text(encoding="utf-8")


def test_clean_changed_markdown_passes_without_touching_disk(
    studio_roots: tuple[Path, Path],
) -> None:
    skills_dir, _workspaces = studio_roots
    skill_id = "text-segmentation"
    original_on_disk = _disk_graph_text(skills_dir, skill_id)
    # A valid edit the user has NOT saved yet: tweak the description only.
    changed = original_on_disk.replace(
        "description: Text segments",
        "description: Text segments edited in editor",
    )
    assert changed != original_on_disk

    result = skill_service.lint_skill_changed_markdown(skill_id, changed)

    assert result.status == "passed"
    assert result.errors == []
    # The unsaved body must NOT have been written to the skill store on disk.
    assert _disk_graph_text(skills_dir, skill_id) == original_on_disk


def test_invalid_changed_markdown_fails_while_disk_stays_valid(
    studio_roots: tuple[Path, Path],
) -> None:
    skills_dir, _workspaces = studio_roots
    skill_id = "text-segmentation"
    original_on_disk = _disk_graph_text(skills_dir, skill_id)
    # Break the unsaved body: drop the required frontmatter `name` key.
    broken = original_on_disk.replace("name: text-segmentation\n", "")
    assert broken != original_on_disk

    result = skill_service.lint_skill_changed_markdown(skill_id, broken)

    assert result.status == "failed"
    assert result.errors, "a broken manifest must surface at least one diagnostic"
    # Disk copy is untouched — lint never persisted the broken body.
    assert _disk_graph_text(skills_dir, skill_id) == original_on_disk


def test_changed_markdown_diagnostic_keeps_typed_engine_code(
    studio_roots: tuple[Path, Path],
) -> None:
    skills_dir, _workspaces = studio_roots
    skill_id = "text-segmentation"
    original_on_disk = _disk_graph_text(skills_dir, skill_id)
    broken = original_on_disk.replace("name: text-segmentation\n", "")

    result = skill_service.lint_skill_changed_markdown(skill_id, broken)

    assert result.status == "failed"
    first = result.errors[0]
    # Typed axis from the engine payload survives: an engine F-code, not a
    # Studio-invented placeholder, and the GRAPH.md location is attributed.
    assert first.error_code.startswith("F-")
    assert first.severity == "error"
    assert first.file == "GRAPH.md"


def test_body_lint_diverges_from_stale_disk_state(
    studio_roots: tuple[Path, Path],
) -> None:
    """The whole point: lint must reflect the *body*, not the disk file.

    Disk holds a valid skill; the unsaved body is broken. Linting the body must
    fail even though the on-disk file would pass — proving the body (not the
    disk path) is the source of truth for this call.
    """
    skills_dir, _workspaces = studio_roots
    skill_id = "event-extraction"
    original_on_disk = _disk_graph_text(skills_dir, skill_id)

    # Sanity: the disk path lints clean.
    disk_result = skill_service.lint_skill(skill_id)
    assert disk_result.status == "passed"

    broken_body = original_on_disk.replace("phases:\n  - setup\n", "phases: []\n")
    assert broken_body != original_on_disk

    body_result = skill_service.lint_skill_changed_markdown(skill_id, broken_body)

    assert body_result.status == "failed"
    # Disk untouched after the body lint.
    assert _disk_graph_text(skills_dir, skill_id) == original_on_disk
