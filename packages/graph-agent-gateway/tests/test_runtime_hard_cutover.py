"""Gateway runtime hard-cutover tests."""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
import yaml
from langchain_core.messages import AIMessage, AIMessageChunk, BaseMessage, HumanMessage, SystemMessage
from pydantic import SecretStr
from stream_fakes import as_one_piece


def _snapshot():
    from graph_agent_gateway.registry.schema import (
        ProviderEndpoint,
        ProviderRoute,
        RegistrySnapshot,
        RoleEntry,
        RoleRouteEntry,
        RuntimePolicy,
    )

    return RegistrySnapshot(
        provider_endpoints={
            "openai-direct": ProviderEndpoint(
                endpoint_id="openai-direct",
                protocol="openai_compatible",
                base_url="https://api.openai.example/v1",
                api_key=SecretStr("route-secret"),
                timeout_seconds=17,
                trust_env=False,
            ),
            "openrouter-prod": ProviderEndpoint(
                endpoint_id="openrouter-prod",
                protocol="openai_compatible",
                base_url="https://openrouter.example/v1",
                api_key=SecretStr("fallback-secret"),
            ),
        },
        provider_routes={
            "openai-direct:gpt-5": ProviderRoute(
                route_id="openai-direct:gpt-5",
                endpoint_id="openai-direct",
                route_slug="gpt-5",
                provider_model_id="gpt-5",
                canonical_id="gpt-5",
                status="verified",
            ),
            "openrouter-prod:openai.gpt-5": ProviderRoute(
                route_id="openrouter-prod:openai.gpt-5",
                endpoint_id="openrouter-prod",
                route_slug="openai.gpt-5",
                provider_model_id="openai/gpt-5",
                canonical_id="gpt-5",
                status="verified",
            ),
        },
        runtime_policy=RuntimePolicy(
            provider_down_ttl_seconds=9,
            probe_timeout_seconds=3,
            token_escalation_rounds=1,
        ),
        roles={
            "graph_agent": RoleEntry(
                system_prompt_prefix="Always be exact.",
                fallback_chain=[
                    RoleRouteEntry(
                        route_id="openai-direct:gpt-5",
                        runtime_settings={
                            "temperature": 0.25,
                            "max_output_tokens": 2048,
                            "reasoning": {"enabled": False},
                        },
                    ),
                    RoleRouteEntry(route_id="openrouter-prod:openai.gpt-5"),
                ],
            )
        },
    )


class RecordingClientManager:
    def __init__(self) -> None:
        self.marked_down: list[tuple[str, str]] = []

    def is_provider_marked_down(self, route: Any, runtime_policy: Any) -> bool:
        return False

    def mark_provider_down(self, route: Any, exc: BaseException, runtime_policy: Any) -> None:
        self.marked_down.append((route.route_id, str(exc)))

    def usage_total_calls(self, route: Any) -> int:
        return 0


class FakeRouteChatModel:
    def __init__(self, factory: FakeRouteChatModelFactory, route: Any) -> None:
        self.factory = factory
        self.route = route

    def stream(self, messages: list[BaseMessage], **kwargs: Any) -> Iterator[AIMessageChunk]:
        del kwargs
        self.factory.invocations.append({"route": self.route, "messages": messages})
        yield from as_one_piece(
            AIMessage(
                content="ok",
                usage_metadata={"input_tokens": 2, "output_tokens": 1, "total_tokens": 3},
                response_metadata={"finish_reason": "stop"},
            )
        )


class FakeRouteChatModelFactory:
    def __init__(self, **kwargs: Any) -> None:
        self.init_kwargs = dict(kwargs)
        self.builds: list[dict[str, Any]] = []
        self.invocations: list[dict[str, Any]] = []

    def build(self, route: Any, **kwargs: Any) -> FakeRouteChatModel:
        self.builds.append({"route": route, "kwargs": dict(kwargs)})
        return FakeRouteChatModel(self, route)


def _install_route_factory(monkeypatch: pytest.MonkeyPatch) -> FakeRouteChatModelFactory:
    from graph_agent_gateway import gateway_chat_model

    factory = FakeRouteChatModelFactory()

    def make_factory(**kwargs: Any) -> FakeRouteChatModelFactory:
        factory.init_kwargs.update(kwargs)
        return factory

    monkeypatch.setattr(gateway_chat_model, "RouteChatModelFactory", make_factory)
    return factory





def _install_route_factory(monkeypatch: pytest.MonkeyPatch) -> FakeRouteChatModelFactory:
    from graph_agent_gateway import gateway_chat_model

    factory = FakeRouteChatModelFactory()

    def make_factory(**kwargs: Any) -> FakeRouteChatModelFactory:
        factory.init_kwargs.update(kwargs)
        return factory

    monkeypatch.setattr(gateway_chat_model, "RouteChatModelFactory", make_factory)
    return factory


