"""Model Resolver — role-based model selection with provider failover.

Reads config/llm_roles.yaml, resolves role → model → provider chain,
and returns LangChain BaseChatModel instances for DeerFlow's create_agent.

Migrated from LLMGateway's circuit-breaking logic, adapted to output
BaseChatModel instead of raw API responses.
"""
from __future__ import annotations

import logging
import os
import re
import threading
import time
from dataclasses import dataclass

import httpx
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_openai import ChatOpenAI
from openai import APIConnectionError, APITimeoutError, BadRequestError, InternalServerError

try:
    from anthropic import InternalServerError as AnthropicInternalServerError
    from anthropic import APIConnectionError as AnthropicAPIConnectionError
    from anthropic import APITimeoutError as AnthropicAPITimeoutError
except ImportError:
    AnthropicInternalServerError = None  # type: ignore[assignment,misc]
    AnthropicAPIConnectionError = None  # type: ignore[assignment,misc]
    AnthropicAPITimeoutError = None  # type: ignore[assignment,misc]

from ..config.llm_config import (
    ResolvedProvider,
    get_role_config,
)
from .reasoning_patch import _apply_reasoning_content_patch

logger = logging.getLogger(__name__)

# ── Constants ────────────────────────────────────────────────────────────────

_PROBE_DOWN_TTL: float = 1800.0  # 30 min cool-down
_WS_HTTP_5XX_RE = re.compile(r"HTTP\s+50[234]")
_PROVIDER_CALL_RETRIES = 2
_RUNTIME_FAILOVER_EXCEPTIONS_LIST = [
    httpx.TimeoutException,
    httpx.ConnectError,
    httpx.RemoteProtocolError,
    ConnectionError,
    APIConnectionError,
    APITimeoutError,
    InternalServerError,
    BadRequestError,   # e.g. OC_GM returning 400 "upstream_error" — treat as provider failure
    RuntimeError,  # e.g. provider wrappers returning plain "HTTP 502..." runtime errors
]
# Also include Anthropic SDK exceptions if available (anthropic != openai exception hierarchy)
if AnthropicInternalServerError is not None:
    _RUNTIME_FAILOVER_EXCEPTIONS_LIST.append(AnthropicInternalServerError)
if AnthropicAPIConnectionError is not None:
    _RUNTIME_FAILOVER_EXCEPTIONS_LIST.append(AnthropicAPIConnectionError)
if AnthropicAPITimeoutError is not None:
    _RUNTIME_FAILOVER_EXCEPTIONS_LIST.append(AnthropicAPITimeoutError)
_RUNTIME_FAILOVER_EXCEPTIONS = tuple(_RUNTIME_FAILOVER_EXCEPTIONS_LIST)


def _is_network_failure(exc: Exception) -> bool:
    """Return True if exc indicates a network/gateway failure worth circuit-breaking."""
    if isinstance(exc, (httpx.TimeoutException, httpx.ConnectError, httpx.RemoteProtocolError)):
        return True
    if isinstance(exc, ConnectionError):
        return True
    status_code = getattr(exc, "status_code", None)
    if isinstance(status_code, int) and status_code in {500, 502, 503, 504}:  # All server errors
        return True
    if isinstance(exc, RuntimeError) and _WS_HTTP_5XX_RE.search(str(exc)):
        return True
    return False


# ── ModelResolver ────────────────────────────────────────────────────────────


@dataclass
class ModelResolverStats:
    """Runtime statistics for observability."""

    total_resolves: int = 0
    cache_hits: int = 0
    provider_failures: int = 0
    circuit_breaks: int = 0


