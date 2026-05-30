from __future__ import annotations

import inspect

from graph_agent_gateway.gateway_chat_model import GatewayChatModel
from graph_agent_gateway.llm_config import (
    ModelEntry,
    ProviderEntry,
    RoleEntry,
    RoleModelEntry,
    RolesData,
)
from graph_agent_gateway.resolver import ModelResolver

import graph_agent
from graph_agent.core._predict_internal.strategy import BaseMockStrategy

EXPECTED_TOP_LEVEL_EXPORTS = [
    "run_skill",
    "WorkflowResult",
    "compile_skill",
    "CompileResult",
    "assemble_graph",
    "CompiledSkill",
    "CompiledStateGraph",
    "BlackboardState",
    "LocalWorkspaceResolver",
    "SkillManifest",
    "serialize_skill",
    "Callback",
    "LoggingCallback",
    "MetricsCallback",
    "TracingCallback",
    "GraphAgentError",
    "GraphCompileError",
    "GraphExecutionError",
    "ModelProviderError",
    "ResourceNotFoundError",
]


class DummyMockStrategy(BaseMockStrategy):
    def has_phase(self, phase_name: str) -> bool:
        return phase_name == "phaseA"


def _make_config() -> RolesData:
    models = {
        "X": ModelEntry(
            name="Primary",
            min_max_tokens=321,
            max_input_tokens=200000,
            providers={"PX": "x-model"},
        ),
    }
    providers = {
        "PX": ProviderEntry(name="Provider X", type="openai_compatible"),
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
    return RolesData(models=models, providers=providers, roles=roles)


def test_predict_internal_exports_bind_predictor_only() -> None:
    import graph_agent.core._predict_internal as predict_internal
    from graph_agent.core._predict_internal import bind_predictor

    assert predict_internal.__all__ == ["bind_predictor"]
    assert inspect.isfunction(bind_predictor)


def test_predict_gateway_chat_model_is_dynamic_subclass() -> None:
    from graph_agent.core._predict_internal.interception import PredictGatewayChatModel

    assert issubclass(PredictGatewayChatModel, GatewayChatModel)
    assert PredictGatewayChatModel is not GatewayChatModel


def test_top_level_export_abi_has_no_predict_additions() -> None:
    assert graph_agent.__all__ == EXPECTED_TOP_LEVEL_EXPORTS
    assert "PredictGatewayChatModel" not in graph_agent.__all__
    assert "BaseMockStrategy" not in graph_agent.__all__
    assert "bind_predictor" not in graph_agent.__all__


def test_model_resolver_non_predict_path_still_returns_gateway() -> None:
    cfg = _make_config()
    resolver = ModelResolver(roles_data=cfg)

    model = resolver.resolve("test_role", phase_name="phaseA")

    assert type(model) is GatewayChatModel
    assert model.phase_name == "phaseA"


def test_bind_predictor_switches_resolver_to_predict_gateway() -> None:
    from graph_agent.core._predict_internal import bind_predictor
    from graph_agent.core._predict_internal.interception import PredictGatewayChatModel

    cfg = _make_config()
    resolver = ModelResolver(roles_data=cfg)
    strategy = DummyMockStrategy()

    bound = bind_predictor(resolver, strategy)
    model = resolver.resolve("test_role", phase_name="phaseA")

    assert bound is resolver
    assert isinstance(model, PredictGatewayChatModel)
    assert model.phase_name == "phaseA"
    assert model.mock_strategy is strategy
