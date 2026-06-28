from __future__ import annotations

import dataclasses
import importlib
import inspect
from pathlib import Path
from typing import Any

import pytest

ENGINE_ROOT = Path(__file__).resolve().parents[2]


def _fields(cls: type[Any]) -> set[str]:
    if hasattr(cls, "model_fields"):
        return set(cls.model_fields)
    if dataclasses.is_dataclass(cls):
        return {field.name for field in dataclasses.fields(cls)}
    try:
        return {
            name
            for name in inspect.signature(cls).parameters
            if name != "self"
        }
    except (TypeError, ValueError):
        return set(getattr(cls, "__annotations__", {}))


def _method_parameters(cls: type[Any], name: str) -> set[str]:
    method = getattr(cls, name)
    return {
        parameter
        for parameter in inspect.signature(method).parameters
        if parameter != "self"
    }


def _first_ref(refs: Any) -> Any:
    if isinstance(refs, dict):
        return next(iter(refs.values()))
    return refs[0]


def _object_bytes(obj: Any) -> bytes:
    if isinstance(obj, bytes):
        return obj
    for attr in ("content", "data", "bytes"):
        if hasattr(obj, attr):
            value = getattr(obj, attr)
            if isinstance(value, bytes):
                return value
    raise AssertionError("get_object(hash=...) must return bytes or an object carrying bytes")


def _corrupt_store_bytes(store: Any, ref: Any, damaged: bytes) -> None:
    content_hash = ref.content_hash
    bytes_ref = getattr(ref, "bytes_ref", None)

    if hasattr(store, "corrupt_object_for_test"):
        store.corrupt_object_for_test(hash=content_hash, content=damaged)
        return

    for attr, key in (
        ("_objects", bytes_ref),
        ("_objects", content_hash),
        ("_content", content_hash),
        ("_content_by_hash", content_hash),
        ("_bytes_by_hash", content_hash),
    ):
        if key is None or not hasattr(store, attr):
            continue
        mapping = getattr(store, attr)
        if isinstance(mapping, dict) and key in mapping:
            mapping[key] = damaged
            return

    raise AssertionError(
        "InMemoryRunArtifactStore must expose corrupt_object_for_test(hash=..., content=...) "
        "or keep deterministic in-memory bytes for hash verification tests"
    )


def test_storage_protocols_define_run_artifact_and_runtime_state_methods() -> None:
    storage = importlib.import_module("graph_agent.core.storage_contracts")

    RunArtifactStore = storage.RunArtifactStore
    RuntimeStateStore = storage.RuntimeStateStore

    for method_name in ("begin_run", "put_batch", "seal_run", "get_object"):
        assert callable(getattr(RunArtifactStore, method_name, None))

    for method_name in ("acquire_lease", "heartbeat", "snapshot", "restore", "release"):
        assert callable(getattr(RuntimeStateStore, method_name, None))

    assert "hash" in _method_parameters(RunArtifactStore, "get_object")
    assert "lease_token" in _method_parameters(RuntimeStateStore, "snapshot")


def test_run_artifact_store_does_not_expose_test_corruption_helper_in_production_class() -> None:
    source = (ENGINE_ROOT / "src" / "graph_agent" / "core" / "storage_contracts.py").read_text(encoding="utf-8")

    assert "def corrupt_object_for_test" not in source


def test_run_artifact_store_rejects_writes_after_seal_with_explicit_error_code() -> None:
    storage = importlib.import_module("graph_agent.core.storage_contracts")

    store = storage.InMemoryRunArtifactStore()
    store.begin_run("run-sealed", metadata={"source": "contract-test"})
    refs = store.put_batch("run-sealed", {"outputs/value.txt": b"first"})
    assert _first_ref(refs).content_hash

    index = store.seal_run("run-sealed")
    assert index.run_id == "run-sealed"

    with pytest.raises(storage.SealedRunWriteError) as exc_info:
        store.put_batch("run-sealed", {"outputs/late.txt": b"late"})

    assert getattr(exc_info.value, "error_code", None) == "artifact.sealed_write"


def test_sealed_run_cannot_be_reopened_by_begin_run() -> None:
    storage = importlib.import_module("graph_agent.core.storage_contracts")

    store = storage.InMemoryRunArtifactStore()
    store.begin_run("run-sealed-reopened", metadata={"attempt": 1})
    store.put_batch("run-sealed-reopened", {"outputs/value.txt": b"first"})
    store.seal_run("run-sealed-reopened")

    store.begin_run("run-sealed-reopened", metadata={"attempt": 2})

    with pytest.raises(storage.SealedRunWriteError) as exc_info:
        store.put_batch("run-sealed-reopened", {"outputs/late.txt": b"late"})

    assert getattr(exc_info.value, "error_code", None) == "artifact.sealed_write"


def test_get_object_recomputes_hash_and_hard_fails_on_corrupt_bytes() -> None:
    storage = importlib.import_module("graph_agent.core.storage_contracts")

    store = storage.InMemoryRunArtifactStore()
    store.begin_run("run-hash", metadata={})
    refs = store.put_batch("run-hash", {"outputs/value.txt": b"original-bytes"})
    ref = _first_ref(refs)
    content_hash = ref.content_hash

    assert _object_bytes(store.get_object(hash=content_hash)) == b"original-bytes"

    _corrupt_store_bytes(store, ref, b"damaged-bytes")

    with pytest.raises(storage.HashMismatchError) as exc_info:
        store.get_object(hash=content_hash)

    assert getattr(exc_info.value, "error_code", None) == "artifact.hash_mismatch"


def test_lease_token_carries_monotonic_fencing_token() -> None:
    storage = importlib.import_module("graph_agent.core.storage_contracts")

    LeaseToken = storage.LeaseToken
    assert {
        "lease_id",
        "owner_id",
        "fencing_token",
        "ttl_ms",
        "safety_margin_ms",
    } <= _fields(LeaseToken)

    state_store = storage.InMemoryRuntimeStateStore()
    first = state_store.acquire_lease("run-lease", owner_id="worker-a", ttl_ms=1000)
    assert first.owner_id == "worker-a"
    assert isinstance(first.fencing_token, int)
    assert first.fencing_token >= 1

    state_store.release("run-lease", lease_token=first)
    second = state_store.acquire_lease("run-lease", owner_id="worker-b", ttl_ms=1000)

    assert second.owner_id == "worker-b"
    assert second.fencing_token > first.fencing_token


def test_released_lease_token_cannot_snapshot_again() -> None:
    storage = importlib.import_module("graph_agent.core.storage_contracts")

    state_store = storage.InMemoryRuntimeStateStore()
    lease = state_store.acquire_lease("run-release-fence", owner_id="worker-a", ttl_ms=1000)
    state_store.snapshot("run-release-fence", {"step": 1}, lease_token=lease)
    state_store.release("run-release-fence", lease_token=lease)

    with pytest.raises(storage.LeaseFencingError) as exc_info:
        state_store.snapshot("run-release-fence", {"step": 2}, lease_token=lease)

    assert getattr(exc_info.value, "error_code", None) == "state.lease_fenced"
