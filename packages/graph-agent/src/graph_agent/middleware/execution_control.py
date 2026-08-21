"""ExecutionControlMiddleware — iteration / dead-end owner.

MVP-3 T9 (B3 middleware simplification): the framework's runtime
operations layer. ProtocolValidationMiddleware (T7) owns state
contracts; CognitiveFlowMiddleware (T8) owns finish_task and
clarification interception; ExecutionControlMiddleware (T9) owns
everything *operational* — when to abort the agent loop, when to
inject a dead-end warning, and when to count an iteration. Token
metrics used to be parked here too; they are counted on the run's
event sink now (OB10) and this middleware no longer touches them.

Responsibilities consolidated from the legacy ``cognitive/middlewares.py``:

* ``AgentLoopIterationMiddleware`` (line 249-289) — the per-iteration
  ``before_model`` counter that emits ``AgentLoopIterationEvent``.
  Used by Studio to group LLMCall / ToolCall events under one
  iteration boundary.
* ``DeadEndPruningMiddleware`` (line 164-246) — repeated tool-failure
  detection. When the same tool returns ``status="error"`` ≥
  ``dead_end_threshold`` times in a row, inject a structured warning
  back into the message stream so the LLM stops mechanically retrying
  the same failing path.
The middleware deliberately does *not* drive any retry loop of its
own: ExecutionControl observes and reports (dead-end warnings),
while recovery is the model's job — the injected warning
message tells it to change course.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from typing import Any

from langchain.agents import AgentState
from langchain.agents.middleware import AgentMiddleware
from langchain_core.messages import HumanMessage, ToolMessage
from langgraph.runtime import Runtime

from graph_agent.callbacks.base import Callback
from graph_agent.callbacks.emit import _safe_emit_event
from graph_agent.callbacks.events import AgentLoopIterationEvent, DeadEndPrunedEvent
from graph_agent.middleware.invocation_scope import agent_invocation_key

logger = logging.getLogger(__name__)


_DEAD_END_WARNING_NAME = "dead_end_warning"

_DEAD_END_WARNING_TEMPLATE = (
    "<dead_end_warning>\n"
    "工具 `{tool_name}` 已连续失败 {count} 次。不要机械地重复同一路径。\n"
    "请优先检查:\n"
    "1. 输入格式是否错误\n"
    "2. 是否应该切换工具或改用已有上下文\n"
    "3. 是否应先更新 working memory 再继续\n"
    "最近错误: {latest_error}\n"
    "</dead_end_warning>"
)


class ExecutionControlMiddleware(AgentMiddleware[AgentState[Any]]):
    """Single owner of agent-loop runtime operations.

    Three concerns, all observed at the LangGraph step boundary:

    1. **Iteration counter** (``before_model``): counts the model turns
       spent by ONE invocation of the phase and emits
       ``AgentLoopIterationEvent``. Studio uses the event to group LLMCall /
       ToolCall events under one iteration boundary, so the count has to
       restart for each batch item / loop round / resume — see
       ``invocation_scope.agent_invocation_key``.
    2. **Dead-end detection** (``after_model``): when the last
       ``dead_end_threshold`` TOOL RESULTS are all errors from the same
       tool, inject a structured warning so the LLM breaks out of the
       failing path. "Consecutive" counts tool results, not adjacent list
       entries — the AIMessage that asked for each call necessarily sits
       between two results, so a window that stopped at it could only ever
       see one turn's worth (see ``_summarize_recent_failures``).
    No-progress tool loops are NOT this middleware's concern:
    ``LoopDetectionMiddleware`` owns them, with the same window and
    threshold, and it both emits ``LoopDetectedEvent`` and injects the
    corrective diagnostic.
    """

    def __init__(
        self,
        *,
        max_retries: int = 3,
        max_iterations: int = 20,
        dead_end_threshold: int = 3,
        callbacks: Sequence[Callback] | None = None,
        phase_name: str = "unknown",
    ) -> None:
        super().__init__()
        self._max_retries = max(0, max_retries)
        self._max_iterations = max(1, max_iterations)
        self._dead_end_threshold = max(1, dead_end_threshold)
        self._callbacks = list(callbacks or [])
        self._phase_name = phase_name
        # One graph node = one middleware instance, invoked again for every
        # batch item / loop round / resume, so the turn count is per
        # invocation and not per instance.
        self._iterations_by_invocation: dict[str, int] = {}

    @property
    def iteration(self) -> int:
        """Model turns spent by the invocation running right now."""
        return self._iterations_by_invocation.get(agent_invocation_key(), 0)

    def before_model(
        self,
        state: AgentState[Any],
        runtime: Runtime[Any],
    ) -> dict[str, Any] | None:
        """Increment iteration counter and emit ``AgentLoopIterationEvent``.

        Returns ``None`` (no state update). The event is emitted via
        the configured callbacks; if none are wired the increment is
        still observable via ``self.iteration`` for testing.
        """
        del runtime
        invocation_key = agent_invocation_key()
        iteration = self._iterations_by_invocation.get(invocation_key, 0) + 1
        self._iterations_by_invocation[invocation_key] = iteration
        self._emit_iteration_event(iteration)
        return None

    def after_model(
        self,
        state: AgentState[Any],
        runtime: Runtime[Any],
    ) -> dict[str, Any] | None:
        """Detect dead-end retries.

        Returns a state update with a ``dead_end_warning`` message when
        the threshold trips; otherwise ``None``.
        """
        del runtime
        messages = list(state.get("messages", [])) if isinstance(state, dict) else []

        return self._maybe_inject_dead_end_warning(messages)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _emit_iteration_event(self, iteration: int) -> None:
        _safe_emit_event(
            self._callbacks,
            AgentLoopIterationEvent(
                phase_name=self._phase_name,
                iteration=iteration,
            ),
        )

    def _summarize_recent_failures(
        self,
        messages: list[Any],
    ) -> tuple[str, int, str] | None:
        """Return ``(tool_name, consecutive_count, latest_error)`` or ``None``.

        Walks the message list backwards over TOOL RESULTS, ignoring the
        AIMessages between them. That distinction is the whole behaviour:
        "the LLM keeps mechanically calling the same tool" is one call per
        turn, so every pair of failures has the AIMessage that asked for the
        second one sitting between them. A window that ended at the first
        non-tool entry could only ever count the results of a SINGLE turn —
        the parallel-tool-call shape — and so never fired in a real run
        (ledger E5: seven consecutive rejected ``finish_task`` calls, zero
        ``DeadEndPrunedEvent``).

        The window shape is taken from the sibling in this same chain,
        ``LoopDetectionMiddleware._recent_tool_messages``, which reads tool
        history exactly this way. What is NOT taken from it is its signature:
        it keys on tool name AND identical content, because a no-progress loop
        is the same answer coming back, whereas a dead end is the same tool
        failing however the error is worded.

        Two things end the streak, both facts about tool results: a result
        that is not an error, and a result from a different tool. One thing
        floors the window: a warning this middleware already injected — the
        model has been told about those failures, so counting them again
        would make every further failure re-warn. Reading the floor out of
        the message history rather than remembering it on the instance also
        keeps batch items, loop rounds and resumes from suppressing each
        other's warnings; one instance serves all of them (see
        ``_iterations_by_invocation``).
        """
        tool_name: str | None = None
        latest_error = ""
        count = 0

        for msg in reversed(messages):
            if isinstance(msg, ToolMessage):
                if getattr(msg, "status", None) != "error":
                    break
                current_name = str(getattr(msg, "name", None) or "unknown")
                if tool_name is None:
                    tool_name = current_name
                    content = msg.content if isinstance(msg.content, str) else str(msg.content)
                    latest_error = content[:300]
                elif current_name != tool_name:
                    break
                count += 1
                continue
            if getattr(msg, "name", None) == _DEAD_END_WARNING_NAME:
                break

        if tool_name is None or count < self._dead_end_threshold:
            return None
        return tool_name, count, latest_error

    def _maybe_inject_dead_end_warning(
        self,
        messages: list[Any],
    ) -> dict[str, Any] | None:
        summary = self._summarize_recent_failures(messages)
        if summary is None:
            return None

        tool_name, count, latest_error = summary
        warning = _DEAD_END_WARNING_TEMPLATE.format(
            tool_name=tool_name,
            count=count,
            latest_error=latest_error,
        )
        _safe_emit_event(
            self._callbacks,
            DeadEndPrunedEvent(phase_name=self._phase_name, summary=warning),
        )
        logger.warning(
            "[ExecutionControl] Injected dead-end warning phase=%s tool=%s count=%d",
            self._phase_name,
            tool_name,
            count,
        )
        return {"messages": [HumanMessage(name=_DEAD_END_WARNING_NAME, content=warning)]}


__all__ = ["ExecutionControlMiddleware"]
