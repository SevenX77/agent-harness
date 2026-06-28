from __future__ import annotations

import importlib
from pathlib import Path
from typing import Any

import pytest

from graph_agent.core.adapter_contracts import RunArtifactRequest
from graph_agent.core.artifacts import ArtifactRef
from graph_agent.core.runtime_state import StateLeaseRequiredError
from graph_agent.core.storage_contracts import (
    InMemoryRunArtifactStore,
    InMemoryRuntimeStateStore,
    LeaseConflictError,
    LeaseFencingError,
    SealedRunWriteError,
)
from graph_agent.io.storage import LegacyRunArtifactReadForbiddenError, StorageManager


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


def test_storage_manager_load_latest_rejects_run_scoped_artifact_as_business_fact(
    tmp_path: Path,
) -> None:
    writer = StorageManager(
        tmp_path / "workspace",
        skill_id="d2-storage",
        run_id="20260615T010000",
    )
    writer.get_output_dir()
    writer.save_artifact("outputs.json", {"answer": "legacy-file-payload"})

    reader = StorageManager(
        tmp_path / "workspace",
        skill_id="d2-storage",
        run_id="_probe",
    )
    reader.get_output_dir()

    with pytest.raises(LegacyRunArtifactReadForbiddenError) as exc_info:
        reader.load_latest(phase=None, name="outputs.json")

    assert getattr(exc_info.value, "error_code", None) == "artifact.legacy_storage_forbidden"


def test_storage_manager_read_artifact_helper_is_legacy_only(tmp_path: Path) -> None:
    artifact_path = (
        tmp_path / "workspace" / "runs" / "d2-storage" / "run-1" / "outputs.json"
    )
    artifact_path.parent.mkdir(parents=True)
    artifact_path.write_text('{"answer": "bare-file-payload"}', encoding="utf-8")

    with pytest.raises(LegacyRunArtifactReadForbiddenError) as exc_info:
        StorageManager._read_artifact(artifact_path)

    assert getattr(exc_info.value, "error_code", None) == "artifact.legacy_storage_forbidden"


def test_run_artifact_store_keeps_sealed_run_closed_after_reopen_attempt() -> None:
    store = InMemoryRunArtifactStore()
    store.begin_run("sealed-run", metadata={"artifact_id": "artifact-storage-demo"})
    store.put_batch("sealed-run", {"before.txt": b"ok"})
    store.seal_run("sealed-run")

    store.begin_run("sealed-run", metadata={"artifact_id": "artifact-storage-demo"})

    with pytest.raises(SealedRunWriteError) as exc_info:
        store.put_batch("sealed-run", {"after.txt": b"blocked"})

    assert getattr(exc_info.value, "error_code", None) == "artifact.sealed_write"


def test_runtime_state_store_reports_lease_conflict_and_stale_fencing_codes() -> None:
    state_store = InMemoryRuntimeStateStore()
    first = state_store.acquire_lease("run-state", owner_id="worker-a", ttl_ms=1000)

    with pytest.raises(LeaseConflictError) as conflict_info:
        state_store.acquire_lease("run-state", owner_id="worker-b", ttl_ms=1000)

    assert getattr(conflict_info.value, "error_code", None) == "state.lease_conflict"

    state_store.release("run-state", lease_token=first)
    second = state_store.acquire_lease("run-state", owner_id="worker-b", ttl_ms=1000)

    with pytest.raises(LeaseFencingError) as fenced_info:
        state_store.snapshot("run-state", {"old": True}, lease_token=first)

    assert second.fencing_token > first.fencing_token
    assert getattr(fenced_info.value, "error_code", None) == "state.lease_fenced"


def test_checkpoint_snapshot_requires_runtime_state_store_lease() -> None:
    runtime_state = importlib.import_module("graph_agent.core.runtime_state")
    state_store = InMemoryRuntimeStateStore()

    with pytest.raises(StateLeaseRequiredError) as exc_info:
        runtime_state.snapshot_checkpoint(
            run_id="run-without-lease",
            state={"step": "draft"},
            runtime_state_store=state_store,
            lease_token=None,
        )

    assert getattr(exc_info.value, "error_code", None) == "state.lease_required"


def test_resolve_checkpointer_keeps_different_sqlite_specs_isolated(tmp_path: Path) -> None:
    checkpointer_module = importlib.import_module("graph_agent.core.checkpointer")
    checkpointer_module.reset_checkpointer()

    first_db = tmp_path / "first" / "checkpoints.db"
    second_db = tmp_path / "second" / "checkpoints.db"

    try:
        first = checkpointer_module.resolve_checkpointer(f"sqlite:{first_db}")
        second = checkpointer_module.resolve_checkpointer(f"sqlite:{second_db}")
    finally:
        checkpointer_module.reset_checkpointer()

    assert first is not second


def test_get_checkpointer_keeps_different_sqlite_db_paths_isolated(tmp_path: Path) -> None:
    checkpointer_module = importlib.import_module("graph_agent.core.checkpointer")
    checkpointer_module.reset_checkpointer()

    first_db = tmp_path / "first" / "checkpoints.db"
    second_db = tmp_path / "second" / "checkpoints.db"

    try:
        first = checkpointer_module.get_checkpointer(db_path=first_db)
        second = checkpointer_module.get_checkpointer(db_path=second_db)
        first_again = checkpointer_module.get_checkpointer(db_path=first_db)
    finally:
        checkpointer_module.reset_checkpointer()

    assert first is not second
    assert first_again is first
