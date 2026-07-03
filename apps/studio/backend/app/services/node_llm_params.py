"""Per-skill+node persistence for node-level LLM param overrides (PR3).

Stored at ``<skill>/.workspace/node_llm_params.json`` as
``{"nodes": {node_id: {thinking?, max_output_tokens?, temperature?}}}``. Only
nodes carrying at least one non-null override are kept; writing an all-null (or
absent) override removes the node's entry. Mirrors ``compare_candidates.py``.
"""

from __future__ import annotations

import json
from pathlib import Path

from app.models.node_llm_params import NodeLlmParams
from app.services.skills import workspace_dir_for


def node_llm_params_path_for(skill_dir: Path) -> Path:
    return workspace_dir_for(skill_dir) / "node_llm_params.json"


def read_node_llm_params(skill_dir: Path) -> dict[str, NodeLlmParams]:
    """Read the node -> override map, empty when the file is absent/malformed."""
    path = node_llm_params_path_for(skill_dir)
    if not path.exists():
        return {}
    loaded = json.loads(path.read_text(encoding="utf-8"))
    nodes = loaded.get("nodes") if isinstance(loaded, dict) else None
    if not isinstance(nodes, dict):
        return {}
    result: dict[str, NodeLlmParams] = {}
    for node_id, raw in nodes.items():
        if isinstance(raw, dict):
            params = NodeLlmParams.model_validate(raw)
            if not params.is_empty():
                result[node_id] = params
    return result


def _write_all(skill_dir: Path, nodes: dict[str, NodeLlmParams]) -> Path:
    workspace_dir_for(skill_dir).mkdir(parents=True, exist_ok=True)
    path = node_llm_params_path_for(skill_dir)
    payload = {
        "nodes": {
            node_id: params.model_dump(exclude_none=True)
            for node_id, params in sorted(nodes.items())
        }
    }
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def write_node_llm_params(
    skill_dir: Path,
    node_id: str,
    params: NodeLlmParams,
) -> NodeLlmParams:
    """Replace one node's override. An all-null override clears the node entry."""
    nodes = read_node_llm_params(skill_dir)
    if params.is_empty():
        nodes.pop(node_id, None)
    else:
        nodes[node_id] = params
    _write_all(skill_dir, nodes)
    return params
