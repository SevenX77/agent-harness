"""Gateway-owned role materialization rules for Studio adapter delegation.

PR3: role intent is now three role-level params — ``thinking`` (bool, best
effort), ``max_output_tokens`` (int|None, clamped to the route range), and
``temperature`` (float|None). There is no per-group intent, no token mode /
downgrade, and thinking-unsupported is a non-blocking warning (never not_fit /
needs_test / downgraded).
"""

from __future__ import annotations

from pydantic import SecretStr


class NoCircuits:
    def get_active_circuits(self, **kwargs: object) -> list[object]:
        return []


def test_thinking_true_supported_enables_reasoning() -> None:
    from graph_agent_gateway.registry import CapabilityValue
    from graph_agent_gateway.role_materialization import MaterializeRoleRequest, materialize_role

    route = _route(
        capabilities={
            "thinking_protocol": CapabilityValue(value=True, source="probed_verified"),
        }
    )
    materialized = materialize_role(
        MaterializeRoleRequest(
            role=_role(thinking=True),
            credentials=_credentials(endpoint=_endpoint(), route=route),
            health_store=NoCircuits(),
        )
    )

    assert [entry.route_id for entry in materialized.fallback_chain] == ["openai:gpt-5"]
    assert materialized.fallback_chain[0].runtime_settings.reasoning.enabled is True
    # The report carries the raw resolved dict the caller writes into the chain.
    resolved = materialized.materialization_report["entries"][0]["resolved_settings"]
    assert resolved["reasoning"] == {"enabled": True}
    entry = materialized.materialization_report["entries"][0]
    assert entry["role_fit"] == "using"
    assert entry["warnings"] == []


def test_thinking_true_unsupported_warns_but_still_fits() -> None:
    from graph_agent_gateway.registry import CapabilityValue
    from graph_agent_gateway.role_materialization import MaterializeRoleRequest, materialize_role

    route = _route(
        capabilities={
            "thinking_protocol": CapabilityValue(value=False, source="provider_doc"),
        }
    )
    materialized = materialize_role(
        MaterializeRoleRequest(
            role=_role(thinking=True),
            credentials=_credentials(endpoint=_endpoint(), route=route),
            health_store=NoCircuits(),
        )
    )

    # Best-effort: unsupported thinking is a warning, NOT a fit downgrade or skip.
    assert [entry.route_id for entry in materialized.fallback_chain] == ["openai:gpt-5"]
    entry = materialized.materialization_report["entries"][0]
    assert entry["role_fit"] == "using"
    assert entry["warnings"][0]["code"] == "thinking_unsupported"
    # Reasoning is NOT enabled on an unsupported route.
    assert materialized.fallback_chain[0].runtime_settings.reasoning.enabled is None
    assert "reasoning" not in entry["resolved_settings"]


def test_thinking_false_does_nothing() -> None:
    from graph_agent_gateway.registry import CapabilityValue
    from graph_agent_gateway.role_materialization import MaterializeRoleRequest, materialize_role

    route = _route(
        capabilities={
            "thinking_protocol": CapabilityValue(value=True, source="probed_verified"),
        }
    )
    materialized = materialize_role(
        MaterializeRoleRequest(
            role=_role(thinking=False),
            credentials=_credentials(endpoint=_endpoint(), route=route),
            health_store=NoCircuits(),
        )
    )

    entry = materialized.materialization_report["entries"][0]
    assert entry["role_fit"] == "using"
    assert entry["warnings"] == []
    assert materialized.fallback_chain[0].runtime_settings.reasoning.enabled is None
    assert "reasoning" not in entry["resolved_settings"]


def test_max_output_tokens_none_uses_route_max() -> None:
    from graph_agent_gateway.registry import CapabilityValue
    from graph_agent_gateway.role_materialization import MaterializeRoleRequest, materialize_role

    route = _route(
        capabilities={
            "max_output_tokens": CapabilityValue(
                value={"min": 1, "max": 65536, "default": 4096},
                source="provider_doc",
            )
        }
    )
    materialized = materialize_role(
        MaterializeRoleRequest(
            role=_role(max_output_tokens=None),
            credentials=_credentials(endpoint=_endpoint(), route=route),
            health_store=NoCircuits(),
        )
    )

    assert materialized.fallback_chain[0].runtime_settings.max_output_tokens == 65536
    assert materialized.materialization_report["entries"][0]["role_fit"] == "using"


