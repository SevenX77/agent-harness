from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

from app.models.llm_config import ProviderEndpoint, ProviderRoute


def _endpoint(
    *,
    endpoint_id: str = "openai-direct",
    api_key: str | None = "secret",
    status: str = "verified",
) -> ProviderEndpoint:
    return ProviderEndpoint(
        endpoint_id=endpoint_id,
        display_name="OpenAI",
        protocol="openai_compatible",
        base_url="https://api.openai.example/v1",
        api_key=api_key,
        status=status,
    )


def _route(
    *,
    route_id: str = "openai-direct:gpt-5",
    status: str = "verified",
) -> ProviderRoute:
    endpoint_id, route_slug = route_id.split(":", 1)
    return ProviderRoute(
        route_id=route_id,
        endpoint_id=endpoint_id,
        route_slug=route_slug,
        provider_model_id=route_slug,
        canonical_id=route_slug,
        display_name=route_slug,
        status=status,
    )


def test_provider_state_projection_uses_explicit_priority_chain() -> None:
    from app.services.llm_health_store import RuntimeCircuit
    from app.services.llm_state_projection import project_provider_model_state

    now = datetime(2026, 5, 26, 12, 0, tzinfo=UTC)
    circuit = RuntimeCircuit(
        scope="route",
        scope_id="openai-direct:gpt-5",
        opened_at=now,
        retry_at=now + timedelta(seconds=30),
        ttl_seconds=30,
        reason_code="rate_limited",
        failure_count=1,
        message="429 from provider",
    )

    off_projection = project_provider_model_state(
        endpoint=_endpoint(status="disabled"),
        route=_route(status="verified"),
        circuits=[circuit],
        now=now,
    )
    assert off_projection.ui_state == "off"
    assert off_projection.retry_at is None

    setup_projection = project_provider_model_state(
        endpoint=_endpoint(api_key=None, status="verified"),
        route=_route(status="verified"),
        circuits=[circuit],
        now=now,
    )
    assert setup_projection.ui_state == "failed"
    assert setup_projection.reason_code == "missing_config"

    cooling_projection = project_provider_model_state(
        endpoint=_endpoint(status="verified"),
        route=_route(status="verified"),
        circuits=[circuit],
        now=now,
    )
    assert cooling_projection.ui_state == "cooling_down"
    assert cooling_projection.retry_at == (now + timedelta(seconds=30)).isoformat()
    assert cooling_projection.reason_code == "rate_limited"

    ready_projection = project_provider_model_state(
        endpoint=_endpoint(status="verified"),
        route=_route(status="verified"),
        circuits=[],
        now=now,
    )
    assert ready_projection.ui_state == "ready"

    untested_projection = project_provider_model_state(
        endpoint=_endpoint(status="unverified_manual"),
        route=_route(status="unverified_manual"),
        circuits=[],
        now=now,
    )
    assert untested_projection.ui_state == "untested"


def test_provider_state_projection_uses_farthest_retry_at_across_circuit_scopes() -> None:
    from app.services.llm_health_store import RuntimeCircuit
    from app.services.llm_state_projection import project_provider_model_state

    now = datetime(2026, 5, 26, 12, 0, tzinfo=UTC)
    route_retry = now + timedelta(seconds=20)
    endpoint_retry = now + timedelta(seconds=45)
    bucket_retry = now + timedelta(seconds=35)
    projection = project_provider_model_state(
        endpoint=_endpoint(status="verified"),
        route=_route(status="verified"),
        circuits=[
            RuntimeCircuit(
                scope="route",
                scope_id="openai-direct:gpt-5",
                opened_at=now,
                retry_at=route_retry,
                ttl_seconds=20,
                reason_code="route_timeout",
                failure_count=1,
                message="route timeout",
            ),
            RuntimeCircuit(
                scope="endpoint",
                scope_id="openai-direct",
                opened_at=now,
                retry_at=endpoint_retry,
                ttl_seconds=45,
                reason_code="endpoint_rate_limited",
                failure_count=2,
                message="endpoint limited",
            ),
            RuntimeCircuit(
                scope="rate_limit_bucket",
                scope_id="openai-shared",
                opened_at=now,
                retry_at=bucket_retry,
                ttl_seconds=35,
                reason_code="bucket_rate_limited",
                failure_count=3,
                message="bucket limited",
            ),
        ],
        now=now,
    )

    assert projection.ui_state == "cooling_down"
    assert projection.retry_at == endpoint_retry.isoformat()
    assert projection.reason_code == "endpoint_rate_limited"
    assert projection.ui_detail == "endpoint limited"


