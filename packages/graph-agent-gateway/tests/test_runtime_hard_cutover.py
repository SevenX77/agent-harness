"""Gateway runtime hard-cutover tests."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
import yaml
from langchain_core.messages import HumanMessage
from pydantic import SecretStr


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
        self.probes: list[tuple[str, int]] = []
        self.dispatches: list[dict[str, Any]] = []
        self.marked_down: list[tuple[str, str]] = []

    def is_provider_marked_down(self, route: Any, runtime_policy: Any) -> bool:
        return False

    def probe_provider(self, route: Any, runtime_policy: Any) -> bool:
        self.probes.append((route.route_id, runtime_policy.probe_timeout_seconds))
        return True

    def dispatch_provider_call(
        self,
        route: Any,
        messages: list[dict[str, Any]],
        **kwargs: Any,
    ) -> dict[str, Any]:
        self.dispatches.append({"route": route, "messages": messages, "kwargs": kwargs})
        return {
            "content": "ok",
            "usage": {"prompt_tokens": 2, "completion_tokens": 1, "total_tokens": 3},
            "finish_reason": "stop",
        }

    def mark_provider_down(self, route: Any, exc: BaseException, runtime_policy: Any) -> None:
        self.marked_down.append((route.route_id, str(exc)))

    def usage_total_calls(self, route: Any) -> int:
        return len(self.dispatches)


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


def test_model_resolver_requires_explicit_registry_source() -> None:
    from graph_agent_gateway.resolver import ModelResolver

    with pytest.raises(ValueError, match="registry_snapshot|credentials_path"):
        ModelResolver()


def test_model_resolver_loads_explicit_v4_v2_files(tmp_path: Path) -> None:
    from graph_agent_gateway.gateway_chat_model import GatewayChatModel
    from graph_agent_gateway.resolver import ModelResolver

    credentials_path, roles_path = _write_registry_files(tmp_path)
    client_manager = RecordingClientManager()
    resolver = ModelResolver(
        credentials_path=credentials_path,
        roles_path=roles_path,
        client_manager=client_manager,
    )

    model = resolver.resolve("graph_agent", phase_name="draft")

    assert isinstance(model, GatewayChatModel)
    assert model.max_tokens == 2048
    assert model.temperature == 0.25
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
    from graph_agent_gateway.resolver import ModelResolver

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

    resolver = ModelResolver(credentials_path=credentials_path, roles_path=roles_path)
    model = resolver.resolve("graph_agent", phase_name="draft")

    assert isinstance(model, GatewayChatModel)
    assert [route.route_id for route in model.resolved_role.routes] == [
        "openai-direct:gpt-5",
        "openrouter-prod:openai.gpt-5",
    ]


def test_model_override_is_exact_route_id() -> None:
    from graph_agent_gateway.resolver import ModelResolver

    resolver = ModelResolver(registry_snapshot=_snapshot())

    model = resolver.resolve("graph_agent", model_override="openrouter-prod:openai.gpt-5")
    assert [route.route_id for route in model.resolved_role.routes] == [
        "openrouter-prod:openai.gpt-5"
    ]

    with pytest.raises(Exception, match="route"):
        resolver.resolve("graph_agent", model_override="gpt-5")


def test_runtime_uses_route_secret_and_no_provider_env(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from graph_agent_gateway.resolver import ModelResolver

    for key in (
        "OPENAI_API_KEY",
        "ANTHROPIC_API_KEY",
        "GOOGLE_API_KEY",
        "GEMINI_API_KEY",
        "OPENROUTER_API_KEY",
        "WAVESPEED_API_KEY",
    ):
        monkeypatch.delenv(key, raising=False)

    client_manager = RecordingClientManager()
    model = ModelResolver(
        registry_snapshot=_snapshot(),
        client_manager=client_manager,
    ).resolve("graph_agent")

    response = model.invoke([HumanMessage(content="hello")])

    assert response.content == "ok"
    assert client_manager.probes == [("openai-direct:gpt-5", 3)]
    dispatch = client_manager.dispatches[0]
    assert dispatch["route"].api_key.get_secret_value() == "route-secret"
    assert dispatch["route"].credential_fingerprint
    assert dispatch["kwargs"]["runtime_policy"].token_escalation_rounds == 1
    assert dispatch["messages"][0] == {"role": "system", "content": "Always be exact."}


def test_thinking_protocol_uses_capability_value_not_field_presence() -> None:
    from graph_agent_gateway.registry.schema import CapabilityValue
    from graph_agent_gateway.resolver import ModelResolver

    snapshot = _snapshot()
    route = snapshot.provider_routes["openai-direct:gpt-5"]
    snapshot.provider_routes["openai-direct:gpt-5"] = route.model_copy(
        update={
            "capabilities": {
                "thinking_protocol": CapabilityValue(value=False, source="manual"),
            }
        }
    )
    client_manager = RecordingClientManager()
    model = ModelResolver(
        registry_snapshot=snapshot,
        client_manager=client_manager,
    ).resolve("graph_agent")

    model.invoke([HumanMessage(content="hello")])

    assert client_manager.dispatches[0]["kwargs"]["reasoning"] is False


def test_route_runtime_setting_not_capability_enables_thinking() -> None:
    from graph_agent_gateway.registry.schema import CapabilityValue, RoleRouteEntry
    from graph_agent_gateway.resolver import ModelResolver

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
    client_manager = RecordingClientManager()
    model = ModelResolver(
        registry_snapshot=snapshot,
        client_manager=client_manager,
    ).resolve("graph_agent")

    model.invoke([HumanMessage(content="hello")])

    assert model.thinking_enabled is True
    assert client_manager.dispatches[0]["kwargs"]["reasoning"] is True


def test_legacy_roles_schema_is_fatal(tmp_path: Path) -> None:
    from graph_agent_gateway.resolver import ModelResolver

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
        ModelResolver(credentials_path=credentials_path, roles_path=roles_path)


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
