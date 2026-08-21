from __future__ import annotations

from pathlib import Path

import pytest

from graph_agent.core.exceptions import GraphAgentFatalError
from graph_agent.core.state import (
    BusinessData,
    FrameworkState,
    WorkflowState,
    merge_business_channel,
)
from graph_agent.runtime.state_mapper import (
    PhaseWrapper,
    ReaderSandboxState,
    StateMapper,
    filter_runtime_inputs,
)


def _project_and_require(mapper: StateMapper, state: WorkflowState) -> WorkflowState:
    """The two halves ``PhaseWrapper`` runs back to back on entering a phase.

    They are separate methods because only the second one may reject: reporting
    what a phase was handed calls the projection alone (ledger E18). These cases
    are about the input contract's semantics — which fields count as required at
    which nesting level — so they exercise the pair.
    """
    phase_input = mapper.select_declared_inputs(state)
    mapper.require_declared_inputs(phase_input)
    return phase_input


def test_filter_runtime_inputs_uses_declared_schema_properties() -> None:
    schema = {
        "type": "object",
        "properties": {"topic": {"type": "string"}},
        "required": ["topic"],
    }

    assert filter_runtime_inputs({"topic": "A", "extra": True}, schema) == {"topic": "A"}


def test_a_missing_required_input_field_is_a_mapping_failure() -> None:
    """MVP1 contract (compile-rules §2.3 / graph-exec §3): slicing must fail fast
    when a declared-required input field is absent from the blackboard, instead
    of silently dropping it and letting the phase run on partial input."""
    mapper = StateMapper(
        input_schema={
            "type": "object",
            "required": ["topic", "chapter"],
            "properties": {"topic": {"type": "string"}, "chapter": {"type": "object"}},
        },
        phase_id="analyze",
    )
    state = WorkflowState(
        data=BusinessData.model_validate({"topic": "A"}),
        flow=FrameworkState(),
        messages=[],
    )

    with pytest.raises(GraphAgentFatalError) as exc_info:
        _project_and_require(mapper, state)

    assert exc_info.value.payload.code == "[F-v3-runtime-state-mapping-failed]"
    assert exc_info.value.payload.phase_id == "analyze"
    assert "chapter" in str(exc_info.value)


def test_a_present_required_input_field_passes() -> None:
    mapper = StateMapper(
        input_schema={
            "type": "object",
            "required": ["topic"],
            "properties": {"topic": {"type": "string"}},
        },
        phase_id="analyze",
    )
    state = WorkflowState(
        data=BusinessData.model_validate({"topic": "A", "extra": True}),
        flow=FrameworkState(),
        messages=[],
    )

    phase_input = _project_and_require(mapper, state)

    assert phase_input["data"].model_dump() == {"topic": "A"}


def test_a_missing_nested_required_input_field_is_a_mapping_failure() -> None:
    """MVP1 contract (compile-rules §2.3 slice row): ``required`` is enforced at
    EVERY object nesting level, not only the top. A declared-required sub-field
    of a present object (``chapter.aa_number``) missing from the blackboard is
    the same mapping failure as a missing top-level field — dotted field_path so
    the studio config tree can point at the exact broken sub-field."""
    mapper = StateMapper(
        input_schema={
            "type": "object",
            "required": ["chapter"],
            "properties": {
                "chapter": {
                    "type": "object",
                    "required": ["aa_number"],
                    "properties": {"aa_number": {"type": "integer"}},
                },
            },
        },
        phase_id="analyze",
    )
    state = WorkflowState(
        data=BusinessData.model_validate({"chapter": {"title": "x"}}),
        flow=FrameworkState(),
        messages=[],
    )

    with pytest.raises(GraphAgentFatalError) as exc_info:
        _project_and_require(mapper, state)

    assert exc_info.value.payload.code == "[F-v3-runtime-state-mapping-failed]"
    assert exc_info.value.payload.field_path == "chapter.aa_number"
    assert "chapter.aa_number" in str(exc_info.value)


