from __future__ import annotations

from pydantic import BaseModel

from graph_agent.tools.md_to_json import _parse_block_data


class DialogueLine(BaseModel):
    speaker: str
    text: str


def test_parse_block_data_coerces_flat_int_float_and_inline_list_fields() -> None:
    parsed = _parse_block_data(
        [
            "- index: 3",
            "- score: 0.75",
            "- tags: a, b, c",
        ],
        {"index": int, "score": float, "tags": list[str]},
    )

    assert parsed == {"index": 3, "score": 0.75, "tags": ["a", "b", "c"]}


def test_parse_block_data_keeps_uncoercible_numeric_values_as_strings() -> None:
    parsed = _parse_block_data(["- index: many"], {"index": int})

    assert parsed == {"index": "many"}


def test_parse_block_data_collects_indented_children_for_plain_list_fields() -> None:
    parsed = _parse_block_data(
        [
            "- beats:",
            "  - first",
            "  - second",
            "",
            "- title: done",
        ],
        {"beats": list[str], "title": str},
    )

    assert parsed == {"beats": ["first", "second"], "title": "done"}


def test_parse_block_data_parses_at_key_children_for_nested_model_lists() -> None:
    parsed = _parse_block_data(
        [
            "- dialogue:",
            "  - @speaker: narrator",
            "  - @text: hello",
            "  - @speaker: hero",
            "  - @text: hi",
        ],
        {"dialogue": list[DialogueLine]},
    )

    assert parsed == {
        "dialogue": [
            {"speaker": "narrator", "text": "hello"},
            {"speaker": "hero", "text": "hi"},
        ]
    }


def test_parse_block_data_treats_at_key_children_as_objects_even_for_string_lists() -> None:
    parsed = _parse_block_data(
        [
            "- notes:",
            "  - @kind: clue",
            "  - @text: door",
        ],
        {"notes": list[str]},
    )

    assert parsed == {"notes": [{"kind": "clue", "text": "door"}]}


def test_parse_block_data_joins_children_for_non_list_nested_fields() -> None:
    parsed = _parse_block_data(
        [
            "- summary:",
            "  - line one",
            "  - line two",
        ],
        {"summary": str},
    )

    assert parsed == {"summary": "line one, line two"}


def test_parse_block_data_skips_orphan_children_and_unrecognised_lines() -> None:
    parsed = _parse_block_data(
        [
            "  - orphan",
            "plain text",
            "- title: kept",
        ],
        {"title": str},
    )

    assert parsed == {"title": "kept"}
