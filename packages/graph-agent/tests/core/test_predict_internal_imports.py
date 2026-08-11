from __future__ import annotations

from typing import Any

from graph_agent_gateway.gateway_chat_model import GatewayChatModel
from graph_agent_gateway.registry import InMemoryConfigTruthStore
from graph_agent_gateway.resolver import ModelResolver

import graph_agent

_TEST_USER_ID = "engine-contract-test-user"

EXPECTED_TOP_LEVEL_EXPORTS = [
    "run_skill",
    "predict_skill",
    "resume_skill",
    "evaluate_golden_baseline",
    "RunResult",
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
    "GraphAgentError",
    "GraphCompileError",
    "GraphExecutionError",
    "ModelProviderError",
    "ResourceNotFoundError",
    "compile_artifact",
    "run_artifact",
    "predict_artifact",
]


def _make_config_store() -> InMemoryConfigTruthStore:
    store = InMemoryConfigTruthStore()
    store.put_config(
        _TEST_USER_ID,
        "credentials",
        {
            "schema_version": 4,
            "provider_endpoints": {
                "px": {
                    "endpoint_id": "px",
                    "protocol": "openai_compatible",
                    "base_url": "https://provider.example/v1",
                    "api_key": "secret",
                }
            },
            "provider_routes": {
                "px:x-model": {
                    "route_id": "px:x-model",
                    "endpoint_id": "px",
                    "route_slug": "x-model",
                    "provider_model_id": "x-model",
                    "canonical_id": "x-model",
                    "status": "verified",
                }
            },
            "runtime_policy": {},
        },
    )
    store.put_config(
        _TEST_USER_ID,
        "roles",
        {
            "schema_version": 2,
            "roles": {
                "test_role": {
                    "fallback_chain": [
                        {
                            "route_id": "px:x-model",
                            "runtime_settings": {"temperature": 0.4},
                        }
                    ],
                }
            },
        },
    )
    return store


def test_top_level_export_abi_has_no_predict_additions() -> None:
    assert sorted(graph_agent.__all__) == sorted(EXPECTED_TOP_LEVEL_EXPORTS)
    assert "PredictGatewayChatModel" not in graph_agent.__all__
    assert "BaseMockStrategy" not in graph_agent.__all__
    assert "bind_predictor" not in graph_agent.__all__


def test_model_resolver_non_predict_path_still_returns_gateway() -> None:
    resolver = ModelResolver(config_store=_make_config_store(), user_id=_TEST_USER_ID)

    model = resolver.resolve("test_role", phase_name="phaseA")

    assert type(model) is GatewayChatModel
    assert model.phase_name == "phaseA"


def test_resolver_with_predict_context_resolves_to_predict_gateway() -> None:
    from graph_agent_gateway.predict_interception import PredictGatewayChatModel

    class DummyPredictContext:
        def resolve_generation(self, phase_name: str, role_name: str, messages: list[Any]) -> str:
            return "mocked content"

    resolver = ModelResolver(config_store=_make_config_store(), user_id=_TEST_USER_ID)
    model = resolver.resolve("test_role", phase_name="phaseA", predict_context=DummyPredictContext())

    assert isinstance(model, PredictGatewayChatModel)
    assert model.phase_name == "phaseA"
