from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from pydantic import TypeAdapter, ValidationError

from graph_agent.core.exceptions import SkillLoadError
from graph_agent.core.graph_serializer import serialize_graph
from graph_agent.core.loader import SkillLoader
from graph_agent.core.manifest import GraphManifest, LogicNodeAST, PhaseAST, PhaseIOSchema


class DictSkillResolver:
    def __init__(self, roots: dict[str, Path]) -> None:
        self.roots = roots

    def resolve_skill(self, skill_id: str) -> Path:
        return self.roots[skill_id]


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _schema_yaml(field: str = "text") -> str:
    return f"""type: object
    properties:
      {field}:
        type: string
    required:
      - {field}"""


def _object_schema(*properties: str) -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {name: {"type": "string"} for name in properties},
        "required": list(properties),
    }


def _graph(
    root: Path,
    *,
    schema_version: str = "v0.3.0",
    phases: list[str] | None = None,
    body: str | None = None,
    inputs_field: str = "text",
    outputs_field: str = "result",
    extra_frontmatter: str = "",
) -> None:
    phase_names = phases if phases is not None else ["main"]
    phase_list = ", ".join(phase_names)
    phase_body = body if body is not None else '<phase depends_on="input" output>main</phase>'
    _write(
        root / "GRAPH.md",
        f"""---
schema_version: "{schema_version}"
name: round14
phases: [{phase_list}]
io:
  inputs:
    {_schema_yaml(inputs_field)}
  outputs:
    {_schema_yaml(outputs_field)}
{extra_frontmatter}---
{phase_body}
""",
    )


def _agent_phase(
    root: Path,
    phase_id: str = "main",
    *,
    frontmatter: str = "",
    body: str | None = None,
) -> None:
    phase_body = (
        body
        or """<role>Tester</role>
<goal>Exercise the round-14 compiler contract.</goal>
<step id="S1" name="check">Use @protocol:P1 and @example:E1.</step>
<protocol id="P1">Return a precise result.</protocol>
<example id="E1">Input text becomes a result string.</example>
"""
    )
    _write(
        root / "phases" / phase_id / "SKILL.md",
        f"""---
validator: false
tools: [finish_task]
references:
  - {{id: R1, path: references/r1.md, summary: "Reference"}}
examples:
  - {{id: E2, path: examples/e2.md, summary: "Document example"}}
{frontmatter}---
{phase_body}
""",
    )
    _write(root / "phases" / phase_id / "references" / "r1.md", "reference\n")
    _write(root / "phases" / phase_id / "examples" / "e2.md", "example\n")


def _logic_phase(
    root: Path,
    phase_id: str = "main",
    *,
    input_field: str = "text",
    validator: str = "false",
) -> None:
    _write(
        root / "phases" / phase_id / "LOGIC.md",
        f"""---
io:
  inputs:
    {_schema_yaml(input_field)}
  outputs:
    {_schema_yaml("result")}
actions: [run]
validator: {validator}
---
<action>run</action>
""",
    )
    _write(
        root / "phases" / phase_id / "actions" / "run.py",
        f"def run(context):\n    return {{'result': context['{input_field}']}}\n",
    )


def _subgraph_phase(
    root: Path,
    phase_id: str = "main",
    *,
    child_path: Path | None = None,
    input_field: str = "text",
    output_field: str = "result",
) -> None:
    child_path = child_path or root / "subgraphs" / "child"
    _write(
        root / "phases" / phase_id / "SUBGRAPH.md",
        f"""---
path: {child_path}
io:
  inputs:
    {_schema_yaml(input_field)}
  outputs:
    {_schema_yaml(output_field)}
validator: false
---
""",
    )


def _expect_code(exc: pytest.ExceptionInfo[SkillLoadError], code: str) -> None:
    assert exc.value.payload is not None
    assert exc.value.payload.code == code


def test_valid_v030_graph_uses_frontmatter_phase_registry_and_body_phase_dag(
    tmp_path: Path,
    mock_skill_resolver: object,
) -> None:
    _graph(tmp_path)
    _agent_phase(tmp_path)

    compiled = SkillLoader().compile_skill(tmp_path, skill_resolver=mock_skill_resolver)

    assert compiled.manifest.schema_version == "v0.3.0"
    assert compiled.manifest.phases == ["main"]
    assert compiled.nodes[0].ast.mode == "agent"


