"""Custom middlewares for GraphAgent agent execution.

These middlewares are designed for `langchain.agents.create_agent(..., middleware=...)`.
They may also be reused by DeerFlow's hook-based lead-agent path, but the primary
consumer is `GraphAgentHarness`.
"""

from __future__ import annotations

import logging
import json
from collections.abc import Awaitable, Callable, Mapping, Sequence
from typing import Any

try:
    from typing import override
except ImportError:  # pragma: no cover - Python < 3.12
    from typing_extensions import override

from langchain.agents import AgentState
from langchain.agents.middleware import AgentMiddleware
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langgraph.prebuilt.tool_node import ToolCallRequest
from langgraph.runtime import Runtime
from langgraph.types import Command
from pydantic import BaseModel

from ..callbacks.base import Callback
from ..tools.dynamic_schema import (
    DynamicSchemaDef,
    coerce_item_against_dynamic_schema,
    parse_md_simple,
)

logger = logging.getLogger(__name__)

_SUMMARIZATION_FALLBACK_MAX_INPUT_TOKENS = 32_000


class _ProfiledSummarizationModel:
    """Delegate model calls while supplying a conservative LangChain profile."""

    def __init__(self, wrapped: Any, *, max_input_tokens: int) -> None:
        self._wrapped = wrapped
        self.profile = {"max_input_tokens": max_input_tokens}

    def __getattr__(self, name: str) -> Any:
        return getattr(self._wrapped, name)

    def invoke(self, *args: Any, **kwargs: Any) -> Any:
        return self._wrapped.invoke(*args, **kwargs)

    async def ainvoke(self, *args: Any, **kwargs: Any) -> Any:
        return await self._wrapped.ainvoke(*args, **kwargs)


def _has_max_input_profile(model: Any) -> bool:
    try:
        profile = model.profile
    except AttributeError:
        return False
    return (
        isinstance(profile, Mapping)
        and isinstance(profile.get("max_input_tokens"), int)
    )


def _ensure_summarization_profile(model: Any) -> Any:
    if _has_max_input_profile(model):
        return model
    logger.warning(
        "middleware: summarization model lacks profile.max_input_tokens; "
        "using fallback max_input_tokens=%d",
        _SUMMARIZATION_FALLBACK_MAX_INPUT_TOKENS,
    )
    return _ProfiledSummarizationModel(
        model,
        max_input_tokens=_SUMMARIZATION_FALLBACK_MAX_INPUT_TOKENS,
    )


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


