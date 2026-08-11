"""Ordinary-chat provider dispatch core for generic gateway routes."""

from __future__ import annotations

import json
import logging
import time
from collections.abc import Callable, Iterable, Mapping, Sequence
from typing import Any, Literal, cast

import httpx
from anthropic import Anthropic
from anthropic.types import MessageParam
from openai import OpenAI
from openai.types.chat import ChatCompletionMessageParam

from graph_agent_gateway.registry import (
    CredentialProviderProtocol,
    ResolvedRoute,
    RuntimePolicy,
    provider_temperature_from_authored,
)

logger = logging.getLogger(__name__)

MessageDict = dict[str, object]
CallResult = dict[str, object]
ToolSchema = dict[str, object]

_RETRYABLE_WAVESPEED_STATUS = {502, 503, 504}
_TRUNCATED_FINISH_REASONS = {
    "length",
    "max_tokens",
    "max_output_tokens",
    "finish_reason_max_tokens",
    "stop_reason_max_tokens",
}


def dispatch_ordinary_chat(
    route: ResolvedRoute,
    messages: list[MessageDict],
    *,
    max_tokens: int,
    temperature: float | None,
    runtime_policy: RuntimePolicy,
    reasoning: bool = False,
    thinking_budget_tokens: int | None = None,
    tools: list[ToolSchema] | None = None,
    tool_choice: str | None = None,
    top_p: float | None = None,
    stop_sequences: list[str] | None = None,
    seed: int | None = None,
    parallel_tool_calls: bool | None = None,
    structured_output: Mapping[str, object] | None = None,
    reasoning_effort: str | None = None,
    call_method_id: str | None = None,
    request_mapper_id: str | None = None,
    credential_provider: CredentialProviderProtocol | None = None,
) -> CallResult:
    """Dispatch one generic ordinary-chat route outside LLMClientManager."""
    provider_temperature = provider_temperature_from_authored(temperature, route)

    def invoke(token_budget: int) -> CallResult:
        return _dispatch_provider_call(
            route,
            messages,
            token_budget,
            provider_temperature,
            runtime_policy=runtime_policy,
            reasoning=reasoning,
            thinking_budget_tokens=thinking_budget_tokens,
            tools=tools,
            tool_choice=tool_choice,
            top_p=top_p,
            stop_sequences=stop_sequences,
            seed=seed,
            parallel_tool_calls=parallel_tool_calls,
            structured_output=structured_output,
            reasoning_effort=reasoning_effort,
            call_method_id=call_method_id,
            request_mapper_id=request_mapper_id,
            credential_provider=credential_provider,
        )

    return _call_with_token_escalation(
        route,
        max_tokens,
        invoke,
        runtime_policy=runtime_policy,
    )


