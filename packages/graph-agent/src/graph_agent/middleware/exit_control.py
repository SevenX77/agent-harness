from __future__ import annotations

import logging
from collections.abc import Sequence
from typing import Any

from langchain.agents import AgentState
from langchain.agents.middleware import AgentMiddleware, hook_config
from langchain_core.messages import HumanMessage
from langgraph.runtime import Runtime

from graph_agent.callbacks.base import Callback

logger = logging.getLogger(__name__)


class ExitControlMiddleware(AgentMiddleware[AgentState[Any]]):
    """Exit-control middleware implementing AGENT phase exit governance.

    It ensures:
    1. A phase succeeds only when a qualified finish_task marker reaches the gate.
    2. Nudges the model to use finish_task when no tool calls are made and budget is available.
    3. Fails explicitly with a fatal error code when budget is exhausted.
    """

    def __init__(
        self,
        *,
        phase_name: str = "unknown",
        callbacks: Sequence[Callback] | None = None,
        has_finish_task: bool = False,
    ) -> None:
        super().__init__()
        self._phase_name = phase_name
        self._callbacks = list(callbacks or [])
        self._has_finish_task = has_finish_task
        # Per-thread iteration budget, held OUTSIDE the flow channel: a flow
        # write from before_model races other legitimate flow writers in the
        # same superstep and the reducer-less LastValue channel raises
        # InvalidUpdateError (field evidence: runs 2026-08-01T12-16-44 /
        # 13-14-57). Keying by thread_id keeps the pinned contract that a
        # reused graph gives every invoke a fresh budget.
        self._iterations_by_thread: dict[str, int] = {}

    def _thread_key(self) -> str:
        from langgraph.config import get_config

        config = get_config()
        return str(config.get("configurable", {}).get("thread_id") or "default")

    def before_model(
        self,
        state: AgentState[Any],
        runtime: Runtime[Any],
    ) -> dict[str, Any] | None:
        del runtime
        if not self._has_finish_task:
            return None

        thread_key = self._thread_key()
        current_iteration = self._iterations_by_thread.get(thread_key, 0) + 1
        self._iterations_by_thread[thread_key] = current_iteration

        # 进行预算判断
        from langgraph.config import get_config
        config = get_config()
        max_iterations = config.get("configurable", {}).get("max_iterations", 20)

        if not self._has_valid_finish(state) and current_iteration > max_iterations:
            self._raise_fatal_error(max_iterations)

        return None

    def _has_valid_finish(self, state: AgentState[Any]) -> bool:
        flow = state.get("flow")
        finish_result = getattr(flow, "finish_task_result", None) if flow else None
        if isinstance(flow, dict):
            finish_result = flow.get("finish_task_result")

        if finish_result is None:
            return False
        if finish_result.get("schema_validation") != "passed":
            return False
        # Only THIS phase's own marker counts: the framework state carries the
        # previous phase's marker across the boundary.
        return bool(finish_result.get("phase_name") == self._phase_name)

    def _raise_fatal_error(self, max_iterations: int) -> None:
        from graph_agent.core.exceptions import GraphAgentFatalError
        msg = (
            f"[F-v3-agent-exit-control-failed] Phase '{self._phase_name}' failed: "
            f"max iterations ({max_iterations}) reached without a valid finish_task marker."
        )
        logger.error("[ExitControlMiddleware] Iteration limit exceeded. Raising fatal error.")
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

    @hook_config(can_jump_to=["end", "model"])
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

    @hook_config(can_jump_to=["end", "model"])
    def after_agent(
        self,
        state: AgentState[Any],
        runtime: Runtime[Any],
    ) -> dict[str, Any] | None:
        if not self._has_finish_task:
            return None

        # 1. 检查是否有合格的 finish_task_result
        if self._has_valid_finish(state):
            logger.info(
                "[ExitControlMiddleware] Qualified finish_task marker observed. Exiting success."
            )
            return {"jump_to": "end"}

        # 2. 到这里代表没有合格标记，需要评估预算
        from langgraph.config import get_config
        config = get_config()
        max_iterations = config.get("configurable", {}).get("max_iterations", 20)

        current_iteration = self._iterations_by_thread.get(self._thread_key(), 0)

        if current_iteration >= max_iterations:
            self._raise_fatal_error(max_iterations)

        # 3. 评估无完成标记的情况（跳转会 model 或 nudge）
        return self._handle_no_finish_marker(state, current_iteration)

    def _handle_no_finish_marker(self, state: AgentState[Any], current_iteration: int) -> dict[str, Any]:
        messages = state.get("messages", [])
        last_msg = messages[-1] if messages else None

        has_tool_calls = False
        if last_msg and hasattr(last_msg, "tool_calls") and last_msg.tool_calls:
            has_tool_calls = True

        if not has_tool_calls:
            # 没有 tool calls 也无完成标记，nudge 并跳转回 model
            logger.info(
                "[ExitControlMiddleware] No tool calls and no finish_task. "
                "Nudging model back to model node. Iteration: %d",
                current_iteration,
            )
            nudge_text = (
                "No tool calls were made and no finish_task marker was found. "
                "Please use the `finish_task` tool to submit the final output once complete."
            )
            nudge_msg = HumanMessage(content=nudge_text)
            return {
                "jump_to": "model",
                "messages": [nudge_msg],
            }

        # 如果有 tool calls，但既然它到了这里且无合格标记（可能是校验失败），跳回 model
        logger.info(
            "[ExitControlMiddleware] Tool calls present but no valid finish marker. "
            "Jumping back to model."
        )
        return {
            "jump_to": "model"
        }
