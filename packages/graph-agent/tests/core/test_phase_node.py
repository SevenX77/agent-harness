"""Tests for PhaseNode skeleton."""

from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest
from graph_agent.core.phase_node import PhaseNode
from graph_agent.core.state import BusinessData, FrameworkState, StateManager, WorkflowState


def _state() -> WorkflowState:
    return WorkflowState(data=BusinessData(), flow=FrameworkState(), messages=[])


def test_phase_node_execute_returns_updated_state() -> None:
    def execute(state: WorkflowState) -> WorkflowState:
        return StateManager.update_business(state, result="ok")

    node = PhaseNode(name="draft", execute_fn=execute)

    result = node.execute(_state())

    assert result["data"]["result"] == "ok"


def test_phase_node_is_frozen() -> None:
    node = PhaseNode(name="draft", execute_fn=lambda state: state)

    with pytest.raises(FrozenInstanceError):
        node.name = "other"  # type: ignore[misc]


def test_phase_node_keeps_metadata() -> None:
    node = PhaseNode(name="draft", execute_fn=lambda state: state, metadata={"mode": "llm"})

    assert node.metadata == {"mode": "llm"}