def test_schema_version_without_v_is_rejected(tmp_path: Path, mock_skill_resolver: object) -> None:
    _graph(tmp_path, schema_version="0." + "3.0")
    _agent_phase(tmp_path)

    with pytest.raises(SkillLoadError) as exc:
        SkillLoader().compile_skill(tmp_path, skill_resolver=mock_skill_resolver)

    _expect_code(exc, "[F-v3-graph-schema-version-mismatch]")


def test_schema_version_21_is_rejected_with_otherwise_v030_shape(tmp_path: Path, mock_skill_resolver: object) -> None:
    _graph(tmp_path, schema_version="2.1")
    _agent_phase(tmp_path)

    with pytest.raises(SkillLoadError) as exc:
        SkillLoader().compile_skill(tmp_path, skill_resolver=mock_skill_resolver)

    _expect_code(exc, "[F-v3-graph-schema-version-mismatch]")


@pytest.mark.parametrize("mode", ["skill", "agent", "logic", "subgraph"])
def test_phase_frontmatter_mode_is_forbidden_metadata(tmp_path: Path, mode: str, mock_skill_resolver: object) -> None:
    _graph(tmp_path)
    _agent_phase(tmp_path, frontmatter=f"mode: {mode}\n")

    with pytest.raises(SkillLoadError) as exc:
        SkillLoader().compile_skill(tmp_path, skill_resolver=mock_skill_resolver)

    assert exc.value.payload.code == "[F-v3-agent-schema-unknown-field]"


@pytest.mark.parametrize("field", ["schema_version", "graph_skill_id", "phase_id"])
def test_phase_frontmatter_rejects_root_only_metadata(tmp_path: Path, field: str, mock_skill_resolver: object) -> None:
    _graph(tmp_path)
    _agent_phase(tmp_path, frontmatter=f'{field}: "polluted"\n')

    with pytest.raises(SkillLoadError) as exc:
        SkillLoader().compile_skill(tmp_path, skill_resolver=mock_skill_resolver)

    assert exc.value.payload.code == "[F-v3-agent-schema-unknown-field]"


def test_phase_ast_rejects_legacy_skill_mode_at_pydantic_layer() -> None:
    payload = {
        "mode": "skill",
        "system_prompt": "old prompt",
        "exit_contract": "old contract",
    }

    with pytest.raises(ValidationError):
        TypeAdapter(PhaseAST).validate_python(payload)


def test_logic_node_ast_accepts_validator_boolean_and_defaults_false() -> None:
    ast = LogicNodeAST.model_validate(
        {
            "mode": "logic",
            "io": {
                "inputs": _object_schema("text"),
                "outputs": _object_schema("result"),
            },
            "actions": ["run"],
        }
    )

    assert ast.validator is False


def test_logic_validator_must_be_boolean(tmp_path: Path, mock_skill_resolver: object) -> None:
    _graph(tmp_path)
    _logic_phase(tmp_path, validator='"yes"')

    with pytest.raises(SkillLoadError) as exc:
        SkillLoader().compile_skill(tmp_path, skill_resolver=mock_skill_resolver)

    _expect_code(exc, "[F-v3-logic-validator-type-invalid]")


def test_phase_directory_with_multiple_node_files_uses_ambiguous_code(tmp_path: Path, mock_skill_resolver: object) -> None:
    _graph(tmp_path)
    _agent_phase(tmp_path)
    _logic_phase(tmp_path)

    with pytest.raises(SkillLoadError) as exc:
        SkillLoader().compile_skill(tmp_path, skill_resolver=mock_skill_resolver)

    _expect_code(exc, "[F-v3-graph-phase-mode-ambiguous]")


def test_declared_phase_without_node_file_uses_node_missing_code(tmp_path: Path, mock_skill_resolver: object) -> None:
    _graph(tmp_path)
    (tmp_path / "phases" / "main").mkdir(parents=True)

    with pytest.raises(SkillLoadError) as exc:
        SkillLoader().compile_skill(tmp_path, skill_resolver=mock_skill_resolver)

    _expect_code(exc, "[F-v3-graph-phase-node-missing]")


def test_graph_without_frontmatter_phases_is_rejected(tmp_path: Path, mock_skill_resolver: object) -> None:
    _write(
        tmp_path / "GRAPH.md",
        """---
schema_version: "v0.3.0"
name: round14
io:
  inputs:
    type: object
    properties: {}
  outputs:
    type: object
    properties: {}
---
<phase depends_on="input" output>main</phase>
""",
    )
    _agent_phase(tmp_path)

    with pytest.raises(SkillLoadError) as exc:
        SkillLoader().compile_skill(tmp_path, skill_resolver=mock_skill_resolver)

    _expect_code(exc, "[F-v3-graph-phases-missing]")


