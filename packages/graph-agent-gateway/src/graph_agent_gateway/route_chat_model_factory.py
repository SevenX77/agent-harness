"""Build LangChain ChatX models from resolved gateway routes."""

from __future__ import annotations

import importlib
from collections.abc import Mapping, Sequence
from typing import Any, Final, cast

from langchain_anthropic import ChatAnthropic
from langchain_core.language_models.base import LanguageModelInput
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage
from langchain_openai import ChatOpenAI
from pydantic import SecretStr

from graph_agent_gateway.models import GenericRouteChatModel
from graph_agent_gateway.provider_profiles import (
    apply_provider_profile_layers,
    route_provider_profile_keys,
)
from graph_agent_gateway.registry import (
    CredentialResolveError,
    ResolvedRoute,
    canonicalize_base_url,
    provider_temperature_from_authored,
)


class RouteChatModelFactory:
    """Construct a provider ChatX model for one resolved route."""

    def __init__(self, *, credential_provider: Any = None) -> None:
        self.credential_provider = credential_provider

    def build(
        self,
        route: ResolvedRoute,
        *,
        timeout_seconds: float | None = None,
        **caller_kwargs: Any,
    ) -> BaseChatModel:
        """Build the chat model for one route.

        ``timeout_seconds`` overrides the route's own timeout for callers that
        are asking a deliberately cheap question — a probe waits out the
        policy's probe timeout, not the minutes a real generation may take.
        """
        if route.credential_ref.startswith("secret-handle://expired/"):
            raise CredentialResolveError(
                error_code="credential.secret_expired",
                error_payload={"credential_ref": route.credential_ref},
            )
        protocol = str(route.protocol)
        base_url = canonicalize_base_url(route.base_url, protocol)
        api_key = _resolve_api_key(route, self.credential_provider)
        timeout = timeout_seconds if timeout_seconds is not None else route.timeout_seconds
        common = _runtime_kwargs(caller_kwargs)
        common["temperature"] = provider_temperature_from_authored(
            common.get("temperature"),
            route,
        )

        if protocol in {"openai_compatible", "ark_runtime"}:
            kwargs = {
                "model": route.provider_model_id,
                "api_key": api_key,
                "base_url": base_url,
                "timeout": timeout,
                **_mapped_runtime_kwargs(protocol, common),
            }
            chat_openai_cls = (
                PatchedChatDeepSeek if _is_deepseek_route(route) else OpenAICompatibleChatModel
            )
            return chat_openai_cls(**_apply_profiles(route, kwargs))

        if protocol == "anthropic_compatible":
            kwargs = {
                "model": route.provider_model_id,
                "api_key": api_key,
                "base_url": base_url,
                "timeout": timeout,
                **_mapped_runtime_kwargs(protocol, common),
            }
            return ChatAnthropic(**_apply_profiles(route, kwargs))

        if protocol == "google_genai":
            google_module = _import_google_chat_module()
            chat_google = google_module.ChatGoogleGenerativeAI
            kwargs = {
                "model": route.provider_model_id,
                "google_api_key": api_key,
                "timeout": timeout,
                **_mapped_runtime_kwargs(protocol, common),
            }
            return cast(BaseChatModel, chat_google(**_apply_profiles(route, kwargs)))

        generic_kwargs = {
            "max_tokens": common.get("max_tokens"),
            "temperature": common.get("temperature"),
            "top_p": common.get("top_p"),
            "stop_sequences": common.get("stop_sequences"),
            "seed": common.get("seed"),
            "reasoning_effort": common.get("reasoning_effort"),
            "runtime_policy": caller_kwargs.get("runtime_policy"),
            "reasoning": caller_kwargs.get("reasoning"),
            "thinking_budget_tokens": caller_kwargs.get("thinking_budget_tokens"),
            "parallel_tool_calls": caller_kwargs.get("parallel_tool_calls"),
            "structured_output": caller_kwargs.get("structured_output"),
            "call_method_id": caller_kwargs.get("call_method_id"),
            "request_mapper_id": caller_kwargs.get("request_mapper_id"),
        }
        return GenericRouteChatModel(
            route=route,
            credential_provider=self.credential_provider,
            **{key: value for key, value in generic_kwargs.items() if value is not None},
        )


def _runtime_kwargs(caller_kwargs: dict[str, Any]) -> dict[str, Any]:
    """The settings this build was handed, under the names the mappers use.

    Read from the caller and from nowhere else. What a call asks a route for is
    settled in one place — :mod:`graph_agent_gateway.call_settings` — and a
    second reader of the route's own settings here would put back whatever that
    place deliberately left off, which is exactly how a preference a provider
    refuses survives the retry that was supposed to drop it.
    """
    return {
        key: caller_kwargs.get(key)
        for key in ("temperature", "max_tokens", "top_p", "stop_sequences", "seed", "reasoning_effort")
    }


# Which request key each setting becomes, per protocol. This IS the mapping the
# request is built from — not a second list describing it. Anything absent has
# no place in that protocol's request body, so asking a provider about it would
# be asking about a parameter it was never sent (decision doc D4).
_PROVIDER_KEYS: Final[dict[str, dict[str, str]]] = {
    "openai_compatible": {
        "temperature": "temperature",
        "max_tokens": "max_completion_tokens",
        "top_p": "top_p",
        "seed": "seed",
        "stop_sequences": "stop",
        "reasoning_effort": "reasoning_effort",
    },
    "anthropic_compatible": {
        "temperature": "temperature",
        "max_tokens": "max_tokens",
        "top_p": "top_p",
        "stop_sequences": "stop_sequences",
        # Anthropic sells the same dial; ChatAnthropic renders this field as
        # ``output_config.effort`` on the wire (measured 2026-08-10).
        "reasoning_effort": "effort",
    },
    "google_genai": {
        "temperature": "temperature",
        "max_tokens": "max_tokens",
        "top_p": "top_p",
        "stop_sequences": "stop",
        "reasoning_effort": "thinking_level",
    },
}
_PROVIDER_KEYS["ark_runtime"] = _PROVIDER_KEYS["openai_compatible"]


