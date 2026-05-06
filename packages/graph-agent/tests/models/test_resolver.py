"""Tests for ModelResolver's Phase 4 GatewayChatModel output."""

from __future__ import annotations

from pathlib import Path

import pytest
from langchain_core.language_models.chat_models import BaseChatModel

from graph_agent.callbacks.base import Callback
from graph_agent.callbacks.events import CallbackEvent
from graph_agent.config.llm_config import (
    ModelDef,
    ProviderDef,
    ResolvedProvider,
    RoleConfigData,
    RoleDef,
    RoleModelEntry,
    load_config,
)
from graph_agent.models import resolver as resolver_module
from graph_agent.models.gateway_chat_model import GatewayChatModel
from graph_agent.models.llm_client_manager import LLMClientManager
from graph_agent.models.resolver import ModelResolver


class RecordingCallback(Callback):
    def __init__(self) -> None:
        self.events: list[CallbackEvent] = []

    def on_event(self, event: CallbackEvent) -> None:
        self.events.append(event)


def _make_config(
    *,
    peer_model_groups: dict[str, list[str]] | None = None,
    single_model_roles: list[str] | None = None,
) -> RoleConfigData:
    models = {
        "X": ModelDef(
            code="X",
            name="Primary",
            min_max_tokens=321,
            max_input_tokens=200000,
            providers={"PX": "x-model"},
        ),
        "Y": ModelDef(
            code="Y",
            name="Peer",
            min_max_tokens=123,
            providers={"PY": "y-model"},
        ),
    }
    providers = {
        "PX": ProviderDef(code="PX", name="Provider X", type="openai_compatible"),
        "PY": ProviderDef(code="PY", name="Provider Y", type="openai_compatible"),
    }
    roles = {
        "test_role": RoleDef(
            name="test_role",
            temperature=0.4,
            active_model="X",
            model_fallback=True,
            models={
                "X": RoleModelEntry(model_code="X", provider_codes=["PX"]),
            },
        )
    }
    return RoleConfigData(
        models=models,
        providers=providers,
        roles=roles,
        peer_model_groups=peer_model_groups or {},
        single_model_roles=single_model_roles or [],
    )


