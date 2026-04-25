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

PERSONA_PATH_ENV_VAR = "GRAPH_AGENT_PERSONA_PATH"


def default_persona_search_paths() -> list[Path]:
    """Read ``GRAPH_AGENT_PERSONA_PATH`` and return its directory entries."""
    raw = os.environ.get(PERSONA_PATH_ENV_VAR, "")
    if not raw:
        return []
    return [Path(p) for p in raw.split(os.pathsep) if p]
