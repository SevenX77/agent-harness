"""Per-skill+node persistence for model-compare candidates (PR2).

Stored at ``<skill>/.workspace/compare_candidates.json`` as
``{"nodes": {node_id: [candidate, ...]}}``. Only non-empty nodes are kept;
writing an empty list for a node removes its entry. Mirrors the
``local_settings.py`` read/write shape.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from pathlib import Path

from app.models.model_compare import CompareCandidate
from app.services.skills import workspace_dir_for


def compare_candidates_path_for(skill_dir: Path) -> Path:
    return workspace_dir_for(skill_dir) / "compare_candidates.json"


def read_compare_candidates(skill_dir: Path) -> dict[str, list[CompareCandidate]]:
    """Read the node -> candidates map, empty when the file is absent/malformed."""
    path = compare_candidates_path_for(skill_dir)
    if not path.exists():
        return {}
    loaded = json.loads(path.read_text(encoding="utf-8"))
    nodes = loaded.get("nodes") if isinstance(loaded, dict) else None
    if not isinstance(nodes, dict):
        return {}
    result: dict[str, list[CompareCandidate]] = {}
    for node_id, raw in nodes.items():
        if isinstance(raw, list):
            result[node_id] = [CompareCandidate.model_validate(item) for item in raw]
    return result


def _write_all(skill_dir: Path, nodes: dict[str, list[CompareCandidate]]) -> Path:
    workspace_dir_for(skill_dir).mkdir(parents=True, exist_ok=True)
    path = compare_candidates_path_for(skill_dir)
    payload = {
        "nodes": {
            node_id: [c.model_dump() for c in cands]
            for node_id, cands in sorted(nodes.items())
        }
    }
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def write_node_compare_candidates(
    skill_dir: Path,
    node_id: str,
    candidates: Sequence[CompareCandidate],
) -> list[CompareCandidate]:
    """Replace one node's candidate list. An empty list removes the node entry."""
    nodes = read_compare_candidates(skill_dir)
    stored = list(candidates)
    if stored:
        nodes[node_id] = stored
    else:
        nodes.pop(node_id, None)
    _write_all(skill_dir, nodes)
    return stored
