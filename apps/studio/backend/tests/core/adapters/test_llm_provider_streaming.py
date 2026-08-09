"""The adapter passes the gateway model's stream through instead of folding it.

`_generate` returned one finished answer, which is where the model client's
ability to report progress used to end. What replaces it has to keep the answer
identical while letting the slices out one at a time — so this pins both: more
than one slice arrives, and the closing slice still carries everything the
engine bills and routes on.
"""

from __future__ import annotations

from typing import Any

from app.core.adapters.engine import _GatewayBackedLLMProvider
from graph_agent.core.llm_provider import LLMProviderRequest


class _Chunk:
    """A stand-in for AIMessageChunk: addable, and metadata lands on the last."""

    def __init__(
        self,
        content: str,
        *,
        tool_calls: list[Any] | None = None,
        usage_metadata: dict[str, int] | None = None,
        response_metadata: dict[str, Any] | None = None,
    ) -> None:
        self.content = content
        self.tool_calls = tool_calls or []
        self.usage_metadata = usage_metadata
        self.response_metadata = response_metadata or {}

    def __add__(self, other: _Chunk) -> _Chunk:
        return _Chunk(
            self.content + other.content,
            tool_calls=self.tool_calls + other.tool_calls,
            usage_metadata=other.usage_metadata or self.usage_metadata,
            response_metadata={**self.response_metadata, **other.response_metadata},
        )


class _StreamingResolver:
    def __init__(self, chunks: list[_Chunk]) -> None:
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
    resolver = _StreamingResolver([_Chunk("Hel"), _Chunk("lo, "), _Chunk("world")])

    slices = list(_GatewayBackedLLMProvider(resolver).stream(_request()))

    text_slices = [s for s in slices if s.content]
    assert len(text_slices) == 3, "the model's slices must reach the engine as slices"
    assert "".join(str(s.content) for s in text_slices) == "Hello, world"
    assert resolver.streamed_stop == ["END"]


def test_the_closing_slice_carries_what_the_run_bills_and_routes_on() -> None:
    tool_call = {"name": "lookup", "args": {}, "id": "call-1", "type": "tool_call"}
    resolver = _StreamingResolver(
        [
            _Chunk("thinking"),
            _Chunk(
                "",
                tool_calls=[tool_call],
                usage_metadata={"input_tokens": 7, "output_tokens": 3},
                response_metadata={"finish_reason": "tool_use"},
            ),
        ]
    )

    slices = list(_GatewayBackedLLMProvider(resolver).stream(_request()))

    closing = slices[-1]
    assert closing.content == ""
    assert closing.metadata["tool_calls"] == [tool_call]
    assert closing.metadata["usage_metadata"] == {"input_tokens": 7, "output_tokens": 3}
    assert closing.metadata["finish_reason"] == "tool_use"
    assert closing.metadata["model_name"] == "claude-opus-5"


def test_a_model_that_yields_nothing_still_closes_the_answer() -> None:
    slices = list(_GatewayBackedLLMProvider(_StreamingResolver([])).stream(_request()))

    assert [s.content for s in slices] == [""]
