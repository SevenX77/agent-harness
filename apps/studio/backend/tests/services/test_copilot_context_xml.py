"""F4 4-layer context resolver: the injected view context renders as structured
XML (skill basics / selection / lint / mentions / implicit), not a flat JSON dump,
and is XML-safe."""

from __future__ import annotations

from app.services import copilot


def test_renders_skill_basics_and_view() -> None:
    xml = copilot.render_copilot_context_xml("demo-skill", "Edit", {})
    assert xml.startswith("<copilot_context>")
    assert xml.endswith("</copilot_context>")
    assert '<skill>{"id": "demo-skill", "view": "Edit"}</skill>' in xml


def test_renders_selection_node_and_edge_layer() -> None:
    context = {
        "selected_node": {"id": "step1", "label": "Step One"},
        "selected_edge": {"source": "input", "target": "step1"},
    }
    xml = copilot.render_copilot_context_xml("s", "Edit", context)
    assert "<selection>" in xml
    assert "<node>" in xml and "step1" in xml
    assert "<edge>" in xml and "input" in xml


def test_lint_status_layer_only_when_not_idle() -> None:
    idle = copilot.render_copilot_context_xml("s", "Edit", {"lint_status": "idle"})
    assert "<lint_status>" not in idle
    failing = copilot.render_copilot_context_xml("s", "Edit", {"lint_status": "error"})
    assert "<lint_status>error</lint_status>" in failing


def test_mentions_and_implicit_layers() -> None:
    context = {
        "mentions": [{"kind": "file", "path": "GRAPH.md"}],
        "active_file": "phases/p1/LOGIC.md",
    }
    xml = copilot.render_copilot_context_xml("s", "Predict", context)
    assert "<mentions>" in xml and "GRAPH.md" in xml
    # Unhandled keys fall under <implicit>, not lost.
    assert "<implicit>" in xml and "active_file" in xml


def test_xml_escapes_angle_brackets_and_amps() -> None:
    # A value containing XML metacharacters must not break the structure.
    xml = copilot.render_copilot_context_xml("s", "Edit", {"lint_status": "a < b & c > d"})
    assert "a &lt; b &amp; c &gt; d" in xml
    assert "a < b & c > d" not in xml


def test_omits_empty_layers() -> None:
    xml = copilot.render_copilot_context_xml("s", "Edit", {"selected_node": None, "lint_status": "idle"})
    assert "<selection>" not in xml
    assert "<lint_status>" not in xml
    assert "<mentions>" not in xml
    # Only the skill-basics layer remains.
    assert xml.count("<skill>") == 1


def test_turn_prompt_uses_xml_not_json_dump() -> None:
    import asyncio

    asyncio.run(copilot.set_view_context("xml-skill", "Edit", {"lint_status": "error"}, 1))
    prompt = copilot._prompt_with_turn_context("xml-skill", "hi")
    assert "<copilot_context>" in prompt
    assert "<lint_status>error</lint_status>" in prompt
