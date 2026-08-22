"""Breakpoint endpoints: which nodes a run stops before.

Addressed per node, because that is how the canvas addresses everything else
(see ``node_llm_params``), and answered with the whole list, because a caller
that is told only about the node it touched has to maintain its own copy of the
rest.

Writes only. Reading breakpoints is reading ``runtime_config``, which the canvas
already holds and already revalidates on this router's own
``runtime_config_changed`` event — a second endpoint for one of that document's
fields would be a second replica of the same truth, free to disagree with the
first (SSOT 读取原则).
"""

from __future__ import annotations

import re

from fastapi import APIRouter

from app.core.exceptions import standard_http_exception
from app.models.breakpoints import BreakpointList
from app.models.errors import ErrorResponse
from app.services.breakpoints import clear_breakpoint, set_breakpoint
from app.services.runtime_config_events import publish_runtime_config_changed
from app.services.skills import resolve_skill_dir

# Prevent pytest from collecting this router module as tests.
__test__ = False

router = APIRouter(prefix="/api/skills/{skill_id}", tags=["breakpoints"])

# Node ids are phase names: start alphanumeric, then word/dot/dash. Blocks path
# traversal (no `/`, `\`, leading `..`).
_NODE_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")


def _validate_node_id(node_id: str) -> str:
    if not _NODE_ID_RE.match(node_id):
        raise standard_http_exception(
            "INVALID_NODE_ID",
            f"Invalid node id: {node_id!r}",
            {"node_id": node_id},
        )
    return node_id


@router.put(
    "/nodes/{node_id}/breakpoint",
    response_model=BreakpointList,
    responses={400: {"model": ErrorResponse}, 404: {"model": ErrorResponse}},
)
async def put_breakpoint(skill_id: str, node_id: str) -> BreakpointList:
    return await _apply(skill_id, node_id, set_it=True)


@router.delete(
    "/nodes/{node_id}/breakpoint",
    response_model=BreakpointList,
    responses={400: {"model": ErrorResponse}, 404: {"model": ErrorResponse}},
)
async def delete_breakpoint(skill_id: str, node_id: str) -> BreakpointList:
    return await _apply(skill_id, node_id, set_it=False)


async def _apply(skill_id: str, node_id: str, *, set_it: bool) -> BreakpointList:
    skill_dir = resolve_skill_dir(skill_id)
    _validate_node_id(node_id)
    apply = set_breakpoint if set_it else clear_breakpoint
    result = apply(skill_dir, node_id)
    if result.changed:
        await publish_runtime_config_changed(
            skill_id=skill_id,
            dataset="breakpoints",
            node_id=node_id,
        )
    return BreakpointList(node_ids=result.node_ids)
