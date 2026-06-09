"""Loop-detection middleware skeleton for the MVP0 middleware chain."""

from __future__ import annotations

import json
from typing import Any

from langchain.agents import AgentState
from langchain.agents.middleware import AgentMiddleware
from langchain_core.messages import HumanMessage, ToolMessage
from langgraph.runtime import Runtime


class LoopDetectionMiddleware(AgentMiddleware[AgentState[Any]]):
    """Loop-detection slot to flag repeated no-progress tool loops."""

    def __init__(
        self,
        *,
        loop_window: int = 5,
        loop_threshold: int = 3,
        phase_name: str = "unknown",
    ) -> None:
        super().__init__()
        self._loop_window = max(1, loop_window)
        self._loop_threshold = max(2, loop_threshold)
        self._phase_name = phase_name
        self._last_diagnostic_signature: tuple[str, str] | None = None

    def after_model(
        self,
        state: AgentState[Any],
        runtime: Runtime[Any],
    ) -> dict[str, Any] | None:
        """Inspect ToolMessage history and inject diagnostic warning if a loop is detected."""
        del runtime
        repeated = _find_repeated_signature(
            _recent_tool_messages(_state_messages(state), self._loop_window),
            self._loop_threshold,
        )
        if repeated is None:
            return None

        signature, count = repeated
        if signature == self._last_diagnostic_signature:
            return None
        self._last_diagnostic_signature = signature
        return _diagnostic_update(self._phase_name, signature[0], count)


def _state_messages(state: AgentState[Any]) -> list[Any]:
    if not isinstance(state, dict):
        return []
    return list(state.get("messages", []))


def _recent_tool_messages(messages: list[Any], limit: int) -> list[ToolMessage]:
    recent: list[ToolMessage] = []
    for msg in reversed(messages):
        if isinstance(msg, ToolMessage):
            recent.append(msg)
            if len(recent) >= limit:
                break
    return recent


def _find_repeated_signature(
    messages: list[ToolMessage],
    threshold: int,
) -> tuple[tuple[str, str], int] | None:
    for signature, count in _signature_counts(messages).items():
        if count >= threshold:
            return signature, count
    return None


def _signature_counts(messages: list[ToolMessage]) -> dict[tuple[str, str], int]:
    counts: dict[tuple[str, str], int] = {}
    for msg in messages:
        signature = _tool_message_signature(msg)
        counts[signature] = counts.get(signature, 0) + 1
    return counts


def _tool_message_signature(msg: ToolMessage) -> tuple[str, str]:
    return (
        str(getattr(msg, "name", None) or "unknown"),
        _stringify_content(msg.content),
    )


def _stringify_content(content: Any) -> str:
    if isinstance(content, str):
        return content
    try:
        return json.dumps(content, sort_keys=True, default=str)
    except Exception:
        return str(content)


def _diagnostic_update(
    phase_name: str,
    tool_name: str,
    count: int,
) -> dict[str, Any]:
    diagnostic = (
        f"<loop_detection_diagnostic>\n"
        f"检测到死循环！工具 `{tool_name}` 在 phase `{phase_name}` "
        f"中连续或滑窗内重复执行了 {count} 次，且返回内容无进展。\n"
        f"请调整执行路径或切换工具。\n"
        f"</loop_detection_diagnostic>"
    )
    return {
        "messages": [
            HumanMessage(
                name="loop_detection_diagnostic",
                content=diagnostic,
            )
        ]
    }
