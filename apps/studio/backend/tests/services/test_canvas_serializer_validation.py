from app.core.adapters.engine import (
    GraphPhaseRef,
    GraphTopologySerializationError,
    serialize_graph_topology_from_markdown,
)

_GRAPH_MD = """---
schema_version: "v0.3.0"
name: serializer-validation
io:
  inputs:
    type: object
    properties: {}
  outputs:
    type: object
    properties: {}
phases:
  - init
---
<phase depends_on="input" output>init</phase>
"""


def test_canvas_serializer_allows_disconnected_phase_nodes() -> None:
    markdown = serialize_graph_topology_from_markdown(
        skill_id="serializer-validation",
        original_md=_GRAPH_MD,
        phases=[
            GraphPhaseRef(id="init", src="phases/init/LOGIC.md", depends_on=[]),
            GraphPhaseRef(id="agent", src="phases/agent/SKILL.md", depends_on=[]),
        ],
    )

    assert '<phase depends_on="input" output>init</phase>' in markdown
    assert '<phase depends_on="input" output>agent</phase>' in markdown


def test_canvas_serializer_still_rejects_unknown_dependencies() -> None:
    try:
        serialize_graph_topology_from_markdown(
            skill_id="serializer-validation",
            original_md=_GRAPH_MD,
            phases=[GraphPhaseRef(id="agent", src="phases/agent/SKILL.md", depends_on=["missing"])],
        )
    except GraphTopologySerializationError as exc:
        assert exc.code == "serializer_orphan"
    else:
        raise AssertionError("expected unknown dependency to be rejected")
