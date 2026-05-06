"""Template variable lifecycle validators."""

from __future__ import annotations

import re

from graph_agent.core.compiler import CompileIssue
from graph_agent.core.manifest import GraphSkillDef, LLMPhase

TEMPLATE_VAR_RE = re.compile(r"(?<!\{)\{(\w+)\}(?!\})")


def find_template_variables(template: str | None) -> set[str]:
    """Return unescaped ``{var}`` placeholders from a template string."""
    if not template:
        return set()
    return set(TEMPLATE_VAR_RE.findall(template))


def check_template_variables(manifest: GraphSkillDef) -> list[CompileIssue]:
    """Validate user_prompt_template variables against upstream producers."""
    issues: list[CompileIssue] = []
    available_vars: set[str] = set()

    for input_spec in manifest.io.inputs or []:
        available_vars.add(input_spec.name)
    available_vars.update((manifest.context_mapping or {}).keys())

    for phase in manifest.phases:
        if isinstance(phase, LLMPhase) and phase.user_prompt_template:
            for var in sorted(find_template_variables(phase.user_prompt_template)):
                if var in available_vars:
                    continue
                issues.append(
                    CompileIssue(
                        rule_id="F-TEMPLATE-VAR-UNDECLARED",
                        severity="FATAL",
                        location=f"SKILL.md:phases.{phase.name}.user_prompt_template",
                        message=(
                            f"Template variable '{{{var}}}' referenced in phase "
                            f"'{phase.name}' user_prompt_template, but no upstream "
                            f"producer found. Did you forget to set 'hoist_to: {var}' "
                            "on a prior phase, or declare it in io.inputs / "
                            "context_mapping?\n"
                            f"Available variables at this phase: {sorted(available_vars)}"
                        ),
                    )
                )

        if isinstance(phase, LLMPhase) and phase.hoist_to:
            available_vars.add(phase.hoist_to)

    return issues


__all__ = ["TEMPLATE_VAR_RE", "check_template_variables", "find_template_variables"]
