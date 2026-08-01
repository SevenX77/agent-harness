"""Validation must not invent fields the submitter never sent.

The schema-projected Pydantic model defaults absent optionals to None, and
``model_dump()`` materialises them — so a finish_task submission that simply
omitted an optional ``metadata: object`` reached the blackboard as
``metadata: null`` and was then killed by state_mapper's OWN jsonschema check
("None is not of type 'object'"; field evidence: run 2026-08-01T10-32-40,
skill exp-a-round1, model args carried no ``metadata`` key at all).
"""

from __future__ import annotations

from graph_agent.core.schema_engine import (
    SchemaEngine,
    SchemaObject,
    _schema_from_mapping,
)


def _schema_with_optional_object() -> SchemaObject:
    return _schema_from_mapping(
        {
            "type": "object",
            "required": ["name"],
            "properties": {
                "name": {"type": "string"},
                "metadata": {"type": "object"},
            },
        }
    )


def test_absent_optional_stays_absent_in_parsed() -> None:
    engine = SchemaEngine()
    result = engine.validate({"name": "第1章"}, _schema_with_optional_object())

    assert result.ok
    assert result.parsed is not None
    assert result.parsed["name"] == "第1章"
    assert "metadata" not in result.parsed, (
        "validation invented metadata=None for a field the submitter omitted; "
        "downstream jsonschema rejects null where an object is declared"
    )


def _schema_with_nested_optional_object() -> SchemaObject:
    return _schema_from_mapping(
        {
            "type": "object",
            "required": ["result"],
            "properties": {
                "result": {
                    "type": "object",
                    "required": ["chapter_number"],
                    "properties": {
                        "chapter_number": {"type": "integer"},
                        "metadata": {"type": "object"},
                    },
                }
            },
        }
    )


def test_absent_optional_inside_nested_object_stays_absent() -> None:
    """Field evidence: run 2026-08-01T16-37-57 died on
    "None is not of type 'object'" for segmentation_result.metadata — the
    top-level filter did not reach fields the parent model dumps recursively."""
    engine = SchemaEngine()

    result = engine.validate(
        {"result": {"chapter_number": 1}}, _schema_with_nested_optional_object()
    )

    assert result.ok
    assert result.parsed is not None
    assert "metadata" not in result.parsed["result"]


def test_submitted_optional_survives_parsing() -> None:
    engine = SchemaEngine()
    result = engine.validate(
        {"name": "第1章", "metadata": {"k": 1}}, _schema_with_optional_object()
    )

    assert result.ok
    assert result.parsed is not None
    assert result.parsed["metadata"] == {"k": 1}
