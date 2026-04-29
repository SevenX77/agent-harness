"""CognitiveFlowMiddleware — finish_task and clarification tool interception.

MVP-3 T8 moves the cognitive tool-call side effects into the new
``graph_agent.middleware`` package. The legacy ``cognitive`` middleware
chain stays in place until the follow-up cleanup, but this class is the
new owner for two behaviours:

* ``finish_task``: parse and validate ``business_data_md`` with
  ``SchemaEngine``, persist the structured result in ``FrameworkState``,
  run ``IOManager.resolve_hoist``, and return a LangGraph state update
  that writes the new ``BusinessData``.
* ``ask_clarification``: one implementation for attended and unattended
  mode. Attended mode uses LangGraph ``interrupt`` when running inside a
  graph and falls back to the existing end-turn message outside one;
  unattended mode returns a conservative auto-answer and routes back to
  the model.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Awaitable, Callable
from hashlib import sha256
from typing import Any

from langchain.agents import AgentState
from langchain.agents.middleware import AgentMiddleware
from langchain_core.messages import ToolMessage
from langgraph.graph import END
from langgraph.prebuilt.tool_node import ToolCallRequest
from langgraph.types import Command, interrupt

from ..core.exceptions import GraphAgentError
from ..core.io_manager import IOManager
from ..core.schema_engine import SchemaEngine, SchemaObject
from ..core.state import BusinessData, FrameworkState, StateManager, WorkflowState
from ..tools.md_to_json import parse_md

logger = logging.getLogger(__name__)

ToolCallResult = ToolMessage | Command[Any]
ToolCallHandler = Callable[[ToolCallRequest], ToolCallResult]
AsyncToolCallHandler = Callable[[ToolCallRequest], Awaitable[ToolCallResult]]
InterruptFn = Callable[[dict[str, Any]], Any]


class CognitiveFlowError(GraphAgentError):
    """Raised when CognitiveFlow cannot apply a stateful interception."""


class CognitiveFlowMiddleware(AgentMiddleware[AgentState[Any]]):
    """Handle non-business tool-call flow for ``finish_task`` and clarification."""

    _FINISH_TOOL = "finish_task"
    _CLARIFICATION_TOOL = "ask_clarification"
    _REJECTION_PREFIX = (
        "[提交已被系统驳回] 当前任务仍未结束，请继续修正并重新提交！"
    )

    def __init__(
        self,
        io_manager: IOManager,
        unattended: bool = False,
        *,
        schema_engine: SchemaEngine | None = None,
        current_phase_schema: SchemaObject | None = None,
        phase_name: str = "unknown",
        interrupt_fn: InterruptFn | None = None,
    ) -> None:
        super().__init__()
        self._io_manager = io_manager
        self._unattended = bool(unattended)
        self._schema_engine = schema_engine or SchemaEngine()
        self._current_phase_schema = current_phase_schema
        self._phase_name = phase_name
        self._interrupt_fn = interrupt_fn or interrupt

    def intercept_tool_call(
        self,
        tool_name: str,
        args: dict[str, Any],
        state: WorkflowState,
    ) -> tuple[bool, Any]:
        """Return ``(handled, result)`` for design.md §5.3 callers.

        ``wrap_tool_call`` uses the richer private helper so it can keep
        the original tool-call id in the emitted ``ToolMessage``. This
        public method keeps the design-level API small and testable.
        """
        if tool_name == self._FINISH_TOOL:
            return True, self._handle_finish_task(args, state, tool_call_id="")
        if tool_name == self._CLARIFICATION_TOOL:
            return True, self._handle_clarification(args, tool_call_id="")
        return False, None

    def wrap_tool_call(
        self,
        request: ToolCallRequest,
        handler: ToolCallHandler,
    ) -> ToolCallResult:
        """Intercept supported tool calls and pass all others through."""
        tool_name = str(request.tool_call.get("name") or "")
        if tool_name not in {self._FINISH_TOOL, self._CLARIFICATION_TOOL}:
            return handler(request)

        parsed_args = self._args_dict(request)
        if isinstance(parsed_args, Command):
            return parsed_args

        if tool_name == self._CLARIFICATION_TOOL:
            return self._handle_clarification(
                parsed_args,
                tool_call_id=_tool_call_id(request),
            )

        state = _workflow_state_or_none(request.state)
        if state is None:
            logger.debug(
                "[CognitiveFlowMiddleware] finish_task pass-through without WorkflowState"
            )
            return handler(request)
        return self._handle_finish_task(
            parsed_args,
            state,
            tool_call_id=_tool_call_id(request),
        )

    async def awrap_tool_call(
        self,
        request: ToolCallRequest,
        handler: AsyncToolCallHandler,
    ) -> ToolCallResult:
        """Async equivalent of :meth:`wrap_tool_call`."""
        tool_name = str(request.tool_call.get("name") or "")
        if tool_name not in {self._FINISH_TOOL, self._CLARIFICATION_TOOL}:
            return await handler(request)

        parsed_args = self._args_dict(request)
        if isinstance(parsed_args, Command):
            return parsed_args

        if tool_name == self._CLARIFICATION_TOOL:
            return self._handle_clarification(
                parsed_args,
                tool_call_id=_tool_call_id(request),
            )

        state = _workflow_state_or_none(request.state)
        if state is None:
            logger.debug(
                "[CognitiveFlowMiddleware] finish_task async pass-through without WorkflowState"
            )
            return await handler(request)
        return self._handle_finish_task(
            parsed_args,
            state,
            tool_call_id=_tool_call_id(request),
        )

    def _args_dict(self, request: ToolCallRequest) -> dict[str, Any] | Command[Any]:
        args = request.tool_call.get("args", {})
        if isinstance(args, dict):
            return dict(args)
        if isinstance(args, str):
            try:
                parsed = json.loads(args)
            except (TypeError, ValueError) as exc:
                return self._json_parse_retry(request, exc)
            return parsed if isinstance(parsed, dict) else {}
        return {}

    def _json_parse_retry(
        self,
        request: ToolCallRequest,
        exc: TypeError | ValueError,
    ) -> Command[Any]:
        tool_name = str(request.tool_call.get("name") or "unknown")
        logger.warning(
            "phase=%s action=cognitive_flow_parse fallback "
            "from=parse_json to=llm_retry reason=%s",
            self._phase_name,
            type(exc).__name__,
        )
        return Command(
            goto="model",
            update={
                "messages": [
                    ToolMessage(
                        status="error",
                        content=(
                            f"JSON parse failed: {exc}. "
                            "Please retry with valid JSON."
                        ),
                        name=tool_name,
                        tool_call_id=_tool_call_id(request),
                    )
                ]
            },
        )

    def _handle_finish_task(
        self,
        args: dict[str, Any],
        state: WorkflowState,
        *,
        tool_call_id: str,
    ) -> Command[Any]:
        validation = self._validate_finish_args(args)
        if not validation.ok:
            return self._reject_finish(tool_call_id, list(validation.errors))

        finish_result: dict[str, Any] = {
            "reasoning": str(args.get("reasoning") or "").strip(),
            "diagnostics_md": str(args.get("diagnostics_md") or "").strip(),
            "business_data_md": str(args.get("business_data_md") or "").strip(),
            "schema_validation": validation.schema_validation,
        }
        if validation.parsed_items is not None:
            finish_result["business_data_parsed"] = validation.parsed_items

        next_state = StateManager.update_framework(
            state,
            finish_task_result=finish_result,
        )
        next_state = self._apply_io_hoist(next_state, finish_result)

        logger.info(
            "[CognitiveFlowMiddleware] accepted finish_task phase=%s schema=%s",
            self._phase_name,
            validation.schema_validation,
        )
        return Command(
            update={
                "data": next_state["data"],
                "flow": next_state["flow"],
                "messages": [
                    ToolMessage(
                        content="PHASE_COMPLETE",
                        name=self._FINISH_TOOL,
                        tool_call_id=tool_call_id,
                    )
                ],
            },
            goto=END,
        )

    def _validate_finish_args(self, args: dict[str, Any]) -> _FinishValidation:
        schema = self._current_phase_schema
        if schema is None:
            # Phase 2 A1 contract: any phase reaching CognitiveFlowMiddleware's
            # finish_task validation must already have a compiled output_schema.
            # The compile-time gate in skill_validator.py rejects validator-
            # bearing LLMPhases without schemas; getting here means either an
            # upstream wiring bug (the middleware was mounted on a schema-less
            # phase) or a phase that bypassed compile validation entirely.
            # Either way we must fail loud, never silently mark "skipped".
            logger.error(
                "phase=%s action=cognitive_flow_finish_task decision=reject "
                "reason=missing_output_schema",
                self._phase_name,
            )
            raise CognitiveFlowError(
                f"Phase '{self._phase_name}' reached CognitiveFlowMiddleware "
                "finish_task without a compiled output_schema. Phase 2 A1 "
                "contract: every phase using finish_task validation must "
                "declare output_schema (or output_example) at SKILL.md "
                "compile time."
            )

        business_data_md = str(args.get("business_data_md") or "").strip()
        if not business_data_md:
            return _FinishValidation(
                ok=False,
                schema_validation="failed",
                errors=("business_data_md 是空。必须填入完整 markdown 结果。",),
            )

        try:
            model = self._schema_engine.get_pydantic_model(schema)
            blocks = parse_md(business_data_md, model)
        except Exception as exc:  # noqa: BLE001 - returned to LLM as retry feedback
            return _FinishValidation(
                ok=False,
                schema_validation="failed",
                errors=(f"Markdown 解析失败：{type(exc).__name__}: {exc}",),
            )

        if not blocks:
            return _FinishValidation(
                ok=False,
                schema_validation="failed",
                errors=(
                    "未能在 business_data_md 中检测到任何 ## 块。"
                    "必须按 output_schema 范例输出至少 1 个 ## 块。",
                ),
            )

        parsed_items: list[dict[str, Any]] = []
        errors: list[str] = []
        for block in blocks:
            result = self._schema_engine.validate(block.data, schema)
            if result.ok:
                parsed_items.append(result.parsed or dict(block.data))
                continue
            item_id = block.meta.id or "unknown"
            errors.extend(f"item {item_id}: {error}" for error in result.errors)

        if errors:
            return _FinishValidation(
                ok=False,
                schema_validation="failed",
                errors=tuple(errors),
            )
        return _FinishValidation(
            ok=True,
            schema_validation="passed",
            parsed_items=parsed_items,
        )

    def _reject_finish(self, tool_call_id: str, errors: list[str]) -> Command[Any]:
        content = self._REJECTION_PREFIX + "\n" + "\n".join(errors)
        logger.info(
            "[CognitiveFlowMiddleware] rejected finish_task phase=%s errors=%d",
            self._phase_name,
            len(errors),
        )
        return Command(
            update={
                "messages": [
                    ToolMessage(
                        content=content,
                        name=self._FINISH_TOOL,
                        tool_call_id=tool_call_id,
                        status="error",
                    )
                ]
            },
            goto="model",
        )

    def _apply_io_hoist(
        self,
        state: WorkflowState,
        finish_result: dict[str, Any],
    ) -> WorkflowState:
        result = self._io_manager.resolve_hoist(finish_result, state["data"])
        next_state = state

        new_dump = result.new_business_data.model_dump()
        if new_dump != state["data"].model_dump():
            next_state = StateManager.update_business(next_state, **new_dump)

        if result.io_errors:
            existing = list(next_state["flow"].io_errors)
            next_state = StateManager.update_framework(
                next_state,
                io_errors=existing + list(result.io_errors),
            )
        return next_state

    def _handle_clarification(
        self,
        args: dict[str, Any],
        *,
        tool_call_id: str,
    ) -> Command[Any]:
        if self._unattended:
            return self._auto_answer_clarification(args, tool_call_id=tool_call_id)
        return self._interrupt_clarification(args, tool_call_id=tool_call_id)

    def _auto_answer_clarification(
        self,
        args: dict[str, Any],
        *,
        tool_call_id: str,
    ) -> Command[Any]:
        question = str(args.get("question") or "").strip()
        content = (
            "[系统] 当前执行流为无人值守环境（unattended=True），不允许人类干预。"
            "请基于当前已有上下文做出最保守、最合理的推测并继续执行任务。"
            "务必在最终 finish_task 的 diagnostics_md 中明确记录：\n"
            f"  - 你曾想问的问题：{question or '未提供'}\n"
            "  - 你做出的推测：[你的推测]\n"
            "  - 该推测的依据：[依据]\n"
            "现在请继续执行后续步骤。"
        )
        logger.info("[CognitiveFlowMiddleware] auto-answered ask_clarification")
        return Command(
            update={
                "messages": [
                    ToolMessage(
                        content=content,
                        name=self._CLARIFICATION_TOOL,
                        tool_call_id=tool_call_id,
                    )
                ]
            },
            goto="model",
        )

    def _interrupt_clarification(
        self,
        args: dict[str, Any],
        *,
        tool_call_id: str,
    ) -> Command[Any]:
        formatted = self._format_clarification_message(args)
        payload = {
            "tool": self._CLARIFICATION_TOOL,
            "phase_name": self._phase_name,
            "message": formatted,
            "args": args,
        }
        try:
            human_answer = self._interrupt_fn(payload)
        except RuntimeError as exc:
            # Unit tests and direct middleware calls run outside LangGraph's
            # runnable context. In that case keep legacy behaviour: surface a
            # tool message and end the graph turn for the host to handle.
            if "outside of a runnable context" not in str(exc):
                raise
            human_answer = None

        if human_answer is not None:
            return Command(
                update={
                    "messages": [
                        ToolMessage(
                            content=str(human_answer),
                            name=self._CLARIFICATION_TOOL,
                            tool_call_id=tool_call_id,
                        )
                    ]
                },
                goto="model",
            )

        return Command(
            update={
                "messages": [
                    ToolMessage(
                        id=self._stable_message_id(tool_call_id, formatted),
                        content=formatted,
                        name=self._CLARIFICATION_TOOL,
                        tool_call_id=tool_call_id,
                    )
                ]
            },
            goto=END,
        )

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
            for index, option in enumerate(options, 1):
                message_parts.append(f"  {index}. {option}")

        return "\n".join(message_parts)

    def _stable_message_id(self, tool_call_id: str, formatted_message: str) -> str:
        if tool_call_id:
            return f"clarification:{tool_call_id}"
        digest = sha256(formatted_message.encode("utf-8")).hexdigest()[:16]
        return f"clarification:{digest}"


class _FinishValidation:
    def __init__(
        self,
        *,
        ok: bool,
        schema_validation: str,
        parsed_items: list[dict[str, Any]] | None = None,
        errors: tuple[str, ...] = (),
    ) -> None:
        self.ok = ok
        self.schema_validation = schema_validation
        self.parsed_items = parsed_items
        self.errors = errors


def _workflow_state_or_none(value: object) -> WorkflowState | None:
    if not isinstance(value, dict):
        return None
    data = value.get("data")
    flow = value.get("flow")
    messages = value.get("messages")
    if isinstance(data, BusinessData) and isinstance(flow, FrameworkState) and isinstance(messages, list):
        return WorkflowState(data=data, flow=flow, messages=messages)
    return None


def _tool_call_id(request: ToolCallRequest) -> str:
    return str(request.tool_call.get("id") or "")


__all__ = ["CognitiveFlowError", "CognitiveFlowMiddleware"]
