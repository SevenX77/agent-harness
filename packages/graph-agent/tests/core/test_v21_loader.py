from __future__ import annotations

from pathlib import Path

import pytest
from graph_agent.core.exceptions import SkillLoadError
from graph_agent.core.loader import SkillLoader, load_workflow_from_md
from graph_agent.core.manifest import GraphPhaseRef, SkillNodeAST
from graph_agent.core.parser import extract_raw_blocks
from pydantic import ValidationError


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _valid_skill(root: Path) -> None:
    _write(
        root / "GRAPH.md",
        """---
schema_version: "2.1"
name: hello-v21
description: hello
---
<input src="io/inputs.json" />
<output src="io/outputs.json" />
<phase id="hello" src="phases/hello" depends_on="" />
""",
    )
    _write(root / "io" / "inputs.json", "{}\n")
    _write(root / "io" / "outputs.json", "{}\n")
    _write(
        root / "phases" / "hello" / "SKILL.md",
        """---
mode: skill
name: hello
---
<system_prompt>
Say hello. Preserve raw text like A < B and <div>demo</div>.
</system_prompt>
<exit_contract>
Call finish_task when done.
</exit_contract>
""",
    )


def _write_graph_with_io_refs(
    root: Path, input_ref: str, output_ref: str = "io/outputs.json"
) -> None:
    _write(
        root / "GRAPH.md",
        f"""---
schema_version: "2.1"
name: hello-v21
description: hello
---
<input src="{input_ref}" />
<output src="{output_ref}" />
<phase id="hello" src="phases/hello" depends_on="" />
""",
    )


def _write_graph_with_phase_lines(root: Path, phase_lines: list[str]) -> None:
    _write(
        root / "GRAPH.md",
        """---
schema_version: "2.1"
name: hello-v21
description: hello
---
<input src="io/inputs.json" />
<output src="io/outputs.json" />
"""
        + "\n".join(phase_lines)
        + "\n",
    )


def _write_skill_phase(root: Path, phase_dir: str) -> None:
    _write(
        root / phase_dir / "SKILL.md",
        f"""---
mode: skill
name: {Path(phase_dir).name}
---
<system_prompt>
Run {phase_dir}.
</system_prompt>
<exit_contract>
Finish {phase_dir}.
</exit_contract>
""",
    )


def _base_v21_root(root: Path) -> None:
    _write(root / "io" / "inputs.json", "{}\n")
    _write(root / "io" / "outputs.json", "{}\n")


def _assert_fatal(exc: pytest.ExceptionInfo[SkillLoadError], path_fragment: str) -> None:
    message = str(exc.value)
    assert "[F-v3-route]" in message
    assert path_fragment in message
    assert ":1" in message or ":2" in message or ":5" in message


def _assert_io_fatal(exc: pytest.ExceptionInfo[SkillLoadError], path_fragment: str) -> None:
    message = str(exc.value)
    assert "[F-v3-io]" in message
    assert path_fragment in message
    assert ":1" in message or ":2" in message


def _assert_graph_fatal(exc: pytest.ExceptionInfo[SkillLoadError]) -> None:
    message = str(exc.value)
    assert "[F-v3-graph]" in message
    assert "GRAPH.md:" in message


def test_v21_happy_path_routes_graph_and_skill_raw_blocks(tmp_path: Path) -> None:
    _valid_skill(tmp_path)

    compiled = SkillLoader().compile_skill(tmp_path)

    assert compiled.manifest.schema_version == "2.1"
    assert compiled.manifest.io_inputs_ref == "io/inputs.json"
    assert compiled.manifest.io_outputs_ref == "io/outputs.json"
    assert compiled.manifest.phases[0].id == "hello"
    assert compiled.raw["io"]["inputs"] == {}
    assert compiled.raw["io"]["outputs"] == {}
    assert len(compiled.nodes) == 1
    node = compiled.nodes[0]
    assert node.mode == "skill"
    assert isinstance(node.ast, SkillNodeAST)
    assert "A < B" in node.raw_blocks["system_prompt"]
    assert "<div>demo</div>" in node.raw_blocks["system_prompt"]
    assert node.raw_blocks["exit_contract"] == "Call finish_task when done."


def test_extract_raw_blocks_keeps_inner_angle_brackets() -> None:
    blocks = extract_raw_blocks(
        "<system_prompt>Use A < B and <div>x</div>.</system_prompt>",
        ["system_prompt"],
    )
    assert blocks["system_prompt"] == "Use A < B and <div>x</div>."


