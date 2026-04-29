"""Tests for MVP-2 T1: SchemaEngine module skeleton.

These tests pin the T1 contract (interface shapes, dataclass defaults,
caching behaviour). Later MVP-2 tasks (T2/T3/T5/T6) will extend the
suite as real parsing/validation logic lands behind the same interface.
"""

from __future__ import annotations

from pydantic import BaseModel

from graph_agent.core.schema_engine import (
    SchemaEngine,
    SchemaObject,
    ValidationResult,
)


class TestSchemaEngineInit:
    def test_schema_engine_init(self) -> None:
        engine = SchemaEngine()
        assert isinstance(engine, SchemaEngine)
        # Per-instance cache starts empty (no singleton, MVP-2 research D1).
        assert engine._pydantic_model_cache == {}


class TestSchemaObject:
    def test_schema_object_has_default_fields(self) -> None:
        obj = SchemaObject(raw={"foo": "bar"}, fields={"foo": str})

        assert obj.raw == {"foo": "bar"}
        assert obj.fields == {"foo": str}
        assert obj.field_descriptions == {}
        assert obj.required_fields == []
        assert obj.schema_version is None
        assert obj.skill_id is None


class TestParseFromMd:
    def test_parse_from_md_returns_schema_object(self) -> None:
        engine = SchemaEngine()
        md = "## output_schema\nfoo: str\nbar: int\n"

        result = engine.parse_from_md(md)

        # T1 stub returns empty SchemaObject; T3 will populate.
        assert isinstance(result, SchemaObject)
        assert result.raw == {}
        assert result.fields == {}

    def test_parse_from_md_handles_empty_input(self) -> None:
        engine = SchemaEngine()

        result = engine.parse_from_md("")

        assert isinstance(result, SchemaObject)
        assert result.raw == {}


class TestGetPydanticModel:
    def test_get_pydantic_model_returns_basemodel_subclass(self) -> None:
        engine = SchemaEngine()
        schema = SchemaObject(raw={}, fields={})

        model_cls = engine.get_pydantic_model(schema)

        assert isinstance(model_cls, type)
        assert issubclass(model_cls, BaseModel)
        # T1 stub allows extra fields so callers can attach business data.
        instance = model_cls.model_validate({"any_field": 123})
        assert instance.model_dump() == {"any_field": 123}

    def test_get_pydantic_model_caches_result(self) -> None:
        engine = SchemaEngine()
        schema = SchemaObject(raw={}, fields={})

        first = engine.get_pydantic_model(schema)
        second = engine.get_pydantic_model(schema)

        # Same SchemaObject identity → same class object returned.
        assert first is second

    def test_get_pydantic_model_distinct_schemas_get_distinct_classes(self) -> None:
        engine = SchemaEngine()
        schema_a = SchemaObject(raw={}, fields={})
        schema_b = SchemaObject(raw={}, fields={})

        model_a = engine.get_pydantic_model(schema_a)
        model_b = engine.get_pydantic_model(schema_b)

        # Different SchemaObject instances → different cached class objects.
        assert model_a is not model_b


class TestValidate:
    def test_validate_returns_validation_result(self) -> None:
        engine = SchemaEngine()
        schema = SchemaObject(raw={}, fields={})

        result = engine.validate({"foo": "bar"}, schema)

        assert isinstance(result, ValidationResult)

    def test_validate_passes_for_t1_stub(self) -> None:
        engine = SchemaEngine()
        schema = SchemaObject(raw={}, fields={})

        # T1 stub always passes. T3 will run real Pydantic validation.
        result = engine.validate({"anything": "goes"}, schema)

        assert result.passed is True
        assert result.errors == []
        assert result.warnings == []
        assert result.field_errors == {}


class TestGetJsonSchema:
    def test_get_json_schema_returns_dict(self) -> None:
        engine = SchemaEngine()
        schema = SchemaObject(raw={"type": "object"}, fields={})

        result = engine.get_json_schema(schema)

        assert isinstance(result, dict)
        assert result == {"type": "object"}

    def test_get_json_schema_returns_independent_copy(self) -> None:
        engine = SchemaEngine()
        original = {"type": "object"}
        schema = SchemaObject(raw=original, fields={})

        result = engine.get_json_schema(schema)
        result["mutated"] = True

        # T1 stub copies raw, callers may mutate without affecting source.
        assert "mutated" not in schema.raw
