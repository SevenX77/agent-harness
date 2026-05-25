"""Resolver protocol consumed by GraphAgent runtime."""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from langchain_core.language_models.chat_models import BaseChatModel


@runtime_checkable
class ModelResolverProtocol(Protocol):
    """Resolve one logical role/model override into a LangChain chat model."""

    def resolve(
        self,
        role_name: str | None = None,
        *,
        thinking_enabled: bool | None = None,
        model_override: str | None = None,
        callbacks: tuple[Any, ...] = (),
        phase_name: str | None = None,
        **kwargs: Any,
    ) -> BaseChatModel:
        """Return a LangChain-compatible chat model for one phase."""
