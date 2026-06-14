from __future__ import annotations

import json
import logging
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.core.adapters.http_transport import StudioAdapterError

logger = logging.getLogger(__name__)


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
    def __init__(self, root: Path):
        self.root = Path(root)

    def acquire_lease(self, run_id: str, owner_id: str, ttl_ms: int) -> LeaseToken:
        run_dir = self.root / "runs" / run_id
        run_dir.mkdir(parents=True, exist_ok=True)
        lease_file = run_dir / "lease.json"
        next_token = self._next_fencing_token(run_dir)

        lease_id = str(uuid.uuid4())
        lease_data = {
            "lease_id": lease_id,
            "owner_id": owner_id,
            "fencing_token": next_token,
            "ttl_ms": ttl_ms,
            "safety_margin_ms": 1000,
        }

        temp_file = lease_file.with_suffix(".tmp")
        with open(temp_file, "w") as f:
            json.dump(lease_data, f)
        temp_file.replace(lease_file)

        return LeaseToken(
            lease_id=lease_id,
            owner_id=owner_id,
            fencing_token=next_token,
            ttl_ms=ttl_ms,
            safety_margin_ms=1000,
        )

    def heartbeat(self, run_id: str, lease: LeaseToken) -> LeaseToken:
        run_dir = self.root / "runs" / run_id
        lease_file = run_dir / "lease.json"

        if not lease_file.exists():
            raise StudioAdapterError("state.lease_fenced", {"detail": "Lease not found on disk"})

        with open(lease_file) as f:
            data = json.load(f)

        if data.get("fencing_token", 0) > lease.fencing_token:
            raise StudioAdapterError("state.lease_fenced", {"detail": "Lease fenced by a newer token"})

        data["ttl_ms"] = lease.ttl_ms

        temp_file = lease_file.with_suffix(".tmp")
        with open(temp_file, "w") as f:
            json.dump(data, f)
        temp_file.replace(lease_file)

        return lease

    def snapshot(self, run_id: str, state: dict[str, Any], lease: LeaseToken | None) -> StateSnapshot:
        if lease is None:
            raise StudioAdapterError("state.lease_required", {"detail": "Lease token is required for snapshot"})

        run_dir = self.root / "runs" / run_id
        run_dir.mkdir(parents=True, exist_ok=True)
        lease_file = run_dir / "lease.json"

        if not lease_file.exists():
            raise StudioAdapterError("state.lease_fenced", {"detail": "No active lease"})

        with open(lease_file) as f:
            data = json.load(f)

        if data.get("fencing_token", 0) > lease.fencing_token:
            raise StudioAdapterError("state.lease_fenced", {"detail": "Snapshot fenced by a newer lease"})

        snapshot_file = run_dir / "snapshot.json"
        snapshot_data = {
            "run_id": run_id,
            "state": state,
            "fencing_token": lease.fencing_token,
        }

        temp_file = snapshot_file.with_suffix(".tmp")
        with open(temp_file, "w") as f:
            json.dump(snapshot_data, f)
        temp_file.replace(snapshot_file)

        return StateSnapshot(
            run_id=run_id,
            state=state,
            fencing_token=lease.fencing_token,
        )

    def restore(self, run_id: str) -> StateSnapshot:
        snapshot_file = self.root / "runs" / run_id / "snapshot.json"
        if not snapshot_file.exists():
            raise StudioAdapterError("state.not_found", {"detail": "Snapshot not found"})

        with open(snapshot_file) as f:
            data = json.load(f)

        return StateSnapshot(
            run_id=data["run_id"],
            state=data["state"],
            fencing_token=data["fencing_token"],
        )

    def release(self, run_id: str, lease: LeaseToken) -> None:
        run_dir = self.root / "runs" / run_id
        lease_file = run_dir / "lease.json"
        if not lease_file.exists():
            return
        try:
            data = json.loads(lease_file.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            # Degrade explicitly and observably (no silent swallow): a corrupt or
            # unreadable lease file is left in place rather than blindly removed.
            logger.warning(
                "runtime_state.release run=%s could not read lease, leaving in place: %s",
                run_id,
                exc,
            )
            return
        if data.get("fencing_token") != lease.fencing_token:
            # A newer owner holds the lease; a stale holder must not release it.
            logger.info(
                "runtime_state.release run=%s skipped: lease held by a newer fencing token",
                run_id,
            )
            return
        try:
            lease_file.unlink()
        except OSError as exc:
            logger.warning("runtime_state.release run=%s failed to unlink lease: %s", run_id, exc)

    def _next_fencing_token(self, run_dir: Path) -> int:
        counter_file = run_dir / "fencing_counter.json"
        current_token = 0
        if counter_file.exists():
            with open(counter_file) as f:
                data = json.load(f)
            current_token = int(data.get("fencing_token", 0))

        next_token = current_token + 1
        temp_file = counter_file.with_suffix(".tmp")
        with open(temp_file, "w") as f:
            json.dump({"fencing_token": next_token}, f)
        temp_file.replace(counter_file)
        return next_token
