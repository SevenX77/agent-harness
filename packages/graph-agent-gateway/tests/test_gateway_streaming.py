"""The gateway asks the provider for an answer the way the answer arrives.

A provider writes its answer a piece at a time. Everything above the gateway is
now built to carry pieces, and the gateway was the one layer that still asked
for the finished thing — LangChain reads a chat model with no `_stream` as one
that cannot stream, so `stream()` on it collapses into a single blocking call
and hands back one slice containing everything.

What makes this more than a plumbing change is that the gateway retries. It
escalates the token budget when an answer was cut off, and it moves to the next
route when one fails. A retry produces a different answer, so the pieces of the
attempt being abandoned must be voided — otherwise whoever is folding the
pieces back together ends up with two attempts spliced into one, which is a
wrong answer and not merely a wrong picture.
"""

from __future__ import annotations

from collections.abc import Iterator, Sequence
from typing import Any

import pytest
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, AIMessageChunk, BaseMessage, HumanMessage


def _route(*, endpoint_id: str = "qiniu-anthropic", route_slug: str = "claude-sonnet-4-6"):
    from graph_agent_gateway.registry.schema import ResolvedRoute

    return ResolvedRoute(
        role_name="graph_agent",
        route_id=f"{endpoint_id}:{route_slug}",
        endpoint_id=endpoint_id,
        protocol="anthropic_compatible",  # type: ignore[arg-type]
        base_url="https://llm.wavespeed.ai",
        credential_ref=f"endpoint:{endpoint_id}",
        credential_fingerprint="fingerprint-a",
        provider_model_id=route_slug,
        canonical_id=route_slug,
    )


def _role(routes: Sequence[Any], *, token_escalation_rounds: int = 0):
    from graph_agent_gateway.registry.schema import ResolvedRole, RuntimePolicy

    return ResolvedRole(
        role_name="graph_agent",
        system_prompt_prefix="Always keep tool-call context.",
        runtime_policy=RuntimePolicy(token_escalation_rounds=token_escalation_rounds),
        routes=list(routes),
    )


class _Manager:
    def __init__(self) -> None:
        self.marked_down: list[str] = []
        self.usage_records: list[tuple[str, int, int]] = []

    def is_provider_marked_down(self, route: Any, runtime_policy: Any) -> bool:
        return False


    def mark_provider_down(self, route: Any, exc: BaseException, runtime_policy: Any) -> None:
        self.marked_down.append(route.route_id)

    def usage_total_calls(self, route: Any) -> int:
        return 0

    def record_usage(self, provider_code: str, prompt: int, completion: int) -> None:
        self.usage_records.append((provider_code, prompt, completion))


class _MidStreamFailure(RuntimeError):
    """A failure the gateway is willing to fall back from (a 404 from the route)."""

    status_code = 404


class _Attempt:
    """One provider answer, expressed the way a provider expresses it."""

    def __init__(
        self,
        pieces: list[str],
        *,
        finish_reason: str = "stop",
        usage: dict[str, int] | None = None,
        raises_after: int | None = None,
    ) -> None:
        self.pieces = pieces
        self.finish_reason = finish_reason
        self.usage = usage or {"input_tokens": 5, "output_tokens": 7, "total_tokens": 12}
        self.raises_after = raises_after

    def chunks(self) -> Iterator[AIMessageChunk]:
        for index, piece in enumerate(self.pieces):
            if self.raises_after is not None and index == self.raises_after:
                raise _MidStreamFailure("the route stopped answering mid-stream")
            yield AIMessageChunk(content=piece)
        yield AIMessageChunk(
            content="",
            usage_metadata=self.usage,  # type: ignore[arg-type]
            response_metadata={"finish_reason": self.finish_reason},
        )


class _StreamingChatModel:
    def __init__(self, attempts: list[_Attempt]) -> None:
        self.attempts = attempts
        self.calls: list[list[BaseMessage]] = []

    def stream(self, messages: list[BaseMessage], **kwargs: Any) -> Iterator[AIMessageChunk]:
        del kwargs
        self.calls.append(list(messages))
        yield from self.attempts.pop(0).chunks()


class _Factory:
    def __init__(self, per_route: dict[str, _StreamingChatModel]) -> None:
        self.per_route = per_route
        self.built: list[str] = []

    def build(self, route: Any, **kwargs: Any) -> _StreamingChatModel:
        del kwargs
        self.built.append(route.route_id)
        return self.per_route[route.route_id]


def _install(monkeypatch: pytest.MonkeyPatch, factory: _Factory) -> None:
    from graph_agent_gateway import gateway_chat_model

    monkeypatch.setattr(
        gateway_chat_model,
        "RouteChatModelFactory",
        lambda **_kwargs: factory,
        raising=False,
    )


