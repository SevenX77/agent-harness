"""Dependency-graph slicing for per-node resume dirtiness (n5-node#3).

When a Studio user edits an upstream node and then asks to resume from some
node, the whole-skill dirty compare (``EngineAdapter.resume_validity``) flips
``resume_allowed`` for the ENTIRE skill -- even side-branches the edit cannot
affect. This module slices dirtiness by the compiled graph's ``depends_on``
order so the frontend can gray exactly the downstream nodes a change reaches,
and leave unrelated branches runnable.

The engine has no per-node content hash (``artifacts.py`` hashes the whole
skill), so the slice is dependency-graph based: the affected-downstream set of
a node is that node plus every phase that transitively depends on it. This is
sufficient for the graying UX and stays entirely in the Studio shell -- it only
reads ``compiled.nodes`` (phase_name + depends_on), no engine edit.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


def _phase_depends_on(compiled: Any) -> dict[str, list[str]]:
    """Map each phase to its declared upstream dependencies from the compiled graph.

    Prefers the graph-topology rows in ``compiled.raw`` (which carry the resolved
    ``depends_on`` edge list); falls back to an empty edge set per phase when the
    topology block is absent (single-phase / linear skills still slice correctly).
    """
    raw = getattr(compiled, "raw", {})
    topology = raw.get("graph_topology", {}) if isinstance(raw, dict) else {}
    rows = topology.get("phases", []) if isinstance(topology, dict) else []
    depends: dict[str, list[str]] = {}
    if isinstance(rows, list):
        for row in rows:
            if not isinstance(row, dict):
                continue
            name = row.get("name")
            edges = row.get("depends_on")
            if isinstance(name, str) and isinstance(edges, list):
                depends[name] = [str(edge) for edge in edges if isinstance(edge, str)]
    # Ensure every compiled phase is present even if it has no topology row.
    for node in getattr(compiled, "nodes", []) or []:
        phase_name = getattr(node, "phase_name", None)
        if isinstance(phase_name, str) and phase_name not in depends:
            depends[phase_name] = []
    return depends


def affected_downstream_nodes(compiled: Any, changed_node_id: str) -> list[str]:
    """Return ``changed_node_id`` plus every phase that transitively depends on it.

    These are the nodes a change at ``changed_node_id`` can dirty -- the set the
    frontend should gray. The returned list is deterministic (sorted) and always
    includes ``changed_node_id`` itself when it is a known phase.
    """
    depends = _phase_depends_on(compiled)
    if changed_node_id not in depends:
        logger.warning(
            "resume_downstream: changed_node_id=%s not a known phase; no downstream slice",
            changed_node_id,
        )
        return []

    # Invert depends_on into a forward adjacency (dependency -> dependents).
    dependents: dict[str, set[str]] = {phase: set() for phase in depends}
    for phase, upstreams in depends.items():
        for upstream in upstreams:
            dependents.setdefault(upstream, set()).add(phase)

    affected: set[str] = set()
    stack = [changed_node_id]
    while stack:
        current = stack.pop()
        if current in affected:
            continue
        affected.add(current)
        stack.extend(dependents.get(current, set()))
    logger.debug(
        "resume_downstream: changed_node_id=%s affects %d downstream phase(s)",
        changed_node_id,
        len(affected),
    )
    return sorted(affected)


def is_resume_node_affected(
    compiled: Any,
    *,
    resume_from_node_id: str,
    dirty_node_ids: list[str],
) -> bool:
    """Is the resume node within the dirty set's downstream reach?

    ``dirty_node_ids`` are the nodes flagged dirty (here: the affected-downstream
    set of the changed upstream). The resume is blocked only when the resume node
    itself is one of them; resuming from a node on an unrelated branch is allowed.
    """
    return resume_from_node_id in set(dirty_node_ids)


def resume_allowed_for_node(
    *,
    resume_from_node_id: str | None,
    is_dirty: bool,
    affected_downstream: list[str] | None,
) -> bool:
    """Decide ``resume_allowed`` per spec F3, branching on whether a node is named.

    Two distinct semantics, by design (n5-node fn#3):

    * **No resume node** (``resume_from_node_id is None`` -- the global Trace Resume
      that continues a run from its last checkpoint): keep the whole-skill gate.
      A clean skill resumes; any dirt blocks. The per-node slice must NOT silently
      flip a globally-dirty skill back to resumable.
    * **A resume node is named** (per-node Resume anchored on the canvas node): a
      clean skill always resumes; when dirty, resume is allowed iff the node sits
      OUTSIDE the affected-downstream slice -- so an unrelated side-branch stays
      resumable while a node the change reaches is blocked.

    ``affected_downstream is None`` means the slice could NOT be computed (the skill
    would not compile). An empty *list* means "computed, nothing downstream"; ``None``
    means "unknown". When the slice is unknown we cannot prove the node sits outside
    the dirtied set, so a dirty skill degrades to the conservative whole-skill gate
    (blocked) -- a slice failure must never silently weaken the gate to "allowed".
    """
    if not is_dirty:
        return True
    if resume_from_node_id is None:
        # Global Trace Resume: dirty skill stays blocked (whole-skill semantics).
        logger.info(
            "resume_downstream: global resume gate -> blocked (skill dirty, no node target)"
        )
        return False
    if affected_downstream is None:
        # Slice unavailable (skill did not compile): cannot prove the node is an
        # unrelated side-branch, so degrade to the conservative whole-skill gate.
        logger.warning(
            "resume_downstream: per-node slice unavailable for node=%s -> blocked "
            "(conservative; skill is dirty)",
            resume_from_node_id,
        )
        return False
    affected = is_resume_node_affected(
        None,
        resume_from_node_id=resume_from_node_id,
        dirty_node_ids=affected_downstream,
    )
    logger.info(
        "resume_downstream: per-node resume gate node=%s affected=%s -> %s",
        resume_from_node_id,
        affected,
        "blocked" if affected else "allowed",
    )
    return not affected
