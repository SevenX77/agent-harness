from __future__ import annotations

from pathlib import Path

from graph_agent.core.compiler import compile_skill
from graph_agent.core.loader import get_phase_token_info


def _write_v030_phase_token_skill(root: Path) -> None:
    (root / "phases" / "prepare" / "actions").mkdir(parents=True)
    (root / "phases" / "branch_a" / "actions").mkdir(parents=True)
    (root / "phases" / "branch_b" / "actions").mkdir(parents=True)
    (root / "phases" / "assemble" / "actions").mkdir(parents=True)
    (root / "GRAPH.md").write_text(
        """---
schema_version: "v0.3.0"
name: phase-token-smoke
io:
  inputs:
    type: object
    properties: {}
  outputs:
    type: object
    properties: {}
phases: [prepare, branch_a, branch_b, assemble]
---
<phase depends_on="input">prepare</phase>
<phase depends_on="prepare">branch_a</phase>
<phase depends_on="prepare">branch_b</phase>
<phase depends_on="branch_a branch_b" output>assemble</phase>
""",
        encoding="utf-8",
    )
    for phase_id in ("prepare", "branch_a", "branch_b", "assemble"):
        (root / "phases" / phase_id / "LOGIC.md").write_text(
            f"""---
io:
  inputs:
    type: object
    properties: {{}}
  outputs:
    type: object
    properties: {{}}
---
<action>{phase_id}</action>
""",
            encoding="utf-8",
        )
        (root / "phases" / phase_id / "actions" / f"{phase_id}.py").write_text(
            f"def {phase_id}(inputs):\n    return {{}}\n",
            encoding="utf-8",
        )


def test_v030_phase_token_info_has_raw_line_and_line_numbers(
    tmp_path: Path, mock_skill_resolver: object
) -> None:
    _write_v030_phase_token_skill(tmp_path)
    graph_text = (tmp_path / "GRAPH.md").read_text(encoding="utf-8")
    graph_body = graph_text.split("---", 2)[2].lstrip("\n")
    compiled = compile_skill(tmp_path, cache=False, skill_resolver=mock_skill_resolver)

    info = get_phase_token_info(compiled, "prepare")

    assert info is not None
    assert info.raw_text == '<phase depends_on="input">prepare</phase>'
    assert graph_body[info.start_offset : info.end_offset] == info.raw_text
    assert info.line_start == info.line_end == 1
    assert info.attrs == {"depends_on": "input"}


def test_v030_phase_tokens_expose_attribute_offsets(
    tmp_path: Path, mock_skill_resolver: object
) -> None:
    _write_v030_phase_token_skill(tmp_path)
    graph_text = (tmp_path / "GRAPH.md").read_text(encoding="utf-8")
    graph_body = graph_text.split("---", 2)[2].lstrip("\n")
    compiled = compile_skill(tmp_path, cache=False, skill_resolver=mock_skill_resolver)

    for phase_id in ("prepare", "branch_a", "branch_b", "assemble"):
        info = get_phase_token_info(compiled, phase_id)
        assert info is not None
        assert graph_body[info.start_offset : info.end_offset] == info.raw_text
        assert {"depends_on"} <= set(info.attr_spans)
        for attr_name, span in info.attr_spans.items():
            assert info.attrs[attr_name] == span.value
            assert graph_body[span.value_start : span.value_end] == span.value
            assert graph_body[span.attr_start : span.attr_end].startswith(attr_name)

    assemble = get_phase_token_info(compiled, "assemble")
    assert assemble is not None
    assert assemble.attr_spans["depends_on"].value == "branch_a branch_b"


def test_missing_phase_token_info_returns_none(tmp_path: Path, mock_skill_resolver: object) -> None:
    _write_v030_phase_token_skill(tmp_path)
    compiled = compile_skill(tmp_path, cache=False, skill_resolver=mock_skill_resolver)

    assert get_phase_token_info(compiled, "missing") is None
