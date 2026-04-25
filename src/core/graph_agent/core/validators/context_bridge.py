"""Static semantic validator: DelegatePhase.context_bridge ↔ child io.

See docs/superpowers/plans/2026-04-25-pr7-context-bridge-validator.md for
the full rule catalogue and rationale.
"""
from __future__ import annotations

from pathlib import Path

from ..compiler import CompileIssue
from ..manifest import GraphSkillDef


def check_context_bridge(
    parent: GraphSkillDef,
    *,
    base_dir: Path,
) -> list[CompileIssue]:
    """Run the context_bridge static type check on every DelegatePhase."""
    raise NotImplementedError("filled in by Task 2 onward")
