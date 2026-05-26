"""Public persona registry shared by load-time and compile-time callers.

Replaces the implicit walk-up that ``loader._resolve_persona`` used to do
(searching up the parent chain for any directory named ``skills/``). The
new contract is explicit:

1. **Skill-local convention** — ``<base_dir>/subskills/<name>/SKILL.md``
   is always checked first. This is the natural authoring convention for
   personas that ship inside a single skill tree.
2. **Explicit search paths** — additional directories are taken from the
   ``GRAPH_AGENT_PERSONA_PATH`` env var (``os.pathsep``-separated, like
   ``PYTHONPATH``). Each entry is treated as a registry root: a persona
   named ``foo`` resolves to ``<entry>/foo/SKILL.md``.

If the env var is unset, only the skill-local convention applies. Authors
who want a project-wide registry export the env var at the top of their
workflow; a YAML-driven registry can later be layered on top by
extending ``default_persona_search_paths`` without changing callers.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import TYPE_CHECKING

from graph_agent.core.exceptions import SkillLoadError

if TYPE_CHECKING:
    from graph_agent.core.manifest import PersonaSkillDef

PERSONA_PATH_ENV_VAR = "GRAPH_AGENT_PERSONA_PATH"


def default_persona_search_paths() -> list[Path]:
    """Read ``GRAPH_AGENT_PERSONA_PATH`` and return its directory entries."""
    raw = os.environ.get(PERSONA_PATH_ENV_VAR, "")
    if not raw:
        return []
    return [Path(p) for p in raw.split(os.pathsep) if p]


def resolve_persona(
    name: str,
    *,
    base_dir: Path,
    search_paths: list[Path] | None = None,
) -> PersonaSkillDef:
    """Resolve a persona ``name`` to a ``PersonaSkillDef`` manifest.

    Args:
        name: The persona name as written in ``adopted_persona``.
        base_dir: The parent directory of the SKILL.md that referenced
            the persona. ``<base_dir>/subskills/<name>/SKILL.md`` is
            always checked first.
        search_paths: Additional registry root directories. Each entry
            ``<root>`` is checked as ``<root>/<name>/SKILL.md`` in the
            order given. ``None`` falls back to
            :func:`default_persona_search_paths`, which reads
            ``GRAPH_AGENT_PERSONA_PATH``.

    Raises:
        SkillLoadError: when no candidate path exists, or when a
            candidate exists but does not parse as a ``PersonaSkillDef``.
    """
    from pydantic import TypeAdapter

    from graph_agent.core.manifest import PersonaSkillDef, SkillManifest
    from graph_agent.core.parser import parse_skill_file

    if search_paths is None:
        search_paths = default_persona_search_paths()

    # Cohesion plan 方针 4.2 (2026-04-26): a relative path
    # (``./...``) or a path containing a separator is anchored at
    # ``base_dir`` directly — do NOT prepend the implicit
    # ``subskills/`` convention prefix. Bare names (no slash, no
    # leading ``./``) keep the skill-local convention.
    #
    # Direct anchoring without a containment check would let
    # ``../external`` escape ``base_dir``. Resolve the candidate and
    # verify it stays inside ``base_dir``.
    is_relative_path = name.startswith("./") or "/" in name or "\\" in name
    if is_relative_path:
        candidate = base_dir / name / "SKILL.md"
        try:
            resolved_base = base_dir.resolve()
            resolved_candidate = candidate.resolve()
        except (OSError, RuntimeError) as exc:
            raise SkillLoadError(
                f"adopted_persona '{name}' could not be resolved on disk: {exc}"
            ) from exc
        try:
            resolved_candidate.relative_to(resolved_base)
        except ValueError as exc:
            raise SkillLoadError(
                f"adopted_persona '{name}' resolves to {resolved_candidate}, "
                f"which is outside the skill's base directory "
                f"{resolved_base}. References that escape the skill tree "
                f"are rejected."
            ) from exc
        candidates: list[Path] = [candidate]
    else:
        candidates = [base_dir / "subskills" / name / "SKILL.md"]
        candidates.extend(root / name / "SKILL.md" for root in search_paths)

    for candidate in candidates:
        if not candidate.is_file():
            continue
        parsed = parse_skill_file(candidate)
        manifest: SkillManifest = TypeAdapter(SkillManifest).validate_python(parsed["frontmatter"])
        if not isinstance(manifest, PersonaSkillDef):
            raise SkillLoadError(
                f"adopted_persona '{name}' resolved to {candidate}, but its "
                f"type is {type(manifest).__name__}, not PersonaSkillDef."
            )
        return manifest

    raise SkillLoadError(
        f"adopted_persona '{name}' not found. Searched: " + ", ".join(str(c) for c in candidates)
    )