def _write_registry_files(tmp_path: Path) -> tuple[Path, Path]:
    snapshot = _snapshot()
    credentials_path = tmp_path / "llm_credentials.json"
    roles_path = tmp_path / "llm_roles.yaml"
    credentials_path.write_text(
        json.dumps(
            {
                "schema_version": 4,
                "provider_endpoints": snapshot.model_dump(mode="json")[
                    "provider_endpoints"
                ],
                "provider_routes": snapshot.model_dump(mode="json")["provider_routes"],
                "runtime_policy": snapshot.model_dump(mode="json")["runtime_policy"],
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    roles_path.write_text(
        yaml.safe_dump(
            {
                "schema_version": 2,
                "model_profiles": {},
                "roles": snapshot.model_dump(mode="json")["roles"],
            },
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    return credentials_path, roles_path


def _resolver_from_payloads(
    credentials: dict[str, Any],
    roles: dict[str, Any],
    **kwargs: Any,
) -> Any:
    from graph_agent_gateway.resolver import ModelResolver
    from graph_agent_gateway.storage_contracts import InMemoryConfigTruthStore

    store = InMemoryConfigTruthStore()
    user_id = "test-user"
    store.put_config(user_id, "credentials", credentials)
    store.put_config(user_id, "roles", roles)
    return ModelResolver(config_store=store, user_id=user_id, **kwargs)


def _resolver_from_snapshot(snapshot: Any, **kwargs: Any) -> Any:
    payload = snapshot.model_dump(mode="python")
    return _resolver_from_payloads(
        {
            "schema_version": 4,
            "provider_endpoints": payload["provider_endpoints"],
            "provider_routes": payload["provider_routes"],
            "runtime_policy": payload["runtime_policy"],
        },
        {
            "schema_version": 2,
            "model_profiles": payload["model_profiles"],
            "roles": payload["roles"],
        },
        **kwargs,
    )


def _resolver_from_files(
    credentials_path: Path,
    roles_path: Path,
    **kwargs: Any,
) -> Any:
    credentials = json.loads(credentials_path.read_text(encoding="utf-8"))
    roles = yaml.safe_load(roles_path.read_text(encoding="utf-8"))
    return _resolver_from_payloads(credentials, roles, **kwargs)


def test_model_resolver_requires_config_truth_store() -> None:
    from graph_agent_gateway.resolver import ModelResolver

    with pytest.raises(TypeError, match="config_store"):
        ModelResolver()


def test_model_resolver_loads_explicit_v4_v2_files(tmp_path: Path) -> None:
    from graph_agent_gateway.gateway_chat_model import GatewayChatModel

    credentials_path, roles_path = _write_registry_files(tmp_path)
    client_manager = RecordingClientManager()
    resolver = _resolver_from_files(
        credentials_path,
        roles_path,
        client_manager=client_manager,
    )

    model = resolver.resolve("graph_agent", phase_name="draft")

    assert isinstance(model, GatewayChatModel)
    assert model.max_tokens == 2048
    assert model.temperature is None
    assert model.resolved_role.routes[0].effective_runtime_settings["temperature"].value == 0.25
    assert model.thinking_enabled is False
    assert model.resolved_role.system_prompt_prefix == "Always be exact."
    assert [route.route_id for route in model.resolved_role.routes] == [
        "openai-direct:gpt-5",
        "openrouter-prod:openai.gpt-5",
    ]


def test_model_resolver_loads_studio_v3_roles_file_using_materialized_chain(
    tmp_path: Path,
) -> None:
    from graph_agent_gateway.gateway_chat_model import GatewayChatModel

    credentials_path, roles_path = _write_registry_files(tmp_path)
    roles_payload = yaml.safe_load(roles_path.read_text(encoding="utf-8"))
    roles_payload["schema_version"] = 3
    roles_payload["model_bundles"] = {
        "analysis-default": {
            "model_groups": [],
        }
    }
    roles_payload["roles"]["graph_agent"].update(
        {
            "role_kind": "graph_agent",
            "model_fallback_enabled": True,
            "intent": {"provider_preference": "manual_order"},
            "model_groups": [
                {
                    "canonical_id": "gpt-5",
                    "provider_models": [
                        {"route_id": "openai-direct:gpt-5"},
                        {"route_id": "openrouter-prod:openai.gpt-5"},
                    ],
                }
            ],
            "materialization_report": {
                "entries": [
                    {"route_id": "openai-direct:gpt-5", "role_fit": "using"},
                    {"route_id": "openrouter-prod:openai.gpt-5", "role_fit": "using"},
                ]
            },
        }
    )
    roles_path.write_text(yaml.safe_dump(roles_payload, sort_keys=True), encoding="utf-8")

    resolver = _resolver_from_files(credentials_path, roles_path)
    model = resolver.resolve("graph_agent", phase_name="draft")

    assert isinstance(model, GatewayChatModel)
    assert [route.route_id for route in model.resolved_role.routes] == [
        "openai-direct:gpt-5",
        "openrouter-prod:openai.gpt-5",
    ]


def test_model_override_is_exact_route_id() -> None:

    resolver = _resolver_from_snapshot(_snapshot())

    model = resolver.resolve("graph_agent", model_override="openrouter-prod:openai.gpt-5")
    assert [route.route_id for route in model.resolved_role.routes] == [
        "openrouter-prod:openai.gpt-5"
    ]

    with pytest.raises(Exception, match="route"):
        resolver.resolve("graph_agent", model_override="gpt-5")


def test_model_resolver_resolve_routes_returns_route_chain_without_provider_call(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from graph_agent_gateway.gateway_chat_model import GatewayChatModel
    from graph_agent_gateway.route_handoff import ResolvedRouteChain

    factory = _install_route_factory(monkeypatch)
    client_manager = RecordingClientManager()
    resolver = _resolver_from_snapshot(
        _snapshot(),
        client_manager=client_manager,
    )

    resolved = resolver.resolve_routes("graph_agent")

    assert isinstance(resolved, ResolvedRouteChain)
    assert not isinstance(resolved, GatewayChatModel)
    assert resolved.role == "graph_agent"
    assert [route.route_id for route in resolved.routes] == [
        "openai-direct:gpt-5",
        "openrouter-prod:openai.gpt-5",
    ]
    assert not hasattr(resolved, "role_name")
    assert not hasattr(resolved, "lint_results")
    # Resolving a chain asks no provider anything — not even the one cheap
    # question a call would open with.
    assert factory.builds == []
    assert client_manager.marked_down == []


def test_resolve_and_resolve_routes_share_the_same_route_resolution() -> None:

    resolver = _resolver_from_snapshot(_snapshot())

    model = resolver.resolve("graph_agent")
    resolved = resolver.resolve_routes("graph_agent")

    assert [route.model_dump(mode="json") for route in resolved.routes] == [
        route.model_dump(mode="json") for route in model.resolved_role.routes
    ]


def test_resolve_routes_projects_resource_terminal_error() -> None:
    from graph_agent_gateway.resolver import ResourceTerminalError

    resolver = _resolver_from_snapshot(_snapshot())

    with pytest.raises(ResourceTerminalError) as exc_info:
        resolver.resolve_routes("not_exist")

    assert exc_info.value.error_code == "resource.no_available_route"
    assert exc_info.value.error_payload == {"role": "not_exist"}


def test_model_resolver_maps_filtered_empty_chain_to_resource_terminal_error() -> None:
    from graph_agent_gateway.registry.schema import RoleEntry
    from graph_agent_gateway.resolver import ResourceTerminalError

    snapshot = _snapshot()
    snapshot.roles["empty"] = RoleEntry(fallback_chain=[])
    resolver = _resolver_from_snapshot(snapshot)

    with pytest.raises(ResourceTerminalError) as exc_info:
        resolver.resolve("empty", phase_name="draft")

    assert exc_info.value.error_code == "resource.no_available_route"
    assert exc_info.value.error_payload == {"role": "empty"}


def test_model_resolver_predict_context_returns_predict_gateway_chat_model() -> None:
    from graph_agent_gateway.predict_interception import PredictGatewayChatModel

    class DummyPredictContext:
        def resolve_generation(
            self,
            phase_name: str,
            role_name: str,
            messages: list[Any],
        ) -> tuple[dict[str, Any], str]:
            del phase_name, role_name, messages
            return {"answer": "ok"}, "unit-test"

    model = _resolver_from_snapshot(_snapshot()).resolve(
        "graph_agent",
        phase_name="draft",
        predict_context=DummyPredictContext(),
    )

    assert isinstance(model, PredictGatewayChatModel)
    assert [route.route_id for route in model.resolved_role.routes] == [
        "openai-direct:gpt-5",
        "openrouter-prod:openai.gpt-5",
    ]


def test_mark_provider_down_uses_resolved_executable_route() -> None:

    client_manager = RecordingClientManager()
    resolver = _resolver_from_snapshot(
        _snapshot(),
        client_manager=client_manager,
    )

    resolver.mark_provider_down("openai-direct:gpt-5")

    assert client_manager.marked_down == [("openai-direct:gpt-5", "manual mark down")]


def test_runtime_uses_route_secret_and_no_provider_env(
    monkeypatch: pytest.MonkeyPatch,
) -> None:

    for key in (
        "OPENAI_API_KEY",
        "ANTHROPIC_API_KEY",
        "GOOGLE_API_KEY",
        "GEMINI_API_KEY",
        "OPENROUTER_API_KEY",
            "WAVESPEED_API_KEY",
    ):
        monkeypatch.delenv(key, raising=False)

    factory = _install_route_factory(monkeypatch)
    client_manager = RecordingClientManager()
    model = _resolver_from_snapshot(
        _snapshot(),
        client_manager=client_manager,
    ).resolve("graph_agent")

    response = model.invoke([HumanMessage(content="hello")])

    assert response.content == "ok"
    # The probe is the first thing built: the same request, asking for one
    # token, and waiting only as long as the policy's probe timeout.
    probe_build = factory.builds[0]
    assert probe_build["kwargs"]["timeout_seconds"] == 3
    assert probe_build["kwargs"]["max_tokens"] == 1
    build = factory.builds[1]
    assert build["route"].credential_ref == "endpoint:openai-direct"
    assert "api_key" not in build["route"].model_dump(mode="json")
    assert build["route"].credential_fingerprint
    assert factory.init_kwargs["credential_provider"].get("endpoint:openai-direct").get_secret_value() == "route-secret"
    call = factory.invocations[1]
    assert isinstance(call["messages"][0], SystemMessage)
    assert call["messages"][0].content == "Always be exact."


def test_thinking_protocol_uses_capability_value_not_field_presence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from graph_agent_gateway.registry.schema import CapabilityValue

    snapshot = _snapshot()
    route = snapshot.provider_routes["openai-direct:gpt-5"]
    snapshot.provider_routes["openai-direct:gpt-5"] = route.model_copy(
        update={
            "capabilities": {
                "thinking_protocol": CapabilityValue(value=False, source="manual"),
            }
        }
    )
    factory = _install_route_factory(monkeypatch)
    client_manager = RecordingClientManager()
    model = _resolver_from_snapshot(
        snapshot,
        client_manager=client_manager,
    ).resolve("graph_agent")

    model.invoke([HumanMessage(content="hello")])

    assert factory.builds[0]["kwargs"]["reasoning"] is False


def test_route_runtime_setting_not_capability_enables_thinking(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from graph_agent_gateway.registry.schema import CapabilityValue, RoleRouteEntry

    snapshot = _snapshot()
    route = snapshot.provider_routes["openai-direct:gpt-5"]
    snapshot.provider_routes["openai-direct:gpt-5"] = route.model_copy(
        update={
            "capabilities": {
                "thinking_protocol": CapabilityValue(value=True, source="manual"),
            }
        }
    )
    snapshot.roles["graph_agent"].fallback_chain = [
        RoleRouteEntry(
            route_id="openai-direct:gpt-5",
            runtime_settings={
                "max_output_tokens": 2048,
                "reasoning": {"enabled": True},
            },
        )
    ]
    factory = _install_route_factory(monkeypatch)
    client_manager = RecordingClientManager()
    model = _resolver_from_snapshot(
        snapshot,
        client_manager=client_manager,
    ).resolve("graph_agent")

    model.invoke([HumanMessage(content="hello")])

    assert model.thinking_enabled is True
    assert factory.builds[0]["kwargs"]["reasoning"] is True


def test_legacy_roles_schema_is_fatal(tmp_path: Path) -> None:

    credentials_path, roles_path = _write_registry_files(tmp_path)
    roles_path.write_text(
        yaml.safe_dump(
            {
                "models": {"GPT5": {"name": "GPT-5", "providers": {"openai": "gpt-5"}}},
                "providers": {"openai": {"name": "OpenAI", "type": "openai_compatible"}},
                "roles": {"graph_agent": {"active_model": "GPT5", "models": {}}},
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="legacy|schema_version"):
        _resolver_from_files(credentials_path, roles_path)


def test_gateway_runtime_source_has_no_engine_llm_imports() -> None:
    root = Path(__file__).resolve().parents[1] / "src" / "graph_agent_gateway"
    source = "\n".join(
        (root / name).read_text(encoding="utf-8")
        for name in ("resolver.py", "gateway_chat_model.py", "client_manager.py")
        if (root / name).exists()
    )

    assert "graph_agent.models.llm_client_manager" not in source
    assert "graph_agent.config.llm_config" not in source
    assert "_load_default_roles_data" not in source
    assert "GRAPH_AGENT_DEFAULT_ROLE" not in source