def _dispatch_provider_call(
    route: ResolvedRoute,
    messages: list[MessageDict],
    max_tokens: int,
    temperature: float | None,
    *,
    runtime_policy: RuntimePolicy,
    reasoning: bool = False,
    thinking_budget_tokens: int | None = None,
    tools: list[ToolSchema] | None = None,
    tool_choice: str | None = None,
    top_p: float | None = None,
    stop_sequences: list[str] | None = None,
    seed: int | None = None,
    parallel_tool_calls: bool | None = None,
    structured_output: Mapping[str, object] | None = None,
    reasoning_effort: str | None = None,
    call_method_id: str | None = None,
    request_mapper_id: str | None = None,
    credential_provider: CredentialProviderProtocol | None = None,
) -> CallResult:
    """Route an ordinary-chat call by configured endpoint protocol."""
    from graph_agent_gateway.client_manager import LLMClientManager

    if route.protocol == "openai_compatible":
        client_kwargs: dict[str, Any] = {"runtime_policy": runtime_policy}
        if credential_provider is not None:
            client_kwargs["credential_provider"] = credential_provider
        client = LLMClientManager._get_openai_client(route, **client_kwargs)
        if call_method_id == "openai_responses":
            return _call_openai_responses(
                client,
                route.provider_model_id,
                messages,
                max_tokens,
                temperature,
                top_p=top_p,
                reasoning_effort=reasoning_effort,
            )
        return _call_openai_compatible(
            client,
            route.provider_model_id,
            messages,
            max_tokens,
            temperature,
            tools=tools,
            tool_choice=tool_choice,
            top_p=top_p,
            stop_sequences=stop_sequences,
            seed=seed,
            parallel_tool_calls=parallel_tool_calls,
            structured_output=structured_output,
            reasoning_effort=reasoning_effort,
        )

    if route.protocol == "anthropic_compatible":
        client_kwargs = {"runtime_policy": runtime_policy}
        if credential_provider is not None:
            client_kwargs["credential_provider"] = credential_provider
        anthropic_client = LLMClientManager._get_anthropic_client(route, **client_kwargs)
        return _call_anthropic_compatible(
            anthropic_client,
            route.provider_model_id,
            messages,
            max_tokens,
            temperature,
            reasoning=reasoning,
            thinking_budget_tokens=thinking_budget_tokens,
            tools=tools,
            tool_choice=tool_choice,
            top_p=top_p,
            stop_sequences=stop_sequences,
            request_mapper_id=request_mapper_id,
        )

    if route.protocol == "google_genai":
        client_kwargs = {"runtime_policy": runtime_policy}
        if credential_provider is not None:
            client_kwargs["credential_provider"] = credential_provider
        google_client = LLMClientManager._get_google_client(route, **client_kwargs)
        return _call_google_genai(
            google_client,
            route.provider_model_id,
            messages,
            max_tokens,
            temperature,
            top_p=top_p,
            stop_sequences=stop_sequences,
            seed=seed,
            structured_output=structured_output,
            reasoning=reasoning,
            thinking_budget_tokens=thinking_budget_tokens,
            reasoning_effort=reasoning_effort,
        )

    if route.protocol == "ark_runtime":
        client_kwargs = {"runtime_policy": runtime_policy}
        if credential_provider is not None:
            client_kwargs["credential_provider"] = credential_provider
        ark_client = LLMClientManager._get_ark_client(route, **client_kwargs)
        return _call_ark_runtime(
            ark_client,
            route.provider_model_id,
            messages,
            max_tokens,
            temperature,
            top_p=top_p,
            stop_sequences=stop_sequences,
            seed=seed,
            parallel_tool_calls=parallel_tool_calls,
            structured_output=structured_output,
            reasoning_effort=reasoning_effort,
        )

    if route.protocol == "wavespeed_any_llm":
        return _call_wavespeed_any_llm(
            route,
            messages,
            route.provider_model_id,
            max_tokens,
            temperature,
            reasoning=reasoning,
            credential_provider=credential_provider,
            tools=tools,
            tool_choice=tool_choice,
        )

    raise ValueError(f"Unknown endpoint protocol: {route.protocol}")


def _call_openai_compatible(
    client: OpenAI,
    model: str,
    messages: list[MessageDict],
    max_tokens: int,
    temperature: float | None,
    *,
    tools: list[ToolSchema] | None = None,
    tool_choice: str | None = None,
    top_p: float | None = None,
    stop_sequences: list[str] | None = None,
    seed: int | None = None,
    parallel_tool_calls: bool | None = None,
    structured_output: Mapping[str, object] | None = None,
    reasoning_effort: str | None = None,
) -> CallResult:
    """Call an OpenAI-compatible chat completion endpoint."""
    kwargs: dict[str, object] = {
        "model": model,
        "messages": cast(Iterable[ChatCompletionMessageParam], messages),
        "max_tokens": max_tokens,
    }
    if temperature is not None:
        kwargs["temperature"] = temperature
    if top_p is not None:
        kwargs["top_p"] = top_p
    if stop_sequences:
        kwargs["stop"] = stop_sequences
    if seed is not None:
        kwargs["seed"] = seed
    if parallel_tool_calls is not None:
        kwargs["parallel_tool_calls"] = parallel_tool_calls
    if reasoning_effort:
        kwargs["reasoning_effort"] = reasoning_effort
    response_format = _openai_response_format(structured_output)
    if response_format is not None:
        kwargs["response_format"] = response_format
    if tools:
        kwargs["tools"] = tools
    if tool_choice:
        kwargs["tool_choice"] = tool_choice
    response = cast(Callable[..., object], client.chat.completions.create)(**kwargs)
    usage_obj = _field(response, "usage")
    choice = _first_sequence_item(_field(response, "choices"))
    message = _field(choice, "message")
    content = _string_field(message, "content")
    prompt_tokens = _int_field(usage_obj, "prompt_tokens")
    completion_tokens = _int_field(usage_obj, "completion_tokens")
    total_tokens = _int_field(usage_obj, "total_tokens")
    if total_tokens == 0:
        total_tokens = prompt_tokens + completion_tokens
    result: CallResult = {
        "content": content,
        "usage": {
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": total_tokens,
        },
        "finish_reason": _optional_string_field(choice, "finish_reason"),
    }
    tool_calls = _openai_tool_calls(message)
    if tool_calls:
        result["tool_calls"] = tool_calls
    return result


