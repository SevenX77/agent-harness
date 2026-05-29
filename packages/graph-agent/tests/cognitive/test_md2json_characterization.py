from __future__ import annotations

import pytest

from graph_agent.cognitive.md2json import _coerce_value


@pytest.mark.parametrize(
    ("raw", "schema", "expected"),
    [
        ("42", {"type": "integer"}, 42),
        ("3.5", {"type": "number"}, 3.5),
        ("YES", {"type": "boolean"}, True),
        ("no", {"type": "boolean"}, False),
        ("a, b,, c", {"type": "array"}, ["a", "b", "c"]),
        ('{"a": 1}', {"type": "object"}, {"a": 1}),
        ("```json\n[1, 2]\n```", {"type": "array"}, [1, 2]),
        (" text ", None, "text"),
    ],
)
def test_coerce_value_current_successful_coercions(
    raw: str,
    schema: dict[str, object] | None,
    expected: object,
) -> None:
    assert _coerce_value(raw, schema) == expected


@pytest.mark.parametrize(
    ("raw", "schema", "expected"),
    [
        ("not-int", {"type": "integer"}, "not-int"),
        ("not-number", {"type": "number"}, "not-number"),
        ("maybe", {"type": "boolean"}, "maybe"),
        ("a, b", {"type": "string"}, "a, b"),
        ("```json\n[1, 2]", {"type": "array"}, ["```json\n[1", "2]"]),
        ("{bad json}", {"type": "object"}, "{bad json}"),
    ],
)
def test_coerce_value_current_fallbacks_return_original_stripped_text(
    raw: str,
    schema: dict[str, object],
    expected: object,
) -> None:
    assert _coerce_value(raw, schema) == expected
