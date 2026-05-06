"""MVP-3 T5 build_graph_nodes tests."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from graph_agent.core.exceptions import SkillLoadError
from graph_agent.core.io_manager import IOManager
from graph_agent.core.loader import build_graph_nodes, parse_skill_md, validate_manifest
from graph_agent.core.manifest import GraphSkillDef
from graph_agent.core.manifest import SkillManifest as SkillManifestType
from graph_agent.core.module_sandbox import ModuleSandbox
from graph_agent.core.phase_node import PhaseNode
from graph_agent.core.schema_engine import SchemaEngine

ROOT = Path(__file__).resolve().parents[4]
CORE_SKILLS = [
    ROOT / "skills/text-segmentation/SKILL.md",
    ROOT / "skills/event-extraction/SKILL.md",
    ROOT / "skills/batch-analysis/SKILL.md",
    ROOT / "skills/global-synthesis/SKILL.md",
]


def _manifest_from_text(
    text: str,
    engine: SchemaEngine | None = None,
) -> SkillManifestType:
    schema_engine = engine or SchemaEngine()
    raw = parse_skill_md(text)
    return validate_manifest(raw, schema_engine, lambda specs: IOManager(specs))


def _graph_yaml(phase_yaml: str, *, io_yaml: str = "io: {inputs: [], outputs: []}\n") -> str:
    return (
        "---\n"
        'schema_version: "2.0"\n'
        "name: graph\n"
        "description: test graph\n"
        "type: graph\n"
        f"{io_yaml}"
        "phases:\n"
        f"{phase_yaml}"
        "---\n"
    )


def test_build_graph_nodes_compiles_logic_phase_and_execute_updates_state(
    tmp_path: Path,
) -> None:
    (tmp_path / "tools.py").write_text(
        "def prepare(context):\n"
        "    return 'prepared'\n"
        "\n"
        "def validate(context):\n"
        "    return True, []\n",
        encoding="utf-8",
    )
    manifest = _manifest_from_text(
        _graph_yaml(
            "  - name: setup\n"
            "    mode: logic\n"
            "    execute_steps:\n"
            "      - tools.prepare\n"
            "    validator: tools.validate\n"
        )
    )

    nodes = build_graph_nodes(manifest, SchemaEngine(), ModuleSandbox([tmp_path]))

    assert len(nodes) == 1
    node = nodes[0]
    assert isinstance(node, PhaseNode)
    assert node.name == "setup"
    assert node.phase is not None
    assert node.phase.requires_llm is False
    assert node.phase.tools[0]({}) == "prepared"
    assert node.validator is not None
    assert node.validator({}) == (True, [])
    assert node.initial_state_factory is not None
    assert node.execute(node.initial_state_factory({}))["flow"].current_phase == "setup"


def test_build_graph_nodes_attaches_compiled_schema_and_business_data_fields() -> None:
    engine = SchemaEngine()
    manifest = _manifest_from_text(
        _graph_yaml(
            "  - name: draft\n"
            "    mode: llm\n"
            "    hoist_to: parsed_result\n"
            "    output_schema: |\n"
            "      title: str\n",
            io_yaml=(
                "io:\n"
                "  inputs:\n"
                "    - name: chapter_content\n"
                "      source: runtime\n"
                "  outputs:\n"
                "    - name: final_result\n"
                "      target: artifact\n"
            ),
        ),
        engine,
    )

    nodes = build_graph_nodes(manifest, engine, ModuleSandbox())

    node = nodes[0]
    assert node.compiled_schema is not None
    assert node.compiled_schema.field_map["title"] is str
    assert node.business_data_cls is not None
    assert {"chapter_content", "final_result", "parsed_result"} <= set(
        node.business_data_cls.model_fields
    )
    assert node.initial_state_factory is not None
    state = node.initial_state_factory({"chapter_content": "raw"})
    assert state["data"]["chapter_content"] == "raw"


def test_build_graph_nodes_resolves_dotted_output_schema_without_public_module(
    tmp_path: Path,
) -> None:
    (tmp_path / "schemas.py").write_text(
        "from pydantic import BaseModel, Field\n"
        "\n"
        "class OutputSchema(BaseModel):\n"
        "    title: str = Field(..., description='result title')\n",
        encoding="utf-8",
    )
    sys.modules.pop("schemas", None)
    manifest = _manifest_from_text(
        _graph_yaml(
            "  - name: draft\n"
            "    mode: llm\n"
            "    prompt: Write a title.\n"
            "    output_schema: schemas.OutputSchema\n"
        )
    )

    node = build_graph_nodes(manifest, SchemaEngine(), ModuleSandbox([tmp_path]))[0]

    assert node.output_schema_cls is not None
    assert node.output_schema_cls.__name__ == "OutputSchema"
    assert node.phase is not None
    assert node.phase.output_schema is node.output_schema_cls
    assert node.phase.output_schema_path == "schemas.OutputSchema"
    assert node.phase.system_prompt is not None
    assert "title" in node.phase.system_prompt
    assert "schemas" not in sys.modules


def test_build_graph_nodes_rejects_persona_manifest() -> None:
    manifest = _manifest_from_text(
        "---\n"
        'schema_version: "2.0"\n'
        "name: narrator\n"
        "description: persona\n"
        "type: persona\n"
        "role_profile: Keep voice consistent.\n"
        "---\n"
    )

    with pytest.raises(SkillLoadError, match="not runnable"):
        build_graph_nodes(manifest, SchemaEngine(), ModuleSandbox())


@pytest.mark.parametrize("skill_path", CORE_SKILLS)
def test_build_graph_nodes_core_skills_compile(skill_path: Path) -> None:
    engine = SchemaEngine()
    raw = parse_skill_md(skill_path.read_text(encoding="utf-8"))
    manifest = validate_manifest(raw, engine, lambda specs: IOManager(specs))
    assert isinstance(manifest, GraphSkillDef)
    sys_path_snapshot = list(sys.path)
    try:
        nodes = build_graph_nodes(
            manifest,
            engine,
            ModuleSandbox(search_paths=[skill_path.parent]),
        )
    finally:
        sys.path[:] = sys_path_snapshot

    assert nodes
    assert all(isinstance(node, PhaseNode) for node in nodes)
    assert [node.name for node in nodes] == [phase.name for phase in manifest.phases]