def _call_openai_responses(
    client: OpenAI,
    model: str,
    messages: list[MessageDict],
    max_tokens: int,
    temperature: float | None,
    *,
    top_p: float | None = None,
    reasoning_effort: str | None = None,
) -> CallResult:
    """Call OpenAI's Responses API for a text route."""
    kwargs: dict[str, object] = {
        "model": model,
        "input": messages,
        "max_output_tokens": max_tokens,
    }
    if temperature is not None:
        kwargs["temperature"] = temperature
    if top_p is not None:
        kwargs["top_p"] = top_p
    if reasoning_effort:
        kwargs["reasoning"] = {"effort": reasoning_effort}

    responses = _field(client, "responses")
    create = cast(Callable[..., object], _field(responses, "create"))
    response = create(**kwargs)
    usage_obj = _field(response, "usage")
    prompt_tokens = _int_field(usage_obj, "input_tokens")
    completion_tokens = _int_field(usage_obj, "output_tokens")
    total_tokens = _int_field(usage_obj, "total_tokens")
    if total_tokens == 0:
        total_tokens = prompt_tokens + completion_tokens
    return {
        "content": _openai_responses_text(response),
        "usage": {
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": total_tokens,
        },
        "finish_reason": _optional_string_field(response, "status"),
    }


def _call_google_genai(
    client: object,
    model: str,
    messages: list[MessageDict],
    max_tokens: int,
    temperature: float | None,
    *,
    top_p: float | None = None,
    stop_sequences: list[str] | None = None,
    seed: int | None = None,
    structured_output: Mapping[str, object] | None = None,
    reasoning: bool = False,
    thinking_budget_tokens: int | None = None,
    reasoning_effort: str | None = None,
) -> CallResult:
    """Call a google-genai generate_content endpoint."""
    system_instruction, contents = _google_contents(messages)
    config: dict[str, object] = {"max_output_tokens": max_tokens}
    if temperature is not None:
        config["temperature"] = temperature
    if system_instruction:
        config["system_instruction"] = system_instruction
    if top_p is not None:
        config["top_p"] = top_p
    if stop_sequences:
        config["stop_sequences"] = stop_sequences
    if seed is not None:
        config["seed"] = seed
    _apply_google_structured_output(config, structured_output)
    thinking_config = _google_thinking_config(
        reasoning=reasoning,
        thinking_budget_tokens=thinking_budget_tokens,
        reasoning_effort=reasoning_effort,
    )
    if thinking_config is not None:
        config["thinking_config"] = thinking_config

    models = _field(client, "models")
    generate_content = cast(Any, models).generate_content
    response = cast(Callable[..., object], generate_content)(
        model=model,
        contents=contents,
        config=config,
    )
    usage_obj = _field(response, "usage_metadata")
    prompt_tokens = _int_field(usage_obj, "prompt_token_count")
    completion_tokens = _int_field(usage_obj, "candidates_token_count")
    total_tokens = _int_field(usage_obj, "total_token_count")
    if total_tokens == 0:
        total_tokens = prompt_tokens + completion_tokens
    candidate = _first_sequence_item(_field(response, "candidates"))
    return {
        "content": _google_response_text(response),
        "usage": {
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": total_tokens,
        },
        "finish_reason": _optional_string_field(candidate, "finish_reason"),
    }


