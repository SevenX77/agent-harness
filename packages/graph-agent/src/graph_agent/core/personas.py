"""Legacy persona registry placeholder.

V0.3.0 graph skills do not support schema-2.0 persona SKILL.md resolution.
"""

from __future__ import annotations

import os
from pathlib import Path

from graph_agent.core.exceptions import SkillLoadError

PERSONA_PATH_ENV_VAR = "GRAPH_AGENT_PERSONA_PATH"


def default_persona_search_paths() -> list[Path]:
    """Read ``GRAPH_AGENT_PERSONA_PATH`` and return its directory entries."""
    raw = os.environ.get(PERSONA_PATH_ENV_VAR, "")
    if not raw:
        return []
    return [Path(p) for p in raw.split(os.pathsep) if p]


def resolve_persona(name: str, *, base_dir: Path, search_paths: list[Path] | None = None) -> None:
    del base_dir, search_paths
    raise SkillLoadError(
        f"[F-v3-agent-schema-unknown-field] adopted_persona {name!r} is not supported"
    )
