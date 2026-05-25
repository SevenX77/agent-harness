"""Compatibility wrapper for the CognitiveFlow ask_clarification path."""

from __future__ import annotations

from typing import Any

from langchain.agents import AgentState

from graph_agent.core.io_manager import IOManager
from graph_agent.middleware.cognitive_flow import CognitiveFlowMiddleware


class ClarificationMiddlewareState(AgentState[Any]):
    """Compatible state schema for old clarification middleware imports."""


class ClarificationMiddleware(CognitiveFlowMiddleware):
    """Thin compatibility wrapper; logic lives in ``CognitiveFlowMiddleware``."""

    state_schema = ClarificationMiddlewareState

    def __init__(self) -> None:
        super().__init__(IOManager([]))
