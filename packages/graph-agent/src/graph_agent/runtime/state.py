"""V0.3.0 runtime state model."""

from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
from typing import Annotated, Any, TypedDict

from langchain_core.messages import AnyMessage
from langgraph.graph.message import add_messages

from graph_agent.core.exceptions import GraphAgentFatalError


class BlackboardData(TypedDict, total=False):
    """Normalized V0.3.0 blackboard data regions."""

    inputs: dict[str, Any]
    phase_outputs: dict[str, dict[str, Any]]
    scratch: dict[str, Any]


def normalize_blackboard_data(data: Mapping[str, Any] | None) -> BlackboardData:
    """Return data in the V0.3.0 inputs/phase_outputs/scratch shape."""

    raw = dict(data or {})
    if any(key in raw for key in ("inputs", "phase_outputs", "scratch")):
        inputs = raw.get("inputs")
        phase_outputs = raw.get("phase_outputs")
        scratch = raw.get("scratch")
        return {
            "inputs": deepcopy(inputs) if isinstance(inputs, dict) else {},
            "phase_outputs": deepcopy(phase_outputs) if isinstance(phase_outputs, dict) else {},
            "scratch": deepcopy(scratch) if isinstance(scratch, dict) else {},
        }
    return {"inputs": raw, "phase_outputs": {}, "scratch": {}}


def blackboard_data_merge(
    left: Mapping[str, Any] | None,
    right: Mapping[str, Any] | None,
) -> BlackboardData:
    """Merge normalized blackboard data and fail loudly on ambiguous writes."""

    if not left and not right:
        return {}
    if not left:
        return normalize_blackboard_data(right)
    if not right:
        return normalize_blackboard_data(left)

    left_data = normalize_blackboard_data(left)
    right_data = normalize_blackboard_data(right)
    merged = normalize_blackboard_data(left_data)

    if right_data["inputs"]:
        if merged["inputs"] and merged["inputs"] != right_data["inputs"]:
            raise GraphAgentFatalError(
                "[F-v3-runtime-state-mapping-failed] data.inputs is read-only after initialization"
            )
        merged["inputs"] = dict(right_data["inputs"])

    for phase_id, output in right_data["phase_outputs"].items():
        if phase_id in merged["phase_outputs"]:
            raise GraphAgentFatalError(
                f"[F-v3-state-conflict] phase_outputs[{phase_id!r}] written more than once"
            )
        merged["phase_outputs"][phase_id] = deepcopy(output)

    for key, value in right_data["scratch"].items():
        if key in merged["scratch"]:
            raise GraphAgentFatalError(
                f"[F-v3-state-conflict] scratch key={key!r} written more than once"
            )
        merged["scratch"][key] = deepcopy(value)
    return merged


shallow_dict_merge = blackboard_data_merge


class BlackboardState(TypedDict, total=False):
    """Shared LangGraph blackboard state for V0.3.0 skills."""

    data: Annotated[BlackboardData, blackboard_data_merge]
    flow: dict[str, Any]
    messages: Annotated[list[AnyMessage], add_messages]
    run_id: str | None


__all__ = [
    "BlackboardData",
    "BlackboardState",
    "blackboard_data_merge",
    "normalize_blackboard_data",
    "shallow_dict_merge",
]