def test_provider_state_projection_ties_use_route_endpoint_bucket_message_priority() -> None:
    from app.services.llm_health_store import RuntimeCircuit
    from app.services.llm_state_projection import project_provider_model_state

    now = datetime(2026, 5, 26, 12, 0, tzinfo=UTC)
    retry_at = now + timedelta(seconds=30)

    projection = project_provider_model_state(
        endpoint=_endpoint(status="verified"),
        route=_route(status="verified"),
        circuits=[
            RuntimeCircuit(
                scope="rate_limit_bucket",
                scope_id="openai-direct",
                opened_at=now,
                retry_at=retry_at,
                ttl_seconds=30,
                reason_code="bucket_rate_limited",
                failure_count=3,
                message="bucket limited",
            ),
            RuntimeCircuit(
                scope="endpoint",
                scope_id="openai-direct",
                opened_at=now,
                retry_at=retry_at,
                ttl_seconds=30,
                reason_code="endpoint_rate_limited",
                failure_count=2,
                message="endpoint limited",
            ),
            RuntimeCircuit(
                scope="route",
                scope_id="openai-direct:gpt-5",
                opened_at=now,
                retry_at=retry_at,
                ttl_seconds=30,
                reason_code="route_timeout",
                failure_count=1,
                message="route timeout",
            ),
        ],
        now=now,
    )

    assert projection.ui_state == "cooling_down"
    assert projection.retry_at == retry_at.isoformat()
    assert projection.reason_code == "route_timeout"
    assert projection.ui_detail == "route timeout"

    projection_without_route = project_provider_model_state(
        endpoint=_endpoint(status="verified"),
        route=_route(status="verified"),
        circuits=[
            RuntimeCircuit(
                scope="rate_limit_bucket",
                scope_id="openai-direct",
                opened_at=now,
                retry_at=retry_at,
                ttl_seconds=30,
                reason_code="bucket_rate_limited",
                failure_count=3,
                message="bucket limited",
            ),
            RuntimeCircuit(
                scope="endpoint",
                scope_id="openai-direct",
                opened_at=now,
                retry_at=retry_at,
                ttl_seconds=30,
                reason_code="endpoint_rate_limited",
                failure_count=2,
                message="endpoint limited",
            ),
        ],
        now=now,
    )

    assert projection_without_route.reason_code == "endpoint_rate_limited"
    assert projection_without_route.ui_detail == "endpoint limited"


def test_sqlite_health_store_persists_and_clears_circuits(tmp_path: Path) -> None:
    from app.services.llm_health_store import RuntimeCircuit, SqliteLlmHealthStore

    now = datetime(2026, 5, 26, 12, 0, tzinfo=UTC)
    db_path = tmp_path / "llm_health.sqlite"
    store = SqliteLlmHealthStore(db_path)
    store.open_circuit(
        RuntimeCircuit(
            scope="route",
            scope_id="openai-direct:gpt-5",
            opened_at=now,
            retry_at=now + timedelta(seconds=60),
            ttl_seconds=60,
            reason_code="timeout",
            failure_count=1,
            message="probe timed out",
        )
    )

    reloaded = SqliteLlmHealthStore(db_path)
    active = reloaded.get_active_circuits(
        route_id="openai-direct:gpt-5",
        endpoint_id="openai-direct",
        rate_limit_bucket="openai-direct",
        now=now,
    )

    assert [circuit.scope for circuit in active] == ["route"]
    assert active[0].retry_at == now + timedelta(seconds=60)

    reloaded.clear_circuit(scope="route", scope_id="openai-direct:gpt-5")

    assert (
        reloaded.get_active_circuits(
            route_id="openai-direct:gpt-5",
            endpoint_id="openai-direct",
            rate_limit_bucket="openai-direct",
            now=now,
        )
        == []
    )


def test_sqlite_health_store_ignores_expired_circuits(tmp_path: Path) -> None:
    from app.services.llm_health_store import RuntimeCircuit, SqliteLlmHealthStore

    now = datetime(2026, 5, 26, 12, 0, tzinfo=UTC)
    db_path = tmp_path / "llm_health.sqlite"
    store = SqliteLlmHealthStore(db_path)
    store.open_circuit(
        RuntimeCircuit(
            scope="route",
            scope_id="openai-direct:gpt-5",
            opened_at=now - timedelta(minutes=2),
            retry_at=now - timedelta(minutes=1),
            ttl_seconds=60,
            reason_code="timeout",
            failure_count=1,
            message="expired timeout",
        )
    )

    assert (
        store.get_active_circuits(
            route_id="openai-direct:gpt-5",
            endpoint_id="openai-direct",
            rate_limit_bucket="openai-direct",
            now=now,
        )
        == []
    )


def test_sqlite_health_store_persists_endpoint_and_bucket_scope_circuits(
    tmp_path: Path,
) -> None:
    from app.services.llm_health_store import RuntimeCircuit, SqliteLlmHealthStore

    now = datetime(2026, 5, 26, 12, 0, tzinfo=UTC)
    db_path = tmp_path / "llm_health.sqlite"
    store = SqliteLlmHealthStore(db_path)
    store.open_circuit(
        RuntimeCircuit(
            scope="endpoint",
            scope_id="openai-direct",
            opened_at=now,
            retry_at=now + timedelta(seconds=40),
            ttl_seconds=40,
            reason_code="endpoint_rate_limited",
            failure_count=2,
            message="endpoint limited",
        )
    )
    store.open_circuit(
        RuntimeCircuit(
            scope="rate_limit_bucket",
            scope_id="shared-openai-key",
            opened_at=now,
            retry_at=now + timedelta(seconds=50),
            ttl_seconds=50,
            reason_code="bucket_rate_limited",
            failure_count=3,
            message="bucket limited",
        )
    )

    active = SqliteLlmHealthStore(db_path).get_active_circuits(
        route_id="openai-direct:gpt-5",
        endpoint_id="openai-direct",
        rate_limit_bucket="shared-openai-key",
        now=now,
    )

    assert {circuit.scope for circuit in active} == {"endpoint", "rate_limit_bucket"}
    assert {circuit.scope_id for circuit in active} == {"openai-direct", "shared-openai-key"}