def test_graph_without_body_phase_is_rejected(tmp_path: Path, mock_skill_resolver: object) -> None:
    _graph(tmp_path, body="")
    _agent_phase(tmp_path)

    with pytest.raises(SkillLoadError) as exc:
        SkillLoader().compile_skill(tmp_path, skill_resolver=mock_skill_resolver)

    _expect_code(exc, "[F-v3-graph-phase-id-invalid]")


def test_body_phase_name_must_match_physical_directory(tmp_path: Path, mock_skill_resolver: object) -> None:
    _graph(tmp_path, phases=["main"], body='<phase depends_on="input" output>other</phase>')
    _agent_phase(tmp_path, "main")

    with pytest.raises(SkillLoadError) as exc:
        SkillLoader().compile_skill(tmp_path, skill_resolver=mock_skill_resolver)

    _expect_code(exc, "[F-v3-graph-phase-name-mismatch]")


def test_duplicate_phase_registration_uses_dedicated_code(tmp_path: Path, mock_skill_resolver: object) -> None:
    _graph(
        tmp_path,
        phases=["main", "main"],
        body='<phase depends_on="input" output>main</phase>',
    )
    _agent_phase(tmp_path)

    with pytest.raises(SkillLoadError) as exc:
        SkillLoader().compile_skill(tmp_path, skill_resolver=mock_skill_resolver)

    _expect_code(exc, "[F-v3-graph-phase-id-duplicate]")


def test_unknown_depends_on_uses_dedicated_code(tmp_path: Path, mock_skill_resolver: object) -> None:
    _graph(tmp_path, body='<phase depends_on="missing" output>main</phase>')
    _agent_phase(tmp_path)

    with pytest.raises(SkillLoadError) as exc:
        SkillLoader().compile_skill(tmp_path, skill_resolver=mock_skill_resolver)

    _expect_code(exc, "[F-v3-graph-depends-unknown]")


def test_graph_cycle_uses_dedicated_code(tmp_path: Path, mock_skill_resolver: object) -> None:
    _graph(
        tmp_path,
        phases=["first", "second"],
        body="""<phase depends_on="second">first</phase>
<phase depends_on="first" output>second</phase>""",
    )
    _agent_phase(tmp_path, "first")
    _agent_phase(tmp_path, "second")

    with pytest.raises(SkillLoadError) as exc:
        SkillLoader().compile_skill(tmp_path, skill_resolver=mock_skill_resolver)

    _expect_code(exc, "[F-v3-graph-phase-cycle]")


def test_unreachable_phase_uses_island_code(tmp_path: Path, mock_skill_resolver: object) -> None:
    _graph(
        tmp_path,
        phases=["first", "orphan"],
        body="""<phase depends_on="input" output>first</phase>
<phase depends_on="missing">orphan</phase>""",
    )
    _agent_phase(tmp_path, "first")
    _agent_phase(tmp_path, "orphan")

    with pytest.raises(SkillLoadError) as exc:
        SkillLoader().compile_skill(tmp_path, skill_resolver=mock_skill_resolver)

    _expect_code(exc, "[F-v3-graph-phase-island]")


def test_missing_output_phase_uses_leaf_terminal_fallback(tmp_path: Path, mock_skill_resolver: object) -> None:
    _graph(tmp_path, body='<phase depends_on="input">main</phase>')
    _agent_phase(tmp_path)

    compiled = SkillLoader().compile_skill(tmp_path, skill_resolver=mock_skill_resolver)

    assert compiled.raw["graph_topology"]["phases"] == [
        {"name": "main", "depends_on": ["input"], "output": False},
    ]


def test_bare_body_phase_compiles_as_dependency_free_node(
    tmp_path: Path,
    mock_skill_resolver: object,
) -> None:
    _graph(tmp_path, body="<phase>main</phase>")
    _agent_phase(tmp_path)

    compiled = SkillLoader().compile_skill(tmp_path, skill_resolver=mock_skill_resolver)

    assert compiled.raw["graph_topology"]["phases"] == [
        {"name": "main", "depends_on": [], "output": False},
    ]


