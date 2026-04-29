"""Phase 2 raw manifest validation for the loader pipeline."""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING, Any, cast

from .exceptions import SkillCompilationError
from .schema_engine import SchemaEngine

if TYPE_CHECKING:
    from .io_manager import IODef, IOManager
    from .manifest import SkillManifest as SkillManifestType


def validate_manifest(
    raw: dict[str, Any],
    schema_engine: SchemaEngine,
    io_manager_factory: Callable[[list[IODef]], IOManager],
) -> SkillManifestType:
    """Phase 2: raw dict to typed manifest plus compiled schema cache."""
    from pydantic import TypeAdapter, ValidationError

    from .io_manager import IODef
    from .manifest import GraphSkillDef, LLMPhase, SkillManifest
    from .schema_engine import SchemaObject, SchemaParseError

    _validate_raw_manifest_spec(raw, schema_engine)

    try:
        manifest: SkillManifestType = TypeAdapter(SkillManifest).validate_python(raw)
    except ValidationError as exc:
        raise SkillCompilationError(f"SkillManifest validation failed: {exc}") from exc

    if not isinstance(manifest, GraphSkillDef):
        manifest.compiled_schemas = {}
        return manifest

    compiled: dict[str, SchemaObject] = {}
    try:
        for phase in manifest.phases:
            if not isinstance(phase, LLMPhase):
                continue
            schema_text = phase.output_schema_md or phase.output_example_md
            if schema_text:
                compiled[phase.name] = schema_engine.parse_from_md(schema_text)
    except SchemaParseError as exc:
        rule = (
            "[F-output-example-invalid]" if "output_example" in str(exc) else "[F-schema-invalid]"
        )
        raise SkillCompilationError(f"{rule} SchemaEngine validation failed: {exc}") from exc

    manifest.compiled_schemas = compiled
    _validate_io_specs(manifest, io_manager_factory, IODef)
    return manifest


def _validate_raw_manifest_spec(
    raw: dict[str, Any],
    schema_engine: SchemaEngine,
) -> None:
    validator = getattr(schema_engine, "validate_spec_dict", None)
    if validator is None:
        return
    if not callable(validator):
        raise SkillCompilationError(
            "[F-manifest-spec-invalid] SchemaEngine.validate_spec_dict is not callable"
        )

    ok, errors = cast(
        Callable[[dict[str, Any]], tuple[bool, list[str]]],
        validator,
    )(raw)
    if ok:
        return

    message = "; ".join(str(error) for error in errors) or "manifest spec invalid"
    raise SkillCompilationError(f"[F-manifest-spec-invalid] {message}")


def _validate_io_specs(
    manifest: Any,
    io_manager_factory: Callable[[list[IODef]], IOManager],
    io_def_cls: type[IODef],
) -> None:
    io_specs = _manifest_io_specs(manifest, io_def_cls)
    io_manager = io_manager_factory(io_specs)
    errors: list[str] = []
    for spec in io_specs:
        ok, spec_errors = io_manager.validate_spec(
            {
                "source_field": spec.source_field,
                "target_field": spec.target_field,
                "hoist_path": spec.hoist_path,
                "required": spec.required,
            }
        )
        if not ok:
            errors.extend(spec_errors)
    if errors:
        raise SkillCompilationError("[F-io-spec-invalid] " + "; ".join(errors))


def _manifest_io_specs(manifest: Any, io_def_cls: type[IODef]) -> list[IODef]:
    from .manifest import LLMPhase

    specs: list[Any] = []
    for output in manifest.io.outputs:
        specs.append(
            io_def_cls(
                source_field=output.name,
                target_field=output.name,
                hoist_path=output.path,
                required=True,
            )
        )
    for phase in manifest.phases:
        if isinstance(phase, LLMPhase) and phase.hoist_to:
            specs.append(
                io_def_cls(
                    source_field="business_data_parsed",
                    target_field=phase.hoist_to,
                    required=True,
                )
            )
    return specs


__all__ = ["validate_manifest"]
