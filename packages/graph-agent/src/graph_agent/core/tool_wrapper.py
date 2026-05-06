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
    return (
        f"[系统] 工具调用次数已达上限({max_calls})，"
        "请基于已获得信息直接给出最终结果。"
    )


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
    try:
        sig = inspect.signature(fn, eval_str=True)
    except (NameError, TypeError):
        logger.debug("[ToolWrap] eval_str=True failed for '%s', falling back", fn_name)
        sig = inspect.signature(fn, eval_str=False)
    params = list(sig.parameters.values())

    context_idx = next((i for i, p in enumerate(params) if _is_context_param(p.name)), -1)
    has_context_param = context_idx >= 0

    if has_context_param:
        ctx_param_name = params[context_idx].name
        remaining_params = [
            p for i, p in enumerate(params)
            if i != context_idx and p.kind not in (
                inspect.Parameter.VAR_POSITIONAL, inspect.Parameter.VAR_KEYWORD,
            )
        ]
        fields: dict[str, Any] = {}
        for param in remaining_params:
            annotation = param.annotation if param.annotation != inspect.Parameter.empty else str
            default = param.default if param.default != inspect.Parameter.empty else ...
            fields[param.name] = (annotation, default)

        if fields:
            args_schema = _make_robust_schema(f"{fn_name}_Schema", fields)

            def _invoke(**kwargs: Any) -> str:
                if tool_limiter is not None and tool_limiter.should_block_tool_call():
                    return _blocked_tool_message(tool_limiter)
                bound_kwargs: dict[str, Any] = {}
                for param in params:
                    if _is_context_param(param.name):
                        bound_kwargs[param.name] = context
                    elif param.name in kwargs:
                        bound_kwargs[param.name] = kwargs[param.name]
                    # else: omitted optional param, use function default
                try:
                    return str(fn(**bound_kwargs))
                except Exception as exc:
                    logger.warning("[ToolWrap] Tool '%s' raised %s: %s", fn_name, type(exc).__name__, exc)
                    return f"[Tool Error] {type(exc).__name__}: {exc}"

            return StructuredTool.from_function(
                func=_invoke,
                name=fn_name,
                description=fn_doc,
                args_schema=args_schema,
                return_direct=return_direct,
            )

        def _invoke_no_args() -> str:
            if tool_limiter is not None and tool_limiter.should_block_tool_call():
                return _blocked_tool_message(tool_limiter)
            try:
                return str(fn(**{ctx_param_name: context}))
            except Exception as exc:
                logger.warning("[ToolWrap] Tool '%s' raised %s: %s", fn_name, type(exc).__name__, exc)
                return f"[Tool Error] {type(exc).__name__}: {exc}"

        return StructuredTool.from_function(
            func=_invoke_no_args,
            name=fn_name,
            description=fn_doc,
            return_direct=return_direct,
        )

    fields = {}
    for param in params:
        if param.kind in (inspect.Parameter.VAR_POSITIONAL, inspect.Parameter.VAR_KEYWORD):
            continue
        annotation = param.annotation if param.annotation != inspect.Parameter.empty else str
        default = param.default if param.default != inspect.Parameter.empty else ...
        fields[param.name] = (annotation, default)

    if fields:
        args_schema = _make_robust_schema(f"{fn_name}_Schema", fields)

        def _invoke_plain(**kwargs: Any) -> str:
            if tool_limiter is not None and tool_limiter.should_block_tool_call():
                return _blocked_tool_message(tool_limiter)
            try:
                return str(fn(**kwargs))
            except Exception as exc:
                logger.warning("[ToolWrap] Tool '%s' raised %s: %s", fn_name, type(exc).__name__, exc)
                return f"[Tool Error] {type(exc).__name__}: {exc}"

        return StructuredTool.from_function(
            func=_invoke_plain,
            name=fn_name,
            description=fn_doc,
            args_schema=args_schema,
            return_direct=return_direct,
        )

    def _invoke_plain_no_args() -> str:
        if tool_limiter is not None and tool_limiter.should_block_tool_call():
            return _blocked_tool_message(tool_limiter)
        try:
            return str(fn())
        except Exception as exc:
            logger.warning("[ToolWrap] Tool '%s' raised %s: %s", fn_name, type(exc).__name__, exc)
            return f"[Tool Error] {type(exc).__name__}: {exc}"

    return StructuredTool.from_function(
        func=_invoke_plain_no_args,
        name=fn_name,
        description=fn_doc,
        return_direct=return_direct,
    )


__all__ = ["_wrap_tool_for_langchain"]
