from __future__ import annotations

import pytest

from graph_agent.core.exceptions import GraphAgentFatalError
from graph_agent.runtime.state import shallow_dict_merge


def test_shallow_merge_disjoint_keys() -> None:
    assert shallow_dict_merge({"a": 1}, {"b": 2}) == {"a": 1, "b": 2}


def test_shallow_merge_left_none() -> None:
    assert shallow_dict_merge(None, {"a": 1}) == {"a": 1}


def test_shallow_merge_right_none() -> None:
    assert shallow_dict_merge({"a": 1}, None) == {"a": 1}


def test_shallow_merge_both_none() -> None:
    assert shallow_dict_merge(None, None) == {}


def test_shallow_merge_conflict_raises_fatal() -> None:
    with pytest.raises(GraphAgentFatalError, match=r"\[F-v21-state-conflict\].*key='a'"):
        shallow_dict_merge({"a": 1}, {"a": 2})
