"""Static semantic validator: adopted_persona name resolution.

See docs/superpowers/plans/2026-04-25-pr7-persona-resolution-validator.md
for the full rule catalogue and rationale.
"""
from __future__ import annotations

from pathlib import Path

from ..compiler import CompileIssue
from ..exceptions import SkillLoadError
# Cross-module private import is intentional: keeps the walk-up
# resolver as a single source of truth between load-time and
# compile-time. See plan "Scope decisions". Promoting _resolve_persona
# to public is tracked separately in loader.py's TODO block.
from ..loader import _resolve_persona
from ..manifest import AgentSkillDef, GraphSkillDef, LLMPhase


def check_persona_resolution(
    manifest: AgentSkillDef | GraphSkillDef,
    *,
    base_dir: Path,
) -> list[CompileIssue]:
    """For each adopted_persona, confirm it resolves to a PersonaSkillDef.

    The single rule_id ``F-persona-not-resolved`` covers both failure
    modes the loader's resolver raises: name not found in any candidate
    path, and name resolves to a non-persona artifact (e.g. a graph
    skill staged under the same name). The PM-facing message includes
    the loader's verbatim error so the specific cause is visible
    without needing distinct rule_ids.
    """
    issues: list[CompileIssue] = []

    if isinstance(manifest, AgentSkillDef):
        if manifest.adopted_persona is not None:
            _check_one(
                manifest.adopted_persona,
                base_dir=base_dir,
                location="SKILL.md:adopted_persona",
                issues=issues,
            )
        return issues

    if isinstance(manifest, GraphSkillDef):
        for phase in manifest.phases:
            if not isinstance(phase, LLMPhase):
                continue
            if phase.adopted_persona is None:
                continue
            _check_one(
                phase.adopted_persona,
                base_dir=base_dir,
                location=f"SKILL.md:phases.{phase.name}.adopted_persona",
                issues=issues,
            )
    return issues


def _check_one(
    persona_name: str,
    *,
    base_dir: Path,
    location: str,
    issues: list[CompileIssue],
) -> None:
    try:
        _resolve_persona(persona_name, base_dir)
    except SkillLoadError as exc:
        issues.append(CompileIssue(
            rule_id="F-persona-not-resolved",
            severity="FATAL",
            location=location,
            message=str(exc),
        ))
