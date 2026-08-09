"""Predict-mode gateway model placeholder."""

from __future__ import annotations

import json
from collections.abc import Iterator
from typing import Any

from langchain_core.callbacks.manager import CallbackManagerForLLMRun
from langchain_core.messages import AIMessage, AIMessageChunk, BaseMessage
from langchain_core.outputs import ChatGeneration, ChatGenerationChunk, ChatResult

from graph_agent_gateway.gateway_chat_model import GatewayChatModel
from graph_agent_gateway.protocol import PredictContext
from graph_agent_gateway.registry.schema import ResolvedRole


class PredictGatewayChatModel(GatewayChatModel):
    """Gateway-compatible model that delegates mock resolution to the SDK predict context."""

    predict_context: PredictContext

    def __init__(
        self,
        role_name: str,
        resolved_role: ResolvedRole,
        *,
        predict_context: PredictContext,
        **kwargs: Any,
    ) -> None:
        kwargs["predict_context"] = predict_context
        kwargs["probe_before_call"] = False
        super().__init__(role_name, resolved_role, **kwargs)

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: CallbackManagerForLLMRun | None = None,
        **kwargs: Any,
    ) -> ChatResult:
        del stop, run_manager, kwargs
        payload, mocked_source = self.predict_context.resolve_generation(
            phase_name=self.phase_name or "",
            role_name=self.role_name or "",
            messages=messages,
        )
        content = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
        message = AIMessage(
            content=content,
            response_metadata={"mocked_source": mocked_source},
        )
        return ChatResult(
            generations=[ChatGeneration(message=message)],
            llm_output={"provider": "predict", "model_name": self.role_name},
        )

    def _stream(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: CallbackManagerForLLMRun | None = None,
        **kwargs: Any,
    ) -> Iterator[ChatGenerationChunk]:
        """A rehearsal has nothing to reveal gradually, so it is one piece.

        It still has to be a piece: callers reach every model the same way now,
        and a model without this override is one LangChain reads as unable to
        stream — which would quietly route predict through a different call
        path than a real run takes.
        """
        result = self._generate(messages, stop, run_manager, **kwargs)
        message = result.generations[0].message
        yield ChatGenerationChunk(
            message=AIMessageChunk(
                content=message.content,
                response_metadata=message.response_metadata,
            )
        )
