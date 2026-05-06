"""Compiler rule requiring validators for non-trivial output schemas."""

from __future__ import annotations

from typing import Literal

from graph_agent.tools.dynamic_schema import parse_output_example
from graph_agent.core.compiler import CompileIssue
from graph_agent.core.manifest import GraphSkillDef, LLMPhase


def check_validator_required(manifest: GraphSkillDef) -> list[CompileIssue]:
    """Enforce the business-validator gate for schema-bearing LLM phases."""
    issues: list[CompileIssue] = []

    for phase in manifest.phases:
        if not isinstance(phase, LLMPhase):
            continue
        if not (phase.output_schema or phase.output_example):
            continue
        if phase.validator or phase.validator_optional:
            continue

        complexity = _assess_schema_complexity(phase)
        if complexity == "complex":
            issues.append(
                CompileIssue(
                    rule_id="F-VALIDATOR-MISSING-FOR-COMPLEX-SCHEMA",
                    severity="FATAL",
                    location=f"SKILL.md:phases.{phase.name}",
                    message=(
                        f"Phase '{phase.name}' declares output_schema/output_example "
                        "with interdependent numeric/relational fields, but no "
                        "business validator is configured. Pydantic or dynamic "
                        "schema checks cannot catch cross-field invariants such "
                        "as start_line <= end_line or line coverage continuity. "
                        "Add 'validator: <module.fn>' or explicitly set "
                        "'validator_optional: true' to silence this after review."
                    ),
                )
            )
        else:
            issues.append(
                CompileIssue(
                    rule_id="W-VALIDATOR-MISSING",
                    severity="WARNING",
                    location=f"SKILL.md:phases.{phase.name}",
                    message=(
                        f"Phase '{phase.name}' declares output_schema/output_example "
                        "but no business validator. This is allowed for simple "
                        "schemas, but downstream consumers will trust the result "
                        "without business-rule verification. Add "
                        "'validator: <module.fn>' or 'validator_optional: true' "
                        "to silence."
                    ),
                )
            )

    return issues


def _assess_schema_complexity(phase: LLMPhase) -> Literal["simple", "complex"]:
    """Heuristic complexity check for output schema declarations."""
    if phase.output_example:
        try:
            schema_def = parse_output_example(phase.output_example)
        except Exception:  # noqa: BLE001
            return "simple"

        numeric_count = sum(1 for field in schema_def.fields if field.type_hint in ("int", "float"))
        relational_count = sum(1 for field in schema_def.fields if _looks_relational(field.name))
        if numeric_count >= 2 or relational_count >= 1:
            return "complex"
    return "simple"


def _looks_relational(field_name: str) -> bool:
    return field_name.startswith(("start_", "end_")) or field_name.endswith(
        ("_index", "_count", "_offset")
    )


__all__ = ["check_validator_required"]
