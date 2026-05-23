from __future__ import annotations

import pytest
from graph_agent.core.exceptions import GraphAgentFatalError
from graph_agent.runtime.state import smart_dict_reducer


def test_smart_reducer_disjoint_keys() -> None:
    assert smart_dict_reducer({"a": 1}, {"b": 2}) == {"a": 1, "b": 2}


def test_smart_reducer_left_none() -> None:
    assert smart_dict_reducer(None, {"a": 1}) == {"a": 1}


def test_smart_reducer_right_none() -> None:
    assert smart_dict_reducer({"a": 1}, None) == {"a": 1}


def test_smart_reducer_both_none() -> None:
    assert smart_dict_reducer(None, None) == {}


def test_smart_reducer_allows_sequential_overwrite() -> None:
    assert smart_dict_reducer({"a": 1}, {"a": 2}) == {"a": 2}


def test_smart_reducer_parallel_conflict_raises_fatal() -> None:
    with pytest.raises(GraphAgentFatalError, match=r"\[F-v3-runtime-state-mapping-failed\]"):
        smart_dict_reducer(
            {"a": 1},
            {"a": 2},
            merge_context={"parallel": True, "source_phase_id": "branch_a"},
        )
