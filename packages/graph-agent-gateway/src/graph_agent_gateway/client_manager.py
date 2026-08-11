"""Native SDK client manager for route-backed gateway runtime."""

from __future__ import annotations

import importlib
import logging
import time
from collections.abc import Mapping
from typing import Any, ClassVar, cast

import httpx
from anthropic import Anthropic
from openai import OpenAI
from pydantic import SecretStr

from graph_agent_gateway.registry import CredentialProviderProtocol, ResolvedRoute, RuntimePolicy

logger = logging.getLogger(__name__)

UsageStats = dict[str, int]


class LLMClientManager:
    """Shared native-SDK client cache and provider call helpers.

    The class attributes intentionally live for the process lifetime:
    SDK clients own HTTP connection pools, while usage stats and
    provider-down TTL state are global infrastructure concerns rather
    than per-harness runtime state.
    """

    _clients: ClassVar[dict[str, Any]] = {}
    _usage_stats: ClassVar[dict[str, UsageStats]] = {}
    _provider_down_cache: ClassVar[dict[str, float]] = {}

    # WS-1 moved provider invocation to RouteChatModelFactory + ChatX invoke.
    # Generic ordinary-chat dispatch now lives in graph_agent_gateway.ordinary_chat.

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
        credential_provider: CredentialProviderProtocol | None = None,
    ) -> OpenAI:
        """Return a cached OpenAI-compatible client for one route endpoint."""
        policy = runtime_policy or RuntimePolicy()
        timeout_value = float(timeout_override or route.timeout_seconds)
        cache_key = cls._client_cache_key("openai", route, timeout_value, policy)

        cached = cls._clients.get(cache_key)
        if cached is not None:
            return cast(OpenAI, cached)

        api_key = cls._resolve_api_key(route, credential_provider=credential_provider)
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
            "phase=llm_client_manager action=create_client type=openai "
            "endpoint=%s route=%s base_url=%s",
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
        credential_provider: CredentialProviderProtocol | None = None,
    ) -> Anthropic:
        """Return a cached Anthropic-compatible client for one route endpoint."""
        policy = runtime_policy or RuntimePolicy()
        cache_key = cls._client_cache_key("anthropic", route, float(route.timeout_seconds), policy)
        cached = cls._clients.get(cache_key)
        if cached is not None:
            return cast(Anthropic, cached)

        client = Anthropic(
            api_key=cls._resolve_api_key(route, credential_provider=credential_provider),
            base_url=route.base_url or None,
            timeout=float(route.timeout_seconds),
            max_retries=0,
        )
        cls._clients[cache_key] = client
        cls._init_usage_stats(route.endpoint_id)
        logger.info(
            "phase=llm_client_manager action=create_client type=anthropic "
            "endpoint=%s route=%s base_url=%s",
            route.endpoint_id,
            route.route_id,
            route.base_url or "<default>",
        )
        return client

    @classmethod
    def _get_google_client(
        cls,
        route: ResolvedRoute,
        *,
        runtime_policy: RuntimePolicy | None = None,
        credential_provider: CredentialProviderProtocol | None = None,
    ) -> object:
        """Return a cached google-genai client for one route endpoint."""
        policy = runtime_policy or RuntimePolicy()
        cache_key = cls._client_cache_key("google", route, float(route.timeout_seconds), policy)
        cached = cls._clients.get(cache_key)
        if cached is not None:
            return cached

        try:
            genai = importlib.import_module("google.genai")
        except ImportError as exc:  # pragma: no cover - depends on optional SDK install
            raise RuntimeError(
                "google-genai SDK is not installed; install google-genai to use google_genai routes"
            ) from exc

        kwargs: dict[str, object] = {
            "api_key": cls._resolve_api_key(route, credential_provider=credential_provider)
        }
        if route.base_url:
            kwargs["http_options"] = {"base_url": route.base_url}
        client = genai.Client(**kwargs)
        cls._clients[cache_key] = client
        cls._init_usage_stats(route.endpoint_id)
        logger.info(
            "phase=llm_client_manager action=create_client type=google "
            "endpoint=%s route=%s base_url=%s",
            route.endpoint_id,
            route.route_id,
            route.base_url or "<default>",
        )
        return client

    @classmethod
    def _get_ark_client(
        cls,
        route: ResolvedRoute,
        *,
        runtime_policy: RuntimePolicy | None = None,
        credential_provider: CredentialProviderProtocol | None = None,
    ) -> object:
        """Return a cached Volcengine Ark official SDK client for one endpoint."""
        policy = runtime_policy or RuntimePolicy()
        cache_key = cls._client_cache_key("ark", route, float(route.timeout_seconds), policy)
        cached = cls._clients.get(cache_key)
        if cached is not None:
            return cached

        try:
            ark_module = importlib.import_module("volcenginesdkarkruntime")
        except ImportError as exc:  # pragma: no cover - depends on optional SDK install
            raise RuntimeError(
                "Volcengine Ark SDK is not installed; install graph-agent-gateway[ark] "
                "to use ark_runtime routes"
            ) from exc

        kwargs: dict[str, object] = {
            "api_key": cls._resolve_api_key(route, credential_provider=credential_provider)
        }
        if route.base_url:
            kwargs["base_url"] = route.base_url
        client = ark_module.Ark(**kwargs)
        cls._clients[cache_key] = client
        cls._init_usage_stats(route.endpoint_id)
        logger.info(
            "phase=llm_client_manager action=create_client type=ark "
            "endpoint=%s route=%s base_url=%s",
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
    def _resolve_api_key(
        cls,
        route: ResolvedRoute,
        *,
        credential_provider: CredentialProviderProtocol | None = None,
    ) -> str:
        if not route.credential_ref:
            raise ValueError(f"route has no credential_ref: {route.route_id}")
        if credential_provider is None:
            raise ValueError(
                "CredentialProvider integration is required for credential_ref: "
                f"{route.credential_ref}"
            )
        try:
            secret = credential_provider.get(route.credential_ref)
        except Exception as exc:
            raise ValueError(f"credential is unavailable: {route.credential_ref}") from exc
        api_key = secret.get_secret_value() if isinstance(secret, SecretStr) else str(secret)
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
            f"token_escalation:{runtime_policy.token_escalation_rounds}:"
            f"terminal_retry_enabled:{runtime_policy.terminal_retry_enabled}:"
            f"terminal_retry:{runtime_policy.terminal_retry_policy.model_dump_json()}:"
            f"secret_lifetime:{runtime_policy.secret_lifetime_policy.model_dump_json()}"
        )

__all__ = ["LLMClientManager"]
