"""The gateway's non-LangChain face: plain data in, plain data out.

Design: docs/graph-agent-gateway/mvp1/09-inv-invocation-runtime/mvp1-alignment.md
(PM 2026-06-04, three faces — this is the second one), restored per decision doc
D10 after it was deleted on a wrong reading of "nothing calls it".
"""

from __future__ import annotations

import dataclasses
from collections.abc import Iterator, Sequence
from typing import Any

import httpx
import openai
import pytest
from langchain_core.messages import AIMessage, AIMessageChunk, BaseMessage
from stream_fakes import as_one_piece


def _route(
    *,
    endpoint_id: str = "vendor",
    route_slug: str = "gpt-5",
    protocol: str = "openai_compatible",
):
    from graph_agent_gateway.registry import ResolvedRoute

    return ResolvedRoute(
        role_name="graph_agent",
        route_id=f"{endpoint_id}:{route_slug}",
        endpoint_id=endpoint_id,
        protocol=protocol,  # type: ignore[arg-type]
        base_url="https://api.vendor.example/v1",
        credential_ref=f"endpoint:{endpoint_id}",
        credential_fingerprint="fingerprint-a",
        provider_model_id=route_slug,
        canonical_id=route_slug,
    )


def _role(routes: Sequence[Any]):
    from graph_agent_gateway.registry import ResolvedRole, RuntimePolicy

    return ResolvedRole(
        role_name="graph_agent",
        runtime_policy=RuntimePolicy(token_escalation_rounds=0),
        routes=list(routes),
    )


class _Ledger:
    """Enough of the circuit/usage ledger for the face to run without one."""

    def is_provider_marked_down(self, route: Any, runtime_policy: Any) -> bool:
        return False

    def mark_provider_down(self, route: Any, exc: BaseException, runtime_policy: Any) -> None:
        return None

    def usage_total_calls(self, route: Any) -> int:
        return 0

    def record_usage(self, provider_code: str, prompt: int, completion: int) -> None:
        return None


class _RouteAwareFactory:
    """Answers (or raises) per route, and records the order routes were tried."""

    def __init__(self, answers: dict[str, AIMessage | BaseException]) -> None:
        self.answers = answers
        self.tried: list[str] = []
        self.seen_messages: list[list[BaseMessage]] = []

    def build(self, route: Any, **kwargs: object) -> Any:
        del kwargs
        answer = self.answers[route.route_id]
        tried = self.tried
        seen = self.seen_messages
        route_id = route.route_id

        class _Model:
            def stream(self, messages: list[BaseMessage], **_: Any) -> Iterator[AIMessageChunk]:
                tried.append(route_id)
                seen.append(list(messages))
                if isinstance(answer, BaseException):
                    raise answer
                yield from as_one_piece(answer)

        return _Model()


def _with_factory(monkeypatch: pytest.MonkeyPatch, factory: _RouteAwareFactory) -> None:
    from graph_agent_gateway.call import chat_model as gateway_chat_model

    monkeypatch.setattr(
        gateway_chat_model,
        "RouteChatModelFactory",
        lambda **_kwargs: factory,
        raising=False,
    )


def _openai_error(error_cls: type[Exception], status_code: int, message: str) -> Exception:
    response = httpx.Response(
        status_code,
        request=httpx.Request("POST", "https://api.vendor.example/v1/chat/completions"),
        json={"error": {"message": message, "type": "provider_error"}},
    )
    return error_cls(message, response=response, body=response.json())


def _is_langchain(value: object) -> bool:
    return type(value).__module__.split(".")[0] in {"langchain", "langchain_core"}


