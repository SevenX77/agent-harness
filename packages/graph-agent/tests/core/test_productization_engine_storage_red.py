from __future__ import annotations

import importlib
from typing import Any

import pytest

from graph_agent.core.adapter_contracts import RunArtifactRequest
from graph_agent.core.artifacts import ArtifactRef
from graph_agent.core.storage_contracts import InMemoryRunArtifactStore, InMemoryRuntimeStateStore


class SpyRunArtifactStore(InMemoryRunArtifactStore):
    def __init__(self) -> None:
        super().__init__()
        self.put_batch_calls = 0

    def put_batch(self, run_id: str, objects: dict[str, bytes]) -> Any:
        self.put_batch_calls += 1
        return super().put_batch(run_id, objects)


def _artifact_ref() -> ArtifactRef:
    return ArtifactRef(
        artifact_id="artifact-storage-demo",
        content_hash="sha256:storage-demo",
        store="ephemeral",
        manifest_ref="object://manifest.json",
        source_map_ref="object://source-map.json",
    )


def _request() -> RunArtifactRequest:
    return RunArtifactRequest(
        artifact_ref=_artifact_ref(),
        inputs={"topic": "red"},
        execution_context={"workspace_id": "local"},
        idempotency_key="idem-storage",
    )


def test_run_artifact_writes_outputs_through_run_artifact_store() -> None:
    runner = importlib.import_module("graph_agent.core.runner")
    store = SpyRunArtifactStore()

    session = runner.run_artifact(
        _request(),
        run_artifact_store=store,
        artifact_executor=lambda req: {"answer": "default-output"},
    )

    assert session.result_ref
    assert store.put_batch_calls >= 1


def test_run_artifact_store_keeps_sealed_run_closed_after_reopen_attempt() -> None:
    store = InMemoryRunArtifactStore()
    store.begin_run("sealed-run", metadata={"artifact_id": "artifact-storage-demo"})
    store.put_batch("sealed-run", {"before.txt": b"ok"})
    store.seal_run("sealed-run")

    store.begin_run("sealed-run", metadata={"artifact_id": "artifact-storage-demo"})

    with pytest.raises(Exception) as exc_info:
        store.put_batch("sealed-run", {"after.txt": b"blocked"})

    assert getattr(exc_info.value, "error_code", None) == "artifact.sealed_write"


def test_runtime_state_store_reports_lease_conflict_and_stale_fencing_codes() -> None:
    state_store = InMemoryRuntimeStateStore()
    first = state_store.acquire_lease("run-state", owner_id="worker-a", ttl_ms=1000)

    with pytest.raises(Exception) as conflict_info:
        state_store.acquire_lease("run-state", owner_id="worker-b", ttl_ms=1000)

    assert getattr(conflict_info.value, "error_code", None) == "state.lease_conflict"

    state_store.release("run-state", lease_token=first)
    second = state_store.acquire_lease("run-state", owner_id="worker-b", ttl_ms=1000)

    with pytest.raises(Exception) as fenced_info:
        state_store.snapshot("run-state", {"old": True}, lease_token=first)

    assert second.fencing_token > first.fencing_token
    assert getattr(fenced_info.value, "error_code", None) == "state.lease_fenced"


def test_checkpoint_snapshot_requires_runtime_state_store_lease() -> None:
    runtime_state = importlib.import_module("graph_agent.core.runtime_state")
    state_store = InMemoryRuntimeStateStore()

    with pytest.raises(Exception) as exc_info:
        runtime_state.snapshot_checkpoint(
            run_id="run-without-lease",
            state={"step": "draft"},
            runtime_state_store=state_store,
            lease_token=None,
        )

    assert getattr(exc_info.value, "error_code", None) == "state.lease_required"
