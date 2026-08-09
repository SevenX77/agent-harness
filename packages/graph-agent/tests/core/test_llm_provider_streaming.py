"""A model answer arrives in slices, so the Port has to be able to say so.

`LLMProvider` used to expose one blocking `invoke`, which meant the engine
could not express "the answer is still arriving" no matter what the underlying
client supported. The Port now streams, and the chat model builds its answer by
consuming that stream — the assembled result is what the agent loop sees, so it
must be identical to what one blocking call produced.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

from langchain_core.messages import HumanMessage

from graph_agent.core.llm_provider import (
    LLMProvider,
    LLMProviderChatModel,
    LLMProviderChunk,
    LLMProviderRequest,
    LLMProviderResponse,
)


class _InvokeOnlyProvider:
    """What every provider looked like before the Port could stream."""

    def invoke(self, request: LLMProviderRequest) -> LLMProviderResponse:
        del request
        return LLMProviderResponse(content="whole answer", metadata={})


class _SlicingProvider:
    """Hands back a prepared list of slices and records what it was asked."""

    def __init__(self, slices: list[LLMProviderChunk]) -> None:
        self._slices = slices
        self.stream_requests: list[LLMProviderRequest] = []
        self.invoke_requests: list[LLMProviderRequest] = []

    def invoke(self, request: LLMProviderRequest) -> LLMProviderResponse:
        self.invoke_requests.append(request)
        return LLMProviderResponse(content="blocking answer", metadata={})

    def stream(self, request: LLMProviderRequest) -> Iterator[LLMProviderChunk]:
        self.stream_requests.append(request)
        yield from self._slices


def _model(provider: Any) -> LLMProviderChatModel:
    return LLMProviderChatModel(provider=provider, role="analyst", phase_name="segment")


def test_a_provider_that_cannot_stream_no_longer_satisfies_the_port() -> None:
    """The Port is the contract; a provider missing the streaming half fails it."""
    assert not isinstance(_InvokeOnlyProvider(), LLMProvider)
    assert isinstance(_SlicingProvider([]), LLMProvider)


def test_the_answer_is_assembled_from_the_slices_not_from_one_blocking_call() -> None:
    provider = _SlicingProvider(
        [
            LLMProviderChunk(content="Hel"),
            LLMProviderChunk(content="lo, "),
            LLMProviderChunk(content="world"),
        ]
    )

    message = _model(provider).invoke([HumanMessage(content="hi")])

    assert message.content == "Hello, world"
    assert len(provider.stream_requests) == 1
    assert provider.invoke_requests == [], "streaming path must not fall back to invoke"


def test_the_request_reaching_the_stream_carries_the_same_metadata_as_before() -> None:
    provider = _SlicingProvider([LLMProviderChunk(content="ok")])
    model = LLMProviderChatModel(
        provider=provider,
        role="analyst",
        phase_name="segment",
        model_override="anthropic/claude",
    )

    model.invoke([HumanMessage(content="hi")], stop=["END"])

    request = provider.stream_requests[0]
    assert request.role == "analyst"
    assert request.metadata["phase_name"] == "segment"
    assert request.metadata["model_override"] == "anthropic/claude"
    assert request.metadata["stop"] == ["END"]


def test_tool_calls_usage_and_model_survive_the_assembly() -> None:
    """The agent loop routes on tool calls and the run bills on usage.

    Both arrive on the closing slice, the way providers report them, and both
    have to end up exactly where a blocking answer would have put them.
    """
    tool_call = {"name": "lookup", "args": {"topic": "ports"}, "id": "call-1", "type": "tool_call"}
    provider = _SlicingProvider(
        [
            LLMProviderChunk(content="thinking"),
            LLMProviderChunk(
                content="",
                metadata={
                    "tool_calls": [tool_call],
                    "usage_metadata": {"input_tokens": 11, "output_tokens": 4, "total_tokens": 15},
                    "model_name": "claude-opus-5",
                },
            ),
        ]
    )
    model = _model(provider)

    message = model.invoke([HumanMessage(content="hi")])

    assert message.tool_calls == [tool_call]
    assert message.usage_metadata == {"input_tokens": 11, "output_tokens": 4, "total_tokens": 15}
    assert message.response_metadata["model_name"] == "claude-opus-5"
    # The resolved model is what the provider answered with, and the model
    # remembers it for the events that report which model served the call.
    assert model.model_name == "claude-opus-5"
    assert "tool_calls" not in message.response_metadata
    assert "usage_metadata" not in message.response_metadata


def test_a_single_slice_answer_is_indistinguishable_from_a_blocking_one() -> None:
    """A provider with nothing to stream still has to produce a normal answer."""
    provider = _SlicingProvider(
        [LLMProviderChunk(content="whole answer", metadata={"model_name": "m"})]
    )

    message = _model(provider).invoke([HumanMessage(content="hi")])

    assert message.content == "whole answer"
    assert message.response_metadata["model_name"] == "m"
