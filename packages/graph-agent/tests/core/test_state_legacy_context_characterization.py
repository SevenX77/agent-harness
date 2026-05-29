"""Characterization tests for legacy_context_from_state."""

from __future__ import annotations

from typing import Any

from graph_agent.core.state import (
    BusinessData,
    FrameworkState,
    WorkflowState,
    legacy_context_from_state,
)


def make_state(
    data: dict[str, Any] | None = None,
    **flow_fields: Any,
) -> WorkflowState:
    return WorkflowState(
        data=BusinessData(**dict(data or {})),
        flow=FrameworkState(**flow_fields),
        messages=[],
    )


def test_legacy_context_contains_business_data_and_unattended_default() -> None:
    ctx = legacy_context_from_state(make_state({"answer": "ok", "score": 2}))

    assert ctx == {
        "answer": "ok",
        "score": 2,
        "_unattended": False,
    }


def test_legacy_context_maps_all_populated_framework_fields() -> None:
    ctx = legacy_context_from_state(
        make_state(
            {"answer": "ok"},
            finish_task_result={"meta": {"_done": True}},
            md_id="md-1",
            io_errors=["missing-input"],
            validation_warnings=["soft-warning"],
            thread_id="thread-1",
            run_id="run-1",
            unattended=True,
            persistent_runtime_inputs={"topic": "contracts"},
            persistent_storage_config={"root": "/tmp/run"},
            sub_run_id="sub-1",
            retry_feedback=["try again"],
            working_memory={"plan": ["step"]},
            ambiguity_reports=[{"question": "which?", "decision": "this"}],
            last_output={"status": "done"},
            group_key="group-1",
            trace_path="/tmp/trace.jsonl",
            validation_middleware_phase="validate",
            current_phase="draft",
            md_schema={"type": "object"},
            md_schema_path="schema.Result",
            md_type_dict={"answer": "str"},
        )
    )

    assert ctx == {
        "answer": "ok",
        "_finish_task_result": {"meta": {"_done": True}},
        "_md_id": "md-1",
        "_io_errors": ["missing-input"],
        "_validation_warnings": ["soft-warning"],
        "_thread_id": "thread-1",
        "_run_id": "run-1",
        "_unattended": True,
        "_persistent_runtime_inputs": {"topic": "contracts"},
        "_persistent_storage_config": {"root": "/tmp/run"},
        "_sub_run_id": "sub-1",
        "_retry_feedback": ["try again"],
        "_working_memory": {"plan": ["step"]},
        "_ambiguity_reports": [{"question": "which?", "decision": "this"}],
        "_last_output": {"status": "done"},
        "_group_key": "group-1",
        "_trace_path": "/tmp/trace.jsonl",
        "_validation_middleware_phase": "validate",
        "_current_phase": "draft",
        "_md_schema": {"type": "object"},
        "_md_schema_path": "schema.Result",
        "_md_type_dict": {"answer": "str"},
    }


def test_legacy_context_omits_empty_collections_except_retry_feedback() -> None:
    ctx = legacy_context_from_state(
        make_state(
            {},
            io_errors=[],
            validation_warnings=[],
            retry_feedback=[],
            working_memory={},
            ambiguity_reports=[],
            current_phase="",
        )
    )

    assert ctx == {
        "_unattended": False,
        "_retry_feedback": [],
    }
    assert "_io_errors" not in ctx
    assert "_validation_warnings" not in ctx
    assert "_working_memory" not in ctx
    assert "_ambiguity_reports" not in ctx
    assert "_current_phase" not in ctx


def test_legacy_context_includes_not_none_falsy_scalar_fields() -> None:
    ctx = legacy_context_from_state(
        make_state(
            {},
            md_id="",
            thread_id="",
            run_id="",
            sub_run_id="",
            last_output=0,
            group_key="",
            trace_path="",
            validation_middleware_phase="",
            md_schema_path="",
            current_phase="",
        )
    )

    assert ctx == {
        "_md_id": "",
        "_thread_id": "",
        "_run_id": "",
        "_unattended": False,
        "_sub_run_id": "",
        "_last_output": 0,
        "_group_key": "",
        "_trace_path": "",
        "_validation_middleware_phase": "",
        "_md_schema_path": "",
    }


def test_legacy_context_copies_list_and_dict_metadata_but_reuses_working_memory() -> None:
    io_errors = ["io"]
    validation_warnings = ["warning"]
    runtime_inputs = {"topic": "contracts"}
    storage_config = {"root": "/tmp/run"}
    retry_feedback = ["retry"]
    ambiguity_reports = [{"question": "q"}]
    md_schema = {"type": "object"}
    md_type_dict = {"field": "str"}
    working_memory = {"steps": ["draft"]}
    state = make_state(
        {},
        io_errors=io_errors,
        validation_warnings=validation_warnings,
        persistent_runtime_inputs=runtime_inputs,
        persistent_storage_config=storage_config,
        retry_feedback=retry_feedback,
        working_memory=working_memory,
        ambiguity_reports=ambiguity_reports,
        md_schema=md_schema,
        md_type_dict=md_type_dict,
    )

    ctx = legacy_context_from_state(state)

    assert ctx["_io_errors"] == io_errors
    assert ctx["_io_errors"] is not state["flow"].io_errors
    assert ctx["_validation_warnings"] == validation_warnings
    assert ctx["_validation_warnings"] is not state["flow"].validation_warnings
    assert ctx["_persistent_runtime_inputs"] == runtime_inputs
    assert ctx["_persistent_runtime_inputs"] is not state["flow"].persistent_runtime_inputs
    assert ctx["_persistent_storage_config"] == storage_config
    assert ctx["_persistent_storage_config"] is not state["flow"].persistent_storage_config
    assert ctx["_retry_feedback"] == retry_feedback
    assert ctx["_retry_feedback"] is not state["flow"].retry_feedback
    assert ctx["_ambiguity_reports"] == ambiguity_reports
    assert ctx["_ambiguity_reports"] is not state["flow"].ambiguity_reports
    assert ctx["_md_schema"] == md_schema
    assert ctx["_md_schema"] is not state["flow"].md_schema
    assert ctx["_md_type_dict"] == md_type_dict
    assert ctx["_md_type_dict"] is not state["flow"].md_type_dict
    assert ctx["_working_memory"] is state["flow"].working_memory


def test_legacy_context_preserves_business_underscore_fields_if_already_present() -> None:
    state = WorkflowState(
        data=BusinessData(_legacy_shadow="business", visible=True),
        flow=FrameworkState(md_id="framework"),
        messages=[],
    )

    ctx = legacy_context_from_state(state)

    assert ctx["_legacy_shadow"] == "business"
    assert ctx["visible"] is True
    assert ctx["_md_id"] == "framework"
