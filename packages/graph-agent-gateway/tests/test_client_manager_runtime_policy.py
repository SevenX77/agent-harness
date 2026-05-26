"""LLMClientManager route/runtime-policy behavior tests."""

from __future__ import annotations

from pydantic import SecretStr


def _route():
    from graph_agent_gateway.registry.schema import ResolvedRoute

    return ResolvedRoute(
        role_name="graph_agent",
        route_id="openai-direct:gpt-5",
        endpoint_id="openai-direct",
        protocol="openai_compatible",
        base_url="https://api.openai.example/v1",
        api_key=SecretStr("secret"),
        credential_fingerprint="fingerprint-a",
        timeout_seconds=17,
        trust_env=False,
        proxy_env="HTTPS_PROXY",
        provider_model_id="gpt-5",
        canonical_id="gpt-5",
        display_name="GPT-5",
    )


def test_runtime_policy_changes_runtime_client_cache_key_not_credential_fingerprint() -> None:
    from graph_agent_gateway.client_manager import LLMClientManager
    from graph_agent_gateway.registry.schema import ProviderEndpoint, RuntimePolicy
    from graph_agent_gateway.registry.storage import compute_credential_fingerprint

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
        display_name=route.display_name,
        protocol=route.protocol,
        base_url=route.base_url,
        api_key=route.api_key,
        timeout_seconds=route.timeout_seconds,
        trust_env=route.trust_env,
        proxy_env=route.proxy_env,
    )
    assert compute_credential_fingerprint(endpoint) == compute_credential_fingerprint(endpoint)


def test_provider_down_ttl_comes_from_runtime_policy(monkeypatch) -> None:
    from graph_agent_gateway import client_manager
    from graph_agent_gateway.client_manager import LLMClientManager
    from graph_agent_gateway.registry.schema import RuntimePolicy

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
    from graph_agent_gateway.client_manager import LLMClientManager
    from graph_agent_gateway.registry.schema import CapabilityValue, RuntimePolicy

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

    result = LLMClientManager._call_with_token_escalation(
        route,
        2,
        invoke,
        runtime_policy=RuntimePolicy(token_escalation_rounds=2),
    )

    assert result["content"] == "ok"
    assert calls == [2, 4]

    calls.clear()
    result = LLMClientManager._call_with_token_escalation(
        route,
        2,
        invoke,
        runtime_policy=RuntimePolicy(token_escalation_rounds=0),
    )

    assert result["content"] == "partial"
    assert calls == [2]


def test_anthropic_thinking_rejects_max_tokens_below_budget_floor(monkeypatch) -> None:
    import pytest
    from graph_agent_gateway import client_manager
    from graph_agent_gateway.client_manager import LLMClientManager

    def fake_messages_create(_client: object, kwargs: dict[str, object]) -> dict[str, object]:
        raise AssertionError(f"provider should not be called with invalid thinking budget: {kwargs}")

    monkeypatch.setattr(client_manager, "_anthropic_messages_create", fake_messages_create)

    with pytest.raises(ValueError, match="thinking budget"):
        LLMClientManager._call_anthropic_compatible(
            object(),  # type: ignore[arg-type]
            "claude-sonnet-4-6",
            [{"role": "user", "content": "hello"}],
            512,
            0,
            reasoning=True,
        )