def test_a_present_nested_required_input_field_passes() -> None:
    mapper = StateMapper(
        input_schema={
            "type": "object",
            "required": ["chapter"],
            "properties": {
                "chapter": {
                    "type": "object",
                    "required": ["aa_number"],
                    "properties": {"aa_number": {"type": "integer"}},
                },
            },
        },
        phase_id="analyze",
    )
    state = WorkflowState(
        data=BusinessData.model_validate({"chapter": {"aa_number": 3, "title": "x"}}),
        flow=FrameworkState(),
        messages=[],
    )

    phase_input = _project_and_require(mapper, state)

    assert phase_input["data"].model_dump() == {"chapter": {"aa_number": 3, "title": "x"}}


def test_an_absent_optional_object_skips_its_nested_required() -> None:
    """Nested required only bites when the parent object is present (standard
    JSON-Schema semantics): an ABSENT optional object must not raise on its
    unmet sub-required — only the missing parent (if the parent itself is
    required) would."""
    mapper = StateMapper(
        input_schema={
            "type": "object",
            "required": ["topic"],
            "properties": {
                "topic": {"type": "string"},
                "chapter": {
                    "type": "object",
                    "required": ["aa_number"],
                    "properties": {"aa_number": {"type": "integer"}},
                },
            },
        },
        phase_id="analyze",
    )
    state = WorkflowState(
        data=BusinessData.model_validate({"topic": "A"}),
        flow=FrameworkState(),
        messages=[],
    )

    phase_input = _project_and_require(mapper, state)

    assert phase_input["data"].model_dump() == {"topic": "A"}


def test_ensure_no_input_write_stub_is_deleted() -> None:
    """The no-op ensure_no_input_write stub (documented code debt) must be gone,
    not silently exported as if it protected anything."""
    import graph_agent.runtime.state_mapper as state_mapper_module

    assert not hasattr(state_mapper_module, "ensure_no_input_write")
    assert "ensure_no_input_write" not in state_mapper_module.__all__


def test_state_mapper_rejects_undeclared_output_keys() -> None:
    mapper = StateMapper(output_schema={"type": "object", "properties": {"answer": {}}})
    state = WorkflowState(data=BusinessData(), flow=FrameworkState(), messages=[])

    with pytest.raises(GraphAgentFatalError) as exc_info:
        mapper.wrap_phase_output(state, {"data": {"answer": "ok", "extra": True}})
    assert exc_info.value.payload.code == "[F-v3-runtime-state-mapping-failed]"


def test_phase_wrapper_maps_input_and_output() -> None:
    mapper = StateMapper(
        input_schema={"type": "object", "properties": {"topic": {}}},
        output_schema={"type": "object", "properties": {"answer": {}}},
    )
    seen: dict[str, object] = {}

    def node(state):
        seen.update(state["data"]["inputs"])
        return {"data": {"answer": state["data"]["inputs"]["topic"]}}

    wrapped = PhaseWrapper(mapper).wrap(node)

    state = WorkflowState(
        data=BusinessData.model_validate({"topic": "A", "extra": True}),
        flow=FrameworkState(),
        messages=[],
    )
    res = wrapped(state)

    # The wrapper returns a channel delta (parallel-fanout decision 2026-08-15);
    # folding it through the data reducer yields the merged state, with the
    # phase's outputs recorded in the reserved phase_outputs map (D7 per-node
    # golden); phase_id defaults to "unknown" for this bare mapper.
    assert res["data"] == {
        "answer": "A",
        "phase_outputs": {"unknown": {"answer": "A"}},
    }
    merged = merge_business_channel(state["data"], res["data"])
    assert merged.model_dump() == {
        "topic": "A",
        "extra": True,
        "answer": "A",
        "phase_outputs": {"unknown": {"answer": "A"}},
    }
    assert seen == {"topic": "A"}


