"""Model resolver that maps configured roles to the Phase 4 gateway adapter.

The resolver's job is now intentionally narrow: read ``llm_roles.yaml``,
expand role/model/provider fallback metadata, and return a LangChain-compatible
``GatewayChatModel``.  Network health, probing, provider mark-down, token
accounting, and real fallback events belong to ``LLMClientManager`` and the
gateway runtime call loop, not to model construction.
"""

from __future__ import annotations

import logging
import os
import threading
from dataclasses import dataclass, replace
from typing import Any

from langchain_core.language_models.chat_models import BaseChatModel

from ..callbacks.base import Callback
from ..config.llm_config import (
    ResolvedProvider,
    ResolvedRole,
    RoleConfigData,
    get_role_config,
)
from .gateway_chat_model import GatewayChatModel
from .llm_client_manager import LLMClientManager

logger = logging.getLogger(__name__)


@dataclass
class ModelResolverStats:
    """Runtime statistics for resolver calls."""

    total_resolves: int = 0
    cache_hits: int = 0
    provider_failures: int = 0
    circuit_breaks: int = 0


class ModelResolver:
    """Resolve role names to ``GatewayChatModel`` instances.

    The returned object still satisfies LangChain's ``BaseChatModel`` contract
    for the existing agent loop.  Provider selection and failover happen inside
    ``GatewayChatModel._generate`` so observability reflects real runtime
    failures instead of predicted fallback chains.
    """

    def __init__(self) -> None:
        """Initialize runtime counters."""
        self._stats_lock = threading.Lock()
        self.stats = ModelResolverStats()

    def resolve(
        self,
        role_name: str | None = None,
        *,
        thinking_enabled: bool | None = None,
        model_override: str | None = None,
        callbacks: tuple[Callback, ...] = (),
        phase_name: str | None = None,
        **kwargs: Any,
    ) -> BaseChatModel:
        """Resolve a role or model override to a LangChain-compatible gateway."""
        self._bump_stat("total_resolves")

        cfg = get_role_config()
        resolved = self._resolve_configured_role(
            cfg,
            role_name,
            model_override=model_override,
        )
        if resolved is None:
            logger.info(
                "[ModelResolver] Role '%s' not in llm_roles.yaml, delegating to minimal factory",
                role_name,
            )
            return self._fallback_to_minimal_factory(role_name, thinking_enabled, **kwargs)

        effective_role_name = resolved.role_name
        resolved = self._append_peer_model_fallbacks(
            cfg=cfg,
            resolved=resolved,
            original_role_name=role_name or effective_role_name,
            model_override=model_override,
        )
        if not resolved.call_chain:
            from ..core.exceptions import AllProvidersFailedError

            raise AllProvidersFailedError(effective_role_name, [])

        logger.info(
            "[ModelResolver] Gateway role=%s chain=%s",
            effective_role_name,
            " -> ".join(_candidate_id(rp) for rp in resolved.call_chain),
        )
        return GatewayChatModel(
            effective_role_name,
            resolved,
            max_tokens=_default_max_tokens(resolved.call_chain),
            temperature=resolved.temperature,
            callbacks=callbacks,
            phase_name=phase_name,
            thinking_enabled=thinking_enabled,
            name=_display_model_name(resolved),
            profile=_profile_for_chain(resolved.call_chain),
        )

    def mark_provider_down(self, provider_code: str, model_name: str) -> None:
        """Manually mark a provider/model down in the shared gateway cache."""
        LLMClientManager._mark_provider_down(provider_code, model_name)

    def _resolve_configured_role(
        self,
        cfg: RoleConfigData,
        role_name: str | None,
        *,
        model_override: str | None,
    ) -> ResolvedRole | None:
        if model_override:
            try:
                resolved = cfg.resolve_model(model_override)
            except KeyError:
                logger.warning(
                    "[ModelResolver] model_override '%s' not in llm_roles.yaml models: section; "
                    "falling back to role-based resolution for '%s'",
                    model_override,
                    role_name or "<default>",
                )
            else:
                logger.info(
                    "[ModelResolver] model_override=%s -> chain=%s",
                    model_override,
                    " | ".join(_candidate_id(rp) for rp in resolved.call_chain),
                )
                return resolved

        effective_role = role_name or self._get_default_role_name()
        try:
            return cfg.resolve_role(effective_role)
        except KeyError:
            return None

    def _append_peer_model_fallbacks(
        self,
        *,
        cfg: RoleConfigData,
        resolved: ResolvedRole,
        original_role_name: str,
        model_override: str | None,
    ) -> ResolvedRole:
        if (
            model_override is not None
            or original_role_name in cfg.single_model_roles
            or not cfg.peer_model_groups
        ):
            return resolved

        peer_codes = _peer_model_codes(cfg, resolved.active_model_code)
        if not peer_codes:
            return resolved

        logger.info(
            "[ModelResolver] peer fallback candidates for role=%s (active=%s): %s",
            original_role_name,
            resolved.active_model_code,
            peer_codes,
        )
        already_seen = {
            (rp.provider_code, rp.model_name)
            for rp in resolved.call_chain
        }
        extras: list[ResolvedProvider] = []
        for code in peer_codes:
            try:
                peer_resolved = cfg.resolve_model(code)
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "[ModelResolver] peer model %s resolution failed: %s",
                    code,
                    exc,
                )
                continue

            for rp in peer_resolved.call_chain:
                key = (rp.provider_code, rp.model_name)
                if key in already_seen:
                    continue
                extras.append(rp)
                already_seen.add(key)

        if not extras:
            return resolved
        return replace(
            resolved,
            call_chain=[*resolved.call_chain, *extras],
            model_fallback=True,
        )

    def _get_default_role_name(self) -> str:
        """Return the default role name when the caller does not provide one."""
        return os.environ.get("GRAPH_AGENT_DEFAULT_ROLE", "balanced")

    def _fallback_to_minimal_factory(
        self,
        name: str | None,
        thinking_enabled: bool | None,
        **kwargs: Any,
    ) -> BaseChatModel:
        """Call the local minimal chat model factory for explicit ad-hoc roles."""
        from .factory import create_chat_model

        effective_thinking = False if thinking_enabled is None else thinking_enabled
        model_name = kwargs.pop("model", None) or name
        model = create_chat_model(
            model=model_name,
            thinking_enabled=effective_thinking,
            **kwargs,
        )
        logger.info("[ModelResolver] minimal factory resolved: %s", model_name)
        return model

    def _bump_stat(self, field_name: str, amount: int = 1) -> None:
        """Increment runtime stats under lock for concurrent safety."""
        with self._stats_lock:
            current = getattr(self.stats, field_name)
            setattr(self.stats, field_name, current + amount)