def test_io_schema_happy_path(tmp_path: Path) -> None:
    _valid_skill(tmp_path)
    _write(tmp_path / "io" / "inputs.json", '{"type": "object"}\n')
    _write(tmp_path / "io" / "outputs.json", '{"type": "object"}\n')

    compiled = SkillLoader().compile_skill(tmp_path)

    assert compiled.manifest.io_inputs_ref == "io/inputs.json"
    assert compiled.manifest.io_outputs_ref == "io/outputs.json"
    assert compiled.raw["io"]["inputs"] == {"type": "object"}
    assert compiled.raw["io"]["outputs"] == {"type": "object"}


def test_io_inputs_missing(tmp_path: Path) -> None:
    _valid_skill(tmp_path)
    (tmp_path / "io" / "inputs.json").unlink()

    with pytest.raises(SkillLoadError) as exc:
        SkillLoader().compile_skill(tmp_path)

    _assert_io_fatal(exc, "io/inputs.json")
    assert "missing IO schema referenced by GRAPH.md input" in str(exc.value)


def test_io_outputs_missing(tmp_path: Path) -> None:
    _valid_skill(tmp_path)
    (tmp_path / "io" / "outputs.json").unlink()

    with pytest.raises(SkillLoadError) as exc:
        SkillLoader().compile_skill(tmp_path)

    _assert_io_fatal(exc, "io/outputs.json")
    assert "missing IO schema referenced by GRAPH.md output" in str(exc.value)


def test_io_inputs_invalid_json(tmp_path: Path) -> None:
    _valid_skill(tmp_path)
    _write(tmp_path / "io" / "inputs.json", "{bad\n")

    with pytest.raises(SkillLoadError) as exc:
        SkillLoader().compile_skill(tmp_path)

    _assert_io_fatal(exc, "io/inputs.json")
    assert "invalid JSON:" in str(exc.value)


def test_io_outputs_top_level_not_object(tmp_path: Path) -> None:
    _valid_skill(tmp_path)
    _write(tmp_path / "io" / "outputs.json", "[]\n")

    with pytest.raises(SkillLoadError) as exc:
        SkillLoader().compile_skill(tmp_path)

    _assert_io_fatal(exc, "io/outputs.json")
    assert "JSON Schema document must be an object" in str(exc.value)


def test_io_inputs_invalid_schema(tmp_path: Path) -> None:
    _valid_skill(tmp_path)
    _write(tmp_path / "io" / "inputs.json", '{"type": 123}\n')

    with pytest.raises(SkillLoadError) as exc:
        SkillLoader().compile_skill(tmp_path)

    _assert_io_fatal(exc, "io/inputs.json")
    assert "invalid JSON Schema:" in str(exc.value)


def test_io_ref_non_json_suffix(tmp_path: Path) -> None:
    _valid_skill(tmp_path)
    _write_graph_with_io_refs(tmp_path, "io/inputs.yaml")
    _write(tmp_path / "io" / "inputs.yaml", "type: object\n")

    with pytest.raises(SkillLoadError) as exc:
        SkillLoader().compile_skill(tmp_path)

    _assert_io_fatal(exc, "io/inputs.yaml")
    assert "IO schema refs must point to .json files" in str(exc.value)


def test_io_ref_escape_root(tmp_path: Path) -> None:
    _valid_skill(tmp_path)
    _write_graph_with_io_refs(tmp_path, "../../etc/passwd")

    with pytest.raises(SkillLoadError) as exc:
        SkillLoader().compile_skill(tmp_path)

    _assert_io_fatal(exc, "../../etc/passwd")
    assert "IO schema ref must stay inside skill root" in str(exc.value)


def test_topology_happy_path_chain(tmp_path: Path) -> None:
    _base_v21_root(tmp_path)
    _write_graph_with_phase_lines(
        tmp_path,
        [
            '<phase id="prep" src="phases/prep" depends_on="" />',
            '<phase id="draft" src="phases/draft" depends_on="prep" />',
            '<phase id="review" src="phases/review" depends_on="draft" />',
        ],
    )
    for phase in ["phases/prep", "phases/draft", "phases/review"]:
        _write_skill_phase(tmp_path, phase)

    compiled = SkillLoader().compile_skill(tmp_path)

    assert [phase.id for phase in compiled.manifest.phases] == ["prep", "draft", "review"]


