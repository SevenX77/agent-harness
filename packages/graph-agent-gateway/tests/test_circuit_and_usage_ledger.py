"""What the ledger remembers between calls, and who resolves a route's key.

The rest of this file used to test a hand-rolled dispatch layer no route could
reach. It is gone; the rules that were live and only tested there moved here or
to `test_production_wire_contract.py`.
"""

from __future__ import annotations

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


def test_provider_down_ttl_comes_from_runtime_policy(monkeypatch) -> None:
    from graph_agent_gateway.call import LLMCircuitAndUsageLedger
    from graph_agent_gateway.call import clients as ledger_module
    from graph_agent_gateway.registry import RuntimePolicy

    route = _route()
    policy = RuntimePolicy(provider_down_ttl_seconds=9)
    LLMCircuitAndUsageLedger._provider_down_cache.clear()
    monkeypatch.setattr(ledger_module.time, "monotonic", lambda: 100.0)

    LLMCircuitAndUsageLedger.mark_provider_down(route, RuntimeError("boom"), policy)

    down_key = LLMCircuitAndUsageLedger._make_down_key(route.endpoint_id, route.provider_model_id)
    assert LLMCircuitAndUsageLedger._provider_down_cache[down_key] == 109.0
    monkeypatch.setattr(ledger_module.time, "monotonic", lambda: 108.0)
    assert LLMCircuitAndUsageLedger.is_provider_marked_down(route, policy) is True
    monkeypatch.setattr(ledger_module.time, "monotonic", lambda: 110.0)
    assert LLMCircuitAndUsageLedger.is_provider_marked_down(route, policy) is False


def test_the_factory_resolves_a_routes_key_through_the_injected_provider() -> None:
    """The ledger used to carry a second copy of this; the factory's is the live one."""

    from graph_agent_gateway.call.factory import _resolve_api_key

    provider = StaticCredentialProvider({"endpoint:openai-direct": "secret-from-provider"})

    assert _resolve_api_key(_route(), provider) == "secret-from-provider"


def test_a_key_that_cannot_be_fetched_names_the_ref_it_failed_on() -> None:
    from graph_agent_gateway.call.factory import _resolve_api_key
    from graph_agent_gateway.registry import CredentialResolveError

    class FailingProvider:
        def get(self, ref: str) -> SecretStr:
            raise RuntimeError("vault down")

    try:
        _resolve_api_key(_route(), FailingProvider())
    except CredentialResolveError as exc:
        assert exc.error_code == "credential.vault_unreachable"
        assert exc.error_payload == {"credential_ref": "endpoint:openai-direct"}
    else:  # pragma: no cover - the call above must raise
        raise AssertionError("a provider that cannot answer must not yield a key")
