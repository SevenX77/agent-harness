"""A run in flight can be paused, and a paused run can be resumed or ended.

The only way to end a run early used to be DELETE, which terminates the worker
and then removes the whole run directory. Two things were missing, not one: the
engine clears a run's checkpoints only when the run finishes on its own, so a
worker halted part-way leaves one behind and the run can be picked up again —
pausing is therefore not an ending. Ending it is the separate, deliberate act.
"""

from __future__ import annotations

import queue
from pathlib import Path
from typing import Any

import pytest
from app.services.run_manager import run_manager
from fastapi.testclient import TestClient

from .test_api import _record_predict_pass, fake_run_worker


class HangingProcess:
    """A worker that starts and then never finishes on its own."""

    def __init__(self, *, target: Any, args: tuple[Any, ...]) -> None:
        self._target = target
        self._args = args
        self.exitcode: int | None = None
        self._alive = False
        self.terminated = False

    def start(self) -> None:
        self._alive = True

    def is_alive(self) -> bool:
        return self._alive

    def join(self, timeout: float | None = None) -> None:
        del timeout

    def terminate(self) -> None:
        self.terminated = True
        self._alive = False
        self.exitcode = -15


def _start_hanging_run(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> str:
    monkeypatch.setattr(run_manager, "process_factory", HangingProcess)
    monkeypatch.setattr(run_manager, "queue_factory", queue.Queue)
    monkeypatch.setattr(run_manager, "worker", fake_run_worker)
    _record_predict_pass("text-segmentation")

    response = client.post(
        "/api/skills/text-segmentation/runs",
        json={"input_data": {"input_text": "hello"}},
    )
    assert response.status_code == 202
    body = response.json()
    assert body["status"] == "running"
    return str(body["run_id"])


def test_pausing_halts_the_worker_and_leaves_the_run_waiting(
    client: TestClient,
    studio_roots: tuple[Path, Path],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    del studio_roots
    run_id = _start_hanging_run(client, monkeypatch)

    response = client.post(f"/api/skills/text-segmentation/runs/{run_id}/pause")

    assert response.status_code == 200
    assert response.json()["status"] == "paused"

    # Pausing is not deleting, which is what DELETE would have done to it.
    listed = client.get("/api/skills/text-segmentation/runs")
    statuses = {run["run_id"]: run["status"] for run in listed.json()["runs"]}
    assert statuses[run_id] == "paused"


def test_pausing_a_run_that_is_not_running_is_rejected(
    client: TestClient,
    studio_roots: tuple[Path, Path],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    del studio_roots
    run_id = _start_hanging_run(client, monkeypatch)
    assert client.post(f"/api/skills/text-segmentation/runs/{run_id}/pause").status_code == 200

    again = client.post(f"/api/skills/text-segmentation/runs/{run_id}/pause")

    assert again.status_code == 409
    assert again.json()["error_code"] == "RUN_NOT_RUNNING"


def test_a_paused_run_can_still_be_ended(
    client: TestClient,
    studio_roots: tuple[Path, Path],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # The two futures of a paused run are resuming it and ending it; ending has to
    # be reachable from paused, not only from running.
    del studio_roots
    run_id = _start_hanging_run(client, monkeypatch)
    assert client.post(f"/api/skills/text-segmentation/runs/{run_id}/pause").status_code == 200

    stopped = client.post(f"/api/skills/text-segmentation/runs/{run_id}/stop")

    assert stopped.status_code == 200
    assert stopped.json()["status"] == "cancelled"


def test_stopping_a_run_in_flight_skips_the_pause(
    client: TestClient,
    studio_roots: tuple[Path, Path],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    del studio_roots
    run_id = _start_hanging_run(client, monkeypatch)

    stopped = client.post(f"/api/skills/text-segmentation/runs/{run_id}/stop")

    assert stopped.status_code == 200
    assert stopped.json()["status"] == "cancelled"
