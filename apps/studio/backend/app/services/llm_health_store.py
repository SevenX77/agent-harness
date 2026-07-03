"""Durable Studio runtime health state for LLM provider routes."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

CircuitScope = Literal["route", "endpoint", "rate_limit_bucket"]


@dataclass(frozen=True)
class RuntimeCircuit:
    scope: CircuitScope
    scope_id: str
    opened_at: datetime
    retry_at: datetime
    ttl_seconds: int
    reason_code: str
    failure_count: int = 1
    message: str | None = None


class SqliteLlmHealthStore:
    """Small SQLite store for runtime circuit state."""

    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._ensure_schema()

    def open_circuit(self, circuit: RuntimeCircuit) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO runtime_circuits (
                    scope, scope_id, opened_at, retry_at, ttl_seconds,
                    reason_code, failure_count, message
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(scope, scope_id) DO UPDATE SET
                    opened_at = excluded.opened_at,
                    retry_at = excluded.retry_at,
                    ttl_seconds = excluded.ttl_seconds,
                    reason_code = excluded.reason_code,
                    failure_count = excluded.failure_count,
                    message = excluded.message
                """,
                (
                    circuit.scope,
                    circuit.scope_id,
                    _to_iso(circuit.opened_at),
                    _to_iso(circuit.retry_at),
                    circuit.ttl_seconds,
                    circuit.reason_code,
                    circuit.failure_count,
                    circuit.message,
                ),
            )

    def clear_circuit(self, *, scope: CircuitScope, scope_id: str) -> None:
        with self._connect() as conn:
            conn.execute(
                "DELETE FROM runtime_circuits WHERE scope = ? AND scope_id = ?",
                (scope, scope_id),
            )

    def get_all_active_circuits(self, now: datetime | None = None) -> list[RuntimeCircuit]:
        """ONE query for every currently-open circuit, across every scope.

        R7-D: building the registry needs to know "which routes/endpoints are
        cooling down" — but the table itself is tiny (only actively-failing
        entries live here; on a normal running app it is usually EMPTY). Callers
        that need this once per request (e.g. a registry build covering hundreds
        of routes) must call this ONCE and build an ``ActiveCircuitsIndex`` from
        the result, not call the scoped ``get_active_circuits`` per route — that
        would be one SQLite round-trip per route for a lookup whose answer is
        almost always "nothing is open".
        """
        current_time = now or datetime.now(UTC)
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT scope, scope_id, opened_at, retry_at, ttl_seconds,
                       reason_code, failure_count, message
                FROM runtime_circuits
                """
            ).fetchall()
        return [
            _row_to_circuit(row)
            for row in rows
            if _from_iso(row["retry_at"]) > current_time
        ]

    def get_active_circuits(
        self,
        *,
        route_id: str,
        endpoint_id: str,
        rate_limit_bucket: str,
        now: datetime | None = None,
    ) -> list[RuntimeCircuit]:
        current_time = now or datetime.now(UTC)
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT scope, scope_id, opened_at, retry_at, ttl_seconds,
                       reason_code, failure_count, message
                FROM runtime_circuits
                WHERE (scope = 'route' AND scope_id = ?)
                   OR (scope = 'endpoint' AND scope_id = ?)
                   OR (scope = 'rate_limit_bucket' AND scope_id = ?)
                ORDER BY
                    CASE scope
                        WHEN 'route' THEN 0
                        WHEN 'endpoint' THEN 1
                        ELSE 2
                    END
                """,
                (route_id, endpoint_id, rate_limit_bucket),
            ).fetchall()
        return [
            _row_to_circuit(row)
            for row in rows
            if _from_iso(row["retry_at"]) > current_time
        ]

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _ensure_schema(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS runtime_circuits (
                    scope TEXT NOT NULL,
                    scope_id TEXT NOT NULL,
                    opened_at TEXT NOT NULL,
                    retry_at TEXT NOT NULL,
                    ttl_seconds INTEGER NOT NULL,
                    reason_code TEXT NOT NULL,
                    failure_count INTEGER NOT NULL,
                    message TEXT,
                    PRIMARY KEY (scope, scope_id)
                )
                """
            )


def _to_iso(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.isoformat()


def _from_iso(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed


def _row_to_circuit(row: sqlite3.Row) -> RuntimeCircuit:
    return RuntimeCircuit(
        scope=row["scope"],
        scope_id=row["scope_id"],
        opened_at=_from_iso(row["opened_at"]),
        retry_at=_from_iso(row["retry_at"]),
        ttl_seconds=row["ttl_seconds"],
        reason_code=row["reason_code"],
        failure_count=row["failure_count"],
        message=row["message"],
    )


@dataclass(frozen=True)
class ActiveCircuitsIndex:
    """In-memory snapshot of every open circuit, built from ONE query (R7-D).

    Membership per route is then O(1) dict lookups — an endpoint's circuit state
    is derived once (as part of building this index) regardless of how many
    routes/models hang off that endpoint, instead of being re-queried per route.
    """

    by_route: dict[str, list[RuntimeCircuit]]
    by_endpoint: dict[str, list[RuntimeCircuit]]
    by_bucket: dict[str, list[RuntimeCircuit]]

    @classmethod
    def build(cls, circuits: list[RuntimeCircuit]) -> ActiveCircuitsIndex:
        by_route: dict[str, list[RuntimeCircuit]] = {}
        by_endpoint: dict[str, list[RuntimeCircuit]] = {}
        by_bucket: dict[str, list[RuntimeCircuit]] = {}
        targets: dict[CircuitScope, dict[str, list[RuntimeCircuit]]] = {
            "route": by_route,
            "endpoint": by_endpoint,
            "rate_limit_bucket": by_bucket,
        }
        for circuit in circuits:
            targets[circuit.scope].setdefault(circuit.scope_id, []).append(circuit)
        return cls(by_route=by_route, by_endpoint=by_endpoint, by_bucket=by_bucket)

    def for_route(
        self, *, route_id: str, endpoint_id: str, rate_limit_bucket: str
    ) -> list[RuntimeCircuit]:
        """Circuits affecting one route, in the same route→endpoint→bucket
        priority order the old per-route SQL query returned."""
        return [
            *self.by_route.get(route_id, []),
            *self.by_endpoint.get(endpoint_id, []),
            *self.by_bucket.get(rate_limit_bucket, []),
        ]
