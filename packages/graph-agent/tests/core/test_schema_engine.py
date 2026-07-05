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


class TestEdgeCaseInputsT8:
    """MVP-2 T8: branch coverage for SchemaEngine edge cases.

    Pin previously-uncovered branches surfaced by the T8 coverage report
    (target ≥ 95%): empty fragments, ``output_schema`` named-block,
    JSON Schema route, malformed JSON, duplicate fields, indent errors,
    Optional/Literal/list[X] type variants, and ``Any`` descriptors.
    """

    def test_empty_fragment_returns_empty_schema_object(self) -> None:
        engine = SchemaEngine()

        result = engine.parse_from_md("")

        assert result.fields == ()
        assert result.required_fields == frozenset()

    def test_whitespace_only_fragment_returns_empty_schema_object(self) -> None:
        engine = SchemaEngine()

        result = engine.parse_from_md("   \n   \n")

        assert result.fields == ()

    def test_named_output_schema_block_inline_value(self) -> None:
        """``output_schema:`` with an inline (non-``|``) string value."""
        engine = SchemaEngine()

        md = 'output_schema: "title: str"\n'
        # The inline-value path returns the bare string, not a structured
        # schema, so re-feeding it as md_content yields a 1-field schema.
        # Calling parse_from_md should still succeed without raising.
        schema = engine.parse_from_md(md)
        assert isinstance(schema, SchemaObject)

    def test_named_output_schema_block_with_pipe_body(self) -> None:
        engine = SchemaEngine()

        md = "output_schema: |\n  title: str\n  score: int\n"
        schema = engine.parse_from_md(md)

        names = [n for n, _ in schema.fields]
        assert "title" in names
        assert "score" in names

    def test_named_output_example_block_in_yaml(self) -> None:
        """``output_example:`` named-yaml block path."""
        engine = SchemaEngine()

        md = (
            "output_example: |\n"
            '  <output_example name="Item">\n'
            "  ## item\n"
            "  - title (str, required): 标题\n"
            "  </output_example>\n"
        )
        schema = engine.parse_from_md(md)

        assert "title" in {n for n, _ in schema.fields}

    def test_json_object_schema_via_properties(self) -> None:
        engine = SchemaEngine()

        md = '{"properties": {"title": "str", "score": "int"}, "required": ["title"]}'
        schema = engine.parse_from_md(md)

        assert {n for n, _ in schema.fields} == {"title", "score"}
        assert schema.required_fields == frozenset({"title"})

    def test_json_object_schema_inline_mapping(self) -> None:
        """JSON object without ``properties`` wraps every key as required."""
        engine = SchemaEngine()

        schema = engine.parse_from_md('{"title": "str", "score": "int"}')

        assert schema.required_fields == frozenset({"title", "score"})

    def test_json_object_schema_with_list_shorthand(self) -> None:
        engine = SchemaEngine()

        schema = engine.parse_from_md('{"tags": ["str"]}')

        assert {n for n, _ in schema.fields} == {"tags"}

    def test_json_object_schema_string_enum_maps_to_literal(self) -> None:
        engine = SchemaEngine()

        schema = engine.parse_from_md(
            '{"properties": {"kind": {"type": "string", "enum": ["A", "B", "C"]}}, '
            '"required": ["kind"]}'
        )
        model = engine.get_pydantic_model(schema)

        assert model.model_validate({"kind": "A"}).model_dump() == {"kind": "A"}
        with pytest.raises(ValueError, match="Input should be 'A', 'B' or 'C'"):
            model.model_validate({"kind": "D"})

    def test_json_invalid_raises_schema_parse_error(self) -> None:
        engine = SchemaEngine()

        with pytest.raises(SchemaParseError, match="Invalid JSON"):
            engine.parse_from_md('{"title": "str"')  # missing closing brace

    # ``_try_parse_json_schema`` returns None unless the fragment begins
    # with ``{``, so the "must be an object" branch (lines 270-272) is
    # defensive against future callers that bypass the prefix gate.
    # Not exercising it here keeps tests behavioural rather than
    # white-box.

    def test_json_required_must_be_list(self) -> None:
        engine = SchemaEngine()

        with pytest.raises(SchemaParseError, match="'required' must be a list"):
            engine.parse_from_md('{"properties": {"title": "str"}, "required": "title"}')

    def test_json_list_shorthand_must_have_one_item(self) -> None:
        engine = SchemaEngine()

        with pytest.raises(SchemaParseError, match="exactly one item"):
            engine.parse_from_md('{"tags": ["str", "int"]}')

    def test_json_unsupported_value_type_raises(self) -> None:
        engine = SchemaEngine()

        with pytest.raises(SchemaParseError, match="Unsupported schema value"):
            engine.parse_from_md('{"oops": 42}')

    def test_duplicate_field_in_output_example_raises(self) -> None:
        engine = SchemaEngine()

        md = (
            '<output_example name="Item">\n'
            "## item\n"
            "- name (str, required): A\n"
            "- name (int, required): duplicate\n"
            "</output_example>"
        )
        with pytest.raises((SchemaParseError, ValueError)):
            engine.parse_from_md(md)

    def test_optional_question_mark_marker(self) -> None:
        engine = SchemaEngine()

        schema = engine.parse_from_md("title: str?")

        assert schema.required_fields == frozenset()

    def test_optional_via_pipe_none_suffix(self) -> None:
        engine = SchemaEngine()

        schema = engine.parse_from_md("title: str | None")

        assert schema.required_fields == frozenset()

    def test_optional_via_none_pipe_prefix(self) -> None:
        engine = SchemaEngine()

        schema = engine.parse_from_md("title: None | str")

        assert schema.required_fields == frozenset()

    def test_optional_via_typing_optional(self) -> None:
        engine = SchemaEngine()

        schema = engine.parse_from_md("title: Optional[str]")

        assert schema.required_fields == frozenset()

    def test_uppercase_list_alias(self) -> None:
        engine = SchemaEngine()

        schema = engine.parse_from_md("tags: List[str]")

        # ListType wrapping str descriptor.
        assert {n for n, _ in schema.fields} == {"tags"}

    def test_empty_literal_raises(self) -> None:
        engine = SchemaEngine()

        with pytest.raises(SchemaParseError, match="Literal"):
            engine.parse_from_md("status: Literal[]")

    def test_empty_type_via_internal_parser_raises(self) -> None:
        """``_parse_type_expr`` rejects an empty string — the public
        ``parse_from_md`` path raises ``missing a type declaration``
        before reaching this guard, so we exercise it directly."""
        from graph_agent.core.schema_engine import _parse_type_expr

        with pytest.raises(SchemaParseError, match="Empty type"):
            _parse_type_expr("")

    def test_unsupported_type_raises(self) -> None:
        engine = SchemaEngine()

        with pytest.raises(SchemaParseError, match="Unsupported schema type"):
            engine.parse_from_md("title: Set[str]")

    def test_unexpected_indentation_raises(self) -> None:
        engine = SchemaEngine()

        # second field is indented one space deeper than the first while
        # still being at top-level — the parser must reject it.
        md = "title: str\n score: int\n"
        with pytest.raises(SchemaParseError, match="Unexpected indentation"):
            engine.parse_from_md(md)

    def test_invalid_schema_line_raises(self) -> None:
        engine = SchemaEngine()

        with pytest.raises(SchemaParseError, match="Invalid schema line"):
            engine.parse_from_md("not a key value pair\n")

    def test_field_missing_type_with_no_children_raises(self) -> None:
        engine = SchemaEngine()

        with pytest.raises(SchemaParseError, match="missing a type declaration"):
            engine.parse_from_md("metadata:\n")

    def test_any_type_descriptor_round_trip(self) -> None:
        """``Any`` descriptor exercises the ``_optional_annotation``
        identity and ``_descriptor_to_raw`` no-type branches."""
        engine = SchemaEngine()

        schema = engine.parse_from_md("payload?: Any")

        json_schema = engine.get_json_schema(schema)
        # Any descriptor is rendered as an open object schema.
        assert "payload" in json_schema["properties"]

    def test_list_inline_primitive(self) -> None:
        engine = SchemaEngine()

        schema = engine.parse_from_md("tags:\n  - str\n")

        assert {n for n, _ in schema.fields} == {"tags"}

    def test_validate_with_default_value_optional_field(self) -> None:
        """A field with ``default=`` must carry that default through the
        Pydantic model so omitted submissions accept the default."""
        engine = SchemaEngine()
        md = (
            '<output_example name="Item">\n'
            "## item\n"
            "- title (str, required): A\n"
            "- score (int, optional, default=5): B\n"
            "</output_example>"
        )
        schema = engine.parse_from_md(md)

        result = engine.validate({"title": "x"}, schema)

        assert result.ok
        assert result.parsed is not None
        assert result.parsed["score"] == 5
