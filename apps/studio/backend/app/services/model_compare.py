"""Node-level model-compare mechanics (PR2): isolated single-node side-runs.

Compare does NOT inject a parallel graph node; it runs the node again on the
side. The design source records that as the PM-approved shape
(``docs/studio/mvp1/03_regions/properties/mvp1-alignment.md:61``), because a
side-run touches neither the engine's execution nor the main blackboard. (The
original 2026-07-02 reason — that two in-graph nodes could not run in the same
superstep — no longer holds: ``WorkflowState.data`` became a reducer channel in
#804, see ``graph_agent.core.state.merge_business_channel``. The design stands
on its own grounds.) For each candidate we:

1. take the compare node's real input slice from the base run's
   ``input_dispatch`` event (:func:`extract_node_input`),
2. materialize a single-phase skill variant that runs just that node
   (:func:`materialize_single_node_skill`),
3. write a temp roles file that is the active roles truth with every role's
   model swapped to the candidate (:func:`write_candidate_roles_file`),

then run each variant with the captured slice via the ordinary run machinery. The
side-run is a physically separate run, so it never writes the main blackboard and
gets its own artifacts directory for free.
"""

from __future__ import annotations

import shutil
import uuid
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import yaml

from app.core.adapters.engine import AgentNodeAST, compile_skill, effective_llm_role
from app.core.exceptions import BoundaryValidationError
from app.models.llm_config import RoleEntry, RolesData
from app.models.model_compare import CompareCandidate


class CompareNodeInputMissingError(Exception):
    """Raised when the base run has no input_dispatch event for the node."""


def new_compare_group_id() -> str:
    """Stable id shared by every candidate side-run in one compare group."""
    return f"cmp-{uuid.uuid4().hex[:12]}"


def extract_node_input(events: Sequence[Any], node_id: str) -> dict[str, Any]:
    """Return the exact input slice the base run dispatched to ``node_id``.

    Reads the last ``input_dispatch`` event whose ``to_phase`` is ``node_id`` and
    returns its ``blackboard_snapshot`` (what the engine actually fed the node).
    """
    snapshot: dict[str, Any] | None = None
    for envelope in events:
        payload = getattr(envelope, "payload", None)
        if not isinstance(payload, dict):
            continue
        if getattr(envelope, "event_type", None) != "input_dispatch":
            continue
        if payload.get("to_phase") != node_id:
            continue
        candidate = payload.get("blackboard_snapshot")
        if isinstance(candidate, dict):
            snapshot = candidate
    if snapshot is None:
        raise CompareNodeInputMissingError(
            f"base run has no input_dispatch for node {node_id!r}"
        )
    return dict(snapshot)


def materialize_single_node_skill(skill_dir: Path, node_id: str, dest: Path) -> Path:
    """Copy ``skill_dir`` into ``dest`` reduced to a runnable single-node graph.

    The variant keeps only ``node_id``'s phase directory and a rewritten GRAPH.md
    whose sole phase is ``node_id`` (``depends_on="input"``), with the graph io
    taken from that node's declared io so the captured slice validates. The graph
    ``llm_role`` default is preserved so the node's effective role is unchanged.
    """
    compiled = compile_skill(skill_dir, cache=False)
    doc = next((n for n in compiled.nodes if n.phase_name == node_id), None)
    if doc is None:
        raise BoundaryValidationError(f"node {node_id!r} not found in skill {skill_dir}")
    io = getattr(doc.ast, "io", None)
    if io is None:
        raise BoundaryValidationError(f"node {node_id!r} has no declared io; cannot compare")
    io_plain = io.model_dump(mode="json")

    graph_fm: dict[str, Any] = {
        "schema_version": "v0.3.0",
        "name": f"{compiled.manifest.name}__cmp_{node_id}",
    }
    if compiled.manifest.llm_role is not None:
        graph_fm["llm_role"] = compiled.manifest.llm_role
    graph_fm["io"] = {"inputs": io_plain["inputs"], "outputs": io_plain["outputs"]}
    graph_fm["phases"] = [node_id]

    shutil.copytree(skill_dir, dest, dirs_exist_ok=True)
    # Loader requires frontmatter phases == body <phase> names == physical phase
    # dirs, so drop every sibling phase directory.
    phases_dir = dest / "phases"
    if phases_dir.is_dir():
        for child in phases_dir.iterdir():
            if child.is_dir() and child.name != node_id:
                shutil.rmtree(child)
    # A stale .workspace copy would confuse resolution; the variant is throwaway.
    workspace = dest / ".workspace"
    if workspace.is_dir():
        shutil.rmtree(workspace)

    body = f'<phase depends_on="input" output>{node_id}</phase>\n'
    graph_md = "---\n" + yaml.safe_dump(graph_fm, sort_keys=False, allow_unicode=True) + "---\n" + body
    (dest / "GRAPH.md").write_text(graph_md, encoding="utf-8")
    return dest


