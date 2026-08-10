"""A setting the route will not take is not a route that is down.

Runtime settings are preferences: the gateway puts them on the request when it
can, and the call still has to happen when it cannot. Today a provider that
refuses one parameter is read as a provider that failed, so a single mistyped
setting is reported as "all providers failed" — measured 2026-08-09 against
api.deepseek.com, where `thinking: true` (the right key, the wrong shape) ended
the whole call.

Telling the two apart does not need a table of every provider's wording. It
needs one cheap question: ask the same route again without the preferences. If
it answers, the route was never the problem.

Decision: docs/design/2026-08-10-runtime-settings-are-preferences-decision.md
"""

from __future__ import annotations

from collections.abc import Iterator, Sequence
from typing import Any

import pytest
from langchain_core.messages import AIMessage, AIMessageChunk, BaseMessage, HumanMessage
from stream_fakes import as_one_piece

# The preferences a call may lose and still be the same call. The budget is not
# among them: it is protocol-required for anthropic, and it already has its own
# escalation path, so dropping it would be a different change to the request.
PREFERENCE_KWARGS = ("temperature", "top_p", "seed", "reasoning", "reasoning_effort")


class _RejectedByProvider(RuntimeError):
    """A 400 whose wording matches none of the classifier's known markers.

    Deliberately worded like DeepSeek's real refusal: no "unsupported", no
    "unknown parameter" — the words a keyword table would need and never has.
    """

    status_code = 400

    def __init__(self, param: str) -> None:
        super().__init__(
            "Failed to deserialize the JSON body into the target type: "
            f"{param}: invalid type: boolean `true`, expected struct Options"
        )


def _route(*, endpoint_id: str = "primary", route_slug: str = "deepseek-v4-pro"):
    from graph_agent_gateway.registry.schema import ResolvedRoute

    return ResolvedRoute(
        role_name="graph_agent",
        route_id=f"{endpoint_id}:{route_slug}",
        endpoint_id=endpoint_id,
        protocol="openai_compatible",  # type: ignore[arg-type]
        base_url="https://api.deepseek.example",
        credential_ref=f"endpoint:{endpoint_id}",
        credential_fingerprint="fingerprint-a",
        provider_model_id=route_slug,
        canonical_id=route_slug,
    )


def _role(routes: Sequence[Any]):
    from graph_agent_gateway.registry.schema import ResolvedRole, RuntimePolicy

    return ResolvedRole(
        role_name="graph_agent",
        system_prompt_prefix="prefix",
        runtime_policy=RuntimePolicy(token_escalation_rounds=0),
        routes=list(routes),
    )


class _Manager:
    def __init__(self) -> None:
        self.marked_down: set[str] = set()

    def is_provider_marked_down(self, route: Any, runtime_policy: Any) -> bool:
        return route.route_id in self.marked_down


    def mark_provider_down(self, route: Any, exc: BaseException, runtime_policy: Any) -> None:
        self.marked_down.add(route.route_id)

    def usage_total_calls(self, route: Any) -> int:
        return 0

    def record_usage(self, provider_code: str, prompt: int, completion: int) -> None:
        return None


class _Recorder:
    def __init__(self) -> None:
        self.events: list[Any] = []

    def on_event(self, event: Any) -> None:
        self.events.append(event)


class _RouteThatRefusesPreferences:
    """Answers only when the request carries no preference parameters."""

    def __init__(self, *, refuse_always: bool = False) -> None:
        self.refuse_always = refuse_always
        self.builds: list[dict[str, Any]] = []

    def build(self, route: Any, **kwargs: Any) -> Any:
        del route
        self.builds.append(dict(kwargs))
        offending = [key for key in PREFERENCE_KWARGS if key in kwargs]
        refuse = self.refuse_always or bool(offending)
        return _Behaviour(_RejectedByProvider(offending[0]) if refuse else None)


class _Behaviour:
    def __init__(self, refusal: BaseException | None) -> None:
        self.refusal = refusal

    def stream(self, messages: list[BaseMessage], **kwargs: Any) -> Iterator[AIMessageChunk]:
        del messages, kwargs
        if self.refusal is not None:
            raise self.refusal
        yield from as_one_piece(AIMessage(content="answered without the preferences"))


