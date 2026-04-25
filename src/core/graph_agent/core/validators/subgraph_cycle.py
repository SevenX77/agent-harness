"""Static semantic validator: DelegatePhase.subgraph cycle detection.

See docs/superpowers/plans/2026-04-25-pr7-subgraph-cycle-validator.md for
the full rule catalogue and rationale.
"""
from __future__ import annotations

from pathlib import Path

from ..compiler import CompileIssue
from ..manifest import GraphSkillDef


def check_subgraph_cycles(
    parent: GraphSkillDef,
    *,
    skill_path: Path,
) -> list[CompileIssue]:
    """DFS-walk subgraph references and emit F-subgraph-cycle on revisits."""
    raise NotImplementedError("filled in by Task 2 onward")
