from __future__ import annotations

from pathlib import Path

from graph_agent.core.compiler import compile_skill
from graph_agent.core.loader import get_phase_token_info

REPO_ROOT = Path(__file__).resolve().parents[4]


def test_hello_world_phase_token_info_has_raw_line_and_line_numbers() -> None:
    skill_root = REPO_ROOT / "skills" / "hello-world"
    compiled = compile_skill(skill_root, cache=False)

    info = get_phase_token_info(compiled, "greet")

    assert info is not None
    assert info.raw_text == '<phase id="greet" src="phases/greet" depends_on="" />'
    assert info.line_start == info.line_end == 10
    assert info.attrs == {"id": "greet", "src": "phases/greet", "depends_on": ""}


def test_fake_canvas_fanout_phase_tokens_expose_attribute_offsets() -> None:
    skill_root = (
        REPO_ROOT / "packages" / "graph-agent" / "tests" / "fixtures" / "fake_canvas_fanout"
    )
    graph_text = (skill_root / "GRAPH.md").read_text(encoding="utf-8")
    compiled = compile_skill(skill_root, cache=False)

    for phase_id in ("prepare", "branch_a", "branch_b", "assemble"):
        info = get_phase_token_info(compiled, phase_id)
        assert info is not None
        assert graph_text[info.start_offset : info.end_offset] == info.raw_text
        assert info.attrs["id"] == phase_id
        assert {"id", "src", "depends_on"} <= set(info.attr_spans)
        for attr_name, span in info.attr_spans.items():
            assert info.attrs[attr_name] == span.value
            assert graph_text[span.value_start : span.value_end] == span.value
            assert graph_text[span.attr_start : span.attr_end].startswith(attr_name)

    assemble = get_phase_token_info(compiled, "assemble")
    assert assemble is not None
    assert assemble.attr_spans["depends_on"].value == "branch_a branch_b"


def test_missing_phase_token_info_returns_none() -> None:
    compiled = compile_skill(REPO_ROOT / "skills" / "hello-world", cache=False)

    assert get_phase_token_info(compiled, "missing") is None
