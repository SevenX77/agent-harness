"""Node-level model-compare (PR2) request/response models.

Compare candidates are *model-only* (a model group + one endpoint route) and are
attached to a specific node. They are persisted per skill+node in the skill
workspace, and consumed to launch isolated single-node side-runs at run time.
Distinct from ``models/compare.py`` (golden diff) — that is a different feature.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class CompareCandidate(BaseModel):
    """One model candidate for a node's Compare LLMs block.

    ``model_group_id`` names a model group from Settings; ``route`` is either the
    sentinel ``"auto"`` (let the group's fallback order decide) or a specific
    endpoint route id. No role/bundle — comparison means "same node, same input,
    only the underlying model differs".
    """

    model_config = ConfigDict(extra="forbid")

    candidate_id: str = Field(..., min_length=1)
    model_group_id: str = Field(..., min_length=1)
    route: str = "auto"


class NodeCompareCandidates(BaseModel):
    """PUT body / per-node response: the candidate list for one node."""

    model_config = ConfigDict(extra="forbid")

    candidates: list[CompareCandidate] = Field(default_factory=list)


class CompareCandidatesMap(BaseModel):
    """GET response: node id -> its candidate list (only non-empty nodes)."""

    model_config = ConfigDict(extra="forbid")

    nodes: dict[str, list[CompareCandidate]] = Field(default_factory=dict)
