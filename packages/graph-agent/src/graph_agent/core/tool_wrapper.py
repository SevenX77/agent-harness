"""Plain Python function -> LangChain tool adapter."""

from __future__ import annotations

import inspect
import json
import logging
from typing import Annotated, Any, Protocol

from langchain.tools import BaseTool
from langchain_core.tools import StructuredTool
from pydantic import BaseModel, BeforeValidator, create_model, model_validator

logger = logging.getLogger(__name__)

_CONTEXT_PARAM_NAMES = {"context", "ctx"}


class _ToolLimiter(Protocol):
    _max_tool_calls: int

    def should_block_tool_call(self) -> bool:
        """Return True when the current phase should stop calling tools."""


def _is_context_param(param_name: str) -> bool:
    return param_name in _CONTEXT_PARAM_NAMES


def _json_coerce(value: Any) -> Any:
    """Auto-convert dict/list arguments into JSON strings before validation."""
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False)
    return value


_JsonStr = BeforeValidator(_json_coerce)


def _make_robust_schema(name: str, fields: dict[str, Any]) -> type[BaseModel]:
    """Create a schema that can unpack the raw_arguments JSON wrapper pattern."""
    normalized_fields: dict[str, Any] = {}
    for field_name, field_value in fields.items():
        annotation, default = field_value
        if annotation is str or annotation == "str":
            annotation = Annotated[str, _JsonStr]
        normalized_fields[field_name] = (annotation, default)

    expected = set(normalized_fields)
    base = create_model(name, **normalized_fields)

    class RobustSchema(base):  # type: ignore[misc,valid-type]  # create_model returns a runtime BaseModel subclass.
        @model_validator(mode="before")
        @classmethod
        def _unpack_raw_arguments(cls, data: Any) -> Any:
            if not isinstance(data, dict) or set(data) != {"raw_arguments"}:
                return data
            raw = data["raw_arguments"]
            if not isinstance(raw, str):
                return data
            try:
                parsed = json.loads(raw)
            except (ValueError, TypeError):
                return data
            if isinstance(parsed, dict) and expected.issubset(parsed):
                logger.debug("[ToolWrap] Unpacked raw_arguments -> %d fields", len(parsed))
                return parsed
            return data

        model_config = {"title": name}

    RobustSchema.__name__ = name
    RobustSchema.__qualname__ = name
    return RobustSchema


def _blocked_tool_message(tool_limiter: _ToolLimiter | None) -> str:
    max_calls = getattr(tool_limiter, "_max_tool_calls", 0)
    return f"[系统] 工具调用次数已达上限({max_calls})，请基于已获得信息直接给出最终结果。"


def _tool_context_with_callbacks(context: dict[str, Any]) -> dict[str, Any]:
    try:
        from graph_agent.core.callback_bridge import current_tool_callback_context
    except Exception:  # pragma: no cover - defensive against partial imports
        return context

    callback_context = current_tool_callback_context()
    if not isinstance(callback_context, dict):
        return context
    callbacks = callback_context.get("callbacks")
    if not isinstance(callbacks, list):
        return context
    enriched = dict(context)
    enriched.setdefault("_callbacks", callbacks)
    phase_name = callback_context.get("phase_name")
    if isinstance(phase_name, str) and phase_name:
        enriched.setdefault("_current_phase", phase_name)
    return enriched


def _wrap_tool_for_langchain(
    fn: Any,
    context: dict[str, Any],
    tool_limiter: _ToolLimiter | None = None,
    return_direct: bool = False,
) -> BaseTool:
    """Wrap a Python callable as a LangChain tool with context auto-injection."""
    if inspect.iscoroutinefunction(fn):
        raise TypeError(
            f"Tool '{getattr(fn, '__name__', 'unknown')}' is async; "
            "graph_agent does not support async tools yet"
        )
    fn_name = getattr(fn, "__name__", "unnamed_tool")
    fn_doc = (getattr(fn, "__doc__", None) or f"Tool: {fn_name}").strip()
    sig = _signature_for_tool(fn, fn_name)
    params = list(sig.parameters.values())
    context_idx = _context_param_index(params)

    if context_idx >= 0:
        return _wrap_context_tool(
            fn,
            fn_name,
            fn_doc,
            params,
            context_idx,
            context,
            tool_limiter,
            return_direct,
        )
    return _wrap_plain_tool(fn, fn_name, fn_doc, params, tool_limiter, return_direct)


def _signature_for_tool(fn: Any, fn_name: str) -> inspect.Signature:
    try:
        return inspect.signature(fn, eval_str=True)
    except (NameError, TypeError):
        logger.debug("[ToolWrap] eval_str=True failed for '%s', falling back", fn_name)
        return inspect.signature(fn, eval_str=False)


def _context_param_index(params: list[inspect.Parameter]) -> int:
    return next((i for i, p in enumerate(params) if _is_context_param(p.name)), -1)


def _wrap_context_tool(
    fn: Any,
    fn_name: str,
    fn_doc: str,
    params: list[inspect.Parameter],
    context_idx: int,
    context: dict[str, Any],
    tool_limiter: _ToolLimiter | None,
    return_direct: bool,
) -> BaseTool:
    ctx_param_name = params[context_idx].name
    fields = _schema_fields_for_params(_non_context_tool_params(params, context_idx))

    if fields:
        args_schema = _make_robust_schema(f"{fn_name}_Schema", fields)
        invoke = _make_context_invoke(fn, fn_name, params, context, tool_limiter)
        return _structured_tool(fn_name, fn_doc, invoke, return_direct, args_schema=args_schema)

    invoke_no_args = _make_context_no_args_invoke(
        fn, fn_name, ctx_param_name, context, tool_limiter
    )
    return _structured_tool(fn_name, fn_doc, invoke_no_args, return_direct)


