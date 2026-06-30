"""n2-canvas#10 (data-gap-viz): per-phase io supply/demand projection tests.

Verifies the Studio-shell projection that surfaces, per phase, the io.inputs /
io.outputs field schema PLUS a supply map (which upstream phase or graph input
feeds each input field, or whether it is an unmet data gap). All data is read
from the engine's already-compiled graph -- no engine edit.
"""

from __future__ import annotations

from pathlib import Path

from app.services.canvas_data_gap import (
    build_phase_io_index,
    compute_field_supply,
)
from app.services.skill_resolver import build_studio_skill_resolver
from app.services.skills import _graph_topology
from graph_agent.core.loader import SkillLoader


def _compile(skill_dir: Path):
    return SkillLoader().compile_skill(
        skill_dir,
        skill_resolver=build_studio_skill_resolver(),
    )


def _write_two_phase_skill(skill_dir: Path) -> None:
    """A skill where phase `b` consumes one field from `a` and one graph input,
    plus one field nobody produces (the data gap)."""
    (skill_dir / "phases" / "a" / "actions").mkdir(parents=True)
    (skill_dir / "phases" / "a" / "actions" / "__init__.py").write_text("", encoding="utf-8")
    (skill_dir / "phases" / "a" / "actions" / "make.py").write_text(
        "def make(inputs):\n    return {'alpha': '1'}\n",
        encoding="utf-8",
    )
    (skill_dir / "phases" / "b" / "actions").mkdir(parents=True)
    (skill_dir / "phases" / "b" / "actions" / "__init__.py").write_text("", encoding="utf-8")
    (skill_dir / "phases" / "b" / "actions" / "use.py").write_text(
        "def use(inputs):\n    return {'done': True}\n",
        encoding="utf-8",
    )
    (skill_dir / "GRAPH.md").write_text(
        """---
schema_version: "v0.3.0"
name: gap-skill
description: data gap demo
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
      done:
        type: boolean
    required: [done]
    additionalProperties: true
phases:
  - a
  - b
---
<phase depends_on="input">a</phase>
<phase depends_on="a" output>b</phase>
""",
        encoding="utf-8",
    )
    (skill_dir / "phases" / "a" / "LOGIC.md").write_text(
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
      alpha:
        type: string
---
<action>make</action>
""",
        encoding="utf-8",
    )
    (skill_dir / "phases" / "b" / "LOGIC.md").write_text(
        """---
io:
  inputs:
    type: object
    properties:
      alpha:
        type: string
      seed:
        type: string
      orphan:
        type: string
  outputs:
    type: object
    properties:
      done:
        type: boolean
---
<action>use</action>
""",
        encoding="utf-8",
    )


def test_should_build_phase_io_index_from_compiled_nodes(tmp_path: Path) -> None:
    skill_dir = tmp_path / "gap-skill"
    _write_two_phase_skill(skill_dir)
    compiled = _compile(skill_dir)

    index = build_phase_io_index(compiled)

    assert "alpha" in index["a"]["outputs"]
    assert "seed" in index["a"]["inputs"]
    assert set(index["b"]["inputs"]) == {"alpha", "seed", "orphan"}
    assert "done" in index["b"]["outputs"]


def test_should_resolve_supply_from_phase_graph_input_and_flag_gap() -> None:
    index = {
        "a": {"inputs": {"seed": {}}, "outputs": {"alpha": {}}},
        "b": {"inputs": {"alpha": {}, "seed": {}, "orphan": {}}, "outputs": {"done": {}}},
    }

    supply = compute_field_supply(
        phase_name="b",
        depends_on=["a"],
        phase_io_index=index,
        graph_input_fields={"seed"},
    )

    by_field = {entry["field"]: entry for entry in supply}
    assert by_field["alpha"] == {
        "field": "alpha",
        "supplied": True,
        "source": "phase",
        "producer_phase": "a",
    }
    assert by_field["seed"]["source"] == "graph_input"
    assert by_field["seed"]["supplied"] is True
    assert by_field["orphan"]["supplied"] is False
    assert by_field["orphan"]["source"] == "none"


def test_graph_topology_rows_carry_io_fields_and_supply(tmp_path: Path) -> None:
    skill_dir = tmp_path / "gap-skill"
    _write_two_phase_skill(skill_dir)
    compiled = _compile(skill_dir)

    rows = _graph_topology(compiled, skill_dir)

    rows_by_id = {row["id"]: row for row in rows}
    b_row = rows_by_id["b"]
    assert "io_fields" in b_row
    assert "field_supply" in b_row
    supply_by_field = {entry["field"]: entry for entry in b_row["field_supply"]}
    # alpha is produced by upstream phase `a`
    assert supply_by_field["alpha"]["producer_phase"] == "a"
    # seed is the graph-level run input
    assert supply_by_field["seed"]["source"] == "graph_input"
    # orphan has no producer and no graph input -> data gap
    assert supply_by_field["orphan"]["supplied"] is False