def test_topology_multi_entry_happy_path(tmp_path: Path) -> None:
    _base_v21_root(tmp_path)
    _write_graph_with_phase_lines(
        tmp_path,
        [
            '<phase id="left" src="phases/left" depends_on="" />',
            '<phase id="right" src="phases/right" depends_on="" />',
            '<phase id="join" src="phases/join" depends_on="left right" />',
        ],
    )
    for phase in ["phases/left", "phases/right", "phases/join"]:
        _write_skill_phase(tmp_path, phase)

    compiled = SkillLoader().compile_skill(tmp_path)

    assert compiled.manifest.phases[1].depends_on == []
    assert compiled.manifest.phases[2].depends_on == ["left", "right"]


def test_topology_missing_depends_on_non_entry(tmp_path: Path) -> None:
    _base_v21_root(tmp_path)
    _write_graph_with_phase_lines(
        tmp_path,
        [
            '<phase id="prep" src="phases/prep" depends_on="" />',
            '<phase id="draft" src="phases/draft" />',
        ],
    )
    _write_skill_phase(tmp_path, "phases/prep")
    _write_skill_phase(tmp_path, "phases/draft")

    with pytest.raises(SkillLoadError) as exc:
        SkillLoader().compile_skill(tmp_path)

    _assert_graph_fatal(exc)
    assert "phase 'draft' missing required depends_on" in str(exc.value)
    assert 'use depends_on="" for entry phases' in str(exc.value)


def test_topology_missing_depends_on_entry_phase(tmp_path: Path) -> None:
    _base_v21_root(tmp_path)
    _write_graph_with_phase_lines(tmp_path, ['<phase id="prep" src="phases/prep" />'])
    _write_skill_phase(tmp_path, "phases/prep")

    with pytest.raises(SkillLoadError) as exc:
        SkillLoader().compile_skill(tmp_path)

    _assert_graph_fatal(exc)
    assert "phase 'prep' missing required depends_on" in str(exc.value)
    assert 'use depends_on="" for entry phases' in str(exc.value)


def test_topology_duplicate_phase_id(tmp_path: Path) -> None:
    _base_v21_root(tmp_path)
    _write_graph_with_phase_lines(
        tmp_path,
        [
            '<phase id="dup" src="phases/one" depends_on="" />',
            '<phase id="dup" src="phases/two" depends_on="dup" />',
        ],
    )
    _write_skill_phase(tmp_path, "phases/one")
    _write_skill_phase(tmp_path, "phases/two")

    with pytest.raises(SkillLoadError) as exc:
        SkillLoader().compile_skill(tmp_path)

    _assert_graph_fatal(exc)
    assert "duplicate phase id 'dup'" in str(exc.value)


def test_topology_dep_unknown_phase(tmp_path: Path) -> None:
    _base_v21_root(tmp_path)
    _write_graph_with_phase_lines(
        tmp_path,
        [
            '<phase id="prep" src="phases/prep" depends_on="" />',
            '<phase id="draft" src="phases/draft" depends_on="missing" />',
        ],
    )
    _write_skill_phase(tmp_path, "phases/prep")
    _write_skill_phase(tmp_path, "phases/draft")

    with pytest.raises(SkillLoadError) as exc:
        SkillLoader().compile_skill(tmp_path)

    _assert_graph_fatal(exc)
    assert "phase 'draft' depends_on unknown phase 'missing'" in str(exc.value)


def test_topology_self_loop(tmp_path: Path) -> None:
    _base_v21_root(tmp_path)
    _write_graph_with_phase_lines(
        tmp_path, ['<phase id="loop" src="phases/loop" depends_on="loop" />']
    )
    _write_skill_phase(tmp_path, "phases/loop")

    with pytest.raises(SkillLoadError) as exc:
        SkillLoader().compile_skill(tmp_path)

    _assert_graph_fatal(exc)
    assert "phase 'loop' cannot depend on itself" in str(exc.value)


