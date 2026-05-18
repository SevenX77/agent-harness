from __future__ import annotations

from pathlib import Path

import pytest

from graph_agent.core.exceptions import SkillLoadError
from graph_agent.core.loader import SkillLoader
from graph_agent.core.manifest import SkillNodeAST


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
    relative: str,
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
) -> None:
    root = parent_phase_root / relative
    _write(
        root / "GRAPH.md",
        """---
schema_version: "2.1"
name: child
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
    _sub_skill(tmp_path / "phases" / "main", "subskills/beat_extractor")
    _sub_skill(tmp_path / "phases" / "main", "subskills/producer_strategy")
    _skill(
        tmp_path,
        _skill_text(
            phase_config="""  tools:
    - read_file
  subagents:
    - name: beat_extractor
      path: subskills/beat_extractor
      description: Extract narrative beats.
    - name: producer_strategy
      path: subskills/producer_strategy
      description: Score audience pull.
"""
        ),
    )

    compiled = SkillLoader().compile_skill(tmp_path)
    ast = compiled.nodes[0].ast

    assert isinstance(ast, SkillNodeAST)
    assert ast.tools == ["read_file"]
    assert [subagent.name for subagent in ast.subagents] == [
        "beat_extractor",
        "producer_strategy",
    ]
    assert ast.subagents[0].path == "subskills/beat_extractor"
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
    - path: subskills/missing_name
      description: Missing name.
""",
            "name",
        ),
        (
            """  subagents:
    - name: bad-name
      path: subskills/bad
      description: Invalid name.
""",
            "bad-name",
        ),
        (
            """  subagents:
    - name: missing_description
      path: subskills/missing_description
""",
            "description",
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
    _sub_skill(tmp_path / "phases" / "main", "subskills/beat_extractor")
    _skill(
        tmp_path,
        _skill_text(
            phase_config="""  subagents:
    - name: beat_extractor
      path: subskills/beat_extractor
      description: Extract narrative beats.
"""
        ),
    )

    compiled = SkillLoader().compile_skill(tmp_path)
    subagents = compiled.subagents_by_phase["main"]

    assert len(subagents) == 1
    assert subagents[0].name == "beat_extractor"
    assert subagents[0].root == tmp_path / "phases" / "main" / "subskills" / "beat_extractor"
    assert subagents[0].input_schema["properties"]["scene_text"]["type"] == "string"


@pytest.mark.parametrize(
    ("relative", "message"),
    [
        ("subskills/missing", "does not exist"),
        ("subskills/not_a_skill", "has no GRAPH.md"),
    ],
)
def test_subagent_target_must_exist_and_be_v21_skill_root(
    tmp_path: Path,
    relative: str,
    message: str,
) -> None:
    _base(tmp_path)
    if relative.endswith("not_a_skill"):
        (tmp_path / "phases" / "main" / relative).mkdir(parents=True)
    _skill(
        tmp_path,
        _skill_text(
            phase_config=f"""  subagents:
    - name: beat_extractor
      path: {relative}
      description: Extract narrative beats.
"""
        ),
    )

    with pytest.raises(SkillLoadError, match=message):
        SkillLoader().compile_skill(tmp_path)


def test_subagent_target_must_declare_io_inputs(tmp_path: Path) -> None:
    _base(tmp_path)
    _sub_skill(tmp_path / "phases" / "main", "subskills/beat_extractor", inputs="{}\n")
    _skill(
        tmp_path,
        _skill_text(
            phase_config="""  subagents:
    - name: beat_extractor
      path: subskills/beat_extractor
      description: Extract narrative beats.
"""
        ),
    )

    with pytest.raises(SkillLoadError, match="io.inputs"):
        SkillLoader().compile_skill(tmp_path)
