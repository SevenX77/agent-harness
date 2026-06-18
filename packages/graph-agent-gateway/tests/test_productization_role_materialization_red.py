"""Gateway-owned role materialization rules for Studio adapter delegation."""

from __future__ import annotations

from types import SimpleNamespace

from pydantic import SecretStr


class NoCircuits:
    def get_active_circuits(self, **kwargs: object) -> list[object]:
        return []


def test_gateway_materializer_blocks_required_thinking_when_route_is_not_fit() -> None:
    from graph_agent_gateway.registry.schema import CapabilityValue, ProviderEndpoint, ProviderRoute
    from graph_agent_gateway.role_materialization import MaterializeRoleRequest, materialize_role

    role = _role(
        role_thinking="required",
        group_thinking="inherit",
        token_intent=None,
    )
    route = _route(
        capabilities={
            "thinking_protocol": CapabilityValue(value=False, source="provider_doc"),
        }
    )

    materialized = materialize_role(
        MaterializeRoleRequest(
            role=role,
            credentials=_credentials(
                endpoint=ProviderEndpoint(
                    endpoint_id="openai",
                    protocol="openai_compatible",
                    base_url="https://api.openai.example/v1",
                    api_key=SecretStr("secret"),
                    status="verified",
                ),
                route=route,
            ),
            health_store=NoCircuits(),
        )
    )

    assert materialized.fallback_chain == []
    assert materialized.materialization_report["entries"][0]["role_fit"] == "not_fit"
    assert materialized.materialization_report["entries"][0]["warnings"][0]["code"] == "thinking_unsupported"


def test_gateway_materializer_applies_output_token_intent_from_route_capability() -> None:
    from graph_agent_gateway.registry.schema import CapabilityValue, ProviderEndpoint, ProviderRoute
    from graph_agent_gateway.role_materialization import MaterializeRoleRequest, materialize_role

    role = _role(
        role_thinking="off",
        group_thinking="inherit",
        token_intent=SimpleNamespace(mode="target", value=10_000, downgrade="allow_with_warning"),
    )
    route = _route(
        capabilities={
            "max_output_tokens": CapabilityValue(
                value={"max": 8192, "default": 4096},
                source="provider_doc",
            )
        }
    )

    materialized = materialize_role(
        MaterializeRoleRequest(
            role=role,
            credentials=_credentials(
                endpoint=ProviderEndpoint(
                    endpoint_id="openai",
                    protocol="openai_compatible",
                    base_url="https://api.openai.example/v1",
                    api_key=SecretStr("secret"),
                    status="verified",
                ),
                route=route,
            ),
            health_store=NoCircuits(),
        )
    )

    assert materialized.fallback_chain[0].route_id == "openai:gpt-5"
    assert materialized.fallback_chain[0].runtime_settings.max_output_tokens == 8192
    assert materialized.materialization_report["entries"][0]["role_fit"] == "downgraded"
    assert materialized.materialization_report["warnings"][0]["code"] == "token_downgraded"


def test_gateway_materializer_accepts_credential_ref_only_endpoint() -> None:
    from graph_agent_gateway.registry.schema import ProviderEndpoint
    from graph_agent_gateway.role_materialization import MaterializeRoleRequest, materialize_role

    materialized = materialize_role(
        MaterializeRoleRequest(
            role=_role(
                role_thinking="off",
                group_thinking="inherit",
                token_intent=None,
            ),
            credentials=_credentials(
                endpoint=ProviderEndpoint(
                    endpoint_id="openai",
                    protocol="openai_compatible",
                    base_url="https://api.openai.example/v1",
                    credential_ref="credential:openai-prod",
                    api_key=None,
                    status="verified",
                ),
                route=_route(capabilities={}),
            ),
            health_store=NoCircuits(),
        )
    )

    assert [entry.route_id for entry in materialized.fallback_chain] == ["openai:gpt-5"]
    assert materialized.materialization_report["skipped_provider_details"] == []


def _role(
    *,
    role_thinking: str,
    group_thinking: str,
    token_intent: object | None,
) -> SimpleNamespace:
    role_intent = SimpleNamespace(
        thinking=role_thinking,
        target_output_tokens=token_intent,
    )
    group_intent = SimpleNamespace(
        thinking=group_thinking,
        target_output_tokens=None,
    )
    return SimpleNamespace(
        model_fallback_enabled=True,
        intent=role_intent,
        model_groups=[
            SimpleNamespace(
                canonical_id="gpt-5",
                intent=group_intent,
                provider_models=[
                    SimpleNamespace(route_id="openai:gpt-5"),
                ],
            )
        ],
    )


def _route(*, capabilities: dict[str, object]) -> object:
    from graph_agent_gateway.registry.schema import ProviderRoute

    return ProviderRoute(
        route_id="openai:gpt-5",
        endpoint_id="openai",
        route_slug="gpt-5",
        provider_model_id="gpt-5",
        canonical_id="gpt-5",
        status="verified",
        capabilities=capabilities,
    )


def _credentials(*, endpoint: object, route: object) -> SimpleNamespace:
    return SimpleNamespace(
        provider_endpoints={"openai": endpoint},
        provider_routes={"openai:gpt-5": route},
    )
