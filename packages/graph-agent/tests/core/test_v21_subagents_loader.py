from __future__ import annotations

from pathlib import Path

import pytest
from graph_agent.core.exceptions import SkillLoadError
from graph_agent.core.loader import SkillLoader
from graph_agent.core.manifest import SkillNodeAST
from tests.conftest import InMemorySkillResolver

_FIXTURES = Path(__file__).parents[1] / "fixtures"


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _base(root: Path, phase: str = "main") -> None:
    _write(
        root / "GRAPH.md",
        f"""---
schema_version: "2.1"
name: subagent-test
---
<input src="io/inputs.json" />
<output src="io/outputs.json" />
<phase id="{phase}" src="phases/{phase}" depends_on="" />
""",
    )
    _write(root / "io" / "inputs.json", "{}\n")
    _write(root / "io" / "outputs.json", "{}\n")


def _skill(root: Path, body: str, phase: str = "main") -> None:
    _write(root / "phases" / phase / "SKILL.md", body)


def _sub_skill(
    parent_phase_root: Path,
    name: str,
    *,
    inputs: str = """{
  "type": "object",
  "properties": {
    "scene_text": {
      "type": "string",
      "description": "Scene text to analyze."
    }
  },
  "required": ["scene_text"]
}
""",
) -> Path:
    root = parent_phase_root / "subskills" / name
    _write(
        root / "GRAPH.md",
        f"""---
schema_version: "2.1"
name: {name}
---
<input src="io/inputs.json" />
<output src="io/outputs.json" />
<phase id="child" src="phases/child" depends_on="" />
""",
    )
    _write(root / "io" / "inputs.json", inputs)
    _write(root / "io" / "outputs.json", "{}\n")
    _write(
        root / "phases" / "child" / "SKILL.md",
        """---
mode: skill
name: child
---
<system_prompt>
Do child work.
</system_prompt>
<exit_contract>
Call finish_task.
</exit_contract>
""",
    )
    return root


def _subskill_resolver(tmp_path: Path, *names: str) -> InMemorySkillResolver:
    return InMemorySkillResolver(
        {name: tmp_path / "phases" / "main" / "subskills" / name for name in names}
    )


def _skill_text(*, phase_config: str = "") -> str:
    config_block = f"phase_config:\n{phase_config}" if phase_config else ""
    return f"""---
mode: skill
name: main
{config_block}
---
<system_prompt>
Do work.
</system_prompt>
<exit_contract>
Call finish_task.
</exit_contract>
"""


def test_skill_phase_config_subagents_parse_into_ast(tmp_path: Path) -> None:
    _base(tmp_path)
    _sub_skill(tmp_path / "phases" / "main", "beat_extractor")
    _sub_skill(tmp_path / "phases" / "main", "producer_strategy")
    _skill(
        tmp_path,
        _skill_text(
            phase_config="""  tools:
    - read_file
  subagents:
    - name: beat_extractor
      target_skill: beat_extractor
      description: Extract narrative beats.
    - name: producer_strategy
      target_skill: producer_strategy
      description: Score audience pull.
"""
        ),
    )

    compiled = SkillLoader().compile_skill(
        tmp_path,
        skill_resolver=_subskill_resolver(tmp_path, "beat_extractor", "producer_strategy"),
    )
    ast = compiled.nodes[0].ast

    assert isinstance(ast, SkillNodeAST)
    assert ast.tools == ["read_file"]
    assert [subagent.name for subagent in ast.subagents] == [
        "beat_extractor",
        "producer_strategy",
    ]
    assert ast.subagents[0].target_skill == "beat_extractor"
    assert ast.subagents[0].description == "Extract narrative beats."


def test_skill_without_subagents_keeps_empty_default(tmp_path: Path) -> None:
    _base(tmp_path)
    _skill(tmp_path, _skill_text())

    ast = SkillLoader().compile_skill(tmp_path).nodes[0].ast

    assert isinstance(ast, SkillNodeAST)
    assert ast.subagents == []


