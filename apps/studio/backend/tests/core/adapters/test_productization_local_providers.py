from __future__ import annotations

import hashlib
import importlib
from pathlib import Path
from typing import Any

import pytest


def test_local_config_store_tracks_user_etag_and_if_match(tmp_path: Path) -> None:
    LocalGatewayConfigStore = _load_symbol(
        "app.core.adapters.gateway_config_store_local",
        "LocalGatewayConfigStore",
    )
    store = LocalGatewayConfigStore(root=tmp_path)

    with pytest.raises(ValueError):
        store.put_config(user_id="", key="llm.roles", value={"roles": {}})

    created = store.put_config(user_id="alice", key="llm.roles", value={"roles": {"writer": {}}})
    first_etag = _etag(created)
    record = store.get_config(user_id="alice", key="llm.roles")

    assert _field(record, "user_id") == "alice"
    assert _field(record, "key") == "llm.roles"
    assert _field(record, "etag") == first_etag
    assert _field(record, "value") == {"roles": {"writer": {}}}

    with pytest.raises(Exception) as exc_info:
        store.put_config(
            user_id="alice",
            key="llm.roles",
            value={"roles": {"critic": {}}},
            if_match="stale-etag",
        )

    assert _error_code(exc_info.value) == "config.etag_conflict"

    updated = store.put_config(
        user_id="alice",
        key="llm.roles",
        value={"roles": {"critic": {}}},
        if_match=first_etag,
    )
    assert _etag(updated) != first_etag


def test_product_artifact_store_get_by_hash_rejects_corrupted_bytes(tmp_path: Path) -> None:
    LocalProductArtifactStore = _load_symbol(
        "app.core.adapters.product_store_local",
        "LocalProductArtifactStore",
    )
    store = LocalProductArtifactStore(root=tmp_path)
    payload = b'{"artifact": "compiled"}'

    artifact_ref = store.put(content=payload, artifact_id="artifact-123")
    content_hash = _field(artifact_ref, "content_hash")

    assert content_hash == f"sha256:{hashlib.sha256(payload).hexdigest()}"
    assert store.get(content_hash) == payload

    blob_path = Path(store.blob_path(content_hash))
    blob_path.write_bytes(b"corrupted bytes")

    with pytest.raises(Exception) as exc_info:
        store.get(content_hash)

    assert _error_code(exc_info.value) == "artifact.hash_mismatch"


def test_runtime_state_store_rejects_missing_lease_and_stale_fencing_token(tmp_path: Path) -> None:
    LocalRuntimeStateStore = _load_symbol(
        "app.core.adapters.runtime_state_store_local",
        "LocalRuntimeStateStore",
    )
    store = LocalRuntimeStateStore(root=tmp_path)

    with pytest.raises(Exception) as exc_info:
        store.snapshot(run_id="run-123", state={"phase": "setup"}, lease=None)
    assert _error_code(exc_info.value) == "state.lease_required"

    stale_lease = store.acquire_lease(run_id="run-123", owner_id="worker-a", ttl_ms=0)
    current_lease = store.acquire_lease(run_id="run-123", owner_id="worker-b", ttl_ms=30_000)

    with pytest.raises(Exception) as exc_info:
        store.snapshot(run_id="run-123", state={"phase": "stale"}, lease=stale_lease)
    assert _error_code(exc_info.value) == "state.lease_fenced"

    store.snapshot(run_id="run-123", state={"phase": "current"}, lease=current_lease)
    assert _field(store.restore(run_id="run-123"), "state") == {"phase": "current"}


def test_runtime_state_store_fencing_token_stays_monotonic_after_release(tmp_path: Path) -> None:
    LocalRuntimeStateStore = _load_symbol(
        "app.core.adapters.runtime_state_store_local",
        "LocalRuntimeStateStore",
    )
    store = LocalRuntimeStateStore(root=tmp_path)

    released_lease = store.acquire_lease(run_id="run-123", owner_id="worker-a", ttl_ms=30_000)
    store.release(run_id="run-123", lease=released_lease)
    current_lease = store.acquire_lease(run_id="run-123", owner_id="worker-b", ttl_ms=30_000)

    assert _field(current_lease, "fencing_token") > _field(released_lease, "fencing_token")

    with pytest.raises(Exception) as exc_info:
        store.snapshot(run_id="run-123", state={"phase": "released"}, lease=released_lease)

    assert _error_code(exc_info.value) == "state.lease_fenced"


def test_run_artifact_store_rejects_writes_after_seal(tmp_path: Path) -> None:
    LocalRunArtifactStore = _load_symbol(
        "app.core.adapters.run_artifact_store_local",
        "LocalRunArtifactStore",
    )
    store = LocalRunArtifactStore(root=tmp_path)

    store.begin_run(run_id="run-123")
    store.put_batch(
        run_id="run-123",
        objects=[{"path": "trace.jsonl", "content": b'{"seq": 1}\n'}],
    )
    store.seal_run(run_id="run-123")

    with pytest.raises(Exception) as exc_info:
        store.put_batch(
            run_id="run-123",
            objects=[{"path": "trace.jsonl", "content": b'{"seq": 2}\n'}],
        )

    assert _error_code(exc_info.value) == "artifact.sealed_write"


def _load_symbol(module_name: str, symbol_name: str) -> Any:
    try:
        module = importlib.import_module(module_name)
    except ModuleNotFoundError as exc:
        pytest.fail(f"{module_name} is missing for the Studio MVP1 local provider contract: {exc}")
    try:
        return getattr(module, symbol_name)
    except AttributeError:
        pytest.fail(f"{module_name}.{symbol_name} is missing from the Studio MVP1 local provider contract")


def _field(value: Any, key: str) -> Any:
    if isinstance(value, dict):
        return value[key]
    return getattr(value, key)


def _etag(value: Any) -> str:
    if isinstance(value, str):
        return value
    return str(_field(value, "etag"))


def _error_code(exc: BaseException) -> str | None:
    return getattr(exc, "error_code", None) or getattr(exc, "code", None)
