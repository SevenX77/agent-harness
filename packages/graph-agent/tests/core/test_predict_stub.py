from __future__ import annotations

from graph_agent.core._predict_internal.stub import generate_heuristic_stub


def test_generate_basic_json_schema_field_types() -> None:
    schema = {
        "type": "object",
        "properties": {
            "title": {"type": "string"},
            "count": {"type": "integer"},
            "score": {"type": "number"},
            "accepted": {"type": "boolean"},
            "items": {"type": "array", "items": {"type": "string"}},
            "metadata": {"type": "object", "properties": {"source": {"type": "string"}}},
            "category": {"type": "string", "enum": ["alpha", "beta"]},
        },
    }

    assert generate_heuristic_stub(schema) == {
        "title": "<mock_title>",
        "count": 0,
        "score": 0.0,
        "accepted": True,
        "items": [],
        "metadata": {"source": "<mock_source>"},
        "category": "alpha",
    }


def test_generate_pydantic_style_json_schema() -> None:
    schema = {
        "properties": {
            "text": {"title": "Text", "type": "string"},
            "tags": {"items": {"type": "string"}, "title": "Tags", "type": "array"},
            "confidence": {"title": "Confidence", "type": "number"},
        },
        "required": ["text"],
        "title": "Answer",
        "type": "object",
    }

    assert generate_heuristic_stub(schema) == {
        "text": "<mock_text>",
        "tags": [],
        "confidence": 0.0,
    }


def test_generate_nested_object_and_dict_like_additional_properties() -> None:
    schema = {
        "type": "object",
        "properties": {
            "profile": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "stats": {
                        "type": "object",
                        "additionalProperties": {"type": "integer"},
                    },
                },
            }
        },
    }

    assert generate_heuristic_stub(schema) == {
        "profile": {
            "name": "<mock_name>",
            "stats": {},
        }
    }


def test_generate_top_level_scalar_degrades_to_payload() -> None:
    assert generate_heuristic_stub({"type": "string"}) == {"value": "<mock_value>"}
    assert generate_heuristic_stub({"type": "integer"}) == {"value": 0}


def test_unknown_missing_or_malformed_schema_degrades_without_raising() -> None:
    assert generate_heuristic_stub(None) == {"value": "<mock_unknown>"}
    assert generate_heuristic_stub({}) == {"value": "<mock_unknown>"}
    assert generate_heuristic_stub({"type": "never-heard-of"}) == {"value": "<mock_unknown>"}
    assert generate_heuristic_stub({"type": "object", "properties": "not-a-dict"}) == {}


def test_circular_schema_degrades_without_recursion_error() -> None:
    schema: dict[str, object] = {"type": "object", "properties": {}}
    properties = schema["properties"]
    assert isinstance(properties, dict)
    properties["self"] = schema

    assert generate_heuristic_stub(schema) == {"self": "<mock_self>"}
