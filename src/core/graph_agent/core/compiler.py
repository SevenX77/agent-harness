"""Static compilation checker for GraphAgent SKILL.md files (schema 2.0 only).

After PR #6 the compiler is a thin shell: Pydantic discriminated unions on
``SkillManifest`` (``core/manifest.py``) carry the entire structural-validation
load, so this module only re-runs Pydantic and surfaces validation errors as
``CompileResult`` issues for callers (loader.py, the compiler-skill agent loop,
the Studio UI). Schema 1.x (``<phase>``/``<node>``/XML body) is rejected with
``F-schema-version`` — there is no migration path inside the loader anymore.

Usage::

    from graph_agent.core.compiler import compile_skill
    result = compile_skill(Path("path/to/SKILL.md"))
    if not result.passed:
        for f in result.fatals:
            print(f"[{f.rule_id}] {f.location}: {f.message}")

TODO(PR#7) — schema-2.0 semantic checks
=======================================

The 1.x ``_check_*`` rules were rule-bound to the XML body and have no
schema-2.0 equivalent worth porting verbatim. Pydantic now handles every
structural rule. The remaining *semantic* rules — the ones Pydantic cannot
express because they cross files or need import side-effects — must be
reintroduced in PR #7 against the already-validated ``SkillManifest``:

- **Tool-path resolvability** ✅ shipped in PR #7 step 4.
  See ``validators/tool_paths.py``. Static, non-executing check —
  validates file existence (local refs) or ``find_spec`` (builtin
  refs); function-symbol existence stays at load-time to avoid running
  user code during Studio "save validate".
- **Subgraph cycle detection** ✅ shipped in PR #7 step 2.
  See ``validators/subgraph_cycle.py``. Independent of step 1 — both
  validators run unconditionally for ``GraphSkillDef`` manifests in the
  order context_bridge → subgraph_cycle (no shared state).
- **Persona resolution** ✅ shipped in PR #7 step 3.
  See ``validators/persona_resolution.py``. Reuses
  ``loader._resolve_persona`` so compile-time and load-time agree on
  the search order; promoting that helper to a public registry remains
  a separate refactor (loader.py TODO).
- **context_bridge static type check** — shipped in PR #7 step 1.
  See ``validators/context_bridge.py``. The remaining checks below
  still have only load-time fallbacks (or no fallback at all in the
  case of ``rules.yaml``).
- **Custom rules.yaml** — the 1.x rules.yaml carried project-specific
  conventions (placeholder presence, prompt-length budgets). Decide
  whether to keep that authoring surface or absorb the rules into the
  Pydantic schema.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path

from .parser import _parse_frontmatter
from .exceptions import SkillLoadError

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------


@dataclass
class CompileIssue:
    """A single compilation diagnostic."""

    rule_id: str
    severity: str  # "FATAL" or "WARNING"
    location: str  # e.g. "SKILL.md:47" or "tools/compile.py"
    message: str


@dataclass
class CompileResult:
    """Aggregated result of compile_skill()."""

    issues: list[CompileIssue] = field(default_factory=list)

    @property
    def fatals(self) -> list[CompileIssue]:
        return [i for i in self.issues if i.severity == "FATAL"]

    @property
    def warnings(self) -> list[CompileIssue]:
        return [i for i in self.issues if i.severity == "WARNING"]

    @property
    def passed(self) -> bool:
        return len(self.fatals) == 0


def compile_skill(skill_path: str | Path) -> CompileResult:
    """Run static compilation checks on a schema-2.0 SKILL.md file.

    Most structural checks are now delegated to Pydantic at parse time
    (the manifest's ``extra='forbid'`` + discriminated unions + per-mode field
    constraints). This function is reduced to a thin wrapper that surfaces
    parse errors as ``CompileResult`` issues.

    Semantic checks (tool resolvability, persona resolution, subgraph cycle)
    for schema 2.0 are TODO — see PR #6 follow-up issue.
    """
    skill_path = Path(skill_path)
    result = CompileResult()

    if not skill_path.exists():
        result.issues.append(CompileIssue(
            rule_id="INTERNAL",
            severity="FATAL",
            location=str(skill_path),
            message="SKILL.md 文件不存在",
        ))
        return result

    content = skill_path.read_text(encoding="utf-8")

    if not content.strip():
        result.issues.append(CompileIssue(
            rule_id="INTERNAL",
            severity="FATAL",
            location=str(skill_path),
            message="SKILL.md 文件为空",
        ))
        return result

    try:
        frontmatter = _parse_frontmatter(content)
    except SkillLoadError as e:
        result.issues.append(CompileIssue(
            rule_id="INTERNAL",
            severity="FATAL",
            location="SKILL.md:frontmatter",
            message=str(e),
        ))
        return result

    schema_version = (frontmatter.get("schema_version") or "").strip()
    if schema_version != "2.0":
        result.issues.append(CompileIssue(
            rule_id="F-schema-version",
            severity="FATAL",
            location="SKILL.md:frontmatter",
            message=(
                f"Unsupported schema_version: {schema_version!r}. "
                'Only schema_version: "2.0" is supported.'
            ),
        ))
        return result

    # Pydantic does the structural validation when the manifest is
    # constructed in load_workflow_from_md. Surface validation errors
    # as fatals here too so static compile catches them before runtime.
    from pydantic import TypeAdapter, ValidationError

    from .manifest import GraphSkillDef, SkillManifest

    try:
        manifest = TypeAdapter(SkillManifest).validate_python(frontmatter)
    except ValidationError as ve:
        for err in ve.errors():
            loc = ".".join(str(p) for p in err.get("loc", ()))
            result.issues.append(CompileIssue(
                rule_id="F-pydantic",
                severity="FATAL",
                location=f"SKILL.md:{loc or 'frontmatter'}",
                message=err.get("msg", "Pydantic validation failed"),
            ))
        return result

    # PR #7 semantic checks (run only when Pydantic validation succeeds).
    # GraphSkillDef carries phases (DelegatePhase + LLMPhase) so it runs
    # the full quadruple. AgentSkillDef has no phases but does carry a
    # top-level ``adopted_persona`` and ``agent_tools``, so it runs
    # persona_resolution + tool_paths. PersonaSkillDef carries neither
    # and falls through unchanged.
    from .manifest import AgentSkillDef
    from .validators.persona_resolution import check_persona_resolution
    from .validators.tool_paths import check_tool_paths

    if isinstance(manifest, GraphSkillDef):
        from .validators.context_bridge import check_context_bridge
        from .validators.subgraph_cycle import check_subgraph_cycles

        result.issues.extend(
            check_context_bridge(manifest, base_dir=skill_path.parent)
        )
        result.issues.extend(
            check_subgraph_cycles(manifest, skill_path=skill_path)
        )
        result.issues.extend(
            check_persona_resolution(manifest, base_dir=skill_path.parent)
        )
        result.issues.extend(
            check_tool_paths(manifest, base_dir=skill_path.parent)
        )
    elif isinstance(manifest, AgentSkillDef):
        result.issues.extend(
            check_persona_resolution(manifest, base_dir=skill_path.parent)
        )
        result.issues.extend(
            check_tool_paths(manifest, base_dir=skill_path.parent)
        )

    logger.info(
        "Compiled '%s' (schema 2.0): %d FATAL, %d WARNING",
        skill_path.name,
        len(result.fatals),
        len(result.warnings),
    )
    return result
