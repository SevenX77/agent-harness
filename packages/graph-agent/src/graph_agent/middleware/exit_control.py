"""ExitControlMiddleware — AGENT phase exit governance + nudge adapter.

Migration decision 2026-08-15 §3.5: this middleware is the ONLY adapter
over :mod:`graph_agent.middleware.nudge_policy` (the single nudge
strategy source). The planning gate hangs on ``after_model``; the
selfcheck/standard gates hang on ``after_agent``; every injected nudge
emits a typed :class:`NudgeEvent` (the dead-side ``on_nudge`` callback
channel does not exist on the live path).

Division of labour with CognitiveFlowMiddleware: CognitiveFlow educates
the model INSIDE the loop when a finish_task submission is rejected
(schema/business errors, its own rejection text, ``goto model``, no
nudge budget consumed — matching the dead-side rule that a validation
failure is a correction, not a nudge). ExitControl governs LOOP EXITS:
a turn either ends with a qualified finish marker or gets exactly one
layer of education per failure — planning at after_model jumps before
the loop can end, so after_agent never re-educates the same turn.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from typing import Any, NoReturn

from langchain.agents import AgentState
from langchain.agents.middleware import AgentMiddleware, hook_config
from langchain_core.messages import AIMessage, HumanMessage
from langgraph.runtime import Runtime

from graph_agent.callbacks.base import Callback
from graph_agent.callbacks.emit import _safe_emit_event
from graph_agent.callbacks.events import (
    AgentExitDecision,
    AgentExitDecisionEvent,
    NudgeEvent,
)
from graph_agent.middleware.cognitive_flow import WORKING_MEMORY_PLAN_KEY
from graph_agent.middleware.invocation_scope import agent_invocation_key
from graph_agent.middleware.nudge_policy import (
    DEFAULT_MAX_NUDGES,
    NudgeDecision,
    NudgePolicy,
)

logger = logging.getLogger(__name__)


class ExitControlMiddleware(AgentMiddleware[AgentState[Any]]):
    """Exit-control middleware implementing AGENT phase exit governance.

    It ensures:
    1. A phase succeeds only when a qualified finish_task marker reaches the gate.
    2. The migrated nudge policy educates the model (planning at after_model;
       selfcheck/standard at after_agent) while budget is available.
    3. The phase fails explicitly with a fatal error code when either the
       iteration budget or the nudge budget is exhausted — never a silent END.
    """

    def __init__(
        self,
        *,
        phase_name: str = "unknown",
        callbacks: Sequence[Callback] | None = None,
        max_nudges: int = DEFAULT_MAX_NUDGES,
    ) -> None:
        super().__init__()
        self._phase_name = phase_name
        self._callbacks = list(callbacks or [])
        self._max_nudges = max_nudges
        # Per-invocation iteration budget, held OUTSIDE the flow channel: a flow
        # write from before_model races other legitimate flow writers in the
        # same superstep and the reducer-less LastValue channel raises
        # InvalidUpdateError (field evidence: runs 2026-08-01T12-16-44 /
        # 13-14-57). Keying by the invocation (see `agent_invocation_key`) keeps the pinned
        # contract that a reused graph gives every invoke a fresh budget.
        self._iterations_by_invocation: dict[str, int] = {}
        # Nudge counters follow the same scoping rule for the same reason:
        # one policy instance per invocation = fresh nudge budget per invoke.
        self._nudge_policy_by_invocation: dict[str, NudgePolicy] = {}

    def _nudge_policy(self) -> NudgePolicy:
        invocation_key = agent_invocation_key()
        policy = self._nudge_policy_by_invocation.get(invocation_key)
        if policy is None:
            policy = NudgePolicy(max_nudges=self._max_nudges)
            self._nudge_policy_by_invocation[invocation_key] = policy
        return policy

    def before_model(
        self,
        state: AgentState[Any],
        runtime: Runtime[Any],
    ) -> dict[str, Any] | None:
        del runtime
        invocation_key = agent_invocation_key()
        current_iteration = self._iterations_by_invocation.get(invocation_key, 0) + 1
        self._iterations_by_invocation[invocation_key] = current_iteration

        # 进行预算判断
        from langgraph.config import get_config
        config = get_config()
        max_iterations = config.get("configurable", {}).get("max_iterations", 20)

        if not self._has_valid_finish(state) and current_iteration > max_iterations:
            self._raise_fatal_error(
                f"max iterations ({max_iterations}) reached without a valid "
                "finish_task marker."
            )

        return None

    def _has_valid_finish(self, state: AgentState[Any]) -> bool:
        finish_result = self._own_finish_payload(state)
        if finish_result is None:
            return False
        return bool(finish_result.get("schema_validation") == "passed")

    def _own_finish_payload(self, state: AgentState[Any]) -> dict[str, Any] | None:
        """Return THIS phase's finish_task marker, qualified or not.

        The framework state carries the previous phase's marker across the
        boundary, so only a marker labelled with this phase's name counts.
        """
        flow = state.get("flow")
        finish_result = getattr(flow, "finish_task_result", None) if flow else None
        if isinstance(flow, dict):
            finish_result = flow.get("finish_task_result")
        if not isinstance(finish_result, dict):
            return None
        if finish_result.get("phase_name") != self._phase_name:
            return None
        return finish_result

    def _working_memory_has_plan(self, state: AgentState[Any]) -> bool:
        flow = state.get("flow")
        working_memory = getattr(flow, "working_memory", None) if flow else None
        if isinstance(flow, dict):
            working_memory = flow.get("working_memory")
        return isinstance(working_memory, dict) and WORKING_MEMORY_PLAN_KEY in working_memory

    def _raise_fatal_error(self, reason: str) -> NoReturn:
        from graph_agent.core.exceptions import GraphAgentFatalError
        msg = f"[F-v3-agent-exit-control-failed] Phase '{self._phase_name}' failed: {reason}"
        logger.error("[ExitControlMiddleware] %s", msg)
        raise GraphAgentFatalError(msg)

    async def abefore_model(
        self,
        state: AgentState[Any],
        runtime: Runtime[Any],
    ) -> dict[str, Any] | None:
        # Async graph executions dispatch to the async hook only; without this
        # counterpart the iteration budget silently never advances there (the
        # sibling CognitiveFlow middleware ships both hooks for this reason).
        return self.before_model(state, runtime)

    @hook_config(can_jump_to=["model"])
    def after_model(
        self,
        state: AgentState[Any],
        runtime: Runtime[Any],
    ) -> dict[str, Any] | None:
        """Planning gate (§3.5 目标设计 3).

        Fires when the model produced text, called no tools, and
        ``flow.working_memory`` carries no plan yet; the nudge jumps
        straight back to the model, so the loop never reaches after_agent
        for this turn — one failure, one education.
        """
        del runtime
        if self._has_valid_finish(state):
            return None
        messages = state.get("messages", [])
        last_message = messages[-1] if messages else None
        has_tool_calls = bool(last_message is not None and getattr(last_message, "tool_calls", None))
        decision = self._nudge_policy().try_planning(
            _latest_ai_text(messages),
            has_tool_calls=has_tool_calls,
            has_plan=self._working_memory_has_plan(state),
        )
        if decision.text is None:
            return None
        self._emit_nudge(
            decision,
            reason=(
                "the model produced text without tool calls and no plan exists "
                "in working memory; asked it to record a plan via "
                "update_working_memory first"
            ),
        )
        self._report(
            "continue_nudged",
            self._iterations_by_invocation.get(agent_invocation_key(), 0),
            "The model produced text with no plan recorded, so the planning gate sent it "
            "back with a nudge before the turn could end.",
        )
        return {"jump_to": "model", "messages": [HumanMessage(content=decision.text)]}

    @hook_config(can_jump_to=["model"])
    async def aafter_model(
        self,
        state: AgentState[Any],
        runtime: Runtime[Any],
    ) -> dict[str, Any] | None:
        # Same async-dispatch requirement as abefore_model / aafter_agent.
        return self.after_model(state, runtime)

    @hook_config(can_jump_to=["model"])
    async def aafter_agent(
        self,
        state: AgentState[Any],
        runtime: Runtime[Any],
    ) -> dict[str, Any] | None:
        # Same async-dispatch requirement: without this, a model turn that
        # neither calls tools nor finishes ends the phase silently instead of
        # being nudged back to the model (field evidence: run
        # 2026-08-01T12-52-39, review phase, 1 llm_call, no tool_call).
        return self.after_agent(state, runtime)

    @hook_config(can_jump_to=["model"])
    def after_agent(
        self,
        state: AgentState[Any],
        runtime: Runtime[Any],
    ) -> dict[str, Any] | None:
        del runtime
        # 1. 检查是否有合格的 finish_task_result
        current_iteration = self._iterations_by_invocation.get(agent_invocation_key(), 0)

        if self._has_valid_finish(state):
            self._report(
                "exit_success",
                current_iteration,
                "The exit gate accepted a qualified finish_task submission, so the phase ends here.",
            )
            # after_agent only runs when the loop is already terminating, so
            # success needs no jump — and `{"jump_to": "end"}` here re-enters
            # after_agent forever (langchain hook routing, minimal repro
            # 2026-08-14: 21 re-entries before an artificial cap fired).
            return None

        # 2. 到这里代表没有合格标记，需要评估预算
        from langgraph.config import get_config
        config = get_config()
        max_iterations = config.get("configurable", {}).get("max_iterations", 20)

        if current_iteration >= max_iterations:
            self._raise_fatal_error(
                f"max iterations ({max_iterations}) reached without a valid "
                "finish_task marker."
            )

        # 3. 评估无完成标记的情况（selfcheck / standard 闸,或显式失败）
        return self._govern_no_finish_exit(state, current_iteration)

    def _govern_no_finish_exit(
        self,
        state: AgentState[Any],
        current_iteration: int,
    ) -> dict[str, Any]:
        """Selfcheck / standard gates (§3.5 目标设计 2) + explicit failure."""
        messages = state.get("messages", [])
        last_message = messages[-1] if messages else None
        has_tool_calls = bool(last_message is not None and getattr(last_message, "tool_calls", None))

        if has_tool_calls:
            # Tool activity is progress, not a nudge condition: the loop is
            # ending with unfinished tool work (e.g. a rejected validation),
            # so send it back and let the iteration budget govern.
            self._report(
                "continue_tool_work",
                current_iteration,
                "The turn ended with tool calls outstanding and no finish_task submission, "
                "so the loop continues and the iteration budget governs.",
            )
            return {"jump_to": "model"}

        policy = self._nudge_policy()

        # Selfcheck gate: only a finish attempt from THIS phase is judged.
        # On today's live path CognitiveFlow only persists qualified markers,
        # so this branch is defensive; the policy semantics are pinned by
        # unit tests either way.
        finish_payload = self._own_finish_payload(state)
        if finish_payload is not None:
            decision = policy.try_selfcheck(finish_payload)
            if decision.text is not None:
                self._emit_nudge(
                    decision,
                    reason=(
                        "the finish_task submission lacked a substantive "
                        "self-check; asked for diagnostics_md and "
                        "business_data_md via finish_task"
                    ),
                )
                self._report(
                    "continue_nudged",
                    current_iteration,
                    "The finish_task submission lacked a substantive self-check, so the loop "
                    "continues with a nudge instead of ending.",
                )
                return {
                    "jump_to": "model",
                    "messages": [HumanMessage(content=decision.text)],
                }
            if decision.budget_exhausted:
                self._raise_nudge_budget_error(current_iteration)

        decision = policy.try_standard(_latest_ai_text(messages), has_tool_calls=False)
        if decision.text is not None:
            self._emit_nudge(
                decision,
                reason=(
                    "the model made no tool calls and did not finish; asked it "
                    "to advance via tools or submit through finish_task"
                ),
            )
            self._report(
                "continue_nudged",
                current_iteration,
                "The turn made no tool calls and did not submit, so the loop continues "
                "with a nudge instead of ending.",
            )
            return {
                "jump_to": "model",
                "messages": [HumanMessage(content=decision.text)],
            }

        if decision.budget_exhausted:
            # The nudge budget can educate no further; ending here without a
            # marker would be a silent success — forbidden by the
            # exit-governance contract — so converge on the existing
            # explicit-failure semantics.
            self._raise_nudge_budget_error(current_iteration)

        # The policy has no opinion on this end shape (no trailing AI text —
        # e.g. the loop is ending on a ToolMessage such as a finish_task
        # rejection). Keep the loop alive; the iteration budget governs.
        self._report(
            "continue_open",
            current_iteration,
            "The turn ended on a tool reply with nothing for the nudge policy to correct, "
            "so the loop continues and the iteration budget governs.",
        )
        return {"jump_to": "model"}

    def _raise_nudge_budget_error(self, current_iteration: int) -> NoReturn:
        counts = self._nudge_policy().counts()
        self._raise_fatal_error(
            f"nudge budget exhausted (counts={counts}, max_nudges={self._max_nudges}) "
            f"after {current_iteration} iteration(s) without a valid finish_task "
            "marker."
        )

    def _report(self, decision: AgentExitDecision, iteration: int, message: str) -> None:
        """Say what the gate answered, in the stream a reader of the run watches.

        These four sentences existed before this method did — as ``logger.info``
        lines, which is to say in a place no reader of a run ever looks. A
        decision the product cannot show is not observable, however carefully it
        is worded.
        """
        _safe_emit_event(
            self._callbacks,
            AgentExitDecisionEvent(
                phase_name=self._phase_name,
                decision=decision,
                iteration=iteration,
                message=message,
            ),
        )

    def _emit_nudge(self, decision: NudgeDecision, *, reason: str) -> None:
        _safe_emit_event(
            self._callbacks,
            NudgeEvent(
                phase_name=self._phase_name,
                nudge_count=decision.count,
                nudge_type=str(decision.kind or "standard"),
                message=(
                    f"Injected {decision.kind} nudge #{decision.count} in phase "
                    f"{self._phase_name!r}: {reason}; sent the model back for "
                    "another turn."
                ),
            ),
        )


def _latest_ai_text(messages: Sequence[Any]) -> str:
    """Text of the model turn the loop is ending on (empty when none)."""
    if not messages:
        return ""
    last = messages[-1]
    if not isinstance(last, AIMessage):
        return ""
    content = last.content
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for block in content:
            if isinstance(block, dict):
                parts.append(str(block.get("text", "")))
            else:
                parts.append(str(block))
        return "".join(parts)
    return ""
