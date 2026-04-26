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

    # Cohesion plan 方针 4.3 (2026-04-26): reject references whose
    # resolved path escapes ``base_dir`` (e.g. via ``..`` segments
    # collapsing through Path arithmetic, or via an absolute literal
    # leaking in, or via a symlink inside the tree pointing out).
    # Without this check, the compile pass would silently accept paths
    # the load-time resolver later refuses, producing inconsistent
    # behaviour across the static / dynamic boundary.
    #
    # Codex review follow-up (2026-04-26): the original check resolved
    # only ``module_file`` (the no-extension directory form), but a
    # symlinked ``foo.py`` or ``foo/__init__.py`` inside base_dir
    # pointing outside slipped past unnoticed. Resolve all three
    # candidate forms and reject if any of them escapes.
    try:
        resolved_base = base_dir.resolve()
        candidates_to_check = [
            module_file.resolve(),
            py_file.resolve(),
            init_file.resolve(),
        ]
    except OSError:
        # Could not resolve (e.g. base_dir itself missing on disk).
        # Fall through — existence check below will produce a
        # not-found fatal with whatever path string we have.
        resolved_base = base_dir
        candidates_to_check = [module_file, py_file, init_file]
    escape_target = next(
        (c for c in candidates_to_check if not _is_within(c, resolved_base)),
        None,
    )
    if escape_target is not None:
        issues.append(CompileIssue(
            rule_id="F-tool-path-escape",
            severity="FATAL",
            location=location,
            message=(
                f"Tool reference '{ref}' resolves to '{escape_target}', "
                f"which is outside the skill's base directory "
                f"'{resolved_base}'. References that escape the skill tree "
                f"(including via symlinks pointing out) are rejected to "
                f"keep static-compile behaviour consistent with load-time "
                f"path-anchored resolution."
            ),
        ))
        return

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


def _is_within(candidate: Path, root: Path) -> bool:
    """Return True iff ``candidate`` is at or below ``root``.

    ``Path.is_relative_to`` was added in Python 3.9; this wrapper makes
    the intent explicit (and lets us swap implementation later if we
    need to handle symlink semantics specially).
    """
    try:
        candidate.relative_to(root)
        return True
    except ValueError:
        return False
