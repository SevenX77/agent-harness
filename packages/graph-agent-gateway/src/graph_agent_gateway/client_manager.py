"""Native SDK client manager for route-backed gateway runtime."""

from __future__ import annotations

import json
import logging
import time
from collections.abc import Callable, Iterable, Mapping, Sequence
from typing import ClassVar, Literal, cast

import httpx
from anthropic import Anthropic
from anthropic.types import MessageParam
from openai import OpenAI
from openai.types.chat import ChatCompletionMessageParam

from graph_agent_gateway.registry.schema import ResolvedRoute, RuntimePolicy

logger = logging.getLogger(__name__)

MessageDict = dict[str, object]
CallResult = dict[str, object]
UsageStats = dict[str, int]
ToolSchema = dict[str, object]

_RETRYABLE_WAVESPEED_STATUS = {502, 503, 504}
_TRUNCATED_FINISH_REASONS = {
    "length",
    "max_tokens",
    "max_output_tokens",
    "finish_reason_max_tokens",
    "stop_reason_max_tokens",
}


class LLMClientManager:
    """Shared native-SDK client cache and provider call helpers.

    The class attributes intentionally live for the process lifetime:
    SDK clients own HTTP connection pools, while usage stats and
    provider-down TTL state are global infrastructure concerns rather
    than per-harness runtime state.
    """

    _clients: ClassVar[dict[str, OpenAI | Anthropic]] = {}
    _usage_stats: ClassVar[dict[str, UsageStats]] = {}
    _provider_down_cache: ClassVar[dict[str, float]] = {}

    @classmethod
    def is_provider_marked_down(
        cls,
        route: ResolvedRoute,
        runtime_policy: RuntimePolicy,
    ) -> bool:
        """Return true when a route is still inside the configured down TTL."""
        del runtime_policy
        return cls._is_provider_marked_down(route)

    @classmethod
    def probe_provider(
        cls,
        route: ResolvedRoute,
        runtime_policy: RuntimePolicy,
    ) -> bool:
        """Probe one route using runtime policy instead of class constants."""
        return cls._probe_provider(route, runtime_policy)

    @classmethod
    def dispatch_provider_call(
        cls,
        route: ResolvedRoute,
        messages: list[MessageDict],
        *,
        max_tokens: int,
        temperature: float,
        runtime_policy: RuntimePolicy,
        reasoning: bool = False,
        tools: list[ToolSchema] | None = None,
        tool_choice: str | None = None,
    ) -> CallResult:
        """Call one route and return a normalized chat result."""
        return cls._dispatch_provider_call(
            route,
            messages,
            max_tokens,
            temperature,
            runtime_policy=runtime_policy,
            reasoning=reasoning,
            tools=tools,
            tool_choice=tool_choice,
        )

    @classmethod
    def mark_provider_down(
        cls,
        route: ResolvedRoute,
        exc: BaseException,
        runtime_policy: RuntimePolicy,
    ) -> None:
        """Mark one route down after a fallback-eligible failure."""
        del exc
        cls._mark_provider_down(route, runtime_policy)

    @classmethod
    def usage_total_calls(cls, route: ResolvedRoute) -> int:
        """Return total call count for one endpoint/route stats bucket."""
        stats = cls._usage_stats.get(route.endpoint_id)
        if not isinstance(stats, Mapping):
            return 0
        value = stats.get("total_calls")
        return value if isinstance(value, int) else 0

    @classmethod
    def _get_openai_client(
        cls,
        route: ResolvedRoute,
        *,
        timeout_override: float | None = None,
        runtime_policy: RuntimePolicy | None = None,
    ) -> OpenAI:
        """Return a cached OpenAI-compatible client for one route endpoint."""
        policy = runtime_policy or RuntimePolicy()
        timeout_value = float(timeout_override or route.timeout_seconds)
        cache_key = cls._client_cache_key("openai", route, timeout_value, policy)

        cached = cls._clients.get(cache_key)
        if cached is not None:
            return cast(OpenAI, cached)

        api_key = cls._resolve_api_key(route)
        base_url = route.base_url
        http_client = httpx.Client(
            trust_env=route.trust_env,
            timeout=httpx.Timeout(timeout_value),
        )
        client = OpenAI(
            api_key=api_key,
            base_url=base_url or None,
            timeout=timeout_value,
            max_retries=0,
            http_client=http_client,
        )

        cls._clients[cache_key] = client
        cls._init_usage_stats(route.endpoint_id)
        logger.info(
            "phase=llm_client_manager action=create_client type=openai endpoint=%s route=%s base_url=%s",
            route.endpoint_id,
            route.route_id,
            base_url or "<default>",
        )
        return client

    @classmethod
    def _get_anthropic_client(
        cls,
        route: ResolvedRoute,
        *,
        runtime_policy: RuntimePolicy | None = None,
    ) -> Anthropic:
        """Return a cached Anthropic-compatible client for one route endpoint."""
        policy = runtime_policy or RuntimePolicy()
        cache_key = cls._client_cache_key("anthropic", route, float(route.timeout_seconds), policy)
        cached = cls._clients.get(cache_key)
        if cached is not None:
            return cast(Anthropic, cached)

        client = Anthropic(
            api_key=cls._resolve_api_key(route),
            base_url=route.base_url or None,
            timeout=float(route.timeout_seconds),
            max_retries=0,
        )
        cls._clients[cache_key] = client
        cls._init_usage_stats(route.endpoint_id)
        logger.info(
            "phase=llm_client_manager action=create_client type=anthropic endpoint=%s route=%s base_url=%s",
            route.endpoint_id,
            route.route_id,
            route.base_url or "<default>",
        )
        return client

    @classmethod
    def _init_usage_stats(cls, provider_code: str) -> None:
        """Ensure the per-provider usage accumulator exists."""
        cls._usage_stats.setdefault(
            provider_code,
            {
                "total_calls": 0,
                "prompt_tokens": 0,
                "completion_tokens": 0,
                "total_tokens": 0,
            },
        )

    @classmethod
    def record_usage(
        cls,
        provider: str,
        prompt_tokens: int,
        completion_tokens: int,
    ) -> None:
        """Accumulate one provider call's token usage."""
        cls._init_usage_stats(provider)
        stats = cls._usage_stats[provider]
        stats["total_calls"] += 1
        stats["prompt_tokens"] += int(prompt_tokens)
        stats["completion_tokens"] += int(completion_tokens)
        stats["total_tokens"] += int(prompt_tokens) + int(completion_tokens)

    @classmethod
    def get_usage_stats(cls) -> dict[str, UsageStats]:
        """Return a deep copy of current usage stats."""
        return {provider: dict(stats) for provider, stats in cls._usage_stats.items()}

    @classmethod
    def reset_stats(cls) -> None:
        """Clear all accumulated usage stats."""
        cls._usage_stats.clear()

    @classmethod
    def _make_down_key(cls, provider_code: str, model_name: str) -> str:
        """Build the provider/model key used by the down-cache."""
        return f"{provider_code}:{model_name}"

    @classmethod
    def _is_provider_marked_down(cls, route: ResolvedRoute) -> bool:
        """Return true when route is still inside the down TTL."""
        key = cls._make_down_key(route.endpoint_id, route.provider_model_id)
        expires_at = cls._provider_down_cache.get(key)
        if expires_at is None:
            return False
        if time.monotonic() >= expires_at:
            del cls._provider_down_cache[key]
            return False
        return True

    @classmethod
    def _mark_provider_down(
        cls,
        route: ResolvedRoute,
        runtime_policy: RuntimePolicy,
    ) -> None:
        """Mark route down for the configured probe TTL window."""
        key = cls._make_down_key(route.endpoint_id, route.provider_model_id)
        ttl = runtime_policy.provider_down_ttl_seconds
        cls._provider_down_cache[key] = time.monotonic() + ttl
        logger.warning(
            "phase=llm_client_manager action=mark_down endpoint=%s route=%s model=%s ttl=%d",
            route.endpoint_id,
            route.route_id,
            route.provider_model_id,
            ttl,
        )

    @classmethod
    def _probe_provider(
        cls,
        route: ResolvedRoute,
        runtime_policy: RuntimePolicy,
    ) -> bool:
        """Run a one-token active probe when the provider type supports it."""
        if route.protocol == "openai_compatible":
            try:
                openai_client = cls._get_openai_client(
                    route,
                    timeout_override=runtime_policy.probe_timeout_seconds,
                    runtime_policy=runtime_policy,
                )
                openai_client.chat.completions.create(
                    model=route.provider_model_id,
                    messages=cast(
                        Iterable[ChatCompletionMessageParam],
                        [{"role": "user", "content": "."}],
                    ),
                    max_tokens=1,
                    temperature=0,
                )
                return True
            except Exception as exc:
                logger.warning(
                    "phase=llm_client_manager action=probe_fail endpoint=%s route=%s model=%s error=%s",
                    route.endpoint_id,
                    route.route_id,
                    route.provider_model_id,
                    exc,
                )
                cls._mark_provider_down(route, runtime_policy)
                return False

        if route.protocol == "anthropic_compatible":
            try:
                anthropic_client = cls._get_anthropic_client(
                    route,
                    runtime_policy=runtime_policy,
                )
                anthropic_client.messages.create(
                    model=route.provider_model_id,
                    messages=[MessageParam(role="user", content=".")],
                    max_tokens=1,
                )
                return True
            except Exception as exc:
                logger.warning(
                    "phase=llm_client_manager action=probe_fail endpoint=%s route=%s model=%s error=%s",
                    route.endpoint_id,
                    route.route_id,
                    route.provider_model_id,
                    exc,
                )
                cls._mark_provider_down(route, runtime_policy)
                return False

        return True

    @classmethod
    def _call_openai_compatible(
        cls,
        client: OpenAI,
        model: str,
        messages: list[MessageDict],
        max_tokens: int,
        temperature: float,
        *,
        tools: list[ToolSchema] | None = None,
        tool_choice: str | None = None,
    ) -> CallResult:
        """Call an OpenAI-compatible chat completion endpoint."""
        kwargs: dict[str, object] = {
            "model": model,
            "messages": cast(Iterable[ChatCompletionMessageParam], messages),
            "max_tokens": max_tokens,
            "temperature": temperature,
        }
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

    @classmethod
    def _call_anthropic_compatible(
        cls,
        client: Anthropic,
        model: str,
        messages: list[MessageDict],
        max_tokens: int,
        temperature: float,
        *,
        reasoning: bool = False,
        tools: list[ToolSchema] | None = None,
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
        anthropic_tools = _anthropic_tools_from_openai(tools)
        if anthropic_tools:
            kwargs["tools"] = anthropic_tools

        if reasoning:
            kwargs["temperature"] = 1.0
            kwargs["thinking"] = {
                "type": "adaptive",
                "budget_tokens": _anthropic_thinking_budget(max_tokens),
            }
            try:
                response = _anthropic_messages_create(client, kwargs)
            except Exception as exc:
                if not _is_anthropic_adaptive_rejection(exc):
                    raise
                kwargs["thinking"] = {
                    "type": "enabled",
                    "budget_tokens": _anthropic_thinking_budget(max_tokens),
                }
                response = _anthropic_messages_create(client, kwargs)
        else:
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

    @classmethod
    def _call_wavespeed_any_llm(
        cls,
        route: ResolvedRoute,
        messages: list[MessageDict],
        model: str,
        max_tokens: int,
        temperature: float,
        *,
        reasoning: bool,
        tools: list[ToolSchema] | None = None,
        tool_choice: str | None = None,
    ) -> CallResult:
        """Call WaveSpeed's Any-LLM endpoint with 5xx backoff retries."""
        api_key = cls._resolve_api_key(route)
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
            "temperature": temperature,
            "reasoning": reasoning,
            "priority": "latency",
        }
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
                    "phase=llm_client_manager action=wavespeed_retry status=%s attempt=%d wait=%d",
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

    @classmethod
    def _dispatch_provider_call(
        cls,
        route: ResolvedRoute,
        messages: list[MessageDict],
        max_tokens: int,
        temperature: float,
        *,
        runtime_policy: RuntimePolicy,
        reasoning: bool = False,
        tools: list[ToolSchema] | None = None,
        tool_choice: str | None = None,
    ) -> CallResult:
        """Route a provider call by configured endpoint protocol."""

        def invoke(token_budget: int) -> CallResult:
            if route.protocol == "openai_compatible":
                client = cls._get_openai_client(route, runtime_policy=runtime_policy)
                return cls._call_openai_compatible(
                    client,
                    route.provider_model_id,
                    messages,
                    token_budget,
                    temperature,
                    tools=tools,
                    tool_choice=tool_choice,
                )

            if route.protocol == "anthropic_compatible":
                anthropic_client = cls._get_anthropic_client(
                    route,
                    runtime_policy=runtime_policy,
                )
                return cls._call_anthropic_compatible(
                    anthropic_client,
                    route.provider_model_id,
                    messages,
                    token_budget,
                    temperature,
                    reasoning=reasoning,
                    tools=tools,
                )

            if route.protocol == "google_genai":
                raise NotImplementedError("google_genai route execution is not implemented yet")

            raise ValueError(f"Unknown endpoint protocol: {route.protocol}")

        return cls._call_with_token_escalation(
            route,
            max_tokens,
            invoke,
            runtime_policy=runtime_policy,
        )

    @classmethod
    def _call_with_token_escalation(
        cls,
        route: ResolvedRoute,
        max_tokens: int,
        invoke: Callable[[int], CallResult],
        *,
        runtime_policy: RuntimePolicy,
    ) -> CallResult:
        """Retry with a larger token budget when the provider truncates output."""
        current_tokens = max(1, int(max_tokens))
        cap = cls._max_token_cap(route, current_tokens)
        result: CallResult | None = None
        for _ in range(runtime_policy.token_escalation_rounds + 1):
            result = invoke(current_tokens)
            cls._record_usage_from_result(route.endpoint_id, result)
            if not _is_finish_reason_truncated(result.get("finish_reason")):
                return result
            if current_tokens >= cap:
                return result
            current_tokens = min(cap, max(current_tokens + 1, current_tokens * 2))
        assert result is not None
        return result

    @classmethod
    def _record_usage_from_result(cls, provider_code: str, result: Mapping[str, object]) -> None:
        usage = result.get("usage")
        if isinstance(usage, Mapping):
            cls.record_usage(
                provider_code,
                _int_field(usage, "prompt_tokens"),
                _int_field(usage, "completion_tokens"),
            )
        else:
            cls.record_usage(provider_code, 0, 0)

    @classmethod
    def _max_token_cap(cls, route: ResolvedRoute, requested: int) -> int:
        capability = route.capabilities.get("max_output_tokens")
        value = capability.value if capability is not None else None
        if isinstance(value, int) and value > 0:
            return max(requested, value)
        return requested

    @classmethod
    def _resolve_api_key(cls, route: ResolvedRoute) -> str:
        api_key = route.api_key.get_secret_value()
        if not api_key:
            raise ValueError(f"endpoint has no credential: {route.endpoint_id}")
        return api_key

    @classmethod
    def _client_cache_key(
        cls,
        client_type: str,
        route: ResolvedRoute,
        timeout_value: float,
        runtime_policy: RuntimePolicy,
    ) -> str:
        return (
            f"{client_type}:{route.endpoint_id}:{route.credential_fingerprint}:"
            f"timeout:{timeout_value:g}:trust_env:{route.trust_env}:"
            f"proxy:{route.proxy_env or ''}:"
            f"down_ttl:{runtime_policy.provider_down_ttl_seconds}:"
            f"probe_timeout:{runtime_policy.probe_timeout_seconds}:"
            f"token_escalation:{runtime_policy.token_escalation_rounds}"
        )


def _normalise_message_role(role: object) -> Literal["user", "assistant"]:
    raw = str(role or "user")
    return "assistant" if raw == "assistant" else "user"


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
    return "\n\n".join(system_parts), api_messages


def _is_anthropic_adaptive_rejection(exc: Exception) -> bool:
    text = str(exc).lower()
    return "adaptive" in text or "extra inputs" in text


def _anthropic_thinking_budget(max_tokens: int) -> int:
    return max(1, min(4096, max_tokens - 1))


def _anthropic_messages_create(client: Anthropic, kwargs: Mapping[str, object]) -> object:
    create = cast(Callable[..., object], client.messages.create)
    return create(**dict(kwargs))


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


__all__ = ["LLMClientManager"]
