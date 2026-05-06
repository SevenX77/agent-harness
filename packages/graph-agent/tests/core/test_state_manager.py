"""Tests for MVP-1 T4 StateManager routing helpers."""

from __future__ import annotations

from typing import Any

from graph_agent.core.state import BusinessData, FrameworkState, StateManager, WorkflowState


def _state(
    *,
    data: dict[str, Any] | None = None,
    flow: dict[str, Any] | None = None,
) -> WorkflowState:
    return {
        "data": BusinessData(**dict(data or {})),
        "flow": FrameworkState(**dict(flow or {})),
        "messages": [],
    }


def test_route_finish_task_business_only() -> None:
    state = _state(data={"chapter": 1})

    next_state = StateManager.route_finish_task(state, {"segments": [1, 2]})

    assert next_state["data"].model_dump() == {"chapter": 1, "segments": [1, 2]}
    assert next_state["flow"].finish_task_result == {
        "meta": {},
        "raw": {"segments": [1, 2]},
    }


def test_route_finish_task_with_underscore_meta() -> None:
    state = _state()

    next_state = StateManager.route_finish_task(
        state,
        {"segments": [1], "_md_id": "block-1"},
    )

    assert next_state["data"].model_dump() == {"segments": [1]}
    assert next_state["flow"].finish_task_result == {
        "meta": {"_md_id": "block-1"},
        "raw": {"segments": [1], "_md_id": "block-1"},
    }


def test_route_finish_task_empty_output() -> None:
    state = _state(data={"existing": "ok"})

    next_state = StateManager.route_finish_task(state, {})

    assert next_state["data"].model_dump() == {"existing": "ok"}
    assert next_state["flow"].finish_task_result == {"meta": {}, "raw": {}}


def test_update_business_immutable_returns_new_state() -> None:
    state = _state(data={"a": 1})

    next_state = StateManager.update_business(state, b=2)

    assert next_state is not state
    assert next_state["data"] is not state["data"]
    assert state["data"].model_dump() == {"a": 1}
    assert next_state["data"].model_dump() == {"a": 1, "b": 2}
    assert next_state["flow"] is state["flow"]
    assert next_state["messages"] is state["messages"]


def test_update_framework_partial_update_preserves_others() -> None:
    state = _state(
        flow={
            "thread_id": "thread-1",
            "metrics": {"tokens": 10},
            "retry_counts": {"phase": 1},
        }
    )

    next_state = StateManager.update_framework(state, current_phase="phase-a")

    assert next_state is not state
    assert next_state["flow"] is not state["flow"]
    assert next_state["flow"].current_phase == "phase-a"
    assert next_state["flow"].thread_id == "thread-1"
    assert next_state["flow"].metrics == {"tokens": 10}
    assert next_state["flow"].retry_counts == {"phase": 1}
    assert next_state["data"] is state["data"]
