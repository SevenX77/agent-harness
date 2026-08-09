"""What the gateway decided is part of what happened.

A call that took two minutes and answered from the second-choice endpoint did
not just "take two minutes". The gateway skipped a route it had circuit-broken
earlier, probed another, retried one on a transient status, doubled a budget
after a cut-off answer, fell back, and finally answered somewhere. Of those,
only "fell back" ever reached anyone watching.

The rest are the same fact with different outcomes — the gateway made a routing
decision — so they are one event with a closed set of outcomes, not six event
types. `voided_streamed_answer` rides on the decision that caused it because
discarding what was already streamed is a consequence of deciding to retry, not
a moment of its own.
"""

from __future__ import annotations

from collections.abc import Iterator, Sequence
from typing import Any

import pytest
from langchain_core.messages import AIMessage, AIMessageChunk, BaseMessage, HumanMessage
from stream_fakes import as_one_piece


class _RetryableStatusError(RuntimeError):
    status_code = 503


class _FallbackStatusError(RuntimeError):
    status_code = 404


def _route(*, endpoint_id: str = "primary", route_slug: str = "claude-sonnet-4-6"):
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
        system_prompt_prefix="prefix",
        runtime_policy=RuntimePolicy(token_escalation_rounds=token_escalation_rounds),
        routes=list(routes),
    )


class _Manager:
    def __init__(self, *, marked_down: set[str] | None = None, probe_ok: bool = True) -> None:
        self._marked_down = marked_down or set()
        self._probe_ok = probe_ok

    def is_provider_marked_down(self, route: Any, runtime_policy: Any) -> bool:
        return route.route_id in self._marked_down

    def probe_provider(self, route: Any, runtime_policy: Any, **kwargs: Any) -> bool:
        return self._probe_ok

    def mark_provider_down(self, route: Any, exc: BaseException, runtime_policy: Any) -> None:
        self._marked_down.add(route.route_id)

    def usage_total_calls(self, route: Any) -> int:
        return 0

    def record_usage(self, provider_code: str, prompt: int, completion: int) -> None:
        return None


class _Recorder:
    def __init__(self) -> None:
        self.events: list[Any] = []

    def on_event(self, event: Any) -> None:
        self.events.append(event)


class _Behaviour:
    """What one route does when asked, once per ask."""

    def __init__(self, answers: list[Any]) -> None:
        self.answers = answers

    def stream(self, messages: list[BaseMessage], **kwargs: Any) -> Iterator[AIMessageChunk]:
        del messages, kwargs
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


def _install(monkeypatch: pytest.MonkeyPatch, factory: _Factory) -> None:
    from graph_agent_gateway import gateway_chat_model

    monkeypatch.setattr(
        gateway_chat_model, "RouteChatModelFactory", lambda **_kw: factory, raising=False
    )


def _ask(
    routes: Sequence[Any],
    factory: _Factory,
    monkeypatch: pytest.MonkeyPatch,
    *,
    manager: Any = None,
    escalation: int = 0,
    probe: bool = False,
) -> list[Any]:
    from graph_agent_gateway.gateway_chat_model import GatewayChatModel

    _install(monkeypatch, factory)
    recorder = _Recorder()
    model = GatewayChatModel(
        "graph_agent",
        _role(routes, token_escalation_rounds=escalation),
        max_tokens=512,
        client_manager=manager or _Manager(),
        probe_before_call=probe,
        callbacks=[recorder],
    )
    try:
        list(model.stream([HumanMessage(content="hi")]))
    except Exception:
        pass
    return [e for e in recorder.events if getattr(e, "event_type", None) == "llm_route_decision"]


def _decisions(events: list[Any]) -> list[str]:
    return [e.decision for e in events]


def test_the_route_that_answered_is_named(monkeypatch: pytest.MonkeyPatch) -> None:
    """Without this, a trace cannot say which endpoint produced the answer."""
    route = _route()
    events = _ask([route], _Factory({route.route_id: _Behaviour([AIMessage(content="ok")])}), monkeypatch)

    assert _decisions(events) == ["answered"]
    assert events[0].route_id == route.route_id
    assert events[0].endpoint_id == "primary"
    assert events[0].provider_model_id == "claude-sonnet-4-6"


