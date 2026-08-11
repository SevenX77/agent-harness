"""LLMClientManager route/runtime-policy behavior tests."""

from __future__ import annotations

import pytest
from pydantic import SecretStr


class StaticCredentialProvider:
    def __init__(self, secrets: dict[str, str]) -> None:
        self.secrets = secrets

    def get(self, ref: str) -> SecretStr:
        return SecretStr(self.secrets[ref])


def _route():
    from graph_agent_gateway.registry import ResolvedRoute

    return ResolvedRoute(
        role_name="graph_agent",
        route_id="openai-direct:gpt-5",
        endpoint_id="openai-direct",
        protocol="openai_compatible",
        base_url="https://api.openai.example/v1",
        credential_ref="endpoint:openai-direct",
        credential_fingerprint="fingerprint-a",
        timeout_seconds=17,
        trust_env=False,
        proxy_env="HTTPS_PROXY",
        provider_model_id="gpt-5",
        canonical_id="gpt-5",
    )


def test_runtime_policy_changes_runtime_client_cache_key_not_credential_fingerprint() -> None:
    from graph_agent_gateway.client_manager import LLMClientManager
    from graph_agent_gateway.registry import ProviderEndpoint, RuntimePolicy, compute_credential_fingerprint

    route = _route()
    base_policy = RuntimePolicy(
        provider_down_ttl_seconds=60,
        probe_timeout_seconds=5,
        token_escalation_rounds=2,
    )
    changed_policy = RuntimePolicy(
        provider_down_ttl_seconds=120,
        probe_timeout_seconds=5,
        token_escalation_rounds=2,
    )

    base_key = LLMClientManager._client_cache_key("openai", route, 17, base_policy)
    changed_key = LLMClientManager._client_cache_key("openai", route, 17, changed_policy)

    assert base_key != changed_key
    assert "openai-direct" in base_key
    assert "fingerprint-a" in base_key
    assert "timeout:17" in base_key
    assert "proxy:HTTPS_PROXY" in base_key

    endpoint = ProviderEndpoint(
        endpoint_id=route.endpoint_id,
        protocol=route.protocol,
        base_url=route.base_url,
        credential_ref=route.credential_ref,
        timeout_seconds=route.timeout_seconds,
        trust_env=route.trust_env,
        proxy_env=route.proxy_env,
    )
    assert compute_credential_fingerprint(endpoint) == compute_credential_fingerprint(endpoint)


def test_resolve_api_key_uses_credential_provider_ref() -> None:
    from graph_agent_gateway.client_manager import LLMClientManager

    route = _route()
    provider = StaticCredentialProvider({"endpoint:openai-direct": "secret-from-provider"})

    assert (
        LLMClientManager._resolve_api_key(route, credential_provider=provider)
        == "secret-from-provider"
    )


def test_provider_down_ttl_comes_from_runtime_policy(monkeypatch) -> None:
    from graph_agent_gateway import client_manager
    from graph_agent_gateway.client_manager import LLMClientManager
    from graph_agent_gateway.registry import RuntimePolicy

    route = _route()
    policy = RuntimePolicy(provider_down_ttl_seconds=9)
    LLMClientManager._provider_down_cache.clear()
    monkeypatch.setattr(client_manager.time, "monotonic", lambda: 100.0)

    LLMClientManager.mark_provider_down(route, RuntimeError("boom"), policy)

    down_key = LLMClientManager._make_down_key(route.endpoint_id, route.provider_model_id)
    assert LLMClientManager._provider_down_cache[down_key] == 109.0
    monkeypatch.setattr(client_manager.time, "monotonic", lambda: 108.0)
    assert LLMClientManager.is_provider_marked_down(route, policy) is True
    monkeypatch.setattr(client_manager.time, "monotonic", lambda: 110.0)
    assert LLMClientManager.is_provider_marked_down(route, policy) is False


