from __future__ import annotations

import logging

import pytest

from graph_agent.config.llm_config import (
    ModelDef,
    ProviderDef,
    RoleConfigData,
    RoleDef,
    RoleModelEntry,
)


def _provider(code: str) -> ProviderDef:
    return ProviderDef(code=code, name=code, type="openai_compatible")


def test_resolve_role_orders_active_model_first_then_declared_fallbacks() -> None:
    cfg = RoleConfigData(
        models={
            "M1": ModelDef(
                code="M1",
                name="Model 1",
                providers={"P1": "m1-p1"},
                provider_options={"P1": {"max_tokens": 100}},
            ),
            "M2": ModelDef(code="M2", name="Model 2", providers={"P2": "m2-p2"}),
        },
        providers={"P1": _provider("P1"), "P2": _provider("P2")},
        roles={
            "writer": RoleDef(
                name="Writer",
                temperature=0.2,
                model_fallback=True,
                active_model="M2",
                system_prompt_prefix="  Use concise prose.  ",
                models={
                    "M1": RoleModelEntry(model_code="M1", provider_codes=["P1"]),
                    "M2": RoleModelEntry(model_code="M2", provider_codes=["P2"]),
                },
            )
        },
    )

    role = cfg.resolve_role("writer")

    assert role.role_name == "writer"
    assert role.temperature == 0.2
    assert role.system_prompt_prefix == "Use concise prose."
    assert role.active_model_code == "M2"
    assert role.model_fallback is True
    assert [(item.provider_code, item.model_name) for item in role.call_chain] == [
        ("P2", "m2-p2"),
        ("P1", "m1-p1"),
    ]
    assert role.call_chain[1].provider_options == {"max_tokens": 100}


def test_resolve_role_stops_after_active_model_when_fallback_disabled() -> None:
    cfg = RoleConfigData(
        models={
            "M1": ModelDef(code="M1", name="Model 1", providers={"P1": "m1-p1"}),
            "M2": ModelDef(code="M2", name="Model 2", providers={"P2": "m2-p2"}),
        },
        providers={"P1": _provider("P1"), "P2": _provider("P2")},
        roles={
            "validator": RoleDef(
                name="Validator",
                model_fallback=False,
                active_model="M1",
                models={
                    "M1": RoleModelEntry(model_code="M1", provider_codes=["P1"]),
                    "M2": RoleModelEntry(model_code="M2", provider_codes=["P2"]),
                },
            )
        },
    )

    role = cfg.resolve_role("validator")

    assert [(item.provider_code, item.model_name) for item in role.call_chain] == [
        ("P1", "m1-p1")
    ]


def test_resolve_role_skips_missing_models_and_providers(caplog: pytest.LogCaptureFixture) -> None:
    cfg = RoleConfigData(
        models={
            "M1": ModelDef(code="M1", name="Model 1", providers={"P1": "m1-p1"}),
            "M2": ModelDef(code="M2", name="Model 2", providers={}),
        },
        providers={"P1": _provider("P1")},
        roles={
            "planner": RoleDef(
                name="Planner",
                model_fallback=True,
                active_model="MISSING_MODEL",
                models={
                    "MISSING_MODEL": RoleModelEntry(
                        model_code="MISSING_MODEL",
                        provider_codes=["P1"],
                    ),
                    "M1": RoleModelEntry(model_code="M1", provider_codes=["MISSING_PROVIDER", "P1"]),
                    "M2": RoleModelEntry(model_code="M2", provider_codes=["P1"]),
                },
            )
        },
    )

    with caplog.at_level(logging.WARNING, logger="graph_agent.config.llm_config"):
        role = cfg.resolve_role("planner")

    assert [(item.provider_code, item.model_name) for item in role.call_chain] == [
        ("P1", "m1-p1")
    ]
    assert "引用了未注册的模型代号: MISSING_MODEL" in caplog.text
    assert "引用了未注册的 provider 代号: MISSING_PROVIDER" in caplog.text
    assert "在 provider P1 下无模型名映射" in caplog.text


def test_resolve_role_raises_key_error_for_unknown_role() -> None:
    with pytest.raises(KeyError, match="未知角色: missing"):
        RoleConfigData().resolve_role("missing")
