"""RouteChatModelFactory contract tests."""

from __future__ import annotations

import json
import sys
import types

import pytest
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
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
    import graph_agent_gateway.route_chat_model_factory as factory_module
    from graph_agent_gateway import provider_profiles
    from graph_agent_gateway.provider_profiles import ProviderProfile, register_provider_profile

    class FakeChatOpenAI:
        def __init__(self, **kwargs: object) -> None:
            self.kwargs = kwargs

    monkeypatch.setattr(provider_profiles, "_PROVIDER_PROFILES", {})
    monkeypatch.setattr(factory_module, "ChatOpenAI", FakeChatOpenAI)

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
    assert chat_model.kwargs["top_p"] == 0.5
    assert chat_model.kwargs["extra_body"] == {"reasoning": {"enabled": True}}
    assert chat_model.kwargs["temperature"] == 0.9
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
    import graph_agent_gateway.route_chat_model_factory as factory_module
    from graph_agent_gateway.route_chat_model_factory import RouteChatModelFactory

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


def test_client_manager_no_longer_exposes_legacy_ordinary_chat_dispatch_helpers() -> None:
    from graph_agent_gateway.client_manager import LLMClientManager

    legacy_helpers = {
        "dispatch_provider_call",
        "_dispatch_provider_call",
        "_call_openai_compatible",
        "_call_openai_responses",
        "_call_google_genai",
        "_call_ark_runtime",
        "_call_anthropic_compatible",
        "_call_wavespeed_any_llm",
        "_call_with_token_escalation",
    }

    remaining = {name for name in legacy_helpers if hasattr(LLMClientManager, name)}

    assert remaining == set()


def test_generic_chat_model_default_dispatcher_uses_ordinary_chat_core(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from graph_agent_gateway import ordinary_chat
    from graph_agent_gateway.models import GenericRouteChatModel
    from graph_agent_gateway.registry.schema import ResolvedRoute

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
    captured: list[dict[str, object]] = []

    def dispatch_ordinary_chat(route_arg, messages, **kwargs):
        captured.append({"route": route_arg, "messages": messages, "kwargs": kwargs})
        return {
            "content": "ordinary-core-ok",
            "usage": {"prompt_tokens": 2, "completion_tokens": 3, "total_tokens": 5},
            "finish_reason": "stop",
        }

    monkeypatch.setattr(ordinary_chat, "dispatch_ordinary_chat", dispatch_ordinary_chat)

    result = GenericRouteChatModel(
        route=route,
        credential_provider=StaticCredentialProvider({"endpoint:generic": "generic-secret"}),
        max_tokens=64,
        temperature=0.1,
    ).invoke([HumanMessage(content="hello")])

    assert result.content == "ordinary-core-ok"
    assert captured[0]["route"] is route
    assert captured[0]["messages"] == [{"role": "user", "content": "hello"}]
    assert captured[0]["kwargs"]["max_tokens"] == 64  # type: ignore[index]
    assert captured[0]["kwargs"]["temperature"] == 0.1  # type: ignore[index]


def test_generic_chat_model_dispatches_ordinary_chat_messages_preserving_tool_context() -> None:
    from graph_agent_gateway.models import GenericRouteChatModel
    from graph_agent_gateway.registry.schema import ResolvedRoute

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
    captured: list[dict[str, object]] = []

    def ordinary_chat_dispatcher(route_arg, messages, **kwargs):
        captured.append({"route": route_arg, "messages": messages, "kwargs": kwargs})
        return {
            "content": "ordinary-ok",
            "usage": {"prompt_tokens": 3, "completion_tokens": 5, "total_tokens": 8},
            "finish_reason": "stop",
        }

    chat_model = GenericRouteChatModel(
        route=route,
        credential_provider=StaticCredentialProvider({"endpoint:generic": "generic-secret"}),
        ordinary_chat_dispatcher=ordinary_chat_dispatcher,
        max_tokens=128,
        temperature=0.3,
    )

    result = chat_model.invoke(
        [
            HumanMessage(content="hello"),
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "lookup_weather",
                        "args": {"city": "Shenzhen"},
                        "id": "call_1",
                    }
                ],
            ),
            ToolMessage(content="sunny", tool_call_id="call_1"),
        ]
    )

    assert result.content == "ordinary-ok"
    assert result.usage_metadata == {"input_tokens": 3, "output_tokens": 5, "total_tokens": 8}
    assert len(captured) == 1
    assert captured[0]["route"] is route
    assert captured[0]["kwargs"]["max_tokens"] == 128  # type: ignore[index]
    assert captured[0]["kwargs"]["temperature"] == 0.3  # type: ignore[index]
    messages = captured[0]["messages"]
    assert messages[1]["role"] == "assistant"  # type: ignore[index]
    assert messages[1]["content"] == ""  # type: ignore[index]
    tool_call = messages[1]["tool_calls"][0]  # type: ignore[index]
    assert tool_call["function"]["name"] == "lookup_weather"
    assert json.loads(tool_call["function"]["arguments"]) == {"city": "Shenzhen"}
    assert messages[2]["role"] == "tool"  # type: ignore[index]
    assert messages[2]["tool_call_id"] == "call_1"  # type: ignore[index]


def test_generic_chat_model_runs_langchain_create_agent_tool_loop() -> None:
    from graph_agent_gateway.models import GenericRouteChatModel
    from graph_agent_gateway.registry.schema import ResolvedRoute
    from langchain.agents import create_agent

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
    captured_messages: list[list[dict[str, object]]] = []

    def lookup_weather(city: str) -> str:
        """Look up weather by city."""
        return f"sunny:{city}"

    def ordinary_chat_dispatcher(_route, messages, **_kwargs):
        captured_messages.append(messages)
        if any(message.get("role") == "tool" for message in messages):
            return {
                "content": "final answer",
                "usage": {"prompt_tokens": 4, "completion_tokens": 6, "total_tokens": 10},
                "finish_reason": "stop",
            }
        return {
            "content": "",
            "tool_calls": [
                {
                    "id": "call_1",
                    "type": "function",
                    "function": {
                        "name": "lookup_weather",
                        "arguments": "{\"city\":\"Shenzhen\"}",
                    },
                }
            ],
            "usage": {"prompt_tokens": 2, "completion_tokens": 1, "total_tokens": 3},
            "finish_reason": "tool_calls",
        }

    chat_model = GenericRouteChatModel(
        route=route,
        credential_provider=StaticCredentialProvider({"endpoint:generic": "generic-secret"}),
        ordinary_chat_dispatcher=ordinary_chat_dispatcher,
        max_tokens=128,
        temperature=0.3,
    )
    agent = create_agent(
        model=chat_model,
        tools=[lookup_weather],
        system_prompt="Use tools when needed.",
    )

    result = agent.invoke({"messages": [{"role": "user", "content": "weather?"}]})

    assert result["messages"][-1].content == "final answer"
    assert len(captured_messages) == 2
    assistant_message = next(
        message for message in captured_messages[1] if message.get("role") == "assistant"
    )
    assistant_tool_call = assistant_message["tool_calls"][0]
    assert assistant_tool_call["function"]["name"] == "lookup_weather"
    assert json.loads(assistant_tool_call["function"]["arguments"]) == {"city": "Shenzhen"}
    tool_message = next(message for message in captured_messages[1] if message.get("role") == "tool")
    assert tool_message["role"] == "tool"
    assert tool_message["tool_call_id"] == "call_1"
    assert tool_message["content"] == "sunny:Shenzhen"