class ValidationMiddleware(AgentMiddleware[AgentState]):
    """Validate ``finish_task`` submissions inside the agent loop.

    Pydantic validation and business validators run before the return-direct
    ``finish_task`` tool is allowed to execute. Rejections are returned as
    tool results and routed back to the model node, so the LLM corrects its
    submission in the same LangGraph agent loop instead of restarting the
    whole phase.
    """

    _REJECTION_PREFIX = (
        "[提交已被系统驳回] 当前任务仍未结束，请继续修正并重新提交！"
    )

    def __init__(
        self,
        *,
        output_schema: type[BaseModel] | DynamicSchemaDef | None = None,
        output_schema_path: str | None = None,
        business_validator: Callable[..., tuple[bool, list[str]]] | None = None,
        ctx: dict[str, Any],
        callbacks: Sequence[Callback] | None = None,
        phase_name: str = "unknown",
    ) -> None:
        super().__init__()
        self.output_schema = output_schema
        self.output_schema_path = output_schema_path
        self.business_validator = business_validator
        self.ctx = ctx
        self._callbacks = list(callbacks or [])
        self._phase_name = phase_name
        self.hoist_to = (
            getattr(output_schema, "hoist_to", None)
            or getattr(business_validator, "hoist_to", None)
        )

    def _json_parse_retry(
        self,
        request: ToolCallRequest,
        exc: TypeError | ValueError,
    ) -> Command:
        error_msg = f"JSON parse failed: {exc}. Please retry with valid JSON."
        tool_name = str(request.tool_call.get("name") or "unknown")
        logger.warning(
            "phase=%s action=middleware_parse fallback "
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
                        content=error_msg,
                        name=tool_name,
                        tool_call_id=request.tool_call["id"],
                    )
                ]
            },
        )

    def _args_dict(self, request: ToolCallRequest) -> dict[str, Any] | Command:
        args = request.tool_call.get("args", {})
        if isinstance(args, dict):
            return args
        if isinstance(args, str):
            try:
                parsed = json.loads(args)
            except (TypeError, ValueError) as exc:
                return self._json_parse_retry(request, exc)
            return parsed if isinstance(parsed, dict) else {}
        return {}

    def _resolve_output_schema(self) -> type[BaseModel] | None:
        if isinstance(self.output_schema, DynamicSchemaDef):
            return None
        if self.output_schema is not None:
            return self.output_schema
        if not self.output_schema_path:
            return None
        from ..tools.md_to_json import _resolve_schema_from_path

        self.output_schema = _resolve_schema_from_path(self.output_schema_path)
        return self.output_schema

    def _normalize_errors(self, errors: Any) -> list[str]:
        if errors is None:
            return []
        if isinstance(errors, str):
            return [errors] if errors else []
        if isinstance(errors, list):
            return [str(err) for err in errors if str(err)]
        return [str(errors)] if errors else []

    def _run_business_validator(self, payload: Any) -> list[str]:
        if self.business_validator is None:
            return []
        try:
            passed, errors = self.business_validator(payload)
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "[ValidationMiddleware] business validator failed in phase=%s: %s",
                self._phase_name,
                exc,
            )
            return [f"[Business] validator 异常：{type(exc).__name__}: {exc}"]
        if passed:
            return []
        return [f"[Business] {err}" for err in self._normalize_errors(errors)]

    def _emit_validation_fail(self, errors: list[str]) -> None:
        for cb in self._callbacks:
            try:
                cb.on_validation_fail(self._phase_name, errors, 0)
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "[ValidationMiddleware] callback validation_fail error: %s",
                    exc,
                )

    def _emit_validation_pass(self) -> None:
        try:
            from ..callbacks.events import ValidationPassEvent

            event = ValidationPassEvent(phase_name=self._phase_name, retry_count=0)
            for cb in self._callbacks:
                try:
                    cb.on_event(event)
                except Exception as exc:  # noqa: BLE001
                    logger.warning(
                        "[ValidationMiddleware] callback validation_pass error: %s",
                        exc,
                    )
        except Exception as exc:  # noqa: BLE001
            logger.warning("[ValidationMiddleware] validation_pass emit failed: %s", exc)

    def _store_validated_result(
        self,
        parsed_list: list[dict[str, Any]],
        *,
        schema_validation: str = "passed",
        extra: dict[str, Any] | None = None,
    ) -> None:
        result = {
            "business_data_parsed": parsed_list,
            "schema_validation": schema_validation,
        }
        if extra:
            result.update(extra)
        self.ctx["_finish_task_result"] = result
        if self.hoist_to:
            self.ctx[str(self.hoist_to)] = parsed_list
            logger.info(
                "[ValidationMiddleware] hoisted %d items to ctx[%s]",
                len(parsed_list),
                self.hoist_to,
            )

    def _reject(self, request: ToolCallRequest, errors: list[str] | str) -> Command:
        error_lines = [errors] if isinstance(errors, str) else errors
        content = self._REJECTION_PREFIX + "\n" + "\n".join(error_lines)
        self._emit_validation_fail(error_lines)
        logger.info(
            "[ValidationMiddleware] Rejected finish_task in phase=%s with %d error(s)",
            self._phase_name,
            len(error_lines),
        )
        return Command(
            update={
                "messages": [
                    ToolMessage(
                        content=content,
                        name="finish_task",
                        tool_call_id=request.tool_call["id"],
                        status="error",
                    )
                ]
            },
            # ``finish_task`` is return_direct=True. Without an explicit jump,
            # LangChain routes the tools node to END. Jumping to model keeps the
            # correction inside the same agent loop.
            goto="model",
        )

    def _validate_finish_task(self, request: ToolCallRequest) -> Command | None:
        args = self._args_dict(request)
        if isinstance(args, Command):
            return args
        business_data_md = str(args.get("business_data_md") or "").strip()
        if isinstance(self.output_schema, DynamicSchemaDef):
            return self._validate_dynamic_finish_task(
                request,
                business_data_md=business_data_md,
                schema=self.output_schema,
            )

        try:
            schema = self._resolve_output_schema()
        except Exception as exc:  # noqa: BLE001
            return self._reject(
                request,
                f"Markdown 解析失败：无法加载 output_schema {self.output_schema_path!r}: "
                f"{type(exc).__name__}: {exc}",
            )

        if schema is not None and not business_data_md:
            return self._reject(
                request,
                "你声明了 output_schema 但 business_data_md 是空。必须填入完整 markdown 结果。",
            )

        if schema is None:
            business_errors = self._run_business_validator(self.ctx)
            if business_errors:
                return self._reject(request, business_errors)
            self._emit_validation_pass()
            return None

        from ..tools.md_to_json import diagnose, parse_md

        try:
            parsed_blocks = parse_md(business_data_md, schema)
        except Exception as exc:  # noqa: BLE001
            return self._reject(request, f"Markdown 解析失败：{type(exc).__name__}: {exc}")

        if not parsed_blocks:
            return self._reject(
                request,
                "未能在 business_data_md 中检测到任何 ## 块。必须按 output_schema 范例输出至少 1 个 ## 块。",
            )

        report = diagnose(parsed_blocks, schema)
        pydantic_errors: list[str] = []
        for item_error in report.errors:
            fields = "; ".join(
                f"{field.field}: {field.error}" for field in item_error.fields
            )
            item_id = item_error.item_id or f"index={item_error.index}"
            pydantic_errors.append(f"[Pydantic] {item_id}: {fields}")

        raw_items = [block.data for block in parsed_blocks]
        business_errors = self._run_business_validator(raw_items)
        all_errors = pydantic_errors + business_errors
        if all_errors:
            return self._reject(
                request,
                ["校验错误如下（请一次性全部修复）：", *all_errors],
            )

        self._store_validated_result(
            [item.model_dump() for item in report.valid_items],
        )
        self._emit_validation_pass()
        return None

    def _validate_dynamic_finish_task(
        self,
        request: ToolCallRequest,
        *,
        business_data_md: str,
        schema: DynamicSchemaDef,
    ) -> Command | None:
        if not business_data_md:
            return self._reject(
                request,
                "你声明了 output_example 但 business_data_md 是空。必须填入完整 markdown 结果。",
            )

        parsed_blocks = parse_md_simple(business_data_md)
        if not parsed_blocks:
            return self._reject(
                request,
                "未能在 business_data_md 中检测到任何 ## 块。必须按 output_example 范例输出至少 1 个 ## 块。",
            )

        schema_errors: list[str] = []
        coerced_items: list[dict[str, Any]] = []
        for block in parsed_blocks:
            coerced, errors = coerce_item_against_dynamic_schema(block.data, schema)
            if errors:
                schema_errors.extend(
                    f"[DynamicSchema] {block.meta.id}: {error}" for error in errors
                )
            coerced_items.append(coerced)

        business_errors = self._run_business_validator(coerced_items)
        all_errors = schema_errors + business_errors
        if all_errors:
            return self._reject(
                request,
                ["校验错误如下（请一次性全部修复）：", *all_errors],
            )

        self._store_validated_result(
            coerced_items,
            extra={"schema_type": "dynamic", "schema_name": schema.name},
        )
        logger.info(
            "[ValidationMiddleware] dynamic schema validation passed phase=%s schema=%s items=%d",
            self._phase_name,
            schema.name,
            len(coerced_items),
        )
        self._emit_validation_pass()
        return None

    @override
    def wrap_tool_call(
        self,
        request: ToolCallRequest,
        handler: Callable[[ToolCallRequest], ToolMessage | Command],
    ) -> ToolMessage | Command:
        if request.tool_call.get("name") != "finish_task":
            return handler(request)
        rejection = self._validate_finish_task(request)
        if rejection is not None:
            return rejection
        return handler(request)

    @override
    async def awrap_tool_call(
        self,
        request: ToolCallRequest,
        handler: Callable[[ToolCallRequest], Awaitable[ToolMessage | Command]],
    ) -> ToolMessage | Command:
        if request.tool_call.get("name") != "finish_task":
            return await handler(request)
        rejection = self._validate_finish_task(request)
        if rejection is not None:
            return rejection
        return await handler(request)