def _call_ark_runtime(
    client: object,
    model: str,
    messages: list[MessageDict],
    max_tokens: int,
    temperature: float | None,
    *,
    top_p: float | None = None,
    stop_sequences: list[str] | None = None,
    seed: int | None = None,
    parallel_tool_calls: bool | None = None,
    structured_output: Mapping[str, object] | None = None,
    reasoning_effort: str | None = None,
) -> CallResult:
    """Call Volcengine Ark official SDK chat completions."""
    kwargs: dict[str, object] = {
        "model": model,
        "messages": cast(Iterable[ChatCompletionMessageParam], messages),
        "max_tokens": max_tokens,
    }
    if temperature is not None:
        kwargs["temperature"] = temperature
    if top_p is not None:
        kwargs["top_p"] = top_p
    if stop_sequences:
        kwargs["stop"] = stop_sequences
    if seed is not None:
        kwargs["seed"] = seed
    if parallel_tool_calls is not None:
        kwargs["parallel_tool_calls"] = parallel_tool_calls
    if reasoning_effort:
        kwargs["reasoning_effort"] = reasoning_effort
    response_format = _openai_response_format(structured_output)
    if response_format is not None:
        kwargs["response_format"] = response_format

    chat = _field(client, "chat")
    completions = _field(chat, "completions")
    create = cast(Any, completions).create
    response = cast(Callable[..., object], create)(**kwargs)
    usage_obj = _field(response, "usage")
    choice = _first_sequence_item(_field(response, "choices"))
    message = _field(choice, "message")
    prompt_tokens = _int_field(usage_obj, "prompt_tokens")
    completion_tokens = _int_field(usage_obj, "completion_tokens")
    total_tokens = _int_field(usage_obj, "total_tokens")
    if total_tokens == 0:
        total_tokens = prompt_tokens + completion_tokens
    return {
        "content": _string_field(message, "content"),
        "usage": {
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": total_tokens,
        },
        "finish_reason": _optional_string_field(choice, "finish_reason"),
    }


def _call_anthropic_compatible(
    client: Anthropic,
    model: str,
    messages: list[MessageDict],
    max_tokens: int,
    temperature: float | None,
    *,
    reasoning: bool = False,
    thinking_budget_tokens: int | None = None,
    tools: list[ToolSchema] | None = None,
    tool_choice: str | None = None,
    top_p: float | None = None,
    stop_sequences: list[str] | None = None,
    request_mapper_id: str | None = None,
) -> CallResult:
    """Call an Anthropic-compatible messages endpoint."""
    system_text, api_messages = _split_anthropic_messages(messages)
    kwargs: dict[str, object] = {
        "model": model,
        "messages": api_messages,
        "max_tokens": max_tokens,
    }
    if system_text:
        kwargs["system"] = system_text
    if top_p is not None:
        kwargs["top_p"] = top_p
    if stop_sequences:
        kwargs["stop_sequences"] = stop_sequences
    anthropic_tools = _anthropic_tools_from_openai(tools)
    if anthropic_tools:
        kwargs["tools"] = anthropic_tools
        anthropic_tool_choice = _anthropic_tool_choice(tool_choice)
        if anthropic_tool_choice is not None:
            kwargs["tool_choice"] = anthropic_tool_choice

    if reasoning:
        response = _anthropic_messages_create_with_reasoning(
            client,
            kwargs,
            model,
            max_tokens,
            thinking_budget_tokens,
            request_mapper_id,
        )
    else:
        if temperature is not None:
            kwargs["temperature"] = temperature
        response = _anthropic_messages_create(client, kwargs)

    usage_obj = _field(response, "usage")
    prompt_tokens = _int_field(usage_obj, "input_tokens")
    completion_tokens = _int_field(usage_obj, "output_tokens")
    result: CallResult = {
        "content": _anthropic_content_text(_field(response, "content")),
        "usage": {
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": prompt_tokens + completion_tokens,
        },
        "finish_reason": _optional_string_field(response, "stop_reason"),
    }
    tool_calls = _anthropic_tool_calls(_field(response, "content"))
    if tool_calls:
        result["tool_calls"] = tool_calls
    return result


