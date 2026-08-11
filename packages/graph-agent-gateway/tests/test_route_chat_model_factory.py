"""RouteChatModelFactory contract tests."""

from __future__ import annotations

import sys
import types

import pytest
from langchain_core.messages import AIMessage, HumanMessage
from pydantic import SecretStr


class StaticCredentialProvider:
    def __init__(self, secrets: dict[str, str]) -> None:
        self.secrets = secrets

    def get(self, ref: str) -> SecretStr:
        return SecretStr(self.secrets[ref])


def _route(
    *,
    endpoint_id: str = "openrouter-prod",
    route_slug: str = "openai.gpt-5",
    protocol: str = "openai_compatible",
    base_url: str = "https://openrouter.example/api/v1/",
    provider_model_id: str = "openai/gpt-5",
    canonical_id: str = "gpt-5",
    timeout_seconds: int = 17,
    temperature: float | None = 0.2,
    max_tokens: int = 333,
):
    from graph_agent_gateway.registry import EffectiveRuntimeSetting, ResolvedRoute
    effective_runtime_settings = {
        "max_output_tokens": EffectiveRuntimeSetting(value=max_tokens, source="route_setting"),
    }
    if temperature is not None:
        effective_runtime_settings["temperature"] = EffectiveRuntimeSetting(
            value=temperature,
            source="route_setting",
        )

    return ResolvedRoute(
        role_name="graph_agent",
        route_id=f"{endpoint_id}:{route_slug}",
        endpoint_id=endpoint_id,
        protocol=protocol,  # type: ignore[arg-type]
        base_url=base_url,
        credential_ref=f"endpoint:{endpoint_id}",
        credential_fingerprint="fingerprint-a",
        timeout_seconds=timeout_seconds,
        trust_env=False,
        provider_model_id=provider_model_id,
        canonical_id=canonical_id,
        effective_runtime_settings=effective_runtime_settings,
    )


def _factory():
    from graph_agent_gateway.call import RouteChatModelFactory

    return RouteChatModelFactory(
        credential_provider=StaticCredentialProvider(
            {
                "endpoint:openrouter-prod": "openrouter-secret",
                "endpoint:wavespeed": "wavespeed-secret",
                "endpoint:ark-cn": "ark-secret",
                "endpoint:google": "google-secret",
                "endpoint:generic": "generic-secret",
            }
        )
    )


def test_factory_builds_openai_compatible_chat_openai_with_the_settings_it_is_given() -> None:
    from langchain_openai import ChatOpenAI

    chat_model = _factory().build(_route(), temperature=0.2, max_tokens=333)

    assert isinstance(chat_model, ChatOpenAI)
    assert chat_model.model_name == "openai/gpt-5"
    assert chat_model.openai_api_base == "https://openrouter.example/api/v1"
    assert chat_model.openai_api_key.get_secret_value() == "openrouter-secret"
    assert chat_model.request_timeout == 17.0
    assert chat_model.temperature == 0.2
    assert chat_model.max_tokens == 333
    assert chat_model.stream_usage is True


def test_the_factory_sends_only_the_settings_it_was_given() -> None:
    """The caller composes the settings; the factory maps them onto a client.

    A second reader of the route's settings here would mean a setting the caller
    deliberately left off still went out — measured 2026-08-10 against
    api.deepseek.com, where the gateway dropped an out-of-range `top_p` after
    the provider refused it and the factory put it straight back on the retry.
    """
    from graph_agent_gateway.registry import EffectiveRuntimeSetting

    route = _route()
    route.effective_runtime_settings["top_p"] = EffectiveRuntimeSetting(
        value=5.0,
        source="route_setting",
    )

    chat_model = _factory().build(route, max_tokens=512, temperature=0.2)

    assert chat_model.top_p is None
    assert chat_model.max_tokens == 512


def test_deepseek_openai_payload_replays_multiturn_assistant_reasoning_content() -> None:
    chat_model = _factory().build(
        _route(
            route_slug="deepseek.deepseek-r1",
            provider_model_id="deepseek/deepseek-r1",
            canonical_id="deepseek-r1",
        )
    )

    payload = chat_model._get_request_payload(  # type: ignore[attr-defined]
        [
            HumanMessage(content="first"),
            AIMessage(
                content="answer one",
                additional_kwargs={"reasoning_content": "reasoning one"},
            ),
            HumanMessage(content="second"),
            AIMessage(
                content="answer two",
                additional_kwargs={"reasoning_content": "reasoning two"},
            ),
            HumanMessage(content="third"),
        ]
    )

    assistant_payloads = [
        message for message in payload["messages"] if message["role"] == "assistant"
    ]
    assert assistant_payloads == [
        {
            "role": "assistant",
            "content": "answer one",
            "reasoning_content": "reasoning one",
        },
        {
            "role": "assistant",
            "content": "answer two",
            "reasoning_content": "reasoning two",
        },
    ]


