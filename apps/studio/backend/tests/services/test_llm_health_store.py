"""R7-D perf fix: circuit lookups must be ONE query per registry build, not one
per route. See llm_health_store.py's ActiveCircuitsIndex — PM 2026-07-03:
"一个 endpoint 挂 1 万个模型也不该被算 1 万次"."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from app.services.llm_health_store import (
    ActiveCircuitsIndex,
    RuntimeCircuit,
    SqliteLlmHealthStore,
)


def _circuit(
    *,
    scope: str,
    scope_id: str,
    now: datetime,
    ttl_seconds: int = 60,
    reason_code: str = "timeout",
) -> RuntimeCircuit:
    return RuntimeCircuit(
        scope=scope,  # type: ignore[arg-type]
        scope_id=scope_id,
        opened_at=now,
        retry_at=now + timedelta(seconds=ttl_seconds),
        ttl_seconds=ttl_seconds,
        reason_code=reason_code,
    )


@pytest.fixture
def store(tmp_path: Path) -> SqliteLlmHealthStore:
    return SqliteLlmHealthStore(tmp_path / "llm_health.sqlite")


def test_get_all_active_circuits_returns_every_open_scope_in_one_query(
    store: SqliteLlmHealthStore,
) -> None:
    now = datetime(2026, 7, 3, 12, 0, tzinfo=UTC)
    store.open_circuit(_circuit(scope="route", scope_id="ep:model-a", now=now))
    store.open_circuit(_circuit(scope="endpoint", scope_id="ep", now=now))
    store.open_circuit(_circuit(scope="rate_limit_bucket", scope_id="bucket-1", now=now))

    circuits = store.get_all_active_circuits(now)

    assert {(c.scope, c.scope_id) for c in circuits} == {
        ("route", "ep:model-a"),
        ("endpoint", "ep"),
        ("rate_limit_bucket", "bucket-1"),
    }


def test_get_all_active_circuits_excludes_expired(store: SqliteLlmHealthStore) -> None:
    now = datetime(2026, 7, 3, 12, 0, tzinfo=UTC)
    store.open_circuit(_circuit(scope="route", scope_id="ep:model-a", now=now, ttl_seconds=1))

    circuits = store.get_all_active_circuits(now + timedelta(seconds=120))

    assert circuits == []


def test_get_all_active_circuits_returns_empty_list_on_empty_table(
    store: SqliteLlmHealthStore,
) -> None:
    # R7-D root observation: on a normal running app NOTHING has failed yet, so
    # this table is empty — the common case must cost exactly one (cheap) query,
    # not be skipped via a special case that hides a bug for the non-empty case.
    assert store.get_all_active_circuits(datetime.now(UTC)) == []


def test_active_circuits_index_matches_route_endpoint_and_bucket_in_priority_order(
) -> None:
    now = datetime(2026, 7, 3, 12, 0, tzinfo=UTC)
    route_circuit = _circuit(scope="route", scope_id="ep:model-a", now=now)
    endpoint_circuit = _circuit(scope="endpoint", scope_id="ep", now=now)
    bucket_circuit = _circuit(scope="rate_limit_bucket", scope_id="bucket-1", now=now)
    index = ActiveCircuitsIndex.build([bucket_circuit, endpoint_circuit, route_circuit])

    matched = index.for_route(
        route_id="ep:model-a", endpoint_id="ep", rate_limit_bucket="bucket-1"
    )

    # Priority order preserved: route-scoped circuit first, then endpoint, then
    # bucket — matches the original ORDER BY CASE scope semantics.
    assert matched == [route_circuit, endpoint_circuit, bucket_circuit]


def test_active_circuits_index_route_with_no_open_circuit_returns_empty(
) -> None:
    index = ActiveCircuitsIndex.build([])

    assert index.for_route(
        route_id="ep:model-a", endpoint_id="ep", rate_limit_bucket="ep"
    ) == []


def test_active_circuits_index_endpoint_circuit_is_shared_by_every_route_under_it(
) -> None:
    # PM's exact scenario: one endpoint circuit must be usable by every route
    # hanging off that endpoint WITHOUT re-deriving/re-querying it per route —
    # an endpoint with 10,000 models still only has ONE endpoint-scope entry to
    # look up, an O(1) dict hit regardless of route count.
    now = datetime(2026, 7, 3, 12, 0, tzinfo=UTC)
    endpoint_circuit = _circuit(scope="endpoint", scope_id="big-endpoint", now=now)
    index = ActiveCircuitsIndex.build([endpoint_circuit])

    route_ids = [f"big-endpoint:model-{i}" for i in range(10_000)]
    for route_id in route_ids:
        matched = index.for_route(
            route_id=route_id,
            endpoint_id="big-endpoint",
            rate_limit_bucket="big-endpoint",
        )
        assert matched == [endpoint_circuit]
