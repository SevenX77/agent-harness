"""V2.1 runtime state model."""

from __future__ import annotations

from typing import Annotated, Any, TypedDict

from langchain_core.messages import AnyMessage
from langgraph.graph.message import add_messages


class BlackboardState(TypedDict, total=False):
    """Shared LangGraph blackboard state for V2.1 skills."""

    data: dict[str, Any]
    flow: dict[str, Any]
    messages: Annotated[list[AnyMessage], add_messages]
    run_id: str | None


__all__ = ["BlackboardState"]
