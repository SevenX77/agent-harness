"""n5-node#3 (dirty-downstream-graying): per-node resume dirtiness slice tests.

Verifies the Studio-shell dependency-graph slice that, given a resume node,
computes which downstream phases a change can stale (the set the canvas grays)
and leaves unrelated side-branches out. Reads only compiled.nodes -- no engine
edit.
"""

from __future__ import annotations

from pathlib import Path

from app.services.resume_downstream import (
    affected_downstream_nodes,
    is_resume_node_affected,
    resume_allowed_for_node,
)
from app.services.skill_resolver import build_studio_skill_resolver
from graph_agent.core.loader import SkillLoader


def _write_fanout_skill(skill_dir: Path) -> None:
    """Diamond-ish graph: a -> b, a -> c, b -> d. c is a side-branch of b/d."""
    for phase in ("a", "b", "c", "d"):
        actions = skill_dir / "phases" / phase / "actions"
        actions.mkdir(parents=True)
        (actions / "__init__.py").write_text("", encoding="utf-8")
        (actions / "step.py").write_text(
            f"def step(context):\n    context.set('{phase}_out', True)\n    return {{'{phase}_out': True}}\n",
            encoding="utf-8",
        )
        (skill_dir / "phases" / phase / "LOGIC.md").write_text(
            f"""---
io:
  inputs:
    type: object
    properties:
      seed:
        type: string
  outputs:
    type: object
    properties:
      {phase}_out:
        type: boolean
---
<action>step</action>
""",
            encoding="utf-8",
        )
    (skill_dir / "GRAPH.md").write_text(
        """---
schema_version: "v0.3.0"
name: fanout
description: fanout demo
io:
  inputs:
    type: object
    properties:
      seed:
        type: string
    required: [seed]
    additionalProperties: false
  outputs:
    type: object
    properties:
      d_out:
        type: boolean
    required: [d_out]
    additionalProperties: true
phases:
  - a
  - b
  - c
  - d
---
<phase depends_on="input">a</phase>
<phase depends_on="a">b</phase>
<phase depends_on="a">c</phase>
<phase depends_on="b" output>d</phase>
""",
        encoding="utf-8",
    )


def _compile(skill_dir: Path):
    return SkillLoader().compile_skill(
        skill_dir,
        skill_resolver=build_studio_skill_resolver(),
    )


def test_affected_downstream_from_root_covers_all(tmp_path: Path) -> None:
    skill_dir = tmp_path / "fanout"
    _write_fanout_skill(skill_dir)
    compiled = _compile(skill_dir)

    affected = affected_downstream_nodes(compiled, "a")

    assert set(affected) == {"a", "b", "c", "d"}


def test_affected_downstream_from_b_excludes_sidebranch_c(tmp_path: Path) -> None:
    skill_dir = tmp_path / "fanout"
    _write_fanout_skill(skill_dir)
    compiled = _compile(skill_dir)

    affected = affected_downstream_nodes(compiled, "b")

    # b dirties b and its dependent d, but NOT the side-branch c.
    assert set(affected) == {"b", "d"}
    assert "c" not in affected


def test_resume_node_affected_only_when_in_dirty_set(tmp_path: Path) -> None:
    skill_dir = tmp_path / "fanout"
    _write_fanout_skill(skill_dir)
    compiled = _compile(skill_dir)

    dirty = affected_downstream_nodes(compiled, "b")

    assert is_resume_node_affected(compiled, resume_from_node_id="d", dirty_node_ids=dirty)
    assert not is_resume_node_affected(compiled, resume_from_node_id="c", dirty_node_ids=dirty)


def test_unknown_node_yields_empty_slice(tmp_path: Path) -> None:
    skill_dir = tmp_path / "fanout"
    _write_fanout_skill(skill_dir)
    compiled = _compile(skill_dir)

    assert affected_downstream_nodes(compiled, "does-not-exist") == []


# --- B1 (n5-node fn#3): per-node resume_allowed gate ---------------------------
# resume_allowed must stop being a GLOBAL "not dirty" flag once a resume node is
# named. These tests pin spec F3's three cases: an unrelated side-branch stays
# resumable even when a sibling upstream changed, an affected downstream is
# blocked, and the no-node (global Trace Resume) path keeps gating on any dirt.


def test_resume_allowed_for_unrelated_sidebranch_when_sibling_changed(
    tmp_path: Path,
) -> None:
    """spec F3 (a): change upstream sibling b -> resuming side-branch c is allowed."""
    skill_dir = tmp_path / "fanout"
    _write_fanout_skill(skill_dir)
    compiled = _compile(skill_dir)

    # Editing b dirties b and its dependent d (NOT the side-branch c).
    dirty = affected_downstream_nodes(compiled, "b")

    assert resume_allowed_for_node(
        resume_from_node_id="c",
        is_dirty=True,
        affected_downstream=dirty,
    )


def test_resume_blocked_for_affected_downstream_node(tmp_path: Path) -> None:
    """spec F3 (b): change upstream b -> resuming affected downstream d is blocked."""
    skill_dir = tmp_path / "fanout"
    _write_fanout_skill(skill_dir)
    compiled = _compile(skill_dir)

    dirty = affected_downstream_nodes(compiled, "b")

    assert not resume_allowed_for_node(
        resume_from_node_id="d",
        is_dirty=True,
        affected_downstream=dirty,
    )


def test_resume_allowed_for_node_clean_skill_is_always_true(tmp_path: Path) -> None:
    """A clean skill resumes from any node regardless of the (empty) slice."""
    assert resume_allowed_for_node(
        resume_from_node_id="d",
        is_dirty=False,
        affected_downstream=[],
    )


def test_global_resume_gates_on_any_dirt_when_no_node(tmp_path: Path) -> None:
    """spec F3 (c): no resume node (global Trace Resume) stays globally gated.

    With no node target, the per-node predicate must NOT silently flip a dirty
    skill to resumable -- it falls back to the global dirty gate (dirty => blocked,
    clean => allowed).
    """
    assert not resume_allowed_for_node(
        resume_from_node_id=None,
        is_dirty=True,
        affected_downstream=[],
    )
    assert resume_allowed_for_node(
        resume_from_node_id=None,
        is_dirty=False,
        affected_downstream=[],
    )


def test_per_node_resume_blocked_when_slice_unavailable() -> None:
    """Regression: an UNAVAILABLE slice (None) must degrade to a conservative block.

    When the skill cannot be compiled, the affected-downstream slice is unknown
    (``None``, distinct from an empty list). We cannot prove the resume node is an
    unrelated side-branch, so a dirty skill must stay BLOCKED -- a slice failure must
    never silently flip per-node resume to allowed. (Previously an unavailable slice
    was returned as ``[]``, which let any node resume because it was "not in" the
    empty set; this is exactly the false-allow this test pins shut.)
    """
    assert not resume_allowed_for_node(
        resume_from_node_id="beta",
        is_dirty=True,
        affected_downstream=None,
    )
    # A clean skill with an unknown slice still resumes (no dirt to gate on).
    assert resume_allowed_for_node(
        resume_from_node_id="beta",
        is_dirty=False,
        affected_downstream=None,
    )