def test_factory_applies_protocol_endpoint_and_exact_model_profiles_with_caller_wins(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import graph_agent_gateway.call.factory as factory_module
    from graph_agent_gateway.call import ProviderProfile, register_provider_profile
    from graph_agent_gateway.call import profiles as provider_profiles

    class FakeChatOpenAI:
        def __init__(self, **kwargs: object) -> None:
            self.kwargs = kwargs

    monkeypatch.setattr(provider_profiles, "_PROVIDER_PROFILES", {})
    monkeypatch.setattr(factory_module, "OpenAICompatibleChatModel", FakeChatOpenAI)

    register_provider_profile(
        "protocol:openai_compatible",
        ProviderProfile(
            init_kwargs={
                "profile_scope": "protocol",
                "default_headers": {"x-profile-layer": "protocol"},
                "stream_usage": True,
                "temperature": 0.1,
            }
        ),
    )
    register_provider_profile(
        "endpoint:profile-endpoint",
        ProviderProfile(
            init_kwargs={
                "profile_scope": "endpoint",
                "default_headers": {"x-profile-layer": "endpoint"},
                "top_p": 0.5,
            }
        ),
    )
    register_provider_profile(
        "endpoint:profile-endpoint:model:vendor/model-a",
        ProviderProfile(
            init_kwargs={
                "profile_scope": "exact",
                "default_headers": {"x-profile-layer": "exact"},
                "temperature": 0.2,
                "extra_body": {"reasoning": {"enabled": True}},
            }
        ),
    )

    factory = factory_module.RouteChatModelFactory(
        credential_provider=StaticCredentialProvider(
            {"endpoint:profile-endpoint": "profile-secret"}
        )
    )

    chat_model = factory.build(
        _route(
            endpoint_id="profile-endpoint",
            route_slug="vendor.model-a",
            provider_model_id="Vendor/Model-A",
            temperature=0.3,
        ),
        temperature=0.9,
    )

    assert isinstance(chat_model, FakeChatOpenAI)
    assert chat_model.kwargs["profile_scope"] == "exact"
    assert chat_model.kwargs["default_headers"] == {"x-profile-layer": "exact"}
    assert chat_model.kwargs["stream_usage"] is True
    assert chat_model.kwargs["top_p"] == pytest.approx(0.5)
    assert chat_model.kwargs["extra_body"] == {"reasoning": {"enabled": True}}
    assert chat_model.kwargs["temperature"] == pytest.approx(0.9)
    assert chat_model.kwargs["model"] == "Vendor/Model-A"
    assert chat_model.kwargs["api_key"] == "profile-secret"


def test_factory_builds_anthropic_chat_model_with_canonical_root_base_url() -> None:
    from langchain_anthropic import ChatAnthropic

    chat_model = _factory().build(
        _route(
            endpoint_id="wavespeed",
            route_slug="claude-sonnet-4-6",
            protocol="anthropic_compatible",
            base_url="https://llm.wavespeed.ai/v1",
            provider_model_id="claude-sonnet-4-6",
            canonical_id="claude-sonnet-4-6",
        ),
        max_tokens=333,
    )

    assert isinstance(chat_model, ChatAnthropic)
    assert chat_model.model == "claude-sonnet-4-6"
    assert chat_model.anthropic_api_url == "https://llm.wavespeed.ai"
    assert chat_model.anthropic_api_key.get_secret_value() == "wavespeed-secret"
    assert chat_model.default_request_timeout == 17.0
    assert chat_model.max_tokens == 333


def test_factory_remaps_anthropic_temperature_from_authored_two_point_scale(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import graph_agent_gateway.call.factory as factory_module

    class FakeChatAnthropic:
        def __init__(self, **kwargs: object) -> None:
            self.kwargs = kwargs

    monkeypatch.setattr(factory_module, "ChatAnthropic", FakeChatAnthropic)

    chat_model = _factory().build(
        _route(
            endpoint_id="wavespeed",
            route_slug="claude-sonnet-4-6",
            protocol="anthropic_compatible",
            base_url="https://llm.wavespeed.ai/v1",
            provider_model_id="claude-sonnet-4-6",
            canonical_id="claude-sonnet-4-6",
        ),
        temperature=1.5,
    )

    assert isinstance(chat_model, FakeChatAnthropic)
    assert chat_model.kwargs["temperature"] == pytest.approx(0.75)


def test_factory_carries_reasoning_effort_to_anthropic_under_the_name_it_uses() -> None:
    """Anthropic sells effort too; it just spells it ``output_config.effort``.

    Measured 2026-08-10: ``ChatAnthropic(effort="medium")`` renders
    ``{'output_config': {'effort': 'medium'}}``. Until this mapping existed the
    setting was dropped while the request was being built, so a Claude route
    could be given an effort and never send one byte of it.
    """
    from langchain_anthropic import ChatAnthropic
    from langchain_core.messages import HumanMessage

    chat_model = _factory().build(
        _route(
            endpoint_id="wavespeed",
            route_slug="claude-opus-5",
            protocol="anthropic_compatible",
            base_url="https://llm.wavespeed.ai/v1",
            provider_model_id="claude-opus-5",
            canonical_id="claude-opus-5",
        ),
        max_tokens=333,
        reasoning_effort="medium",
    )

    assert isinstance(chat_model, ChatAnthropic)
    payload = chat_model._get_request_payload([HumanMessage(content="hi")])
    assert payload["output_config"] == {"effort": "medium"}


def test_factory_carries_reasoning_effort_to_google_under_the_name_it_uses(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Gemini names the same dial ``thinking_level``."""
    import graph_agent_gateway.call.factory as factory_module

    captured: dict[str, object] = {}

    class FakeGoogleModule:
        class ChatGoogleGenerativeAI:
            def __init__(self, **kwargs: object) -> None:
                captured.update(kwargs)

    monkeypatch.setattr(factory_module, "_import_google_chat_module", lambda: FakeGoogleModule)
    _factory().build(
        _route(
            endpoint_id="google",
            route_slug="gemini-3-pro",
            protocol="google_genai",
            base_url="https://generativelanguage.googleapis.com",
            provider_model_id="gemini-3-pro",
            canonical_id="gemini-3-pro",
        ),
        max_tokens=333,
        reasoning_effort="medium",
    )

    assert captured["thinking_level"] == "medium"


def test_factory_keeps_openai_temperature_on_authored_two_point_scale() -> None:
    chat_model = _factory().build(_route(), temperature=1.5)

    assert chat_model.temperature == pytest.approx(1.5)


def test_factory_omits_unset_temperature_from_provider_kwargs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import graph_agent_gateway.call.factory as factory_module

    class FakeChatOpenAI:
        def __init__(self, **kwargs: object) -> None:
            self.kwargs = kwargs

    monkeypatch.setattr(factory_module, "OpenAICompatibleChatModel", FakeChatOpenAI)

    chat_model = _factory().build(_route(temperature=None))

    assert isinstance(chat_model, FakeChatOpenAI)
    assert "temperature" not in chat_model.kwargs


def test_factory_maps_ark_runtime_to_chat_openai_api_v3() -> None:
    from langchain_openai import ChatOpenAI

    chat_model = _factory().build(
        _route(
            endpoint_id="ark-cn",
            route_slug="deepseek-v3",
            protocol="ark_runtime",
            base_url="https://ark.cn-beijing.volces.com",
            provider_model_id="ep-20260525-test",
            canonical_id="deepseek-v3",
        )
    )

    assert isinstance(chat_model, ChatOpenAI)
    assert chat_model.model_name == "ep-20260525-test"
    assert chat_model.openai_api_base == "https://ark.cn-beijing.volces.com/api/v3"
    assert chat_model.openai_api_key.get_secret_value() == "ark-secret"


def test_factory_lazy_imports_chat_google_generative_ai(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeChatGoogleGenerativeAI:
        def __init__(self, **kwargs: object) -> None:
            self.kwargs = kwargs

    monkeypatch.setitem(
        sys.modules,
        "langchain_google_genai",
        types.SimpleNamespace(ChatGoogleGenerativeAI=FakeChatGoogleGenerativeAI),
    )

    chat_model = _factory().build(
        _route(
            endpoint_id="google",
            route_slug="gemini-3-pro",
            protocol="google_genai",
            base_url="https://generativelanguage.googleapis.com",
            provider_model_id="gemini-3-pro",
            canonical_id="gemini-3-pro",
        ),
        temperature=0.2,
        max_tokens=333,
    )

    assert isinstance(chat_model, FakeChatGoogleGenerativeAI)
    assert chat_model.kwargs["model"] == "gemini-3-pro"
    assert chat_model.kwargs["google_api_key"] == "google-secret"
    assert chat_model.kwargs["temperature"] == 0.2
    assert chat_model.kwargs["max_tokens"] == 333


def test_factory_reports_missing_google_extra_at_build_time(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import graph_agent_gateway.call.factory as factory_module
    from graph_agent_gateway.call import RouteChatModelFactory

    real_import_module = factory_module.importlib.import_module

    def fake_import_module(name: str, package: str | None = None) -> object:
        if name == "langchain_google_genai":
            raise ModuleNotFoundError(name)
        return real_import_module(name, package)

    monkeypatch.delitem(sys.modules, "langchain_google_genai", raising=False)
    monkeypatch.setattr(factory_module.importlib, "import_module", fake_import_module)
    factory = RouteChatModelFactory(
        credential_provider=StaticCredentialProvider({"endpoint:google": "google-secret"})
    )

    with pytest.raises(ImportError, match=r"graph-agent-gateway\[google\]|langchain-google-genai"):
        factory.build(
            _route(
                endpoint_id="google",
                route_slug="gemini-3-pro",
                protocol="google_genai",
                base_url="https://generativelanguage.googleapis.com",
                provider_model_id="gemini-3-pro",
                canonical_id="gemini-3-pro",
            )
        )
def _reasoning_stream_chunk(*, reasoning: str = "", content: str = "") -> dict:
    """One raw stream chunk shaped the way an openai-compatible provider sends it.

    The provider puts its reasoning in its own key next to an empty ``content``
    — measured against api.deepseek.com on 2026-08-09, where a plain streamed
    call returns 147 characters of ``reasoning_content`` before the answer.
    """
    return {
        "id": "chunk-1",
        "model": "deepseek-v4-pro",
        "choices": [
            {
                "index": 0,
                "delta": {"role": "assistant", "content": content, "reasoning_content": reasoning},
                "finish_reason": None,
            }
        ],
    }


def test_openai_compatible_stream_keeps_the_providers_reasoning() -> None:
    # Reasoning arrives on the wire in its own field. Dropping it here is what
    # left every surface downstream — the thinking channel, the trace, the UI —
    # with nothing to show, while the provider had been sending it all along.
    from langchain_core.messages import AIMessageChunk

    chat_model = _factory().build(_route())

    generation = chat_model._convert_chunk_to_generation_chunk(  # type: ignore[attr-defined]
        _reasoning_stream_chunk(reasoning="thinking out loud"),
        AIMessageChunk,
        None,
    )

    assert generation is not None
    assert generation.message.additional_kwargs["reasoning_content"] == "thinking out loud"


def test_a_chunk_without_reasoning_says_nothing_about_reasoning() -> None:
    # An absent field is not an empty one: a caller that reads "" as "the model
    # reasoned, and said nothing" would report a thinking step for every plain
    # answer.
    from langchain_core.messages import AIMessageChunk

    chat_model = _factory().build(_route())

    generation = chat_model._convert_chunk_to_generation_chunk(  # type: ignore[attr-defined]
        _reasoning_stream_chunk(content="just the answer"),
        AIMessageChunk,
        None,
    )

    assert generation is not None
    assert "reasoning_content" not in generation.message.additional_kwargs


def test_no_route_can_reach_a_hand_rolled_provider_call() -> None:
    """Every protocol a route can carry is served by a LangChain model.

    `ResolvedRoute.protocol` is a four-value `Literal` on a model that forbids
    extras, and `RouteChatModelFactory.build` returns from a branch for each of
    those four. A dispatch layer below them could only run for a route built by
    skipping the model's own validation, so it is gone — together with the four
    provider SDK clients it was the only caller of.
    """

    import importlib

    from graph_agent_gateway.call import LLMCircuitAndUsageLedger
    from graph_agent_gateway.registry import Protocol

    assert set(Protocol.__args__) == {
        "openai_compatible",
        "anthropic_compatible",
        "google_genai",
        "ark_runtime",
    }

    for module in ("graph_agent_gateway.call.dispatch", "graph_agent_gateway.call.models"):
        with pytest.raises(ModuleNotFoundError):
            importlib.import_module(module)

    gone = {
        "_get_openai_client",
        "_get_anthropic_client",
        "_get_google_client",
        "_get_ark_client",
        "_client_cache_key",
        "_resolve_api_key",
        "reset_stats",
    }
    assert {name for name in gone if hasattr(LLMCircuitAndUsageLedger, name)} == set()
