"""Tool-error handling middleware skeleton for the MVP0 middleware chain."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from langchain.agents import AgentState
from langchain.agents.middleware import AgentMiddleware
from langchain_core.messages import ToolMessage
from langgraph.errors import GraphBubbleUp
from langgraph.prebuilt.tool_node import ToolCallRequest
from langgraph.types import Command


class ToolErrorHandlingMiddleware(AgentMiddleware[AgentState[Any]]):
    """Tool-error slot to convert ordinary tool exceptions to error ToolMessage."""

    def __init__(self, *, phase_name: str = "unknown") -> None:
        super().__init__()
        self._phase_name = phase_name

    def wrap_tool_call(
        self,
        request: ToolCallRequest,
        handler: Callable[[ToolCallRequest], ToolMessage | Command[Any]],
    ) -> ToolMessage | Command[Any]:
        try:
            return handler(request)
        except GraphBubbleUp:
            raise
        except Exception as exc:
            tool_name = request.tool_call.get("name", "unknown")
            tool_call_id = request.tool_call.get("id", "")
            exc_type = type(exc).__name__
            exc_msg = str(exc)

            diagnostic = (
                f"Error executing tool '{tool_name}' in phase '{self._phase_name}' "
                f"(call_id: {tool_call_id}): {exc_type}: {exc_msg}"
            )
            return ToolMessage(
                content=diagnostic,
                name=tool_name,
                tool_call_id=tool_call_id,
                status="error",
            )

    async def awrap_tool_call(
        self,
        request: ToolCallRequest,
        handler: Callable[[ToolCallRequest], Awaitable[ToolMessage | Command[Any]]],
    ) -> ToolMessage | Command[Any]:
        try:
            return await handler(request)
        except GraphBubbleUp:
            raise
        except Exception as exc:
            tool_name = request.tool_call.get("name", "unknown")
            tool_call_id = request.tool_call.get("id", "")
            exc_type = type(exc).__name__
            exc_msg = str(exc)

            diagnostic = (
                f"Error executing tool '{tool_name}' in phase '{self._phase_name}' "
                f"(call_id: {tool_call_id}): {exc_type}: {exc_msg}"
            )
            return ToolMessage(
                content=diagnostic,
                name=tool_name,
                tool_call_id=tool_call_id,
                status="error",
            )
