"""One reading of a Markdown value that is declared to be a list.

Regression cover for the 2026-08-16 defect: a bullet value that is written as a
JSON array (``- dynamic_dimensions: ["a", "b", "c"]``) was split on commas into
three strings still carrying brackets and quotes. The fragments type-check as
``list[str]``, so schema validation accepted them and the wrong data flowed on.

Decision: ``.kiro/specs/decision-2026-08-16-json-array-in-a-bullet-value.md``
"""

from __future__ import annotations

import pytest
from pydantic import BaseModel, ConfigDict

from graph_agent.cognitive.md2json import _coerce_value
from graph_agent.core.schema_engine import _parse_output_example_to_schema
from graph_agent.tools.md_to_json import diagnose, parse_md


class DimensionList(BaseModel):
    model_config = ConfigDict(extra="forbid")

    dynamic_dimensions: list[str]


class Tagged(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tags: list[str]


class Line(BaseModel):
    speaker: str
    text: str


class Dialogue(BaseModel):
    model_config = ConfigDict(extra="forbid")

    lines: list[Line]


class Matrix(BaseModel):
    model_config = ConfigDict(extra="forbid")

    rows: list[list[str]]


# ── (a) a JSON array in a bullet value is a JSON array ────────────────────────


def test_json_array_bullet_value_parses_into_its_real_elements() -> None:
    md = '## dimension-list\n- dynamic_dimensions: ["mirror_connection", "protagonist_awareness"]'

    blocks = parse_md(md, DimensionList)

    assert blocks[0].data == {
        "dynamic_dimensions": ["mirror_connection", "protagonist_awareness"]
    }


def test_json_array_bullet_value_survives_schema_validation_intact() -> None:
    md = '## dimension-list\n- dynamic_dimensions: ["a", "b", "c"]'

    report = diagnose(parse_md(md, DimensionList), DimensionList)

    assert report.all_valid
    assert report.valid_items[0].dynamic_dimensions == ["a", "b", "c"]  # type: ignore[attr-defined]


# ── (b) a real comma list keeps working ───────────────────────────────────────


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("a, b, c", ["a", "b", "c"]),
        ("a, b,, c", ["a", "b", "c"]),
        ("solo", ["solo"]),
        ("红, 蓝", ["红", "蓝"]),
    ],
)
def test_plain_comma_list_bullet_value_is_unchanged(value: str, expected: list[str]) -> None:
    blocks = parse_md(f"## item-1\n- tags: {value}", Tagged)

    assert blocks[0].data == {"tags": expected}


# ── (c) commas inside a JSON object / nested array ────────────────────────────


def test_json_object_array_bullet_value_parses_into_objects_not_fragments() -> None:
    md = '## turn-1\n- lines: [{"speaker": "narrator", "text": "a, b"}, {"speaker": "hero", "text": "c"}]'

    report = diagnose(parse_md(md, Dialogue), Dialogue)

    assert report.all_valid
    assert [line.text for line in report.valid_items[0].lines] == ["a, b", "c"]  # type: ignore[attr-defined]


def test_nested_json_array_bullet_value_keeps_its_nesting() -> None:
    md = '## grid\n- rows: [["a", "b"], ["c"]]'

    assert parse_md(md, Matrix)[0].data == {"rows": [["a", "b"], ["c"]]}


def test_json_object_for_a_list_field_is_rejected_instead_of_being_split() -> None:
    """A ``{...}`` value read as a list field must reach validation as an object.

    The point is that no comma-splitting happens: validation gets to say "this
    is not a list" instead of receiving plausible-looking string fragments.
    """
    md = '## item-1\n- tags: {"a": 1, "b": 2}'

    report = diagnose(parse_md(md, Tagged), Tagged)

    assert not report.all_valid
    assert report.errors[0].fields[0].field == "tags"


def test_bracketed_value_that_is_not_valid_json_is_refused_not_fragmented() -> None:
    """``["a" "b"]`` opens and closes as a JSON array but does not parse.

    It must NOT degrade into comma-separated fragments — the whole reason this
    defect went unnoticed is that fragments pass a ``list[str]`` schema. The
    unparsed text reaches validation, which rejects it by naming the field.
    """
    md = '## item-1\n- tags: ["a" "b", "c"]'

    report = diagnose(parse_md(md, Tagged), Tagged)

    assert not report.all_valid
    assert report.errors[0].fields[0].field == "tags"


def test_unterminated_bracket_value_is_still_read_as_a_comma_list() -> None:
    """KNOWN GAP, recorded rather than hidden.

    ``[a, b`` carries an opening bracket but never closes, so it does not
    announce itself as a complete JSON literal and stays a comma list — the
    first fragment keeps its stray ``[``. Widening the trigger to "starts with
    ``[``" would misread genuinely comma-separated values whose first item is
    bracketed (``[a](u1), [b](u2)``), which is why the trigger stays
    "opens AND closes". See the decision doc's known-gaps section.
    """
    blocks = parse_md("## item-1\n- tags: [a, b", Tagged)

    assert blocks[0].data == {"tags": ["[a", "b"]}


# ── (d) the same rule, the same authority, at the other two call sites ────────


def test_output_example_list_default_written_as_json_is_not_fragmented() -> None:
    block = (
        '<output_example name="Demo">\n'
        "## item-1\n"
        "- title (str): the title\n"
        '- tags (list[str], optional, default=["a","b"]): labels\n'
        "</output_example>"
    )

    schema = _parse_output_example_to_schema(block)

    assert dict(schema.field_defaults)["tags"] == ["a", "b"]


def test_finish_markdown_array_value_that_opens_an_unclosed_fence_is_refused() -> None:
    """The finish_task parser reads list values through the same rule.

    A value that opens a ```json fence and never closes it announced structure
    it did not deliver; it reaches schema validation as text rather than as
    ``["```json\\n[1", "2]"]``.
    """
    assert _coerce_value("```json\n[1, 2]", {"type": "array"}) == "```json\n[1, 2]"
