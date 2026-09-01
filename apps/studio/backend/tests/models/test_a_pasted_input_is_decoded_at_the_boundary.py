"""``RunRequest`` folds ``paste_json`` into ``input_data``, on every construction path.

Asserted by CONSTRUCTING the model, not by driving a route, and that is the whole
point of this file. The route-level tests reach the run gate and stop there —
``RUN_REQUIRES_PREDICT`` answers before anything consumes the inputs — so they
can only show that a bad paste is refused, never that a good one arrived. A fold
that silently produced ``{}`` would pass every one of them.

The distinction that makes this necessary: pydantic's ``mode="after"`` model
validator is specified to return the current instance, so returning a NEW one
from ``model_copy`` is outside the contract. It happens to work through
``model_validate`` and is not something to rely on for ``RunRequest(...)``, which
is how the worker and the tests build one. The fold therefore happens in
``mode="before"``, on the raw mapping, where rewriting the input IS the contract.
"""

from __future__ import annotations

import json

import pytest
from app.models.runs import RunRequest
from pydantic import ValidationError


def test_a_pasted_object_becomes_the_input_data() -> None:
    request = RunRequest(paste_json='{"a": 1}')

    assert request.input_data == {"a": 1}
    assert request.paste_json is None


def test_a_pasted_empty_object_overrides_with_an_empty_object() -> None:
    """``"{}"`` is a paste that says "run with no inputs", not "no paste".

    It has to survive as ``{}`` rather than collapsing to ``None``, because the
    two mean different things to the run: an explicit empty payload versus a
    field nobody filled in.
    """
    request = RunRequest(input_data={"stale": True}, paste_json="{}")

    assert request.input_data == {}
    assert request.paste_json is None


def test_a_pasted_object_wins_over_input_data() -> None:
    """Both fields given: the paste is what the person just typed, so it wins."""
    request = RunRequest(input_data={"from": "fields"}, paste_json='{"from": "paste"}')

    assert request.input_data == {"from": "paste"}
    assert request.paste_json is None


def test_an_absent_or_empty_paste_leaves_input_data_alone() -> None:
    """An empty paste box is not a paste, so it overrides nothing."""
    assert RunRequest(input_data={"kept": 1}).input_data == {"kept": 1}
    assert RunRequest(input_data={"kept": 1}, paste_json="").input_data == {"kept": 1}
    assert RunRequest(input_data={"kept": 1}, paste_json=None).input_data == {"kept": 1}


def test_the_folded_request_round_trips_through_model_validate() -> None:
    """The HTTP path builds the model from a dict; it must fold the same way."""
    request = RunRequest.model_validate({"paste_json": json.dumps({"topic": "x"})})

    assert request.input_data == {"topic": "x"}
    assert request.paste_json is None


@pytest.mark.parametrize(
    "pasted",
    ["not json at all", '{"unclosed": ', '["a", "list"]', '"a string"', "42", "null", "true"],
)
def test_a_paste_that_is_not_a_json_object_is_a_validation_error(pasted: str) -> None:
    with pytest.raises(ValidationError) as excinfo:
        RunRequest(paste_json=pasted)

    assert "paste_json" in str(excinfo.value)


def test_a_paste_that_is_not_a_string_is_a_validation_error() -> None:
    """The fold runs before field coercion, so it meets whatever was sent."""
    with pytest.raises(ValidationError) as excinfo:
        RunRequest.model_validate({"paste_json": {"already": "an object"}})

    assert "paste_json" in str(excinfo.value)