class ModelResolver:
    """Resolve role names to LangChain BaseChatModel instances.

    Reads config/llm_roles.yaml and creates ChatOpenAI instances with
    the correct provider credentials. Includes circuit breaking, probe,
    and timeout escalation from the original LLMGateway.

    Usage::

        resolver = ModelResolver()
        model = resolver.resolve("premium", thinking_enabled=True)
        # Returns a ChatOpenAI instance ready for create_agent(model=...)
    """

    def __init__(self) -> None:
        """Initialize provider caches and runtime counters."""
        self._provider_down_cache: dict[str, float] = {}
        self._cache_lock = threading.Lock()
        self._stats_lock = threading.Lock()
        self.stats = ModelResolverStats()

    # ── Public API ────────────────────────────────────────────────────────

    def resolve(
        self,
        role_name: str | None = None,
        *,
        thinking_enabled: bool | None = None,
        **kwargs,
    ) -> BaseChatModel:
        """Resolve a role name to a BaseChatModel instance.

        This is the hook function registered with DeerFlow's
        set_model_resolver_hook(). All DeerFlow model creation calls
        (Phase agents, summarization, memory, title) flow through here.

        Args:
            role_name: Role name from llm_roles.yaml (e.g. "premium", "fast").
                If None, reads DeerFlow config's default model alias and then
                resolves that alias through ``llm_roles.yaml`` or DeerFlow native fallback.
            thinking_enabled: Whether to enable thinking/reasoning mode.
                None = auto-detect from the selected model's ``reasoning`` flag.
                True = force enable reasoning mode when the provider supports it.
                False = force disable reasoning mode even for reasoning models.
            **kwargs: Additional kwargs (passed through but mostly ignored
                because ModelResolver creates its own LangChain model instances.

        Returns:
            A configured BaseChatModel instance, potentially wrapped with runtime
            fallbacks when more than one provider candidate is available.

        Raises:
            AllProvidersFailedError: When all providers in the role fail.

        """
        self._bump_stat("total_resolves")

        if role_name is None:
            role_name = self._get_deerflow_default_name()

        cfg = get_role_config()
        try:
            resolved = cfg.resolve_role(role_name)
        except KeyError:
            logger.info(
                "[ModelResolver] Role '%s' not in llm_roles.yaml, delegating to DeerFlow native",
                role_name,
            )
            return self._fallback_to_deerflow_native(role_name, thinking_enabled, **kwargs)

        errors: list[tuple[str, Exception]] = []
        model_chain: list[tuple[str, str, BaseChatModel]] = []

        for rp in resolved.call_chain:
            cid = f"{rp.provider_code}/{rp.model_name}"

            # Skip providers in down-cache
            if self._is_provider_down(rp.provider_code, rp.model_name):
                self._bump_stat("cache_hits")
                errors.append((cid, RuntimeError("Provider marked down")))
                continue

            # Only probe openai_compatible (ChatOpenAI handles its own errors)
            # Skip probe for now — let ChatOpenAI fail fast on first use
            # Probing adds latency and the model might work fine

            try:
                model = self._create_langchain_model(
                    rp, resolved.temperature, thinking_enabled
                )
                logger.info(
                    "[ModelResolver] Candidate role=%s → %s (thinking=%s)",
                    role_name, cid, thinking_enabled,
                )
                model_chain.append((rp.provider_code, rp.model_name, model))
            except Exception as exc:
                logger.warning("[ModelResolver] %s creation failed: %s", cid, exc)
                if _is_network_failure(exc):
                    self._mark_provider_down(rp.provider_code, rp.model_name)
                    self._bump_stat("circuit_breaks")
                self._bump_stat("provider_failures")
                errors.append((cid, exc))

        if model_chain:
            primary_provider, primary_model, primary = model_chain[0]
            fallback_models = [entry[2] for entry in model_chain[1:]]
            if fallback_models:
                logger.info(
                    "[ModelResolver] Runtime fallback chain for role=%s: %s",
                    role_name,
                    " -> ".join(f"{p}/{m}" for p, m, _ in model_chain),
                )
                return primary.with_fallbacks(
                    fallback_models,
                    exceptions_to_handle=_RUNTIME_FAILOVER_EXCEPTIONS,
                )
            logger.info(
                "[ModelResolver] Resolved role=%s → %s/%s (single provider)",
                role_name,
                primary_provider,
                primary_model,
            )
            return primary

        from ..core.exceptions import AllProvidersFailedError
        raise AllProvidersFailedError(role_name, errors)

    def mark_provider_down(self, provider_code: str, model_name: str) -> None:
        """Manually mark a provider as down (called by harness on runtime failure)."""
        self._mark_provider_down(provider_code, model_name)

    # ── DeerFlow integration ─────────────────────────────────────────────

    def _get_deerflow_default_name(self) -> str:
        """读取 DeerFlow config 中第一个模型的名称作为默认值."""
        try:
            from deerflow.config import get_app_config
            config = get_app_config()
            if config.models:
                return config.models[0].name
        except Exception as exc:
            logger.warning("[ModelResolver] Cannot read DeerFlow default: %s", exc)
        return "deerflow_default"  # 最终兜底

    def _fallback_to_deerflow_native(
        self,
        name: str | None,
        thinking_enabled: bool | None,
        **kwargs,
    ) -> BaseChatModel:
        """Call DeerFlow native create_chat_model bypassing the hook.

        Uses the _bypass_hook parameter instead of toggling global state,
        which is thread-safe for concurrent callers.
        """
        from deerflow.models.factory import create_chat_model
        effective_thinking = False if thinking_enabled is None else thinking_enabled
        model = create_chat_model(
            name=name,
            thinking_enabled=effective_thinking,
            _bypass_hook=True,
            **kwargs,
        )
        logger.info("[ModelResolver] DeerFlow native resolved: %s", name)
        return model

    # ── Model creation ────────────────────────────────────────────────────

    def _create_langchain_model(
        self,
        rp: ResolvedProvider,
        temperature: float,
        thinking_enabled: bool | None,
    ) -> BaseChatModel:
        """Create a LangChain BaseChatModel from a resolved provider."""
        pdef = rp.provider_def

        if pdef.type in ("openai_compatible", "wavespeed_any_llm"):
            return self._create_openai_compatible(rp, temperature, thinking_enabled)

        if pdef.type == "anthropic_compatible":
            return self._create_anthropic_compatible(rp, temperature, thinking_enabled)

        if pdef.type == "gemini_official":
            if thinking_enabled:
                logger.warning(
                    "thinking_enabled=True requested for Gemini provider '%s', "
                    "but ChatGoogleGenerativeAI does not support thinking mode — ignoring",
                    pdef.code,
                )
            return self._create_gemini_official(rp, temperature)

        raise ValueError(f"Unknown provider type: {pdef.type}")

    def _create_openai_compatible(
        self,
        rp: ResolvedProvider,
        temperature: float,
        thinking_enabled: bool | None,
    ) -> ChatOpenAI:
        """Create ChatOpenAI for openai_compatible and wavespeed providers."""
        _apply_reasoning_content_patch()
        pdef = rp.provider_def

        api_key = os.getenv(pdef.api_key_env)
        if not api_key and pdef.api_key_env_fallback:
            api_key = os.getenv(pdef.api_key_env_fallback)
        if not api_key:
            raise ValueError(f"API key not configured: {pdef.api_key_env}")

        # For wavespeed, use llm_base_url (OpenAI-compatible endpoint)
        base_url = pdef.base_url
        if pdef.type == "wavespeed_any_llm" and pdef.llm_base_url:
            base_url = pdef.llm_base_url

        # Get max_tokens from provider_options or model defaults
        max_tokens = rp.provider_options.get(
            "max_max_tokens", rp.model_def.min_max_tokens
        )

        kwargs: dict = {
            "model": rp.model_name,
            "base_url": base_url,
            "api_key": api_key,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "timeout": float(pdef.timeout),
            "max_retries": _PROVIDER_CALL_RETRIES,
        }

        # Thinking mode: auto-enable when model supports reasoning,
        # unless caller explicitly passes thinking_enabled=False.
        should_think = thinking_enabled if thinking_enabled is not None else rp.model_def.reasoning
        if should_think and rp.model_def.reasoning:
            kwargs["extra_body"] = {"thinking": {"type": "enabled"}}
            kwargs["temperature"] = 1.0

        return ChatOpenAI(**kwargs)

    def _create_anthropic_compatible(
        self,
        rp: ResolvedProvider,
        temperature: float,
        thinking_enabled: bool | None,
    ) -> BaseChatModel:
        """Create ChatAnthropic for anthropic-native endpoints (/v1/messages).

        Uses langchain_anthropic which natively supports thinking blocks,
        tool_use, and the Anthropic message format.
        """
        try:
            from langchain_anthropic import ChatAnthropic
        except ImportError:
            raise ImportError(
                "langchain_anthropic is required for anthropic_compatible providers. "
                "Install: pip install langchain-anthropic"
            )

        pdef = rp.provider_def
        api_key = os.getenv(pdef.api_key_env)
        if not api_key and pdef.api_key_env_fallback:
            api_key = os.getenv(pdef.api_key_env_fallback)
        if not api_key:
            raise ValueError(f"API key not configured: {pdef.api_key_env}")

        max_tokens = rp.provider_options.get(
            "max_max_tokens", rp.model_def.min_max_tokens
        )

        should_think = thinking_enabled if thinking_enabled is not None else rp.model_def.reasoning
        thinking_cfg = None
        if should_think and rp.model_def.reasoning:
            thinking_cfg = {"type": "enabled", "budget_tokens": max(1024, max_tokens // 2)}
            temperature = 1.0  # Anthropic requires temperature=1 when thinking is enabled

        kwargs: dict = {
            "model": rp.model_name,
            "api_key": api_key,
            "base_url": pdef.base_url or None,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "timeout": float(pdef.timeout),
            "max_retries": _PROVIDER_CALL_RETRIES,
        }
        if thinking_cfg:
            kwargs["thinking"] = thinking_cfg

        return ChatAnthropic(**kwargs)

    def _create_gemini_official(
        self,
        rp: ResolvedProvider,
        temperature: float,
    ) -> BaseChatModel:
        """Create a Gemini model via langchain_google_genai."""
        pdef = rp.provider_def
        api_key = os.getenv(pdef.api_key_env)
        if not api_key:
            raise ValueError(f"API key not configured: {pdef.api_key_env}")

        try:
            from langchain_google_genai import ChatGoogleGenerativeAI
        except ImportError:
            raise ImportError(
                "langchain_google_genai not installed. "
                "Install with: pip install langchain-google-genai"
            )

        return ChatGoogleGenerativeAI(
            model=rp.model_name,
            google_api_key=api_key,
            temperature=temperature,
            max_output_tokens=rp.model_def.min_max_tokens,
        )

    # ── Circuit breaker ───────────────────────────────────────────────────

    def _is_provider_down(self, provider_code: str, model_name: str) -> bool:
        key = f"{provider_code}:{model_name}"
        with self._cache_lock:
            expires = self._provider_down_cache.get(key)
            if expires is None:
                return False
            if time.monotonic() >= expires:
                del self._provider_down_cache[key]
                return False
            return True

    def _mark_provider_down(self, provider_code: str, model_name: str) -> None:
        key = f"{provider_code}:{model_name}"
        with self._cache_lock:
            self._provider_down_cache[key] = time.monotonic() + _PROBE_DOWN_TTL
        logger.warning("[CircuitBreaker] Marked %s down for %.0fs", key, _PROBE_DOWN_TTL)

    def _bump_stat(self, field_name: str, amount: int = 1) -> None:
        """Increment runtime stats under lock for concurrent safety."""
        with self._stats_lock:
            current = getattr(self.stats, field_name)
            setattr(self.stats, field_name, current + amount)


# ── Singleton ────────────────────────────────────────────────────────────────

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
    """Reset the singleton (for testing)."""
    global _resolver
    with _resolver_lock:
        _resolver = None