@pytest.mark.parametrize(
    ("frontmatter", "path"),
    [
        ("io_inputs_ref: io/inputs.json\n", None),
        ("io_outputs_ref: io/outputs.json\n", None),
        ("", "io/inputs.json"),
        ("", "io/outputs.json"),
    ],
)
def test_physical_root_io_is_deprecated(
    tmp_path: Path,
    frontmatter: str,
    path: str | None,
    mock_skill_resolver: object,
) -> None:
    _graph(tmp_path, extra_frontmatter=frontmatter)
    _agent_phase(tmp_path)
    if path is not None:
        _write(tmp_path / path, "{}\n")

    with pytest.raises(SkillLoadError) as exc:
        SkillLoader().compile_skill(tmp_path, skill_resolver=mock_skill_resolver)

    _expect_code(exc, "[F-v3-graph-io-physical-file-deprecated]")


@pytest.mark.parametrize(
    "body",
    [
        '<role>Tester</role><goal>Goal</goal><steps><step id="S1">bad</step></steps>',
        "<role>Tester</role><goal>Goal</goal><exit_contract>bad</exit_contract>",
    ],
)
def test_agent_body_rejects_non_whitelisted_top_level_tags(tmp_path: Path, body: str, mock_skill_resolver: object) -> None:
    _graph(tmp_path)
    _agent_phase(tmp_path, body=body)

    with pytest.raises(SkillLoadError) as exc:
        SkillLoader().compile_skill(tmp_path, skill_resolver=mock_skill_resolver)

    _expect_code(exc, "[F-v3-agent-body-tag-unknown]")


def test_agent_body_extracts_inline_examples_for_mentions(tmp_path: Path, mock_skill_resolver: object) -> None:
    _graph(tmp_path)
    _agent_phase(
        tmp_path,
        body="""<role>Tester</role>
<goal>Use @example:E1.</goal>
<example id="E1">Inline body example.</example>
""",
    )

    compiled = SkillLoader().compile_skill(tmp_path, skill_resolver=mock_skill_resolver)

    assert compiled.nodes[0].ast.examples_inline[0].id == "E1"


def test_missing_mention_target_is_rejected(tmp_path: Path, mock_skill_resolver: object) -> None:
    _graph(tmp_path)
    _agent_phase(
        tmp_path,
        body="""<role>Tester</role>
<goal>Use @reference:MISSING.</goal>
""",
    )

    with pytest.raises(SkillLoadError) as exc:
        SkillLoader().compile_skill(tmp_path, skill_resolver=mock_skill_resolver)

    _expect_code(exc, "[F-v3-mention-target-not-found]")


def test_subgraph_io_input_mismatch_is_allowed_at_compile_time(tmp_path: Path, mock_skill_resolver: object) -> None:
    parent = tmp_path / "parent"
    child = parent / "subgraphs" / "child"
    _graph(parent)
    _subgraph_phase(parent, child_path=child, input_field="parent_input", output_field="result")
    _graph(child, inputs_field="child_input", outputs_field="result")
    _logic_phase(child, input_field="child_input")

    compiled = SkillLoader().compile_skill(parent, skill_resolver=DictSkillResolver({"child": child}))

    assert compiled.nodes[0].phase_name == "main"


def test_subgraph_io_output_mismatch_is_allowed_at_compile_time(tmp_path: Path, mock_skill_resolver: object) -> None:
    # §2.4 / cutover item ⑦: the parent/child io.outputs 1:1 equality gate is
    # relaxed. A subgraph whose declared outputs differ from the child's now
    # compiles — StateMapper merges by the parent's declared outputs at runtime;
    # no [F-v3-subgraph-io-mismatch] at compile time.
    parent = tmp_path / "parent"
    child = parent / "subgraphs" / "child"
    _graph(parent)
    _subgraph_phase(parent, child_path=child, input_field="text", output_field="parent_output")
    _graph(child, inputs_field="text", outputs_field="child_output")
    _logic_phase(child)

    compiled = SkillLoader().compile_skill(parent, skill_resolver=DictSkillResolver({"child": child}))

    assert compiled.nodes[0].phase_name == "main"


def test_graph_serializer_fresh_render_does_not_synthesize_graph_boundaries() -> None:
    manifest = GraphManifest(
        schema_version="v0.3.0",
        name="serializer",
        io=PhaseIOSchema(inputs=_object_schema("text"), outputs=_object_schema("result")),
        phases=["main"],
    )

    rendered = serialize_graph(manifest)

    assert 'schema_version: "v0.3.0"' in rendered
    assert "phases:" in rendered
    assert "<phase>main</phase>" in rendered
    assert 'depends_on="input"' not in rendered
    assert "<phase output" not in rendered
    assert "<input" not in rendered
    assert "<output" not in rendered
