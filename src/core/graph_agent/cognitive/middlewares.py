"""Custom middlewares for GraphAgent agent execution.

These middlewares are designed for `langchain.agents.create_agent(..., middleware=...)`.
They may also be reused by DeerFlow's hook-based lead-agent path, but the primary
consumer is `GraphAgentHarness`.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from typing import Any

try:
    from typing import override
except ImportError:  # pragma: no cover - Python < 3.12
    from typing_extensions import override

from langchain.agents import AgentState
from langchain.agents.middleware import AgentMiddleware
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langgraph.runtime import Runtime

from ..callbacks.base import Callback

logger = logging.getLogger(__name__)


class WorkingMemoryMiddleware(AgentMiddleware[AgentState]):
    """Inject working memory into the next model call as a reminder message."""

    def __init__(
        self,
        *,
        blackboard: dict[str, Any] | None = None,
        context_ref: dict[str, Any] | None = None,
        max_chars: int = 4000,
    ):
        super().__init__()
        self._blackboard = blackboard or {}
        self._context_ref = context_ref
        self._max_chars = max_chars
        self._last_injected_signature: str | None = None

    def reset_signature(self) -> None:
        """Reset dedup signature so the next invoke gets a fresh injection."""
        self._last_injected_signature = None

    def update_blackboard(self, key: str, value: str) -> None:
        """Update a blackboard entry."""
        self._blackboard[key] = value

    def get_blackboard(self) -> dict:
        """Get the current blackboard state."""
        return dict(self._blackboard)

    def _build_working_memory_text(self) -> str:
        if self._context_ref is not None:
            raw = self._context_ref.get("_working_memory")
            if raw is None:
                return ""
            text = str(raw).strip()
            if not text:
                return ""
            if len(text) > self._max_chars:
                return text[: self._max_chars] + "... [truncated]"
            return text

        if not self._blackboard:
            return ""

        wm_lines = ["<working_memory>"]
        for key, value in self._blackboard.items():
            value_text = str(value)
            if len(value_text) > self._max_chars:
                value_text = value_text[: self._max_chars] + "... [truncated]"
            wm_lines.append(f"  <{key}>{value_text}</{key}>")
        wm_lines.append("</working_memory>")
        return "\n".join(wm_lines)

    @override
    def before_model(self, state: AgentState, runtime: Runtime) -> dict[str, Any] | None:
        wm_text = self._build_working_memory_text()
        if not wm_text:
            return None

        signature = wm_text
        if signature == self._last_injected_signature:
            return None
        self._last_injected_signature = signature

        if self._context_ref is not None:
            reminder = HumanMessage(
                name="working_memory_update",
                content=f"<working_memory>\n{wm_text}\n</working_memory>",
            )
            logger.info("[WorkingMemory] Injected working memory reminder")
            return {"messages": [reminder]}

        messages = list(state.get("messages", []))
        if messages and isinstance(messages[-1], HumanMessage) and getattr(messages[-1], "name", "") == "working_memory_update":
            return None
        reminder = HumanMessage(name="working_memory_update", content=wm_text)
        return {"messages": [reminder]}


class DeadEndPruningMiddleware(AgentMiddleware[AgentState]):
    """Detect repeated tool failures and inject a diagnostic warning."""

    def __init__(
        self,
        threshold: int = 3,
        *,
        callbacks: Sequence[Callback] | None = None,
        phase_name: str | None = None,
    ):
        super().__init__()
        self._threshold = max(1, threshold)
        self._callbacks = list(callbacks or [])
        self._phase_name = phase_name or "unknown"
        self._last_warning_signature: str | None = None

    def _summarize_recent_failures(
        self,
        messages: list[Any],
    ) -> tuple[str, int, str] | None:
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
            if seen_failure and not isinstance(msg, AIMessage):
                break

        if tool_name is None or count < self._threshold:
            return None
        return tool_name, count, latest_error

    @override
    def before_model(self, state: AgentState, runtime: Runtime) -> dict[str, Any] | None:
        summary = self._summarize_recent_failures(list(state.get("messages", [])))
        if summary is None:
            return None

        tool_name, count, latest_error = summary
        signature = f"{tool_name}:{count}:{latest_error}"
        if signature == self._last_warning_signature:
            return None
        self._last_warning_signature = signature

        warning = (
            "<dead_end_warning>\n"
            f"工具 `{tool_name}` 已连续失败 {count} 次。不要机械地重复同一路径。\n"
            "请优先检查：\n"
            "1. 输入格式是否错误\n"
            "2. 是否应该切换工具或改用已有上下文\n"
            "3. 是否应先更新 working memory 再继续\n"
            f"最近错误：{latest_error}\n"
            "</dead_end_warning>"
        )
        for cb in self._callbacks:
            try:
                cb.on_dead_end_pruned(self._phase_name, warning)
            except Exception as exc:
                logger.warning("[DeadEndPruning] Callback %s error: %s", type(cb).__name__, exc)
        logger.warning(
            "[DeadEndPruning] Injected warning for phase=%s tool=%s count=%d",
            self._phase_name,
            tool_name,
            count,
        )
        return {"messages": [HumanMessage(name="dead_end_warning", content=warning)]}


class AgentLoopIterationMiddleware(AgentMiddleware[AgentState]):
    """Emit one AgentLoopIterationEvent at the top of each agent-loop turn.

    Tier 2 — T-B4. ``before_model`` fires once per LangGraph-controlled
    iteration of the agent (between tool-calls), which is exactly the
    "iteration" boundary Studio needs to group the LLMCall / ToolCall
    events emitted during that turn.
    """

    def __init__(
        self,
        *,
        phase_name: str,
        callbacks: Sequence[Callback] | None = None,
    ) -> None:
        super().__init__()
        self._phase_name = phase_name
        self._callbacks = list(callbacks or [])
        self._iteration = 0

    @override
    def before_model(self, state: AgentState, runtime: Runtime) -> dict[str, Any] | None:
        self._iteration += 1
        try:
            from ..callbacks.events import AgentLoopIterationEvent

            event = AgentLoopIterationEvent(
                phase_name=self._phase_name,
                iteration=self._iteration,
            )
            for cb in self._callbacks:
                try:
                    cb.on_event(event)
                except Exception:  # noqa: BLE001
                    logger.warning(
                        "[AgentLoopIteration] callback %r raised; continuing",
                        type(cb).__name__,
                    )
        except Exception:  # noqa: BLE001
            logger.exception("[AgentLoopIteration] emit failed; continuing")
        return None  # pass-through, no state mutation


def create_custom_middlewares(
    *,
    working_memory: bool = True,
    dead_end_pruning: bool = True,
    dead_end_threshold: int = 3,
    blackboard: dict[str, Any] | None = None,
    context_ref: dict[str, Any] | None = None,
    callbacks: Sequence[Callback] | None = None,
    phase_name: str | None = None,
    agent_loop_iteration: bool = True,
) -> list[AgentMiddleware]:
    """Create the middleware list for GraphAgent / DeerFlow integration."""
    middlewares: list[AgentMiddleware] = []

    # T-B4: iteration counter goes *first* so its event lands before
    # the WorkingMemory / DeadEnd middlewares' own before_model logic
    # in the same iteration.
    if agent_loop_iteration and phase_name:
        middlewares.append(
            AgentLoopIterationMiddleware(
                phase_name=phase_name,
                callbacks=callbacks,
            )
        )

    if working_memory:
        middlewares.append(
            WorkingMemoryMiddleware(
                blackboard=blackboard,
                context_ref=context_ref,
            )
        )

    if dead_end_pruning:
        middlewares.append(
            DeadEndPruningMiddleware(
                threshold=dead_end_threshold,
                callbacks=callbacks,
                phase_name=phase_name,
            )
        )

    return middlewares
