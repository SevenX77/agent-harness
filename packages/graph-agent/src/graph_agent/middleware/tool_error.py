"""Tool-error handling middleware skeleton for the MVP0 middleware chain."""

from __future__ import annotations

from typing import Any

from langchain.agents import AgentState
from langchain.agents.middleware import AgentMiddleware


class ToolErrorHandlingMiddleware(AgentMiddleware[AgentState[Any]]):
    """No-op tool-error slot reserved by ``MVP0_MIDDLEWARE_ORDER_CONTRACT``."""

    def __init__(self, *, phase_name: str = "unknown") -> None:
        super().__init__()
        self._phase_name = phase_name
