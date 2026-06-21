"""P8 model-compare run fan-out (n4-trace#23).

A model-compare run executes the SAME compiled artifact and inputs N times, once
per candidate role, so the frontend Trace can tab between per-model results. The
candidate selection rides on the temporary-ROLE seam the Studio shell already
owns: the engine resolver loads roles from ``STUDIO_LLM_ROLES_PATH`` per worker
process (engine.py), so we materialize a per-candidate ``llm_roles.yaml`` and
point that worker's env at it -- NO gateway/engine edit.

For each candidate we copy the active roles file and override the skill-bound
graph_agent role(s) with the named candidate role, so every agent node resolves
through the candidate's fallback chain. The temporary files live under the run's
compare-group directory and are passed to the worker via ``STUDIO_LLM_ROLES_PATH``.
"""

from __future__ import annotations

import logging
import uuid
from pathlib import Path

from app.models.llm_config import RoleEntry, RolesData
from app.models.runs import RunCandidate
from app.services.llm_paths import roles_path
from app.services.llm_roles import load_roles_file, save_roles_file

logger = logging.getLogger(__name__)


class CompareCandidateError(ValueError):
    """Raised when a candidate references a role absent from the active roles file."""

    def __init__(self, candidate_id: str, role_name: str) -> None:
        self.candidate_id = candidate_id
        self.role_name = role_name
        super().__init__(
            f"compare candidate {candidate_id!r} references unknown role {role_name!r}"
        )


def new_compare_group_id() -> str:
    """Stable id shared by every per-candidate run in one compare fan-out."""
    return f"cmp-{uuid.uuid4().hex[:12]}"


def _load_active_roles() -> RolesData:
    active = roles_path()
    if not active.exists():
        logger.info("run_compare: active roles file absent at %s; using empty roles", active)
        return RolesData()
    return load_roles_file(active)


def _apply_candidate_role(
    base: RolesData,
    *,
    candidate: RunCandidate,
) -> RolesData:
    """Return a copy of ``base`` with the candidate role bound to the skill's role(s).

    Override scope:
      - ``candidate.target_role`` set -> replace only that role's entry;
      - otherwise -> replace every ``graph_agent`` role entry.
    The candidate's own role entry (already materialized with a fallback chain)
    becomes the body of the overridden role(s), so agent nodes resolve through it.
    """
    source_role = base.roles.get(candidate.role_name)
    if source_role is None:
        raise CompareCandidateError(candidate.candidate_id, candidate.role_name)

    projected = base.model_copy(deep=True)
    targets = _override_targets(projected, target_role=candidate.target_role)
    for target_name in targets:
        projected.roles[target_name] = _rebind_role(
            projected.roles[target_name],
            source_role,
        )
    logger.info(
        "run_compare: candidate=%s role=%s overrides target role(s)=%s",
        candidate.candidate_id,
        candidate.role_name,
        targets,
    )
    return projected


def _override_targets(data: RolesData, *, target_role: str | None) -> list[str]:
    if target_role is not None:
        if target_role not in data.roles:
            return []
        return [target_role]
    return [name for name, role in data.roles.items() if role.role_kind == "graph_agent"]


def _rebind_role(target: RoleEntry, source: RoleEntry) -> RoleEntry:
    """Copy the source candidate's resolution into the target role, keeping its name kind."""
    return target.model_copy(
        update={
            "intent": source.intent,
            "model_groups": list(source.model_groups),
            "model_fallback_enabled": source.model_fallback_enabled,
            "fallback_chain": list(source.fallback_chain),
            "materialization_report": dict(source.materialization_report),
        }
    )


def write_candidate_roles_file(
    *,
    candidate: RunCandidate,
    group_dir: Path,
    base_roles: RolesData | None = None,
) -> Path:
    """Materialize a per-candidate ``llm_roles.yaml`` and return its path.

    The worker for this candidate is launched with ``STUDIO_LLM_ROLES_PATH``
    pointed here, so its in-process engine resolver loads the candidate's roles.
    """
    base = base_roles if base_roles is not None else _load_active_roles()
    projected = _apply_candidate_role(base, candidate=candidate)
    group_dir.mkdir(parents=True, exist_ok=True)
    candidate_path = group_dir / f"llm_roles__{candidate.candidate_id}.yaml"
    # Reference validation is against the candidate file's own route ids; the
    # candidate roles already carry materialized chains, so pass the projected
    # file's known ids to keep save_roles_file's validator satisfied.
    save_roles_file(candidate_path, projected)
    logger.info(
        "run_compare: wrote candidate roles file candidate=%s path=%s",
        candidate.candidate_id,
        candidate_path,
    )
    return candidate_path
