"""Pausing a run is a state the user chose, and closing the app does not undo it.

``pause_run`` ends the worker on purpose and keeps the checkpoint
(``run_manager.pause_run``: "Stop the worker but leave the run continuable"), so
a paused run has NO worker by design. Liveness reconciliation (ledger C1 ②) was
written to check ``running`` and ``paused`` alike, and "nobody holds the lock"
is trivially true of every paused run — so restarting the sidecar rewrote the
user's deliberate pause as ``abandoned`` and told them "the app closed while it
was going", which is not what happened.

Only ``running`` is a claim about a worker. ``paused`` is a claim about a
checkpoint, and the checkpoint is on disk.

The other half is the ending: a paused run has no worker to kill, so stopping it
is a record operation. It used to require the sidecar's in-memory registry and
answered 409 to any run a previous sidecar had paused — the same one-question-
two-answers shape the reconciliation was added to remove.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

import pytest
from app.models.runs import RunMetadata
from app.services.run_manager import RunManager
from app.services.skills import run_dir_for

SKILL = "text-segmentation"


@pytest.fixture
def paused_run(studio_roots: tuple[Path, Path]) -> Callable[[str], Path]:
    """Leave a run directory exactly as a sidecar that paused a run leaves it.

    Depends on ``studio_roots`` so ``run_dir_for`` resolves inside the test's own
    temporary skills root rather than whatever this machine has installed.
    """
    del studio_roots

    def paused(run_id: str) -> Path:
        run_dir = run_dir_for(SKILL, run_id)
        run_dir.mkdir(parents=True, exist_ok=True)
        metadata = RunMetadata(run_id=run_id, status="paused", started_at=datetime.now(UTC))
        (run_dir / "run_metadata.json").write_text(metadata.persisted_json(), encoding="utf-8")
        return run_dir

    return paused


def _stored_status(run_dir: Path) -> str:
    payload = json.loads((run_dir / "run_metadata.json").read_text(encoding="utf-8"))
    status = payload["status"]
    assert isinstance(status, str)
    return status


def test_a_new_sidecar_leaves_a_paused_run_paused(paused_run: Callable[[str], Path]) -> None:
    run_dir = paused_run("run-paused-before-the-app-closed")

    # A restarted sidecar: same run directory, empty registry, no worker — which
    # is what a paused run looks like even while its own sidecar is alive.
    manager = RunManager()
    row = next(
        run
        for run in manager.list_runs(SKILL).runs
        if run.run_id == "run-paused-before-the-app-closed"
    )

    assert row.status == "paused"
    assert _stored_status(run_dir) == "paused"


@pytest.mark.anyio
async def test_a_paused_run_can_be_ended_by_a_sidecar_that_did_not_pause_it(
    paused_run: Callable[[str], Path],
) -> None:
    """There is no worker to kill, so ending it is a write, not a signal."""
    run_dir = paused_run("run-paused-then-stopped")

    manager = RunManager()
    sealed = await manager.stop_run(SKILL, "run-paused-then-stopped")

    assert sealed.status == "cancelled"
    assert _stored_status(run_dir) == "cancelled"


@pytest.mark.anyio
async def test_a_run_that_does_not_exist_is_reported_as_missing_not_as_finished(
    paused_run: Callable[[str], Path],
) -> None:
    """Stoppability is read from the record, so no record is "no such run".

    It used to answer 409 "neither running nor paused" — a statement about a run
    that is not there to have a status. Reading through ``_metadata_for`` gives
    the same not-found this module already answers everywhere else.
    """
    del paused_run
    manager = RunManager()

    with pytest.raises(Exception, match="RESUME_CHECKPOINT_NOT_FOUND|Run not found"):
        await manager.stop_run(SKILL, "run-that-was-never-here")
