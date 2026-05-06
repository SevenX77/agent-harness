"""MVP-3 T2 loader pipeline Phase 1 + Phase 2 tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from graph_agent.core.exceptions import SkillCompilationError, SkillLoadError
from graph_agent.core.io_manager import IOManager
from graph_agent.core.loader import SkillLoader, parse_skill_md, validate_manifest
from graph_agent.core.manifest import GraphSkillDef
from graph_agent.core.schema_engine import SchemaEngine

ROOT = Path(__file__).resolve().parents[3]


@pytest.mark.parametrize(
    "skill_path",
    [
        "skills/text-segmentation/SKILL.md",
        "skills/event-extraction/SKILL.md",
        "skills/batch-analysis/SKILL.md",
        "skills/global-synthesis/SKILL.md",
    ],
)
def test_parse_skill_md_core_skills_return_top_level_keys(skill_path: str) -> None:
    raw = parse_skill_md((ROOT / skill_path).read_text(encoding="utf-8"))

    assert raw["schema_version"] == "2.0"
    assert raw["name"]
    assert raw["description"]
    assert raw["type"] == "graph"
    assert isinstance(raw["phases"], list) and raw["phases"]
    assert "io" in raw


def test_parse_skill_md_is_schema_engine_free(monkeypatch: pytest.MonkeyPatch) -> None:
    class _ExplodingEngine:
        def parse_from_md(self, _: str) -> None:
            raise AssertionError("parse_skill_md must not call SchemaEngine")

    monkeypatch.setattr("graph_agent.core.loader._SCHEMA_ENGINE", _ExplodingEngine())

    raw = parse_skill_md(
        "---\n"
        "schema_version: 2.0\n"
        "name: x\n"
        "description: d\n"
        "type: persona\n"
        "role_profile: r\n"
        "---\n"
    )

    assert raw["schema_version"] == "2.0"


def test_parse_skill_md_mirrors_output_example_to_raw_md_field() -> None:
    example = (
        '<output_example name="Item">\n'
        "## items\n"
        "- title (str, required): title\n"
        "</output_example>"
    )

    raw = parse_skill_md(
        "---\n"
        "schema_version: 2.0\n"
        "name: graph\n"
        "description: d\n"
        "type: graph\n"
        "io: {inputs: [], outputs: []}\n"
        "phases:\n"
        "  - mode: llm\n"
        "    name: draft\n"
        "    output_example: |\n"
        f"      {example.replace(chr(10), chr(10) + '      ')}\n"
        "---\n"
    )

    assert raw["phases"][0]["output_example_md"].strip() == example


def test_parse_skill_md_moves_inline_output_schema_to_md_field() -> None:
    raw = parse_skill_md(
        "---\n"
        "schema_version: 2.0\n"
        "name: graph\n"
        "description: d\n"
        "type: graph\n"
        "io: {inputs: [], outputs: []}\n"
        "phases:\n"
        "  - mode: llm\n"
        "    name: draft\n"
        "    output_schema: |\n"
        "      title: str\n"
        "      score: int\n"
        "---\n"
    )

    phase = raw["phases"][0]
    assert phase["output_schema_md"] == "title: str\nscore: int"
    assert "output_schema" not in phase


def test_parse_skill_md_missing_frontmatter_raises() -> None:
    with pytest.raises(SkillLoadError):
        parse_skill_md("# not a SKILL frontmatter")


@pytest.mark.parametrize(
    "skill_path",
    [
        "skills/text-segmentation/SKILL.md",
        "skills/event-extraction/SKILL.md",
        "skills/batch-analysis/SKILL.md",
        "skills/global-synthesis/SKILL.md",
    ],
)
def test_validate_manifest_core_skills_pass(skill_path: str) -> None:
    raw = parse_skill_md((ROOT / skill_path).read_text(encoding="utf-8"))

    manifest = validate_manifest(raw, SchemaEngine(), lambda specs: IOManager(specs))

    assert isinstance(manifest, GraphSkillDef)
    assert isinstance(manifest.compiled_schemas, dict)


def test_validate_manifest_compiles_phase_schema() -> None:
    raw = parse_skill_md(
        "---\n"
        "schema_version: 2.0\n"
        "name: graph\n"
        "description: d\n"
        "type: graph\n"
        "io: {inputs: [], outputs: []}\n"
        "phases:\n"
        "  - mode: llm\n"
        "    name: draft\n"
        "    output_schema: |\n"
        "      title: str\n"
        "---\n"
    )

    manifest = validate_manifest(raw, SchemaEngine(), lambda specs: IOManager(specs))

    assert manifest.compiled_schemas["draft"].field_map["title"] is str
    assert "compiled_schemas" not in manifest.model_dump()


def test_validate_manifest_invalid_schema_raises_compilation_error() -> None:
    raw = parse_skill_md(
        "---\n"
        "schema_version: 2.0\n"
        "name: graph\n"
        "description: d\n"
        "type: graph\n"
        "io: {inputs: [], outputs: []}\n"
        "phases:\n"
        "  - mode: llm\n"
        "    name: draft\n"
        "    output_schema: 'title:'\n"
        "---\n"
    )

    with pytest.raises(SkillCompilationError, match="SchemaEngine"):
        validate_manifest(raw, SchemaEngine(), lambda specs: IOManager(specs))


def test_validate_manifest_rejects_private_hoist_target() -> None:
    raw = parse_skill_md(
        "---\n"
        "schema_version: 2.0\n"
        "name: graph\n"
        "description: d\n"
        "type: graph\n"
        "io: {inputs: [], outputs: []}\n"
        "phases:\n"
        "  - mode: llm\n"
        "    name: draft\n"
        "    hoist_to: _private\n"
        "---\n"
    )

    with pytest.raises(SkillCompilationError, match="target_field"):
        validate_manifest(raw, SchemaEngine(), lambda specs: IOManager(specs))


def test_skill_loader_compile_skill_runs_phase_1_and_2(tmp_path: Path) -> None:
    skill = tmp_path / "SKILL.md"
    skill.write_text(
        "---\n"
        "schema_version: 2.0\n"
        "name: graph\n"
        "description: d\n"
        "type: graph\n"
        "io: {inputs: [], outputs: []}\n"
        "phases:\n"
        "  - mode: llm\n"
        "    name: draft\n"
        "    output_schema: |\n"
        "      title: str\n"
        "---\n",
        encoding="utf-8",
    )

    compiled = SkillLoader(
        schema_engine=SchemaEngine(),
        io_manager_factory=lambda specs: IOManager(specs),
    ).compile_skill(skill)

    assert compiled.raw["name"] == "graph"
    assert compiled.manifest.compiled_schemas["draft"].field_map["title"] is str
