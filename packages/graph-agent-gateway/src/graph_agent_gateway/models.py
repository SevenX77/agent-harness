"""Provider model wrappers for graph-agent-gateway."""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping, Sequence
from typing import Any, cast

from langchain_core.callbacks.manager import CallbackManagerForLLMRun
from langchain_core.language_models.base import LanguageModelInput
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langchain_core.runnables import Runnable
from langchain_core.tools import BaseTool
from langchain_core.utils.function_calling import convert_to_openai_tool
from pydantic import ConfigDict, Field

ToolSpec = dict[str, Any] | type | Callable[..., object] | BaseTool
OrdinaryChatDispatcher = Callable[..., Mapping[str, object] | AIMessage]
MessageContent = str | list[str | dict[Any, Any]]


class GenericRouteChatModel(BaseChatModel):
    """LangChain wrapper around the gateway ordinary-chat dispatcher."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    route: Any
    credential_provider: Any = None
    ordinary_chat_dispatcher: OrdinaryChatDispatcher | None = None
    max_tokens: int = 4096
    temperature: float = 0.7
    runtime_policy: Any = None
    reasoning: bool = False
    thinking_budget_tokens: int | None = None
    top_p: float | None = None
    stop_sequences: list[str] | None = None
    seed: int | None = None
    parallel_tool_calls: bool | None = None
    structured_output: Mapping[str, object] | None = None
    reasoning_effort: str | None = None
    call_method_id: str | None = None
    request_mapper_id: str | None = None
    bound_tools: tuple[dict[str, object], ...] = Field(default_factory=tuple)
    tool_choice: str | None = None
    tool_kwargs: dict[str, object] = Field(default_factory=dict)

    @property
    def _llm_type(self) -> str:
        return "graph_agent_gateway_generic_route"

    def bind_tools(
        self,
        tools: Sequence[ToolSpec],
        *,
        tool_choice: str | None = None,
        **kwargs: Any,
    ) -> Runnable[LanguageModelInput, AIMessage]:
        bound = self.model_copy(
            update={
                "bound_tools": tuple(_normalise_tool(tool) for tool in tools),
                "tool_choice": tool_choice,
                "tool_kwargs": dict(kwargs),
            }
        )
        return cast(Runnable[LanguageModelInput, AIMessage], bound)

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: CallbackManagerForLLMRun | None = None,
        **kwargs: Any,
    ) -> ChatResult:
        del run_manager, kwargs
        dispatcher = self.ordinary_chat_dispatcher or _default_ordinary_chat_dispatcher()
        response = dispatcher(
            self.route,
            _messages_to_ordinary_chat_dicts(messages),
            max_tokens=self.max_tokens,
            temperature=self.temperature,
            runtime_policy=self.runtime_policy or _default_runtime_policy(),
            reasoning=self.reasoning,
            thinking_budget_tokens=self.thinking_budget_tokens,
            tools=list(self.bound_tools) or None,
            tool_choice=self.tool_choice,
            top_p=self.top_p,
            stop_sequences=stop or self.stop_sequences,
            seed=self.seed,
            parallel_tool_calls=self.parallel_tool_calls,
            structured_output=self.structured_output,
            reasoning_effort=self.reasoning_effort,
            call_method_id=self.call_method_id,
            request_mapper_id=self.request_mapper_id,
            credential_provider=self.credential_provider,
        )
        return ChatResult(
            generations=[ChatGeneration(message=_ai_message_from_response(response))]
        )


def _default_ordinary_chat_dispatcher() -> OrdinaryChatDispatcher:
    from graph_agent_gateway.ordinary_chat import dispatch_ordinary_chat

    return dispatch_ordinary_chat


def _default_runtime_policy() -> object:
    from graph_agent_gateway.registry.schema import RuntimePolicy

    return RuntimePolicy()


def _messages_to_ordinary_chat_dicts(messages: Sequence[BaseMessage]) -> list[dict[str, object]]:
    result: list[dict[str, object]] = []
    for message in messages:
        payload: dict[str, object] = {
            "role": _message_role(message),
            "content": _message_content(message.content),
        }
        name = getattr(message, "name", None)
        if name:
            payload["name"] = name
        if isinstance(message, ToolMessage):
            payload["tool_call_id"] = message.tool_call_id
        if isinstance(message, AIMessage):
            raw_tool_calls = message.additional_kwargs.get("tool_calls")
            if isinstance(raw_tool_calls, list) and raw_tool_calls:
                payload["tool_calls"] = _normalise_openai_tool_calls(raw_tool_calls)
            elif message.tool_calls:
                payload["tool_calls"] = [
                    _openai_tool_call_from_langchain(call) for call in message.tool_calls
                ]
        reasoning = message.additional_kwargs.get("reasoning_content")
        if reasoning:
            payload["reasoning_content"] = reasoning
        result.append(payload)
    return result


def _message_role(message: BaseMessage) -> str:
    if isinstance(message, SystemMessage):
        return "system"
    if isinstance(message, HumanMessage):
        return "user"
    if isinstance(message, AIMessage):
        return "assistant"
    if isinstance(message, ToolMessage):
        return "tool"
    return "user"


def _message_content(content: object) -> MessageContent:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return cast(list[str | dict[Any, Any]], content)
    return "" if content is None else str(content)


def _openai_tool_call_from_langchain(call: Mapping[str, Any]) -> dict[str, object]:
    call_id = call.get("id")
    name = str(call.get("name") or "")
    args = call.get("args")
    return {
        "id": str(call_id) if call_id is not None else "",
        "type": "function",
        "function": {
            "name": name,
            "arguments": _json_arguments(args),
        },
    }


def _normalise_openai_tool_calls(tool_calls: Sequence[object]) -> list[dict[str, object]]:
    result: list[dict[str, object]] = []
    for tool_call in tool_calls:
        if not isinstance(tool_call, Mapping):
            continue
        normalized = dict(tool_call)
        function = normalized.get("function")
        if isinstance(function, Mapping):
            normalized["function"] = {
                **dict(function),
                "arguments": _json_arguments(function.get("arguments")),
            }
        result.append(normalized)
    return result


def _json_arguments(value: object) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, Mapping):
        return json.dumps(dict(value), separators=(",", ":"), default=str)
    return "{}"


def _ai_message_from_response(response: Mapping[str, object] | AIMessage) -> AIMessage:
    if isinstance(response, AIMessage):
        return response
    content = _message_content(response.get("content"))
    additional_kwargs = _additional_kwargs_from_response(response)
    raw_tool_calls = response.get("tool_calls")
    tool_calls = _langchain_tool_calls(raw_tool_calls)
    usage_metadata = _usage_metadata(response.get("usage"))
    response_metadata = {
        "finish_reason": response.get("finish_reason"),
    }
    return AIMessage(
        content=content,
        additional_kwargs=additional_kwargs,
        response_metadata=response_metadata,
        tool_calls=tool_calls,
        usage_metadata=usage_metadata,
    )


def _additional_kwargs_from_response(response: Mapping[str, object]) -> dict[str, object]:
    extra = response.get("additional_kwargs")
    result = dict(extra) if isinstance(extra, Mapping) else {}
    raw_tool_calls = response.get("tool_calls")
    if isinstance(raw_tool_calls, list) and raw_tool_calls:
        result["tool_calls"] = _normalise_openai_tool_calls(raw_tool_calls)
    reasoning = response.get("reasoning_content")
    if isinstance(reasoning, str) and reasoning:
        result["reasoning_content"] = reasoning
    return result


def _langchain_tool_calls(raw_tool_calls: object) -> list[dict[str, object]]:
    if not isinstance(raw_tool_calls, list):
        return []
    result: list[dict[str, object]] = []
    for raw_call in raw_tool_calls:
        if not isinstance(raw_call, Mapping):
            continue
        function = raw_call.get("function")
        if not isinstance(function, Mapping):
            continue
        name = function.get("name")
        if not isinstance(name, str) or not name:
            continue
        result.append(
            {
                "name": name,
                "args": _parse_arguments(function.get("arguments")),
                "id": str(raw_call.get("id") or ""),
            }
        )
    return result


def _parse_arguments(value: object) -> dict[str, object]:
    if isinstance(value, Mapping):
        return dict(value)
    if not isinstance(value, str) or not value:
        return {}
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        return {}
    return dict(parsed) if isinstance(parsed, Mapping) else {}


def _usage_metadata(usage: object) -> dict[str, int]:
    if not isinstance(usage, Mapping):
        return {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0}
    input_tokens = _int_value(usage.get("input_tokens") or usage.get("prompt_tokens"))
    output_tokens = _int_value(usage.get("output_tokens") or usage.get("completion_tokens"))
    total_tokens = _int_value(usage.get("total_tokens"))
    if total_tokens == 0:
        total_tokens = input_tokens + output_tokens
    return {
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "total_tokens": total_tokens,
    }


def _int_value(value: object) -> int:
    if isinstance(value, int | float) and value >= 0:
        return int(value)
    if isinstance(value, str) and value.isdigit():
        return int(value)
    return 0


def _normalise_tool(tool: ToolSpec) -> dict[str, object]:
    if isinstance(tool, dict) and tool.get("type") == "function":
        return {str(key): value for key, value in tool.items()}
    normalized = cast(dict[str, object], convert_to_openai_tool(tool))
    function = normalized.get("function")
    if isinstance(function, dict):
        function.setdefault("description", "")
        function.setdefault("parameters", {"type": "object", "properties": {}})
    return normalized


__all__ = ["GenericRouteChatModel"]