def test_wrap_phase_output_accumulates_real_phase_outputs_map_per_node() -> None:
    """D7: simple linear phases must produce a REAL phase_outputs map (node_id ->
    that node's outputs) in model_dump() — not only via the synthetic __getitem__
    compat layer — so headless per-node golden does not degrade to run-level."""
    step1 = StateMapper(output_schema={"type": "object", "properties": {"a": {}}}, phase_id="step1")
    step2 = StateMapper(output_schema={"type": "object", "properties": {"b": {}}}, phase_id="step2")

    state = WorkflowState(data=BusinessData(), flow=FrameworkState(), messages=[])
    delta1 = step1.wrap_phase_output(state, {"data": {"a": 1}})
    folded1 = WorkflowState(
        data=merge_business_channel(state["data"], delta1["data"]),
        flow=state["flow"],
        messages=[],
    )
    delta2 = step2.wrap_phase_output(folded1, {"data": {"b": 2}})
    folded2 = merge_business_channel(folded1["data"], delta2["data"])

    real_map = folded2.model_dump()["phase_outputs"]
    assert real_map == {"step1": {"a": 1}, "step2": {"b": 2}}


def test_wrap_phase_output_does_not_leak_child_phase_outputs_across_subgraph_io() -> None:
    """A child graph's internal phase_outputs must not cross a subgraph IO boundary:
    a node returning {declared_output, phase_outputs:{...}} keeps only its declared
    output, and the parent records phase_outputs[phase_id] = the declared output."""
    delegate = StateMapper(
        output_schema={"type": "object", "properties": {"child_answer": {}}},
        phase_id="delegate",
    )
    state = WorkflowState(data=BusinessData(), flow=FrameworkState(), messages=[])

    # Simulate a subgraph result carrying the child's internal phase_outputs.
    result = {
        "data": {
            "child_answer": "ok",
            "phase_outputs": {"child_prep": {"scratch_only": 1}, "child_final": {"child_answer": "ok"}},
        }
    }
    delta = delegate.wrap_phase_output(state, result)

    dumped = merge_business_channel(state["data"], delta["data"]).model_dump()
    # The child's intermediate field never leaked into the parent business namespace.
    assert "scratch_only" not in dumped
    assert dumped["child_answer"] == "ok"
    assert dumped["phase_outputs"] == {"delegate": {"child_answer": "ok"}}


def test_reader_sandbox_state_does_not_inherit_parent_blackboard(tmp_path: Path) -> None:
    sandbox = ReaderSandboxState(skill_id="demo.skill", phase_id="main", root=tmp_path)

    state = sandbox.to_blackboard()

    assert state["data"].model_dump() == {
        "skill_id": "demo.skill",
        "phase_id": "main",
        "references": [],
        "max_output_tokens": 3000,
        "language": "zh",
        "timeout_s": 60,
    }
    assert state["messages"] == []
    assert state["flow"].timeout_s == 60
    assert getattr(state["flow"], "run_id", None) is None


def test_the_projection_alone_never_rejects_a_missing_required_field() -> None:
    """The half that reports must not be the half that judges.

    ``_emit_input_dispatch`` calls the projection to say what a phase was
    handed. While the two were one method, that call raised on a missing
    required input — killing the run from the reporting path, before the phase's
    execution had been announced, so no event ever named the phase (E18).
    """
    mapper = StateMapper(
        input_schema={
            "type": "object",
            "required": ["chapter"],
            "properties": {"chapter": {"type": "string"}},
        },
        phase_id="analyze",
    )
    state = WorkflowState(
        data=BusinessData.model_validate({"topic": "A"}),
        flow=FrameworkState(),
        messages=[],
    )

    projected = mapper.select_declared_inputs(state)

    assert projected["data"].model_dump() == {}, (
        "the projection keeps only declared inputs that are actually there"
    )
    with pytest.raises(GraphAgentFatalError):
        mapper.require_declared_inputs(projected)
