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

import logging
from collections.abc import Callable
from typing import Any

from langchain.agents.middleware import AgentMiddleware, ModelRequest
from langchain_core.messages import AIMessage, ToolMessage

logger = logging.getLogger(__name__)

_ORPHAN_NOTICE = (
    "[系统] 该工具调用未获得独立结果:同一轮的提交已被系统处理,"
    "请阅读随后的反馈消息并继续。"
)


def _repair_orphaned_tool_calls(messages: list[Any]) -> list[Any]:
    """Enforce the provider contract: each AI(tool_calls) is IMMEDIATELY
    followed by one ToolMessage per id. Existing responses are moved up into
    adjacency (inner-loop jumps can interleave a later model reply between a
    submission and its feedback); only truly missing ones are synthesised."""
    consumed: set[int] = set()
    repaired: list[Any] = []
    for position, message in enumerate(messages):
        if id(message) in consumed:
            continue
        if isinstance(message, ToolMessage):
            # Reached here means no assistant message claimed it: a stray
            # replay of an already-answered call. Providers reject a tool
            # message that does not follow its tool_calls message.
            logger.debug(
                "phase=tool_history action=drop_stray_tool_message id=%s",
                message.tool_call_id,
            )
            continue
        repaired.append(message)
        if not isinstance(message, AIMessage) or not message.tool_calls:
            continue
        for tool_call in message.tool_calls:
            call_id = tool_call.get("id")
            if not call_id:
                continue
            response = next(
                (
                    later
                    for later in messages[position + 1 :]
                    if isinstance(later, ToolMessage)
                    and later.tool_call_id == call_id
                    and id(later) not in consumed
                ),
                None,
            )
            if response is not None:
                consumed.add(id(response))
                repaired.append(response)
            else:
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

    def _repaired_request(self, request: ModelRequest) -> ModelRequest:
        messages = list(request.messages)
        repaired = _repair_orphaned_tool_calls(messages)
        changed = repaired != messages
        logger.debug(
            "phase=tool_history action=wrap_model_call messages=%d repaired=%s",
            len(messages),
            changed,
        )
        if changed:
            request = request.override(messages=repaired)
        return request

    def wrap_model_call(
        self,
        request: ModelRequest,
        handler: Callable[[ModelRequest], Any],
    ) -> Any:
        return handler(self._repaired_request(request))

    async def awrap_model_call(
        self,
        request: ModelRequest,
        handler: Callable[[ModelRequest], Any],
    ) -> Any:
        # The runtime dispatches async graph executions to the async hook only;
        # without this counterpart the repair silently never runs there (the
        # sibling CognitiveFlow middleware ships both for the same reason).
        return await handler(self._repaired_request(request))
