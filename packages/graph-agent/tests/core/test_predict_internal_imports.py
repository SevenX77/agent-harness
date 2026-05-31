from __future__ import annotations

import inspect
from typing import Any

from graph_agent_gateway.gateway_chat_model import GatewayChatModel
from graph_agent_gateway.registry.schema import (
    ProviderEndpoint,
    ProviderRoute,
    RegistrySnapshot,
    RoleEntry,
    RoleRouteEntry,
    RuntimeSettings,
)
from graph_agent_gateway.resolver import ModelResolver

import graph_agent
from graph_agent.core._predict_internal.strategy import BaseMockStrategy

EXPECTED_TOP_LEVEL_EXPORTS = [
    "run_skill",
    "predict_skill",
    "RunResult",
    "WorkflowResult",
    "PathDiff",
    "PhaseRecord",
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


def _make_snapshot() -> RegistrySnapshot:
    return RegistrySnapshot(
        provider_endpoints={
            "px": ProviderEndpoint(
                endpoint_id="px",
                protocol="openai_compatible",
                base_url="https://provider.example/v1",
                api_key="secret",
            ),
        },
        provider_routes={
            "px:x-model": ProviderRoute(
                route_id="px:x-model",
                endpoint_id="px",
                route_slug="x-model",
                provider_model_id="x-model",
                canonical_id="x-model",
                status="verified",
            ),
        },
        roles={
            "test_role": RoleEntry(
                fallback_chain=[
                    RoleRouteEntry(
                        route_id="px:x-model",
                        runtime_settings=RuntimeSettings(temperature=0.4),
                    )
                ],
            )
        },
    )


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
    assert sorted(graph_agent.__all__) == sorted(EXPECTED_TOP_LEVEL_EXPORTS)
    assert "PredictGatewayChatModel" not in graph_agent.__all__
    assert "BaseMockStrategy" not in graph_agent.__all__
    assert "bind_predictor" not in graph_agent.__all__


def test_model_resolver_non_predict_path_still_returns_gateway() -> None:
    resolver = ModelResolver(registry_snapshot=_make_snapshot())

    model = resolver.resolve("test_role", phase_name="phaseA")

    assert type(model) is GatewayChatModel
    assert model.phase_name == "phaseA"


def test_resolver_with_predict_context_resolves_to_predict_gateway() -> None:
    from graph_agent_gateway.predict_interception import PredictGatewayChatModel

    class DummyPredictContext:
        def resolve_generation(self, phase_name: str, role_name: str, messages: list[Any]) -> str:
            return "mocked content"

    resolver = ModelResolver(registry_snapshot=_make_snapshot())
    model = resolver.resolve("test_role", phase_name="phaseA", predict_context=DummyPredictContext())

    assert isinstance(model, PredictGatewayChatModel)
    assert model.phase_name == "phaseA"