def _peer_model_codes(cfg: RoleConfigData, active_model_code: str) -> list[str]:
    peer_codes: list[str] = []
    for group_codes in cfg.peer_model_groups.values():
        if active_model_code not in group_codes:
            continue
        for code in group_codes:
            if code != active_model_code and code not in peer_codes:
                peer_codes.append(code)
    return peer_codes


def _candidate_id(rp: ResolvedProvider) -> str:
    return f"{rp.provider_code}/{rp.model_name}"


def _default_max_tokens(call_chain: list[ResolvedProvider]) -> int:
    primary = call_chain[0]
    provider_cap = primary.provider_options.get("max_max_tokens")
    if isinstance(provider_cap, int) and provider_cap > 0:
        return provider_cap
    return primary.model_def.min_max_tokens


def _display_model_name(resolved: ResolvedRole) -> str:
    first = resolved.call_chain[0]
    return _candidate_id(first)


def _profile_for_chain(call_chain: list[ResolvedProvider]) -> dict[str, int] | None:
    for rp in call_chain:
        if rp.model_def.max_input_tokens is not None:
            return {"max_input_tokens": rp.model_def.max_input_tokens}
    return None


_resolver: ModelResolver | None = None
_resolver_lock = threading.Lock()


def get_model_resolver() -> ModelResolver:
    """Get or create the singleton ModelResolver instance."""
    global _resolver
    if _resolver is not None:
        return _resolver
    with _resolver_lock:
        if _resolver is None:
            _resolver = ModelResolver()
        return _resolver


def reset_model_resolver() -> None:
    """Reset the singleton for tests."""
    global _resolver
    with _resolver_lock:
        _resolver = None
