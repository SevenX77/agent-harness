"""Static compilation checker for GraphAgent SKILL.md files (schema 2.0 only).

After PR #6 the compiler is a thin shell: Pydantic discriminated unions on
``SkillManifest`` (``core/manifest.py``) carry the entire structural-validation
load, so this module only re-runs Pydantic and surfaces validation errors as
``CompileResult`` issues for callers (loader.py, the compiler-skill agent loop,
the Studio UI). Unsupported schema versions are rejected with
``F-schema-version`` — there is no migration path inside the loader.

Usage::

    from graph_agent.core.compiler import compile_skill
    result = compile_skill(Path("path/to/SKILL.md"))
    if not result.passed:
        for f in result.fatals:
            print(f"[{f.rule_id}] {f.location}: {f.message}")

Schema-2.0 semantic checks
==========================

Pydantic now handles every structural rule through the
``SkillManifest`` discriminated union. Semantic rules that cross files or
need import metadata run after Pydantic succeeds against the already-
validated manifest:

- **Tool-path resolvability** ✅ shipped in PR #7 step 4.
  See ``validators/tool_paths.py``. Static, non-executing check —
  validates file existence (local refs) or ``find_spec`` (builtin
  refs); function-symbol existence stays at load-time to avoid running
  user code during Studio "save validate".
- **Persona resolution** ✅ shipped in PR #7 step 3 + step 5.
  See ``validators/persona_resolution.py`` and ``personas.py``. The
  loader's private ``_resolve_persona`` was promoted to the public
  ``personas.resolve_persona`` and the implicit walk-up (which
  searched parent dirs for ``skills/``) was replaced with the explicit
  ``GRAPH_AGENT_PERSONA_PATH`` env-var registry — load-time and
  compile-time share one resolver and one search order.

The 1.x ``subgraph_cycle`` and ``context_bridge`` validators were
removed in MVP-0 B1 (2026-04-28) along with the DelegatePhase /
ParallelDelegatePhase modes they validated. V2 cross-skill composition
will reintroduce equivalent checks for the new Send-API design.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path

from .exceptions import SkillLoadError
from .parser import _parse_frontmatter, locate_line_for_pydantic_loc

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

    Most structural checks are delegated to Pydantic at parse time
    (the manifest's ``extra='forbid'`` + discriminated unions +
    per-mode field constraints, plus the ``GraphSkillDef``
    model_validators added by the 2026-04-26 cohesion plan: phase-name
    uniqueness and retry_target reference resolution).

    Semantic checks layered on top of Pydantic:

    - ``check_persona_resolution`` (F-persona-not-resolved) —
      ``adopted_persona`` references resolve to a real
      ``PersonaSkillDef``.
    - ``check_tool_paths`` (F-tool-path-*) — tool dot-references
      resolve to importable modules and stay inside ``base_dir``.

    All errors aggregate into ``CompileResult`` with ``SKILL.md:<line>:<dotted-loc>``
    locations; nothing escapes as a Python exception.
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

    try:
        content = skill_path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as e:
        result.issues.append(CompileIssue(
            rule_id="INTERNAL",
            severity="FATAL",
            location=str(skill_path),
            message=f"Failed to read SKILL.md: {e}",
        ))
        return result

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

    # Cohesion plan 方针 3.3 (2026-04-26): ``schema_version: 2.0``
    # without quotes parses as a float. Coerce via ``str(...)`` so the
    # comparison succeeds for the valid case and falls through to the
    # F-schema-version fatal for any other value. Then normalise the
    # frontmatter value back to the canonical string form so the
    # downstream Pydantic ``Literal["2.0"]`` check sees the right type.
    schema_version = str(frontmatter.get("schema_version") or "").strip()
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
    frontmatter["schema_version"] = "2.0"

    # Pydantic does the structural validation when the manifest is
    # constructed in load_workflow_from_md. Surface validation errors
    # as fatals here too so static compile catches them before runtime.
    from pydantic import TypeAdapter, ValidationError

    from .manifest import AgentSkillDef, GraphSkillDef, PersonaSkillDef, SkillManifest

    try:
        manifest: AgentSkillDef | GraphSkillDef | PersonaSkillDef = TypeAdapter(
            SkillManifest
        ).validate_python(frontmatter)
    except ValidationError as ve:
        for err in ve.errors():
            loc_tuple = err.get("loc", ())
            loc_dotted = ".".join(str(p) for p in loc_tuple)
            # Cohesion plan 方针 3.2 (2026-04-26): translate the Pydantic
            # ``loc`` tuple into the actual SKILL.md line number using
            # ruamel.yaml's CommentedMap line metadata. Falls back to
            # the dotted-path-only format when the location cannot be
            # walked (e.g. a top-level field with no metadata).
            line = locate_line_for_pydantic_loc(frontmatter, loc_tuple)
            if line is not None:
                location = f"SKILL.md:{line}:{loc_dotted or 'frontmatter'}"
            else:
                location = f"SKILL.md:{loc_dotted or 'frontmatter'}"
            result.issues.append(CompileIssue(
                rule_id="F-pydantic",
                severity="FATAL",
                location=location,
                message=err.get("msg", "Pydantic validation failed"),
            ))
        return result

    # PR #7 semantic checks (run only when Pydantic validation succeeds).
    # GraphSkillDef carries phases (LLMPhase / LogicPhase). AgentSkillDef
    # has no phases but does carry a top-level ``adopted_persona`` and
    # ``agent_tools``, so it runs persona_resolution + tool_paths.
    # PersonaSkillDef carries neither and falls through unchanged.
    from .validators.persona_resolution import check_persona_resolution
    from .validators.tool_paths import check_tool_paths

    if isinstance(manifest, GraphSkillDef):
        from .validators.prompt_quality import check_prompt_quality
        from .validators.template_variables import check_template_variables
        from .validators.validator_required import check_validator_required

        result.issues.extend(
            check_persona_resolution(manifest, base_dir=skill_path.parent)
        )
        result.issues.extend(
            check_tool_paths(manifest, base_dir=skill_path.parent)
        )
        result.issues.extend(check_prompt_quality(manifest))
        result.issues.extend(check_template_variables(manifest))
        result.issues.extend(check_validator_required(manifest))
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
