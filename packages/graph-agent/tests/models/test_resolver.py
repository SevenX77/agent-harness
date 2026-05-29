"""Tests for graph-agent-gateway ModelResolver wiring."""

from __future__ import annotations

from pathlib import Path

import pytest
from graph_agent_gateway.exceptions import AllProvidersFailedError, GatewayRoleNotConfiguredError
from graph_agent_gateway.gateway_chat_model import GatewayChatModel
from graph_agent_gateway.llm_config import (
    ModelEntry,
    ProviderEntry,
    ResolvedProvider,
    RoleEntry,
    RoleModelEntry,
    RolesData,
)
from graph_agent_gateway.resolver import ModelResolver
from langchain_core.language_models.chat_models import BaseChatModel

from graph_agent.models.llm_client_manager import LLMClientManager


def _make_config(
    *,
    peer_model_groups: dict[str, list[str]] | None = None,
    single_model_roles: list[str] | None = None,
) -> RolesData:
    models = {
        "X": ModelEntry(
            name="Primary",
            min_max_tokens=321,
            max_input_tokens=200000,
            providers={"PX": "x-model"},
        ),
        "Y": ModelEntry(
            name="Peer",
            min_max_tokens=123,
            providers={"PY": "y-model"},
        ),
    }
    providers = {
        "PX": ProviderEntry(name="Provider X", type="openai_compatible"),
        "PY": ProviderEntry(name="Provider Y", type="openai_compatible"),
    }
    roles = {
        "test_role": RoleEntry(
            temperature=0.4,
            active_model="X",
            model_fallback=True,
            models={
                "X": RoleModelEntry(providers=["PX"]),
            },
        )
    }
    return RolesData(
        models=models,
        providers=providers,
        roles=roles,
        peer_model_groups=peer_model_groups or {},
        single_model_roles=single_model_roles or [],
    )


def test_resolve_returns_gateway_model_for_configured_role() -> None:
    resolver = ModelResolver(roles_data=_make_config())

    model = resolver.resolve("test_role", thinking_enabled=True, phase_name="phaseA")

    assert isinstance(model, BaseChatModel)
    assert isinstance(model, GatewayChatModel)
    assert model.role_name == "test_role"
    assert model.name == "x-model"
    assert model.temperature == 0.4
    assert model.max_tokens == 321
    assert model.thinking_enabled is True
    assert model.phase_name == "phaseA"
    assert [rp.provider_code for rp in model.resolved_role.call_chain] == ["PX"]


def test_role_model_parameters_override_role_defaults() -> None:
    cfg = _make_config()
    cfg.roles["test_role"].models["X"] = RoleModelEntry(
        providers=["PX"],
        temperature=0.2,
        max_tokens=999,
    )
    resolver = ModelResolver(roles_data=cfg)

    model = resolver.resolve("test_role")

    assert isinstance(model, GatewayChatModel)
    assert model.temperature == 0.2
    assert model.max_tokens == 999


def test_model_fallback_extends_gateway_chain() -> None:
    cfg = _make_config()
    cfg.roles["test_role"].models["Y"] = RoleModelEntry(providers=["PY"])
    resolver = ModelResolver(roles_data=cfg)

    model = resolver.resolve("test_role")

    assert isinstance(model, GatewayChatModel)
    assert [_candidate_id(rp) for rp in model.resolved_role.call_chain] == [
        "PX/x-model",
        "PY/y-model",
    ]


def test_single_model_role_does_not_append_extra_role_models() -> None:
    cfg = _make_config(single_model_roles=["test_role"])
    cfg.roles["test_role"].models["Y"] = RoleModelEntry(providers=["PY"])
    resolver = ModelResolver(roles_data=cfg)

    model = resolver.resolve("test_role")

    assert isinstance(model, GatewayChatModel)
    assert [_candidate_id(rp) for rp in model.resolved_role.call_chain] == ["PX/x-model"]


def test_model_override_resolves_synthetic_gateway_role() -> None:
    resolver = ModelResolver(roles_data=_make_config())

    model = resolver.resolve("test_role", model_override="Y")

    assert isinstance(model, GatewayChatModel)
    assert model.role_name == "_model_override::Y"
    assert [_candidate_id(rp) for rp in model.resolved_role.call_chain] == ["PY/y-model"]


def test_model_override_missing_raises_gateway_error() -> None:
    resolver = ModelResolver(roles_data=_make_config())

    with pytest.raises(GatewayRoleNotConfiguredError):
        resolver.resolve("test_role", model_override="MISSING")


def test_resolve_uses_default_role_from_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    resolver = ModelResolver(roles_data=_make_config())
    monkeypatch.setenv("GRAPH_AGENT_DEFAULT_ROLE", "test_role")

    model = resolver.resolve()

    assert isinstance(model, GatewayChatModel)
    assert model.role_name == "test_role"


def test_resolve_empty_call_chain_raises_all_providers_failed() -> None:
    cfg = _make_config()
    cfg.roles["empty"] = RoleEntry(
        active_model="X",
        models={"X": RoleModelEntry(providers=[])},
    )
    resolver = ModelResolver(roles_data=cfg)

    with pytest.raises(AllProvidersFailedError):
        resolver.resolve("empty")


def test_provider_options_override_gateway_max_tokens() -> None:
    cfg = _make_config()
    cfg.models["X"] = ModelEntry(
        name="Primary",
        min_max_tokens=321,
        providers={"PX": "x-model"},
        provider_options={"PX": {"max_max_tokens": 999}},
    )
    resolver = ModelResolver(roles_data=cfg)

    model = resolver.resolve("test_role")

    assert isinstance(model, GatewayChatModel)
    assert model.max_tokens == 999


def test_mark_provider_down_delegates_to_gateway_cache() -> None:
    LLMClientManager._provider_down_cache.clear()
    resolver = ModelResolver(roles_data=_make_config())

    resolver.mark_provider_down("PX", "x-model")

    assert LLMClientManager._is_provider_marked_down("PX", "x-model")


def test_peer_model_groups_parsed_from_yaml(tmp_path: Path) -> None:
    import yaml

    fixture = tmp_path / "llm_roles.yaml"
    fixture.write_text(
        "peer_model_groups:\n  test_tier: [MA, MB]\n",
        encoding="utf-8",
    )
    payload = yaml.safe_load(fixture.read_text(encoding="utf-8"))

    assert payload["peer_model_groups"]["test_tier"] == ["MA", "MB"]


def _candidate_id(rp: ResolvedProvider) -> str:
    return f"{rp.provider_code}/{rp.model_name}"