def test_a_route_skipped_because_it_was_circuit_broken_says_so(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A silent skip is indistinguishable from a route that was never configured."""
    broken, healthy = _route(endpoint_id="broken"), _route(endpoint_id="healthy")
    events = _ask(
        [broken, healthy],
        _Factory({healthy.route_id: _Behaviour([AIMessage(content="ok")])}),
        monkeypatch,
        manager=_Manager(marked_down={broken.route_id}),
    )

    assert _decisions(events) == ["skipped_circuit_open", "answered"]
    assert events[0].route_id == broken.route_id


def test_a_probe_that_fails_says_so(monkeypatch: pytest.MonkeyPatch) -> None:
    unhealthy, healthy = _route(endpoint_id="unhealthy"), _route(endpoint_id="healthy")
    events = _ask(
        [unhealthy, healthy],
        _Factory({healthy.route_id: _Behaviour([AIMessage(content="ok")])}),
        monkeypatch,
        manager=_Manager(probe_ok=False),
        probe=True,
    )

    assert _decisions(events)[0] == "probe_failed"
    assert events[0].route_id == unhealthy.route_id


def test_a_retry_on_the_same_route_says_so(monkeypatch: pytest.MonkeyPatch) -> None:
    route = _route()
    events = _ask(
        [route],
        _Factory(
            {route.route_id: _Behaviour([_RetryableStatusError("overloaded"), AIMessage(content="ok")])}
        ),
        monkeypatch,
    )

    assert _decisions(events) == ["retried_same_route", "answered"]
    assert "overloaded" in (events[0].reason or "")


def test_doubling_the_budget_says_so_and_says_what_it_discarded(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    route = _route()
    events = _ask(
        [route],
        _Factory(
            {
                route.route_id: _Behaviour(
                    [
                        AIMessage(content="cut off ha", response_metadata={"finish_reason": "length"}),
                        AIMessage(content="the whole answer"),
                    ]
                )
            }
        ),
        monkeypatch,
        escalation=1,
    )

    assert _decisions(events) == ["escalated_budget", "answered"]
    assert events[0].voided_streamed_answer is True, (
        "the panel is showing text this decision just threw away; not saying so leaves it up"
    )


def test_falling_back_says_where_it_is_going(monkeypatch: pytest.MonkeyPatch) -> None:
    first, second = _route(endpoint_id="first"), _route(endpoint_id="second")
    events = _ask(
        [first, second],
        _Factory(
            {
                first.route_id: _Behaviour([_FallbackStatusError("model not found")]),
                second.route_id: _Behaviour([AIMessage(content="ok")]),
            }
        ),
        monkeypatch,
    )

    assert _decisions(events) == ["fell_back", "answered"]
    assert events[0].route_id == first.route_id
    assert events[0].next_route_id == second.route_id


def test_running_out_of_routes_says_so(monkeypatch: pytest.MonkeyPatch) -> None:
    """The exception says the run failed; the trace should say what was tried."""
    only = _route()
    events = _ask(
        [only],
        _Factory({only.route_id: _Behaviour([_FallbackStatusError("model not found")])}),
        monkeypatch,
    )

    assert _decisions(events) == ["fell_back", "exhausted"]


# The three properties below moved here from `test_llm_fallback_event.py` when
# the fall-back event was replaced by the decision event it is one outcome of.
# They are properties of announcing a decision, not of that one outcome.


class _FailingCallback:
    def on_event(self, event: Any) -> None:
        del event
        raise RuntimeError("a listener must not be able to mask the run's own failure")


def test_a_failing_listener_does_not_stop_the_others_from_hearing() -> None:
    from graph_agent_gateway.tracing import emit_route_decision_event

    recorder = _Recorder()

    emit_route_decision_event(
        callbacks=(_FailingCallback(), recorder),
        phase_name="draft",
        decision="exhausted",
        reason="TimeoutError: request timed out",
    )

    assert [e.decision for e in recorder.events] == ["exhausted"]


def test_the_event_code_is_not_something_a_call_site_chooses() -> None:
    """One code per event type, decided by the type — not per emission."""
    from graph_agent_gateway.events import ROUTE_DECISION_EVENT_CODE, LLMRouteDecisionEvent
    from graph_agent_gateway.tracing import build_route_decision_event

    with pytest.raises(TypeError):
        LLMRouteDecisionEvent(  # type: ignore[call-arg]
            phase_name="draft",
            decision="fell_back",
            code="[F-v3-gateway-all-providers-failed]",
        )

    with pytest.raises(TypeError):
        build_route_decision_event(
            phase_name="draft",
            decision="fell_back",
            **{"code": "[F-v3-gateway-all-providers-failed]"},
        )

    assert build_route_decision_event(phase_name="draft", decision="fell_back").code == (
        ROUTE_DECISION_EVENT_CODE
    )


def test_a_decision_serialises_to_the_shape_a_host_stores(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The host serialises every event the same way; this one carries no Pydantic."""
    route = _route()
    events = _ask([route], _Factory({route.route_id: _Behaviour([AIMessage(content="ok")])}), monkeypatch)

    payload = events[0].model_dump(mode="json")
    assert payload["event_type"] == "llm_route_decision"
    assert payload["decision"] == "answered"
    assert payload["route_id"] == route.route_id
    assert payload["voided_streamed_answer"] is False
