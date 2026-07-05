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
    """A skill where phase `b` consumes one field from `a`, one graph input,
    and one file-sourced input that does not need blackboard supply."""
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
    (skill_dir / "assets").mkdir(parents=True)
    (skill_dir / "assets" / "orphan.txt").write_text("file supplied input\n", encoding="utf-8")
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
        source: file
        path: assets/orphan.txt
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


def test_should_resolve_source_file_field_without_blackboard_supply() -> None:
    index = {
        "b": {
            "inputs": {
                "asset_doc": {"type": "string", "source": "file"},
                "chapter": {
                    "type": "object",
                    "source": "file",
                    "properties": {"title": {"type": "string"}},
                },
            },
            "outputs": {},
        },
    }

    supply = compute_field_supply(
        phase_name="b",
        depends_on=[],
        phase_io_index=index,
        graph_input_fields=set(),
    )

    by_field = {entry["field"]: entry for entry in supply}
    assert by_field["asset_doc"]["supplied"] is True
    assert by_field["asset_doc"]["source"] == "file"
    assert by_field["chapter.title"]["supplied"] is True
    assert by_field["chapter.title"]["source"] == "file"


def test_should_flatten_nested_object_fields_into_dotted_paths() -> None:
    """Nested addressing (io-node-scoped-config, PM 2026-07-03): an object input
    field's sub-paths are independently addressable supply entries. A sub-field
    produced (whole object) upstream resolves via its ancestor; a nested field
    nobody produces is its own data gap — so the i/o config tree can mark the
    exact broken sub-field, mirroring the engine's recursive required gate."""
    index = {
        "a": {
            "inputs": {},
            "outputs": {
                "chapter": {
                    "type": "object",
                    "properties": {
                        "aa_number": {"type": "integer"},
                        "title": {"type": "string"},
                    },
                },
            },
        },
        "b": {
            "inputs": {
                "chapter": {
                    "type": "object",
                    "properties": {"aa_number": {"type": "integer"}},
                },
                "meta": {
                    "type": "object",
                    "properties": {"missing": {"type": "string"}},
                },
            },
            "outputs": {},
        },
    }

    supply = compute_field_supply(
        phase_name="b",
        depends_on=["a"],
        phase_io_index=index,
        graph_input_fields=set(),
    )

    by_field = {entry["field"]: entry for entry in supply}
    # the nested sub-path is addressable and resolves to the whole-object producer
    assert by_field["chapter.aa_number"]["supplied"] is True
    assert by_field["chapter.aa_number"]["source"] == "phase"
    assert by_field["chapter.aa_number"]["producer_phase"] == "a"
    # the parent object path is addressable too, supplied by the same producer
    assert by_field["chapter"]["producer_phase"] == "a"
    # a nested field nobody produces is its own gap (parent + leaf both unmet)
    assert by_field["meta.missing"]["supplied"] is False
    assert by_field["meta.missing"]["source"] == "none"
    assert by_field["meta"]["supplied"] is False


def test_should_resolve_nested_subpath_from_flattened_graph_input() -> None:
    """A graph-level object input supplies its declared sub-paths (chapter is a
    run input → chapter.aa_number is sourced from graph_input, not a gap)."""
    index = {
        "b": {
            "inputs": {
                "chapter": {
                    "type": "object",
                    "properties": {"aa_number": {"type": "integer"}},
                },
            },
            "outputs": {},
        },
    }

    supply = compute_field_supply(
        phase_name="b",
        depends_on=[],
        phase_io_index=index,
        graph_input_fields={"chapter"},
    )

    by_field = {entry["field"]: entry for entry in supply}
    assert by_field["chapter.aa_number"]["supplied"] is True
    assert by_field["chapter.aa_number"]["source"] == "graph_input"


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
    # orphan is source:file, so it does not require blackboard supply
    assert supply_by_field["orphan"]["supplied"] is True
    assert supply_by_field["orphan"]["source"] == "file"
