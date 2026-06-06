"""Provider model wrappers for graph-agent-gateway."""

from __future__ import annotations

from typing import Any

from langchain_core.callbacks.manager import CallbackManagerForLLMRun
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import BaseMessage
from langchain_core.outputs import ChatResult
from pydantic import ConfigDict


class GenericRouteChatModel(BaseChatModel):
    """Fail-loud shell for protocols without official ChatX support."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    route: Any
    credential_provider: Any = None

    @property
    def _llm_type(self) -> str:
        return "graph_agent_gateway_generic_route"

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: CallbackManagerForLLMRun | None = None,
        **kwargs: Any,
    ) -> ChatResult:
        del messages, stop, run_manager, kwargs
        route_id = getattr(self.route, "route_id", "<unknown>")
        raise NotImplementedError(
            "GenericRouteChatModel ordinary chat support is deferred; "
            f"route {route_id!r} cannot be invoked without an official ChatX adapter."
        )


__all__ = ["GenericRouteChatModel"]