def test_token_escalation_rounds_come_from_runtime_policy() -> None:
    from graph_agent_gateway import ordinary_chat
    from graph_agent_gateway.registry import CapabilityValue, RuntimePolicy

    route = _route().model_copy(
        update={
            "capabilities": {
                "max_output_tokens": CapabilityValue(value=8, source="manual"),
            }
        }
    )
    calls: list[int] = []

    def invoke(token_budget: int) -> dict[str, object]:
        calls.append(token_budget)
        return {
            "content": "partial" if len(calls) == 1 else "ok",
            "finish_reason": "length" if len(calls) == 1 else "stop",
            "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
        }

    result = ordinary_chat._call_with_token_escalation(
        route,
        2,
        invoke,
        runtime_policy=RuntimePolicy(token_escalation_rounds=2),
    )

    assert result["content"] == "ok"
    assert calls == [2, 4]

    calls.clear()
    result = ordinary_chat._call_with_token_escalation(
        route,
        2,
        invoke,
        runtime_policy=RuntimePolicy(token_escalation_rounds=0),
    )

    assert result["content"] == "partial"
    assert calls == [2]


def test_anthropic_thinking_rejects_max_tokens_below_budget_floor(monkeypatch) -> None:
    import pytest
    from graph_agent_gateway import ordinary_chat

    def fake_messages_create(_client: object, kwargs: dict[str, object]) -> dict[str, object]:
        raise AssertionError(f"provider should not be called with invalid thinking budget: {kwargs}")

    monkeypatch.setattr(ordinary_chat, "_anthropic_messages_create", fake_messages_create)

    with pytest.raises(ValueError, match="thinking budget"):
        ordinary_chat._call_anthropic_compatible(
            object(),  # type: ignore[arg-type]
            "claude-sonnet-4-6",
            [{"role": "user", "content": "hello"}],
            512,
            0,
            reasoning=True,
        )


def test_anthropic_thinking_prefers_adaptive_without_budget_tokens(monkeypatch) -> None:
    from graph_agent_gateway import ordinary_chat

    captured: list[dict[str, object]] = []

    def fake_messages_create(_client: object, kwargs: dict[str, object]) -> dict[str, object]:
        captured.append(dict(kwargs))
        return {
            "content": [{"type": "text", "text": "ok"}],
            "usage": {"input_tokens": 1, "output_tokens": 1},
            "stop_reason": "end_turn",
        }

    monkeypatch.setattr(ordinary_chat, "_anthropic_messages_create", fake_messages_create)

    result = ordinary_chat._call_anthropic_compatible(
        object(),  # type: ignore[arg-type]
        "claude-sonnet-4-6",
        [{"role": "user", "content": "hello"}],
        4097,
        0,
        reasoning=True,
    )

    assert result["content"] == "ok"
    thinking = captured[0]["thinking"]
    assert isinstance(thinking, dict)
    assert thinking == {"type": "adaptive"}


def test_anthropic_request_mapper_forces_adaptive_thinking_payload(monkeypatch) -> None:
    from graph_agent_gateway import ordinary_chat

    captured: list[dict[str, object]] = []

    def fake_messages_create(_client: object, kwargs: dict[str, object]) -> dict[str, object]:
        captured.append(dict(kwargs))
        return {
            "content": [{"type": "text", "text": "ok"}],
            "usage": {"input_tokens": 1, "output_tokens": 1},
            "stop_reason": "end_turn",
        }

    monkeypatch.setattr(ordinary_chat, "_anthropic_messages_create", fake_messages_create)

    result = ordinary_chat._call_anthropic_compatible(
        object(),  # type: ignore[arg-type]
        "claude-custom-route-alias",
        [{"role": "user", "content": "hello"}],
        4097,
        0,
        reasoning=True,
        request_mapper_id="anthropic_thinking_adaptive",
    )

    assert result["content"] == "ok"
    assert captured[0]["thinking"] == {"type": "adaptive"}


