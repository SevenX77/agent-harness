from __future__ import annotations

import pytest
from graph_agent.core.exceptions import GraphAgentFatalError
from graph_agent.runtime.state import blackboard_data_merge


def test_blackboard_data_merge_phase_outputs_disjoint_keys() -> None:
    assert blackboard_data_merge(
        {"inputs": {}, "phase_outputs": {"a": {"value": 1}}, "scratch": {}},
        {"inputs": {}, "phase_outputs": {"b": {"value": 2}}, "scratch": {}},
    ) == {
        "inputs": {},
        "phase_outputs": {"a": {"value": 1}, "b": {"value": 2}},
        "scratch": {},
    }


def test_blackboard_data_merge_left_none() -> None:
    assert blackboard_data_merge(None, {"inputs": {"a": 1}}) == {
        "inputs": {"a": 1},
        "phase_outputs": {},
        "scratch": {},
    }


def test_blackboard_data_merge_right_none() -> None:
    assert blackboard_data_merge({"inputs": {"a": 1}}, None) == {
        "inputs": {"a": 1},
        "phase_outputs": {},
        "scratch": {},
    }


def test_blackboard_data_merge_both_none() -> None:
    assert blackboard_data_merge(None, None) == {}


def test_blackboard_data_merge_phase_output_conflict_raises_fatal() -> None:
    with pytest.raises(GraphAgentFatalError, match=r"\[F-v3-state-conflict\].*phase_outputs"):
        blackboard_data_merge(
            {"inputs": {}, "phase_outputs": {"a": {"value": 1}}, "scratch": {}},
            {"inputs": {}, "phase_outputs": {"a": {"value": 2}}, "scratch": {}},
        )
