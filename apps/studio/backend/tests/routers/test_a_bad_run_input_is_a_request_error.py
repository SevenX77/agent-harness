"""Malformed run input is a 4xx about the input, never an unhandled ValueError.

Three inputs a caller controls used to reach a bare ``raise ValueError`` /
``json.loads`` deep inside the run path: an empty ``input_ids``, a ``paste_json``
that is not a JSON object, and a saved test-input FILE whose contents are not a
JSON object. Each was answered 422 only because a process-wide ValueError
handler happened to catch it — an accident, not a contract, and one that turns
into a 500 the moment that handler is removed (PR #1087).

Each case is driven through the public route, because the point is what the
CALLER is told. A service-level assertion would pass just as well with the
handler gone.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


def _assert_client_error(response: object, *, names: str) -> None:
    body = getattr(response, "text", "")
    status = int(getattr(response, "status_code", 0))
    assert 400 <= status < 500, f"expected a 4xx, got {status}: {body[:400]}"
    assert names in body, f"the error does not name what was wrong ({names}): {body[:400]}"


def test_a_batch_run_with_no_input_ids_is_a_request_error(client: TestClient) -> None:
    """An empty list is refused by the schema, so no run is ever started for it."""
    response = client.post(
        "/api/skills/text-segmentation/runs/batch-run",
        json={"input_ids": []},
    )

    _assert_client_error(response, names="input_ids")


@pytest.mark.parametrize(
    "pasted",
    [
        "not json at all",
        '{"unclosed": ',
        '["a", "list", "is", "not", "an", "object"]',
        '"just a string"',
        "42",
    ],
)
def test_a_run_whose_pasted_json_is_not_an_object_is_a_request_error(
    client: TestClient,
    pasted: str,
) -> None:
    """``paste_json`` is decoded at the boundary, so a bad paste never reaches a run.

    ``json.JSONDecodeError`` is a subclass of ``ValueError``, which is why this
    one looked handled: the paste box's mistakes were being answered by a generic
    exception handler rather than by the field that owns the value.
    """
    response = client.post(
        "/api/skills/text-segmentation/runs",
        json={"paste_json": pasted},
    )

    _assert_client_error(response, names="paste_json")


def test_a_run_whose_pasted_json_is_an_object_still_starts(client: TestClient) -> None:
    """The refusal must be about the SHAPE, not about pasting at all.

    Paired with the parametrized case above so a fix that rejects every paste
    cannot pass. The run itself is gated on a passing Predict, so what is
    asserted is that the request got past request validation into the run gate.
    """
    response = client.post(
        "/api/skills/text-segmentation/runs",
        json={"paste_json": json.dumps({"input_text": "pasted"})},
    )

    assert response.status_code != 422, response.text
    assert "paste_json" not in response.text


def test_a_saved_test_input_that_is_not_an_object_is_a_request_error(
    client: TestClient,
    studio_roots: tuple[Path, Path],
) -> None:
    """A file's CONTENTS cannot be constrained by a request model, so the service
    has to answer for them with a real error code.

    A test input holding a JSON list parses fine and is simply not the thing a
    run's inputs can be. That is a 4xx about the named test input, not an
    unhandled exception from inside the batch loop.
    """
    skills_dir, _ = studio_roots
    import_files = skills_dir / "text-segmentation" / ".workspace" / "import_files"
    import_files.mkdir(parents=True, exist_ok=True)
    (import_files / "listy.json").write_text(json.dumps(["not", "an", "object"]), encoding="utf-8")

    response = client.post(
        "/api/skills/text-segmentation/runs/batch-run",
        json={"input_ids": ["listy"]},
    )

    _assert_client_error(response, names="listy")
    # The CODE is asserted, not just the status: the generic ValueError handler
    # answered this with `MANIFEST_VALIDATION_FAILED`, which tells the reader the
    # skill's manifest is broken when what is broken is one test input file.
    assert response.json()["error_code"] == "TEST_INPUT_VALIDATION_FAILED", response.text
