from __future__ import annotations

from graph_agent.core.graph_serializer import serialize_graph_topology
from graph_agent.core.manifest import GraphPhaseRef, PhaseIOSchema

_IO = PhaseIOSchema(
    inputs={"type": "object", "properties": {}},
    outputs={"type": "object", "properties": {}},
)


def _ref(phase_id: str, depends_on: list[str]) -> GraphPhaseRef:
    return GraphPhaseRef(id=phase_id, src=f"phases/{phase_id}", depends_on=depends_on)


def test_linear_chain_emits_real_depends_on_and_single_output() -> None:
    md = serialize_graph_topology(
        name="linear",
        description=None,
        io=_IO,
        phases=[_ref("a", ["input"]), _ref("b", ["a"]), _ref("c", ["b"])],
    )
    assert '<phase depends_on="input">a</phase>' in md
    assert '<phase depends_on="a">b</phase>' in md
    # c is the only leaf -> the only output.
    assert '<phase depends_on="b" output>c</phase>' in md
    assert md.count(" output>") == 1


def test_diamond_fan_in_preserves_multiple_depends_on() -> None:
    # The regression the old linear stub corrupted: d depends on BOTH b and c.
    md = serialize_graph_topology(
        name="diamond",
        description=None,
        io=_IO,
        phases=[_ref("a", ["input"]), _ref("b", ["a"]), _ref("c", ["a"]), _ref("d", ["b", "c"])],
    )
    assert '<phase depends_on="b, c" output>d</phase>' in md
    # b and c are NOT linearised into a chain; both depend only on a.
    assert '<phase depends_on="a">b</phase>' in md
    assert '<phase depends_on="a">c</phase>' in md
    # Only the single leaf d is the output.
    assert md.count(" output>") == 1
    assert "output>d</phase>" in md


def test_multiple_leaves_each_marked_output() -> None:
    md = serialize_graph_topology(
        name="multi-out",
        description=None,
        io=_IO,
        phases=[_ref("a", ["input"]), _ref("b", ["a"]), _ref("c", ["a"])],
    )
    # Both b and c are leaves -> both output (loader allows multiple outputs).
    assert '<phase depends_on="a" output>b</phase>' in md
    assert '<phase depends_on="a" output>c</phase>' in md
    assert md.count(" output>") == 2


def test_disconnected_phase_renders_input_sentinel_and_is_output() -> None:
    # A freshly-added phase has depends_on=[]; it must render as an input-rooted
    # leaf (depends_on="input" + output) so it lands in GRAPH.md instead of orphaning.
    md = serialize_graph_topology(
        name="with-new",
        description=None,
        io=_IO,
        phases=[_ref("step1", ["input"]), _ref("logic", [])],
    )
    assert "  - logic" in md  # appears in the phases: frontmatter list
    assert '<phase depends_on="input" output>logic</phase>' in md


def test_description_is_emitted_when_present() -> None:
    md = serialize_graph_topology(
        name="n",
        description="hello world",
        io=_IO,
        phases=[_ref("only", [])],
    )
    assert "description: hello world" in md