def test_anthropic_uses_configured_thinking_budget_only_for_manual_fallback(monkeypatch) -> None:
    from graph_agent_gateway import ordinary_chat

    captured: list[dict[str, object]] = []

    def fake_messages_create(_client: object, kwargs: dict[str, object]) -> dict[str, object]:
        captured.append(dict(kwargs))
        if len(captured) == 1:
            raise RuntimeError("adaptive thinking is not supported")
        return {
            "content": [{"type": "text", "text": "ok"}],
            "usage": {"input_tokens": 1, "output_tokens": 1},
            "stop_reason": "end_turn",
        }

    monkeypatch.setattr(ordinary_chat, "_anthropic_messages_create", fake_messages_create)

    ordinary_chat._call_anthropic_compatible(
        object(),  # type: ignore[arg-type]
        "claude-sonnet-4-6",
        [{"role": "user", "content": "hello"}],
        8192,
        0,
        reasoning=True,
        thinking_budget_tokens=2048,
    )

    assert captured[0]["thinking"] == {"type": "adaptive"}
    fallback_thinking = captured[1]["thinking"]
    assert isinstance(fallback_thinking, dict)
    assert fallback_thinking == {"type": "enabled", "budget_tokens": 2048}


def test_anthropic_haiku_thinking_uses_manual_budget_without_adaptive_attempt(monkeypatch) -> None:
    from graph_agent_gateway import ordinary_chat

    captured: list[dict[str, object]] = []

    def fake_messages_create(_client: object, kwargs: dict[str, object]) -> dict[str, object]:
        captured.append(dict(kwargs))
        return {
            "content": [{"type": "text", "text": "ok"}],
            "usage": {"input_tokens": 1, "output_tokens": 1},
            "stop_reason": "end_turn",
        }

    monkeypatch.setattr(ordinary_chat, "_anthropic_messages_create", fake_messages_create)

    result = ordinary_chat._call_anthropic_compatible(
        object(),  # type: ignore[arg-type]
        "claude-haiku-4-5-20251001",
        [{"role": "user", "content": "hello"}],
        2048,
        0,
        reasoning=True,
    )

    assert result["content"] == "ok"
    assert len(captured) == 1
    thinking = captured[0]["thinking"]
    assert isinstance(thinking, dict)
    assert thinking == {"type": "enabled", "budget_tokens": 2047}


def test_anthropic_system_only_messages_keep_required_user_turn() -> None:
    from graph_agent_gateway.ordinary_chat import _split_anthropic_messages

    system_text, api_messages = _split_anthropic_messages(
        [{"role": "system", "content": "You are a v0.3.0 agent prompt."}]
    )

    assert system_text == "You are a v0.3.0 agent prompt."
    assert api_messages == [{"role": "user", "content": "Proceed."}]


def test_openai_runtime_settings_map_to_chat_completion_kwargs() -> None:
    from graph_agent_gateway import ordinary_chat

    captured: list[dict[str, object]] = []

    class FakeCompletions:
        def create(self, **kwargs: object) -> dict[str, object]:
            captured.append(dict(kwargs))
            return {
                "choices": [
                    {
                        "message": {"content": "ok"},
                        "finish_reason": "stop",
                    }
                ],
                "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
            }

    class FakeClient:
        chat = type("Chat", (), {"completions": FakeCompletions()})()

    result = ordinary_chat._call_openai_compatible(
        FakeClient(),  # type: ignore[arg-type]
        "gpt-5",
        [{"role": "user", "content": "hello"}],
        333,
        0.4,
        top_p=0.9,
        stop_sequences=["END"],
        seed=42,
        parallel_tool_calls=False,
        structured_output={
            "mode": "json_schema",
            "json_schema": {"name": "Answer", "schema": {"type": "object"}},
            "strict": True,
        },
        reasoning_effort="medium",
    )

    assert result["content"] == "ok"
    assert captured == [
        {
            "model": "gpt-5",
            "messages": [{"role": "user", "content": "hello"}],
            "max_tokens": 333,
            "temperature": 0.4,
            "top_p": 0.9,
            "stop": ["END"],
            "seed": 42,
            "parallel_tool_calls": False,
            "reasoning_effort": "medium",
            "response_format": {
                "type": "json_schema",
                "json_schema": {"name": "Answer", "schema": {"type": "object"}, "strict": True},
            },
        }
    ]


