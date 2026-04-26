"""Cohesion plan 方针 4.2 (2026-04-26): ``adopted_persona`` written as a
relative path (``./subskills/...``) was being concatenated with the
implicit ``subskills/`` skill-local convention prefix, producing a
double-prefix path like ``<base_dir>/subskills/subskills/<name>/SKILL.md``
that never existed. Authors who used relative paths got a confusing
"not found" error pointing at a path the framework invented, not the
one they wrote.

Fixed contract:

- ``adopted_persona: foo`` → ``<base_dir>/subskills/foo/SKILL.md``
  (the existing skill-local convention)
- ``adopted_persona: ./subskills/foo`` → ``<base_dir>/subskills/foo/SKILL.md``
  (relative paths that already include the convention prefix do NOT
  get it doubled)
- ``adopted_persona: ./other/foo`` → ``<base_dir>/other/foo/SKILL.md``
  (general relative paths anchored at the SKILL.md's directory)
"""
from __future__ import annotations

from pathlib import Path

import pytest

from graph_agent.core.exceptions import SkillLoadError
from graph_agent.core.personas import resolve_persona


def _persona_skill(role: str) -> str:
    return (
        "---\n"
        'schema_version: "2.0"\n'
        "name: p\n"
        "description: tiny persona\n"
        "type: persona\n"
        f'role_profile: "{role}"\n'
        "---\n"
    )


def test_relative_path_with_subskills_prefix_resolves_without_doubling(
    tmp_path: Path,
) -> None:
    """``./subskills/p`` from a host SKILL.md must resolve to
    ``<host>/subskills/p/SKILL.md``, not the doubled
    ``<host>/subskills/subskills/p/SKILL.md`` that the original
    walk produced."""
    base = tmp_path
    persona_dir = base / "subskills" / "p"
    persona_dir.mkdir(parents=True)
    (persona_dir / "SKILL.md").write_text(_persona_skill("RELATIVE-OK"), encoding="utf-8")

    manifest = resolve_persona("./subskills/p", base_dir=base)
    assert manifest.role_profile == "RELATIVE-OK"


def test_relative_path_to_sibling_directory_resolves(tmp_path: Path) -> None:
    """A relative path to a non-``subskills/`` directory must work too."""
    base = tmp_path
    persona_dir = base / "external" / "p"
    persona_dir.mkdir(parents=True)
    (persona_dir / "SKILL.md").write_text(_persona_skill("EXTERNAL-OK"), encoding="utf-8")

    manifest = resolve_persona("./external/p", base_dir=base)
    assert manifest.role_profile == "EXTERNAL-OK"


def test_bare_name_still_uses_subskills_convention(tmp_path: Path) -> None:
    """Regression guard: bare names continue to use the
    ``subskills/<name>/SKILL.md`` convention."""
    base = tmp_path
    persona_dir = base / "subskills" / "p"
    persona_dir.mkdir(parents=True)
    (persona_dir / "SKILL.md").write_text(_persona_skill("BARE-OK"), encoding="utf-8")

    manifest = resolve_persona("p", base_dir=base)
    assert manifest.role_profile == "BARE-OK"


def test_missing_relative_path_reports_correct_search_target(
    tmp_path: Path,
) -> None:
    """When the relative path doesn't exist, the error message must
    mention the path the author actually wrote — not an invented
    double-prefix path."""
    with pytest.raises(SkillLoadError) as excinfo:
        resolve_persona("./subskills/missing", base_dir=tmp_path)
    msg = str(excinfo.value)
    assert "subskills/subskills" not in msg, (
        "Error message must not include doubled subskills prefix; "
        f"got: {msg}"
    )
