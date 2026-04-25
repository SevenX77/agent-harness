"""Static semantic validator: adopted_persona name resolution.

See docs/superpowers/plans/2026-04-25-pr7-persona-resolution-validator.md
for the full rule catalogue and rationale.
"""
from __future__ import annotations

from pathlib import Path

from ..compiler import CompileIssue
from ..manifest import AgentSkillDef, GraphSkillDef


def check_persona_resolution(
    manifest: AgentSkillDef | GraphSkillDef,
    *,
    base_dir: Path,
) -> list[CompileIssue]:
    """For each adopted_persona, confirm it resolves to a PersonaSkillDef."""
    raise NotImplementedError("filled in by Task 2 onward")
