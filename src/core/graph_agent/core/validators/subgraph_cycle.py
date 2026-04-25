"""Static semantic validator: DelegatePhase.subgraph cycle detection.

See docs/superpowers/plans/2026-04-25-pr7-subgraph-cycle-validator.md for
the full rule catalogue and rationale.
"""
from __future__ import annotations

from pathlib import Path

from pydantic import TypeAdapter, ValidationError

from ..compiler import CompileIssue
from ..exceptions import SkillLoadError
from ..manifest import (
    DelegatePhase,
    GraphSkillDef,
    SkillManifest,
)
from ..parser import parse_skill_file


def check_subgraph_cycles(
    parent: GraphSkillDef,
    *,
    skill_path: Path,
) -> list[CompileIssue]:
    """DFS-walk subgraph references and emit F-subgraph-cycle on revisits.

    ``skill_path`` is the absolute path of ``parent``'s SKILL.md — it seeds
    the walk stack so a self-cycle (``subgraph: ./SKILL.md``) is detected.
    The base directory for resolving each ``phase.subgraph`` string is
    derived recursively as ``current_skill_path.parent`` for that level.
    Returns an empty list on no cycles. Does not raise; missing/invalid
    children silently skip (``check_context_bridge`` owns those reports).
    """
    issues: list[CompileIssue] = []
    parent_resolved = skill_path.resolve()
    _walk(
        skill_def=parent,
        skill_path=parent_resolved,
        path_stack=[parent_resolved],
        cycle_reported=set(),
        issues=issues,
    )
    return issues


def _walk(
    *,
    skill_def: GraphSkillDef,
    skill_path: Path,
    path_stack: list[Path],
    cycle_reported: set[Path],
    issues: list[CompileIssue],
) -> None:
    base_dir = skill_path.parent
    for phase in skill_def.phases:
        if not isinstance(phase, DelegatePhase):
            continue
        child_resolved = (base_dir / phase.subgraph).resolve()
        if child_resolved in path_stack:
            if child_resolved in cycle_reported:
                continue
            cycle_reported.add(child_resolved)
            cycle_start = path_stack.index(child_resolved)
            chain = [*path_stack[cycle_start:], child_resolved]
            chain_str = " -> ".join(str(p) for p in chain)
            issues.append(CompileIssue(
                rule_id="F-subgraph-cycle",
                severity="FATAL",
                location=f"SKILL.md:phases.{phase.name}.subgraph",
                message=(
                    f"Cyclic subgraph reference detected from phase "
                    f"'{phase.name}': {chain_str}"
                ),
            ))
            continue
        if not child_resolved.is_file():
            # context_bridge validator owns child-missing
            continue
        try:
            child_raw = parse_skill_file(child_resolved)["frontmatter"]
            child_manifest = TypeAdapter(SkillManifest).validate_python(child_raw)
        except (SkillLoadError, ValidationError):
            # context_bridge validator owns child-invalid
            continue
        if not isinstance(child_manifest, GraphSkillDef):
            # agent / persona have no phases — no cycle possible
            continue
        _walk(
            skill_def=child_manifest,
            skill_path=child_resolved,
            path_stack=[*path_stack, child_resolved],
            cycle_reported=cycle_reported,
            issues=issues,
        )
