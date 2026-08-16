"""Helper-level baselines for ``md_to_json``'s block parser.

Provenance: introduced by ``7a25b5d8`` (2026-05-29, "C901 complexity gate + 13
helper refactor"), whose body reads "Add 8 characterization tests (100 cases)
locking 9 helper baselines". A characterization test records what the code DID
at that moment, to prove a refactor changed nothing — it does not assert what
the code SHOULD do.

Two things changed here on 2026-08-16, both deliberate, both stated rather than
quietly re-baselined:

1. ``_parse_block_data`` now takes ``_SourceLine`` (line number + text) and
   returns ``(fields, unread)``. Line numbers are what let an unread line be
   pointed at rather than only quoted.
2. ``test_parse_block_data_skips_orphan_children_and_unrecognised_lines`` used
   to assert that an orphan child and an unrecognised line are dropped in
   silence. That silence is exactly the defect
   ``.kiro/specs/decision-2026-08-16-parse-md-reports-what-it-did-not-understand.md``
   removes, so the case is rewritten in place: the fields it CAN read are still
   read, and the lines it cannot are now named.
"""

from __future__ import annotations

from pydantic import BaseModel

from graph_agent.tools.md_to_json import _parse_block_data, _SourceLine


def _lines(*texts: str) -> list[_SourceLine]:
    return [_SourceLine(number=i, text=text) for i, text in enumerate(texts, start=1)]


class DialogueLine(BaseModel):
    speaker: str
    text: str


def test_parse_block_data_coerces_flat_int_float_and_inline_list_fields() -> None:
    parsed, unread = _parse_block_data(
        _lines(
            "- index: 3",
            "- score: 0.75",
            "- tags: a, b, c",
        ),
        {"index": int, "score": float, "tags": list[str]},
    )

    assert parsed == {"index": 3, "score": 0.75, "tags": ["a", "b", "c"]}
    assert unread == []


def test_parse_block_data_keeps_uncoercible_numeric_values_as_strings() -> None:
    parsed, unread = _parse_block_data(_lines("- index: many"), {"index": int})

    assert parsed == {"index": "many"}
    assert unread == []


def test_parse_block_data_collects_indented_children_for_plain_list_fields() -> None:
    parsed, unread = _parse_block_data(
        _lines(
            "- beats:",
            "  - first",
            "  - second",
            "",
            "- title: done",
        ),
        {"beats": list[str], "title": str},
    )

    assert parsed == {"beats": ["first", "second"], "title": "done"}
    assert unread == []


def test_parse_block_data_parses_at_key_children_for_nested_model_lists() -> None:
    parsed, unread = _parse_block_data(
        _lines(
            "- dialogue:",
            "  - @speaker: narrator",
            "  - @text: hello",
            "  - @speaker: hero",
            "  - @text: hi",
        ),
        {"dialogue": list[DialogueLine]},
    )

    assert parsed == {
        "dialogue": [
            {"speaker": "narrator", "text": "hello"},
            {"speaker": "hero", "text": "hi"},
        ]
    }
    assert unread == []


def test_parse_block_data_treats_at_key_children_as_objects_even_for_string_lists() -> None:
    parsed, unread = _parse_block_data(
        _lines(
            "- notes:",
            "  - @kind: clue",
            "  - @text: door",
        ),
        {"notes": list[str]},
    )

    assert parsed == {"notes": [{"kind": "clue", "text": "door"}]}
    assert unread == []


def test_parse_block_data_joins_children_for_non_list_nested_fields() -> None:
    parsed, unread = _parse_block_data(
        _lines(
            "- summary:",
            "  - line one",
            "  - line two",
        ),
        {"summary": str},
    )

    assert parsed == {"summary": "line one, line two"}
    assert unread == []


def test_parse_block_data_names_orphan_children_and_unreadable_field_lines() -> None:
    parsed, unread = _parse_block_data(
        _lines(
            "  - orphan",
            "plain text",
            "stray: value",
            "- title: kept",
        ),
        {"title": str},
    )

    assert parsed == {"title": "kept"}
    # "plain text" announces no structure, so it is not claimed as lost; the
    # orphan bullet and the bulletless ``name:`` line do, so they are named.
    assert [(entry.line_number, entry.text) for entry in unread] == [
        (1, "  - orphan"),
        (3, "stray: value"),
    ]
