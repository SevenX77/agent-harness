from __future__ import annotations

import pytest

from graph_agent.core._predict_internal.stub import _normalise_type


@pytest.mark.parametrize(
    ("raw_type", "expected"),
    [
        ("OBJECT", "object"),
        ("dict", "object"),
        ("tuple", "array"),
        ("double", "number"),
        ("int", "integer"),
        ("bool", "boolean"),
        ("custom", "custom"),
        (["null", "string"], "string"),
        (["null", "dict"], "object"),
        (["null"], None),
        (None, None),
        ({"type": "string"}, None),
    ],
)
def test_normalise_type_current_aliases_and_fallbacks(raw_type: object, expected: str | None) -> None:
    assert _normalise_type(raw_type) == expected
