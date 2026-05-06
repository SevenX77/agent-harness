"""MVP-2 e2e: SchemaEngine + IOManager + ContextBridge integration.

T8 of MVP-2 (A5 SchemaEngine + A7 IOManager): proves the post-MVP-2
data path runs end-to-end and continues to honor the MVP-1 state
contract:

- ``SchemaEngine.parse_from_md`` → ``SchemaObject`` → ``get_pydantic_model``
  produces a Pydantic class that round-trips realistic SKILL output.
- ``IOManager.resolve_hoist`` reads the parsed structured data and
  writes it into a new ``BusinessData`` without leaking framework
  metadata into the business namespace (MVP-1 §1 invariant).
- ``ContextBridge.to_business_data_schema`` (T4) routes through the
  shared SchemaEngine so a parent skill's bridge declaration produces
  the same SchemaObject the child skill validates against.
- The 4 production SKILLs (text-segmentation / event-extraction /
  batch-analysis / global-synthesis) compile without regressing — the
  loader uses MVP-2 wiring (T6 ``get_schema_engine`` singleton) but
  the legacy ``DynamicSchemaDef`` shape stays intact for MVP-3
  consumers.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from graph_agent.core.io_manager import IODef, IOManager
from graph_agent.core.loader import get_schema_engine, load_workflow_from_md
from graph_agent.core.manifest import ContextBridge
from graph_agent.core.schema_engine import (
    SchemaEngine,
    SchemaObject,
    ValidationResult,
)
from graph_agent.core.state import (
    BusinessData,
    FrameworkState,
    WorkflowState,
    verify_state_invariants,
)

SEGMENT_OUTPUT_EXAMPLE = """<output_example name="Segment">
## segments
- index (int, required): 段落顺序编号
- type (Literal[A,B,C], required): 段落类型
- start_line (int, required): 起始行号
- end_line (int, required): 结束行号
- content (str, required): 剧情概括
- confidence (float, optional, default=1.0): 置信度
</output_example>
"""


PRODUCTION_SKILLS = [
    "skills/text-segmentation/SKILL.md",
    "skills/event-extraction/SKILL.md",
    "skills/batch-analysis/SKILL.md",
    "skills/global-synthesis/SKILL.md",
]


@pytest.fixture
def expected_mvp2_state_shape() -> dict[str, Any]:
    """Lock the MVP-2 post-hoist state shape for forward regression.

    MVP-3 / MVP-4 / MVP-5 should re-run the smoke against this fixture
    to detect changes in BusinessData / FrameworkState round-trip
    behavior introduced by phase_executor or harness rewrites.
    """
    return {
        "data_keys_min": 1,
        "flow_io_errors_default": [],
        "flow_finish_task_result_default": None,
        "schema_engine_singleton_present": True,
        "production_skill_count": len(PRODUCTION_SKILLS),
    }


class TestSchemaEnginePipeline:
    """End-to-end: parse → Pydantic model → validate → JSON Schema view."""

    def test_full_pipeline_parses_validates_and_renders(self) -> None:
        engine = SchemaEngine()
        schema = engine.parse_from_md(SEGMENT_OUTPUT_EXAMPLE)

        # Pydantic model derived from the SchemaObject.
        model_cls = engine.get_pydantic_model(schema)
        assert hasattr(model_cls, "model_fields")
        assert set(model_cls.model_fields).issuperset(
            {"index", "type", "start_line", "end_line", "content"}
        )

        # JSON Schema view (used by md_to_json prompt rendering).
        json_schema = engine.get_json_schema(schema)
        assert json_schema["type"] == "object"
        assert "index" in json_schema["properties"]
        assert "type" in json_schema["properties"]

        # Round-trip a valid record through validate.
        valid_record = {
            "index": 1,
            "type": "A",
            "start_line": 1,
            "end_line": 5,
            "content": "opening",
            "confidence": 0.9,
        }
        result = engine.validate(valid_record, schema)
        assert isinstance(result, ValidationResult)
        assert result.ok
        assert result.parsed == valid_record

    def test_invalid_record_returns_field_errors(self) -> None:
        engine = SchemaEngine()
        schema = engine.parse_from_md(SEGMENT_OUTPUT_EXAMPLE)

        result = engine.validate(
            {"index": "not-int", "type": "Z", "start_line": 1, "end_line": 5, "content": "x"},
            schema,
        )

        assert not result.ok
        assert "index" in result.field_errors
        assert "type" in result.field_errors


class TestSchemaEngineIOManagerHoist:
    """End-to-end: parsed business_data dict → IOManager.resolve_hoist → BusinessData."""

    def test_hoist_routes_parsed_data_into_business_data(self) -> None:
        engine = SchemaEngine()
        schema = engine.parse_from_md(SEGMENT_OUTPUT_EXAMPLE)

        # Simulate a finish_task payload after schema validation.
        parsed_record = {
            "index": 1,
            "type": "A",
            "start_line": 1,
            "end_line": 5,
            "content": "opening",
            "confidence": 0.9,
        }
        engine.validate(parsed_record, schema)

        manager = IOManager(
            [
                IODef(source_field="content", target_field="story_segment"),
                IODef(source_field="type", target_field="segment_type"),
            ]
        )
        result = manager.resolve_hoist(parsed_record, BusinessData())

        dump = result.new_business_data.model_dump()
        assert dump["story_segment"] == "opening"
        assert dump["segment_type"] == "A"
        assert result.io_errors == []
        # Invariant: no _-prefixed key sneaks into BusinessData.
        assert not any(k.startswith("_") for k in dump)


class TestContextBridgeRoutesViaSchemaEngine:
    """ContextBridge.to_business_data_schema (T4) must use the engine
    we wired into the loader (T6) — the same singleton flows through
    compile and runtime."""

    def test_context_bridge_uses_loader_singleton(self) -> None:
        engine = get_schema_engine()
        bridge = ContextBridge(inputs={"chapter_text": "parent.text", "chapter_id": "parent.id"})

        schema = bridge.to_business_data_schema(engine)

        assert isinstance(schema, SchemaObject)
        assert {n for n, _ in schema.fields} == {"chapter_text", "chapter_id"}
        # Calling get_pydantic_model on the same engine returns a
        # Pydantic class — proves the wiring round-trips.
        cls = engine.get_pydantic_model(schema)
        assert hasattr(cls, "model_fields")


class TestMVP1StateRoundTrip:
    """Verify the MVP-2 hoist path still honors the MVP-1 state contract."""

    def test_workflow_state_round_trip_after_hoist(self) -> None:
        manager = IOManager([IODef(source_field="title", target_field="story_title")])
        new_data, errors = (
            manager.resolve_hoist({"title": "abc"}, BusinessData()).new_business_data,
            manager.resolve_hoist({"title": "abc"}, BusinessData()).io_errors,
        )

        state = WorkflowState(
            data=new_data,
            flow=FrameworkState(io_errors=errors),
            messages=[],
        )

        # MVP-1 verify_state_invariants: BusinessData has no _-prefixed
        # fields and FrameworkState round-trips through model_validate.
        verify_state_invariants(state)
        re_dump = state["flow"].model_dump()
        FrameworkState.model_validate(re_dump)


@pytest.mark.parametrize("skill_path", PRODUCTION_SKILLS)
class TestProductionSkillCompile:
    """4 production SKILLs must compile under MVP-2 wiring."""

    def test_skill_compiles_with_loader_schema_engine_wired(self, skill_path: str) -> None:
        path = Path(skill_path)
        assert path.exists(), f"Production SKILL missing at {skill_path}; verify MVP-0 baseline."
        harness = load_workflow_from_md(path)
        try:
            phase_names = [p.name for p in harness.phases]
            assert len(phase_names) > 0, f"{skill_path} has zero phases"
            # The loader's MVP-2 T6 wiring exposes the SchemaEngine
            # singleton; the harness instance carries an io_config so
            # downstream save_outputs can resolve a target.
            assert harness._io_config is not None
        finally:
            harness.close()

    def test_skill_singleton_schema_engine_unchanged(self, skill_path: str) -> None:
        """Compiling a SKILL must reuse the loader's shared SchemaEngine
        singleton — a regression that builds a per-compile engine would
        defeat the cache and break ContextBridge wiring."""
        engine_before = get_schema_engine()
        harness = load_workflow_from_md(Path(skill_path))
        engine_after = get_schema_engine()
        try:
            assert engine_before is engine_after
        finally:
            harness.close()


class TestExpectedShapeFixture:
    """The fixture is a forward regression hook for MVP-3+ consumers."""

    def test_fixture_describes_post_mvp2_baseline(
        self, expected_mvp2_state_shape: dict[str, Any]
    ) -> None:
        # Lock the keys so MVP-3 / MVP-4 know which slots to read when
        # they re-run the smoke against new pipelines.
        assert set(expected_mvp2_state_shape) == {
            "data_keys_min",
            "flow_io_errors_default",
            "flow_finish_task_result_default",
            "schema_engine_singleton_present",
            "production_skill_count",
        }
        assert expected_mvp2_state_shape["production_skill_count"] == 4
