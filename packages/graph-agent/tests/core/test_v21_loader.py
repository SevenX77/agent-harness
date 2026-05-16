from __future__ import annotations

from pathlib import Path

import pytest

from graph_agent.core.exceptions import SkillLoadError
from graph_agent.core.loader import SkillLoader, load_workflow_from_md
from graph_agent.core.manifest import SkillNodeAST
from graph_agent.core.parser import extract_raw_blocks


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
<phase id="hello" src="phases/hello" />
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


def _assert_fatal(exc: pytest.ExceptionInfo[SkillLoadError], path_fragment: str) -> None:
    message = str(exc.value)
    assert "[F-v21-route]" in message
    assert path_fragment in message
    assert ":1" in message or ":2" in message or ":5" in message


def test_v21_happy_path_routes_graph_and_skill_raw_blocks(tmp_path: Path) -> None:
    _valid_skill(tmp_path)

    compiled = SkillLoader().compile_skill(tmp_path)

    assert compiled.manifest.schema_version == "2.1"
    assert compiled.manifest.io_inputs_ref == "io/inputs.json"
    assert compiled.manifest.io_outputs_ref == "io/outputs.json"
    assert compiled.manifest.phases[0].id == "hello"
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

    assert "[F-v21-route]" in str(exc.value)
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
