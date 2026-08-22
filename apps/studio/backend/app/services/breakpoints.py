"""Which nodes a skill stops before, and how the worker is told.

A breakpoint is an outside observation of a run: the run behaves the same
whether or not one is set, it just stops earlier. So it is not part of the
skill's authored source — it lives with the other run-time choices in
``.workspace/runtime_config.json`` and is disposable with them.

Design: run-execution/mvp1-alignment.md F10 + RUN_EXECUTION-16.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.services.runtime_config import read_runtime_config, update_breakpoints_payload
from app.services.skills import opened_skill_dir


@dataclass(frozen=True)
class BreakpointWriteResult:
    """What a write did. ``changed`` is False when the file already said this.

    The surfaces revalidate when a dataset changes, so a write that changed
    nothing must not announce one — otherwise setting an already-set breakpoint
    refetches with no data change behind it (SSOT 读取原则).
    """

    node_ids: list[str]
    changed: bool


def read_breakpoints(skill_dir: Path) -> list[str]:
    return breakpoints_from_runtime_config(read_runtime_config(skill_dir))


def breakpoints_for_skill(skill_id: str) -> list[str]:
    """The marks standing on this skill right now, named by id instead of path.

    Total on purpose. A run is continued from its own frozen artifact and its
    runtime-state snapshot — never from the live skill directory — so a skill
    this Studio does not hold open is not an error to whoever is asking: it is a
    skill on which nobody could have set a mark. Resolving the directory the
    raising way instead answered 404 SKILL_NOT_FOUND for such a resume, burying
    the runtime-state error the caller actually had to see.
    """
    skill_dir = opened_skill_dir(skill_id)
    return [] if skill_dir is None else read_breakpoints(skill_dir)


def breakpoints_from_runtime_config(config: dict[str, Any]) -> list[str]:
    """The stop list as the engine wants to hear it: node ids, sorted, deduped.

    The engine takes an explicit "stop before these phases" and never reads a
    Studio workspace file, so this is where the workspace's shape stops and the
    engine's vocabulary starts. Node ids ARE phase names (see
    ``routers/node_llm_params``), so the translation is a projection, not a
    mapping.
    """
    stored = config.get("breakpoints")
    if not isinstance(stored, list):
        return []
    return sorted({node_id for node_id in stored if isinstance(node_id, str) and node_id})


def set_breakpoint(skill_dir: Path, node_id: str) -> BreakpointWriteResult:
    return _write(skill_dir, node_id, present=True)


def clear_breakpoint(skill_dir: Path, node_id: str) -> BreakpointWriteResult:
    return _write(skill_dir, node_id, present=False)


def _write(skill_dir: Path, node_id: str, *, present: bool) -> BreakpointWriteResult:
    current = read_breakpoints(skill_dir)
    if (node_id in current) == present:
        return BreakpointWriteResult(node_ids=current, changed=False)
    following = sorted({*current, node_id} if present else set(current) - {node_id})
    update_breakpoints_payload(skill_dir, following)
    return BreakpointWriteResult(node_ids=following, changed=True)