def test_topology_cycle_detected(tmp_path: Path) -> None:
    _base_v21_root(tmp_path)
    _write_graph_with_phase_lines(
        tmp_path,
        [
            '<phase id="a" src="phases/a" depends_on="c" />',
            '<phase id="b" src="phases/b" depends_on="a" />',
            '<phase id="c" src="phases/c" depends_on="b" />',
        ],
    )
    for phase in ["phases/a", "phases/b", "phases/c"]:
        _write_skill_phase(tmp_path, phase)

    with pytest.raises(SkillLoadError) as exc:
        SkillLoader().compile_skill(tmp_path)

    _assert_graph_fatal(exc)
    assert "cycle detected:" in str(exc.value)
    assert " -> " in str(exc.value)


def test_topology_orphan_disconnected(tmp_path: Path) -> None:
    _base_v21_root(tmp_path)
    _write_graph_with_phase_lines(
        tmp_path,
        [
            '<phase id="main" src="phases/main" depends_on="" />',
            '<phase id="isolated" src="phases/isolated" depends_on="" />',
        ],
    )
    _write_skill_phase(tmp_path, "phases/main")
    _write_skill_phase(tmp_path, "phases/isolated")

    with pytest.raises(SkillLoadError) as exc:
        SkillLoader().compile_skill(tmp_path)

    _assert_graph_fatal(exc)
    assert "orphan phase 'isolated' is disconnected from the main graph" in str(exc.value)


def test_topology_src_escape_root(tmp_path: Path) -> None:
    _base_v21_root(tmp_path)
    _write_graph_with_phase_lines(tmp_path, ['<phase id="bad" src="../outside" depends_on="" />'])
    (tmp_path / "phases" / "dummy").mkdir(parents=True)

    with pytest.raises(SkillLoadError) as exc:
        SkillLoader().compile_skill(tmp_path)

    _assert_graph_fatal(exc)
    assert "phase 'bad' src must stay inside skill root" in str(exc.value)


def test_topology_src_directory_missing(tmp_path: Path) -> None:
    _base_v21_root(tmp_path)
    _write_graph_with_phase_lines(
        tmp_path, ['<phase id="bad" src="phases/missing" depends_on="" />']
    )
    (tmp_path / "phases" / "dummy").mkdir(parents=True)

    with pytest.raises(SkillLoadError) as exc:
        SkillLoader().compile_skill(tmp_path)

    _assert_graph_fatal(exc)
    assert "phase 'bad' src 'phases/missing' has no LOGIC.md/SUBGRAPH.md/SKILL.md" in str(exc.value)


def test_topology_src_no_node_file(tmp_path: Path) -> None:
    _base_v21_root(tmp_path)
    _write_graph_with_phase_lines(tmp_path, ['<phase id="bad" src="phases/empty" depends_on="" />'])
    (tmp_path / "phases" / "empty").mkdir(parents=True)

    with pytest.raises(SkillLoadError) as exc:
        SkillLoader().compile_skill(tmp_path)

    _assert_graph_fatal(exc)
    assert "phase 'bad' src 'phases/empty' has no LOGIC.md/SUBGRAPH.md/SKILL.md" in str(exc.value)


def test_topology_phase_missing_id(tmp_path: Path) -> None:
    _base_v21_root(tmp_path)
    _write_graph_with_phase_lines(tmp_path, ['<phase src="phases/hello" />'])
    _write_skill_phase(tmp_path, "phases/hello")

    with pytest.raises(SkillLoadError) as exc:
        SkillLoader().compile_skill(tmp_path)

    _assert_graph_fatal(exc)
    assert "phase tag missing required id" in str(exc.value)


def test_topology_phase_missing_src(tmp_path: Path) -> None:
    _base_v21_root(tmp_path)
    _write_graph_with_phase_lines(tmp_path, ['<phase id="hello" />'])
    (tmp_path / "phases" / "dummy").mkdir(parents=True)

    with pytest.raises(SkillLoadError) as exc:
        SkillLoader().compile_skill(tmp_path)

    _assert_graph_fatal(exc)
    assert "phase 'hello' missing required src" in str(exc.value)


def test_graph_phase_ref_schema_requires_depends_on() -> None:
    schema = GraphPhaseRef.model_json_schema()

    assert "depends_on" in schema["required"]
    with pytest.raises(ValidationError, match="depends_on"):
        GraphPhaseRef.model_validate({"id": "hello", "src": "phases/hello"})


