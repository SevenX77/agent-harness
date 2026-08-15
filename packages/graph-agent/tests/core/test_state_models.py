"""Tests for MVP-1 T1: BusinessData / FrameworkState / WorkflowState models."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from graph_agent.core.state import (
    BusinessData,
    FrameworkState,
    StateManager,
    WorkflowState,
    verify_state_invariants,
)


class TestBusinessData:
    def test_business_data_extra_allow(self) -> None:
        """BusinessData 接受动态业务字段."""
        bd = BusinessData(segments=[1, 2, 3], summary="text")
        assert bd.model_dump()["segments"] == [1, 2, 3]
        assert bd.model_dump()["summary"] == "text"

    def test_business_data_serialization_round_trip(self) -> None:
        """model_dump / model_validate round trip."""
        bd1 = BusinessData(field1="value", nested={"k": "v"})
        dumped = bd1.model_dump(mode="json")
        bd2 = BusinessData.model_validate(dumped)
        assert bd1 == bd2


class TestFrameworkState:
    def test_framework_state_extra_forbid(self) -> None:
        """未声明字段被 Pydantic 拒."""
        with pytest.raises(ValidationError):
            FrameworkState(undeclared_field="value")

    def test_framework_state_default_values(self) -> None:
        """所有字段都有合理默认值."""
        fs = FrameworkState()
        assert fs.finish_task_result is None
        assert fs.current_phase == ""
        assert fs.metrics == {}
        assert fs.unattended is False

    def test_framework_state_serialization_round_trip(self) -> None:
        fs1 = FrameworkState(thread_id="t1", run_id="r1", current_phase="p1")
        dumped = fs1.model_dump(mode="json")
        fs2 = FrameworkState.model_validate(dumped)
        assert fs1 == fs2

    def test_framework_state_trace_path_default(self) -> None:
        fs = FrameworkState()
        assert fs.trace_path is None


class TestWorkflowStateTypedDict:
    def test_workflow_state_compatible(self) -> None:
        """WorkflowState 是 TypedDict, 可直接构造."""
        state: WorkflowState = {
            "data": BusinessData(),
            "flow": FrameworkState(),
            "messages": [],
        }
        assert "data" in state
        assert "flow" in state
        assert "messages" in state


class TestStateManager:
    def test_update_business_rejects_underscore(self) -> None:
        state: WorkflowState = {
            "data": BusinessData(),
            "flow": FrameworkState(),
            "messages": [],
        }
        with pytest.raises(ValueError, match="不允许 _ 前缀字段"):
            StateManager.update_business(state, _internal="x")

    def test_update_business_accepts_normal_fields(self) -> None:
        state: WorkflowState = {
            "data": BusinessData(),
            "flow": FrameworkState(),
            "messages": [],
        }
        new_state = StateManager.update_business(state, segments=[1, 2])
        assert new_state["data"].model_dump()["segments"] == [1, 2]

    def test_update_framework_pydantic_forbid(self) -> None:
        state: WorkflowState = {
            "data": BusinessData(),
            "flow": FrameworkState(),
            "messages": [],
        }
        new_state = StateManager.update_framework(state, subagent_depth=5, current_phase="p1")
        assert new_state["flow"].subagent_depth == 5
        assert new_state["flow"].current_phase == "p1"

        with pytest.raises(ValidationError):
            StateManager.update_framework(state, undeclared_xyz="value")

    def test_verify_state_invariants_rejects_business_underscore(self) -> None:
        state: WorkflowState = {
            "data": BusinessData(_internal="x"),
            "flow": FrameworkState(),
            "messages": [],
        }
        with pytest.raises(ValueError, match="BusinessData 含禁止的 _ 前缀字段"):
            verify_state_invariants(state)

    def test_verify_state_invariants_accepts_split_state(self) -> None:
        state: WorkflowState = {
            "data": BusinessData(result="ok"),
            "flow": FrameworkState(thread_id="t1"),
            "messages": [],
        }
        verify_state_invariants(state)
