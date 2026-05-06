"""MVP-3 T4 validate_manifest integration tests."""

from __future__ import annotations

from typing import Any

import pytest
from graph_agent.core.exceptions import SkillCompilationError, SkillCompileError
from graph_agent.core.io_manager import IOManager
from graph_agent.core.loader import parse_skill_md, validate_manifest
from graph_agent.core.manifest import GraphSkillDef
from graph_agent.core.schema_engine import SchemaEngine, SchemaObject


def _graph_skill_yaml(phase_yaml: str) -> str:
    return (
        "---\n"
        'schema_version: "2.0"\n'
        "name: graph\n"
        "description: test graph\n"
        "type: graph\n"
        "io: {inputs: [], outputs: []}\n"
        "phases:\n"
        f"{phase_yaml}"
        "---\n"
    )


class RecordingSchemaEngine(SchemaEngine):
    def __init__(
        self,
        *,
        spec_ok: bool = True,
        spec_errors: list[str] | None = None,
    ) -> None:
        super().__init__()
        self.spec_ok = spec_ok
        self.spec_errors = spec_errors or []
        self.validated_specs: list[dict[str, Any]] = []
        self.parsed_fragments: list[str] = []

    def validate_spec_dict(self, spec: dict[str, Any]) -> tuple[bool, list[str]]:
        self.validated_specs.append(spec)
        return self.spec_ok, self.spec_errors

    def parse_from_md(self, md_content: str) -> SchemaObject:
        self.parsed_fragments.append(md_content)
        return super().parse_from_md(md_content)


def test_validate_manifest_calls_schema_engine_spec_validator() -> None:
    raw = parse_skill_md(
        _graph_skill_yaml(
            "  - name: draft\n"
            "    mode: llm\n"
            "    output_schema: |\n"
            "      title: str\n"
        )
    )
    engine = RecordingSchemaEngine()

    manifest = validate_manifest(raw, engine, lambda specs: IOManager(specs))

    assert isinstance(manifest, GraphSkillDef)
    assert engine.validated_specs == [raw]


def test_validate_manifest_rejects_schema_engine_spec_errors() -> None:
    raw = parse_skill_md(
        _graph_skill_yaml(
            "  - name: draft\n"
            "    mode: llm\n"
            "    output_schema: |\n"
            "      title: str\n"
        )
    )
    engine = RecordingSchemaEngine(
        spec_ok=False,
        spec_errors=["phase draft has invalid schema declaration"],
    )

    with pytest.raises(SkillCompilationError, match="F-manifest-spec-invalid"):
        validate_manifest(raw, engine, lambda specs: IOManager(specs))

    assert engine.parsed_fragments == []


def test_validate_manifest_compiles_output_schema_md_to_schema_object() -> None:
    raw = parse_skill_md(
        _graph_skill_yaml(
            "  - name: draft\n"
            "    mode: llm\n"
            "    output_schema: |\n"
            "      title: str\n"
            "      score: int\n"
        )
    )
    engine = RecordingSchemaEngine()

    manifest = validate_manifest(raw, engine, lambda specs: IOManager(specs))
    schema = manifest.compiled_schemas["draft"]

    assert isinstance(schema, SchemaObject)
    assert schema.field_map == {"title": str, "score": int}
    assert engine.parsed_fragments == ["title: str\nscore: int"]


def test_validate_manifest_compiles_output_example_md_to_schema_object() -> None:
    example = (
        '<output_example name="Item">\n'
        "## items\n"
        "- title (str, required): item title\n"
        "</output_example>"
    )
    raw = parse_skill_md(
        _graph_skill_yaml(
            "  - name: draft\n"
            "    mode: llm\n"
            "    output_example: |\n"
            f"      {example.replace(chr(10), chr(10) + '      ')}\n"
        )
    )
    engine = RecordingSchemaEngine()

    manifest = validate_manifest(raw, engine, lambda specs: IOManager(specs))
    schema = manifest.compiled_schemas["draft"]

    assert schema.schema_name == "Item"
    assert schema.item_header == "items"
    assert schema.output_example_md == example
    assert engine.parsed_fragments == [example]


def test_validate_manifest_leaves_dotted_output_schema_for_build_phase() -> None:
    raw = parse_skill_md(
        _graph_skill_yaml(
            "  - name: draft\n"
            "    mode: llm\n"
            "    output_schema: script.models.Result\n"
        )
    )
    engine = RecordingSchemaEngine()

    manifest = validate_manifest(raw, engine, lambda specs: IOManager(specs))

    assert manifest.compiled_schemas == {}
    assert engine.parsed_fragments == []


def test_validate_manifest_rejects_io_manager_errors() -> None:
    raw = parse_skill_md(
        _graph_skill_yaml(
            "  - name: draft\n"
            "    mode: llm\n"
            "    hoist_to: _private\n"
        )
    )
    engine = RecordingSchemaEngine()

    with pytest.raises(SkillCompilationError, match="F-io-spec-invalid"):
        validate_manifest(raw, engine, lambda specs: IOManager(specs))


def test_validate_manifest_rejects_validator_without_output_schema() -> None:
    """Phase 2 A1 contract: an LLMPhase that mounts a `validator` must also
    declare a structured output. Pre-A1 SKILLs would silently fall through
    to the legacy parallel pipeline running the validator on the raw legacy ctx.
    """
    raw = parse_skill_md(
        _graph_skill_yaml(
            "  - name: draft\n"
            "    mode: llm\n"
            "    validator: script.validators.check_business\n"
        )
    )
    engine = RecordingSchemaEngine()

    with pytest.raises(SkillCompileError, match="F-validator-without-schema"):
        validate_manifest(raw, engine, lambda specs: IOManager(specs))


def test_validate_manifest_accepts_validator_with_output_schema() -> None:
    raw = parse_skill_md(
        _graph_skill_yaml(
            "  - name: draft\n"
            "    mode: llm\n"
            "    validator: script.validators.check_business\n"
            "    output_schema: |\n"
            "      title: str\n"
        )
    )
    engine = RecordingSchemaEngine()

    manifest = validate_manifest(raw, engine, lambda specs: IOManager(specs))

    assert isinstance(manifest, GraphSkillDef)


def test_validate_manifest_accepts_validator_with_output_example() -> None:
    example = (
        '<output_example name="Item">\n'
        "## items\n"
        "- title (str, required): item title\n"
        "</output_example>"
    )
    raw = parse_skill_md(
        _graph_skill_yaml(
            "  - name: draft\n"
            "    mode: llm\n"
            "    validator: script.validators.check_business\n"
            "    output_example: |\n"
            f"      {example.replace(chr(10), chr(10) + '      ')}\n"
        )
    )
    engine = RecordingSchemaEngine()

    manifest = validate_manifest(raw, engine, lambda specs: IOManager(specs))

    assert isinstance(manifest, GraphSkillDef)


def test_validate_manifest_accepts_logic_phase_validator_without_output_schema() -> None:
    """LogicPhase has no output_schema field — its validator runs on the
    deterministic Python output, so the A1 contract intentionally exempts it.
    """
    raw = parse_skill_md(
        _graph_skill_yaml(
            "  - name: ingest\n"
            "    mode: logic\n"
            "    execute_steps:\n"
            "      - script.steps.run_ingest\n"
            "    validator: script.validators.check_ingest\n"
        )
    )
    engine = RecordingSchemaEngine()

    manifest = validate_manifest(raw, engine, lambda specs: IOManager(specs))

    assert isinstance(manifest, GraphSkillDef)
