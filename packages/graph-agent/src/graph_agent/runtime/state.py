"""V2.1 runtime state model."""

from __future__ import annotations

from typing import Annotated, Any, TypedDict

from langchain_core.messages import AnyMessage
from langgraph.graph.message import add_messages

from graph_agent.core.exceptions import GraphAgentFatalError


def shallow_dict_merge(
    left: dict[str, Any] | None,
    right: dict[str, Any] | None,
) -> dict[str, Any]:
    """Merge top-level data keys and fail loudly on concurrent conflicts."""

    if not left:
        return dict(right or {})
    if not right:
        return dict(left)

    merged = dict(left)
    for key, value in right.items():
        if key in merged:
            raise GraphAgentFatalError(
                f"[F-v21-state-conflict] key={key!r}: branches wrote same key "
                f"(left={merged[key]!r}, right={value!r})"
            )
        merged[key] = value
    return merged


class BlackboardState(TypedDict, total=False):
    """Shared LangGraph blackboard state for V2.1 skills."""

    data: Annotated[dict[str, Any], shallow_dict_merge]
    flow: dict[str, Any]
    messages: Annotated[list[AnyMessage], add_messages]
    run_id: str | None


__all__ = ["BlackboardState", "shallow_dict_merge"]
