"""Middleware for intercepting clarification requests."""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from hashlib import sha256
from typing import Any

from langchain.agents import AgentState
from langchain.agents.middleware import AgentMiddleware
from langchain_core.messages import ToolMessage
from langgraph.graph import END
from langgraph.prebuilt.tool_node import ToolCallRequest
from langgraph.types import Command
from typing_extensions import override

logger = logging.getLogger(__name__)


class ClarificationMiddlewareState(AgentState[Any]):
    """Compatible state schema for clarification-only middleware."""


class ClarificationMiddleware(AgentMiddleware[ClarificationMiddlewareState]):
    """Intercept ``ask_clarification`` tool calls and end the graph turn."""

    state_schema = ClarificationMiddlewareState

    def _stable_message_id(self, tool_call_id: str, formatted_message: str) -> str:
        if tool_call_id:
            return f"clarification:{tool_call_id}"
        digest = sha256(formatted_message.encode("utf-8")).hexdigest()[:16]
        return f"clarification:{digest}"

    def _format_clarification_message(self, args: dict[str, Any]) -> str:
        question = str(args.get("question", ""))
        clarification_type = str(args.get("clarification_type", "missing_info"))
        context = args.get("context")
        options = args.get("options", [])

        type_labels = {
            "missing_info": "Clarification needed",
            "ambiguous_requirement": "Ambiguous requirement",
            "approach_choice": "Approach choice",
            "risk_confirmation": "Risk confirmation",
            "suggestion": "Suggestion",
        }
        label = type_labels.get(clarification_type, "Clarification needed")

        message_parts: list[str] = []
        if context:
            message_parts.append(f"{label}: {context}")
            message_parts.append("")
            message_parts.append(question)
        else:
            message_parts.append(f"{label}: {question}")

        if isinstance(options, list) and options:
            message_parts.append("")
            for i, option in enumerate(options, 1):
                message_parts.append(f"  {i}. {option}")

        return "\n".join(message_parts)

    def _handle_clarification(self, request: ToolCallRequest) -> Command[Any]:
        args = request.tool_call.get("args", {})
        if not isinstance(args, dict):
            args = {}
        question = args.get("question", "")

        logger.info("[ClarificationMiddleware] Intercepted clarification request")
        logger.info("[ClarificationMiddleware] Question: %s", question)

        formatted_message = self._format_clarification_message(args)
        tool_call_id = str(request.tool_call.get("id", ""))
        tool_message = ToolMessage(
            id=self._stable_message_id(tool_call_id, formatted_message),
            content=formatted_message,
            tool_call_id=tool_call_id,
            name="ask_clarification",
        )

        return Command(update={"messages": [tool_message]}, goto=END)

    @override
    def wrap_tool_call(
        self,
        request: ToolCallRequest,
        handler: Callable[[ToolCallRequest], ToolMessage | Command[Any]],
    ) -> ToolMessage | Command[Any]:
        if request.tool_call.get("name") != "ask_clarification":
            return handler(request)
        return self._handle_clarification(request)

    @override
    async def awrap_tool_call(
        self,
        request: ToolCallRequest,
        handler: Callable[[ToolCallRequest], Awaitable[ToolMessage | Command[Any]]],
    ) -> ToolMessage | Command[Any]:
        if request.tool_call.get("name") != "ask_clarification":
            return await handler(request)
        return self._handle_clarification(request)
