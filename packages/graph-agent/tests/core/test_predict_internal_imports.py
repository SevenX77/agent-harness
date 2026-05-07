from __future__ import annotations

import inspect

import graph_agent
import pytest
from graph_agent.config.llm_config import (
    ModelDef,
    ProviderDef,
    RoleConfigData,
    RoleDef,
    RoleModelEntry,
)
from graph_agent.core._predict_internal.strategy import BaseMockStrategy
from graph_agent.models import resolver as resolver_module
from graph_agent.models.gateway_chat_model import GatewayChatModel
from graph_agent.models.resolver import ModelResolver

EXPECTED_TOP_LEVEL_EXPORTS = [
    "run_skill",
    "WorkflowResult",
    "compile_skill",
    "CompileResult",
    "SkillManifest",
    "serialize_skill",
    "Callback",
    "LoggingCallback",
    "MetricsCallback",
    "TracingCallback",
    "GraphAgentError",
    "SkillLoadError",
    "SkillCompilationError",
]

class DummyMockStrategy(BaseMockStrategy):
    def has_phase(self, phase_name: str) -> bool:
        return phase_name == "phaseA"


def _make_config() -> RoleConfigData:
    models = {
        "X": ModelDef(
            code="X",
            name="Primary",
            min_max_tokens=321,
            max_input_tokens=200000,
            providers={"PX": "x-model"},
        ),
    }
    providers = {
        "PX": ProviderDef(code="PX", name="Provider X", type="openai_compatible"),
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
    return RoleConfigData(models=models, providers=providers, roles=roles)


def test_predict_internal_exports_bind_predictor_only() -> None:
    import graph_agent.core._predict_internal as predict_internal
    from graph_agent.core._predict_internal import bind_predictor

    assert predict_internal.__all__ == ["bind_predictor"]
    assert inspect.isfunction(bind_predictor)


def test_predict_gateway_chat_model_is_dynamic_subclass() -> None:
    from graph_agent.core._predict_internal.interception import PredictGatewayChatModel

    assert issubclass(PredictGatewayChatModel, GatewayChatModel)
    assert PredictGatewayChatModel is not GatewayChatModel


def test_top_level_13_export_abi_has_no_predict_additions() -> None:
    assert graph_agent.__all__ == EXPECTED_TOP_LEVEL_EXPORTS
    assert "PredictGatewayChatModel" not in graph_agent.__all__
    assert "BaseMockStrategy" not in graph_agent.__all__
    assert "bind_predictor" not in graph_agent.__all__


def test_model_resolver_non_predict_path_still_returns_gateway(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cfg = _make_config()
    resolver = ModelResolver()
    monkeypatch.setattr(resolver_module, "get_role_config", lambda: cfg)

    model = resolver.resolve("test_role", phase_name="phaseA")

    assert type(model) is GatewayChatModel
    assert model.phase_name == "phaseA"


def test_bind_predictor_switches_resolver_to_predict_gateway(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from graph_agent.core._predict_internal import bind_predictor
    from graph_agent.core._predict_internal.interception import PredictGatewayChatModel

    cfg = _make_config()
    resolver = ModelResolver()
    strategy = DummyMockStrategy()
    monkeypatch.setattr(resolver_module, "get_role_config", lambda: cfg)

    bound = bind_predictor(resolver, strategy)
    model = resolver.resolve("test_role", phase_name="phaseA")

    assert bound is resolver
    assert isinstance(model, PredictGatewayChatModel)
    assert model.phase_name == "phaseA"
    assert model.mock_strategy is strategy