def _anthropic_messages_create_with_reasoning(
    client: Anthropic,
    kwargs: dict[str, object],
    model: str,
    max_tokens: int,
    thinking_budget_tokens: int | None,
    request_mapper_id: str | None,
) -> object:
    kwargs["temperature"] = 1.0
    if _anthropic_mapper_prefers_adaptive_thinking(request_mapper_id):
        kwargs["thinking"] = {"type": "adaptive"}
        return _anthropic_messages_create(client, kwargs)
    if _anthropic_mapper_prefers_manual_thinking(request_mapper_id):
        kwargs["thinking"] = _anthropic_manual_thinking(max_tokens, thinking_budget_tokens)
        return _anthropic_messages_create(client, kwargs)
    if not _anthropic_adaptive_thinking_supported(model):
        kwargs["thinking"] = _anthropic_manual_thinking(max_tokens, thinking_budget_tokens)
        return _anthropic_messages_create(client, kwargs)

    kwargs["thinking"] = {"type": "adaptive"}
    try:
        return _anthropic_messages_create(client, kwargs)
    except Exception as exc:
        if (
            not _is_anthropic_adaptive_rejection(exc)
            or not _anthropic_manual_thinking_budget_supported(model)
        ):
            raise
        kwargs["thinking"] = _anthropic_manual_thinking(max_tokens, thinking_budget_tokens)
        return _anthropic_messages_create(client, kwargs)


def _anthropic_manual_thinking(
    max_tokens: int,
    thinking_budget_tokens: int | None,
) -> dict[str, object]:
    return {
        "type": "enabled",
        "budget_tokens": _anthropic_thinking_budget(
            max_tokens,
            thinking_budget_tokens,
        ),
    }


def _call_wavespeed_any_llm(
    route: ResolvedRoute,
    messages: list[MessageDict],
    model: str,
    max_tokens: int,
    temperature: float | None,
    *,
    reasoning: bool,
    credential_provider: CredentialProviderProtocol | None = None,
    tools: list[ToolSchema] | None = None,
    tool_choice: str | None = None,
) -> CallResult:
    """Call WaveSpeed's Any-LLM endpoint with 5xx backoff retries."""
    from graph_agent_gateway.client_manager import LLMClientManager

    api_key = LLMClientManager._resolve_api_key(route, credential_provider=credential_provider)
    prompt_parts: list[str] = []
    system_prompt = ""
    for msg in messages:
        role = str(msg.get("role", "user"))
        content = _coerce_text(msg.get("content", ""))
        if role == "system":
            system_prompt = (
                f"{system_prompt}\n\n{content}".strip() if system_prompt else content
            )
        else:
            prompt_parts.append(content)

    payload: dict[str, object] = {
        "prompt": "\n\n".join(prompt_parts),
        "model": model,
        "enable_sync_mode": True,
        "max_tokens": max_tokens,
        "reasoning": reasoning,
        "priority": "latency",
    }
    if temperature is not None:
        payload["temperature"] = temperature
    if system_prompt:
        payload["system_prompt"] = system_prompt
    if tools:
        payload["tools"] = tools
    if tool_choice:
        payload["tool_choice"] = tool_choice

    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    response: httpx.Response | None = None
    for attempt in range(3):
        response = httpx.post(
            f"{route.base_url.rstrip('/')}/wavespeed-ai/any-llm",
            json=payload,
            headers=headers,
            timeout=300.0,
        )
        if response.status_code not in _RETRYABLE_WAVESPEED_STATUS:
            break
        if attempt < 2:
            wait_seconds = 10 * (2**attempt)
            logger.warning(
                "phase=ordinary_chat action=wavespeed_retry status=%s attempt=%d wait=%d",
                response.status_code,
                attempt + 1,
                wait_seconds,
            )
            time.sleep(wait_seconds)

    if response is None:
        raise RuntimeError("WaveSpeed returned no response")
    if response.status_code != 200:
        raise RuntimeError(f"WaveSpeed HTTP {response.status_code}: {response.text[:300]}")

    payload_obj = response.json()
    if not isinstance(payload_obj, Mapping):
        raise RuntimeError("WaveSpeed returned a non-object response")
    code = payload_obj.get("code")
    if code != 200:
        raise RuntimeError(f"WaveSpeed error: {payload_obj.get('message', 'unknown')}")

    data = payload_obj.get("data")
    if not isinstance(data, Mapping):
        raise RuntimeError("WaveSpeed returned no data object")
    status = data.get("status")
    if status == "failed":
        raise RuntimeError(f"WaveSpeed task failed: {data.get('error', 'unknown')}")
    if status != "completed":
        raise RuntimeError(f"WaveSpeed unexpected status: {status}")
    output = _first_sequence_item(data.get("outputs"))
    if output is None:
        raise RuntimeError("WaveSpeed returned no outputs")
    return {
        "content": _coerce_text(output),
        "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
        "finish_reason": None,
    }


