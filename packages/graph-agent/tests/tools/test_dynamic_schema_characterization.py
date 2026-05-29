from __future__ import annotations

import pytest

from graph_agent.tools.dynamic_schema import (
    OutputExampleParseError,
    _build_type_runtime,
    parse_output_example,
)


VALID_EXAMPLE = """
<output_example name="Segment">
## segments
- index (int, required): zero-based index
- kind (Literal['scene', 'summary'], required): segment kind
- score (float, optional, default=1.5): confidence
- tags (list[str], optional): labels
</output_example>
""".strip()


def test_parse_output_example_accepts_required_optional_default_and_literal_fields() -> None:
    schema = parse_output_example(VALID_EXAMPLE)

    assert schema.name == "Segment"
    assert schema.item_header == "segments"
    assert [(field.name, field.type_hint, field.required, field.default) for field in schema.fields] == [
        ("index", "int", True, None),
        ("kind", "Literal['scene', 'summary']", True, None),
        ("score", "float", False, "1.5"),
        ("tags", "list[str]", False, None),
    ]
    assert schema.fields[1].enum_values == ["scene", "summary"]


@pytest.mark.parametrize(
    ("block", "message"),
    [
        ("", 'Cannot find a standalone <output_example name="...">'),
        (
            '<output_example name="123Bad">\n## item\n- value (str): desc\n</output_example>',
            "Invalid output_example schema name",
        ),
        (
            '<output_example name="Thing">\nplain text\n- value (str): desc\n</output_example>',
            "Unsupported non-bullet line",
        ),
        (
            '<output_example name="Thing">\n## one\n## two\n- value (str): desc\n</output_example>',
            "declares multiple ## item headers",
        ),
        (
            '<output_example name="Thing">\n## item\n- value str: desc\n</output_example>',
            "Bullet does not match strict pattern",
        ),
        (
            '<output_example name="Thing">\n- value (str): desc\n</output_example>',
            "must include exactly one",
        ),
        (
            '<output_example name="Thing">\n## item\n</output_example>',
            "must declare at least one field",
        ),
        (
            '<output_example name="Thing">\n## item\n- value (str, maybe): desc\n</output_example>',
            "Unknown qualifier",
        ),
    ],
)
def test_parse_output_example_rejects_current_invalid_shapes(block: str, message: str) -> None:
    with pytest.raises(OutputExampleParseError, match=message):
        parse_output_example(block)


@pytest.mark.parametrize(
    ("type_hint", "raw", "expected"),
    [
        ("int", "7", 7),
        ("float", "2.25", 2.25),
        ("str", None, ""),
        ("bool", "YES", True),
        ("Literal['red', 'blue']", "red", "red"),
        ("list[int]", "1, 2,3", [1, 2, 3]),
        ("list[Literal['a', 'b']]", ["a", "b"], ["a", "b"]),
    ],
)
def test_build_type_runtime_current_coercions(type_hint: str, raw: object, expected: object) -> None:
    coerce, enum_values = _build_type_runtime(type_hint, "field")

    assert coerce(raw) == expected
    if type_hint.startswith("Literal"):
        assert enum_values is not None


@pytest.mark.parametrize(
    ("type_hint", "raw", "message"),
    [
        ("int", True, "bool is not accepted as int"),
        ("float", False, "bool is not accepted as float"),
        ("bool", "perhaps", "expected one of true/false"),
        ("list[Literal['a']]", ["b"], "'b' not in"),
    ],
)
def test_build_type_runtime_current_coercion_errors(
    type_hint: str,
    raw: object,
    message: str,
) -> None:
    coerce, _ = _build_type_runtime(type_hint, "field")

    with pytest.raises(ValueError, match=message):
        coerce(raw)


@pytest.mark.parametrize(
    ("type_hint", "message"),
    [
        ("Literal[]", "must list at least one value"),
        ("dict", "Unsupported type 'dict'"),
        ("list[dict]", "Unsupported type 'dict'"),
    ],
)
def test_build_type_runtime_rejects_unsupported_type_declarations(
    type_hint: str,
    message: str,
) -> None:
    with pytest.raises(OutputExampleParseError, match=message):
        _build_type_runtime(type_hint, "field")
