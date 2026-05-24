"""V0.3.0 runtime state model."""

from __future__ import annotations

from typing import Annotated, Any, TypedDict

from langchain_core.messages import AnyMessage
from langgraph.graph.message import add_messages

from graph_agent.core.exceptions import GraphAgentFatalError


def smart_dict_reducer(
    left: dict[str, Any] | None,
    right: dict[str, Any] | None,
    *,
    merge_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Merge state data with sequential overwrite and explicit parallel conflicts."""

    if not left:
        return dict(right or {})
    if not right:
        return dict(left)

    overlapping = sorted(key for key in right if key in left)
    context = merge_context or {}
    if overlapping and context.get("parallel"):
        source = context.get("source_phase_id", "<unknown>")
        raise GraphAgentFatalError(
            "[F-v3-runtime-state-mapping-failed] parallel branches wrote same key(s): "
            + ", ".join(overlapping)
            + f" source={source!r}"
        )

    merged = dict(left)
    merged.update(right)
    return merged


def shallow_dict_merge(
    left: dict[str, Any] | None,
    right: dict[str, Any] | None,
) -> dict[str, Any]:
    return smart_dict_reducer(left, right)


class GraphRuntimeState(TypedDict, total=False):
    """Shared LangGraph blackboard state for V0.3.0 skills."""

    data: Annotated[dict[str, Any], smart_dict_reducer]
    flow: dict[str, Any]
    messages: Annotated[list[AnyMessage], add_messages]
    run_id: str | None


__all__ = ["GraphRuntimeState", "shallow_dict_merge", "smart_dict_reducer"]