def test_openai_runtime_settings_omit_unset_temperature() -> None:
    from graph_agent_gateway import ordinary_chat

    captured: list[dict[str, object]] = []

    class FakeCompletions:
        def create(self, **kwargs: object) -> dict[str, object]:
            captured.append(dict(kwargs))
            return {
                "choices": [
                    {
                        "message": {"content": "ok"},
                        "finish_reason": "stop",
                    }
                ],
                "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
            }

    class FakeClient:
        chat = type("Chat", (), {"completions": FakeCompletions()})()

    result = ordinary_chat._call_openai_compatible(
        FakeClient(),  # type: ignore[arg-type]
        "gpt-5",
        [{"role": "user", "content": "hello"}],
        333,
        None,  # type: ignore[arg-type]
    )

    assert result["content"] == "ok"
    assert "temperature" not in captured[0]


def test_dispatch_keeps_openai_temperature_on_authored_two_point_scale(monkeypatch) -> None:
    from graph_agent_gateway import client_manager, ordinary_chat
    from graph_agent_gateway.registry import RuntimePolicy

    route = _route()
    captured: list[dict[str, object]] = []

    monkeypatch.setattr(
        client_manager.LLMClientManager,
        "_get_openai_client",
        classmethod(lambda cls, route, **kwargs: object()),
    )

    def fake_call_openai_compatible(*args: object, **kwargs: object) -> dict[str, object]:
        captured.append({"args": args, "kwargs": kwargs})
        return {
            "content": "ok",
            "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
            "finish_reason": "stop",
        }

    monkeypatch.setattr(ordinary_chat, "_call_openai_compatible", fake_call_openai_compatible)

    ordinary_chat.dispatch_ordinary_chat(
        route,
        [{"role": "user", "content": "hello"}],
        max_tokens=256,
        temperature=1.5,
        runtime_policy=RuntimePolicy(token_escalation_rounds=0),
    )

    assert captured[0]["args"][4] == pytest.approx(1.5)


def test_openai_call_method_responses_uses_responses_api(monkeypatch) -> None:
    from graph_agent_gateway import ordinary_chat
    from graph_agent_gateway.client_manager import LLMClientManager
    from graph_agent_gateway.registry import ResolvedRoute, RuntimePolicy

    captured: list[dict[str, object]] = []

    class FakeResponses:
        def create(self, **kwargs: object) -> dict[str, object]:
            captured.append(dict(kwargs))
            return {
                "output_text": "ok",
                "usage": {"input_tokens": 1, "output_tokens": 1, "total_tokens": 2},
                "status": "completed",
            }

    class FakeClient:
        responses = FakeResponses()

    route = ResolvedRoute(
        role_name="writer",
        route_id="openai:gpt-5",
        endpoint_id="openai",
        protocol="openai_compatible",
        base_url="https://api.openai.example/v1",
        credential_ref="endpoint:openai",
        credential_fingerprint="fp",
        provider_model_id="gpt-5",
        canonical_id="gpt-5",
    )

    monkeypatch.setattr(
        LLMClientManager,
        "_get_openai_client",
        classmethod(lambda cls, route, runtime_policy: FakeClient()),
    )

    result = ordinary_chat.dispatch_ordinary_chat(
        route,
        [{"role": "user", "content": "hello"}],
        max_tokens=333,
        temperature=0.4,
        runtime_policy=RuntimePolicy(token_escalation_rounds=0),
        top_p=0.9,
        reasoning_effort="medium",
        call_method_id="openai_responses",
        request_mapper_id="openai_responses_reasoning",
    )

    assert result["content"] == "ok"
    assert captured == [
        {
            "model": "gpt-5",
            "input": [{"role": "user", "content": "hello"}],
            "max_output_tokens": 333,
            "temperature": 0.4,
            "top_p": 0.9,
            "reasoning": {"effort": "medium"},
        }
    ]


