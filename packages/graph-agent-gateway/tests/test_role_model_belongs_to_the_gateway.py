"""The role a gateway materializes is the gateway's own model.

``materialize_role`` reads ``role.model_groups``, ``role.intent`` and
``role.model_fallback_enabled`` — and until this change none of them existed on
this package's ``RoleEntry``. They lived on Studio's subclass, together with
``RoleIntent``, ``RoleModelGroup`` and ``RoleProviderModel``, so feeding the
gateway's own ``RoleEntry`` to the gateway's own materializer produced an empty
chain, and this package's tests hand-rolled fake role classes because no real
type could express the input. Same defect class as ``route.evidence`` (#778):
an SDK depending on a shape only one host happens to have.

Decision record: docs/design/2026-08-13-gateway-role-model-and-section-truth-decision.md

The health store stays host-owned (its sqlite persistence is a separate
sink-down item), so it enters through a Port: ``HealthStore`` /
``ActiveCircuit`` Protocols in ``registry/contracts.py``, which Studio's
``SqliteLlmHealthStore`` / ``RuntimeCircuit`` satisfy structurally.
"""

from __future__ import annotations

import inspect
import re
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from graph_agent_gateway.registry import (
    AUTHORED_TEMPERATURE_MAX,
    ActiveCircuit,
    HealthStore,
    ProviderEndpoint,
    ProviderRoute,
    RegistrySnapshot,
    RoleEntry,
    RoleIntent,
    RoleModelGroup,
    RoleProviderModel,
)
from graph_agent_gateway.role import MaterializeRoleRequest, materialization, materialize_role


def _role(**intent_overrides: object) -> RoleEntry:
    return RoleEntry(
        intent=RoleIntent(**intent_overrides),  # type: ignore[arg-type]
        model_groups=[
            RoleModelGroup(
                canonical_id="gpt-5",
                display_name="GPT 5",
                provider_models=[RoleProviderModel(route_id="openai:gpt-5")],
            )
        ],
    )


def _snapshot() -> RegistrySnapshot:
    return RegistrySnapshot(
        provider_endpoints={
            "openai": ProviderEndpoint(
                endpoint_id="openai",
                protocol="openai_compatible",
                base_url="https://api.openai.example/v1",
                credential_ref="cred://openai",
                status="verified",
            )
        },
        provider_routes={
            "openai:gpt-5": ProviderRoute(
                route_id="openai:gpt-5",
                endpoint_id="openai",
                route_slug="gpt-5",
                provider_model_id="gpt-5",
                status="verified",
            )
        },
    )


def test_the_gateways_own_role_entry_is_what_the_materializer_walks() -> None:
    for field in ("model_fallback_enabled", "intent", "model_groups"):
        assert field in RoleEntry.model_fields

    materialized = materialize_role(MaterializeRoleRequest(role=_role(), credentials=_snapshot()))

    assert [entry.route_id for entry in materialized.fallback_chain] == ["openai:gpt-5"]
    assert materialized.error_code is None


def test_the_request_names_its_role_and_its_health_store() -> None:
    annotations = inspect.get_annotations(MaterializeRoleRequest, eval_str=False)

    assert annotations["role"] == "RoleEntry"
    assert annotations["health_store"] == "HealthStore | None"


def test_nothing_is_read_as_a_dict_or_an_object_whichever_this_is() -> None:
    """The helper that hid ``endpoint.secret_handle`` (#778) is gone entirely.

    Word-boundary match on purpose: ``get_secret_value(`` ends in the same
    letters and is a real, typed call.
    """

    assert not re.search(r"(?<!\w)_value\(", inspect.getsource(materialization))


def test_the_temperature_dial_rule_travelled_with_the_model() -> None:
    """Storing what the dial can express is a rule about the authored share,
    and the share arithmetic already lives in this package (registry/bounds.py)."""

    assert RoleIntent(temperature=99.0).temperature == AUTHORED_TEMPERATURE_MAX
    assert RoleIntent(temperature=-3.0).temperature == 0.0
    assert RoleIntent().temperature == 0.7 * AUTHORED_TEMPERATURE_MAX


@dataclass(frozen=True)
class _HostCircuit:
    """The shape Studio's ``RuntimeCircuit`` has, declared independently here:
    the Port must be satisfiable without importing anything of Studio's."""

    scope: str
    scope_id: str
    retry_at: datetime
    reason_code: str
    message: str | None = None


class _HostStore:
    def __init__(self, circuits: list[_HostCircuit]) -> None:
        self._circuits = circuits

    def get_active_circuits(
        self,
        *,
        route_id: str,
        endpoint_id: str,
        rate_limit_bucket: str,
        now: datetime | None = None,
    ) -> list[_HostCircuit]:
        return list(self._circuits)


def test_a_host_shaped_store_satisfies_the_port() -> None:
    store: HealthStore = _HostStore([])
    circuit: ActiveCircuit = _HostCircuit(
        scope="route",
        scope_id="openai:gpt-5",
        retry_at=datetime.now(UTC),
        reason_code="rate_limited",
    )

    assert store.get_active_circuits(
        route_id="openai:gpt-5", endpoint_id="openai", rate_limit_bucket="openai"
    ) == []
    assert circuit.scope == "route"


def test_an_open_circuit_reaches_the_report_as_cooling_down() -> None:
    retry_at = datetime.now(UTC) + timedelta(minutes=5)
    store = _HostStore(
        [
            _HostCircuit(
                scope="route",
                scope_id="openai:gpt-5",
                retry_at=retry_at,
                reason_code="rate_limited",
                message="cooling down",
            )
        ]
    )

    materialized = materialize_role(
        MaterializeRoleRequest(role=_role(), credentials=_snapshot(), health_store=store)
    )

    warning_codes = [warning["code"] for warning in materialized.materialization_report["warnings"]]
    assert "cooling_down" in warning_codes
    assert [entry.route_id for entry in materialized.fallback_chain] == ["openai:gpt-5"]
