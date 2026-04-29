"""Tests for ModelResolver peer fallback event emission."""
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from graph_agent.callbacks.base import Callback
from graph_agent.callbacks.events import CallbackEvent, LLMFallbackEvent
from graph_agent.config.llm_config import (
    ModelDef,
    ProviderDef,
    RoleConfigData,
    RoleDef,
    RoleModelEntry,
    load_config,
)
from graph_agent.models import resolver as resolver_module
from graph_agent.models.resolver import ModelResolver, _attach_profile


class RecordingCallback(Callback):
    def __init__(self) -> None:
        self.events: list[CallbackEvent] = []

    def on_event(self, event: CallbackEvent) -> None:  # type: ignore[override]
        self.events.append(event)


class _FakeModel:
    def __init__(self, name: str) -> None:
        self.name = name
        self.fallbacks: list[Any] = []

    def with_fallbacks(
        self,
        fallback_models: list[Any],
        *,
        exceptions_to_handle: tuple[type[BaseException], ...],
    ) -> _FakeModel:
        self.fallbacks = list(fallback_models)
        return self


class _RejectsDynamicAttrs:
    __slots__ = ()


def test_attach_profile_when_max_input_tokens_set() -> None:
    model = SimpleNamespace()
    model_def = ModelDef(
        code="BIG_MODEL",
        name="Big Context Model",
        max_input_tokens=200000,
    )

    _attach_profile(model, model_def)

    assert model.profile == {"max_input_tokens": 200000}


def test_attach_profile_no_op_when_max_input_tokens_none() -> None:
    model = SimpleNamespace()
    model_def = ModelDef(code="SMALL_MODEL", name="Small Model")

    _attach_profile(model, model_def)

    assert not hasattr(model, "profile")


def test_attach_profile_logs_warning_on_setattr_failure(
    caplog: pytest.LogCaptureFixture,
) -> None:
    model = _RejectsDynamicAttrs()
    model_def = ModelDef(
        code="STRICT_MODEL",
        name="Strict Model",
        max_input_tokens=200000,
    )

    with caplog.at_level("WARNING", logger=resolver_module.logger.name):
        _attach_profile(model, model_def)

    assert "failed to attach profile" in caplog.text
    assert "summary profile fallback will use 32k" in caplog.text


def _make_config(
    *,
    peer_model_groups: dict[str, list[str]] | None = None,
) -> RoleConfigData:
    models = {
        "X": ModelDef(
            code="X",
            name="Primary",
            providers={"PX": "x-model"},
        ),
        "Y": ModelDef(
            code="Y",
            name="Peer",
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
            active_model="X",
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
    )


def test_peer_fallback_emits_llm_fallback_event(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cfg = _make_config(peer_model_groups={"g": ["X", "Y"]})
    resolver = ModelResolver()

    def fake_create(
        rp: Any,
        temperature: float,
        thinking_enabled: bool | None,
    ) -> _FakeModel:
        if rp.model_def.code == "X":
            raise RuntimeError("primary down")
        return _FakeModel(rp.model_name)

    monkeypatch.setattr(resolver_module, "get_role_config", lambda: cfg)
    monkeypatch.setattr(resolver, "_create_langchain_model", fake_create)

    rec = RecordingCallback()
    model = resolver.resolve("test_role", callbacks=(rec,), phase_name="phaseA")

    assert isinstance(model, _FakeModel)
    fallback_events = [e for e in rec.events if isinstance(e, LLMFallbackEvent)]
    assert len(fallback_events) == 1
    assert fallback_events[0].phase_name == "phaseA"
    assert fallback_events[0].from_provider == "PX/X"
    assert fallback_events[0].to_provider == "PY/y-model"
    assert fallback_events[0].reason == "peer_fallback:primary_chain_exhausted"


def test_peer_fallback_no_callbacks_does_not_raise(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cfg = _make_config(peer_model_groups={"g": ["X", "Y"]})
    resolver = ModelResolver()

    def fake_create(
        rp: Any,
        temperature: float,
        thinking_enabled: bool | None,
    ) -> _FakeModel:
        if rp.model_def.code == "X":
            raise RuntimeError("primary down")
        return _FakeModel(rp.model_name)

    monkeypatch.setattr(resolver_module, "get_role_config", lambda: cfg)
    monkeypatch.setattr(resolver, "_create_langchain_model", fake_create)

    model = resolver.resolve("test_role")

    assert isinstance(model, _FakeModel)
    assert model.name == "y-model"


def test_resolve_signature_backward_compat(monkeypatch: pytest.MonkeyPatch) -> None:
    cfg = _make_config()
    resolver = ModelResolver()

    def fake_create(
        rp: Any,
        temperature: float,
        thinking_enabled: bool | None,
    ) -> _FakeModel:
        return _FakeModel(rp.model_name)

    monkeypatch.setattr(resolver_module, "get_role_config", lambda: cfg)
    monkeypatch.setattr(resolver, "_create_langchain_model", fake_create)

    model = resolver.resolve("test_role")

    assert isinstance(model, _FakeModel)
    assert model.name == "x-model"


def test_peer_model_groups_parsed_from_yaml() -> None:
    repo_root = Path(__file__).resolve().parents[3]
    cfg = load_config(repo_root / "config" / "llm_roles.yaml")

    assert cfg.peer_model_groups["claude_sonnet_tier"] == ["CL46T", "CLO46T"]