def test_plain_chat_face_takes_and_returns_no_langchain_type(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """09 test key point (1): a consumer never has to touch a LangChain type.

    Not "no LangChain anywhere" — the package depends on langchain-core either
    way. What is under test is the boundary: plain dicts go in, and every field
    of what comes back is plain data.
    """
    from graph_agent_gateway.call import chat_plainly

    route = _route()
    factory = _RouteAwareFactory(
        {
            route.route_id: AIMessage(
                content="plain-ok",
                usage_metadata={"input_tokens": 5, "output_tokens": 7, "total_tokens": 12},
                response_metadata={"finish_reason": "stop"},
            )
        }
    )
    _with_factory(monkeypatch, factory)

    answer = chat_plainly(
        _role([route]),
        [{"role": "user", "content": "hi"}],
        ledger=_Ledger(),
    )

    assert not _is_langchain(answer)
    for field in dataclasses.fields(answer):
        value = getattr(answer, field.name)
        assert not _is_langchain(value), f"{field.name} leaks a LangChain type"

    assert answer.text == "plain-ok"
    assert answer.route_id == route.route_id
    assert answer.endpoint_id == "vendor"
    assert answer.model == "gpt-5"
    assert answer.protocol == "openai_compatible"
    assert answer.finish_reason == "stop"
    assert answer.usage["total_tokens"] == 12


def test_plain_chat_face_walks_the_whole_fallback_chain(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """D10-4: this face is the gateway calling, not a serializer.

    A consumer that skips LangChain must not thereby lose fallback — that is the
    difference between this face and handing the route over (face 3).
    """
    from graph_agent_gateway.call import chat_plainly

    bad = _route(endpoint_id="primary", route_slug="bad")
    good = _route(endpoint_id="fallback", route_slug="ok")
    factory = _RouteAwareFactory(
        {
            bad.route_id: _openai_error(openai.AuthenticationError, 401, "invalid api key"),
            good.route_id: AIMessage(
                content="fallback-ok",
                usage_metadata={"input_tokens": 1, "output_tokens": 1, "total_tokens": 2},
                response_metadata={"finish_reason": "stop"},
            ),
        }
    )
    _with_factory(monkeypatch, factory)

    answer = chat_plainly(
        _role([bad, good]),
        [{"role": "user", "content": "hi"}],
        ledger=_Ledger(),
    )

    assert answer.text == "fallback-ok"
    assert answer.route_id == good.route_id
    # The first route is asked first and never asked again; the pre-call probe
    # means the second route is asked more than once (probe, then the answer),
    # which is the same behaviour the ChatX face has.
    assert factory.tried[0] == bad.route_id
    assert bad.route_id not in factory.tried[1:]
    assert factory.tried[-1] == good.route_id


def test_plain_chat_face_reads_an_answer_the_provider_sent_in_blocks(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Content blocks are a shape, not a different answer.

    Anthropic-shaped providers answer in blocks, and a thinking block sits in
    the same list as the text. A caller who asked plainly gets the text — with
    the reasoning kept, separately, rather than spliced into it.
    """
    from graph_agent_gateway.call import chat_plainly

    route = _route(protocol="anthropic_compatible")
    factory = _RouteAwareFactory(
        {
            route.route_id: AIMessage(
                content=[
                    {"type": "text", "text": "first half, "},
                    {"type": "text", "text": "second half"},
                ],
                additional_kwargs={"reasoning_content": "thought about it"},
                usage_metadata={"input_tokens": 2, "output_tokens": 3, "total_tokens": 5},
                response_metadata={"finish_reason": "stop"},
            )
        }
    )
    _with_factory(monkeypatch, factory)

    answer = chat_plainly(
        _role([route]),
        [{"role": "user", "content": "hi"}],
        ledger=_Ledger(),
    )

    assert answer.text == "first half, second half"
    assert answer.reasoning == "thought about it"


def test_plain_chat_face_is_exported_from_the_package_root() -> None:
    """A consumer choosing this face should not have to know the domain tree."""
    import graph_agent_gateway

    assert "chat_plainly" in graph_agent_gateway.__all__
    assert "PlainAnswer" in graph_agent_gateway.__all__
