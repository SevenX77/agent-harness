"""Tool-error handling middleware skeleton for the MVP0 middleware chain."""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Sequence
from typing import Any

from langchain.agents import AgentState
from langchain.agents.middleware import AgentMiddleware
from langchain_core.messages import ToolMessage
from langgraph.errors import GraphBubbleUp
from langgraph.prebuilt.tool_node import ToolCallRequest
from langgraph.types import Command

from graph_agent.callbacks.emit import _safe_emit_event
from graph_agent.callbacks.events import ToolErrorHandledEvent


class ToolErrorHandlingMiddleware(AgentMiddleware[AgentState[Any]]):
    """Tool-error slot to convert ordinary tool exceptions to error ToolMessage."""

    def __init__(
        self,
        *,
        phase_name: str = "unknown",
        callbacks: Sequence[Any] | None = None,
    ) -> None:
        super().__init__()
        self._phase_name = phase_name
        self._callbacks = callbacks

    def _say_error_handled(self, request: ToolCallRequest, exc: Exception) -> None:
        """Swallowing an error steers the run — the model reads the converted
        message as feedback — so the swallow announces itself (D4)."""
        tool_name = str(request.tool_call.get("name") or "unknown")
        _safe_emit_event(
            self._callbacks,
            ToolErrorHandledEvent(
                phase_name=self._phase_name,
                tool_name=tool_name,
                error=f"{type(exc).__name__}: {exc}",
                message=(
                    f"Tool {tool_name!r} raised {type(exc).__name__} in phase "
                    f"{self._phase_name!r}; converted it into an error message "
                    "for the model to read and recover from."
                ),
            ),
        )

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
            self._say_error_handled(request, exc)
            return _error_tool_message(self._phase_name, request, exc)

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
            self._say_error_handled(request, exc)
            return _error_tool_message(self._phase_name, request, exc)


def _error_tool_message(
    phase_name: str,
    request: ToolCallRequest,
    exc: Exception,
) -> ToolMessage:
    tool_name = str(request.tool_call.get("name") or "unknown")
    tool_call_id = str(request.tool_call.get("id") or "")
    diagnostic = (
        f"Error executing tool '{tool_name}' in phase '{phase_name}' "
        f"(call_id: {tool_call_id}): {type(exc).__name__}: {exc}"
    )
    return ToolMessage(
        content=diagnostic,
        name=tool_name,
        tool_call_id=tool_call_id,
        status="error",
    )
