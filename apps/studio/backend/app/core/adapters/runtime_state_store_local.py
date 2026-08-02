from __future__ import annotations

import json
import logging
import os
import re
import sys
import threading
import time
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.core.adapters.http_transport import StudioAdapterError

if sys.platform == "win32":
    import msvcrt

    def _platform_lock_file(file: Any) -> None:
        file.seek(0, os.SEEK_END)
        if file.tell() == 0:
            file.write(b"\0")
            file.flush()
        file.seek(0)
        msvcrt.locking(file.fileno(), msvcrt.LK_LOCK, 1)

    def _platform_unlock_file(file: Any) -> None:
        file.seek(0)
        msvcrt.locking(file.fileno(), msvcrt.LK_UNLCK, 1)
else:
    import fcntl

    def _platform_lock_file(file: Any) -> None:
        fcntl.flock(file.fileno(), fcntl.LOCK_EX)

    def _platform_unlock_file(file: Any) -> None:
        fcntl.flock(file.fileno(), fcntl.LOCK_UN)

logger = logging.getLogger(__name__)
_SAFE_RUN_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")


@dataclass
class LeaseToken:
    lease_id: str
    owner_id: str
    fencing_token: int
    ttl_ms: int
    safety_margin_ms: int = 1000


@dataclass
class StateSnapshot:
    run_id: str
    state: dict[str, Any]
    fencing_token: int