def _call_with_token_escalation(
    route: ResolvedRoute,
    max_tokens: int,
    invoke: Callable[[int], CallResult],
    *,
    runtime_policy: RuntimePolicy,
) -> CallResult:
    """Retry ordinary-chat calls with a larger token budget after truncation."""
    current_tokens = max(1, int(max_tokens))
    cap = _max_token_cap(route, current_tokens)
    result: CallResult | None = None
    for _ in range(runtime_policy.token_escalation_rounds + 1):
        result = invoke(current_tokens)
        _record_usage_from_result(route.endpoint_id, result)
        if not _is_finish_reason_truncated(result.get("finish_reason")):
            return result
        if current_tokens >= cap:
            return result
        current_tokens = min(cap, max(current_tokens + 1, current_tokens * 2))
    assert result is not None
    return result


def _record_usage_from_result(provider_code: str, result: Mapping[str, object]) -> None:
    from graph_agent_gateway.client_manager import LLMClientManager

    usage = result.get("usage")
    if isinstance(usage, Mapping):
        LLMClientManager.record_usage(
            provider_code,
            _int_field(usage, "prompt_tokens"),
            _int_field(usage, "completion_tokens"),
        )
    else:
        LLMClientManager.record_usage(provider_code, 0, 0)


def _max_token_cap(route: ResolvedRoute, requested: int) -> int:
    capability = route.capabilities.get("max_output_tokens")
    value = capability.value if capability is not None else None
    if isinstance(value, int) and value > 0:
        return max(requested, value)
    return requested


def _normalise_message_role(role: object) -> Literal["user", "assistant"]:
    raw = str(role or "user")
    return "assistant" if raw == "assistant" else "user"


def _google_contents(messages: Sequence[MessageDict]) -> tuple[str, list[dict[str, object]]]:
    system_parts: list[str] = []
    contents: list[dict[str, object]] = []
    for msg in messages:
        role = str(msg.get("role", "user"))
        text = _coerce_text(msg.get("content", ""))
        if role == "system":
            if text:
                system_parts.append(text)
            continue
        contents.append(
            {
                "role": "model" if role == "assistant" else "user",
                "parts": [{"text": text}],
            }
        )
    if not contents:
        contents.append({"role": "user", "parts": [{"text": "Proceed."}]})
    return "\n\n".join(system_parts), contents


def _apply_google_structured_output(
    config: dict[str, object],
    structured_output: Mapping[str, object] | None,
) -> None:
    if not structured_output:
        return
    mode = structured_output.get("mode")
    if mode not in {"json_object", "json_schema"}:
        return
    config["response_mime_type"] = "application/json"
    schema = structured_output.get("json_schema")
    if isinstance(schema, Mapping):
        config["response_schema"] = dict(schema)


