"""LLMProviderChatModel must not smuggle engine callbacks through LangChain's
reserved ``callbacks`` field.

``BaseChatModel`` already owns ``callbacks`` (list[BaseCallbackHandler] |
BaseCallbackManager | None); shadowing it with a tuple of graph_agent Callback
objects makes every ``.invoke()`` crash inside LangChain's
``CallbackManager.configure`` (``'tuple' object has no attribute 'handlers'``)
— first real LLM call of any run died this way. Engine callbacks ride their own
field (``event_callbacks``), the same convention PredictGatewayChatModel uses.
"""

from __future__ import annotations

from langchain_core.messages import HumanMessage

from graph_agent.core.llm_provider import FakeLLMProvider, LLMProviderChatModel


class _EngineCallback:
    """Stand-in for graph_agent.callbacks.base.Callback — NOT a LangChain handler."""

    def on_phase_start(self) -> None:  # pragma: no cover - never called here
        pass


def _model_with_engine_callbacks(provider: FakeLLMProvider) -> LLMProviderChatModel:
    return LLMProviderChatModel(
        provider=provider,
        role="analyst",
        phase_name="segment",
        event_callbacks=(_EngineCallback(),),
    )


def test_invoke_survives_attached_engine_callbacks() -> None:
    provider = FakeLLMProvider()
    model = _model_with_engine_callbacks(provider)

    result = model.invoke([HumanMessage(content="hi")])

    assert result.content == "fake response"


def test_engine_callbacks_are_forwarded_to_provider_metadata() -> None:
    provider = FakeLLMProvider()
    model = _model_with_engine_callbacks(provider)

    model.invoke([HumanMessage(content="hi")])

    assert len(provider.requests) == 1
    forwarded = provider.requests[0].metadata.get("callbacks")
    assert isinstance(forwarded, tuple)
    assert len(forwarded) == 1
    assert isinstance(forwarded[0], _EngineCallback)


def test_langchain_callbacks_field_keeps_base_class_semantics() -> None:
    """The inherited LangChain field must stay untouched (None by default), so
    LangChain's own callback plumbing never sees engine objects."""

    model = _model_with_engine_callbacks(FakeLLMProvider())

    assert model.callbacks is None