def test_dispatch_remaps_anthropic_temperature_to_provider_scale(monkeypatch) -> None:
    from graph_agent_gateway import client_manager, ordinary_chat
    from graph_agent_gateway.registry import RuntimePolicy

    route = _route().model_copy(
        update={
            "route_id": "anthropic:claude-sonnet-4-6",
            "endpoint_id": "anthropic",
            "protocol": "anthropic_compatible",
            "base_url": "https://api.anthropic.example",
            "provider_model_id": "claude-sonnet-4-6",
            "canonical_id": "claude-sonnet-4-6",
        }
    )
    captured: list[dict[str, object]] = []

    monkeypatch.setattr(
        client_manager.LLMClientManager,
        "_get_anthropic_client",
        classmethod(lambda cls, route, **kwargs: object()),
    )

    def fake_call_anthropic_compatible(*args: object, **kwargs: object) -> dict[str, object]:
        captured.append({"args": args, "kwargs": kwargs})
        return {
            "content": "ok",
            "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
            "finish_reason": "end_turn",
        }

    monkeypatch.setattr(ordinary_chat, "_call_anthropic_compatible", fake_call_anthropic_compatible)

    ordinary_chat.dispatch_ordinary_chat(
        route,
        [{"role": "user", "content": "hello"}],
        max_tokens=256,
        temperature=1.5,
        runtime_policy=RuntimePolicy(token_escalation_rounds=0),
    )

    assert captured[0]["args"][4] == pytest.approx(0.75)


def test_anthropic_runtime_settings_map_to_messages_kwargs(monkeypatch) -> None:
    from graph_agent_gateway import ordinary_chat

    captured: list[dict[str, object]] = []

    def fake_messages_create(_client: object, kwargs: dict[str, object]) -> dict[str, object]:
        captured.append(dict(kwargs))
        return {
            "content": [{"type": "text", "text": "ok"}],
            "usage": {"input_tokens": 1, "output_tokens": 1},
            "stop_reason": "end_turn",
        }

    monkeypatch.setattr(ordinary_chat, "_anthropic_messages_create", fake_messages_create)

    result = ordinary_chat._call_anthropic_compatible(
        object(),  # type: ignore[arg-type]
        "claude-haiku-4-5-20251001",
        [{"role": "user", "content": "hello"}],
        2048,
        0.4,
        top_p=0.9,
        stop_sequences=["END"],
        tools=[
            {
                "type": "function",
                "function": {
                    "name": "lookup",
                    "parameters": {"type": "object", "properties": {}},
                },
            }
        ],
        tool_choice="auto",
    )

    assert result["content"] == "ok"
    assert captured[0]["top_p"] == 0.9
    assert captured[0]["stop_sequences"] == ["END"]
    assert captured[0]["tool_choice"] == {"type": "auto"}


def test_google_genai_runtime_settings_map_to_generate_content_config() -> None:
    from graph_agent_gateway import ordinary_chat

    captured: list[dict[str, object]] = []

    class FakeModels:
        def generate_content(self, **kwargs: object) -> dict[str, object]:
            captured.append(dict(kwargs))
            return {
                "text": "ok",
                "usage_metadata": {
                    "prompt_token_count": 2,
                    "candidates_token_count": 3,
                    "total_token_count": 5,
                },
                "candidates": [{"finish_reason": "STOP"}],
            }

    class FakeClient:
        models = FakeModels()

    result = ordinary_chat._call_google_genai(
        FakeClient(),
        "gemini-3-pro",
        [
            {"role": "system", "content": "You are concise."},
            {"role": "user", "content": "hello"},
        ],
        512,
        0.2,
        top_p=0.8,
        stop_sequences=["END"],
        seed=7,
        structured_output={
            "mode": "json_schema",
            "json_schema": {"name": "Answer", "schema": {"type": "object"}},
        },
        reasoning=True,
        reasoning_effort="high",
    )

    assert result["content"] == "ok"
    assert captured == [
        {
            "model": "gemini-3-pro",
            "contents": [
                {"role": "user", "parts": [{"text": "hello"}]},
            ],
            "config": {
                "system_instruction": "You are concise.",
                "max_output_tokens": 512,
                "temperature": 0.2,
                "top_p": 0.8,
                "stop_sequences": ["END"],
                "seed": 7,
                "response_mime_type": "application/json",
                "response_schema": {"name": "Answer", "schema": {"type": "object"}},
                "thinking_config": {"thinking_level": "high"},
            },
        }
    ]


