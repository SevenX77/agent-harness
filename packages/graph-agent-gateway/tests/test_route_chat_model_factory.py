"""RouteChatModelFactory contract tests."""

from __future__ import annotations

import sys
import types

import pytest
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
    temperature: float = 0.2,
    max_tokens: int = 333,
):
    from graph_agent_gateway.registry.schema import EffectiveRuntimeSetting, ResolvedRoute

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
        effective_runtime_settings={
            "temperature": EffectiveRuntimeSetting(value=temperature, source="route_setting"),
            "max_output_tokens": EffectiveRuntimeSetting(value=max_tokens, source="route_setting"),
        },
    )


def _factory():
    from graph_agent_gateway.route_chat_model_factory import RouteChatModelFactory

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


def test_factory_builds_openai_compatible_chat_openai_with_route_kwargs() -> None:
    from langchain_openai import ChatOpenAI

    chat_model = _factory().build(_route())

    assert isinstance(chat_model, ChatOpenAI)
    assert chat_model.model_name == "openai/gpt-5"
    assert chat_model.openai_api_base == "https://openrouter.example/api/v1"
    assert chat_model.openai_api_key.get_secret_value() == "openrouter-secret"
    assert chat_model.request_timeout == 17.0
    assert chat_model.temperature == 0.2
    assert chat_model.max_tokens == 333
    assert chat_model.stream_usage is True


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
        )
    )

    assert isinstance(chat_model, ChatAnthropic)
    assert chat_model.model == "claude-sonnet-4-6"
    assert chat_model.anthropic_api_url == "https://llm.wavespeed.ai"
    assert chat_model.anthropic_api_key.get_secret_value() == "wavespeed-secret"
    assert chat_model.default_request_timeout == 17.0
    assert chat_model.max_tokens == 333


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
        )
    )

    assert isinstance(chat_model, FakeChatGoogleGenerativeAI)
    assert chat_model.kwargs["model"] == "gemini-3-pro"
    assert chat_model.kwargs["google_api_key"] == "google-secret"
    assert chat_model.kwargs["temperature"] == 0.2
    assert chat_model.kwargs["max_tokens"] == 333


def test_factory_reports_missing_google_extra_at_build_time(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from graph_agent_gateway.route_chat_model_factory import RouteChatModelFactory

    monkeypatch.delitem(sys.modules, "langchain_google_genai", raising=False)
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


def test_factory_returns_generic_chat_model_for_nonstandard_protocol() -> None:
    from graph_agent_gateway.registry.schema import ResolvedRoute
    from langchain_core.language_models.chat_models import BaseChatModel

    route = ResolvedRoute.model_construct(
        role_name="graph_agent",
        route_id="generic:custom-model",
        endpoint_id="generic",
        protocol="custom_chat_protocol",
        base_url="https://generic.example/chat",
        credential_ref="endpoint:generic",
        credential_fingerprint="fingerprint-a",
        timeout_seconds=17,
        trust_env=False,
        provider_model_id="custom-model",
        canonical_id="custom-model",
        effective_runtime_settings={},
    )

    chat_model = _factory().build(route)

    assert isinstance(chat_model, BaseChatModel)
    assert chat_model.__class__.__name__ == "GenericRouteChatModel"


def test_generic_chat_model_fails_loud_until_ordinary_chat_core_exists() -> None:
    from graph_agent_gateway.registry.schema import ResolvedRoute
    from langchain_core.messages import HumanMessage

    route = ResolvedRoute.model_construct(
        role_name="graph_agent",
        route_id="generic:custom-model",
        endpoint_id="generic",
        protocol="custom_chat_protocol",
        base_url="https://generic.example/chat",
        credential_ref="endpoint:generic",
        credential_fingerprint="fingerprint-a",
        timeout_seconds=17,
        trust_env=False,
        provider_model_id="custom-model",
        canonical_id="custom-model",
        effective_runtime_settings={},
    )

    chat_model = _factory().build(route)

    with pytest.raises(NotImplementedError, match="GenericRouteChatModel.*ordinary chat"):
        chat_model.invoke([HumanMessage(content="hello")])