@pytest.mark.parametrize(
    ("phase_config", "message"),
    [
        (
            """  subagents:
    - target_skill: missing_name
      description: Missing name.
""",
            "name",
        ),
        (
            """  subagents:
    - name: bad-name
      target_skill: bad
      description: Invalid name.
""",
            "bad-name",
        ),
        (
            """  subagents:
    - name: missing_description
      target_skill: missing_description
""",
            "description",
        ),
        (
            """  subagents:
    - name: missing_target
      description: Missing target.
""",
            "target_skill",
        ),
        (
            """  subagents:
    - name: legacy_path
      path: subskills/legacy
      description: Legacy path is forbidden.
""",
            "Extra inputs are not permitted",
        ),
    ],
)
def test_invalid_subagent_declaration_fails_compile(
    tmp_path: Path,
    phase_config: str,
    message: str,
) -> None:
    _base(tmp_path)
    _skill(tmp_path, _skill_text(phase_config=phase_config))

    with pytest.raises(SkillLoadError, match=message):
        SkillLoader().compile_skill(tmp_path)


def test_subagent_metadata_resolves_target_and_input_schema(tmp_path: Path) -> None:
    _base(tmp_path)
    _sub_skill(tmp_path / "phases" / "main", "beat_extractor")
    _skill(
        tmp_path,
        _skill_text(
            phase_config="""  subagents:
    - name: beat_extractor
      target_skill: beat_extractor
      description: Extract narrative beats.
"""
        ),
    )

    compiled = SkillLoader().compile_skill(
        tmp_path,
        skill_resolver=_subskill_resolver(tmp_path, "beat_extractor"),
    )
    subagents = compiled.subagents_by_phase["main"]

    assert len(subagents) == 1
    assert subagents[0].name == "beat_extractor"
    assert subagents[0].target_skill == "beat_extractor"
    assert subagents[0].root == tmp_path / "phases" / "main" / "subskills" / "beat_extractor"
    assert subagents[0].input_schema["properties"]["scene_text"]["type"] == "string"
    assert subagents[0].input_model.__name__ == "MainBeatExtractorInput"
    assert subagents[0].expected_schema["properties"]["scene_text"]["type"] == "string"


def test_subagent_input_model_validates_basic_json_schema_types(tmp_path: Path) -> None:
    _base(tmp_path)
    _sub_skill(
        tmp_path / "phases" / "main",
        "typed_expert",
        inputs="""{
  "type": "object",
  "properties": {
    "title": {"type": "string", "description": "Title"},
    "count": {"type": "integer"},
    "score": {"type": "number"},
    "published": {"type": "boolean"},
    "tags": {"type": "array"},
    "metadata": {"type": "object"}
  },
  "required": ["title", "count", "score", "published", "tags", "metadata"]
}
""",
    )
    _skill(
        tmp_path,
        _skill_text(
            phase_config="""  subagents:
    - name: typed_expert
      target_skill: typed_expert
      description: Validate typed input.
"""
        ),
    )

    input_model = SkillLoader().compile_skill(
        tmp_path,
        skill_resolver=_subskill_resolver(tmp_path, "typed_expert"),
    ).subagents_by_phase["main"][0].input_model
    valid = input_model.model_validate(
        {
            "title": "A",
            "count": 2,
            "score": 0.5,
            "published": True,
            "tags": ["x"],
            "metadata": {"k": "v"},
        }
    )

    assert valid.model_dump()["title"] == "A"
    with pytest.raises(ValueError, match="Field required"):
        input_model.model_validate({"title": "A"})
    with pytest.raises(ValueError, match="Extra inputs are not permitted"):
        input_model.model_validate(
            {
                "title": "A",
                "count": 2,
                "score": 0.5,
                "published": True,
                "tags": [],
                "metadata": {},
                "unknown": True,
            }
        )


def test_subagent_tools_are_injected_into_phase_tool_registry(tmp_path: Path) -> None:
    _base(tmp_path)
    _sub_skill(tmp_path / "phases" / "main", "beat_extractor")
    _sub_skill(tmp_path / "phases" / "main", "producer_strategy")
    _skill(
        tmp_path,
        _skill_text(
            phase_config="""  subagents:
    - name: beat_extractor
      target_skill: beat_extractor
      description: Extract narrative beats.
    - name: producer_strategy
      target_skill: producer_strategy
      description: Score audience pull.
"""
        ),
    )

    compiled = SkillLoader().compile_skill(
        tmp_path,
        skill_resolver=_subskill_resolver(tmp_path, "beat_extractor", "producer_strategy"),
    )
    tools = {tool.name: tool for tool in compiled.tools.for_phase("main")}

    assert sorted(tools) == ["call_subagent_beat_extractor", "call_subagent_producer_strategy"]
    beat_tool = tools["call_subagent_beat_extractor"]
    assert "Extract narrative beats." in beat_tool.description
    assert "no more than 3 inputs" in beat_tool.description
    assert beat_tool.metadata is not None
    assert beat_tool.metadata["target_skill"] == "beat_extractor"
    assert "subagent_path" not in beat_tool.metadata
    assert beat_tool.args_schema is not None
    schema = beat_tool.args_schema.model_json_schema()
    assert "inputs" in schema["properties"]
    assert "MainBeatExtractorInput" in schema["$defs"]


