"""Static semantic validator: DelegatePhase.context_bridge ↔ child io.

See docs/superpowers/plans/2026-04-25-pr7-context-bridge-validator.md for
the full rule catalogue and rationale.
"""
from __future__ import annotations

from pathlib import Path

from pydantic import TypeAdapter, ValidationError

from ..compiler import CompileIssue
from ..exceptions import SkillLoadError
from ..manifest import GraphSkillDef, SkillManifest
from ..parser import parse_skill_file


def check_context_bridge(
    parent: GraphSkillDef,
    *,
    base_dir: Path,
) -> list[CompileIssue]:
    """Run the context_bridge static type check on every DelegatePhase.

    For each ``DelegatePhase`` in ``parent.phases``, resolve the child
    SKILL.md relative to ``base_dir``, parse its frontmatter, validate
    against ``SkillManifest``, and compare the bridge's child-side names
    against the child's ``io.inputs`` / ``io.outputs`` declarations.
    Returns an empty list on full pass; otherwise one ``CompileIssue``
    per mismatch. Does not raise — every error becomes an issue so
    callers (compile_skill, Studio) can aggregate diagnostics.
    """
    issues: list[CompileIssue] = []
    for phase in parent.phases:
        if phase.mode != "delegate":  # type: ignore[attr-defined]
            continue
        # phase is DelegatePhase here.
        child_path = (base_dir / phase.subgraph).resolve()  # type: ignore[attr-defined]
        try:
            parsed = parse_skill_file(child_path)
        except SkillLoadError as exc:
            issues.append(CompileIssue(
                rule_id="F-context-bridge-child-invalid",
                severity="FATAL",
                location=f"{child_path}:frontmatter",
                message=str(exc),
            ))
            continue
        # parse_skill_file returns {"frontmatter": dict, "human_body": str};
        # only the frontmatter is what SkillManifest validates.
        child_raw = parsed["frontmatter"]
        try:
            child_manifest = TypeAdapter(SkillManifest).validate_python(child_raw)
        except ValidationError as exc:
            issues.append(CompileIssue(
                rule_id="F-context-bridge-child-invalid",
                severity="FATAL",
                location=f"{child_path}:frontmatter",
                message=str(exc),
            ))
            continue
        if child_manifest.type != "graph":
            # Handled in later tasks (agent → WARNING, persona → FATAL)
            continue
        declared_inputs = {io.name for io in child_manifest.io.inputs}
        declared_outputs = {io.name for io in child_manifest.io.outputs}
        bridge = phase.context_bridge  # type: ignore[attr-defined]
        for parent_key, child_input in bridge.inputs.items():
            if child_input not in declared_inputs:
                issues.append(CompileIssue(
                    rule_id="F-context-bridge-input-undeclared",
                    severity="FATAL",
                    location=f"SKILL.md:phases.{phase.name}.context_bridge.inputs.{parent_key}",
                    message=(
                        f"DelegatePhase '{phase.name}' wires parent context "
                        f"'{parent_key}' to child input '{child_input}', but "
                        f"{child_path.name} declares no io.input named "
                        f"'{child_input}'. Declared: {sorted(declared_inputs) or '[]'}."
                    ),
                ))
        for child_key, parent_key in bridge.outputs.items():
            if child_key not in declared_outputs:
                issues.append(CompileIssue(
                    rule_id="F-context-bridge-output-undeclared",
                    severity="FATAL",
                    location=f"SKILL.md:phases.{phase.name}.context_bridge.outputs.{child_key}",
                    message=(
                        f"DelegatePhase '{phase.name}' reads child output "
                        f"'{child_key}' (mapping to parent '{parent_key}'), but "
                        f"{child_path.name} declares no io.output named "
                        f"'{child_key}'. Declared: {sorted(declared_outputs) or '[]'}."
                    ),
                ))
    return issues
