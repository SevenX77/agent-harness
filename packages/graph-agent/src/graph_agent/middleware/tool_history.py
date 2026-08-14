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
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from typing import Any

from langchain.agents.middleware import AgentMiddleware, ModelRequest
from langchain_core.messages import AIMessage, ToolMessage

from graph_agent.callbacks.emit import _safe_emit_event
from graph_agent.callbacks.events import ToolHistoryRepairedEvent

logger = logging.getLogger(__name__)


@dataclass
class RepairReport:
    """What the repair actually did to the history — the event's raw material."""

    #: Tool names of orphaned tool_calls that got a synthetic ToolMessage.
    synthesized: list[str] = field(default_factory=list)
    #: Stray ToolMessages (answering nothing in this history) that were dropped.
    dropped: int = 0

    @property
    def changed_meaningfully(self) -> bool:
        return bool(self.synthesized) or self.dropped > 0

_ORPHAN_NOTICE = (
    "[系统] 该工具调用未获得独立结果:同一轮的提交已被系统处理,"
    "请阅读随后的反馈消息并继续。"
)


def _repair_orphaned_tool_calls(
    messages: list[Any],
    report: RepairReport | None = None,
) -> list[Any]:
    """Enforce the provider contract: each AI(tool_calls) is IMMEDIATELY
    followed by one ToolMessage per id. Existing responses are moved up into
    adjacency (inner-loop jumps can interleave a later model reply between a
    submission and its feedback); only truly missing ones are synthesised.

    ``report``, when given, collects what changed so the middleware can say it
    out loud (glass-box decision 2026-08-13 D4)."""
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
            if report is not None:
                report.dropped += 1
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
                if report is not None:
                    report.synthesized.append(str(tool_call.get("name") or "tool"))
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

    def __init__(
        self,
        *,
        phase_name: str = "unknown",
        callbacks: Sequence[Any] | None = None,
    ) -> None:
        super().__init__()
        self._phase_name = phase_name
        self._callbacks = callbacks

    def _repaired_request(self, request: ModelRequest) -> ModelRequest:
        messages = list(request.messages)
        report = RepairReport()
        repaired = _repair_orphaned_tool_calls(messages, report)
        changed = repaired != messages
        logger.debug(
            "phase=tool_history action=wrap_model_call messages=%d repaired=%s",
            len(messages),
            changed,
        )
        # Rewriting what the model sees is a decision; re-ordering existing
        # answers into adjacency preserves content and stays quiet (发决定不发路过).
        if report.changed_meaningfully:
            _safe_emit_event(
                self._callbacks,
                ToolHistoryRepairedEvent(
                    phase_name=self._phase_name,
                    synthesized_count=len(report.synthesized),
                    dropped_count=report.dropped,
                    message=_repair_sentence(self._phase_name, report),
                ),
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


def _repair_sentence(phase_name: str, report: RepairReport) -> str:
    acts: list[str] = []
    if report.synthesized:
        acts.append(
            f"synthesized {len(report.synthesized)} placeholder result(s) for unanswered "
            f"tool call(s) ({', '.join(sorted(set(report.synthesized)))})"
        )
    if report.dropped:
        acts.append(f"dropped {report.dropped} stray tool message(s) answering nothing")
    return (
        f"Repaired the outgoing message history in phase {phase_name!r}: "
        + "; ".join(acts)
        + ". The provider rejects histories where a tool call has no adjacent result."
    )
