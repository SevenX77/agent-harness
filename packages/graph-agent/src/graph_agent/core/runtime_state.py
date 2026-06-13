from __future__ import annotations

from typing import Any

from graph_agent.core.storage_contracts import (
    LeaseToken,
    RuntimeStateStore,
    StateRef,
    StateVersionRef,
)


class StateLeaseRequiredError(Exception):
    def __init__(self, message: str = "Lease required to snapshot checkpoint") -> None:
        super().__init__(message)
        self.error_code = "state.lease_required"


def snapshot_checkpoint(
    *,
    run_id: str,
    state: dict[str, Any],
    runtime_state_store: RuntimeStateStore,
    lease_token: LeaseToken | None,
) -> StateVersionRef:
    if lease_token is None:
        raise StateLeaseRequiredError()
    return runtime_state_store.snapshot(run_id, state, lease_token=lease_token)


def restore_checkpoint(
    *,
    run_id: str,
    runtime_state_store: RuntimeStateStore,
    state_ref: StateRef | None = None,
) -> dict[str, Any]:
    return runtime_state_store.restore(run_id, state_ref=state_ref)
