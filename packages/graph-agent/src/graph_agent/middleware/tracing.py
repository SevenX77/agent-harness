"""Tracing middleware skeleton for the MVP0 middleware chain."""

from __future__ import annotations

import json
import logging
import time
from collections.abc import Awaitable, Callable, Sequence
from typing import Any

from langchain.agents import AgentState
from langchain.agents.middleware import AgentMiddleware
from langchain_core.messages import ToolMessage
from langgraph.prebuilt.tool_node import ToolCallRequest
from langgraph.types import Command

from graph_agent.callbacks.base import Callback
from graph_agent.callbacks.events import ToolCallEvent

logger = logging.getLogger(__name__)
ToolCallResult = ToolMessage | Command[Any]


class TracingMiddleware(AgentMiddleware[AgentState[Any]]):
    """Tracing slot to capture tool calls and emit ToolCallEvents."""

    def __init__(
        self,
        *,
        callbacks: Sequence[Callback] | None = None,
        phase_name: str = "unknown",
    ) -> None:
        super().__init__()
        self._callbacks = list(callbacks or [])
        self._phase_name = phase_name

    def wrap_tool_call(
        self,
        request: ToolCallRequest,
        handler: Callable[[ToolCallRequest], ToolCallResult],
    ) -> ToolCallResult:
        start_time = time.perf_counter()
        result = handler(request)
        return self._record_tool_result(request, result, start_time)

    async def awrap_tool_call(
        self,
        request: ToolCallRequest,
        handler: Callable[[ToolCallRequest], Awaitable[ToolCallResult]],
    ) -> ToolCallResult:
        start_time = time.perf_counter()
        result = await handler(request)
        return self._record_tool_result(request, result, start_time)

    def _record_tool_result(
        self,
        request: ToolCallRequest,
        result: ToolCallResult,
        start_time: float,
    ) -> ToolCallResult:
        duration_ms = (time.perf_counter() - start_time) * 1000.0
        if isinstance(result, ToolMessage):
            self._emit_tool_call_event(request, result, duration_ms)
        return result

    def _emit_tool_call_event(
        self,
        request: ToolCallRequest,
        result: ToolMessage,
        duration_ms: float,
    ) -> None:
        if not self._callbacks:
            return

        tool_name = request.tool_call.get("name", "unknown")
        args = _tool_args(request)
        result_content = _result_content(result)
        event = ToolCallEvent(
            phase_name=self._phase_name,
            tool_name=tool_name,
            args=args,
            result=result_content,
            duration_ms=duration_ms,
            parent_node_id=None,
            node_type="tool",
        )

        for cb in self._callbacks:
            try:
                if hasattr(cb, "on_event"):
                    cb.on_event(event)
                elif hasattr(cb, "on_tool_call"):
                    cb.on_tool_call(
                        self._phase_name,
                        tool_name,
                        args,
                        result_content,
                        duration_ms=duration_ms,
                    )
            except Exception as e:
                logger.warning(
                    "[Tracing] callback %s error on dispatch: %s",
                    type(cb).__name__,
                    e,
                )


def _tool_args(request: ToolCallRequest) -> dict[str, Any]:
    args = request.tool_call.get("args", {})
    if isinstance(args, dict):
        return args
    return {"args": args}


def _result_content(result: ToolMessage) -> str:
    if isinstance(result.content, str):
        return result.content
    try:
        return json.dumps(result.content, sort_keys=True, default=str)
    except Exception:
        return str(result.content)
