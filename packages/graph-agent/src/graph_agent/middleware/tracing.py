"""Tracing slot for the MVP0 middleware chain."""

from __future__ import annotations

import json
import uuid
from collections.abc import Awaitable, Callable, Sequence
from typing import Any

from langchain.agents import AgentState
from langchain.agents.middleware import AgentMiddleware
from langchain_core.messages import ToolMessage
from langgraph.prebuilt.tool_node import ToolCallRequest
from langgraph.types import Command

from graph_agent.callbacks.base import Callback
from graph_agent.tracing import StepReporter

ToolCallResult = ToolMessage | Command[Any]


class TracingMiddleware(AgentMiddleware[AgentState[Any]]):
    """Reports the tool calls it wraps as steps.

    It sits around the tool's execution, so it is the one place in the agent
    path that can say "this call is starting" as opposed to "this call ran".
    What a step looks like once reported is not its business — that belongs to
    the reporter it hands the call to.
    """

    def __init__(
        self,
        *,
        callbacks: Sequence[Callback] | None = None,
        phase_name: str = "unknown",
    ) -> None:
        super().__init__()
        self._reporter = StepReporter(callbacks=tuple(callbacks or ()), phase_name=phase_name)

    def wrap_tool_call(
        self,
        request: ToolCallRequest,
        handler: Callable[[ToolCallRequest], ToolCallResult],
    ) -> ToolCallResult:
        with self._step(request) as step:
            result = handler(request)
            _report_result(step, result)
            return result

    async def awrap_tool_call(
        self,
        request: ToolCallRequest,
        handler: Callable[[ToolCallRequest], Awaitable[ToolCallResult]],
    ) -> ToolCallResult:
        with self._step(request) as step:
            result = await handler(request)
            _report_result(step, result)
            return result

    def _step(self, request: ToolCallRequest) -> Any:
        return self._reporter.tool_call(
            tool_call_id=request.tool_call.get("id") or uuid.uuid4().hex,
            tool_name=request.tool_call.get("name", "unknown"),
            args=_tool_args(request),
        )


def _report_result(step: Any, result: ToolCallResult) -> None:
    """Close the step only when the tool answered with a message.

    A tool answering with a ``Command`` steers the graph instead of replying,
    so there is no result text to report and the step stays open here; the
    agent node reports that call from the message list afterwards.
    """
    if isinstance(result, ToolMessage):
        step.finished(_result_content(result))


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
