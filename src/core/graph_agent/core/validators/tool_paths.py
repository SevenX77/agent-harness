"""Static semantic validator: tool-path dot-reference resolvability.

See docs/superpowers/plans/2026-04-25-pr7-tool-paths-validator.md.

The validator does NOT execute user code. ``loader._resolve_tool_reference``
runs ``exec(code, module.__dict__)`` to resolve tool refs at runtime;
that is acceptable on a real load but a side-effect risk during Studio
"save validate". Compile-time static check is limited to:

  - file existence under base_dir for relative refs
  - ``importlib.util.find_spec`` for ``builtin.*`` refs (no execution)

Function-symbol verification (``module.func`` actually defines a callable
named ``func``) stays at load time — covering it statically would require
either AST-parsing (brittle on decorators / dynamic defs) or executing
the module (defeats the no-side-effect invariant).
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

from ..compiler import CompileIssue
from ..manifest import (
    AgentSkillDef,
    GraphSkillDef,
    LLMPhase,
    LogicPhase,
)


def check_tool_paths(
    manifest: AgentSkillDef | GraphSkillDef,
    *,
    base_dir: Path,
) -> list[CompileIssue]:
    """Verify every tool-reference dot-path locates a real Python module."""
    issues: list[CompileIssue] = []

    if isinstance(manifest, AgentSkillDef):
        for idx, ref in enumerate(manifest.agent_tools):
            _check_one(
                ref,
                location=f"SKILL.md:agent_tools.{idx}",
                base_dir=base_dir,
                issues=issues,
            )
        return issues

    if isinstance(manifest, GraphSkillDef):
        for phase in manifest.phases:
            if isinstance(phase, LLMPhase):
                for idx, ref in enumerate(phase.agent_tools):
                    _check_one(
                        ref,
                        location=f"SKILL.md:phases.{phase.name}.agent_tools.{idx}",
                        base_dir=base_dir,
                        issues=issues,
                    )
                if phase.validator is not None:
                    _check_one(
                        phase.validator,
                        location=f"SKILL.md:phases.{phase.name}.validator",
                        base_dir=base_dir,
                        issues=issues,
                    )
                # Cohesion plan 方针 1.4 (2026-04-26): LLMPhase.steps was
                # removed from the schema (no production usage, no
                # runtime wiring). Nothing more to walk for an LLM phase
                # beyond agent_tools + validator.
            elif isinstance(phase, LogicPhase):
                for idx, ref in enumerate(phase.execute_steps):
                    _check_one(
                        ref,
                        location=f"SKILL.md:phases.{phase.name}.execute_steps.{idx}",
                        base_dir=base_dir,
                        issues=issues,
                    )
                if phase.validator is not None:
                    _check_one(
                        phase.validator,
                        location=f"SKILL.md:phases.{phase.name}.validator",
                        base_dir=base_dir,
                        issues=issues,
                    )
            # DelegatePhase has no tool refs.
    return issues


def _check_one(
    ref: str,
    *,
    location: str,
    base_dir: Path,
    issues: list[CompileIssue],
) -> None:
    if "." not in ref:
        issues.append(CompileIssue(
            rule_id="F-tool-path-invalid-format",
            severity="FATAL",
            location=location,
            message=(
                f"Tool reference '{ref}' has no '.' separator. "
                f"Expected format: module.path.function_name."
            ),
        ))
        return

    module_path_str, _func_name = ref.rsplit(".", 1)

    if module_path_str == "builtin" or module_path_str.startswith("builtin."):
        submod = module_path_str[len("builtin"):].lstrip(".")
        full_module = "graph_agent.tools.builtin"
        if submod:
            full_module = f"{full_module}.{submod}"
        try:
            spec = importlib.util.find_spec(full_module)
        except (ImportError, ValueError):
            spec = None
        if spec is None:
            issues.append(CompileIssue(
                rule_id="F-tool-path-not-found",
                severity="FATAL",
                location=location,
                message=(
                    f"Builtin tool reference '{ref}' resolves to module "
                    f"'{full_module}', which is not importable."
                ),
            ))
        return

    # Local path: derive base_dir/module/parts → .py file or package
    module_file = base_dir / module_path_str.replace(".", "/")
    py_file = module_file.with_suffix(".py")
    init_file = module_file / "__init__.py"
    if not py_file.is_file() and not init_file.is_file():
        issues.append(CompileIssue(
            rule_id="F-tool-path-not-found",
            severity="FATAL",
            location=location,
            message=(
                f"Tool reference '{ref}' resolves to module file "
                f"'{py_file}' or package '{init_file}', neither of "
                f"which exists."
            ),
        ))
