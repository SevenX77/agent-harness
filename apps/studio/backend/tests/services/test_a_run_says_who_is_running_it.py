"""A run that claims to be running can be asked whether it still is.

Measured first (2026-08-21, ledger C1): register a run, then stand up a fresh
``RunManager`` over the same run directory — which is what a restarted sidecar
is, since live runs are held in memory only. The run list answered ``running``
(from the record on disk) while ``pause_run`` answered 409 ``RUN_NOT_RUNNING``
(from the empty registry). Two answers to one question, and the badge spins for
the rest of the session because the record is never corrected.

The record now names its worker by having that worker hold a lock for its whole
life, so the claim is checkable by whoever asks next: lock held means the run
really is going, lock free means the worker is gone and the run ended
``abandoned``.
"""

from __future__ import annotations

import json
import shutil
from collections.abc import Callable, Iterator
from datetime import UTC, datetime
from pathlib import Path

import pytest
from app.models.runs import RunMetadata
from app.services.run_liveness import hold_run_liveness, run_worker_handle, run_worker_is_alive
from app.services.run_manager import RunManager
from app.services.skills import run_dir_for

SKILL = "text-segmentation"


@pytest.fixture
def claim_running() -> Iterator[Callable[[str], Path]]:
    """Leave a run directory exactly as a hard-killed sidecar leaves one, then clear it.

    Cleaning up matters more than usual here: a record left behind reads as a
    real run in every later `list_runs`, and the reconciler will rewrite it.
    """
    made: list[Path] = []

    def claim(run_id: str) -> Path:
        run_dir = run_dir_for(SKILL, run_id)
        run_dir.mkdir(parents=True, exist_ok=True)
        metadata = RunMetadata(run_id=run_id, status="running", started_at=datetime.now(UTC))
        (run_dir / "run_metadata.json").write_text(metadata.persisted_json(), encoding="utf-8")
        made.append(run_dir)
        return run_dir

    yield claim

    for run_dir in made:
        shutil.rmtree(run_dir, ignore_errors=True)


def _stored_status(run_dir: Path) -> str:
    payload = json.loads((run_dir / "run_metadata.json").read_text(encoding="utf-8"))
    status = payload["status"]
    assert isinstance(status, str)
    return status


def test_a_lock_nobody_holds_means_the_worker_is_gone(tmp_path: Path) -> None:
    assert run_worker_is_alive(tmp_path) is False

    with hold_run_liveness(tmp_path):
        assert run_worker_is_alive(tmp_path) is True
        handle = run_worker_handle(tmp_path)
        assert handle is not None and handle.pid > 0

    assert run_worker_is_alive(tmp_path) is False


def test_a_worker_that_dies_without_cleanup_still_releases_its_claim(tmp_path: Path) -> None:
    """The lock is the OS's to release, which is why a kill needs no cleanup path."""
    with pytest.raises(RuntimeError, match="deliberate"):
        with hold_run_liveness(tmp_path):
            raise RuntimeError("deliberate: stands in for a killed worker")

    assert run_worker_is_alive(tmp_path) is False


def test_a_new_sidecar_does_not_keep_reporting_a_run_nobody_is_running(
    claim_running: Callable[[str], Path],
) -> None:
    run_dir = claim_running("run-abandoned-by-its-sidecar")

    # A restarted sidecar: same run directory, empty registry.
    manager = RunManager()
    listed = manager.list_runs(SKILL)
    row = next(run for run in listed.runs if run.run_id == "run-abandoned-by-its-sidecar")

    assert row.status == "abandoned"
    assert _stored_status(run_dir) == "abandoned"


def test_a_run_whose_worker_is_still_holding_on_is_left_alone(
    claim_running: Callable[[str], Path],
) -> None:
    run_dir = claim_running("run-still-held")

    with hold_run_liveness(run_dir):
        manager = RunManager()
        listed = manager.list_runs(SKILL)
        row = next(run for run in listed.runs if run.run_id == "run-still-held")

        assert row.status == "running"
        assert _stored_status(run_dir) == "running"
