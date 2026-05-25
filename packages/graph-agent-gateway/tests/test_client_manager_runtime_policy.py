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


def test_anthropic_thinking_budget_stays_below_max_tokens(monkeypatch) -> None:
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
        512,
        0,
        reasoning=True,
    )

    assert result["content"] == "ok"
    thinking = captured[0]["thinking"]
    assert isinstance(thinking, dict)
    assert thinking["budget_tokens"] < captured[0]["max_tokens"]
