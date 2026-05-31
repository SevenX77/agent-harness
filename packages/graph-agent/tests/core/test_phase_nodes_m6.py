"""Focused M6 coverage for the polymorphic phase node layer."""

from __future__ import annotations

import logging
from typing import cast

from langchain_core.messages import HumanMessage

from graph_agent.callbacks.base import Callback
from graph_agent.core.phase_executor import PhaseExecutor
from graph_agent.core.phase_nodes import (
    CodePhaseNode,
    DependencyContainer,
    HeartbeatProtocol,
    build_llm_phase_node,
)
from graph_agent.core.phase_nodes._helpers import (
    _AMBIGUITY_REPORTS_KEY,
    _RETRY_FEEDBACK_KEY,
    _VALIDATION_WARNINGS_KEY,
    _WORKING_MEMORY_KEY,
    _append_tool_warning,
    _as_text,
    _normalize_string_list,
    _sync_tool_state,
    _tool_reports,
)
from graph_agent.core.state import BusinessData, FrameworkState, WorkflowState
from graph_agent.core.types import Phase


def _state() -> WorkflowState:
    return {"data": BusinessData(), "flow": FrameworkState(), "messages": []}


def test_phase_executor_exposes_per_run_collaborators() -> None:
    class _Heartbeat:
        current_phase: str | None = None

    heartbeat = cast(HeartbeatProtocol, _Heartbeat())
    callbacks: list[Callback] = []

    executor = PhaseExecutor(callbacks, heartbeat=heartbeat)

    assert executor.callbacks is callbacks
    assert executor.heartbeat is heartbeat
    assert executor.run_context is None


def test_build_llm_phase_node_routes_non_llm_phase_to_code_node() -> None:
    deps = DependencyContainer(callbacks=[])
    phase = Phase(name="setup", requires_llm=False)

    node = build_llm_phase_node(phase, deps)

    assert isinstance(node, CodePhaseNode)


def test_helper_normalizers_handle_scalar_list_and_empty_values() -> None:
    assert _as_text(None) is None
    assert _as_text(42) == "42"
    assert _normalize_string_list(None) == []
    assert _normalize_string_list("") == []
    assert _normalize_string_list("one") == ["one"]
    assert _normalize_string_list(["a", "", 3]) == ["a", "3"]
    assert _normalize_string_list(7) == ["7"]


def test_tool_reports_filters_non_list_and_non_dict_values() -> None:
    assert _tool_reports({_AMBIGUITY_REPORTS_KEY: "bad"}) == []
    assert _tool_reports({_AMBIGUITY_REPORTS_KEY: [{"phase": "p"}, "bad", {"x": 1}]}) == [
        {"phase": "p"},
        {"x": 1},
    ]


def test_append_tool_warning_preserves_existing_shapes() -> None:
    tool_state: dict[str, object] = {}
    _append_tool_warning(tool_state, "first")
    _append_tool_warning(tool_state, "second")
    assert tool_state[_VALIDATION_WARNINGS_KEY] == ["first", "second"]

    scalar_state: dict[str, object] = {_VALIDATION_WARNINGS_KEY: "old"}
    _append_tool_warning(scalar_state, "new")
    assert scalar_state[_VALIDATION_WARNINGS_KEY] == ["old", "new"]


def test_sync_tool_state_routes_business_and_framework_fields() -> None:
    tool_state: dict[str, object] = {
        "result": "ok",
        _VALIDATION_WARNINGS_KEY: "warn",
        _RETRY_FEEDBACK_KEY: ["retry"],
        _WORKING_MEMORY_KEY: "memory",
        _AMBIGUITY_REPORTS_KEY: [{"phase": "draft"}, "ignored"],
    }
    messages = [HumanMessage(content="hello")]

    synced = _sync_tool_state(_state(), tool_state, messages=messages)

    assert synced["data"]["result"] == "ok"
    assert synced["flow"].validation_warnings == ["warn"]
    assert synced["flow"].retry_feedback == ["retry"]
    assert synced["flow"].working_memory == "memory"
    assert synced["flow"].ambiguity_reports == [{"phase": "draft"}]
    assert synced["messages"] == messages


def test_validation_middleware_phase_bypass_clears_flag() -> None:
    state = _state()
    state["flow"].validation_middleware_phase = "review"
    phase = Phase(name="review")

    out = PhaseExecutor([]).execute_validation_phase(phase, state)

    assert out["flow"].validation_middleware_phase is None


def test_validation_node_coerces_legacy_str_errors(caplog) -> None:
    def validator(_data: BusinessData) -> tuple[bool, list[str]]:
        return False, cast(list[str], "legacy-error")

    phase = Phase(name="review", validator=validator)

    with caplog.at_level(logging.WARNING):
        out = PhaseExecutor([]).execute_validation_phase(phase, _state())

    assert out["flow"].retry_feedback == ["legacy-error"]
    assert "validator returned str instead of list[str]" in caplog.text


def test_validation_node_coerces_non_list_errors(caplog) -> None:
    def validator(_data: BusinessData) -> tuple[bool, list[str]]:
        return False, cast(list[str], 404)

    phase = Phase(name="review", validator=validator)

    with caplog.at_level(logging.WARNING):
        out = PhaseExecutor([]).execute_validation_phase(phase, _state())

    assert out["flow"].retry_feedback == ["404"]
    assert "validator returned int instead of list[str]" in caplog.text