def _google_thinking_config(
    *,
    reasoning: bool,
    thinking_budget_tokens: int | None,
    reasoning_effort: str | None,
) -> dict[str, object] | None:
    if not reasoning:
        return None
    if reasoning_effort:
        return {"thinking_level": reasoning_effort}
    if thinking_budget_tokens is not None:
        return {"thinking_budget": thinking_budget_tokens}
    return None


def _google_response_text(response: object) -> str:
    text = _field(response, "text")
    if isinstance(text, str) and text:
        return text
    candidate = _first_sequence_item(_field(response, "candidates"))
    content = _field(candidate, "content")
    parts = _field(content, "parts")
    if not isinstance(parts, Sequence) or isinstance(parts, str | bytes):
        return ""
    chunks: list[str] = []
    for part in parts:
        part_text = _field(part, "text")
        if isinstance(part_text, str):
            chunks.append(part_text)
    return "".join(chunks)


def _split_anthropic_messages(messages: Sequence[MessageDict]) -> tuple[str, list[MessageParam]]:
    system_parts: list[str] = []
    api_messages: list[MessageParam] = []
    for msg in messages:
        role = str(msg.get("role", "user"))
        content = _coerce_text(msg.get("content", ""))
        if role == "system":
            system_parts.append(content)
            continue
        api_messages.append(MessageParam(role=_normalise_message_role(role), content=content))
    if not api_messages:
        api_messages.append(MessageParam(role="user", content="Proceed."))
    return "\n\n".join(system_parts), api_messages


def _is_anthropic_adaptive_rejection(exc: Exception) -> bool:
    text = str(exc).lower()
    return "adaptive" in text or "extra inputs" in text


def _anthropic_thinking_budget(
    max_tokens: int,
    configured_budget: int | None = None,
) -> int:
    minimum_budget = 1024
    budget = configured_budget if configured_budget is not None else min(4096, max_tokens - 1)
    if budget < minimum_budget:
        raise ValueError(
            f"Anthropic thinking budget must be at least {minimum_budget} tokens"
        )
    if budget >= max_tokens:
        raise ValueError(
            "Anthropic thinking budget must be smaller than max_output_tokens"
        )
    return budget


def _anthropic_mapper_prefers_adaptive_thinking(request_mapper_id: str | None) -> bool:
    return "thinking_adaptive" in (request_mapper_id or "")


def _anthropic_mapper_prefers_manual_thinking(request_mapper_id: str | None) -> bool:
    return "thinking_manual" in (request_mapper_id or "")


def _anthropic_adaptive_thinking_supported(model: str) -> bool:
    normalized = model.strip().lower().replace("_", "-")
    return normalized.startswith(
        (
            "claude-opus-4-7",
            "claude-opus-4-6",
            "claude-sonnet-4-6",
        )
    )


def _anthropic_manual_thinking_budget_supported(model: str) -> bool:
    normalized = model.strip().lower().replace("_", "-")
    return not normalized.startswith("claude-opus-4-7")


def _anthropic_messages_create(client: Anthropic, kwargs: Mapping[str, object]) -> object:
    create = cast(Callable[..., object], client.messages.create)
    return create(**dict(kwargs))


def _openai_response_format(
    structured_output: Mapping[str, object] | None,
) -> dict[str, object] | None:
    if not structured_output:
        return None
    mode = structured_output.get("mode")
    if mode == "json_object":
        return {"type": "json_object"}
    if mode != "json_schema":
        return None
    schema = structured_output.get("json_schema")
    if not isinstance(schema, Mapping):
        return None
    json_schema = dict(schema)
    strict = structured_output.get("strict")
    if isinstance(strict, bool) and "strict" not in json_schema:
        json_schema["strict"] = strict
    return {"type": "json_schema", "json_schema": json_schema}


def _anthropic_tool_choice(tool_choice: str | None) -> dict[str, object] | None:
    if tool_choice is None:
        return None
    if tool_choice in {"auto", "any"}:
        return {"type": tool_choice}
    if tool_choice == "none":
        return {"type": "auto"}
    return {"type": "tool", "name": tool_choice}


