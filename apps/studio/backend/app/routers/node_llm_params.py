"""Node-level LLM param override persistence endpoints (PR3).

Overrides are the three role-level generation params (thinking /
max_output_tokens / temperature) applied per node, stored per skill+node under
``.workspace/runtime_config.json``. The run-time resolver seam that applies
them lives with the run endpoints (wired by the orchestrator).
"""

from __future__ import annotations

import re

from fastapi import APIRouter

from app.core.exceptions import standard_http_exception
from app.models.errors import ErrorResponse
from app.models.node_llm_params import NodeLlmParams, NodeLlmParamsMap
from app.services.node_llm_params import (
    read_node_llm_params,
    write_node_llm_params,
)
from app.services.skills import resolve_skill_dir

# Prevent pytest from collecting this router module as tests.
__test__ = False

router = APIRouter(prefix="/api/skills/{skill_id}", tags=["node-llm-params"])

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


@router.get(
    "/node-llm-params",
    response_model=NodeLlmParamsMap,
    responses={404: {"model": ErrorResponse}},
)
async def get_node_llm_params(skill_id: str) -> NodeLlmParamsMap:
    skill_dir = resolve_skill_dir(skill_id)
    return NodeLlmParamsMap(nodes=read_node_llm_params(skill_dir))


@router.put(
    "/nodes/{node_id}/node-llm-params",
    response_model=NodeLlmParams,
    responses={400: {"model": ErrorResponse}, 404: {"model": ErrorResponse}},
)
async def put_node_llm_params(
    skill_id: str,
    node_id: str,
    request: NodeLlmParams,
) -> NodeLlmParams:
    skill_dir = resolve_skill_dir(skill_id)
    _validate_node_id(node_id)
    return write_node_llm_params(skill_dir, node_id, request)
