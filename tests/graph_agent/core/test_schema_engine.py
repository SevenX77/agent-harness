"""Tests for MVP-2 T2 SchemaEngine parsing and Pydantic projection."""

from __future__ import annotations

import pytest
from pydantic import BaseModel

from graph_agent.core.schema_engine import (
    SchemaEngine,
    SchemaObject,
    SchemaParseError,
    ValidationResult,
)

SIMPLE_SCHEMA = """
title: str
score: int
tags?: list[str]
published: bool | None
"""

NESTED_SCHEMA = """
metadata:
  source: str
  confidence: float
title: str
"""

LIST_SCHEMA = """
tags:
  - str
"""

LIST_OBJECT_SCHEMA = """
segments:
  - start_line: int
    end_line: int
    content: str
"""

OUTPUT_EXAMPLE = """<output_example name="Segment">
## segments
- index (int, required): 段落顺序编号
- type (Literal[A,B,C], required): 段落类型
- content (str, required): 剧情概括
- confidence (float, optional, default=1.0): 置信度
</output_example>
"""


class TestSchemaEngineInit:
    def test_schema_engine_init(self) -> None:
        engine = SchemaEngine()

        assert isinstance(engine, SchemaEngine)


class TestSchemaObject:
    def test_schema_object_is_frozen_and_hashable(self) -> None:
        schema = SchemaObject(fields=(("title", str),), required_fields=frozenset({"title"}))

        assert hash(schema) == hash(schema)
        with pytest.raises(AttributeError):
            schema.schema_name = "Other"  # type: ignore[misc]

    def test_schema_object_dict_views(self) -> None:
        schema = SchemaObject(
            fields=(("title", str),),
            required_fields=frozenset({"title"}),
            raw_schema_dict={"type": "object"},
            field_descriptions=(("title", "Title text"),),
        )

        assert schema.raw == {"type": "object"}
        assert schema.field_map == {"title": str}
        assert schema.description_map == {"title": "Title text"}


class TestParseFromMd:
    def test_parse_from_md_empty_returns_empty_schema(self) -> None:
        result = SchemaEngine().parse_from_md("")

        assert result == SchemaObject(raw_schema_dict={})

    def test_parse_from_md_simple_schema(self) -> None:
        schema = SchemaEngine().parse_from_md(SIMPLE_SCHEMA)

        assert schema.field_map["title"] is str
        assert schema.field_map["score"] is int
        assert "title" in schema.required_fields
        assert "score" in schema.required_fields
        assert "tags" not in schema.required_fields
        assert "published" not in schema.required_fields

    def test_parse_from_md_named_output_schema_block(self) -> None:
        md = """
phases:
  - name: draft
    output_schema: |
      title: str
      score: int
"""

        schema = SchemaEngine().parse_from_md(md)

        assert schema.field_map == {"title": str, "score": int}
        assert schema.required_fields == frozenset({"title", "score"})

    def test_parse_from_md_nested_schema(self) -> None:
        schema = SchemaEngine().parse_from_md(NESTED_SCHEMA)
        nested = schema.field_map["metadata"]

        assert isinstance(nested, SchemaObject)
        assert nested.field_map == {"source": str, "confidence": float}
        assert schema.required_fields == frozenset({"metadata", "title"})

    def test_parse_from_md_list_schema(self) -> None:
        schema = SchemaEngine().parse_from_md(LIST_SCHEMA)
        model = SchemaEngine().get_pydantic_model(schema)

        instance = model.model_validate({"tags": ["a", "b"]})

        assert instance.model_dump() == {"tags": ["a", "b"]}

    def test_parse_from_md_list_object_schema(self) -> None:
        schema = SchemaEngine().parse_from_md(LIST_OBJECT_SCHEMA)
        model = SchemaEngine().get_pydantic_model(schema)

        instance = model.model_validate(
            {"segments": [{"start_line": 1, "end_line": 3, "content": "opening"}]}
        )

        assert instance.model_dump() == {
            "segments": [{"start_line": 1, "end_line": 3, "content": "opening"}]
        }

    def test_parse_from_md_output_example(self) -> None:
        schema = SchemaEngine().parse_from_md(OUTPUT_EXAMPLE)

        assert schema.schema_name == "Segment"
        assert schema.item_header == "segments"
        assert schema.field_map["index"] is int
        assert "confidence" not in schema.required_fields
        assert schema.description_map["content"] == "剧情概括"
        assert schema.output_example_md == OUTPUT_EXAMPLE.strip()

    def test_parse_from_md_invalid_raises(self) -> None:
        with pytest.raises(SchemaParseError, match="missing a type"):
            SchemaEngine().parse_from_md("title:")

    def test_parse_from_md_duplicate_raises(self) -> None:
        with pytest.raises(SchemaParseError, match="Duplicate field"):
            SchemaEngine().parse_from_md("title: str\ntitle: int")

    def test_parse_from_md_invalid_output_example_raises(self) -> None:
        bad_example = OUTPUT_EXAMPLE.replace("(int, required)", "(Int, required)")

        with pytest.raises(SchemaParseError, match="Invalid output_example"):
            SchemaEngine().parse_from_md(bad_example)