def _is_finish_reason_truncated(finish_reason: object) -> bool:
    if finish_reason is None:
        return False
    return str(finish_reason).lower() in _TRUNCATED_FINISH_REASONS


def _field(value: object, name: str) -> object:
    if isinstance(value, Mapping):
        return value.get(name)
    return getattr(value, name, None)


def _first_sequence_item(value: object) -> object | None:
    if isinstance(value, Sequence) and not isinstance(value, str | bytes):
        return value[0] if value else None
    return None


def _coerce_text(value: object) -> str:
    if value is None:
        return ""
    return value if isinstance(value, str) else str(value)


def _string_field(value: object, name: str) -> str:
    return _coerce_text(_field(value, name))


def _optional_string_field(value: object, name: str) -> str | None:
    result = _field(value, name)
    return None if result is None else str(result)


def _int_field(value: object, name: str) -> int:
    raw = _field(value, name)
    if isinstance(raw, bool):
        return int(raw)
    if isinstance(raw, int):
        return raw
    if isinstance(raw, float):
        return int(raw)
    if isinstance(raw, str):
        try:
            return int(raw)
        except ValueError:
            return 0
    return 0


def _anthropic_content_text(value: object) -> str:
    if not isinstance(value, Sequence) or isinstance(value, str | bytes):
        return ""
    chunks: list[str] = []
    for block in value:
        block_type = _field(block, "type")
        if block_type == "text":
            chunks.append(_string_field(block, "text"))
    return "".join(chunks)


def _openai_responses_text(response: object) -> str:
    output_text = _field(response, "output_text")
    if isinstance(output_text, str):
        return output_text
    output = _field(response, "output")
    if not isinstance(output, Sequence) or isinstance(output, str | bytes):
        return ""
    chunks: list[str] = []
    for item in output:
        content = _field(item, "content")
        if not isinstance(content, Sequence) or isinstance(content, str | bytes):
            continue
        for part in content:
            text = _field(part, "text")
            if isinstance(text, str):
                chunks.append(text)
    return "".join(chunks)


def _openai_tool_calls(message: object) -> list[ToolSchema]:
    raw = _field(message, "tool_calls")
    if not isinstance(raw, Sequence) or isinstance(raw, str | bytes):
        return []
    calls: list[ToolSchema] = []
    for call in raw:
        function = _field(call, "function")
        name = _string_field(function, "name")
        arguments = _string_field(function, "arguments")
        if not name:
            continue
        calls.append(
            {
                "id": _optional_string_field(call, "id") or "",
                "type": _optional_string_field(call, "type") or "function",
                "function": {"name": name, "arguments": arguments},
            }
        )
    return calls


def _anthropic_tool_calls(value: object) -> list[ToolSchema]:
    if not isinstance(value, Sequence) or isinstance(value, str | bytes):
        return []
    calls: list[ToolSchema] = []
    for block in value:
        if _field(block, "type") != "tool_use":
            continue
        name = _string_field(block, "name")
        if not name:
            continue
        calls.append(
            {
                "id": _optional_string_field(block, "id") or "",
                "type": "function",
                "function": {
                    "name": name,
                    "arguments": json.dumps(_field(block, "input") or {}),
                },
            }
        )
    return calls


def _anthropic_tools_from_openai(
    tools: list[ToolSchema] | None,
) -> list[ToolSchema]:
    if not tools:
        return []
    converted: list[ToolSchema] = []
    for tool in tools:
        function = tool.get("function")
        if not isinstance(function, Mapping):
            continue
        name = function.get("name")
        if not isinstance(name, str) or not name:
            continue
        input_schema = function.get("parameters")
        if not isinstance(input_schema, Mapping):
            input_schema = {"type": "object", "properties": {}}
        item: ToolSchema = {
            "name": name,
            "input_schema": dict(input_schema),
        }
        description = function.get("description")
        if isinstance(description, str) and description:
            item["description"] = description
        converted.append(item)
    return converted


__all__ = ["dispatch_ordinary_chat"]
