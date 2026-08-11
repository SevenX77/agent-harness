"""A role that resolved to nothing reaches the API saying why.

The gateway now returns a terminal ``error_code`` when every route a role names
was excluded. The adapter is the only place that turns a gateway result into the
Studio role model, so it is where that verdict either survives or is dropped —
and dropping it puts the caller back where it started: an empty list, and the
reason discovered only by running the role.

Decision: docs/design/2026-08-10-gateway-module-tree-and-probing-decision.md
"""

from __future__ import annotations

from app.core.adapters.gateway import GatewayAdapter
from app.models.llm_config import (
    LLMCredentialsFile,
    ProviderEndpoint,
    ProviderRoute,
    RoleEntry,
    RoleModelGroup,
    RoleProviderModel,
)
from pydantic import SecretStr


class _NoCircuits:
    def get_active_circuits(self, **kwargs: object) -> list[object]:
        return []


def _role(route_id: str) -> RoleEntry:
    return RoleEntry(
        model_groups=[
            RoleModelGroup(
                canonical_id="gpt-5",
                display_name="GPT-5",
                provider_models=[RoleProviderModel(route_id=route_id)],
            )
        ]
    )


def _credentials(*, route_status: str) -> LLMCredentialsFile:
    return LLMCredentialsFile(
        provider_endpoints={
            "ep-1": ProviderEndpoint(
                endpoint_id="ep-1",
                display_name="OpenAI",
                protocol="openai_compatible",
                base_url="https://api.openai.example/v1",
                api_key=SecretStr("secret"),
                status="verified",
            )
        },
        provider_routes={
            "ep-1:gpt-5": ProviderRoute(
                route_id="ep-1:gpt-5",
                endpoint_id="ep-1",
                route_slug="gpt-5",
                provider_model_id="gpt-5",
                canonical_id="gpt-5",
                status=route_status,
            )
        },
    )


def test_a_role_with_nothing_runnable_carries_the_terminal_error() -> None:
    adapter = GatewayAdapter(transport="in_process")

    materialized = adapter.materialize_role(
        {
            "role": _role("ep-1:gpt-5"),
            "credentials": _credentials(route_status="failed"),
            "health_store": _NoCircuits(),
        }
    )

    assert materialized.fallback_chain == []
    assert materialized.materialization_report["error_code"] == "resource.no_available_route"


def test_a_role_that_can_run_carries_no_error() -> None:
    adapter = GatewayAdapter(transport="in_process")

    materialized = adapter.materialize_role(
        {
            "role": _role("ep-1:gpt-5"),
            "credentials": _credentials(route_status="verified"),
            "health_store": _NoCircuits(),
        }
    )

    assert [entry.route_id for entry in materialized.fallback_chain] == ["ep-1:gpt-5"]
    assert materialized.materialization_report.get("error_code") is None