class UnattendedClarificationMiddleware(AgentMiddleware[AgentState]):
    """Auto-answer clarification requests when human input is unavailable."""

    _TOOL_NAME = "ask_clarification"

    def __init__(self, *, unattended: bool, phase_name: str = "unknown") -> None:
        super().__init__()
        self.unattended = bool(unattended)
        self._phase_name = phase_name

    def _json_parse_retry(
        self,
        request: ToolCallRequest,
        exc: TypeError | ValueError,
    ) -> Command:
        error_msg = f"JSON parse failed: {exc}. Please retry with valid JSON."
        tool_name = str(request.tool_call.get("name") or self._TOOL_NAME)
        logger.warning(
            "phase=%s action=middleware_parse fallback "
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
                        content=error_msg,
                        name=tool_name,
                        tool_call_id=request.tool_call["id"],
                    )
                ]
            },
        )

    def _args_dict(self, request: ToolCallRequest) -> dict[str, Any] | Command:
        args = request.tool_call.get("args", {})
        if isinstance(args, dict):
            return args
        if isinstance(args, str):
            try:
                parsed = json.loads(args)
            except (TypeError, ValueError) as exc:
                return self._json_parse_retry(request, exc)
            return parsed if isinstance(parsed, dict) else {}
        return {}

    def _auto_response(self, request: ToolCallRequest) -> Command:
        args = self._args_dict(request)
        if isinstance(args, Command):
            return args
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
        logger.info(
            "[UnattendedClarification] auto-answered ask_clarification"
        )
        return Command(
            update={
                "messages": [
                    ToolMessage(
                        content=content,
                        name=self._TOOL_NAME,
                        tool_call_id=request.tool_call["id"],
                    )
                ]
            },
            goto="model",
        )

    @override
    def wrap_tool_call(
        self,
        request: ToolCallRequest,
        handler: Callable[[ToolCallRequest], ToolMessage | Command],
    ) -> ToolMessage | Command:
        if (
            not self.unattended
            or request.tool_call.get("name") != self._TOOL_NAME
        ):
            return handler(request)
        return self._auto_response(request)

    @override
    async def awrap_tool_call(
        self,
        request: ToolCallRequest,
        handler: Callable[[ToolCallRequest], Awaitable[ToolMessage | Command]],
    ) -> ToolMessage | Command:
        if (
            not self.unattended
            or request.tool_call.get("name") != self._TOOL_NAME
        ):
            return await handler(request)
        return self._auto_response(request)


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
    loop_detection: bool = True,
    loop_detection_warn_threshold: int = 3,
    loop_detection_hard_limit: int = 5,
    clarification: bool = True,
    unattended: bool | None = None,
    summarization: bool = False,
    summarization_model: Any = None,
    summarization_trigger_fraction: float = 0.8,
    summarization_keep_messages: int = 20,
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

    if loop_detection:
        try:
            from ..deerflow.agents.middlewares.loop_detection_middleware import (
                LoopDetectionMiddleware,
            )

            middlewares.append(
                LoopDetectionMiddleware(
                    warn_threshold=loop_detection_warn_threshold,
                    hard_limit=loop_detection_hard_limit,
                )
            )
            logger.info(
                "middleware: enabled LoopDetection (warn=%d hard=%d)",
                loop_detection_warn_threshold,
                loop_detection_hard_limit,
            )
        except ImportError as exc:
            logger.warning(
                "middleware: failed to import LoopDetectionMiddleware: %s",
                exc,
            )

    if clarification:
        effective_unattended = bool(
            unattended
            if unattended is not None
            else (
                context_ref.get("_unattended")
                if isinstance(context_ref, dict)
                else False
            )
        )
        if effective_unattended:
            middlewares.append(
                UnattendedClarificationMiddleware(
                    unattended=True,
                    phase_name=phase_name,
                )
            )
            logger.info(
                "middleware: enabled UnattendedClarification "
                "(auto-answer ask_clarification)"
            )
        else:
            try:
                from ..deerflow.agents.middlewares.clarification_middleware import (
                    ClarificationMiddleware,
                )

                middlewares.append(ClarificationMiddleware())
                logger.info("middleware: enabled Clarification (Human-in-the-Loop)")
            except ImportError as exc:
                logger.warning(
                    "middleware: failed to import ClarificationMiddleware: %s",
                    exc,
                )
    if summarization and summarization_model is not None:
        try:
            from langchain.agents.middleware import SummarizationMiddleware

            middlewares.append(
                SummarizationMiddleware(
                    model=_ensure_summarization_profile(summarization_model),
                    trigger=("fraction", summarization_trigger_fraction),
                    keep=("messages", summarization_keep_messages),
                )
            )
            logger.info(
                "middleware: enabled Summarization "
                "(trigger=fraction:%.1f keep=%d msgs)",
                summarization_trigger_fraction,
                summarization_keep_messages,
            )
        except ImportError as exc:
            logger.warning(
                "middleware: failed to import SummarizationMiddleware: %s",
                exc,
            )
    elif summarization and summarization_model is None:
        logger.warning(
            "middleware: summarization=True but summarization_model is None; skipping"
        )

    return middlewares
