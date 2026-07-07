"""Per-skill+node persistence for model-compare candidates (PR2)."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from app.models.model_compare import CompareCandidate
from app.services.runtime_config import read_runtime_config, update_compare_candidates_payload


@dataclass(frozen=True)
class CompareCandidatesWriteResult:
    value: list[CompareCandidate]
    changed: bool


def read_compare_candidates(skill_dir: Path) -> dict[str, list[CompareCandidate]]:
    """Read the node -> candidates map from runtime_config."""
    loaded = read_runtime_config(skill_dir)
    llm = loaded.get("llm") if isinstance(loaded, dict) else None
    compare = llm.get("compare_candidates") if isinstance(llm, dict) else None
    nodes = compare.get("nodes") if isinstance(compare, dict) else None
    if not isinstance(nodes, dict):
        return {}
    result: dict[str, list[CompareCandidate]] = {}
    for node_id, raw in nodes.items():
        if isinstance(raw, list):
            result[node_id] = [CompareCandidate.model_validate(item) for item in raw]
    return result


def write_node_compare_candidates(
    skill_dir: Path,
    node_id: str,
    candidates: Sequence[CompareCandidate],
) -> CompareCandidatesWriteResult:
    """Replace one node's candidate list. An empty list removes the node entry."""
    nodes = read_compare_candidates(skill_dir)
    before = dict(nodes)
    stored = list(candidates)
    if stored:
        nodes[node_id] = stored
    else:
        nodes.pop(node_id, None)
    if nodes == before:
        return CompareCandidatesWriteResult(value=stored, changed=False)
    update_compare_candidates_payload(
        skill_dir,
        {node: [candidate.model_dump() for candidate in cands] for node, cands in nodes.items()},
    )
    return CompareCandidatesWriteResult(value=stored, changed=True)