def test_subagent_dynamic_tool_name_conflict_fails_compile(tmp_path: Path) -> None:
    _base(tmp_path)
    _sub_skill(tmp_path / "phases" / "main", "beat_extractor")
    _skill(
        tmp_path,
        _skill_text(
            phase_config="""  subagents:
    - name: beat_extractor
      target_skill: beat_extractor
      description: Extract narrative beats.
"""
        ),
    )
    _write(
        tmp_path / "phases" / "main" / "tools" / "conflict.py",
        "def call_subagent_beat_extractor(x: str) -> str:\n    return x\n",
    )

    with pytest.raises(SkillLoadError, match="conflicts with an existing tool"):
        SkillLoader().compile_skill(
            tmp_path,
            skill_resolver=_subskill_resolver(tmp_path, "beat_extractor"),
        )


def test_static_subagent_minimal_fixture_compiles() -> None:
    root = _FIXTURES / "subagent_minimal"
    compiled = SkillLoader().compile_skill(
        root,
        skill_resolver=InMemorySkillResolver(
            {"echo_expert": root / "phases" / "main" / "subskills" / "echo_expert"}
        ),
    )

    subagents = compiled.subagents_by_phase["main"]
    tools = {tool.name: tool for tool in compiled.tools.for_phase("main")}

    assert subagents[0].name == "echo_expert"
    assert subagents[0].target_skill == "echo_expert"
    assert subagents[0].input_model.model_validate({"text": "hello"}).text == "hello"
    assert "call_subagent_echo_expert" in tools


def test_subagent_target_requires_resolver(tmp_path: Path) -> None:
    _base(tmp_path)
    _skill(
        tmp_path,
        _skill_text(
            phase_config="""  subagents:
    - name: beat_extractor
      target_skill: beat_extractor
      description: Extract narrative beats.
"""
        ),
    )

    with pytest.raises(SkillLoadError, match="no skill_resolver was provided"):
        SkillLoader().compile_skill(tmp_path)


@pytest.mark.parametrize(
    ("roots", "message"),
    [
        ({}, r"\[F-v3-skill-not-registered\]"),
        ({"beat_extractor": "not_a_skill"}, r"\[F-v3-resolver-path-invalid\]"),
    ],
)
def test_subagent_target_must_resolve_to_skill_root(
    tmp_path: Path,
    roots: dict[str, str],
    message: str,
) -> None:
    _base(tmp_path)
    if roots:
        (tmp_path / "phases" / "main" / "subskills" / "not_a_skill").mkdir(parents=True)
    _skill(
        tmp_path,
        _skill_text(
            phase_config="""  subagents:
    - name: beat_extractor
      target_skill: beat_extractor
      description: Extract narrative beats.
"""
        ),
    )
    resolver = InMemorySkillResolver(
        {
            skill_id: tmp_path / "phases" / "main" / "subskills" / relative
            for skill_id, relative in roots.items()
        }
    )

    with pytest.raises(SkillLoadError, match=message):
        SkillLoader().compile_skill(tmp_path, skill_resolver=resolver)


def test_subagent_target_must_declare_io_inputs(tmp_path: Path) -> None:
    _base(tmp_path)
    _sub_skill(tmp_path / "phases" / "main", "beat_extractor", inputs="{}\n")
    _skill(
        tmp_path,
        _skill_text(
            phase_config="""  subagents:
    - name: beat_extractor
      target_skill: beat_extractor
      description: Extract narrative beats.
"""
        ),
    )

    with pytest.raises(SkillLoadError, match="io.inputs"):
        SkillLoader().compile_skill(
            tmp_path,
            skill_resolver=_subskill_resolver(tmp_path, "beat_extractor"),
        )