def _model(routes: Sequence[Any], *, escalation: int = 0, manager: Any = None) -> Any:
    from graph_agent_gateway.gateway_chat_model import GatewayChatModel

    return GatewayChatModel(
        "graph_agent",
        _role(routes, token_escalation_rounds=escalation),
        max_tokens=512,
        client_manager=manager or _Manager(),
        probe_before_call=False,
    )


def test_the_gateway_model_is_one_langchain_calls_streamable() -> None:
    """LangChain decides by looking for an override, so the override must exist."""
    from graph_agent_gateway.gateway_chat_model import GatewayChatModel
    from graph_agent_gateway.predict_interception import PredictGatewayChatModel

    for cls in (GatewayChatModel, PredictGatewayChatModel):
        assert cls._stream is not BaseChatModel._stream, (
            f"{cls.__name__} without its own _stream is read by LangChain as unable to "
            "stream, and stream() silently becomes one blocking call"
        )


def test_the_answer_reaches_the_caller_in_the_pieces_the_provider_sent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    route = _route()
    _install(monkeypatch, _Factory({route.route_id: _StreamingChatModel([_Attempt(["Hel", "lo, ", "world"])])}))

    pieces = [chunk for chunk in _model([route]).stream([HumanMessage(content="hi")]) if chunk.content]

    assert len(pieces) == 3, "the provider's pieces must not be folded before the caller sees them"
    assert "".join(str(piece.content) for piece in pieces) == "Hello, world"


def test_a_truncated_attempt_is_voided_when_the_gateway_escalates(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Escalation replaces the answer, so the abandoned pieces must not survive."""
    from graph_agent_gateway.gateway_chat_model import answer_restarts_here

    route = _route()
    _install(
        monkeypatch,
        _Factory(
            {
                route.route_id: _StreamingChatModel(
                    [
                        _Attempt(["cut off ha"], finish_reason="length"),
                        _Attempt(["the whole ", "answer"]),
                    ]
                )
            }
        ),
    )
    model = _model([route], escalation=1)

    chunks = list(model.stream([HumanMessage(content="hi")]))

    restarts = [index for index, chunk in enumerate(chunks) if answer_restarts_here(chunk)]
    assert len(restarts) == 1, "the caller has to be told the earlier pieces are void"
    after = "".join(str(chunk.content) for chunk in chunks[restarts[0] + 1 :])
    assert after == "the whole answer"


def test_a_route_that_fails_after_streaming_voids_what_it_streamed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from graph_agent_gateway.gateway_chat_model import answer_restarts_here

    first, second = _route(endpoint_id="primary"), _route(endpoint_id="backup")
    _install(
        monkeypatch,
        _Factory(
            {
                first.route_id: _StreamingChatModel(
                    [_Attempt(["half an ", "answer"], raises_after=1)]
                ),
                second.route_id: _StreamingChatModel([_Attempt(["a complete ", "answer"])]),
            }
        ),
    )

    chunks = list(_model([first, second]).stream([HumanMessage(content="hi")]))

    restarts = [index for index, chunk in enumerate(chunks) if answer_restarts_here(chunk)]
    assert len(restarts) == 1
    after = "".join(str(chunk.content) for chunk in chunks[restarts[0] + 1 :])
    assert after == "a complete answer"


def test_the_finished_answer_is_what_it_was_before_the_pieces_existed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Streaming is how the answer arrives, not what the answer is."""
    route = _route()
    manager = _Manager()
    _install(
        monkeypatch,
        _Factory({route.route_id: _StreamingChatModel([_Attempt(["chatx", "-ok"])])}),
    )

    answer = _model([route], manager=manager).invoke([HumanMessage(content="hi")])

    assert isinstance(answer, AIMessage)
    assert answer.content == "chatx-ok"
    assert answer.response_metadata["route_id"] == route.route_id
    assert answer.response_metadata["endpoint_id"] == route.endpoint_id
    assert answer.response_metadata["finish_reason"] == "stop"
    assert answer.response_metadata["usage"]["prompt_tokens"] == 5
    assert answer.response_metadata["usage"]["completion_tokens"] == 7
    assert manager.usage_records == [("qiniu-anthropic", 5, 7)]


def test_the_finished_answer_of_an_escalated_call_holds_only_the_last_attempt(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    route = _route()
    _install(
        monkeypatch,
        _Factory(
            {
                route.route_id: _StreamingChatModel(
                    [
                        _Attempt(["cut off ha"], finish_reason="length"),
                        _Attempt(["the whole ", "answer"]),
                    ]
                )
            }
        ),
    )

    answer = _model([route], escalation=1).invoke([HumanMessage(content="hi")])

    assert answer.content == "the whole answer", "two attempts must never be spliced together"
