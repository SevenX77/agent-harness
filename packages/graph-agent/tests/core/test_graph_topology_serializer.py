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
    assert '<phase depends_on="b">c</phase>' in md
    assert " output>" not in md


def test_diamond_fan_in_preserves_multiple_depends_on() -> None:
    # The regression the old linear stub corrupted: d depends on BOTH b and c.
    md = serialize_graph_topology(
        name="diamond",
        description=None,
        io=_IO,
        phases=[_ref("a", ["input"]), _ref("b", ["a"]), _ref("c", ["a"]), _ref("d", ["b", "c"])],
    )
    assert '<phase depends_on="b, c">d</phase>' in md
    # b and c are NOT linearised into a chain; both depend only on a.
    assert '<phase depends_on="a">b</phase>' in md
    assert '<phase depends_on="a">c</phase>' in md
    assert " output>" not in md


def test_multiple_leaves_each_marked_output() -> None:
    md = serialize_graph_topology(
        name="multi-out",
        description=None,
        io=_IO,
        phases=[_ref("a", ["input"]), _ref("b", ["a"]), _ref("c", ["a"])],
    )
    assert '<phase depends_on="a">b</phase>' in md
    assert '<phase depends_on="a">c</phase>' in md
    assert " output>" not in md


def test_disconnected_phase_renders_bare_phase_tag() -> None:
    # A freshly-added phase has depends_on=[]; it must land in GRAPH.md as a
    # plain canvas node, without inventing depends_on="input" or output.
    md = serialize_graph_topology(
        name="with-new",
        description=None,
        io=_IO,
        phases=[_ref("step1", ["input"]), _ref("logic", [])],
    )
    assert "  - logic" in md  # appears in the phases: frontmatter list
    assert '<phase>logic</phase>' in md


def test_description_is_emitted_when_present() -> None:
    md = serialize_graph_topology(
        name="n",
        description="hello world",
        io=_IO,
        phases=[_ref("only", [])],
    )
    assert "description: hello world" in md
