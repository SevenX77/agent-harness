"""What a real call puts on the wire, per protocol.

A probe exists to predict a call, so what the call sends has to be written down
somewhere a probe can be checked against. It was not, and the cost was a wrong
change: the probe's token budget field was moved to `max_tokens` on the
evidence of `call/dispatch.py::_call_openai_compatible`, which no route reaches
— `RouteChatModelFactory.build` returns a native LangChain model for every one
of the four protocols `ResolvedRoute.protocol` can hold, so the SDK dispatch
path behind `GenericRouteChatModel` is only reachable through a fall-through
that a validated route cannot take.

The payloads below are read off the models the factory actually builds, which
is the same seam `build_probe_model` uses for the pre-call probe. Nothing here
is asserted from reading provider docs or gateway source.
"""

from __future__ import annotations

from typing import Any

import pytest
from graph_agent_gateway.call import RouteChatModelFactory
from graph_agent_gateway.registry import ResolvedRoute
from pydantic import SecretStr

_BASE_URLS = {
    "openai_compatible": "https://host.example/v1",
    "ark_runtime": "https://ark.example/api/v3",
    "anthropic_compatible": "https://anthropic.example/v1",
    "google_genai": "https://generativelanguage.example/v1beta",
}


class _StaticCredentials:
    def get(self, ref: str) -> SecretStr:
        del ref
        return SecretStr("SECRET")


def _route(protocol: str, *, model_id: str = "m-1") -> ResolvedRoute:
    return ResolvedRoute(
        role_name="graph_agent",
        route_id=f"endpoint-one:{model_id}",
        endpoint_id="endpoint-one",
        protocol=protocol,  # type: ignore[arg-type]
        base_url=_BASE_URLS[protocol],
        credential_ref="endpoint:endpoint-one",
        credential_fingerprint="fingerprint-a",
        provider_model_id=model_id,
        canonical_id=model_id,
        timeout_seconds=17,
        effective_runtime_settings={},
    )


def _built(protocol: str, *, model_id: str = "m-1") -> Any:
    factory = RouteChatModelFactory(credential_provider=_StaticCredentials())
    return factory.build(_route(protocol, model_id=model_id), max_tokens=16, reasoning_effort="high")


@pytest.mark.parametrize(
    ("protocol", "budget_field", "effort_field"),
    [
        ("openai_compatible", "max_completion_tokens", "reasoning_effort"),
        # ARK routes are built as OpenAI-compatible chat models, not through the
        # Volcengine SDK: the ark_chat/ark_responses methods are an official API
        # a probe may ask about, not the request a run makes.
        ("ark_runtime", "max_completion_tokens", "reasoning_effort"),
    ],
)
def test_an_openai_shaped_call_names_its_budget_and_effort(
    protocol: str, budget_field: str, effort_field: str
) -> None:
    payload = _built(protocol)._get_request_payload([], stop=None)

    assert payload[budget_field] == 16
    assert payload[effort_field] == "high"


def test_a_deepseek_route_names_its_budget_the_same_way() -> None:
    """The subclass differs; the field does not.

    A route whose identity mentions deepseek is built as PatchedChatDeepSeek
    rather than the plain OpenAI-compatible model, which is why the probe used
    to send this one a different budget field than the rest.
    """

    model = _built("openai_compatible", model_id="deepseek-reasoner")
    payload = model._get_request_payload([], stop=None)

    assert type(model).__name__ == "PatchedChatDeepSeek"
    assert payload["max_completion_tokens"] == 16


def test_an_anthropic_call_asks_for_effort_without_a_thinking_block() -> None:
    payload = _built("anthropic_compatible")._get_request_payload([], stop=None)

    assert payload["max_tokens"] == 16
    assert payload["output_config"] == {"effort": "high"}
    assert "thinking" not in payload


def test_a_google_call_carries_its_budget_and_thinking_level() -> None:
    model = _built("google_genai")

    assert model.max_output_tokens == 16
    assert model.thinking_level == "high"


def test_every_protocol_a_route_can_declare_is_covered_here() -> None:
    from graph_agent_gateway.registry import Protocol

    assert set(_BASE_URLS) == set(Protocol.__args__)  # type: ignore[attr-defined]