def test_max_output_tokens_above_route_max_is_clamped_down() -> None:
    from graph_agent_gateway.registry import CapabilityValue
    from graph_agent_gateway.role_materialization import MaterializeRoleRequest, materialize_role

    route = _route(
        capabilities={
            "max_output_tokens": CapabilityValue(
                value={"min": 16, "max": 8192, "default": 4096},
                source="provider_doc",
            )
        }
    )
    materialized = materialize_role(
        MaterializeRoleRequest(
            role=_role(max_output_tokens=999_999),
            credentials=_credentials(endpoint=_endpoint(), route=route),
            health_store=NoCircuits(),
        )
    )

    # Clamped to route max, never not_fit / downgraded.
    assert materialized.fallback_chain[0].runtime_settings.max_output_tokens == 8192
    assert materialized.materialization_report["entries"][0]["role_fit"] == "using"


def test_max_output_tokens_below_route_min_is_clamped_up() -> None:
    from graph_agent_gateway.registry import CapabilityValue
    from graph_agent_gateway.role_materialization import MaterializeRoleRequest, materialize_role

    route = _route(
        capabilities={
            "max_output_tokens": CapabilityValue(
                value={"min": 256, "max": 8192, "default": 4096},
                source="provider_doc",
            )
        }
    )
    materialized = materialize_role(
        MaterializeRoleRequest(
            role=_role(max_output_tokens=8),
            credentials=_credentials(endpoint=_endpoint(), route=route),
            health_store=NoCircuits(),
        )
    )

    assert materialized.fallback_chain[0].runtime_settings.max_output_tokens == 256
    assert materialized.materialization_report["entries"][0]["role_fit"] == "using"


def test_temperature_is_applied_to_resolved_settings() -> None:
    from graph_agent_gateway.role_materialization import MaterializeRoleRequest, materialize_role

    materialized = materialize_role(
        MaterializeRoleRequest(
            role=_role(temperature=0.2),
            credentials=_credentials(endpoint=_endpoint(), route=_route(capabilities={})),
            health_store=NoCircuits(),
        )
    )

    assert materialized.fallback_chain[0].runtime_settings.temperature == 0.2
    assert materialized.materialization_report["entries"][0]["role_fit"] == "using"


def test_materializer_accepts_credential_ref_only_endpoint() -> None:
    from graph_agent_gateway.registry import ProviderEndpoint
    from graph_agent_gateway.role_materialization import MaterializeRoleRequest, materialize_role

    materialized = materialize_role(
        MaterializeRoleRequest(
            role=_role(),
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


# ---------------------------------------------------------------------------
# Fixtures — the role/group shape the materializer walks (duck-typed).
# ---------------------------------------------------------------------------


class _RoleIntent:
    def __init__(
        self,
        *,
        thinking: bool,
        max_output_tokens: int | None,
        temperature: float | None,
    ) -> None:
        self.provider_preference = "manual_order"
        self.thinking = thinking
        self.max_output_tokens = max_output_tokens
        self.temperature = temperature


class _ProviderModel:
    def __init__(self, route_id: str) -> None:
        self.route_id = route_id


class _Group:
    def __init__(self) -> None:
        self.canonical_id = "gpt-5"
        self.provider_models = [_ProviderModel("openai:gpt-5")]


class _Role:
    def __init__(self, intent: _RoleIntent) -> None:
        self.model_fallback_enabled = True
        self.intent = intent
        self.model_groups = [_Group()]


class _Credentials:
    def __init__(self, endpoint: object, route: object) -> None:
        self.provider_endpoints = {"openai": endpoint}
        self.provider_routes = {"openai:gpt-5": route}


def _role(
    *,
    thinking: bool = False,
    max_output_tokens: int | None = None,
    temperature: float | None = None,
) -> _Role:
    return _Role(
        _RoleIntent(
            thinking=thinking,
            max_output_tokens=max_output_tokens,
            temperature=temperature,
        )
    )


def _endpoint() -> object:
    from graph_agent_gateway.registry import ProviderEndpoint

    return ProviderEndpoint(
        endpoint_id="openai",
        protocol="openai_compatible",
        base_url="https://api.openai.example/v1",
        api_key=SecretStr("secret"),
        status="verified",
    )


def _route(*, capabilities: dict[str, object]) -> object:
    from graph_agent_gateway.registry import ProviderRoute

    return ProviderRoute(
        route_id="openai:gpt-5",
        endpoint_id="openai",
        route_slug="gpt-5",
        provider_model_id="gpt-5",
        canonical_id="gpt-5",
        status="verified",
        capabilities=capabilities,
    )


def _credentials(*, endpoint: object, route: object) -> _Credentials:
    return _Credentials(endpoint, route)
