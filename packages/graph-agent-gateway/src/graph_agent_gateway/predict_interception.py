"""Predict-mode gateway model placeholder."""

from __future__ import annotations

from typing import Any

from langchain_core.callbacks.manager import CallbackManagerForLLMRun
from langchain_core.messages import AIMessage, BaseMessage
from langchain_core.outputs import ChatGeneration, ChatResult

from graph_agent_gateway.gateway_chat_model import GatewayChatModel
from graph_agent_gateway.registry.schema import ResolvedRole


class PredictGatewayChatModel(GatewayChatModel):
    """Gateway-compatible model that never calls real providers."""

    mock_strategy: Any

    def __init__(
        self,
        role_name: str,
        resolved_role: ResolvedRole,
        *,
        mock_strategy: Any,
        **kwargs: Any,
    ) -> None:
        kwargs["mock_strategy"] = mock_strategy
        super().__init__(role_name, resolved_role, **kwargs)

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: CallbackManagerForLLMRun | None = None,
        **kwargs: Any,
    ) -> ChatResult:
        del messages, stop, run_manager, kwargs
        return ChatResult(
            generations=[ChatGeneration(message=AIMessage(content="predict mock"))],
            llm_output={"provider": "predict", "model_name": self.role_name},
        )