class LocalRuntimeStateStore:
    _locks_guard = threading.Lock()
    _locks: dict[str, threading.RLock] = {}

    def __init__(self, root: Path):
        self.root = Path(root)

    def acquire_lease(self, run_id: str, owner_id: str, ttl_ms: int) -> LeaseToken:
        safe_run_id = self._validate_run_id(run_id)
        with self._run_lock(safe_run_id):
            run_dir = self._run_dir(safe_run_id)
            run_dir.mkdir(parents=True, exist_ok=True)
            with self._run_file_lock(run_dir):
                lease_file = run_dir / "lease.json"
                if lease_file.exists():
                    try:
                        with open(lease_file, encoding="utf-8") as f:
                            current = json.load(f)
                    except (OSError, json.JSONDecodeError) as exc:
                        raise self._lease_fenced_error(
                            run_id,
                            action="acquire_lease",
                            detail="Lease could not be read",
                            owner_id=owner_id,
                        ) from exc
                    current_owner = current.get("owner_id")
                    current_ttl_ms = int(current.get("ttl_ms", 0) or 0)
                    current_expires_at_ms = self._lease_expires_at_ms(current)
                    if current_ttl_ms > 0 and (
                        current_expires_at_ms is None or current_expires_at_ms > self._now_ms()
                    ):
                        raise StudioAdapterError(
                            "state.lease_conflict",
                            {
                                "run_id": run_id,
                                "owner_id": owner_id,
                                "active_owner": current_owner,
                                "fencing_token": current.get("fencing_token"),
                                "expires_at_ms": current_expires_at_ms,
                                "detail": "Lease already active; use heartbeat to renew",
                            },
                        )
                next_token = self._next_fencing_token(run_dir)

                lease_id = str(uuid.uuid4())
                acquired_at_ms = self._now_ms()
                lease_data = {
                    "lease_id": lease_id,
                    "owner_id": owner_id,
                    "fencing_token": next_token,
                    "ttl_ms": ttl_ms,
                    "safety_margin_ms": 1000,
                    "acquired_at_ms": acquired_at_ms,
                    "expires_at_ms": acquired_at_ms + max(ttl_ms, 0),
                }

                self._atomic_write_json(lease_file, lease_data)

                return LeaseToken(
                    lease_id=lease_id,
                    owner_id=owner_id,
                    fencing_token=next_token,
                    ttl_ms=ttl_ms,
                    safety_margin_ms=1000,
                )

    def heartbeat(self, run_id: str, lease: LeaseToken) -> LeaseToken:
        safe_run_id = self._validate_run_id(run_id)
        with self._run_lock(safe_run_id):
            run_dir = self._run_dir(safe_run_id)
            run_dir.mkdir(parents=True, exist_ok=True)
            with self._run_file_lock(run_dir):
                lease_file = run_dir / "lease.json"

                data = self._read_matching_lease(safe_run_id, lease, action="heartbeat")

                heartbeat_at_ms = self._now_ms()
                data["ttl_ms"] = lease.ttl_ms
                data["acquired_at_ms"] = heartbeat_at_ms
                data["expires_at_ms"] = heartbeat_at_ms + max(lease.ttl_ms, 0)

                self._atomic_write_json(lease_file, data)

            return lease

    def snapshot(self, run_id: str, state: dict[str, Any], lease: LeaseToken | None) -> StateSnapshot:
        safe_run_id = self._validate_run_id(run_id)
        if lease is None:
            raise StudioAdapterError("state.lease_required", {"detail": "Lease token is required for snapshot"})

        with self._run_lock(safe_run_id):
            run_dir = self._run_dir(safe_run_id)
            run_dir.mkdir(parents=True, exist_ok=True)
            with self._run_file_lock(run_dir):
                self._read_matching_lease(safe_run_id, lease, action="snapshot")

                snapshot_file = run_dir / "snapshot.json"
                snapshot_data = {
                    "run_id": safe_run_id,
                    "state": state,
                    "fencing_token": lease.fencing_token,
                }

                self._atomic_write_json(snapshot_file, snapshot_data)

            return StateSnapshot(
                run_id=safe_run_id,
                state=state,
                fencing_token=lease.fencing_token,
            )

    def restore(self, run_id: str) -> StateSnapshot:
        safe_run_id = self._validate_run_id(run_id)
        snapshot_file = self._run_dir(safe_run_id) / "snapshot.json"
        if not snapshot_file.exists():
            raise StudioAdapterError("state.not_found", {"detail": "Snapshot not found"})

        with open(snapshot_file, encoding="utf-8") as f:
            data = json.load(f)

        if data.get("run_id") != safe_run_id:
            raise StudioAdapterError(
                "state.invalid_run_id",
                {
                    "run_id": data.get("run_id"),
                    "expected_run_id": safe_run_id,
                    "detail": "Snapshot run_id does not match requested run",
                },
            )
        return StateSnapshot(
            run_id=data["run_id"],
            state=data["state"],
            fencing_token=data["fencing_token"],
        )

    def release(self, run_id: str, lease: LeaseToken) -> None:
        safe_run_id = self._validate_run_id(run_id)
        with self._run_lock(safe_run_id):
            run_dir = self._run_dir(safe_run_id)
            run_dir.mkdir(parents=True, exist_ok=True)
            with self._run_file_lock(run_dir):
                lease_file = run_dir / "lease.json"
                if not lease_file.exists():
                    raise self._lease_fenced_error(
                        safe_run_id,
                        lease=lease,
                        action="release",
                        detail="Lease not found",
                    )
                try:
                    data = json.loads(lease_file.read_text(encoding="utf-8"))
                except (OSError, json.JSONDecodeError) as exc:
                    logger.warning(
                        "runtime_state.release run=%s could not read lease, leaving in place: %s",
                        safe_run_id,
                        exc,
                    )
                    raise self._lease_fenced_error(
                        safe_run_id,
                        lease=lease,
                        action="release",
                        detail="Lease could not be read",
                    ) from exc
                self._assert_lease_matches(safe_run_id, lease, data, action="release")
                try:
                    lease_file.unlink()
                except OSError as exc:
                    logger.warning("runtime_state.release run=%s failed to unlink lease: %s", safe_run_id, exc)
                    raise StudioAdapterError(
                        "state.release_failed",
                        {
                            "run_id": safe_run_id,
                            "lease_id": lease.lease_id,
                            "owner_id": lease.owner_id,
                            "fencing_token": lease.fencing_token,
                            "action": "release",
                            "detail": str(exc),
                        },
                    ) from exc

    def restore_checkpointer(self, snapshot: StateSnapshot) -> Any:
        safe_run_id = self._validate_run_id(snapshot.run_id)
        state = snapshot.state if isinstance(snapshot.state, dict) else {}
        checkpointer_arg = state.get("checkpointer_spec")
        if not isinstance(checkpointer_arg, str) or not checkpointer_arg:
            raise self._invalid_checkpointer_error(
                safe_run_id,
                checkpointer_arg,
                detail="Runtime state snapshot is missing checkpointer_spec",
            )
        self._validate_checkpointer_spec(safe_run_id, checkpointer_arg)
        from graph_agent.core.checkpointer import resolve_checkpointer

        checkpointer = resolve_checkpointer(checkpointer_arg)
        if checkpointer is None or checkpointer is True:
            raise StudioAdapterError(
                "state.not_found",
                {
                    "run_id": snapshot.run_id,
                    "detail": "No runtime checkpointer available for restored state",
                },
            )
        return checkpointer

    def latest_checkpoint_state(
        self,
        *,
        run_id: str,
        checkpointer: Any | None = None,
        checkpointer_spec: str | None = None,
    ) -> dict[str, str] | None:
        safe_run_id = self._validate_run_id(run_id)
        active_checkpointer = checkpointer
        if active_checkpointer is None:
            if not isinstance(checkpointer_spec, str) or not checkpointer_spec:
                raise self._invalid_checkpointer_error(
                    safe_run_id,
                    checkpointer_spec,
                    detail="Runtime state snapshot is missing checkpointer_spec",
                )
            self._validate_checkpointer_spec(safe_run_id, checkpointer_spec)
            from graph_agent.core.checkpointer import resolve_checkpointer

            active_checkpointer = resolve_checkpointer(checkpointer_spec)
        if active_checkpointer is None or isinstance(active_checkpointer, bool):
            return None

        checkpoints = list(active_checkpointer.list({"configurable": {"thread_id": safe_run_id}}))
        if not checkpoints:
            return None

        checkpoint = checkpoints[0]
        config = getattr(checkpoint, "config", {}) or {}
        configurable = config.get("configurable", {}) if isinstance(config, dict) else {}
        checkpoint_payload = getattr(checkpoint, "checkpoint", {}) or {}
        checkpoint_id = configurable.get("checkpoint_id") or checkpoint_payload.get("id")
        if checkpoint_id is None:
            return None
        checkpoint_ns = configurable.get("checkpoint_ns", "")
        return {
            "checkpoint_id": str(checkpoint_id),
            "checkpoint_ns": str(checkpoint_ns or ""),
        }

    def _read_matching_lease(self, run_id: str, lease: LeaseToken, *, action: str) -> dict[str, Any]:
        lease_file = self.root / "runs" / run_id / "lease.json"
        if not lease_file.exists():
            raise StudioAdapterError(
                "state.lease_fenced",
                {"run_id": run_id, "lease_id": lease.lease_id, "action": action, "detail": "Lease not found"},
            )

        try:
            with open(lease_file, encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, json.JSONDecodeError) as exc:
            raise StudioAdapterError(
                "state.lease_fenced",
                {
                    "run_id": run_id,
                    "lease_id": lease.lease_id,
                    "action": action,
                    "detail": "Lease could not be read",
                },
            ) from exc

        if not isinstance(data, dict):
            raise StudioAdapterError(
                "state.lease_fenced",
                {
                    "run_id": run_id,
                    "lease_id": lease.lease_id,
                    "action": action,
                    "detail": "Lease record must be an object",
                },
            )

        self._assert_lease_matches(run_id, lease, data, action=action)
        return data

    def _assert_lease_matches(
        self,
        run_id: str,
        lease: LeaseToken,
        data: dict[str, Any],
        *,
        action: str,
    ) -> None:
        if (
            data.get("lease_id") != lease.lease_id
            or data.get("owner_id") != lease.owner_id
            or int(data.get("fencing_token", 0) or 0) != lease.fencing_token
        ):
            raise StudioAdapterError(
                "state.lease_fenced",
                {
                    "run_id": run_id,
                    "lease_id": lease.lease_id,
                    "owner_id": lease.owner_id,
                    "fencing_token": lease.fencing_token,
                    "active_lease_id": data.get("lease_id"),
                    "active_owner": data.get("owner_id"),
                    "active_fencing_token": data.get("fencing_token"),
                    "action": action,
                },
            )

    def _next_fencing_token(self, run_dir: Path) -> int:
        counter_file = run_dir / "fencing_counter.json"
        current_token = 0
        if counter_file.exists():
            with open(counter_file, encoding="utf-8") as f:
                data = json.load(f)
            current_token = int(data.get("fencing_token", 0))

        next_token = current_token + 1
        self._atomic_write_json(counter_file, {"fencing_token": next_token})
        return next_token

    def _atomic_write_json(self, target_file: Path, data: dict[str, Any]) -> None:
        temp_file = target_file.with_name(f".{target_file.name}.{uuid.uuid4().hex}.tmp")
        try:
            with open(temp_file, "w", encoding="utf-8") as f:
                json.dump(data, f)
            temp_file.replace(target_file)
        finally:
            try:
                temp_file.unlink()
            except FileNotFoundError:
                pass

    @contextmanager
    def _run_file_lock(self, run_dir: Path) -> Iterator[None]:
        lock_file = run_dir / ".runtime_state.lock"
        with open(lock_file, "a+b") as f:
            self._lock_file(f)
            try:
                yield
            finally:
                self._unlock_file(f)

    def _lock_file(self, file: Any) -> None:
        _platform_lock_file(file)

    def _unlock_file(self, file: Any) -> None:
        _platform_unlock_file(file)

    def _now_ms(self) -> int:
        return int(time.time() * 1000)

    def _lease_expires_at_ms(self, data: dict[str, Any]) -> int | None:
        raw = data.get("expires_at_ms")
        if raw is None:
            return None
        try:
            return int(raw)
        except (TypeError, ValueError):
            return None

    def _run_lock(self, run_id: str) -> threading.RLock:
        safe_run_id = self._validate_run_id(run_id)
        key = f"{self.root.resolve(strict=False)}:{safe_run_id}"
        with self._locks_guard:
            lock = self._locks.get(key)
            if lock is None:
                lock = threading.RLock()
                self._locks[key] = lock
            return lock

    def _run_dir(self, run_id: str) -> Path:
        safe_run_id = self._validate_run_id(run_id)
        return self.root / "runs" / safe_run_id

    def _validate_run_id(self, run_id: str) -> str:
        if (
            not isinstance(run_id, str)
            or not run_id
            or run_id in {".", ".."}
            or "/" in run_id
            or "\\" in run_id
            or not _SAFE_RUN_ID_RE.fullmatch(run_id)
        ):
            raise StudioAdapterError(
                "state.invalid_run_id",
                {
                    "run_id": run_id,
                    "detail": "run_id must be a safe filesystem segment",
                },
            )
        return run_id

    def _validate_checkpointer_spec(self, run_id: str, checkpointer_spec: str) -> None:
        if not checkpointer_spec.startswith("sqlite:"):
            raise self._invalid_checkpointer_error(
                run_id,
                checkpointer_spec,
                detail="Only per-run SQLite checkpointers are allowed for runtime state restore",
            )
        raw_path = checkpointer_spec.removeprefix("sqlite:")
        if not raw_path or raw_path == ":memory:" or raw_path.startswith("file:"):
            raise self._invalid_checkpointer_error(
                run_id,
                checkpointer_spec,
                detail="SQLite checkpointer must use an absolute per-run database path",
            )

        candidate = Path(raw_path).expanduser()
        if not candidate.is_absolute():
            raise self._invalid_checkpointer_error(
                run_id,
                checkpointer_spec,
                detail="SQLite checkpointer path must be absolute",
            )

        # No containment root is enforced: a skill is a git repo at an arbitrary
        # user-chosen path, so its .workspace/runs/<run_id>/checkpoints.db can be
        # anywhere on disk. The per-run shape check below (exact filename, run_id
        # directory, runs/ parent) plus the existence check are the invariants.
        candidate_resolved = candidate.resolve(strict=False)

        if (
            candidate_resolved.name != "checkpoints.db"
            or candidate_resolved.parent.name != run_id
            or candidate_resolved.parent.parent.name != "runs"
        ):
            raise self._invalid_checkpointer_error(
                run_id,
                checkpointer_spec,
                detail="SQLite checkpointer path must target this run's checkpoints.db",
            )

        if not candidate_resolved.is_file():
            if not candidate_resolved.exists():
                raise StudioAdapterError(
                    "state.not_found",
                    {
                        "run_id": run_id,
                        "checkpointer_spec": checkpointer_spec,
                        "detail": "SQLite checkpointer database not found",
                    },
                )
            raise self._invalid_checkpointer_error(
                run_id,
                checkpointer_spec,
                detail="SQLite checkpointer path must be a file",
            )

    def _invalid_checkpointer_error(self, run_id: str, checkpointer_spec: Any, *, detail: str) -> StudioAdapterError:
        return StudioAdapterError(
            "state.invalid_checkpointer",
            {
                "run_id": run_id,
                "checkpointer_spec": checkpointer_spec,
                "detail": detail,
            },
        )

    def _lease_fenced_error(
        self,
        run_id: str,
        *,
        lease: LeaseToken | None = None,
        action: str,
        detail: str,
        owner_id: str | None = None,
    ) -> StudioAdapterError:
        payload: dict[str, Any] = {
            "run_id": run_id,
            "action": action,
            "detail": detail,
        }
        if lease is not None:
            payload.update(
                {
                    "lease_id": lease.lease_id,
                    "owner_id": lease.owner_id,
                    "fencing_token": lease.fencing_token,
                }
            )
        if owner_id is not None:
            payload["owner_id"] = owner_id
        return StudioAdapterError("state.lease_fenced", payload)
