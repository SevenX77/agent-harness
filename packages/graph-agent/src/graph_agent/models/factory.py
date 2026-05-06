"""Minimal LangChain chat model factory for GraphAgent."""

from __future__ import annotations

import os
from typing import Any, Literal

from langchain_core.language_models.chat_models import BaseChatModel

Provider = Literal["openai", "openai_compatible", "anthropic", "anthropic_compatible"]


def _first_env(*names: str) -> str | None:
    for name in names:
        value = os.environ.get(name)
        if value:
            return value
    return None


def create_chat_model(
    *,
    provider: str | None = None,
    model: str | None = None,
    api_key: str | None = None,
    base_url: str | None = None,
    timeout: float | None = None,
    temperature: float | None = None,
    thinking_enabled: bool | None = None,
    **kwargs: Any,
) -> BaseChatModel:
    """Create a LangChain chat model from explicit args or environment.

    Supported providers are OpenAI-compatible and Anthropic-compatible. The
    factory intentionally does not read application YAML.
    """
    _ = thinking_enabled
    resolved_provider = (
        provider or os.environ.get("GRAPH_AGENT_MODEL_PROVIDER") or "openai"
    ).lower()
    resolved_model = model or os.environ.get("GRAPH_AGENT_MODEL") or os.environ.get("OPENAI_MODEL")
    common_kwargs: dict[str, Any] = dict(kwargs)
    if timeout is not None:
        common_kwargs["timeout"] = timeout
    if temperature is not None:
        common_kwargs["temperature"] = temperature

    if resolved_provider in {"openai", "openai_compatible"}:
        from langchain_openai import ChatOpenAI

        openai_model = resolved_model or "gpt-4o-mini"
        openai_api_key = api_key or _first_env("OPENAI_API_KEY", "GRAPH_AGENT_API_KEY")
        openai_base_url = base_url or _first_env("OPENAI_BASE_URL", "GRAPH_AGENT_BASE_URL")
        openai_kwargs: dict[str, Any] = {
            "model": openai_model,
            "base_url": openai_base_url,
            **common_kwargs,
        }
        if openai_api_key is not None:
            openai_kwargs["api_key"] = openai_api_key
        return ChatOpenAI(**openai_kwargs)

    if resolved_provider in {"anthropic", "anthropic_compatible"}:
        try:
            from langchain_anthropic import ChatAnthropic
        except ImportError as exc:
            raise ImportError(
                "langchain_anthropic is required for Anthropic-compatible models. "
                "Install it with: pip install langchain-anthropic"
            ) from exc

        anthropic_model = resolved_model or "claude-3-5-sonnet-latest"
        anthropic_api_key = api_key or _first_env("ANTHROPIC_API_KEY", "GRAPH_AGENT_API_KEY")
        anthropic_base_url = base_url or _first_env("ANTHROPIC_BASE_URL", "GRAPH_AGENT_BASE_URL")
        anthropic_kwargs: dict[str, Any] = {
            "model_name": anthropic_model,
            "base_url": anthropic_base_url,
            **common_kwargs,
        }
        if anthropic_api_key is not None:
            anthropic_kwargs["api_key"] = anthropic_api_key
        return ChatAnthropic(**anthropic_kwargs)

    raise ValueError(f"Unsupported chat model provider: {resolved_provider!r}")
