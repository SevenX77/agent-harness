"""The adapter passes the gateway model's stream through instead of folding it.

`_generate` returned one finished answer, which is where the model client's
ability to report progress used to end. What replaces it has to keep the answer
identical while letting the slices out one at a time — so this pins both: more
than one slice arrives, and the closing slice still carries everything the
engine bills and routes on.

The slices here are real ``AIMessageChunk``s. Folding them is LangChain's
addition, not the adapter's own arithmetic, and a stand-in that merges by some
other rule proves the adapter against a provider that does not exist: the first
version of this file used one that let the last slice overwrite usage, and it
stayed green while silently disagreeing with every provider that reports the
prompt count up front.
"""

from __future__ import annotations

from typing import Any

from app.core.adapters.engine import _GatewayBackedLLMProvider
from graph_agent.core.llm_provider import LLMProviderChatModel, LLMProviderRequest
from langchain_core.messages import AIMessage, AIMessageChunk


def _chunk(
    content: str,
    *,
    tool_call_chunks: list[Any] | None = None,
    usage_metadata: Any = None,
    response_metadata: dict[str, Any] | None = None,
) -> AIMessageChunk:
    return AIMessageChunk(
        content=content,
        tool_call_chunks=tool_call_chunks or [],
        usage_metadata=usage_metadata,
        response_metadata=response_metadata or {},
    )


def _usage(input_tokens: int, output_tokens: int) -> dict[str, int]:
    return {
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "total_tokens": input_tokens + output_tokens,
    }


class _StreamingResolver:
    def __init__(self, chunks: list[AIMessageChunk]) -> None:
        self._chunks = chunks
        self.streamed_stop: Any = "unset"

    def resolve(self, role: str, **kwargs: Any) -> Any:
        del role, kwargs
        resolver = self

        class _Model:
            model_name = "claude-opus-5"

            def stream(self, messages: Any, stop: Any = None) -> Any:
                del messages
                resolver.streamed_stop = stop
                yield from resolver._chunks

        return _Model()


def _request() -> LLMProviderRequest:
    return LLMProviderRequest(role="graph_agent", messages=[], metadata={"stop": ["END"]})


def test_the_answer_arrives_in_more_than_one_slice() -> None:
    resolver = _StreamingResolver([_chunk("Hel"), _chunk("lo, "), _chunk("world")])

    slices = list(_GatewayBackedLLMProvider(resolver).stream(_request()))

    text_slices = [s for s in slices if s.content]
    assert len(text_slices) == 3, "the model's slices must reach the engine as slices"
    assert "".join(str(s.content) for s in text_slices) == "Hello, world"
    assert resolver.streamed_stop == ["END"]


def test_the_closing_slice_carries_what_the_run_bills_and_routes_on() -> None:
    resolver = _StreamingResolver(
        [
            _chunk("thinking"),
            _chunk(
                "",
                tool_call_chunks=[
                    {"name": "lookup", "args": "{}", "id": "call-1", "index": 0}
                ],
                usage_metadata=_usage(7, 3),
                response_metadata={"finish_reason": "tool_use"},
            ),
        ]
    )

    slices = list(_GatewayBackedLLMProvider(resolver).stream(_request()))

    closing = slices[-1]
    assert closing.content == ""
    assert [call["name"] for call in closing.metadata["tool_calls"]] == ["lookup"]
    assert closing.metadata["usage_metadata"] == _usage(7, 3)
    assert closing.metadata["finish_reason"] == "tool_use"
    assert closing.metadata["model_name"] == "claude-opus-5"


def test_usage_reported_in_pieces_is_billed_as_a_whole() -> None:
    """Some providers report the two halves of usage at opposite ends of a stream.

    Anthropic sends `input_tokens` with the opening event and `output_tokens`
    with the closing one, so a stream in which no single slice carries the whole
    count is the normal case, not an edge case. Whatever folds the slices back
    together has to add those halves up; taking the last slice's word for it
    bills the run for an answer with no prompt.
    """
    resolver = _StreamingResolver(
        [
            _chunk("", usage_metadata=_usage(7, 0)),
            _chunk("Hel"),
            _chunk("lo"),
            _chunk("", usage_metadata=_usage(0, 3)),
        ]
    )

    slices = list(_GatewayBackedLLMProvider(resolver).stream(_request()))

    usage = slices[-1].metadata["usage_metadata"]
    assert usage["input_tokens"] == 7, "the prompt was counted before the first word arrived"
    assert usage["output_tokens"] == 3


def test_what_the_run_bills_survives_the_trip_back_to_one_message() -> None:
    """The slices exist for the audience; the run's metrics still read a message.

    This is the seam streaming moved: usage used to come off a single finished
    response, and now it has to survive being split, merged and handed back
    through the Port. A provider that streams perfectly but arrives with no
    usage on the message reports every run as costing nothing.
    """
    resolver = _StreamingResolver(
        [
            _chunk("", usage_metadata=_usage(11, 0)),
            _chunk("Hel"),
            _chunk("lo"),
            _chunk("", usage_metadata=_usage(0, 5)),
        ]
    )
    model = LLMProviderChatModel(
        provider=_GatewayBackedLLMProvider(resolver),
        role="graph_agent",
        phase_name="draft",
    )

    answer = model.invoke([])

    assert isinstance(answer, AIMessage)
    assert answer.content == "Hello"
    assert answer.usage_metadata is not None
    assert answer.usage_metadata["input_tokens"] == 11
    assert answer.usage_metadata["output_tokens"] == 5


def test_an_answer_the_gateway_restarted_is_passed_on_as_a_restart() -> None:
    """The gateway retries; the engine folds. One has to tell the other.

    A retry replaces the answer instead of continuing it, so the adapter cannot
    quietly keep accumulating — it would hand the engine one message stitched
    from two attempts. It also must not swallow the fact: the engine is the one
    doing the folding, so the engine is who needs to hear it.
    """
    from graph_agent_gateway import ANSWER_RESTARTED

    resolver = _StreamingResolver(
        [
            _chunk("cut off ha", response_metadata={"finish_reason": "length"}),
            _chunk("", response_metadata={ANSWER_RESTARTED: True}),
            _chunk("the whole "),
            _chunk("answer", usage_metadata=_usage(11, 5), response_metadata={"finish_reason": "stop"}),
        ]
    )

    slices = list(_GatewayBackedLLMProvider(resolver).stream(_request()))

    restarts = [index for index, s in enumerate(slices) if s.restarts_answer]
    assert len(restarts) == 1, "the engine has to be told the earlier slices are void"
    after = "".join(str(s.content) for s in slices[restarts[0] + 1 :])
    assert after == "the whole answer"
    closing = slices[-1]
    assert closing.metadata["usage_metadata"] == _usage(11, 5)
    assert closing.metadata["finish_reason"] == "stop", (
        "the closing metadata must describe the answer that survived, not the one voided"
    )


def test_a_model_that_yields_nothing_still_closes_the_answer() -> None:
    slices = list(_GatewayBackedLLMProvider(_StreamingResolver([])).stream(_request()))

    assert [s.content for s in slices] == [""]