def test_anthropic_thinking_prefers_adaptive_without_budget_tokens(monkeypatch) -> None:
    from graph_agent_gateway import client_manager
    from graph_agent_gateway.client_manager import LLMClientManager

    captured: list[dict[str, object]] = []

    def fake_messages_create(_client: object, kwargs: dict[str, object]) -> dict[str, object]:
        captured.append(dict(kwargs))
        return {
            "content": [{"type": "text", "text": "ok"}],
            "usage": {"input_tokens": 1, "output_tokens": 1},
            "stop_reason": "end_turn",
        }

    monkeypatch.setattr(client_manager, "_anthropic_messages_create", fake_messages_create)

    result = LLMClientManager._call_anthropic_compatible(
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


def test_anthropic_uses_configured_thinking_budget_only_for_manual_fallback(monkeypatch) -> None:
    from graph_agent_gateway import client_manager
    from graph_agent_gateway.client_manager import LLMClientManager

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

    monkeypatch.setattr(client_manager, "_anthropic_messages_create", fake_messages_create)

    LLMClientManager._call_anthropic_compatible(
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
    from graph_agent_gateway import client_manager
    from graph_agent_gateway.client_manager import LLMClientManager

    captured: list[dict[str, object]] = []

    def fake_messages_create(_client: object, kwargs: dict[str, object]) -> dict[str, object]:
        captured.append(dict(kwargs))
        return {
            "content": [{"type": "text", "text": "ok"}],
            "usage": {"input_tokens": 1, "output_tokens": 1},
            "stop_reason": "end_turn",
        }

    monkeypatch.setattr(client_manager, "_anthropic_messages_create", fake_messages_create)

    result = LLMClientManager._call_anthropic_compatible(
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
    from graph_agent_gateway.client_manager import _split_anthropic_messages

    system_text, api_messages = _split_anthropic_messages(
        [{"role": "system", "content": "You are a v0.3.0 agent prompt."}]
    )

    assert system_text == "You are a v0.3.0 agent prompt."
    assert api_messages == [{"role": "user", "content": "Proceed."}]


def test_openai_runtime_settings_map_to_chat_completion_kwargs() -> None:
    from graph_agent_gateway.client_manager import LLMClientManager

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

    result = LLMClientManager._call_openai_compatible(
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


def test_anthropic_runtime_settings_map_to_messages_kwargs(monkeypatch) -> None:
    from graph_agent_gateway import client_manager
    from graph_agent_gateway.client_manager import LLMClientManager

    captured: list[dict[str, object]] = []

    def fake_messages_create(_client: object, kwargs: dict[str, object]) -> dict[str, object]:
        captured.append(dict(kwargs))
        return {
            "content": [{"type": "text", "text": "ok"}],
            "usage": {"input_tokens": 1, "output_tokens": 1},
            "stop_reason": "end_turn",
        }

    monkeypatch.setattr(client_manager, "_anthropic_messages_create", fake_messages_create)

    result = LLMClientManager._call_anthropic_compatible(
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
    from graph_agent_gateway.client_manager import LLMClientManager

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

    result = LLMClientManager._call_google_genai(
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
    from graph_agent_gateway import client_manager
    from graph_agent_gateway.client_manager import LLMClientManager
    from graph_agent_gateway.registry.schema import RuntimePolicy

    route = _route().model_copy(
        update={
            "route_id": "google:gemini-3-pro",
            "endpoint_id": "google",
            "protocol": "google_genai",
            "base_url": "https://generativelanguage.googleapis.com",
            "provider_model_id": "gemini-3-pro",
            "canonical_id": "gemini-3-pro",
            "display_name": "Gemini 3 Pro",
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
    monkeypatch.setattr(client_manager.LLMClientManager, "_call_google_genai", fake_call_google_genai)

    result = LLMClientManager._dispatch_provider_call(
        route,
        [{"role": "user", "content": "hello"}],
        256,
        0.1,
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


def test_ark_runtime_settings_map_to_official_sdk_chat_completion_kwargs() -> None:
    from graph_agent_gateway.client_manager import LLMClientManager

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
                "usage": {"prompt_tokens": 1, "completion_tokens": 2, "total_tokens": 3},
            }

    class FakeClient:
        chat = type("Chat", (), {"completions": FakeCompletions()})()

    result = LLMClientManager._call_ark_runtime(
        FakeClient(),
        "ep-20260525-test",
        [{"role": "user", "content": "hello"}],
        4096,
        0.7,
        top_p=0.9,
        stop_sequences=["END"],
        parallel_tool_calls=False,
        reasoning_effort="high",
    )

    assert result["content"] == "ok"
    assert captured == [
        {
            "model": "ep-20260525-test",
            "messages": [{"role": "user", "content": "hello"}],
            "max_tokens": 4096,
            "temperature": 0.7,
            "top_p": 0.9,
            "stop": ["END"],
            "parallel_tool_calls": False,
            "reasoning_effort": "high",
        }
    ]


def test_dispatch_ark_runtime_uses_official_sdk_client_not_openai_path(monkeypatch) -> None:
    from graph_agent_gateway import client_manager
    from graph_agent_gateway.client_manager import LLMClientManager
    from graph_agent_gateway.registry.schema import RuntimePolicy

    route = _route().model_copy(
        update={
            "route_id": "ark-cn:deepseek-v3",
            "endpoint_id": "ark-cn",
            "protocol": "ark_runtime",
            "base_url": "https://ark.cn-beijing.volces.com/api/v3",
            "provider_model_id": "ep-20260525-test",
            "canonical_id": "deepseek-v3",
            "display_name": "DeepSeek V3 via Ark",
        }
    )
    captured: list[dict[str, object]] = []

    def fake_get_openai_client(*_args: object, **_kwargs: object) -> object:
        raise AssertionError("ark_runtime must not use OpenAI-compatible client")

    def fake_get_ark_client(route_arg: object, runtime_policy: object) -> object:
        captured.append({"route": route_arg, "runtime_policy": runtime_policy})
        return object()

    def fake_call_ark_runtime(*args: object, **kwargs: object) -> dict[str, object]:
        captured.append({"args": args, "kwargs": kwargs})
        return {
            "content": "ok",
            "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
            "finish_reason": "stop",
        }

    monkeypatch.setattr(client_manager.LLMClientManager, "_get_openai_client", fake_get_openai_client)
    monkeypatch.setattr(client_manager.LLMClientManager, "_get_ark_client", fake_get_ark_client)
    monkeypatch.setattr(client_manager.LLMClientManager, "_call_ark_runtime", fake_call_ark_runtime)

    result = LLMClientManager._dispatch_provider_call(
        route,
        [{"role": "user", "content": "hello"}],
        512,
        0.2,
        runtime_policy=RuntimePolicy(token_escalation_rounds=0),
        top_p=0.8,
        reasoning_effort="high",
    )

    assert result["content"] == "ok"
    assert captured[0] == {
        "route": route,
        "runtime_policy": RuntimePolicy(token_escalation_rounds=0),
    }
    assert captured[1]["kwargs"]["top_p"] == 0.8
    assert captured[1]["kwargs"]["reasoning_effort"] == "high"
