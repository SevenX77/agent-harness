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
from dataclasses import dataclass
from hashlib import sha256
from typing import Any

from langchain.agents import AgentState
from langchain.agents.middleware import AgentMiddleware
from langchain_core.messages import ToolMessage
from langgraph.graph import END
from langgraph.prebuilt.tool_node import ToolCallRequest
from langgraph.types import Command, interrupt
from pydantic import BaseModel
from pydantic import ValidationError as PydanticValidationError

from graph_agent.core.exceptions import ErrorPayload, GraphAgentError, make_error_payload
from graph_agent.core.io_manager import IOManager
from graph_agent.core.schema_engine import SchemaEngine, SchemaObject
from graph_agent.core.state import BusinessData, FrameworkState, StateManager, WorkflowState
from graph_agent.tools.md_to_json import parse_md

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
    _REJECTION_PREFIX = "[提交已被系统驳回] 当前任务仍未结束，请继续修正并重新提交！"

    def __init__(
        self,
        io_manager: IOManager,
        unattended: bool = False,
        *,
        schema_engine: SchemaEngine | None = None,
        current_phase_schema: type[BaseModel] | SchemaObject | None = None,
        business_validator: Callable[[list[dict[str, Any]]], tuple[bool, list[str]]] | None = None,
        phase_name: str = "unknown",
        interrupt_fn: InterruptFn | None = None,
    ) -> None:
        # Phase 2 A2 v3 + Phase 3 M7 (PHASE2_DESIGN.md §3.4, PHASE3_DESIGN.md §3):
        # ``current_phase_schema`` accepts ``type[BaseModel] | SchemaObject |
        # None``. ``_validate_finish_args`` dispatches on schema kind:
        # ``SchemaObject`` walks ``schema_engine.get_pydantic_model`` +
        # ``schema_engine.validate``; ``type[BaseModel]`` skips the engine
        # round-trip and validates each parsed block directly with
        # ``schema_cls.model_validate`` (unblocks dotted-path SKILLs whose
        # ``output_schema`` resolves to a Pydantic class at load time).
        #
        # ``business_validator`` is the per-phase business-rule callable
        # mounted via the SKILL's ``validator:`` field. It receives the
        # parsed items list (``list[dict[str, Any]]`` per A1 §2.4) AFTER
        # Pydantic validation succeeds; failures route back to the LLM as
        # retry feedback. M7 retired the legacy parallel pipeline so this
        # middleware is now the sole owner of finish_task validation.
        super().__init__()
        self._io_manager = io_manager
        self._unattended = bool(unattended)
        self._schema_engine = schema_engine or SchemaEngine()
        self._current_phase_schema = current_phase_schema
        self._business_validator = business_validator
        self._phase_name = phase_name
        self._interrupt_fn = interrupt_fn or interrupt

    @staticmethod
    def validate_finish_task_with_schema_gate(
        *,
        business_data_md: str | None = None,
        output: dict[str, Any] | None = None,
        output_schema: dict[str, Any] | SchemaObject | None,
        state: dict[str, Any] | None = None,
        phase_name: str = "unknown",
        business_validator: Callable[..., Any] | None = None,
        schema_engine: SchemaEngine | None = None,
    ) -> FinishTaskSchemaGateResult:
        """Validate finish_task output against compiled ``io.outputs`` before any write.

        PR β keeps this as a small schema gate: business validator wiring
        is deliberately later, so this method only guarantees that schema
        failures do not call ``business_validator`` and do not expose a
        final write candidate.
        """
        del state, business_validator
        engine = schema_engine or SchemaEngine()

        if output_schema is None:
            return _schema_gate_reject(
                phase_name=phase_name,
                code="[F-v3-agent-output-schema-missing]",
                errors=("finish_task reached schema gate without compiled io.outputs.",),
            )

        if output is None:
            parsed = _parse_finish_task_output_payload(business_data_md)
            if not isinstance(parsed, dict):
                return _schema_gate_reject(
                    phase_name=phase_name,
                    code="[F-v3-agent-output-schema-invalid]",
                    errors=(
                        "business_data_md must decode to a JSON object for schema validation.",
                    ),
                )
            output = parsed

        try:
            schema = _coerce_output_schema(output_schema, engine)
            validation = engine.validate(output, schema)
        except Exception as exc:  # noqa: BLE001 - schema issues become tool feedback
            logger.warning(
                "schema gate failed before validation: phase=%s exc=%s",
                phase_name,
                exc,
            )
            return _schema_gate_reject(
                phase_name=phase_name,
                code="[F-v3-agent-output-schema-invalid]",
                errors=(f"invalid compiled io.outputs schema: {exc}",),
            )
        if not validation.ok:
            return _schema_gate_reject(
                phase_name=phase_name,
                code="[F-v3-agent-output-schema-invalid]",
                errors=validation.errors,
            )

        parsed_output = validation.parsed or dict(output)
        return FinishTaskSchemaGateResult(
            True,
            None,
            None,
            None,
            parsed_output,
            parsed_output,
            (),
        )

    @staticmethod
    def invoke_validator_with_contract(
        *,
        validator: Callable[..., dict[str, Any] | None] | None,
        output: dict[str, Any],
        state_slice: dict[str, Any],
        phase_name: str = "unknown",
        **kwargs: Any,
    ) -> ValidatorRuntimeResult:
        """Run the PR β validator contract after schema validation passes."""
        if validator is None:
            return ValidatorRuntimeResult(True, None, None, None)

        try:
            result = validator(output, state_slice, phase_name=phase_name, **kwargs)
        except Exception as exc:  # noqa: BLE001 - converted to LLM-visible feedback
            logger.warning("validator exception: phase=%s exc=%s", phase_name, exc)
            return _validator_runtime_reject(
                phase_name=phase_name,
                feedback=f"{type(exc).__name__}: {exc}",
            )

        if result is None:
            return ValidatorRuntimeResult(True, None, None, None)

        feedback = json.dumps(result, ensure_ascii=False, sort_keys=True, default=str)
        logger.warning("validator rejected: phase=%s feedback=%s", phase_name, feedback)
        return _validator_runtime_reject(phase_name=phase_name, feedback=feedback)

    def handle_finish_task_tool_result(
        self,
        *,
        tool_name: str,
        tool_result: Any,
        output_schema: dict[str, Any] | SchemaObject | None,
        flow: dict[str, Any],
        messages: list[Any],
        critic_metrics: dict[str, Any],
    ) -> dict[str, Any] | None:
        """Handle a finish_task tool result for graph assembly callers."""
        if tool_name != self._FINISH_TOOL:
            return None

        result_payload = tool_result if isinstance(tool_result, dict) else {}
        next_flow = dict(flow)
        next_flow["finish_task_result"] = result_payload
        next_flow.setdefault("critic_metrics", {}).update(
            {
                key: {
                    "invocations": value.invocations,
                    "passed": value.passed,
                    "rejected": value.rejected,
                }
                for key, value in critic_metrics.items()
            }
        )

        if not result_payload.get("ok"):
            return {"flow": next_flow, "messages": messages}

        output = result_payload.get("data", {})
        if not isinstance(output, dict):
            output = {}

        if not _has_strict_output_schema(output_schema):
            return _finish_task_accept_response(
                phase_name=self._phase_name,
                flow=next_flow,
                messages=messages,
                final_write=output,
            )

        schema_gate = self.validate_finish_task_with_schema_gate(
            output=output,
            output_schema=output_schema,
            state={"flow": next_flow},
            phase_name=self._phase_name,
            business_validator=None,
        )
        if not schema_gate.accepted:
            if schema_gate.tool_message is not None:
                messages.append(schema_gate.tool_message)
            return {"flow": next_flow, "messages": messages}

        validator_result = self.invoke_validator_with_contract(
            validator=None,
            output=schema_gate.output or output,
            state_slice={"flow": next_flow},
            phase_name=self._phase_name,
        )
        if not validator_result.accepted:
            if validator_result.tool_message is not None:
                messages.append(validator_result.tool_message)
            return {"flow": next_flow, "messages": messages}

        return _finish_task_accept_response(
            phase_name=self._phase_name,
            flow=next_flow,
            messages=messages,
            final_write=schema_gate.final_write or {},
        )

    @staticmethod
    def intercept_ask_clarification(
        *,
        tool: Any,
        args: dict[str, Any],
        state: dict[str, Any],
        unattended: bool,
        interrupt_fn: Callable[[dict[str, Any]], str] | None,
    ) -> ClarificationResult:
        """Intercept ask_clarification for attended and unattended unit paths."""
        del tool
        question = str(args.get("question") or "").strip()
        if unattended:
            return ClarificationResult(
                answer=_unattended_clarification_answer(question),
                source="unattended_auto_answer",
            )

        payload: dict[str, Any] = {"question": question}
        payload.update(state)
        try:
            answer = interrupt_fn(payload) if interrupt_fn is not None else ""
        except RuntimeError as exc:
            if "outside of a runnable context" not in str(exc):
                raise
            return ClarificationResult(
                answer=str(state.get("message") or question),
                source="needs_human_input",
            )
        return ClarificationResult(answer=str(answer), source="human_interrupt")

    @staticmethod
    def dispatch_tool_call(
        *,
        tool_name: str,
        args: dict[str, Any],
        state: dict[str, Any],
        handler: Callable[[str, dict[str, Any]], Any],
    ) -> Any:
        """Pass non-cognitive tools through unchanged."""
        del state
        if tool_name in {
            CognitiveFlowMiddleware._FINISH_TOOL,
            CognitiveFlowMiddleware._CLARIFICATION_TOOL,
        }:
            return {"handled": False, "tool_name": tool_name, "args": args}
        return handler(tool_name, args)

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
            return True, self.intercept_ask_clarification(
                tool=None,
                args=args,
                state={"phase_name": self._phase_name},
                unattended=self._unattended,
                interrupt_fn=self._interrupt_fn,
            )
        return False, self.dispatch_tool_call(
            tool_name=tool_name,
            args=args,
            state={"phase_name": self._phase_name},
            handler=lambda _tool_name, _args: None,
        )

    def wrap_tool_call(
        self,
        request: ToolCallRequest,
        handler: ToolCallHandler,
    ) -> ToolCallResult:
        """Intercept supported tool calls and pass all others through."""
        tool_name = str(request.tool_call.get("name") or "")
        if tool_name not in {self._FINISH_TOOL, self._CLARIFICATION_TOOL}:
            args = request.tool_call.get("args", {})
            result: ToolCallResult = self.dispatch_tool_call(
                tool_name=tool_name,
                args=args if isinstance(args, dict) else {},
                state={"phase_name": self._phase_name},
                handler=lambda _tool_name, _args: handler(request),
            )
            return result

        parsed_args = self._args_dict(request)
        if isinstance(parsed_args, Command):
            return parsed_args

        if tool_name == self._CLARIFICATION_TOOL:
            return self._clarification_command(
                self.intercept_ask_clarification(
                    tool=None,
                    args=parsed_args,
                    state=self._clarification_state(parsed_args),
                    unattended=self._unattended,
                    interrupt_fn=self._interrupt_fn,
                ),
                args=parsed_args,
                tool_call_id=_tool_call_id(request),
            )

        state = _workflow_state_or_none(request.state)
        if state is None:
            logger.debug("[CognitiveFlowMiddleware] finish_task pass-through without WorkflowState")
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
            return self._clarification_command(
                self.intercept_ask_clarification(
                    tool=None,
                    args=parsed_args,
                    state=self._clarification_state(parsed_args),
                    unattended=self._unattended,
                    interrupt_fn=self._interrupt_fn,
                ),
                args=parsed_args,
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
            "phase=%s action=cognitive_flow_parse fallback from=parse_json to=llm_retry reason=%s",
            self._phase_name,
            type(exc).__name__,
        )
        return Command(
            goto="model",
            update={
                "messages": [
                    ToolMessage(
                        status="error",
                        content=(f"JSON parse failed: {exc}. Please retry with valid JSON."),
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

        # Phase 2 A2 v3 schema dispatch (design v4 §3.4 step 2): pick the
        # Pydantic model class either by asking the schema engine to
        # synthesize one from a SchemaObject, or — for SKILLs that
        # declared ``output_schema`` as a dotted Python path — using the
        # already-imported ``type[BaseModel]`` directly.
        try:
            if isinstance(schema, SchemaObject):
                model = self._schema_engine.get_pydantic_model(schema)
            else:
                model = schema
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
            item_id = block.meta.id or "unknown"
            if isinstance(schema, SchemaObject):
                result = self._schema_engine.validate(block.data, schema)
                if result.ok:
                    parsed_items.append(result.parsed or dict(block.data))
                else:
                    errors.extend(f"item {item_id}: {error}" for error in result.errors)
                continue
            # Pydantic class path: validate the per-item dict directly
            # against the imported BaseModel and surface any
            # ValidationError as a per-item, per-field message so the LLM
            # can correct the markdown on retry.
            try:
                instance = model.model_validate(block.data)
            except PydanticValidationError as exc:
                for detail in exc.errors():
                    loc_parts = detail.get("loc", ())
                    loc = ".".join(str(part) for part in loc_parts) or "__root__"
                    msg = str(detail.get("msg", "validation error"))
                    errors.append(f"item {item_id}: {loc}: {msg}")
                continue
            parsed_items.append(instance.model_dump())

        if errors:
            return _FinishValidation(
                ok=False,
                schema_validation="failed",
                errors=tuple(errors),
            )

        # Phase 2 A2 v3 (design v4 §3.2 #3): run the per-phase business
        # validator on the parsed items list. Pydantic has already
        # asserted the per-item shape; the business validator owns
        # cross-item / domain-specific rules (e.g. line-number continuity
        # for text-segmentation, ID-uniqueness for event-extraction).
        # Validators receive ``list[dict[str, Any]]`` per A1 §2.4.
        business_errors = self._run_business_validator(parsed_items)
        if business_errors:
            return _FinishValidation(
                ok=False,
                schema_validation="failed",
                errors=tuple(business_errors),
            )

        return _FinishValidation(
            ok=True,
            schema_validation="passed",
            parsed_items=parsed_items,
        )

    def _run_business_validator(self, parsed_items: list[dict[str, Any]]) -> list[str]:
        """Phase 2 A2 v3: invoke the optional business validator and
        normalise its (passed, errors) return into a list of strings.

        Validators must conform to A1 §2.4 — they take the parsed items
        list and return ``(bool, list[str])``. Any unexpected exception
        is captured and surfaced to the LLM as a single retry-feedback
        line so the agent loop can recover instead of crashing the
        whole run.
        """
        validator = self._business_validator
        if validator is None:
            return []
        try:
            passed, errors = validator(parsed_items)
        except Exception as exc:  # noqa: BLE001 - returned to LLM as retry feedback
            logger.warning(
                "phase=%s action=cognitive_flow_business_validator decision=fail "
                "reason=exception exc=%s",
                self._phase_name,
                type(exc).__name__,
            )
            return [
                f"[Business] validator 异常：{type(exc).__name__}: {exc}",
            ]
        if passed:
            logger.info(
                "phase=%s action=cognitive_flow_business_validator decision=pass items=%d",
                self._phase_name,
                len(parsed_items),
            )
            return []
        if isinstance(errors, str):
            errors = [errors] if errors else []
        elif not isinstance(errors, list):
            errors = [str(errors)] if errors else []
        logger.warning(
            "phase=%s action=cognitive_flow_business_validator decision=reject issue_count=%d",
            self._phase_name,
            len(errors),
        )
        return [f"[Business] {err}" for err in errors]

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

    def _clarification_state(self, args: dict[str, Any]) -> dict[str, Any]:
        formatted = self._format_clarification_message(args)
        return {
            "tool": self._CLARIFICATION_TOOL,
            "phase_name": self._phase_name,
            "message": formatted,
            "args": args,
        }

    def _clarification_command(
        self,
        result: ClarificationResult,
        *,
        args: dict[str, Any],
        tool_call_id: str,
    ) -> Command[Any]:
        if result.source in {"human_interrupt", "unattended_auto_answer"}:
            if result.source == "unattended_auto_answer":
                logger.info("[CognitiveFlowMiddleware] auto-answered ask_clarification")
            return Command(
                update={
                    "messages": [
                        ToolMessage(
                            content=result.answer,
                            name=self._CLARIFICATION_TOOL,
                            tool_call_id=tool_call_id,
                        )
                    ]
                },
                goto="model",
            )

        formatted = result.answer or self._format_clarification_message(args)
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


@dataclass(frozen=True)
class FinishTaskSchemaGateResult:
    """Result returned by the PR β strict io.outputs schema gate."""

    accepted: bool
    error_code: str | None
    payload: ErrorPayload | None
    tool_message: ToolMessage | None
    final_write: dict[str, Any] | None
    output: dict[str, Any] | None = None
    errors: tuple[str, ...] = ()


@dataclass(frozen=True)
class ValidatorRuntimeResult:
    """Result returned by the PR β validator runtime adapter."""

    accepted: bool
    error_code: str | None
    payload: ErrorPayload | None
    feedback: str | None
    tool_message: ToolMessage | None = None


@dataclass(frozen=True)
class ClarificationResult:
    """Small return value for PR β ask_clarification interception tests."""

    answer: str
    source: str


def _parse_finish_task_output_payload(business_data_md: str | None) -> dict[str, Any] | None:
    text = str(business_data_md or "").strip()
    if not text:
        return None
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None


def _unattended_clarification_answer(question: str) -> str:
    return (
        "[系统] 当前执行流为无人值守环境（unattended=True），不允许人类干预。"
        "请基于当前已有上下文做出最保守、最合理的推测并继续执行任务。"
        "务必在最终 finish_task 的 diagnostics_md 中明确记录：\n"
        f"  - 你曾想问的问题：{question or '未提供'}\n"
        "  - 你做出的推测：[你的推测]\n"
        "  - 该推测的依据：[依据]\n"
        "现在请继续执行后续步骤。"
    )


def _has_strict_output_schema(output_schema: dict[str, Any] | SchemaObject | None) -> bool:
    if output_schema is None:
        return False
    if isinstance(output_schema, SchemaObject):
        return bool(output_schema.fields)
    properties = output_schema.get("properties")
    return isinstance(properties, dict) and bool(properties)


def _finish_task_accept_response(
    *,
    phase_name: str,
    flow: dict[str, Any],
    messages: list[Any],
    final_write: dict[str, Any],
) -> dict[str, Any]:
    response_state: dict[str, Any] = {"flow": flow, "messages": messages}
    response_state["data"] = {
        "inputs": {},
        "phase_outputs": {phase_name: final_write},
        "scratch": {},
    }
    return response_state


def _coerce_output_schema(
    output_schema: dict[str, Any] | SchemaObject,
    schema_engine: SchemaEngine,
) -> SchemaObject:
    if isinstance(output_schema, SchemaObject):
        return output_schema
    return schema_engine.parse_from_md(json.dumps(output_schema, ensure_ascii=False))


def _schema_gate_reject(
    *,
    phase_name: str,
    code: str,
    errors: tuple[str, ...],
) -> FinishTaskSchemaGateResult:
    content = "\n".join((code, f"phase={phase_name}", *errors))
    payload = make_error_payload(code, content, phase_id=phase_name)
    return FinishTaskSchemaGateResult(
        False,
        code,
        payload,
        ToolMessage(
            content=content,
            name=CognitiveFlowMiddleware._FINISH_TOOL,
            tool_call_id="schema-gate",
            status="error",
        ),
        None,
        None,
        errors,
    )


def _validator_runtime_reject(
    *,
    phase_name: str,
    feedback: str,
) -> ValidatorRuntimeResult:
    error_code = "[F-v3-agent-validator-failed]"
    content = "\n".join((error_code, f"phase={phase_name}", feedback))
    payload = make_error_payload(error_code, content, phase_id=phase_name)
    return ValidatorRuntimeResult(
        False,
        error_code,
        payload,
        content,
        ToolMessage(
            content=content,
            name=CognitiveFlowMiddleware._FINISH_TOOL,
            tool_call_id="validator-runtime",
            status="error",
        ),
    )


def _workflow_state_or_none(value: object) -> WorkflowState | None:
    if not isinstance(value, dict):
        return None
    data = value.get("data")
    flow = value.get("flow")
    messages = value.get("messages")
    if (
        isinstance(data, BusinessData)
        and isinstance(flow, FrameworkState)
        and isinstance(messages, list)
    ):
        return WorkflowState(data=data, flow=flow, messages=messages)
    return None


def _tool_call_id(request: ToolCallRequest) -> str:
    return str(request.tool_call.get("id") or "")


__all__ = ["CognitiveFlowError", "CognitiveFlowMiddleware"]