def node_effective_role(skill_dir: Path, node_id: str) -> str | None:
    """The role name ``node_id`` resolves to (PR1 layering), for roles binding.

    None only for a LOGIC/SUBGRAPH node under a graph with no default role:
    such a node consumes no role itself (agent phases inside its subtree each
    declare their own). An AGENT node that resolves no role is refused —
    J-X.10 (用户裁决 2026-08-31): no invented fallback; the side-run would
    resolve models by a name nobody set, and the main compile path already
    rejects the skill as [F-v3-agent-llm-role-missing].
    """
    compiled = compile_skill(skill_dir, cache=False)
    doc = next((n for n in compiled.nodes if n.phase_name == node_id), None)
    if doc is None:
        raise BoundaryValidationError(f"node {node_id!r} not found in skill {skill_dir}")
    if isinstance(doc.ast, AgentNodeAST):
        role = effective_llm_role(doc.ast, compiled.manifest.llm_role)
        if role is None:
            raise BoundaryValidationError(
                f"node {node_id!r} resolves no LLM role: set `llm_role` in the phase "
                "frontmatter or a graph default `llm_role` in GRAPH.md"
            )
        return role
    return compiled.manifest.llm_role


def build_candidate_roles(
    skill_dir: Path,
    node_id: str,
    candidate: CompareCandidate,
) -> RolesData:
    """The active roles truth with EVERY role's model swapped to ``candidate``.

    The side-run worker points ``STUDIO_LLM_ROLES_PATH`` at this data, which
    REPLACES the roles truth wholesale for that process — so any role name the
    execution asks for and this data does not define kills the run at resolution
    (``resource.no_available_route``). Which role names a node's execution asks
    for is not knowable from the node: a SUBGRAPH node's phases each declare
    their own ``llm_role`` and are compiled only at assembly time, and an AGENT
    node's subagents pick theirs at run time. Enumerating them is therefore not
    an option; covering the whole truth is.

    Swapping the model of every role — rather than substituting one candidate
    role everywhere — is what ``CompareCandidate`` means by "same node, same
    input, only the underlying model differs": each role keeps its own
    ``intent`` params, ``system_prompt_prefix`` and lint requirements, and only
    the model behind it changes. Materialization re-fits those params to the
    candidate's routes (temperature is a share of the route ceiling, reasoning
    effort a level the route sells), which is exactly the per-route fitting
    Settings does on save.

    Accepted trade-off: a phase that deliberately runs on a cheap role also runs
    on the candidate model here. That is the direct consequence of "only the
    model differs" — leaving such a phase on its own model would compare a run
    that is only half swapped — and it costs candidate tokens on phases the
    author picked a cheap model for.

    Roles the truth does not define — the node's effective role, and the
    conventional ``graph_agent`` fallback — are synthesized bare, since there is
    no authored role to inherit params from.
    """
    # Deferred import: the builder lives with the llm router; importing at module
    # load would create a router<->service cycle.
    from app.core.adapters.transport_factory import build_gateway_adapter
    from app.routers.llm import CompareCandidateTestRequest, _compare_candidate_role
    from app.services.llm_credentials import load_credentials
    from app.services.llm_paths import roles_path
    from app.services.llm_roles import load_roles_file

    route = None if candidate.route in (None, "", "auto") else candidate.route
    request = CompareCandidateTestRequest(canonical_id=candidate.model_group_id, route_id=route)
    credentials = load_credentials()
    # Reuses the same transient candidate-role builder the node compare-candidate
    # TEST endpoint uses, so a compared model routes identically to a tested one.
    candidate_groups = _compare_candidate_role(request, credentials).model_groups
    adapter = build_gateway_adapter()

    def _with_candidate_model(role: RoleEntry) -> RoleEntry:
        swapped = role.model_copy(
            update={
                "model_groups": [group.model_copy(deep=True) for group in candidate_groups],
                # The candidate is now the role's only model source; a surviving
                # bundle/profile reference would resolve the original model back
                # into the chain.
                "bundle_id": None,
                "source_profile_id": None,
                "source_profile_snapshot": None,
                "fallback_chain": [],
            }
        )
        # `model_groups` is authoring intent; the engine resolves a role through
        # its `fallback_chain`. Settings materializes on save (PUT
        # /llm/roles/{name}) and a candidate role owes the engine the same
        # executable shape — without this the side-run resolves to nothing.
        return adapter.materialize_role({"role": swapped, "credentials": credentials})

    active_path = roles_path()
    # A missing roles file is first-run empty (same reading as the resolver's own
    # build); a malformed one stays fatal in `load_roles_file`.
    active = load_roles_file(active_path) if active_path.exists() else RolesData()

    roles = {name: _with_candidate_model(role) for name, role in active.roles.items()}
    effective_role = node_effective_role(skill_dir, node_id)
    if effective_role is not None and effective_role not in roles:
        roles[effective_role] = _with_candidate_model(RoleEntry())
    # Bundles and profiles are unreachable once every role's bundle reference is
    # cleared; carrying them would leave the original models named in the file.
    return active.model_copy(update={"roles": roles, "model_bundles": {}, "model_profiles": {}})


def write_candidate_roles_file(
    skill_dir: Path,
    node_id: str,
    candidate: CompareCandidate,
    dest_dir: Path,
) -> Path:
    """Materialize a candidate roles YAML for the single-node side-run worker."""
    from app.services.llm_roles import save_roles_file

    dest_dir.mkdir(parents=True, exist_ok=True)
    roles = build_candidate_roles(skill_dir, node_id, candidate)
    path = dest_dir / f"llm_roles__{candidate.candidate_id}.yaml"
    save_roles_file(path, roles)
    return path