def _ask(
    routes: Sequence[Any],
    factory: Any,
    monkeypatch: pytest.MonkeyPatch,
    *,
    manager: Any,
    probe: bool = False,
) -> tuple[list[Any], BaseException | None]:
    from graph_agent_gateway import gateway_chat_model
    from graph_agent_gateway.gateway_chat_model import GatewayChatModel

    monkeypatch.setattr(
        gateway_chat_model, "RouteChatModelFactory", lambda **_kw: factory, raising=False
    )
    recorder = _Recorder()
    model = GatewayChatModel(
        "graph_agent",
        _role(routes),
        max_tokens=512,
        temperature=0.7,
        client_manager=manager,
        probe_before_call=probe,
        callbacks=[recorder],
    )
    raised: BaseException | None = None
    try:
        list(model.stream([HumanMessage(content="hi")]))
    except BaseException as exc:  # noqa: BLE001 — the failure is part of what is asserted
        raised = exc
    decisions = [e for e in recorder.events if getattr(e, "event_type", None) == "llm_route_decision"]
    return decisions, raised


def test_a_setting_the_route_refuses_does_not_kill_the_call(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    route = _route()
    factory = _RouteThatRefusesPreferences()
    manager = _Manager()

    decisions, raised = _ask([route], factory, monkeypatch, manager=manager)

    assert raised is None, f"the call died over a preference: {raised}"
    assert [d.decision for d in decisions] == ["dropped_rejected_settings", "answered"]
    assert route.route_id not in manager.marked_down, "a refused setting marked the route down"


def test_the_retry_keeps_everything_that_is_not_a_preference(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # The budget is not a preference: anthropic requires it, and it has its own
    # escalation path. Dropping it would make the retry a different request.
    route = _route()
    factory = _RouteThatRefusesPreferences()

    _ask([route], factory, monkeypatch, manager=_Manager())

    assert len(factory.builds) == 2, "the route was not asked a second time"
    first, second = factory.builds
    assert "temperature" in first
    assert not [key for key in PREFERENCE_KWARGS if key in second]
    assert second["max_tokens"] == first["max_tokens"]


def test_a_refusal_that_is_not_about_the_settings_still_ends_the_call(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Dropping the preferences is a question, not a cure: when the answer is
    # still no, the route really is refusing the request and today's handling
    # must stand.
    route = _route()
    factory = _RouteThatRefusesPreferences(refuse_always=True)

    decisions, raised = _ask([route], factory, monkeypatch, manager=_Manager())

    assert raised is not None
    assert [d.decision for d in decisions][-1] in {"failed_terminal", "exhausted"}


class _RouteThatRefusesOnePreference:
    """Answers unless the request carries the one setting it will not take."""

    def __init__(self, offending: str = "top_p") -> None:
        self.offending = offending
        self.builds: list[dict[str, Any]] = []

    def build(self, route: Any, **kwargs: Any) -> Any:
        del route
        self.builds.append(dict(kwargs))
        return _Behaviour(_RejectedByProvider(self.offending) if self.offending in kwargs else None)


def test_a_named_refusal_costs_only_the_setting_that_was_named(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """One refused preference must not cost the caller the others.

    The probe says which setting the route will not take. Dropping the whole
    preference layer after being told exactly that would throw away settings
    the route just accepted — the user asked for those, and nothing refused
    them.
    """
    from graph_agent_gateway.registry.schema import EffectiveRuntimeSetting

    route = _route()
    route.effective_runtime_settings["top_p"] = EffectiveRuntimeSetting(
        value=5.0,
        source="route_setting",
    )
    factory = _RouteThatRefusesOnePreference()

    decisions, raised = _ask([route], factory, monkeypatch, manager=_Manager(), probe=True)

    assert raised is None
    call = factory.builds[-1]
    assert "top_p" not in call
    assert call["temperature"] == 0.7
    assert [d.decision for d in decisions] == ["dropped_rejected_settings", "answered"]
