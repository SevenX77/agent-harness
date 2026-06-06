"""Build LangChain ChatX models from resolved gateway routes."""

from __future__ import annotations

import importlib
from typing import Any, cast

from langchain_anthropic import ChatAnthropic
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_openai import ChatOpenAI
from pydantic import SecretStr

from graph_agent_gateway.models import GenericRouteChatModel
from graph_agent_gateway.provider_profiles import apply_provider_profile
from graph_agent_gateway.registry.base_url import canonicalize_base_url
from graph_agent_gateway.registry.schema import ResolvedRoute


class RouteChatModelFactory:
    """Construct a provider ChatX model for one resolved route."""

    def __init__(self, *, credential_provider: Any = None) -> None:
        self.credential_provider = credential_provider

    def build(self, route: ResolvedRoute, **caller_kwargs: Any) -> BaseChatModel:
        protocol = str(route.protocol)
        base_url = canonicalize_base_url(route.base_url, protocol)
        api_key = _resolve_api_key(route, self.credential_provider)
        common = _runtime_kwargs(route, caller_kwargs)

        if protocol in {"openai_compatible", "ark_runtime"}:
            kwargs = {
                "model": route.provider_model_id,
                "api_key": api_key,
                "base_url": base_url,
                "timeout": route.timeout_seconds,
                "stream_usage": True,
                **_openai_runtime_kwargs(common),
            }
            return ChatOpenAI(**_apply_profiles(route, kwargs))

        if protocol == "anthropic_compatible":
            kwargs = {
                "model": route.provider_model_id,
                "api_key": api_key,
                "base_url": base_url,
                "timeout": route.timeout_seconds,
                **_anthropic_runtime_kwargs(common),
            }
            return ChatAnthropic(**_apply_profiles(route, kwargs))

        if protocol == "google_genai":
            google_module = _import_google_chat_module()
            chat_google = google_module.ChatGoogleGenerativeAI
            kwargs = {
                "model": route.provider_model_id,
                "google_api_key": api_key,
                "timeout": route.timeout_seconds,
                **_google_runtime_kwargs(common),
            }
            return cast(BaseChatModel, chat_google(**_apply_profiles(route, kwargs)))

        return GenericRouteChatModel(route=route, credential_provider=self.credential_provider)


def _runtime_kwargs(route: ResolvedRoute, caller_kwargs: dict[str, Any]) -> dict[str, Any]:
    return {
        "temperature": _caller_or_effective(caller_kwargs, route, "temperature"),
        "max_tokens": _caller_or_effective(caller_kwargs, route, "max_tokens", "max_output_tokens"),
        "top_p": _caller_or_effective(caller_kwargs, route, "top_p"),
        "stop_sequences": caller_kwargs.get("stop_sequences")
        or _effective_value(route, "stop_sequences"),
        "seed": _caller_or_effective(caller_kwargs, route, "seed"),
        "reasoning_effort": _caller_or_effective(caller_kwargs, route, "reasoning_effort"),
    }


def _caller_or_effective(
    caller_kwargs: dict[str, Any],
    route: ResolvedRoute,
    caller_key: str,
    effective_key: str | None = None,
) -> Any:
    value = caller_kwargs.get(caller_key)
    if value is not None:
        return value
    return _effective_value(route, effective_key or caller_key)


def _effective_value(route: ResolvedRoute, key: str) -> Any:
    setting = route.effective_runtime_settings.get(key)
    return setting.value if setting is not None else None


def _openai_runtime_kwargs(common: dict[str, Any]) -> dict[str, Any]:
    kwargs: dict[str, Any] = {}
    if common.get("temperature") is not None:
        kwargs["temperature"] = common["temperature"]
    if common.get("max_tokens") is not None:
        kwargs["max_completion_tokens"] = common["max_tokens"]
    if common.get("top_p") is not None:
        kwargs["top_p"] = common["top_p"]
    if common.get("seed") is not None:
        kwargs["seed"] = common["seed"]
    if common.get("stop_sequences"):
        kwargs["stop"] = common["stop_sequences"]
    if common.get("reasoning_effort") is not None:
        kwargs["reasoning_effort"] = common["reasoning_effort"]
    return kwargs


def _anthropic_runtime_kwargs(common: dict[str, Any]) -> dict[str, Any]:
    kwargs: dict[str, Any] = {}
    if common.get("temperature") is not None:
        kwargs["temperature"] = common["temperature"]
    if common.get("max_tokens") is not None:
        kwargs["max_tokens"] = common["max_tokens"]
    if common.get("top_p") is not None:
        kwargs["top_p"] = common["top_p"]
    if common.get("stop_sequences"):
        kwargs["stop_sequences"] = common["stop_sequences"]
    return kwargs


def _google_runtime_kwargs(common: dict[str, Any]) -> dict[str, Any]:
    kwargs: dict[str, Any] = {}
    if common.get("temperature") is not None:
        kwargs["temperature"] = common["temperature"]
    if common.get("max_tokens") is not None:
        kwargs["max_tokens"] = common["max_tokens"]
    if common.get("top_p") is not None:
        kwargs["top_p"] = common["top_p"]
    if common.get("stop_sequences"):
        kwargs["stop"] = common["stop_sequences"]
    return kwargs


def _apply_profiles(route: ResolvedRoute, kwargs: dict[str, Any]) -> dict[str, Any]:
    return apply_provider_profile(
        f"{route.endpoint_id}:{route.provider_model_id}",
        route=route,
        **{key: value for key, value in kwargs.items() if value is not None},
    )


def _resolve_api_key(route: ResolvedRoute, credential_provider: Any) -> str:
    if credential_provider is None:
        raise ValueError(f"credential_provider is required for route {route.route_id}")
    secret = credential_provider.get(route.credential_ref)
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
