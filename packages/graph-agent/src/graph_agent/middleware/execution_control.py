"""ExecutionControlMiddleware — retry / loop detection / metrics owner.

MVP-3 T9 (B3 middleware simplification): the framework's runtime
operations layer. ProtocolValidationMiddleware (T7) owns state
contracts; CognitiveFlowMiddleware (T8) owns finish_task and
clarification interception; ExecutionControlMiddleware (T9) owns
everything *operational* — when to abort the agent loop, when to
inject a dead-end warning, when to count an iteration, and where to
park metrics.

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
* Lightweight loop detection — MVP-0 砍 ``LoopDetectionMiddleware``;
  T9 brings back a minimal version that flags the same tool call (by
  ``name + args hash``) repeating within a short window. Hits a
  callback so operators can surface it without aborting the agent.
* Metrics aggregation — ``collect_metrics`` snapshots token / latency
  totals from ``state['flow'].metrics`` for the LoggingMiddleware /
  TracingCallback consumers.

The middleware deliberately does *not* mutate retry counters or
``state['flow'].retry_feedback``: those flow through ``RetryRouter``
at the LangGraph conditional-edge layer (see
``core/retry_router.py``) and the ValidationPhaseNode at the
phase-executor layer. ExecutionControl observes and reports; the
retry decision is made elsewhere by design.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Sequence
from typing import Any

from langchain.agents import AgentState
from langchain.agents.middleware import AgentMiddleware
from langchain_core.messages import HumanMessage, ToolMessage
from langgraph.runtime import Runtime

from graph_agent.callbacks.base import Callback

logger = logging.getLogger(__name__)


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

    1. **Iteration counter** (``before_model``): increments
       per-instance turn count and emits ``AgentLoopIterationEvent``.
       Studio uses the event to group LLMCall / ToolCall events under
       one iteration boundary.
    2. **Dead-end detection** (``after_model``): when the most recent
       ToolMessage stream contains ``dead_end_threshold`` consecutive
       same-tool errors, inject a structured warning so the LLM
       breaks out of the failing path.
    3. **Lightweight loop detection** (``after_model``): when the same
       ``(tool_name, args_hash)`` pair fires ``loop_threshold`` times
       within ``loop_window`` recent ToolMessages, emit a
       ``LoopDetectedEvent`` callback for operators. The middleware
       does not abort the loop — that is the framework's
       ``max_iterations`` ceiling at the harness level.

    Retry-counter management lives in ``RetryRouter`` and
    ``ValidationPhaseNode``; this middleware does not touch
    ``state['flow'].retry_counts`` or ``retry_feedback`` directly.
    """

    def __init__(
        self,
        *,
        max_retries: int = 3,
        max_iterations: int = 20,
        dead_end_threshold: int = 3,
        loop_window: int = 5,
        loop_threshold: int = 3,
        callbacks: Sequence[Callback] | None = None,
        phase_name: str = "unknown",
    ) -> None:
        super().__init__()
        self._max_retries = max(0, max_retries)
        self._max_iterations = max(1, max_iterations)
        self._dead_end_threshold = max(1, dead_end_threshold)
        self._loop_window = max(1, loop_window)
        self._loop_threshold = max(2, loop_threshold)
        self._callbacks = list(callbacks or [])
        self._phase_name = phase_name
        self._iteration = 0
        self._last_dead_end_signature: str | None = None
        self._last_loop_signature: str | None = None

    @property
    def iteration(self) -> int:
        """Number of LLM turns observed by this middleware instance."""
        return self._iteration

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
        self._iteration += 1
        self._emit_iteration_event()
        return None

    def after_model(
        self,
        state: AgentState[Any],
        runtime: Runtime[Any],
    ) -> dict[str, Any] | None:
        """Detect dead-end retries and lightweight tool-call loops.

        Returns a state update with a ``dead_end_warning`` message when
        the threshold trips; otherwise ``None``. Loop detection emits
        a callback event but does not mutate state — surfacing the
        signal to the operator is enough; aborting belongs to the
        harness's ``max_iterations`` ceiling.
        """
        del runtime
        messages = list(state.get("messages", [])) if isinstance(state, dict) else []

        update: dict[str, Any] | None = self._maybe_inject_dead_end_warning(messages)
        self._maybe_emit_loop_detected(messages)
        return update

    def collect_metrics(self, state: Any) -> dict[str, Any]:
        """Snapshot token / latency totals from ``state['flow'].metrics``.

        Helper for LoggingMiddleware / TracingCallback consumers that
        need a stable view of accumulated metrics. Returns an empty
        dict when the state shape doesn't carry a Pydantic flow (e.g.,
        a default LangGraph ``AgentState``), so callers can use the
        return value unconditionally.
        """
        if not isinstance(state, dict):
            return {}
        flow = state.get("flow")
        if flow is None:
            return {}
        try:
            metrics = getattr(flow, "metrics", None)
        except AttributeError:
            return {}
        if not isinstance(metrics, dict):
            return {}
        return dict(metrics)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _emit_iteration_event(self) -> None:
        try:
            from graph_agent.callbacks.events import AgentLoopIterationEvent

            event = AgentLoopIterationEvent(
                phase_name=self._phase_name,
                iteration=self._iteration,
            )
            for cb in self._callbacks:
                try:
                    cb.on_event(event)
                except Exception:  # noqa: BLE001 — callback faults must not break loop
                    logger.warning(
                        "[ExecutionControl] callback %r raised on iteration event; continuing",
                        type(cb).__name__,
                    )
        except Exception:  # noqa: BLE001
            logger.exception("[ExecutionControl] iteration event emit failed; continuing")

    def _summarize_recent_failures(
        self,
        messages: list[Any],
    ) -> tuple[str, int, str] | None:
        """Return ``(tool_name, consecutive_count, latest_error)`` or ``None``.

        Walks the message list backwards. Counts how many consecutive
        ``ToolMessage(status='error')`` entries share the same
        ``name`` (the LLM keeps mechanically calling the same tool).
        Returns ``None`` when the streak is below the configured
        threshold or when a non-error breaks the streak.
        """
        tool_name: str | None = None
        latest_error = ""
        count = 0
        seen_failure = False

        for msg in reversed(messages):
            if isinstance(msg, ToolMessage):
                status = getattr(msg, "status", None)
                current_name = str(getattr(msg, "name", None) or "unknown")
                content = msg.content if isinstance(msg.content, str) else str(msg.content)
                if status == "error":
                    if tool_name is None:
                        tool_name = current_name
                        latest_error = content[:300]
                    if current_name != tool_name:
                        break
                    count += 1
                    seen_failure = True
                    continue
                if seen_failure:
                    break
                return None
            if seen_failure:
                # Any non-tool message after a failure streak ends the window.
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
        signature = f"{tool_name}:{count}:{latest_error}"
        if signature == self._last_dead_end_signature:
            return None
        self._last_dead_end_signature = signature

        warning = _DEAD_END_WARNING_TEMPLATE.format(
            tool_name=tool_name,
            count=count,
            latest_error=latest_error,
        )
        for cb in self._callbacks:
            try:
                cb.on_dead_end_pruned(self._phase_name, warning)
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "[ExecutionControl] callback %s error on dead_end_pruned: %s",
                    type(cb).__name__,
                    exc,
                )
        logger.warning(
            "[ExecutionControl] Injected dead-end warning phase=%s tool=%s count=%d",
            self._phase_name,
            tool_name,
            count,
        )
        return {"messages": [HumanMessage(name="dead_end_warning", content=warning)]}

    def _maybe_emit_loop_detected(self, messages: list[Any]) -> None:
        """Lightweight loop detection: same ``(tool, args_hash)`` repeating.

        Walks the most recent ``loop_window`` ToolMessages (any status)
        and counts how often each ``(name, content)`` signature
        appears. When any signature meets ``loop_threshold`` the
        callback fires once per signature (deduped via
        ``_last_loop_signature``).
        """
        recent = _recent_tool_messages(messages, self._loop_window)
        if not recent:
            return

        for signature, hits in _tool_message_signatures(recent).items():
            if hits < self._loop_threshold:
                continue
            if signature == self._last_loop_signature:
                continue
            self._last_loop_signature = signature
            for cb in self._callbacks:
                handler = getattr(cb, "on_loop_detected", None)
                if handler is None:
                    continue
                try:
                    handler(self._phase_name, signature, hits)
                except Exception as exc:  # noqa: BLE001
                    logger.warning(
                        "[ExecutionControl] callback %s error on loop_detected: %s",
                        type(cb).__name__,
                        exc,
                    )
            logger.info(
                "[ExecutionControl] Loop detected phase=%s signature=%s hits=%d",
                self._phase_name,
                signature,
                hits,
            )
            break  # one report per after_model call


def _recent_tool_messages(messages: list[Any], limit: int) -> list[ToolMessage]:
    recent: list[ToolMessage] = []
    for msg in reversed(messages):
        if isinstance(msg, ToolMessage):
            recent.append(msg)
            if len(recent) >= limit:
                break
    return recent


def _tool_message_signatures(messages: list[ToolMessage]) -> dict[str, int]:
    signatures: dict[str, int] = {}
    for msg in messages:
        name = str(getattr(msg, "name", None) or "unknown")
        content = (
            msg.content
            if isinstance(msg.content, str)
            else json.dumps(msg.content, sort_keys=True, default=str)
        )
        sig = f"{name}:{hash(content)}"
        signatures[sig] = signatures.get(sig, 0) + 1
    return signatures


__all__ = ["ExecutionControlMiddleware"]
