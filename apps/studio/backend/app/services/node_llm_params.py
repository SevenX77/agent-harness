"""Per-skill+node persistence for node-level LLM param overrides."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from app.models.node_llm_params import NodeLlmParams
from app.services.runtime_config import read_runtime_config, update_node_llm_params_payload


@dataclass(frozen=True)
class NodeLlmParamsWriteResult:
    value: NodeLlmParams
    changed: bool


def read_node_llm_params(skill_dir: Path) -> dict[str, NodeLlmParams]:
    """Read the node -> active override map from runtime_config."""
    loaded = read_runtime_config(skill_dir)
    llm = loaded.get("llm") if isinstance(loaded, dict) else None
    node_params = llm.get("node_params") if isinstance(llm, dict) else None
    nodes = node_params.get("nodes") if isinstance(node_params, dict) else None
    if not isinstance(nodes, dict):
        return {}
    result: dict[str, NodeLlmParams] = {}
    for node_id, raw in nodes.items():
        if isinstance(raw, dict):
            params = NodeLlmParams.model_validate(raw)
            if not params.is_empty():
                result[node_id] = params
    return result


def write_node_llm_params(
    skill_dir: Path,
    node_id: str,
    params: NodeLlmParams,
) -> NodeLlmParamsWriteResult:
    """Replace one node's override; empty disabled params clear the node entry."""
    nodes = read_node_llm_params(skill_dir)
    before = dict(nodes)
    if params.is_empty():
        nodes.pop(node_id, None)
    else:
        nodes[node_id] = params
    if nodes == before:
        return NodeLlmParamsWriteResult(value=params, changed=False)
    update_node_llm_params_payload(
        skill_dir,
        {node: value.model_dump(exclude_none=True) for node, value in nodes.items()},
    )
    return NodeLlmParamsWriteResult(value=params, changed=True)
