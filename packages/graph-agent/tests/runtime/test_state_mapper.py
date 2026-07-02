from __future__ import annotations

from pathlib import Path

import pytest

from graph_agent.core.exceptions import GraphAgentFatalError
from graph_agent.core.state import BusinessData, FrameworkState, WorkflowState
from graph_agent.runtime.state_mapper import (
    PhaseWrapper,
    ReaderSandboxState,
    StateMapper,
    filter_runtime_inputs,
)


def test_filter_runtime_inputs_uses_declared_schema_properties() -> None:
    schema = {
        "type": "object",
        "properties": {"topic": {"type": "string"}},
        "required": ["topic"],
    }

    assert filter_runtime_inputs({"topic": "A", "extra": True}, schema) == {"topic": "A"}


def test_build_phase_input_missing_required_field_raises_state_mapping_fatal() -> None:
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
        mapper.build_phase_input(state)

    assert exc_info.value.payload.code == "[F-v3-runtime-state-mapping-failed]"
    assert exc_info.value.payload.phase_id == "analyze"
    assert "chapter" in str(exc_info.value)


def test_build_phase_input_passes_when_required_fields_present() -> None:
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

    phase_input = mapper.build_phase_input(state)

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

    # The phase now also records its outputs into the reserved phase_outputs map
    # (D7 per-node golden); phase_id defaults to "unknown" for this bare mapper.
    assert res["data"].model_dump() == {
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
    after1 = step1.wrap_phase_output(state, {"data": {"a": 1}})
    after2 = step2.wrap_phase_output(after1, {"data": {"b": 2}})

    real_map = after2["data"].model_dump()["phase_outputs"]
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
    after = delegate.wrap_phase_output(state, result)

    dumped = after["data"].model_dump()
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
