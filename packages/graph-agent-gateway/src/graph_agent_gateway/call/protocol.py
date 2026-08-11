"""Resolver protocol consumed by GraphAgent runtime."""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from langchain_core.language_models.chat_models import BaseChatModel

from graph_agent_gateway.resolve import ResolvedRouteChain


@runtime_checkable
class PredictContext(Protocol):
    """Protocol for target SDK prediction / mock interception context."""

    def resolve_generation(
        self,
        phase_name: str,
        role_name: str,
        messages: list[Any],
    ) -> tuple[dict[str, Any], str]:
        """Resolve a mock generation, returning the dictionary payload and mocked_source metadata string."""
        ...


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
        predict_context: PredictContext | None = None,
        **kwargs: Any,
    ) -> BaseChatModel:
        """Return a LangChain-compatible chat model for one phase."""

    def resolve_routes(
        self,
        role_name: str,
        *,
        route_override: str | None = None,
    ) -> ResolvedRouteChain:
        """Resolve registry configuration to an ordered route chain."""
