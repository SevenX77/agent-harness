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

from .exceptions import SkillLoadError

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
) -> "PersonaSkillDef":
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

    from .manifest import PersonaSkillDef, SkillManifest
    from .parser import parse_skill_file

    if search_paths is None:
        search_paths = default_persona_search_paths()

    candidates: list[Path] = [base_dir / "subskills" / name / "SKILL.md"]
    candidates.extend(root / name / "SKILL.md" for root in search_paths)

    for candidate in candidates:
        if not candidate.exists():
            continue
        parsed = parse_skill_file(candidate)
        manifest = TypeAdapter(SkillManifest).validate_python(parsed["frontmatter"])
        if not isinstance(manifest, PersonaSkillDef):
            raise SkillLoadError(
                f"adopted_persona '{name}' resolved to {candidate}, but its "
                f"type is {type(manifest).__name__}, not PersonaSkillDef."
            )
        return manifest

    raise SkillLoadError(
        f"adopted_persona '{name}' not found. Searched: "
        + ", ".join(str(c) for c in candidates)
    )
