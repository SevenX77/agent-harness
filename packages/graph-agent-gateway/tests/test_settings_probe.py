"""The cheap question asked before the expensive one.

A probe that asks something other than what the call is about to ask answers a
question nobody had. Today's probe is a hand-written minimum — one token, one
dot, no settings — so it reports a healthy route right up until the real
request goes out carrying the user's settings and is refused (measured
2026-08-10: eight calls in one run, each discovering the same refusal for
itself, each after the request was already on the wire).

So the probe is the same request, built the same way, asking for one token. If
it comes back refused, one question per preference says which one, before the
long call starts rather than two minutes into it.

Decision: docs/design/2026-08-10-runtime-settings-are-preferences-decision.md
(D5: two moments, each judging what it can judge)
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

from langchain_core.messages import AIMessage, AIMessageChunk, BaseMessage
from pydantic import SecretStr
from stream_fakes import as_one_piece


class StaticCredentialProvider:
    def __init__(self, secret: str = "endpoint-secret") -> None:
        self.secret = secret

    def get(self, ref: str) -> SecretStr:
        del ref
        return SecretStr(self.secret)


def _route(*, protocol: str = "openai_compatible"):
    from graph_agent_gateway.registry import EffectiveRuntimeSetting, ResolvedRoute

    return ResolvedRoute(
        role_name="graph_agent",
        route_id="deepseek-official:deepseek-v4-pro",
        endpoint_id="deepseek-official",
        protocol=protocol,  # type: ignore[arg-type]
        base_url="https://api.deepseek.example/v1",
        credential_ref="endpoint:deepseek-official",
        credential_fingerprint="fingerprint-a",
        provider_model_id="deepseek-v4-pro",
        canonical_id="deepseek-v4-pro",
        timeout_seconds=17,
        effective_runtime_settings={
            "temperature": EffectiveRuntimeSetting(value=0.9, source="route_setting"),
            "max_output_tokens": EffectiveRuntimeSetting(value=4096, source="route_setting"),
            "top_p": EffectiveRuntimeSetting(value=0.4, source="route_setting"),
        },
    )


def _settings(route: Any):
    from graph_agent_gateway.call_settings import ModelDefaults, compose_call_settings

    return compose_call_settings(
        route,
        defaults=ModelDefaults(
            max_tokens=4096,
            temperature=None,
            thinking_enabled=None,
            runtime_setting_sources={},
        ),
        call_kwargs={},
        budget=4096,
        tools=[{"type": "function", "function": {"name": "noop", "parameters": {}}}],
        tool_choice=None,
    )


def _real_factory():
    from graph_agent_gateway.route_chat_model_factory import RouteChatModelFactory

    return RouteChatModelFactory(credential_provider=StaticCredentialProvider())


def test_the_probe_asks_with_the_settings_the_call_will_use() -> None:
    """Same request, same builder, one token — read off the finished payload."""
    from graph_agent_gateway.settings_probe import build_probe_model

    route = _route()
    model = build_probe_model(route, _settings(route), factory=_real_factory())
    payload = model._get_request_payload([], stop=None)  # type: ignore[attr-defined]

    assert payload["temperature"] == 0.9
    assert payload["top_p"] == 0.4
    # One token is the whole point: the probe pays a token to save a long call.
    assert payload.get("max_completion_tokens") == 1 or payload.get("max_tokens") == 1


def test_the_probe_leaves_the_tools_out_of_the_question_it_asks() -> None:
    """Tools are not settings, and binding them would ask a different question."""
    from graph_agent_gateway.settings_probe import build_probe_model

    route = _route()
    model = build_probe_model(route, _settings(route), factory=_real_factory())
    payload = model._get_request_payload([], stop=None)  # type: ignore[attr-defined]

    assert "tools" not in payload


class _Refusing:
    """A route that answers only when the named settings are absent."""

    status_code = 400

    def __init__(self, *refuses: str) -> None:
        self.refuses = refuses
        self.asked: list[dict[str, Any]] = []

    def build(self, route: Any, **kwargs: Any) -> Any:
        del route
        self.asked.append(dict(kwargs))
        offending = [key for key in self.refuses if key in kwargs]
        return _Behaviour(offending[0] if offending else None)


class _Behaviour:
    def __init__(self, offending: str | None) -> None:
        self.offending = offending

    def stream(self, messages: list[BaseMessage], **kwargs: Any) -> Iterator[AIMessageChunk]:
        del messages, kwargs
        if self.offending is not None:
            error = RuntimeError(
                "Failed to deserialize the JSON body into the target type: "
                f"{self.offending}: invalid value"
            )
            error.status_code = 400  # type: ignore[attr-defined]
            raise error
        yield from as_one_piece(AIMessage(content="."))


def _probe(route: Any, factory: Any):
    from graph_agent_gateway import settings_probe

    return settings_probe.probe_call_settings(route, _settings(route), factory=factory)


def test_the_probe_names_the_setting_the_route_will_not_take() -> None:
    route = _route()
    factory = _Refusing("temperature")

    verdict = _probe(route, factory)

    assert verdict.refused == ("temperature",)
    assert verdict.answers_without_them is True


def test_a_route_that_refuses_no_matter_what_is_not_blamed_on_the_settings() -> None:
    """Dropping the preferences is a question, not a cure.

    When the stripped request is refused too, the settings are not the reason
    and the route's own failure handling has to stand.
    """
    route = _route()
    factory = _Refusing("max_tokens")  # always present, so nothing to drop can help

    verdict = _probe(route, factory)

    assert verdict.refused == ()
    assert verdict.answers_without_them is False


def test_a_route_that_takes_everything_is_asked_exactly_once() -> None:
    """The common case must stay one cheap question, not one per setting."""
    route = _route()
    factory = _Refusing()

    verdict = _probe(route, factory)

    assert verdict.refused == ()
    assert verdict.answers_without_them is True
    assert len(factory.asked) == 1
