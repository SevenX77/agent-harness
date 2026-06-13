from __future__ import annotations

import hashlib
from typing import Any, Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict, Field


class ObjectRef(BaseModel):
    model_config = ConfigDict(frozen=True)
    bytes_ref: str
    content_hash: str
    size_bytes: int
    path: str | None = None


class StoredObject(BaseModel):
    model_config = ConfigDict(frozen=True)
    content: bytes
    content_hash: str


class RunArtifactIndex(BaseModel):
    model_config = ConfigDict(frozen=True)
    run_id: str
    objects: list[ObjectRef] = Field(default_factory=list)
    sealed: bool


class LeaseToken(BaseModel):
    model_config = ConfigDict(frozen=True)
    lease_id: str
    owner_id: str
    fencing_token: int
    ttl_ms: int
    safety_margin_ms: int


class StateRef(BaseModel):
    model_config = ConfigDict(frozen=True)
    run_id: str
    version: int


class StateVersionRef(BaseModel):
    model_config = ConfigDict(frozen=True)
    run_id: str
    version: int
    fencing_token: int


class HashMismatchError(Exception):
    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.error_code = "artifact.hash_mismatch"


class SealedRunWriteError(Exception):
    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.error_code = "artifact.sealed_write"


class LeaseConflictError(Exception):
    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.error_code = "state.lease_conflict"


class LeaseFencingError(Exception):
    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.error_code = "state.lease_fenced"


@runtime_checkable
class RunArtifactStore(Protocol):
    def begin_run(self, run_id: str, metadata: dict[str, Any]) -> None:
        ...

    def put_batch(self, run_id: str, objects: dict[str, bytes]) -> list[ObjectRef] | dict[str, ObjectRef]:
        ...

    def seal_run(self, run_id: str) -> RunArtifactIndex:
        ...

    def get_object(self, *, hash: str) -> bytes | StoredObject:
        ...


@runtime_checkable
class RuntimeStateStore(Protocol):
    def acquire_lease(self, run_id: str, *, owner_id: str, ttl_ms: int) -> LeaseToken:
        ...

    def heartbeat(self, run_id: str, *, lease_token: LeaseToken) -> LeaseToken:
        ...

    def snapshot(self, run_id: str, state: dict[str, Any], *, lease_token: LeaseToken) -> StateVersionRef:
        ...

    def restore(self, run_id: str, *, state_ref: StateRef | None = None) -> dict[str, Any]:
        ...

    def release(self, run_id: str, *, lease_token: LeaseToken) -> None:
        ...


class InMemoryRunArtifactStore:
    def __init__(self) -> None:
        self._runs_metadata: dict[str, dict[str, Any]] = {}
        self._run_objects: dict[str, list[ObjectRef]] = {}
        self._sealed: dict[str, bool] = {}
        self._objects: dict[str, bytes] = {}

    def begin_run(self, run_id: str, metadata: dict[str, Any]) -> None:
        self._runs_metadata[run_id] = metadata
        self._run_objects.setdefault(run_id, [])
        self._sealed.setdefault(run_id, False)

    def put_batch(self, run_id: str, objects: dict[str, bytes]) -> list[ObjectRef] | dict[str, ObjectRef]:
        if self._sealed.get(run_id, False):
            raise SealedRunWriteError(f"Cannot write to sealed run {run_id}")

        refs: list[ObjectRef] = []
        for path, content in objects.items():
            content_hash = hashlib.sha256(content).hexdigest()
            self._objects[content_hash] = content
            ref = ObjectRef(
                bytes_ref=f"bytes://{content_hash}",
                content_hash=content_hash,
                size_bytes=len(content),
                path=path,
            )
            refs.append(ref)
            if run_id in self._run_objects:
                self._run_objects[run_id].append(ref)
        return refs

    def seal_run(self, run_id: str) -> RunArtifactIndex:
        self._sealed[run_id] = True
        objects = self._run_objects.get(run_id, [])
        return RunArtifactIndex(run_id=run_id, objects=objects, sealed=True)

    def get_object(self, *, hash: str) -> bytes | StoredObject:
        if hash not in self._objects:
            raise KeyError(f"Object {hash} not found")
        content = self._objects[hash]
        actual_hash = hashlib.sha256(content).hexdigest()
        if actual_hash != hash:
            raise HashMismatchError(f"Hash mismatch: expected {hash}, got {actual_hash}")
        return StoredObject(content=content, content_hash=hash)

class InMemoryRuntimeStateStore:
    def __init__(self) -> None:
        self._leases: dict[str, LeaseToken | None] = {}
        self._fencing_tokens: dict[str, int] = {}
        self._snapshots: dict[str, dict[int, dict[str, Any]]] = {}
        self._latest_version: dict[str, int] = {}

    def acquire_lease(self, run_id: str, *, owner_id: str, ttl_ms: int) -> LeaseToken:
        active_lease = self._leases.get(run_id)
        if active_lease is not None and active_lease.owner_id != owner_id:
            raise LeaseConflictError(f"Lease for run {run_id} is already held by {active_lease.owner_id}")

        token_val = self._fencing_tokens.get(run_id, 0) + 1
        self._fencing_tokens[run_id] = token_val
        token = LeaseToken(
            lease_id=f"lease-{run_id}-{token_val}",
            owner_id=owner_id,
            fencing_token=token_val,
            ttl_ms=ttl_ms,
            safety_margin_ms=0,
        )
        self._leases[run_id] = token
        return token

    def heartbeat(self, run_id: str, *, lease_token: LeaseToken) -> LeaseToken:
        active_lease = self._leases.get(run_id)
        if active_lease is None or active_lease.lease_id != lease_token.lease_id:
            raise LeaseFencingError(f"Lease {lease_token.lease_id} is no longer active for run {run_id}")
        return lease_token

    def snapshot(self, run_id: str, state: dict[str, Any], *, lease_token: LeaseToken) -> StateVersionRef:
        current_token = self._fencing_tokens.get(run_id, 0)
        if lease_token.fencing_token < current_token:
            raise LeaseFencingError(f"Lease is fenced: token {lease_token.fencing_token} < current {current_token}")

        active_lease = self._leases.get(run_id)
        if active_lease is None:
            raise LeaseFencingError(f"Lease {lease_token.lease_id} is no longer active for run {run_id}")
        if active_lease is not None and active_lease.lease_id != lease_token.lease_id:
            raise LeaseFencingError(f"Lease is fenced: active lease is {active_lease.lease_id}")

        version = self._latest_version.get(run_id, 0) + 1
        self._latest_version[run_id] = version
        self._snapshots.setdefault(run_id, {})[version] = state
        return StateVersionRef(run_id=run_id, version=version, fencing_token=lease_token.fencing_token)

    def restore(self, run_id: str, *, state_ref: StateRef | None = None) -> dict[str, Any]:
        if state_ref is None:
            version = self._latest_version.get(run_id, 0)
        else:
            version = state_ref.version
        return self._snapshots.get(run_id, {}).get(version, {})

    def release(self, run_id: str, *, lease_token: LeaseToken) -> None:
        active_lease = self._leases.get(run_id)
        if active_lease is not None and active_lease.lease_id == lease_token.lease_id:
            self._leases[run_id] = None
