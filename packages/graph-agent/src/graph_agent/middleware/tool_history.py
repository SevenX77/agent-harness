"""Guarantee protocol-legal tool history on every outgoing model request.

OpenAI-protocol providers reject any history where an assistant message with
tool_calls is not followed by tool messages answering each tool_call_id
(HTTP 400 "insufficient tool messages following tool_calls message"). Several
inner-loop paths can legally jump back to the model while the latest
AI(tool_calls) is still unanswered — e.g. CognitiveFlow's finish_task
rejection Command(goto="model") racing a parallel second call, or
ExitControl's after_agent nudge. The model boundary is the single exit where
the provider contract must hold, so the repair lives here: any orphaned
tool_call gets a synthetic ToolMessage before the request leaves the engine.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from langchain.agents.middleware import AgentMiddleware, ModelRequest
from langchain_core.messages import AIMessage, ToolMessage

_ORPHAN_NOTICE = (
    "[系统] 该工具调用未获得独立结果:同一轮的提交已被系统处理,"
    "请阅读随后的反馈消息并继续。"
)


def _repair_orphaned_tool_calls(messages: list[Any]) -> list[Any]:
    repaired: list[Any] = []
    for message in messages:
        repaired.append(message)
        if not isinstance(message, AIMessage) or not message.tool_calls:
            continue
        position = len(repaired)
        answered_after = {
            later.tool_call_id
            for later in messages[position:]
            if isinstance(later, ToolMessage)
        }
        for tool_call in message.tool_calls:
            call_id = tool_call.get("id")
            if call_id and call_id not in answered_after:
                repaired.append(
                    ToolMessage(
                        content=_ORPHAN_NOTICE,
                        name=str(tool_call.get("name") or "tool"),
                        tool_call_id=call_id,
                        status="error",
                    )
                )
    return repaired


class ToolHistoryIntegrityMiddleware(AgentMiddleware):
    """Per-model-call repair of unanswered tool_calls in the request history."""

    def wrap_model_call(
        self,
        request: ModelRequest,
        handler: Callable[[ModelRequest], Any],
    ) -> Any:
        messages = list(request.messages)
        repaired = _repair_orphaned_tool_calls(messages)
        if len(repaired) != len(messages):
            request = request.override(messages=repaired)
        return handler(request)
