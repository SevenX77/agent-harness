from __future__ import annotations

import pytest

from graph_agent.cognitive.md2json import _coerce_value

# These cases were written by 7a25b5d8 (2026-05-29) to pin the THEN-current
# behaviour of nine helpers while a C901 complexity refactor split them apart —
# a characterization suite proves a refactor changed nothing, so it records what
# the code did, not what it should do. That is how the array row below came to
# assert that an unclosed ```json fence is comma-split into
# ``["```json\n[1", "2]"]``. Rewritten 2026-08-16: a value that announces JSON
# structure and fails to parse now reaches validation as text, which is what the
# rest of this parametrize list already calls a fallback. See
# ``.kiro/specs/decision-2026-08-16-json-array-in-a-bullet-value.md``.


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
        ("```json\n[1, 2]", {"type": "array"}, "```json\n[1, 2]"),
        ("{bad json}", {"type": "object"}, "{bad json}"),
    ],
)
def test_coerce_value_current_fallbacks_return_original_stripped_text(
    raw: str,
    schema: dict[str, object],
    expected: object,
) -> None:
    assert _coerce_value(raw, schema) == expected