def test_resolve_returns_gateway_model_for_configured_role(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cfg = _make_config()
    resolver = ModelResolver()
    monkeypatch.setattr(resolver_module, "get_role_config", lambda: cfg)

    model = resolver.resolve("test_role", thinking_enabled=True, phase_name="phaseA")

    assert isinstance(model, BaseChatModel)
    assert isinstance(model, GatewayChatModel)
    assert model.role_name == "test_role"
    assert model.name == "PX/x-model"
    assert model.temperature == 0.4
    assert model.max_tokens == 321
    assert model.thinking_enabled is True
    assert model.phase_name == "phaseA"
    assert model.profile == {"max_input_tokens": 200000}
    assert [rp.provider_code for rp in model.resolved_role.call_chain] == ["PX"]


def test_peer_fallback_extends_gateway_chain_without_predictive_event(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cfg = _make_config(peer_model_groups={"g": ["X", "Y"]})
    resolver = ModelResolver()
    callback = RecordingCallback()
    monkeypatch.setattr(resolver_module, "get_role_config", lambda: cfg)

    model = resolver.resolve("test_role", callbacks=(callback,), phase_name="phaseA")

    assert isinstance(model, GatewayChatModel)
    assert [_candidate_id(rp) for rp in model.resolved_role.call_chain] == [
        "PX/x-model",
        "PY/y-model",
    ]
    assert callback.events == []


def test_single_model_role_does_not_append_peer_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cfg = _make_config(
        peer_model_groups={"g": ["X", "Y"]},
        single_model_roles=["test_role"],
    )
    resolver = ModelResolver()
    monkeypatch.setattr(resolver_module, "get_role_config", lambda: cfg)

    model = resolver.resolve("test_role")

    assert isinstance(model, GatewayChatModel)
    assert [_candidate_id(rp) for rp in model.resolved_role.call_chain] == ["PX/x-model"]


def test_model_override_resolves_synthetic_gateway_role(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cfg = _make_config(peer_model_groups={"g": ["X", "Y"]})
    resolver = ModelResolver()
    monkeypatch.setattr(resolver_module, "get_role_config", lambda: cfg)

    model = resolver.resolve("test_role", model_override="Y")

    assert isinstance(model, GatewayChatModel)
    assert model.role_name == "_model_override::Y"
    assert [_candidate_id(rp) for rp in model.resolved_role.call_chain] == ["PY/y-model"]


def test_model_override_missing_falls_back_to_role_resolution(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cfg = _make_config()
    resolver = ModelResolver()
    monkeypatch.setattr(resolver_module, "get_role_config", lambda: cfg)

    model = resolver.resolve("test_role", model_override="MISSING")

    assert isinstance(model, GatewayChatModel)
    assert model.role_name == "test_role"


def test_resolve_uses_default_role_from_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cfg = _make_config()
    resolver = ModelResolver()
    monkeypatch.setenv("GRAPH_AGENT_DEFAULT_ROLE", "test_role")
    monkeypatch.setattr(resolver_module, "get_role_config", lambda: cfg)

    model = resolver.resolve()

    assert isinstance(model, GatewayChatModel)
    assert model.role_name == "test_role"


def test_resolve_empty_call_chain_raises_all_providers_failed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cfg = _make_config()
    cfg.roles["empty"] = RoleDef(name="empty", active_model="X", models={})
    resolver = ModelResolver()
    monkeypatch.setattr(resolver_module, "get_role_config", lambda: cfg)

    with pytest.raises(Exception, match="All providers failed for tier 'empty'"):
        resolver.resolve("empty")


def test_peer_resolution_failure_is_logged_and_ignored(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    cfg = _make_config(peer_model_groups={"g": ["X", "MISSING"]})
    resolver = ModelResolver()
    monkeypatch.setattr(resolver_module, "get_role_config", lambda: cfg)

    with caplog.at_level("WARNING", logger=resolver_module.logger.name):
        model = resolver.resolve("test_role")

    assert isinstance(model, GatewayChatModel)
    assert [_candidate_id(rp) for rp in model.resolved_role.call_chain] == ["PX/x-model"]
    assert "peer model MISSING resolution failed" in caplog.text


def test_peer_duplicate_provider_model_is_not_appended(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cfg = _make_config(peer_model_groups={"g": ["X", "Y"]})
    cfg.models["Y"] = ModelDef(
        code="Y",
        name="Duplicate Peer",
        providers={"PX": "x-model"},
    )
    resolver = ModelResolver()
    monkeypatch.setattr(resolver_module, "get_role_config", lambda: cfg)

    model = resolver.resolve("test_role")

    assert isinstance(model, GatewayChatModel)
    assert [_candidate_id(rp) for rp in model.resolved_role.call_chain] == ["PX/x-model"]


def test_provider_options_override_gateway_max_tokens(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cfg = _make_config()
    cfg.models["X"] = ModelDef(
        code="X",
        name="Primary",
        min_max_tokens=321,
        providers={"PX": "x-model"},
        provider_options={"PX": {"max_max_tokens": 999}},
    )
    resolver = ModelResolver()
    monkeypatch.setattr(resolver_module, "get_role_config", lambda: cfg)

    model = resolver.resolve("test_role")

    assert isinstance(model, GatewayChatModel)
    assert model.max_tokens == 999


def test_gateway_profile_is_none_when_models_have_no_max_input_tokens(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cfg = _make_config()
    cfg.models["X"] = ModelDef(
        code="X",
        name="Primary",
        min_max_tokens=321,
        providers={"PX": "x-model"},
    )
    resolver = ModelResolver()
    monkeypatch.setattr(resolver_module, "get_role_config", lambda: cfg)

    model = resolver.resolve("test_role")

    assert isinstance(model, GatewayChatModel)
    assert model.profile is None


def test_mark_provider_down_delegates_to_gateway_cache() -> None:
    resolver = ModelResolver()

    resolver.mark_provider_down("PX", "x-model")

    assert LLMClientManager._is_provider_marked_down("PX", "x-model")


def test_resolve_signature_backward_compat(monkeypatch: pytest.MonkeyPatch) -> None:
    cfg = _make_config()
    resolver = ModelResolver()
    monkeypatch.setattr(resolver_module, "get_role_config", lambda: cfg)

    model = resolver.resolve("test_role")

    assert isinstance(model, BaseChatModel)
    assert isinstance(model, GatewayChatModel)


def test_singleton_get_and_reset() -> None:
    resolver_module.reset_model_resolver()

    first = resolver_module.get_model_resolver()
    second = resolver_module.get_model_resolver()
    resolver_module.reset_model_resolver()
    third = resolver_module.get_model_resolver()

    assert first is second
    assert third is not first


def test_peer_model_groups_parsed_from_yaml() -> None:
    repo_root = Path(__file__).resolve().parents[3]
    cfg = load_config(repo_root / "config" / "llm_roles.yaml")

    assert cfg.peer_model_groups["claude_sonnet_tier"] == ["CL46T", "CLO46T"]


def _candidate_id(rp: ResolvedProvider) -> str:
    return f"{rp.provider_code}/{rp.model_name}"