class TestGetPydanticModel:
    def test_get_pydantic_model_returns_basemodel_subclass(self) -> None:
        schema = SchemaEngine().parse_from_md(SIMPLE_SCHEMA)

        model_cls = SchemaEngine().get_pydantic_model(schema)

        assert isinstance(model_cls, type)
        assert issubclass(model_cls, BaseModel)

    def test_get_pydantic_model_lru_cache(self) -> None:
        engine = SchemaEngine()
        schema = engine.parse_from_md(SIMPLE_SCHEMA)

        first = engine.get_pydantic_model(schema)
        second = engine.get_pydantic_model(schema)

        assert first is second

    def test_get_pydantic_model_required_fields(self) -> None:
        engine = SchemaEngine()
        schema = engine.parse_from_md("title: str\nscore: int")
        model = engine.get_pydantic_model(schema)

        with pytest.raises(ValueError, match="score"):
            model.model_validate({"title": "Scene"})

    def test_get_pydantic_model_optional_fields(self) -> None:
        engine = SchemaEngine()
        schema = engine.parse_from_md("title: str\ntags?: list[str]")
        model = engine.get_pydantic_model(schema)

        instance = model.model_validate({"title": "Scene"})

        assert instance.model_dump() == {"title": "Scene", "tags": None}


class TestValidate:
    def test_validate_returns_validation_result(self) -> None:
        engine = SchemaEngine()
        schema = engine.parse_from_md("title: str")

        result = engine.validate({"title": "Scene"}, schema)

        assert isinstance(result, ValidationResult)

    def test_validate_pass_with_valid_data(self) -> None:
        engine = SchemaEngine()
        schema = engine.parse_from_md(OUTPUT_EXAMPLE)

        result = engine.validate(
            {"index": 1, "type": "A", "content": "opening", "confidence": 0.9},
            schema,
        )

        assert result.ok is True
        assert result.passed is True
        assert result.errors == ()
        assert result.parsed == {
            "index": 1,
            "type": "A",
            "content": "opening",
            "confidence": 0.9,
        }

    def test_validate_pass_applies_output_example_default(self) -> None:
        engine = SchemaEngine()
        schema = engine.parse_from_md(OUTPUT_EXAMPLE)

        result = engine.validate(
            {"index": 1, "type": "A", "content": "opening"},
            schema,
        )

        assert result.ok is True
        assert result.parsed == {
            "index": 1,
            "type": "A",
            "content": "opening",
            "confidence": 1.0,
        }

    def test_validate_fail_with_invalid_data(self) -> None:
        engine = SchemaEngine()
        schema = engine.parse_from_md(OUTPUT_EXAMPLE)

        result = engine.validate({"index": "not-int", "type": "Z"}, schema)

        assert result.ok is False
        assert result.parsed is None
        assert "index" in result.field_errors
        assert "type" in result.field_errors
        assert "content" in result.field_errors

    def test_validate_fail_with_extra_field(self) -> None:
        engine = SchemaEngine()
        schema = engine.parse_from_md("title: str")

        result = engine.validate({"title": "Scene", "extra": "no"}, schema)

        assert result.ok is False
        assert "extra" in result.field_errors


class TestGetJsonSchema:
    def test_get_json_schema_returns_jsonschema(self) -> None:
        engine = SchemaEngine()
        schema = engine.parse_from_md(SIMPLE_SCHEMA)

        json_schema = engine.get_json_schema(schema)

        assert json_schema["type"] == "object"
        assert "properties" in json_schema
        assert json_schema["properties"]["title"]["type"] == "string"
        assert json_schema["properties"]["score"]["type"] == "integer"
        assert set(json_schema["required"]) == {"title", "score"}

    def test_get_json_schema_returns_nested_jsonschema(self) -> None:
        engine = SchemaEngine()
        schema = engine.parse_from_md(NESTED_SCHEMA)

        json_schema = engine.get_json_schema(schema)

        assert "$defs" in json_schema
        assert json_schema["properties"]["metadata"]["$ref"].startswith("#/$defs/")
