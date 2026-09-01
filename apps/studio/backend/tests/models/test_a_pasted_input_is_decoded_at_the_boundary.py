"""``RunRequest`` folds ``paste_json`` into ``input_data`` on each VALIDATED path.

Asserted by CONSTRUCTING the model, not by driving a route, and that is the whole
point of this file. The route-level tests reach the run gate and stop there —
``RUN_REQUIRES_PREDICT`` answers before anything consumes the inputs — so they
can only show that a bad paste is refused, never that a good one arrived. A fold
that silently produced nothing passed every one of them.

**Covered here** — the three ways this model gets built:

- ``RunRequest(**kwargs)``, pydantic's ``__init__``. This is the one that was
  broken: an ``mode="after"`` validator is specified to return the CURRENT
  instance, so a ``model_copy`` result is outside the contract — pydantic warned
  and then discarded it, and the paste reached the run as ``None``.
- ``RunRequest.model_validate(dict)``, which is the HTTP path.
- ``RunRequest.model_validate(<any Mapping>)`` — pydantic accepts more than
  ``dict``, so the validator's own gate has to as well; an ``isinstance(…, dict)``
  check skipped the fold for a ``UserDict`` while validating happily.

**Deliberately NOT covered, because pydantic does not run validators there:**
``model_copy(update={...})`` is documented as a copy, not a validation — a
``model_copy(update={"paste_json": "…"})`` would leave the paste unfolded. That
is not a hole to plug with a wrapper: the fold is a BOUNDARY transformation and
``model_copy`` is by definition not the boundary. The repo has no call site that
updates ``input_data`` or ``paste_json`` that way, and must not gain one — set
those two fields by validating a request, never by copying one.
"""

from __future__ import annotations

import json
from collections import UserDict

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


def test_a_mapping_that_is_not_a_dict_folds_too() -> None:
    """pydantic accepts any ``Mapping``, so the validator's gate must as well.

    An ``isinstance(data, dict)`` gate let a ``UserDict`` through UNFOLDED: the
    model validated without complaint and the paste simply never became input
    data. Same class of bug as the ``mode="after"`` one — a construction path
    where the transformation quietly does not happen.
    """
    request = RunRequest.model_validate(UserDict({"paste_json": '{"topic": "mapping"}'}))

    assert request.input_data == {"topic": "mapping"}
    assert request.paste_json is None


def test_a_mapping_the_caller_owns_is_not_mutated() -> None:
    """The fold rewrites a NEW mapping; the caller's own object is left alone."""
    payload = UserDict({"paste_json": '{"topic": "x"}', "golden_id": "g1"})

    RunRequest.model_validate(payload)

    assert payload["paste_json"] == '{"topic": "x"}'
    assert "input_data" not in payload


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
