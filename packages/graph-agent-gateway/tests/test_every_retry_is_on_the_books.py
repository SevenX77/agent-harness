"""A retry the ledger cannot see did not stop being a retry.

Measured on a fake flapping provider (problem ledger E22, 2026-08-22): the
provider answered every set of messages with one 500 followed by a success, the
wire carried five 500s, and the run's `trace.jsonl` held five
`llm_route_decision` events — all of them `answered`, not one
`retried_same_route`. The reader is told the call went smoothly; it took three
requests.

`langchain_openai.ChatOpenAI` leaves `max_retries: int | None = None`, so the
openai SDK's `DEFAULT_MAX_RETRIES = 2` applies and the 5xx was repaired one
layer below the gateway — before `classify_exception` was ever reached.

Two things were wrong with that, and both are fixed here:

*   **Nobody chose the number.** The gateway's own contract has said
    `standard_runtime.max_attempts = 2` since the policy was written, while the
    behaviour in force was openai's 3 — and, stacked on the gateway's own
    same-route retry, up to 6 requests for one call.
*   **Nobody could see it.** The gateway's ledger records DECISIONS; a retry
    taken beneath it is not a decision it can record, so no amount of reading
    the trace could recover it.

So the transport stops retrying and the gateway does it, in the loop that was
already emitting `retried_same_route`. Then "how many times did this route get
asked" and "how many `retried_same_route` events are on the trace" are the same
number by construction, which is the only way the two cannot drift.

This reverses the IMPLEMENTATION of gateway design F2 (07/09 `mvp1-alignment`),
not its ruling: the anti-flap retry stays, bounded, honouring `Retry-After`. F2
chose to leave it inside ChatX because at the time "当前代码反而没有同-route
重试" — and that premise is gone: `chat_model.py` has retried the same route on
a retryable classification since the `retry_same_route` action existed.
"""

from __future__ import annotations

from collections.abc import Iterator, Sequence
from typing import Any

import pytest
from langchain_core.messages import AIMessage, AIMessageChunk, BaseMessage, HumanMessage
from stream_fakes import as_one_piece


class _Flapping(RuntimeError):
    """What a busy endpoint raises: retryable, same route, no advice attached."""

    status_code = 503


class _RateLimited(RuntimeError):
    status_code = 429

    def __init__(self, retry_after: str) -> None:
        super().__init__("slow down")
        self.response = _Response({"retry-after": retry_after})


class _Response:
    def __init__(self, headers: dict[str, str]) -> None:
        self.headers = headers
        self.status_code = 429


def _route(*, endpoint_id: str = "primary", protocol: str = "anthropic_compatible"):
    from graph_agent_gateway.registry import ResolvedRoute

    return ResolvedRoute(
        role_name="graph_agent",
        route_id=f"{endpoint_id}:model-a",
        endpoint_id=endpoint_id,
        protocol=protocol,  # type: ignore[arg-type]
        base_url="https://llm.example.invalid",
        credential_ref=f"endpoint:{endpoint_id}",
        credential_fingerprint="fingerprint-a",
        provider_model_id="model-a",
        canonical_id="model-a",
    )


def _role(routes: Sequence[Any], *, max_attempts: int, backoff_ms: list[int] | None = None):
    from graph_agent_gateway.registry import (
        ResolvedRole,
        RuntimePolicy,
        StandardTerminalRetrySettings,
        TerminalRetryPolicy,
    )

    return ResolvedRole(
        role_name="graph_agent",
        system_prompt_prefix="prefix",
        runtime_policy=RuntimePolicy(
            terminal_retry_policy=TerminalRetryPolicy(
                standard_runtime=StandardTerminalRetrySettings(
                    max_attempts=max_attempts,
                    backoff_ms=backoff_ms if backoff_ms is not None else [0] * (max_attempts - 1),
                )
            )
        ),
        routes=list(routes),
    )


class _Manager:
    def is_provider_marked_down(self, route: Any, runtime_policy: Any) -> bool:
        return False

    def mark_provider_down(self, route: Any, exc: BaseException, runtime_policy: Any) -> None:
        return None

    def usage_total_calls(self, route: Any) -> int:
        return 0

    def record_usage(self, provider_code: str, prompt: int, completion: int) -> None:
        return None


class _StaticCredentials:
    def get(self, credential_ref: str) -> str:
        del credential_ref
        return "sk-test"


class _Recorder:
    def __init__(self) -> None:
        self.events: list[Any] = []

    def on_event(self, event: Any) -> None:
        self.events.append(event)


class _Behaviour:
    def __init__(self, answers: list[Any]) -> None:
        self.answers = answers
        self.asked = 0

    def stream(self, messages: list[BaseMessage], **kwargs: Any) -> Iterator[AIMessageChunk]:
        del messages, kwargs
        self.asked += 1
        answer = self.answers.pop(0)
        if isinstance(answer, BaseException):
            raise answer
        yield from as_one_piece(answer)


class _Factory:
    def __init__(self, per_route: dict[str, _Behaviour]) -> None:
        self.per_route = per_route

    def build(self, route: Any, **kwargs: Any) -> _Behaviour:
        del kwargs
        return self.per_route[route.route_id]


