"""What a route has cost, and whether it is currently marked down."""

from __future__ import annotations

import logging
import time
from collections.abc import Mapping
from typing import ClassVar

from graph_agent_gateway.registry import ResolvedRoute, RuntimePolicy

logger = logging.getLogger(__name__)

UsageStats = dict[str, int]


class LLMCircuitAndUsageLedger:
    """The two facts about a route that outlive any single call.

    Nothing here builds or holds a provider client — every call goes out
    through a LangChain model from `RouteChatModelFactory`. What is left is the
    down-TTL a fallback consults before trying a route again, and the
    per-endpoint usage counters. Both are process-wide on purpose: they belong
    to no single harness and must survive one being torn down.
    """

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
__all__ = ["LLMCircuitAndUsageLedger"]
