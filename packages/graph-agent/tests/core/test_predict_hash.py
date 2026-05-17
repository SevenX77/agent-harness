from __future__ import annotations

import pytest
from graph_agent.core._predict_internal.hash import prompt_hash, schema_hash


def test_prompt_hash_normalizes_spaces_tabs_and_newlines() -> None:
    compact = "Generate JSON with title and score."
    noisy = "  Generate\tJSON\n\nwith   title\r\nand score.  "

    assert prompt_hash(compact) == prompt_hash(noisy)


def test_prompt_hash_changes_when_text_changes_after_normalization() -> None:
    assert prompt_hash("Generate JSON with title.") != prompt_hash("Generate JSON with summary.")


def test_prompt_hash_rejects_non_string_input() -> None:
    with pytest.raises(TypeError):
        prompt_hash(None)  # type: ignore[arg-type]


def test_schema_hash_uses_canonical_json_key_ordering() -> None:
    first = {
        "type": "object",
        "properties": {
            "title": {"type": "string"},
            "score": {"type": "number"},
        },
        "required": ["title", "score"],
    }
    second = {
        "required": ["title", "score"],
        "properties": {
            "score": {"type": "number"},
            "title": {"type": "string"},
        },
        "type": "object",
    }

    assert schema_hash(first) == schema_hash(second)


def test_schema_hash_changes_when_semantics_change() -> None:
    assert schema_hash({"type": "object", "properties": {"count": {"type": "integer"}}}) != (
        schema_hash({"type": "object", "properties": {"count": {"type": "string"}}})
    )


def test_schema_hash_rejects_non_json_serializable_values() -> None:
    with pytest.raises(TypeError):
        schema_hash({"bad": object()})
