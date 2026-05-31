from __future__ import annotations

from graph_agent.config.llm_config import (
    ModelDef,
    ProviderDef,
    RoleDef,
    RoleModelEntry,
    _validate_cross_references,
)


def _model(code: str = "M1", providers: dict[str, str] | None = None) -> ModelDef:
    return ModelDef(code=code, name=code, providers=providers or {"P1": "model-name"})


def _provider(code: str = "P1") -> ProviderDef:
    return ProviderDef(code=code, name=code, type="openai_compatible")


def _role(
    name: str = "writer",
    *,
    active_model: str = "M1",
    model_code: str = "M1",
    provider_codes: list[str] | None = None,
) -> RoleDef:
    return RoleDef(
        name=name,
        active_model=active_model,
        models={
            model_code: RoleModelEntry(
                model_code=model_code,
                provider_codes=provider_codes if provider_codes is not None else ["P1"],
            )
        },
    )


def test_validate_cross_references_returns_empty_list_for_consistent_graph() -> None:
    assert _validate_cross_references({"M1": _model()}, {"P1": _provider()}, {"writer": _role()}) == []


def test_validate_cross_references_reports_model_provider_missing() -> None:
    errors = _validate_cross_references({"M1": _model()}, {}, {})

    assert errors == ["模型 M1 引用了未注册的 provider: P1"]


def test_validate_cross_references_reports_role_active_model_missing() -> None:
    errors = _validate_cross_references({}, {"P1": _provider()}, {"writer": _role()})

    assert errors == [
        "角色 writer 的 active_model=M1 未在 models 注册",
        "角色 writer 引用了未注册的模型: M1",
    ]


def test_validate_cross_references_reports_role_provider_missing() -> None:
    errors = _validate_cross_references(
        {"M1": _model(providers={"P1": "model-name"})},
        {"P1": _provider()},
        {"writer": _role(provider_codes=["P2"])},
    )

    assert errors == ["角色 writer 模型 M1 引用了未注册的 provider: P2"]


def test_validate_cross_references_reports_provider_not_mapped_on_model() -> None:
    errors = _validate_cross_references(
        {"M1": _model(providers={"P1": "model-name"})},
        {"P1": _provider(), "P2": _provider("P2")},
        {"writer": _role(provider_codes=["P2"])},
    )

    assert errors == ["角色 writer 模型 M1 使用 provider P2，但模型未注册该 provider 的模型名映射"]


def test_validate_cross_references_preserves_current_error_order_for_multiple_failures() -> None:
    errors = _validate_cross_references(
        {"M1": _model(providers={"P_missing": "x"})},
        {"P1": _provider()},
        {"writer": _role(active_model="M_missing", model_code="M_missing", provider_codes=["P2"])},
    )

    assert errors == [
        "模型 M1 引用了未注册的 provider: P_missing",
        "角色 writer 的 active_model=M_missing 未在 models 注册",
        "角色 writer 引用了未注册的模型: M_missing",
        "角色 writer 模型 M_missing 引用了未注册的 provider: P2",
    ]
