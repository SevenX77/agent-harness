from __future__ import annotations

from typing import Any

from graph_agent_gateway.registry import (
    ProviderEndpoint,
    ProviderRoute,
    RegistrySnapshot,
    RoleEntry,
    RoleRouteEntry,
)
from graph_agent_gateway.resolver import ModelResolver
from langchain_core.messages import HumanMessage
from pydantic import SecretStr


def _mock_registry_snapshot() -> RegistrySnapshot:
    return RegistrySnapshot(
        provider_endpoints={
            "mock-endpoint": ProviderEndpoint(
                endpoint_id="mock-endpoint",
                protocol="openai_compatible",
                base_url="http://localhost",
                api_key=SecretStr("key"),
            )
        },
        provider_routes={
            "mock-endpoint:mock-route": ProviderRoute(
                route_id="mock-endpoint:mock-route",
                endpoint_id="mock-endpoint",
                route_slug="mock-route",
                provider_model_id="gpt-4o",
                canonical_id="gpt-4o",
                status="verified",
            )
        },
        roles={
            "mock-role": RoleEntry(
                fallback_chain=[RoleRouteEntry(route_id="mock-endpoint:mock-route")]
            )
        }
    )


def _resolver_from_snapshot(snapshot: RegistrySnapshot, **kwargs: Any) -> ModelResolver:
    from graph_agent_gateway.registry import InMemoryConfigTruthStore

    payload = snapshot.model_dump(mode="python")
    store = InMemoryConfigTruthStore()
    user_id = "test-user"
    store.put_config(
        user_id,
        "credentials",
        {
            "schema_version": 4,
            "provider_endpoints": payload["provider_endpoints"],
            "provider_routes": payload["provider_routes"],
            "runtime_policy": payload["runtime_policy"],
        },
    )
    store.put_config(
        user_id,
        "roles",
        {
            "schema_version": 2,
            "model_profiles": payload["model_profiles"],
            "roles": payload["roles"],
        },
    )
    return ModelResolver(config_store=store, user_id=user_id, **kwargs)


class MockPredictContext:
    def __init__(self, expected_payload: dict[str, Any], expected_source: str) -> None:
        self.expected_payload = expected_payload
        self.expected_source = expected_source
        self.called = False

    def resolve_generation(self, phase_name: str, role_name: str, messages: list[Any]) -> tuple[dict[str, Any], str]:
        self.called = True
        return self.expected_payload, self.expected_source


def test_model_resolver_predict_callable_bridge() -> None:
    resolver = _resolver_from_snapshot(_mock_registry_snapshot())
    
    # Define a PredictContext with custom mock response
    context = MockPredictContext(
        expected_payload={"answer": "mocked by copilot callable"},
        expected_source="copilot"
    )
    
    model = resolver.resolve("mock-role", predict_context=context, phase_name="draft")

    # Invoke the model
    response = model.invoke([HumanMessage(content="Hello")])
    
    # Assert that our mock callable was indeed invoked and we got the expected payload content!
    assert context.called is True, "The predict_context.resolve_generation must be called during LLM execution"
    assert response.content == '{"answer":"mocked by copilot callable"}', "The model generation should match the mock payload"
    assert response.response_metadata.get("mocked_source") == "copilot"


def test_model_resolver_ignores_predict_context_when_none() -> None:
    resolver = _resolver_from_snapshot(_mock_registry_snapshot())
    
    # Resolving with predict_context=None should return a regular GatewayChatModel
    model = resolver.resolve("mock-role", predict_context=None)
    
    from graph_agent_gateway.gateway_chat_model import GatewayChatModel
    assert type(model) is GatewayChatModel