def _ask(
    routes: Sequence[Any],
    factory: _Factory,
    monkeypatch: pytest.MonkeyPatch,
    *,
    max_attempts: int,
    backoff_ms: list[int] | None = None,
) -> list[Any]:
    from graph_agent_gateway.call import GatewayChatModel
    from graph_agent_gateway.call import chat_model as gateway_chat_model

    monkeypatch.setattr(
        gateway_chat_model, "RouteChatModelFactory", lambda **_kw: factory, raising=False
    )
    recorder = _Recorder()
    model = GatewayChatModel(
        "graph_agent",
        _role(routes, max_attempts=max_attempts, backoff_ms=backoff_ms),
        max_tokens=512,
        ledger=_Manager(),
        # The pre-call probe is its own question with its own budget
        # (`standard_probe`, one attempt); these tests are about the call.
        probe_before_call=False,
        callbacks=[recorder],
    )
    try:
        list(model.stream([HumanMessage(content="hi")]))
    except Exception:
        pass
    return [e for e in recorder.events if getattr(e, "event_type", None) == "llm_route_decision"]


def _slept(monkeypatch: pytest.MonkeyPatch) -> list[float]:
    from graph_agent_gateway.call import chat_model as gateway_chat_model

    waits: list[float] = []
    monkeypatch.setattr(gateway_chat_model.time, "sleep", waits.append)
    return waits


def test_the_trace_counts_every_ask_the_route_took(monkeypatch: pytest.MonkeyPatch) -> None:
    """The whole point: retries on the trace == requests on the wire."""
    _slept(monkeypatch)
    route = _route()
    behaviour = _Behaviour([_Flapping(), _Flapping(), AIMessage(content="ok")])
    events = _ask([route], _Factory({route.route_id: behaviour}), monkeypatch, max_attempts=3)

    assert [e.decision for e in events] == ["retried_same_route", "retried_same_route", "answered"]
    assert behaviour.asked == 3
    assert behaviour.asked == sum(1 for e in events if e.decision == "retried_same_route") + 1


def test_the_budget_is_the_policy_s_not_a_hardcoded_one(monkeypatch: pytest.MonkeyPatch) -> None:
    """A policy of two attempts means one retry, and the second failure leaves
    the route rather than asking a third time — even though the third ask, the
    fake will tell you, would have succeeded."""
    _slept(monkeypatch)
    route = _route()
    behaviour = _Behaviour([_Flapping(), _Flapping(), AIMessage(content="ok")])
    events = _ask([route], _Factory({route.route_id: behaviour}), monkeypatch, max_attempts=2)

    assert [e.decision for e in events] == ["retried_same_route", "fell_back", "exhausted"]
    assert behaviour.asked == 2


def test_a_retry_waits_the_backoff_the_policy_names(monkeypatch: pytest.MonkeyPatch) -> None:
    """Retrying a busy endpoint the same millisecond is how a flap becomes a storm."""
    waits = _slept(monkeypatch)
    route = _route()
    behaviour = _Behaviour([_Flapping(), _Flapping(), AIMessage(content="ok")])
    _ask(
        [route],
        _Factory({route.route_id: behaviour}),
        monkeypatch,
        max_attempts=3,
        backoff_ms=[250, 1000],
    )

    assert waits == [0.25, 1.0]


def test_the_provider_s_own_retry_after_outranks_the_policy(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The one thing the transport did better than a fixed backoff.

    A 429 that says when to come back is the provider telling us its own
    schedule; a policy that ignores it spends the whole budget arriving early.
    """
    waits = _slept(monkeypatch)
    route = _route()
    behaviour = _Behaviour([_RateLimited("7"), AIMessage(content="ok")])
    _ask(
        [route],
        _Factory({route.route_id: behaviour}),
        monkeypatch,
        max_attempts=2,
        backoff_ms=[250],
    )

    assert waits == [7.0]


def test_a_retry_after_date_is_not_guessed_at(monkeypatch: pytest.MonkeyPatch) -> None:
    """`Retry-After` may be an HTTP date; the policy's own backoff is the answer
    then, rather than a parse that could be off by a clock skew."""
    waits = _slept(monkeypatch)
    route = _route()
    behaviour = _Behaviour([_RateLimited("Wed, 21 Oct 2026 07:28:00 GMT"), AIMessage(content="ok")])
    _ask(
        [route],
        _Factory({route.route_id: behaviour}),
        monkeypatch,
        max_attempts=2,
        backoff_ms=[250],
    )

    assert waits == [0.25]


@pytest.mark.parametrize(
    "protocol",
    ["openai_compatible", "ark_runtime", "anthropic_compatible", "google_genai"],
)
def test_the_transport_does_not_retry_behind_the_ledger(protocol: str) -> None:
    """Every protocol a route can declare is built told not to retry.

    Left unset, each client falls through to its own SDK's default — 2 for
    openai and anthropic, 6 for google — numbers this gateway never chose and
    cannot observe.
    """
    from graph_agent_gateway.call import RouteChatModelFactory

    model = RouteChatModelFactory(credential_provider=_StaticCredentials()).build(
        _route(protocol=protocol)
    )

    assert model.max_retries == 0
