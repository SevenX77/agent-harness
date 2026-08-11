"""MVP1 productization RED tests for resource terminal errors."""

from __future__ import annotations

import inspect

import pytest


def _error_code(exc: BaseException) -> str | None:
    return getattr(exc, "error_code", getattr(exc, "code", None))


def _error_payload(exc: BaseException) -> dict[str, object]:
    return getattr(exc, "error_payload", getattr(exc, "context", {}))


def _store_for_role(role_payload: dict[str, object]):
    from graph_agent_gateway.registry import InMemoryConfigTruthStore

    store = InMemoryConfigTruthStore()
    store.put_config(
        user_id="user-a",
        key="credentials",
        value={
            "schema_version": 4,
            "provider_endpoints": {},
            "provider_routes": {},
            "runtime_policy": {},
        },
        if_none_match="*",
    )
    store.put_config(
        user_id="user-a",
        key="roles",
        value={
            "schema_version": 3,
            "roles": {"graph_agent": role_payload},
        },
        if_none_match="*",
    )
    return store


def _resolver_from_config_store(store: object):
    from graph_agent_gateway.call import ModelResolver

    params = inspect.signature(ModelResolver.__init__).parameters
    if "config_store" in params:
        return ModelResolver(config_store=store, user_id="user-a")
    if "config_truth_store" in params:
        return ModelResolver(config_truth_store=store, user_id="user-a")
    return ModelResolver(config_store=store, user_id="user-a")


def test_resolver_empty_fallback_chain_from_config_store_is_resource_terminal() -> None:
    resolver = _resolver_from_config_store(
        _store_for_role(
            {
                "fallback_chain": [],
            }
        )
    )

    with pytest.raises(Exception) as exc_info:
        resolver.resolve_routes("graph_agent")

    assert _error_code(exc_info.value) == "resource.no_available_route"
    assert _error_payload(exc_info.value)["role"] == "graph_agent"


def test_resolver_missing_route_from_config_store_is_resource_terminal() -> None:
    resolver = _resolver_from_config_store(
        _store_for_role(
            {
                "fallback_chain": [{"route_id": "missing:gpt-5"}],
            }
        )
    )

    with pytest.raises(Exception) as exc_info:
        resolver.resolve_routes("graph_agent")

    assert _error_code(exc_info.value) == "resource.no_available_route"
    assert _error_payload(exc_info.value)["role"] == "graph_agent"
    assert _error_payload(exc_info.value)["skipped"][0]["route_id"] == "missing:gpt-5"
    assert _error_payload(exc_info.value)["skipped"][0]["reason_code"] == "route_missing"
