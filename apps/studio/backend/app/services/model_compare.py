"""Node-level model-compare mechanics (PR2): isolated single-node side-runs.

The engine cannot execute two in-graph nodes in the same superstep
(``WorkflowState.data`` is a reducerless LastValue channel), so compare does NOT
inject a parallel graph node. Instead, for each candidate we:

1. take the compare node's real input slice from the base run's
   ``input_dispatch`` event (:func:`extract_node_input`),
2. materialize a single-phase skill variant that runs just that node
   (:func:`materialize_single_node_skill`),
3. bind that node's effective role to the candidate model in a temp roles file
   (:func:`write_candidate_roles_file`),

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
from app.models.llm_config import RolesData
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
        raise ValueError(f"node {node_id!r} not found in skill {skill_dir}")
    io = getattr(doc.ast, "io", None)
    if io is None:
        raise ValueError(f"node {node_id!r} has no declared io; cannot compare")
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


def node_effective_role(skill_dir: Path, node_id: str) -> str:
    """The role name ``node_id`` resolves to (PR1 layering), for roles binding."""
    compiled = compile_skill(skill_dir, cache=False)
    doc = next((n for n in compiled.nodes if n.phase_name == node_id), None)
    if doc is None:
        raise ValueError(f"node {node_id!r} not found in skill {skill_dir}")
    if isinstance(doc.ast, AgentNodeAST):
        return effective_llm_role(doc.ast, compiled.manifest.llm_role)
    # logic/subgraph nodes have no llm_role; fall back to the conventional role.
    return compiled.manifest.llm_role or "graph_agent"


def build_candidate_roles(
    skill_dir: Path,
    node_id: str,
    candidate: CompareCandidate,
) -> RolesData:
    """Roles data binding the node's effective role + graph_agent to ``candidate``.

    Reuses the same transient candidate-role builder the node compare-candidate
    TEST endpoint uses, so a compared model routes identically to a tested one.
    """
    # Deferred import: the builder lives with the llm router; importing at module
    # load would create a router<->service cycle.
    from app.core.adapters.transport_factory import build_gateway_adapter
    from app.routers.llm import CompareCandidateTestRequest, _compare_candidate_role
    from app.services.llm_credentials import load_credentials

    route = None if candidate.route in (None, "", "auto") else candidate.route
    request = CompareCandidateTestRequest(canonical_id=candidate.model_group_id, route_id=route)
    credentials = load_credentials()
    # `model_groups` is authoring intent; the engine resolves a role through its
    # `fallback_chain`. Settings materializes on save (PUT /llm/roles/{name}) and
    # a candidate role owes the engine the same executable shape — without this
    # the side-run resolves to nothing and dies with `resource.no_available_route`.
    role_entry = build_gateway_adapter().materialize_role(
        {
            "role": _compare_candidate_role(request, credentials),
            "credentials": credentials,
        }
    )

    effective = node_effective_role(skill_dir, node_id)
    roles = {effective: role_entry.model_copy(deep=True)}
    # Bind the conventional fallback too, so resolution lands on the candidate
    # regardless of the node's layering outcome.
    roles.setdefault("graph_agent", role_entry.model_copy(deep=True))
    return RolesData(roles=roles)


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
