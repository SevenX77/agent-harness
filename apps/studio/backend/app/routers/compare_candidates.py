"""Node-level Compare LLMs candidate persistence endpoints (PR2).

Candidates are model-only (model group + endpoint route) and are stored per
skill+node under ``.workspace/compare_candidates.json``. Distinct from
``routers/compare.py`` (golden diff). The run-time side-run wiring that consumes
these candidates lives with the run endpoints.
"""

from __future__ import annotations

import re

from fastapi import APIRouter

from app.core.exceptions import standard_http_exception
from app.models.errors import ErrorResponse
from app.models.model_compare import CompareCandidatesMap, NodeCompareCandidates
from app.services.compare_candidates import (
    read_compare_candidates,
    write_node_compare_candidates,
)
from app.services.skills import resolve_skill_dir

# Prevent pytest from collecting this router module as tests.
__test__ = False

router = APIRouter(prefix="/api/skills/{skill_id}", tags=["compare-candidates"])

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
    "/compare-candidates",
    response_model=CompareCandidatesMap,
    responses={404: {"model": ErrorResponse}},
)
async def get_compare_candidates(skill_id: str) -> CompareCandidatesMap:
    skill_dir = resolve_skill_dir(skill_id)
    return CompareCandidatesMap(nodes=read_compare_candidates(skill_dir))


@router.put(
    "/nodes/{node_id}/compare-candidates",
    response_model=NodeCompareCandidates,
    responses={400: {"model": ErrorResponse}, 404: {"model": ErrorResponse}},
)
async def put_node_compare_candidates(
    skill_id: str,
    node_id: str,
    request: NodeCompareCandidates,
) -> NodeCompareCandidates:
    skill_dir = resolve_skill_dir(skill_id)
    _validate_node_id(node_id)
    stored = write_node_compare_candidates(skill_dir, node_id, request.candidates)
    return NodeCompareCandidates(candidates=stored)