def test_dispatch_google_genai_uses_route_endpoint_and_runtime_policy(monkeypatch) -> None:
    from graph_agent_gateway import client_manager, ordinary_chat
    from graph_agent_gateway.registry import RuntimePolicy

    route = _route().model_copy(
        update={
            "route_id": "google:gemini-3-pro",
            "endpoint_id": "google",
            "protocol": "google_genai",
            "base_url": "https://generativelanguage.googleapis.com",
            "provider_model_id": "gemini-3-pro",
            "canonical_id": "gemini-3-pro",
        }
    )
    captured: list[dict[str, object]] = []

    def fake_get_google_client(route_arg: object, runtime_policy: object) -> object:
        captured.append({"route": route_arg, "runtime_policy": runtime_policy})
        return object()

    def fake_call_google_genai(*args: object, **kwargs: object) -> dict[str, object]:
        captured.append({"args": args, "kwargs": kwargs})
        return {
            "content": "ok",
            "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
            "finish_reason": "STOP",
        }

    monkeypatch.setattr(client_manager.LLMClientManager, "_get_google_client", fake_get_google_client)
    monkeypatch.setattr(ordinary_chat, "_call_google_genai", fake_call_google_genai)

    result = ordinary_chat.dispatch_ordinary_chat(
        route,
        [{"role": "user", "content": "hello"}],
        max_tokens=256,
        temperature=0.1,
        runtime_policy=RuntimePolicy(token_escalation_rounds=0),
        top_p=0.95,
        reasoning=True,
        reasoning_effort="high",
    )

    assert result["content"] == "ok"
    assert captured[0] == {
        "route": route,
        "runtime_policy": RuntimePolicy(token_escalation_rounds=0),
    }
    assert captured[1]["kwargs"] == {
        "top_p": 0.95,
        "stop_sequences": None,
        "seed": None,
        "structured_output": None,
        "reasoning": True,
        "thinking_budget_tokens": None,
        "reasoning_effort": "high",
    }


def test_ark_runtime_factory_maps_to_chat_openai_kwargs() -> None:
    from graph_agent_gateway.route_chat_model_factory import RouteChatModelFactory
    from langchain_openai import ChatOpenAI

    route = _route().model_copy(
        update={
            "route_id": "ark-cn:deepseek-v3",
            "endpoint_id": "ark-cn",
            "protocol": "ark_runtime",
            "base_url": "https://ark.cn-beijing.volces.com",
            "credential_ref": "endpoint:ark-cn",
            "provider_model_id": "ep-20260525-test",
            "canonical_id": "deepseek-v3",
        }
    )
    factory = RouteChatModelFactory(
        credential_provider=StaticCredentialProvider({"endpoint:ark-cn": "ark-secret"})
    )

    chat_model = factory.build(route)

    assert isinstance(chat_model, ChatOpenAI)
    assert chat_model.model_name == "ep-20260525-test"
    assert chat_model.openai_api_base == "https://ark.cn-beijing.volces.com/api/v3"
    assert chat_model.openai_api_key.get_secret_value() == "ark-secret"


def test_ark_runtime_target_no_longer_uses_ark_sdk_client(monkeypatch) -> None:
    from graph_agent_gateway import client_manager
    from graph_agent_gateway.route_chat_model_factory import RouteChatModelFactory
    from langchain_openai import ChatOpenAI

    def fail_if_ark_sdk_path_is_used(*_args: object, **_kwargs: object) -> object:
        raise AssertionError("ark_runtime target should be ChatOpenAI, not Ark SDK")

    monkeypatch.setattr(
        client_manager.LLMClientManager,
        "_get_ark_client",
        fail_if_ark_sdk_path_is_used,
    )
    route = _route().model_copy(
        update={
            "route_id": "ark-cn:deepseek-v3",
            "endpoint_id": "ark-cn",
            "protocol": "ark_runtime",
            "base_url": "https://ark.cn-beijing.volces.com/api/v3",
            "credential_ref": "endpoint:ark-cn",
            "provider_model_id": "ep-20260525-test",
            "canonical_id": "deepseek-v3",
        }
    )

    chat_model = RouteChatModelFactory(
        credential_provider=StaticCredentialProvider({"endpoint:ark-cn": "ark-secret"})
    ).build(route)

    assert isinstance(chat_model, ChatOpenAI)
