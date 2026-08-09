"""Tracing middleware skeleton for the MVP0 middleware chain."""

from __future__ import annotations

import json
import logging
import time
import uuid
from collections.abc import Awaitable, Callable, Sequence
from typing import Any

from langchain.agents import AgentState
from langchain.agents.middleware import AgentMiddleware
from langchain_core.messages import ToolMessage
from langgraph.prebuilt.tool_node import ToolCallRequest
from langgraph.types import Command

from graph_agent.callbacks.base import Callback
from graph_agent.callbacks.events import CallbackEvent, ToolCallEvent, ToolCallStartedEvent

logger = logging.getLogger(__name__)
ToolCallResult = ToolMessage | Command[Any]


class TracingMiddleware(AgentMiddleware[AgentState[Any]]):
    """Tracing slot that reports a tool call at both ends.

    It sits around the tool's execution, so it is the one place in the agent
    path that can say "this call is starting" as opposed to "this call ran".
    """

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
        tool_call_id = self._announce_tool_call(request)
        start_time = time.perf_counter()
        result = handler(request)
        return self._record_tool_result(request, result, start_time, tool_call_id)

    async def awrap_tool_call(
        self,
        request: ToolCallRequest,
        handler: Callable[[ToolCallRequest], Awaitable[ToolCallResult]],
    ) -> ToolCallResult:
        tool_call_id = self._announce_tool_call(request)
        start_time = time.perf_counter()
        result = await handler(request)
        return self._record_tool_result(request, result, start_time, tool_call_id)

    def _announce_tool_call(self, request: ToolCallRequest) -> str:
        """Emit the started event and return the identity both halves share.

        This runs for every tool the middleware wraps, including tools whose
        result is a ``Command`` rather than a ``ToolMessage`` — those have their
        completion reported by the agent node instead, which is no reason to
        withhold the announcement. Tools that CognitiveFlow answers itself
        (``finish_task``, ``ask_clarification``) never reach this middleware at
        all, so they are not announced anywhere; see the e2e test that pins it.
        """
        tool_call_id = request.tool_call.get("id") or uuid.uuid4().hex
        self._dispatch(
            ToolCallStartedEvent(
                tool_call_id=tool_call_id,
                phase_name=self._phase_name,
                tool_name=request.tool_call.get("name", "unknown"),
                args=_tool_args(request),
                parent_node_id=None,
                node_type="tool",
            )
        )
        return tool_call_id

    def _record_tool_result(
        self,
        request: ToolCallRequest,
        result: ToolCallResult,
        start_time: float,
        tool_call_id: str,
    ) -> ToolCallResult:
        duration_ms = (time.perf_counter() - start_time) * 1000.0
        if isinstance(result, ToolMessage):
            self._emit_tool_call_event(request, result, duration_ms, tool_call_id)
        return result

    def _emit_tool_call_event(
        self,
        request: ToolCallRequest,
        result: ToolMessage,
        duration_ms: float,
        tool_call_id: str,
    ) -> None:
        if not self._callbacks:
            return

        tool_name = request.tool_call.get("name", "unknown")
        args = _tool_args(request)
        result_content = _result_content(result)
        event = ToolCallEvent(
            tool_call_id=tool_call_id,
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

    def _dispatch(self, event: CallbackEvent) -> None:
        """Send a typed-only event down the on_event channel.

        Unlike ``ToolCallEvent`` there is no legacy ``on_*`` hook to fall back
        to here — a callback that predates the typed channel simply does not
        learn about starts.
        """
        for cb in self._callbacks:
            on_event = getattr(cb, "on_event", None)
            if on_event is None:
                continue
            try:
                on_event(event)
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
