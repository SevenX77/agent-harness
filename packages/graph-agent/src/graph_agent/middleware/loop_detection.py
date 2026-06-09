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
        self._last_diagnostic_signature: str | None = None

    def after_model(
        self,
        state: AgentState[Any],
        runtime: Runtime[Any],
    ) -> dict[str, Any] | None:
        """Inspect ToolMessage history and inject diagnostic warning if a loop is detected."""
        del runtime
        messages = list(state.get("messages", [])) if isinstance(state, dict) else []

        recent_tool_msgs: list[ToolMessage] = []
        for msg in reversed(messages):
            if isinstance(msg, ToolMessage):
                recent_tool_msgs.append(msg)
                if len(recent_tool_msgs) >= self._loop_window:
                    break

        if not recent_tool_msgs:
            return None

        signatures: dict[str, int] = {}
        for msg in recent_tool_msgs:
            name = str(getattr(msg, "name", None) or "unknown")
            content_str = ""
            if isinstance(msg.content, str):
                content_str = msg.content
            else:
                try:
                    content_str = json.dumps(msg.content, sort_keys=True, default=str)
                except Exception:
                    content_str = str(msg.content)

            sig = f"{name}:{content_str}"
            signatures[sig] = signatures.get(sig, 0) + 1

        for sig, count in signatures.items():
            if count >= self._loop_threshold:
                tool_name = sig.split(":", 1)[0]
                if sig == self._last_diagnostic_signature:
                    return None
                self._last_diagnostic_signature = sig

                diagnostic = (
                    f"<loop_detection_diagnostic>\n"
                    f"检测到死循环！工具 `{tool_name}` 在 phase `{self._phase_name}` "
                    f"中连续或滑窗内重复执行了 {count} 次，且返回内容无进展（参数及结果相同）。\n"
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
        return None
