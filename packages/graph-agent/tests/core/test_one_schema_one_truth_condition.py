"""One io.outputs schema has ONE truth condition across every checkpoint.

The engine already ruled that an OPTIONAL field is nullable: the finish gate's
Pydantic projection gives every non-required field the annotation ``T | None``
through the deliberately named ``_optional_annotation`` (schema_engine).
The state mapper then validated the SAME accepted payload against the RAW JSON
schema with ``Draft202012Validator``, where ``{type: string}`` rejects null —
so a submission the gate accepted was killed one step later.

Field evidence (run 2026-08-19T05-21-45_3aca03a5, skill
story-deconstruction-v3-lab): phase `foreshadow` got
"Accepted the finish_task submission ... passed schema and business
validation", `phase_end` fired, and the run then died fatal with
`[F-v3-runtime-state-mapping-failed] phase output schema validation failed:
None is not of type 'string'` on `foreshadow_results.0.resolves_foreshadowing_id`
— an optional field carrying the null the gate had just allowed.

Second half: declaring the nullability EXPLICITLY, the JSON-Schema-standard way
(`type: [string, "null"]`), did not work either — the compiler accepted it and
materialization then died with `SchemaParseError: List schema shorthand must
contain exactly one item type` (surfaced as `engine.unexpected_error` from
predict, run predict-2026-08-19T05-40-31_498a3bfe): `_descriptor_from_json_mapping`
never handled a JSON Schema type ARRAY, and the list fell through to the
list-shorthand branch.
"""

from __future__ import annotations

from typing import Any

import pytest
from pydantic import ValidationError

from graph_agent.core.exceptions import GraphAgentFatalError
from graph_agent.core.schema_engine import (
    SchemaEngine,
    SchemaObject,
    _canonical_key,
    _schema_from_mapping,
)
from graph_agent.runtime.state_mapper import _validate_phase_updates_against_schema


def _model_for(json_schema: dict[str, Any]):
    engine = SchemaEngine()
    return engine.get_pydantic_model(_schema_from_mapping(json_schema))


NULLABLE_UNION_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": ["event_id"],
    "properties": {
        "event_id": {"type": "string"},
        "resolves_foreshadowing_id": {"type": ["string", "null"]},
    },
}


class TestJsonSchemaTypeArray:
    def test_a_type_array_with_null_materializes_and_accepts_null(self) -> None:
        model = _model_for(NULLABLE_UNION_SCHEMA)

        parsed = model.model_validate(
            {"event_id": "E1", "resolves_foreshadowing_id": None}
        )
        assert parsed.resolves_foreshadowing_id is None  # type: ignore[attr-defined]

        parsed2 = model.model_validate(
            {"event_id": "E1", "resolves_foreshadowing_id": "F1"}
        )
        assert parsed2.resolves_foreshadowing_id == "F1"  # type: ignore[attr-defined]

    def test_a_type_array_still_rejects_other_types(self) -> None:
        model = _model_for(NULLABLE_UNION_SCHEMA)

        with pytest.raises(ValidationError):
            model.model_validate({"event_id": "E1", "resolves_foreshadowing_id": 7})

    def test_a_multi_type_array_is_a_union(self) -> None:
        model = _model_for(
            {
                "type": "object",
                "required": ["value"],
                "properties": {"value": {"type": ["string", "integer"]}},
            }
        )
        assert model.model_validate({"value": "x"}).value == "x"  # type: ignore[attr-defined]
        assert model.model_validate({"value": 3}).value == 3  # type: ignore[attr-defined]
        with pytest.raises(ValidationError):
            model.model_validate({"value": 1.5})

    def test_type_array_descriptor_key_is_deterministic(self) -> None:
        # The canonical key must not fall back to an address-bearing repr.
        schema = SchemaObject(
            fields=(("value", str | None),),
            required_fields=frozenset({"value"}),
            schema_name="U",
        )
        key = _canonical_key(schema)
        assert "0x" not in key, key


class TestMapperSharesTheGateTruthCondition:
    def test_null_in_an_optional_plain_typed_field_passes_the_mapper(self) -> None:
        """The exact shape that killed run 2026-08-19T05-21-45_3aca03a5."""
        schema = {
            "type": "object",
            "required": ["foreshadow_results"],
            "properties": {
                "foreshadow_results": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "required": ["event_id"],
                        "properties": {
                            "event_id": {"type": "string"},
                            "resolves_foreshadowing_id": {"type": "string"},
                        },
                    },
                }
            },
        }
        updates = {
            "foreshadow_results": [
                {"event_id": "E1", "resolves_foreshadowing_id": None}
            ]
        }

        # Must not raise: the gate accepted this payload, so the mapper must too.
        _validate_phase_updates_against_schema(
            updates, schema, code="[F-v3-runtime-state-mapping-failed]", phase_id="foreshadow"
        )

    def test_null_in_a_required_plain_typed_field_still_fails(self) -> None:
        """Required fields keep their strictness — the gate rejects null there
        too (no `_optional_annotation`), so the truth conditions still match."""
        schema = {
            "type": "object",
            "required": ["event_id"],
            "properties": {"event_id": {"type": "string"}},
        }

        with pytest.raises(GraphAgentFatalError):
            _validate_phase_updates_against_schema(
                {"event_id": None},
                schema,
                code="[F-v3-runtime-state-mapping-failed]",
                phase_id="p",
            )

    def test_wrong_type_in_an_optional_field_still_fails(self) -> None:
        """Optional means MAY BE ABSENT OR NULL — not anything-goes."""
        schema = {
            "type": "object",
            "required": [],
            "properties": {"note": {"type": "string"}},
        }

        with pytest.raises(GraphAgentFatalError):
            _validate_phase_updates_against_schema(
                {"note": 42},
                schema,
                code="[F-v3-runtime-state-mapping-failed]",
                phase_id="p",
            )