def test_root_skill_md_is_rejected(tmp_path: Path) -> None:
    _write(tmp_path / "SKILL.md", "---\nschema_version: '2.0'\n---\n")
    _write(tmp_path / "GRAPH.md", "---\nschema_version: '2.1'\nname: x\n---\n")
    _write(tmp_path / "phases" / "hello" / "SKILL.md", "---\nmode: skill\n---\n")

    with pytest.raises(SkillLoadError) as exc:
        SkillLoader().compile_skill(tmp_path)

    _assert_fatal(exc, "SKILL.md")
    assert "schema 2.0 root SKILL.md is not supported; use GRAPH.md" in str(exc.value)


def test_phase_graph_md_is_rejected(tmp_path: Path) -> None:
    _valid_skill(tmp_path)
    _write(tmp_path / "phases" / "hello" / "GRAPH.md", "---\nname: bad\n---\n")

    with pytest.raises(SkillLoadError) as exc:
        SkillLoader().compile_skill(tmp_path)

    _assert_fatal(exc, "phases/hello/GRAPH.md")
    assert "GRAPH.md is only allowed at skill root" in str(exc.value)


def test_mode_mismatch_is_rejected(tmp_path: Path) -> None:
    _valid_skill(tmp_path)
    _write(
        tmp_path / "phases" / "hello" / "SKILL.md",
        """---
mode: logic
name: hello
---
<system_prompt>x</system_prompt>
<exit_contract>done</exit_contract>
""",
    )

    with pytest.raises(SkillLoadError) as exc:
        SkillLoader().compile_skill(tmp_path)

    _assert_fatal(exc, "phases/hello/SKILL.md")
    assert "mode 'logic' does not match SKILL.md filename" in str(exc.value)


def test_missing_graph_is_rejected(tmp_path: Path) -> None:
    _write(tmp_path / "phases" / "hello" / "SKILL.md", "---\nmode: skill\n---\n")

    with pytest.raises(SkillLoadError) as exc:
        SkillLoader().compile_skill(tmp_path)

    _assert_fatal(exc, "GRAPH.md")
    assert "missing required GRAPH.md" in str(exc.value)


def test_missing_phases_is_rejected(tmp_path: Path) -> None:
    _write(tmp_path / "GRAPH.md", "---\nschema_version: '2.1'\nname: x\n---\n")

    with pytest.raises(SkillLoadError) as exc:
        SkillLoader().compile_skill(tmp_path)

    _assert_fatal(exc, "phases")
    assert "missing phases directory or phase entries" in str(exc.value)


def test_empty_phases_is_rejected(tmp_path: Path) -> None:
    _write(tmp_path / "GRAPH.md", "---\nschema_version: '2.1'\nname: x\n---\n")
    (tmp_path / "phases").mkdir()

    with pytest.raises(SkillLoadError) as exc:
        SkillLoader().compile_skill(tmp_path)

    _assert_fatal(exc, "phases")
    assert "missing phases directory or phase entries" in str(exc.value)


@pytest.mark.parametrize("tag", ["phase", "depends_on", "edge"])
def test_phase_body_topology_tags_are_rejected(tmp_path: Path, tag: str) -> None:
    _valid_skill(tmp_path)
    _write(
        tmp_path / "phases" / "hello" / "SKILL.md",
        f"""---
mode: skill
name: hello
---
<system_prompt>
bad
<{tag} id="bad" />
</system_prompt>
<exit_contract>done</exit_contract>
""",
    )

    with pytest.raises(SkillLoadError) as exc:
        SkillLoader().compile_skill(tmp_path)

    assert "[F-v3-route]" in str(exc.value)
    assert "phases/hello/SKILL.md:" in str(exc.value)
    assert f"topology tag '<{tag}>' is forbidden" in str(exc.value)


def test_duplicate_phase_node_files_are_rejected(tmp_path: Path) -> None:
    _valid_skill(tmp_path)
    _write(tmp_path / "phases" / "hello" / "LOGIC.md", "---\nmode: logic\n---\n")

    with pytest.raises(SkillLoadError) as exc:
        SkillLoader().compile_skill(tmp_path)

    _assert_fatal(exc, "phases/hello/SKILL.md")
    assert "phase directory contains multiple node files" in str(exc.value)


def test_load_workflow_from_md_rejects_file_path(tmp_path: Path) -> None:
    _valid_skill(tmp_path)

    with pytest.raises(SkillLoadError) as exc:
        load_workflow_from_md(tmp_path / "GRAPH.md")

    _assert_fatal(exc, "GRAPH.md")
    assert "accepts a V2.1 skill root directory" in str(exc.value)