def _wrap_plain_tool(
    fn: Any,
    fn_name: str,
    fn_doc: str,
    params: list[inspect.Parameter],
    tool_limiter: _ToolLimiter | None,
    return_direct: bool,
) -> BaseTool:
    fields = _schema_fields_for_params(_callable_tool_params(params))
    if fields:
        args_schema = _make_robust_schema(f"{fn_name}_Schema", fields)
        invoke_plain = _make_plain_invoke(fn, fn_name, tool_limiter)
        return _structured_tool(fn_name, fn_doc, invoke_plain, return_direct, args_schema=args_schema)

    invoke_plain_no_args = _make_plain_no_args_invoke(fn, fn_name, tool_limiter)
    return _structured_tool(fn_name, fn_doc, invoke_plain_no_args, return_direct)


def _non_context_tool_params(
    params: list[inspect.Parameter],
    context_idx: int,
) -> list[inspect.Parameter]:
    return [p for i, p in enumerate(params) if i != context_idx and _is_schema_param(p)]


def _callable_tool_params(params: list[inspect.Parameter]) -> list[inspect.Parameter]:
    return [param for param in params if _is_schema_param(param)]


def _is_schema_param(param: inspect.Parameter) -> bool:
    return param.kind not in (
        inspect.Parameter.VAR_POSITIONAL,
        inspect.Parameter.VAR_KEYWORD,
    )


def _schema_fields_for_params(params: list[inspect.Parameter]) -> dict[str, Any]:
    fields: dict[str, Any] = {}
    for param in params:
        annotation = param.annotation if param.annotation != inspect.Parameter.empty else str
        default = param.default if param.default != inspect.Parameter.empty else ...
        fields[param.name] = (annotation, default)
    return fields


def _make_context_invoke(
    fn: Any,
    fn_name: str,
    params: list[inspect.Parameter],
    context: dict[str, Any],
    tool_limiter: _ToolLimiter | None,
) -> Any:
    def _invoke(**kwargs: Any) -> str:
        if _is_blocked(tool_limiter):
            return _blocked_tool_message(tool_limiter)
        bound_kwargs = _bind_context_kwargs(params, kwargs, context)
        return _call_tool(fn, fn_name, **bound_kwargs)

    return _invoke


def _make_context_no_args_invoke(
    fn: Any,
    fn_name: str,
    ctx_param_name: str,
    context: dict[str, Any],
    tool_limiter: _ToolLimiter | None,
) -> Any:
    def _invoke_no_args() -> str:
        if _is_blocked(tool_limiter):
            return _blocked_tool_message(tool_limiter)
        return _call_tool(fn, fn_name, **{ctx_param_name: _tool_context_with_callbacks(context)})

    return _invoke_no_args


def _make_plain_invoke(fn: Any, fn_name: str, tool_limiter: _ToolLimiter | None) -> Any:
    def _invoke_plain(**kwargs: Any) -> str:
        if _is_blocked(tool_limiter):
            return _blocked_tool_message(tool_limiter)
        return _call_tool(fn, fn_name, **kwargs)

    return _invoke_plain


def _make_plain_no_args_invoke(fn: Any, fn_name: str, tool_limiter: _ToolLimiter | None) -> Any:
    def _invoke_plain_no_args() -> str:
        if _is_blocked(tool_limiter):
            return _blocked_tool_message(tool_limiter)
        return _call_tool(fn, fn_name)

    return _invoke_plain_no_args


def _is_blocked(tool_limiter: _ToolLimiter | None) -> bool:
    return tool_limiter is not None and tool_limiter.should_block_tool_call()


def _bind_context_kwargs(
    params: list[inspect.Parameter],
    kwargs: dict[str, Any],
    context: dict[str, Any],
) -> dict[str, Any]:
    bound_kwargs: dict[str, Any] = {}
    call_context = _tool_context_with_callbacks(context)
    for param in params:
        if _is_context_param(param.name):
            bound_kwargs[param.name] = call_context
        elif param.name in kwargs:
            bound_kwargs[param.name] = kwargs[param.name]
    return bound_kwargs


def _call_tool(fn: Any, fn_name: str, **kwargs: Any) -> str:
    try:
        return str(fn(**kwargs))
    except Exception as exc:
        logger.warning("[ToolWrap] Tool '%s' raised %s: %s", fn_name, type(exc).__name__, exc)
        return f"[Tool Error] {type(exc).__name__}: {exc}"


def _structured_tool(
    fn_name: str,
    fn_doc: str,
    func: Any,
    return_direct: bool,
    *,
    args_schema: type[BaseModel] | None = None,
) -> BaseTool:
    kwargs: dict[str, Any] = {
        "func": func,
        "name": fn_name,
        "description": fn_doc,
        "return_direct": return_direct,
    }
    if args_schema is not None:
        kwargs["args_schema"] = args_schema
    return StructuredTool.from_function(**kwargs)


__all__ = ["_wrap_tool_for_langchain"]