def provider_request_keys(protocol: str) -> Mapping[str, str]:
    """The request key each setting becomes on this protocol, if it becomes one.

    Callers that need to know whether a setting reaches the provider at all —
    the settings probe, so it does not spend a request asking about one that
    cannot — read it from here rather than keeping their own idea of it.
    """
    return _PROVIDER_KEYS.get(protocol, {})


def _mapped_runtime_kwargs(protocol: str, common: dict[str, Any]) -> dict[str, Any]:
    """The settings this protocol carries, under the names it carries them."""
    return {
        provider_key: common[setting]
        for setting, provider_key in provider_request_keys(protocol).items()
        if common.get(setting) is not None and common.get(setting) != []
    }


def _apply_profiles(route: ResolvedRoute, kwargs: dict[str, Any]) -> dict[str, Any]:
    return apply_provider_profile_layers(
        route_provider_profile_keys(route),
        route=route,
        **{key: value for key, value in kwargs.items() if value is not None},
    )


class OpenAICompatibleChatModel(ChatOpenAI):
    """ChatOpenAI, plus the reasoning field openai-compatible providers add.

    A provider that reasons reports it in ``reasoning_content`` next to an empty
    ``content`` — its way of saying this part is not the reply. That field is
    not part of OpenAI's own schema, so the base class drops it while converting
    a stream chunk, and everything downstream sees a model that never reasoned
    (measured 2026-08-09: api.deepseek.com sent 147 characters of reasoning on a
    plain call, and the converted chunk carried an empty ``additional_kwargs``).

    Only the streaming seam is covered because the gateway only streams — see
    ``_dispatch``'s "always stream(), never invoke()". A blocking path added
    later would need its own passthrough rather than inheriting one that was
    never exercised.
    """

    def _convert_chunk_to_generation_chunk(
        self,
        chunk: dict[str, Any],
        default_chunk_class: type,
        base_generation_info: dict[str, Any] | None,
    ) -> Any:
        generation = super()._convert_chunk_to_generation_chunk(
            chunk,
            default_chunk_class,
            base_generation_info,
        )
        if generation is None:
            return None
        reasoning = _streamed_reasoning_content(chunk)
        if reasoning:
            generation.message.additional_kwargs["reasoning_content"] = reasoning
        return generation


def _streamed_reasoning_content(chunk: Mapping[str, Any]) -> str:
    """This slice's reasoning, or empty when the provider sent none.

    Absent and empty are kept apart on purpose: a reader that treated a missing
    field as "reasoned, said nothing" would report a thinking step for every
    plain answer.
    """
    choices = chunk.get("choices")
    if not isinstance(choices, list) or not choices:
        return ""
    first = choices[0]
    delta = first.get("delta") if isinstance(first, Mapping) else None
    reasoning = delta.get("reasoning_content") if isinstance(delta, Mapping) else None
    return reasoning if isinstance(reasoning, str) else ""


class PatchedChatDeepSeek(OpenAICompatibleChatModel):
    """DeepSeek over the openai-compatible protocol, with reasoning replayed.

    Replaying is a DeepSeek requirement rather than a shared convention: a
    multi-turn request has to carry back the reasoning of earlier assistant
    turns, which is the reverse direction from the passthrough above.
    """

    def _get_request_payload(
        self,
        input_: LanguageModelInput,
        *,
        stop: list[str] | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        messages = self._convert_input(input_).to_messages()
        payload = cast(
            dict[str, Any],
            super()._get_request_payload(input_, stop=stop, **kwargs),
        )
        _replay_assistant_reasoning_content(payload, messages)
        return payload


def _replay_assistant_reasoning_content(
    payload: dict[str, Any],
    messages: Sequence[BaseMessage],
) -> None:
    payload_messages = payload.get("messages")
    if not isinstance(payload_messages, list):
        return

    assistant_reasoning = [
        message.additional_kwargs.get("reasoning_content")
        for message in messages
        if isinstance(message, AIMessage)
    ]
    if not assistant_reasoning:
        return

    assistant_index = 0
    for payload_message in payload_messages:
        if not isinstance(payload_message, dict) or payload_message.get("role") != "assistant":
            continue
        if assistant_index >= len(assistant_reasoning):
            break
        reasoning = assistant_reasoning[assistant_index]
        assistant_index += 1
        if reasoning and "reasoning_content" not in payload_message:
            payload_message["reasoning_content"] = reasoning


def _is_deepseek_route(route: ResolvedRoute) -> bool:
    identity = " ".join(
        (
            route.route_id,
            route.endpoint_id,
            route.provider_model_id,
            route.canonical_id,
        )
    ).lower()
    return "deepseek" in identity


def _resolve_api_key(route: ResolvedRoute, credential_provider: Any) -> str:
    if credential_provider is None:
        raise ValueError(f"credential_provider is required for route {route.route_id}")
    try:
        secret = credential_provider.get(route.credential_ref)
    except Exception as exc:
        raise CredentialResolveError(
            error_code="credential.vault_unreachable",
            error_payload={"credential_ref": route.credential_ref},
        ) from exc
    if isinstance(secret, SecretStr):
        return secret.get_secret_value()
    return str(secret)


def _import_google_chat_module() -> Any:
    try:
        return importlib.import_module("langchain_google_genai")
    except ImportError as exc:
        raise ImportError(
            "google_genai routes require the graph-agent-gateway[google] optional "
            "extra, which installs langchain-google-genai"
        ) from exc
