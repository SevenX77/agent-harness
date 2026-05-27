"""Tests for the action-facing Context dictionary facade."""

from __future__ import annotations

from graph_agent.cognitive.context_facade import Context


def test_context_supports_minimal_dict_access() -> None:
    blackboard = {"existing": 1}
    context = Context(blackboard, phase_id="p", run_id="r")

    context["new_key"] = 123
    context.setdefault("items", []).append("x")

    assert blackboard["new_key"] == 123
    assert context["existing"] == 1
    assert "existing" in context
    assert "missing" not in context
    assert blackboard["items"] == ["x"]


def test_context_missing_item_raises_key_error() -> None:
    context = Context({}, phase_id="p", run_id="r")

    try:
        context["missing"]
    except KeyError as exc:
        assert exc.args == ("missing",)
    else:
        raise AssertionError("context['missing'] should raise KeyError")
